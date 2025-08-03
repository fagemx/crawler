#!/usr/bin/env python3
"""
Crawl Coordinator Service - 統一爬蟲協調器

實現你要求的「先快後全」雙軌爬蟲流程：
1. fast: 只使用Reader快速提取
2. full: 只使用Playwright完整爬取  
3. hybrid: 先Reader立即返回，背景Playwright補完

支持的工作流程：
- 用戶選擇帳號和模式
- 即時返回可用數據
- 背景補完詳細數據
- 前端實時更新狀態
"""

import asyncio
import aiohttp
import uuid
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
import sys
import os

# 添加專案根目錄到 Python 路徑
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from common.models import PostMetrics, PostMetricsBatch
from common.history import CrawlHistoryDAO
from common.settings import get_settings

app = FastAPI(
    title="Crawl Coordinator Service", 
    version="1.0.0",
    description="統一爬蟲協調器 - 支援快速/完整/混合模式"
)

# 服務端點配置
READER_PROCESSOR_URL = "http://reader-processor:8009"
PLAYWRIGHT_CRAWLER_URL = "http://playwright-crawler-agent:8006"

class CrawlRequest(BaseModel):
    """統一爬蟲請求"""
    username: str = Field(..., description="要爬取的用戶名")
    max_posts: int = Field(default=20, description="最大貼文數量")
    mode: str = Field(default="hybrid", description="爬取模式: fast/full/hybrid")
    also_slow: bool = Field(default=True, description="hybrid模式是否啟用背景完整爬取")
    auth_json_content: Optional[Dict[str, Any]] = Field(None, description="認證信息")
    task_id: Optional[str] = Field(None, description="任務ID")

class CrawlResponse(BaseModel):
    """統一爬蟲響應"""
    task_id: str
    username: str
    mode: str
    status: str  # immediate/processing/completed
    message: str
    posts: List[Dict[str, Any]]
    summary: Dict[str, Any]
    estimated_completion: Optional[datetime] = None

class CrawlCoordinator:
    """爬蟲協調器核心邏輯"""
    
    def __init__(self):
        self.history_dao = CrawlHistoryDAO()
    
    async def get_urls_for_processing(self, username: str, max_posts: int) -> List[str]:
        """獲取需要處理的URLs"""
        try:
            # 方法1: 從數據庫獲取已知URLs
            existing_status = await self.history_dao.get_posts_status(username)
            existing_urls = [item['url'] for item in existing_status[:max_posts]]
            
            if existing_urls:
                logging.info(f"📋 從數據庫獲取 {username} 的 {len(existing_urls)} 個URLs")
                return existing_urls
            
            # 方法2: 調用Playwright Crawler的URL端點（如果可用）
            async with aiohttp.ClientSession() as session:
                url_endpoint = f"{PLAYWRIGHT_CRAWLER_URL}/urls/{username}?max_posts={max_posts}"
                async with session.get(url_endpoint) as response:
                    if response.status == 200:
                        data = await response.json()
                        urls = [item['url'] for item in data['urls']]
                        logging.info(f"🔗 從Playwright獲取 {username} 的 {len(urls)} 個URLs")
                        return urls
            
            logging.warning(f"⚠️ 無法獲取 {username} 的URLs")
            return []
            
        except Exception as e:
            logging.error(f"❌ 獲取URLs失敗: {e}")
            return []
    
    async def process_fast_mode(self, request: CrawlRequest) -> CrawlResponse:
        """快速模式：只使用Reader"""
        task_id = request.task_id or str(uuid.uuid4())
        
        # 獲取URLs
        urls = await self.get_urls_for_processing(request.username, request.max_posts)
        if not urls:
            raise HTTPException(status_code=404, detail=f"找不到用戶 {request.username} 的貼文URLs")
        
        # 檢查哪些需要Reader處理
        existing_status = await self.history_dao.get_posts_status(request.username)
        status_map = {item['url']: item for item in existing_status}
        
        need_reader_urls = [
            url for url in urls 
            if url not in status_map or status_map[url]['reader_status'] != 'success'
        ]
        
        if not need_reader_urls:
            # 所有URLs都已經有Reader結果
            posts = [
                {
                    "url": url,
                    "post_id": status_map[url]['post_id'],
                    "reader_status": status_map[url]['reader_status'],
                    "dom_status": status_map[url]['dom_status'],
                    "content": "已快取" if status_map[url]['has_content'] else None
                }
                for url in urls if url in status_map
            ]
            
            return CrawlResponse(
                task_id=task_id,
                username=request.username,
                mode="fast",
                status="completed",
                message=f"所有 {len(posts)} 篇貼文已有Reader結果",
                posts=posts,
                summary={"from_cache": len(posts), "processed": 0}
            )
        
        # 調用Reader Processor
        async with aiohttp.ClientSession() as session:
            reader_request = {
                "urls": need_reader_urls,
                "username": request.username,
                "task_id": task_id,
                "return_format": "text"
            }
            
            async with session.post(f"{READER_PROCESSOR_URL}/process", json=reader_request) as response:
                if response.status == 200:
                    reader_result = await response.json()
                    
                    # 構建響應
                    posts = []
                    for result in reader_result['results']:
                        posts.append({
                            "url": result['url'],
                            "post_id": result['url'].split('/')[-1],
                            "reader_status": result['status'],
                            "dom_status": "pending",
                            "content": result.get('content'),
                            "processing_time": result.get('processing_time')
                        })
                    
                    return CrawlResponse(
                        task_id=task_id,
                        username=request.username,
                        mode="fast",
                        status="completed",
                        message=f"Reader處理完成: {reader_result['successful']}/{reader_result['total_urls']} 成功",
                        posts=posts,
                        summary={
                            "successful": reader_result['successful'],
                            "failed": reader_result['failed'],
                            "total_time": reader_result['total_time']
                        }
                    )
                else:
                    error_text = await response.text()
                    raise HTTPException(status_code=500, detail=f"Reader處理失敗: {error_text}")
    
    async def process_full_mode(self, request: CrawlRequest) -> CrawlResponse:
        """完整模式：只使用Playwright Crawler"""
        task_id = request.task_id or str(uuid.uuid4())
        
        if not request.auth_json_content:
            raise HTTPException(status_code=400, detail="完整模式需要提供認證信息")
        
        # 調用Playwright Crawler
        async with aiohttp.ClientSession() as session:
            playwright_request = {
                "username": request.username,
                "max_posts": request.max_posts,
                "auth_json_content": request.auth_json_content,
                "task_id": task_id
            }
            
            async with session.post(f"{PLAYWRIGHT_CRAWLER_URL}/v1/playwright/crawl", json=playwright_request) as response:
                if response.status == 200:
                    crawler_result = await response.json()
                    
                    # 轉換格式
                    posts = []
                    for post in crawler_result['posts']:
                        posts.append({
                            "url": post['url'],
                            "post_id": post['post_id'],
                            "reader_status": post.get('reader_status', 'success'),
                            "dom_status": post.get('dom_status', 'success'),
                            "content": post.get('content'),
                            "likes_count": post.get('likes_count'),
                            "views_count": post.get('views_count'),
                            "images": post.get('images', []),
                            "videos": post.get('videos', [])
                        })
                    
                    return CrawlResponse(
                        task_id=task_id,
                        username=request.username,
                        mode="full",
                        status="completed",
                        message=f"完整爬取完成: {len(posts)} 篇貼文",
                        posts=posts,
                        summary={
                            "total_count": crawler_result['total_count'],
                            "processing_stage": crawler_result.get('processing_stage')
                        }
                    )
                else:
                    error_text = await response.text()
                    raise HTTPException(status_code=500, detail=f"Playwright爬取失敗: {error_text}")
    
    async def process_hybrid_mode(self, request: CrawlRequest, background_tasks: BackgroundTasks) -> CrawlResponse:
        """混合模式：先快後全"""
        task_id = request.task_id or str(uuid.uuid4())
        
        # 第1階段：快速Reader處理
        fast_request = CrawlRequest(
            username=request.username,
            max_posts=request.max_posts,
            mode="fast",
            task_id=f"{task_id}_fast"
        )
        
        fast_response = await self.process_fast_mode(fast_request)
        
        # 第2階段：背景Playwright補完（如果有認證信息且啟用also_slow）
        if request.also_slow and request.auth_json_content:
            background_tasks.add_task(
                self.background_full_crawl,
                request.username,
                request.max_posts,
                request.auth_json_content,
                f"{task_id}_full"
            )
            
            return CrawlResponse(
                task_id=task_id,
                username=request.username,
                mode="hybrid",
                status="processing",
                message=f"快速結果已返回，背景補完進行中",
                posts=fast_response.posts,
                summary={
                    **fast_response.summary,
                    "background_processing": True
                },
                estimated_completion=datetime.utcnow()
            )
        else:
            return CrawlResponse(
                task_id=task_id,
                username=request.username,
                mode="hybrid",
                status="completed",
                message="只有快速結果（未啟用背景補完）",
                posts=fast_response.posts,
                summary=fast_response.summary
            )
    
    async def background_full_crawl(self, username: str, max_posts: int, auth_json_content: Dict[str, Any], task_id: str):
        """背景執行完整爬取"""
        try:
            logging.info(f"🔄 [Task: {task_id}] 開始背景完整爬取: {username}")
            
            async with aiohttp.ClientSession() as session:
                playwright_request = {
                    "username": username,
                    "max_posts": max_posts,
                    "auth_json_content": auth_json_content,
                    "task_id": task_id
                }
                
                async with session.post(f"{PLAYWRIGHT_CRAWLER_URL}/v1/playwright/crawl", json=playwright_request) as response:
                    if response.status == 200:
                        result = await response.json()
                        logging.info(f"✅ [Task: {task_id}] 背景爬取完成: {result['total_count']} 篇貼文")
                    else:
                        error_text = await response.text()
                        logging.error(f"❌ [Task: {task_id}] 背景爬取失敗: {error_text}")
                        
        except Exception as e:
            logging.error(f"❌ [Task: {task_id}] 背景爬取異常: {e}")

# 全局協調器實例
coordinator = CrawlCoordinator()

@app.get("/health")
async def health_check():
    """健康檢查"""
    return {
        "status": "healthy",
        "service": "Crawl Coordinator",
        "supported_modes": ["fast", "full", "hybrid"]
    }

@app.post("/crawl", response_model=CrawlResponse)
async def unified_crawl(request: CrawlRequest, background_tasks: BackgroundTasks):
    """
    統一爬蟲端點
    
    支持模式：
    - fast: 只使用Reader快速提取內容
    - full: 只使用Playwright完整爬取（需要認證）
    - hybrid: 先Reader快速返回，背景Playwright補完
    """
    try:
        if request.mode == "fast":
            return await coordinator.process_fast_mode(request)
        elif request.mode == "full":
            return await coordinator.process_full_mode(request)
        elif request.mode == "hybrid":
            return await coordinator.process_hybrid_mode(request, background_tasks)
        else:
            raise HTTPException(status_code=400, detail=f"不支持的模式: {request.mode}")
            
    except Exception as e:
        logging.error(f"❌ 爬蟲協調失敗: {e}")
        raise HTTPException(status_code=500, detail=f"爬蟲處理失敗: {str(e)}")

@app.get("/status/{username}")
async def get_user_status(username: str):
    """獲取用戶貼文處理狀態摘要"""
    try:
        summary = await coordinator.history_dao.get_processing_needs(username)
        posts_status = await coordinator.history_dao.get_posts_status(username)
        
        return {
            "username": username,
            "summary": summary,
            "recent_posts": posts_status[:10]  # 最近10篇
        }
    except Exception as e:
        logging.error(f"❌ 獲取狀態失敗: {e}")
        raise HTTPException(status_code=500, detail=f"狀態查詢失敗: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8008)