#!/usr/bin/env python3
"""
Reader Processor Service - 批量處理Reader請求

負責：
1. 接收URL列表批量處理請求
2. 並行調用Reader服務集群
3. 聚合結果並更新數據庫狀態
4. 提供重試和錯誤處理機制
"""

import asyncio
import aiohttp
import async_timeout
import uuid
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
import sys
import os

# 添加專案根目錄到 Python 路徑
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from common.models import PostMetrics
from common.history import CrawlHistoryDAO
from common.settings import get_settings

app = FastAPI(
    title="Reader Processor Service",
    version="1.0.0",
    description="批量處理Reader請求的協調服務"
)

# 配置
READER_LB_URL = "http://reader-lb:80"
MAX_CONCURRENT_REQUESTS = 10  # 最大並發請求數
DEFAULT_TIMEOUT = 60  # 默認超時時間（秒）

class ReaderRequest(BaseModel):
    """Reader處理請求"""
    urls: List[str] = Field(..., description="要處理的URL列表")
    username: str = Field(..., description="目標用戶名")
    task_id: Optional[str] = Field(None, description="任務ID")
    timeout: int = Field(DEFAULT_TIMEOUT, description="超時時間（秒）")
    return_format: str = Field("text", description="返回格式: text/markdown/json")

class ReaderResult(BaseModel):
    """單個Reader處理結果"""
    url: str
    status: str  # success/failed/timeout
    content: Optional[str] = None
    title: Optional[str] = None
    error: Optional[str] = None
    processing_time: Optional[float] = None
    processed_at: datetime

class ReaderBatchResponse(BaseModel):
    """批量Reader處理響應"""
    task_id: str
    username: str
    total_urls: int
    successful: int
    failed: int
    results: List[ReaderResult]
    total_time: float
    completed_at: datetime

class ReaderProcessor:
    """Reader處理器核心邏輯"""
    
    def __init__(self):
        self.history_dao = CrawlHistoryDAO()
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    
    async def process_url(self, session: aiohttp.ClientSession, url: str, timeout: int, return_format: str) -> ReaderResult:
        """處理單個URL"""
        start_time = asyncio.get_event_loop().time()
        
        async with self.semaphore:
            try:
                # 構建Reader請求URL
                reader_url = f"{READER_LB_URL}/{url}"
                
                headers = {
                    "X-Return-Format": return_format,
                    "User-Agent": "Social-Media-Content-Generator/1.0"
                }
                
                async with async_timeout.timeout(timeout):
                    async with session.get(reader_url, headers=headers) as response:
                        processing_time = asyncio.get_event_loop().time() - start_time
                        
                        if response.status == 200:
                            content = await response.text()
                            
                            # 嘗試解析標題（如果是JSON格式）
                            title = None
                            if return_format == "json":
                                try:
                                    json_data = json.loads(content)
                                    title = json_data.get("title")
                                    content = json_data.get("content", content)
                                except json.JSONDecodeError:
                                    pass
                            
                            return ReaderResult(
                                url=url,
                                status="success",
                                content=content,
                                title=title,
                                processing_time=processing_time,
                                processed_at=datetime.utcnow()
                            )
                        else:
                            error_text = await response.text()
                            return ReaderResult(
                                url=url,
                                status="failed",
                                error=f"HTTP {response.status}: {error_text}",
                                processing_time=processing_time,
                                processed_at=datetime.utcnow()
                            )
                            
            except asyncio.TimeoutError:
                processing_time = asyncio.get_event_loop().time() - start_time
                return ReaderResult(
                    url=url,
                    status="timeout",
                    error=f"Request timeout after {timeout}s",
                    processing_time=processing_time,
                    processed_at=datetime.utcnow()
                )
            except Exception as e:
                processing_time = asyncio.get_event_loop().time() - start_time
                return ReaderResult(
                    url=url,
                    status="failed",
                    error=str(e),
                    processing_time=processing_time,
                    processed_at=datetime.utcnow()
                )
    
    async def process_batch(self, request: ReaderRequest) -> ReaderBatchResponse:
        """批量處理URLs"""
        task_id = request.task_id or str(uuid.uuid4())
        start_time = asyncio.get_event_loop().time()
        
        logging.info(f"🚀 [Task: {task_id}] 開始批量Reader處理: {len(request.urls)} 個URLs")
        
        # 創建HTTP會話
        connector = aiohttp.TCPConnector(
            limit=MAX_CONCURRENT_REQUESTS * 2,
            ttl_dns_cache=300,
            use_dns_cache=True
        )
        
        async with aiohttp.ClientSession(connector=connector) as session:
            # 並行處理所有URLs
            tasks = [
                self.process_url(session, url, request.timeout, request.return_format)
                for url in request.urls
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=False)
        
        # 統計結果
        successful = sum(1 for r in results if r.status == "success")
        failed = len(results) - successful
        total_time = asyncio.get_event_loop().time() - start_time
        
        logging.info(f"✅ [Task: {task_id}] Reader處理完成: {successful}/{len(results)} 成功")
        
        return ReaderBatchResponse(
            task_id=task_id,
            username=request.username,
            total_urls=len(request.urls),
            successful=successful,
            failed=failed,
            results=results,
            total_time=total_time,
            completed_at=datetime.utcnow()
        )
    
    async def update_database_status(self, results: List[ReaderResult], username: str):
        """根據Reader結果更新數據庫狀態"""
        
        post_updates = []
        
        for result in results:
            if result.status == "success" and result.content:
                # 提取post_id
                post_id = result.url.split('/')[-1]
                full_post_id = f"{username}_{post_id}"
                
                # 創建PostMetrics對象用於更新
                post_metrics = PostMetrics(
                    post_id=full_post_id,
                    username=username,
                    url=result.url,
                    content=result.content,
                    created_at=datetime.utcnow(),
                    fetched_at=datetime.utcnow(),
                    source="reader",
                    processing_stage="reader_completed",
                    is_complete=False,  # Reader只提供內容，不算完整
                    reader_status="success",
                    reader_processed_at=result.processed_at
                )
                
                post_updates.append(post_metrics)
            
            elif result.status in ["failed", "timeout"]:
                # 標記Reader處理失敗
                post_id = result.url.split('/')[-1]
                full_post_id = f"{username}_{post_id}"
                
                post_metrics = PostMetrics(
                    post_id=full_post_id,
                    username=username,
                    url=result.url,
                    created_at=datetime.utcnow(),
                    fetched_at=datetime.utcnow(),
                    source="reader",
                    processing_stage="reader_failed",
                    is_complete=False,
                    reader_status="failed",
                    reader_processed_at=result.processed_at
                )
                
                post_updates.append(post_metrics)
        
        # 批量更新數據庫
        if post_updates:
            saved_count = await self.history_dao.upsert_posts(post_updates)
            logging.info(f"📊 Reader狀態更新完成: {saved_count}/{len(post_updates)} 筆記錄")
            return saved_count
        
        return 0

# 全局處理器實例
processor = ReaderProcessor()

@app.get("/health")
async def health_check():
    """健康檢查"""
    try:
        # 檢查Reader LB連通性
        async with aiohttp.ClientSession() as session:
            async with async_timeout.timeout(5):
                async with session.get(f"{READER_LB_URL}/health") as response:
                    if response.status == 200:
                        return {
                            "status": "healthy",
                            "service": "Reader Processor",
                            "reader_lb": "connected"
                        }
                    else:
                        return {
                            "status": "unhealthy",
                            "service": "Reader Processor",
                            "reader_lb": f"HTTP {response.status}"
                        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "service": "Reader Processor",
            "reader_lb": f"error: {str(e)}"
        }

@app.post("/process", response_model=ReaderBatchResponse)
async def process_reader_batch(request: ReaderRequest, background_tasks: BackgroundTasks):
    """
    批量處理Reader請求
    
    處理流程：
    1. 並行調用Reader服務處理所有URLs
    2. 聚合結果並返回
    3. 背景更新數據庫狀態
    """
    try:
        # 主要處理
        response = await processor.process_batch(request)
        
        # 背景任務：更新數據庫狀態
        background_tasks.add_task(
            processor.update_database_status,
            response.results,
            request.username
        )
        
        return response
        
    except Exception as e:
        logging.error(f"❌ Reader批量處理失敗: {e}")
        raise HTTPException(status_code=500, detail=f"Reader處理失敗: {str(e)}")

@app.post("/process-sync", response_model=ReaderBatchResponse)
async def process_reader_batch_sync(request: ReaderRequest):
    """
    批量處理Reader請求（同步更新數據庫）
    
    與 /process 的區別：會等待數據庫更新完成才返回
    """
    try:
        # 主要處理
        response = await processor.process_batch(request)
        
        # 同步更新數據庫狀態
        await processor.update_database_status(response.results, request.username)
        
        return response
        
    except Exception as e:
        logging.error(f"❌ Reader批量處理（同步）失敗: {e}")
        raise HTTPException(status_code=500, detail=f"Reader處理失敗: {str(e)}")

@app.get("/status/{task_id}")
async def get_task_status(task_id: str):
    """
    獲取任務狀態（未來可擴展）
    目前返回基本信息
    """
    return {
        "task_id": task_id,
        "message": "Task status tracking not implemented yet"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8009)