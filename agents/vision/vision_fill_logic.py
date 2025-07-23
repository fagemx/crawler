"""
Vision Fill Agent 核心邏輯 - Plan E 版本

專注於單一職責：補完 Jina Markdown Agent 無法提取的指標
- 從 Redis 佇列獲取需要補值的 URL
- 使用 Jina Screenshot + Gemini Vision 分析
- 更新 Redis 和 PostgreSQL 中的指標
- 不存儲 Screenshot bytes（用完即丟）
"""

import os
import asyncio
from typing import Dict, Any, Optional, List, AsyncIterable
from datetime import datetime

from .screenshot_utils import JinaScreenshotCapture
from common.redis_client import get_redis_client
from common.db_client import get_db_client
from common.a2a import stream_text, stream_status, stream_data, stream_error, TaskState


class VisionFillAgent:
    """Vision Fill Agent - Plan E 單一職責版本"""
    
    def __init__(self):
        """初始化 Vision Fill Agent"""
        self.screenshot_capture = JinaScreenshotCapture()
        self.redis_client = get_redis_client()
        
        # Gemini API Key
        self.gemini_api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not self.gemini_api_key:
            raise ValueError("需要設定 GOOGLE_API_KEY 或 GEMINI_API_KEY 環境變數")
        
        # 任務狀態追蹤
        self.active_tasks = {}
    
    async def fill_single_missing_metrics(self, url: str) -> Dict[str, Any]:
        """
        補值單一貼文的缺失指標
        
        Args:
            url: 貼文 URL
            
        Returns:
            Dict[str, Any]: 補值結果
        """
        try:
            # 1. 從 Redis 獲取現有指標
            existing_metrics = self.redis_client.get_post_metrics(url)
            
            if not existing_metrics:
                raise Exception(f"Redis 中未找到貼文指標: {url}")
            
            # 2. 檢查哪些指標缺失
            missing_fields = [k for k, v in existing_metrics.items() if v == 0 or v is None]
            
            if not missing_fields:
                return {
                    "url": url,
                    "status": "no_missing_fields",
                    "existing_metrics": existing_metrics,
                    "vision_used": False
                }
            
            # 3. 使用 Vision 分析補值
            try:
                # 獲取截圖並分析（不存儲 bytes）
                image_bytes = self.screenshot_capture.get_screenshot_bytes(url)
                vision_metrics = self.screenshot_capture.analyze_with_vision(
                    image_bytes, 
                    self.gemini_api_key
                )
                
                # 4. 合併指標（優先保留現有非零值）
                updated_metrics = existing_metrics.copy()
                for field in missing_fields:
                    if field in vision_metrics and vision_metrics[field] is not None:
                        updated_metrics[field] = vision_metrics[field]
                
                # 5. 更新 Redis
                redis_success = self.redis_client.set_post_metrics(url, updated_metrics)
                
                # 6. 更新 PostgreSQL
                db_client = await get_db_client()
                await db_client.upsert_metrics(
                    url=url,
                    views=updated_metrics.get("views"),
                    likes=updated_metrics.get("likes"),
                    comments=updated_metrics.get("comments"),
                    reposts=updated_metrics.get("reposts"),
                    shares=updated_metrics.get("shares")
                )
                
                # 7. 記錄處理日誌
                await db_client.log_processing(
                    url=url,
                    agent_name="vision_fill",
                    stage="vision_analysis",
                    status="completed",
                    metadata={
                        "missing_fields_before": missing_fields,
                        "fields_filled": [f for f in missing_fields if f in vision_metrics],
                        "vision_metrics": vision_metrics,
                        "redis_updated": redis_success
                    }
                )
                
                return {
                    "url": url,
                    "status": "completed",
                    "missing_fields_before": missing_fields,
                    "fields_filled": [f for f in missing_fields if f in vision_metrics],
                    "updated_metrics": updated_metrics,
                    "vision_used": True,
                    "redis_success": redis_success
                }
                
            except Exception as vision_error:
                # Vision 分析失敗，記錄錯誤但不中斷流程
                db_client = await get_db_client()
                await db_client.log_processing(
                    url=url,
                    agent_name="vision_fill",
                    stage="vision_analysis",
                    status="failed",
                    error_msg=str(vision_error)
                )
                
                return {
                    "url": url,
                    "status": "vision_failed",
                    "missing_fields": missing_fields,
                    "existing_metrics": existing_metrics,
                    "error": str(vision_error),
                    "vision_used": False
                }
                
        except Exception as e:
            return {
                "url": url,
                "status": "failed",
                "error": str(e),
                "vision_used": False
            }
    
    async def batch_fill_missing_metrics(
        self, 
        urls: List[str], 
        task_id: Optional[str] = None
    ) -> AsyncIterable[Dict[str, Any]]:
        """
        批次補值缺失指標
        
        Args:
            urls: URL 列表
            task_id: 任務 ID
            
        Yields:
            Dict[str, Any]: 處理進度和結果
        """
        try:
            total_urls = len(urls)
            processed_count = 0
            success_count = 0
            vision_used_count = 0
            
            yield stream_status(TaskState.RUNNING, f"開始批次補值 {total_urls} 個貼文的缺失指標")
            
            # 更新任務狀態
            if task_id:
                self.active_tasks[task_id] = {
                    "status": "running",
                    "total": total_urls,
                    "processed": 0,
                    "success": 0,
                    "vision_used": 0,
                    "start_time": datetime.utcnow()
                }
            
            for i, url in enumerate(urls):
                try:
                    yield stream_text(f"補值貼文 {i+1}/{total_urls}: {url}")
                    
                    # 補值單一貼文
                    result = await self.fill_single_missing_metrics(url)
                    
                    processed_count += 1
                    
                    if result["status"] in ["completed", "no_missing_fields"]:
                        success_count += 1
                    
                    if result.get("vision_used", False):
                        vision_used_count += 1
                    
                    # 更新進度
                    progress = processed_count / total_urls
                    
                    if task_id:
                        self.active_tasks[task_id].update({
                            "processed": processed_count,
                            "success": success_count,
                            "vision_used": vision_used_count,
                            "progress": progress
                        })
                    
                    yield stream_status(
                        TaskState.RUNNING,
                        f"已補值 {processed_count}/{total_urls}，成功 {success_count}，使用 Vision {vision_used_count}",
                        progress
                    )
                    
                    # 避免過於頻繁的 API 調用
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    processed_count += 1
                    yield stream_text(f"補值貼文失敗 {url}: {str(e)}")
                    continue
            
            # 完成處理
            completion_rate = success_count / total_urls if total_urls > 0 else 0
            
            final_result = {
                "total_urls": total_urls,
                "success_count": success_count,
                "vision_used_count": vision_used_count,
                "completion_rate": completion_rate,
                "processing_time": (datetime.utcnow() - self.active_tasks.get(task_id, {}).get("start_time", datetime.utcnow())).total_seconds() if task_id else 0,
                "next_stage": "ranking"
            }
            
            if task_id:
                self.active_tasks[task_id]["status"] = "completed"
                self.active_tasks[task_id]["final_result"] = final_result
            
            yield stream_data(final_result, final=True)
            
        except Exception as e:
            error_msg = f"批次補值失敗: {str(e)}"
            
            if task_id:
                self.active_tasks[task_id]["status"] = "failed"
                self.active_tasks[task_id]["error"] = error_msg
            
            yield stream_error(error_msg)
    
    async def process_vision_queue(
        self, 
        queue_name: str = "vision_fill", 
        batch_size: int = 10,
        task_id: Optional[str] = None
    ) -> AsyncIterable[Dict[str, Any]]:
        """
        處理 Redis 佇列中的視覺補值任務
        
        Args:
            queue_name: 佇列名稱
            batch_size: 批次大小
            task_id: 任務 ID
            
        Yields:
            Dict[str, Any]: 處理進度和結果
        """
        try:
            yield stream_status(TaskState.RUNNING, f"開始處理 {queue_name} 佇列")
            
            total_processed = 0
            
            while True:
                # 從佇列獲取項目
                urls = self.redis_client.pop_from_queue(queue_name, batch_size)
                
                if not urls:
                    yield stream_text("佇列已空，處理完成")
                    break
                
                yield stream_text(f"從佇列獲取 {len(urls)} 個項目進行處理")
                
                # 批次處理
                batch_results = []
                async for result in self.batch_fill_missing_metrics(urls, task_id):
                    if result.get("type") == "data" and result.get("final"):
                        batch_results.append(result["content"])
                    yield result
                
                total_processed += len(urls)
                
                # 檢查是否還有更多項目
                remaining = self.redis_client.get_queue_length(queue_name)
                
                yield stream_status(
                    TaskState.RUNNING,
                    f"已處理 {total_processed} 個項目，佇列剩餘 {remaining} 個"
                )
                
                if remaining == 0:
                    break
            
            # 完成處理
            final_result = {
                "queue_name": queue_name,
                "total_processed": total_processed,
                "queue_remaining": self.redis_client.get_queue_length(queue_name),
                "status": "completed"
            }
            
            yield stream_data(final_result, final=True)
            
        except Exception as e:
            error_msg = f"處理佇列失敗: {str(e)}"
            yield stream_error(error_msg)
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """獲取任務狀態"""
        return self.active_tasks.get(task_id)
    
    def cleanup_completed_tasks(self, max_age_hours: int = 24):
        """清理已完成的任務"""
        current_time = datetime.utcnow()
        tasks_to_remove = []
        
        for task_id, task_info in self.active_tasks.items():
            if "start_time" in task_info:
                task_age = current_time - task_info["start_time"]
                if task_age.total_seconds() > max_age_hours * 3600:
                    tasks_to_remove.append(task_id)
        
        for task_id in tasks_to_remove:
            del self.active_tasks[task_id]
    
    async def health_check(self) -> Dict[str, Any]:
        """健康檢查"""
        try:
            # 檢查 Jina Screenshot
            jina_health = self.screenshot_capture.health_check()
            
            # 檢查 Gemini API Key
            gemini_configured = bool(self.gemini_api_key)
            
            # 檢查 Redis 連接
            redis_health = self.redis_client.health_check()
            
            # 檢查資料庫連接
            db_client = await get_db_client()
            db_health = await db_client.health_check()
            
            overall_status = "healthy" if all([
                jina_health.get("status") == "healthy",
                gemini_configured,
                redis_health.get("status") == "healthy",
                db_health.get("status") == "healthy"
            ]) else "unhealthy"
            
            return {
                "status": overall_status,
                "service": "Vision Fill Agent",
                "components": {
                    "jina_screenshot": jina_health,
                    "gemini_api_key": gemini_configured,
                    "redis": redis_health,
                    "database": db_health
                },
                "active_tasks": len(self.active_tasks)
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": f"Vision Fill Agent 健康檢查失敗: {str(e)}"
            }


# 便利函數
def create_vision_fill_agent() -> VisionFillAgent:
    """創建 Vision Fill Agent 實例"""
    return VisionFillAgent()


async def fill_missing_metrics(urls: List[str], task_id: str = None) -> AsyncIterable[Dict[str, Any]]:
    """補值缺失指標的便利函數"""
    agent = create_vision_fill_agent()
    async for result in agent.batch_fill_missing_metrics(urls, task_id):
        yield result


async def process_vision_queue(queue_name: str = "vision_fill", batch_size: int = 10) -> AsyncIterable[Dict[str, Any]]:
    """處理視覺佇列的便利函數"""
    agent = create_vision_fill_agent()
    async for result in agent.process_vision_queue(queue_name, batch_size):
        yield result