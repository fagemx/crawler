"""
Crawler Agent 核心邏輯

基於 Apify curious_coder/threads-scraper 的簡化爬蟲實現
只抓取貼文 URL，不處理其他複雜數據
"""

import asyncio
import time
from datetime import datetime
from typing import List, Dict, Any, Optional, AsyncIterable
from dataclasses import dataclass
from apify_client import ApifyClient
import httpx

from common.settings import get_settings
from common.a2a import stream_text, stream_data, stream_status, stream_error, TaskState


@dataclass
class PostURL:
    """簡化的貼文 URL 數據模型"""
    url: str
    post_id: str
    username: str
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        return {
            "url": self.url,
            "post_id": self.post_id,
            "username": self.username
        }


class CrawlerLogic:
    """簡化的爬蟲邏輯核心類別 - 只抓取貼文 URL"""
    
    def __init__(self):
        self.settings = get_settings()
        self.apify_client = ApifyClient(token=self.settings.apify.token)
        self.active_tasks: Dict[str, Dict] = {}
        # 使用 apify-threads-scraper.md 指定的 Actor
        self.threads_actor = "curious_coder/threads-scraper"
    
    async def fetch_threads_post_urls(
        self, 
        username: str, 
        max_posts: int = 10,
        task_id: Optional[str] = None
    ) -> AsyncIterable[Dict[str, Any]]:
        """
        簡化的 Threads 貼文 URL 抓取方法
        
        基於 apify-threads-scraper.md 的範例：
        - 使用 curious_coder/threads-scraper Actor
        - 輸入用戶名稱（格式：@username）
        - 只返回貼文 URL
        - 預設抓取 10 則貼文
        """
        start_time = time.time()
        
        try:
            yield stream_status(TaskState.RUNNING, f"開始抓取 @{username} 的貼文 URL，目標 {max_posts} 則")
            
            # 根據 apify-threads-scraper.md 的範例準備輸入參數
            run_input = {
                "urls": [f"@{username}"],  # 格式：@username
                "postsPerSource": max_posts,  # 每個來源的貼文數量
            }
            
            # 記錄任務狀態
            if task_id:
                self.active_tasks[task_id] = {
                    "status": "running",
                    "progress": 0.0,
                    "posts_collected": 0,
                    "start_time": start_time
                }
            
            yield stream_text(f"調用 Apify Actor: {self.threads_actor}")
            
            # 執行 Apify Actor
            run = await self._run_apify_actor(run_input)
            
            yield stream_status(TaskState.RUNNING, "Apify Actor 執行中，等待結果...")
            
            # 等待執行完成並獲取結果
            raw_posts = await self._get_apify_results(run, task_id)
            
            # 處理和提取 URL
            post_urls = []
            for i, raw_post in enumerate(raw_posts):
                try:
                    post_url = self._extract_post_url(raw_post, username)
                    if post_url:
                        post_urls.append(post_url)
                    
                    # 更新進度
                    progress = (i + 1) / len(raw_posts)
                    if task_id:
                        self.active_tasks[task_id]["progress"] = progress
                        self.active_tasks[task_id]["posts_collected"] = len(post_urls)
                    
                    yield stream_status(
                        TaskState.RUNNING, 
                        f"處理貼文 {i + 1}/{len(raw_posts)}", 
                        progress
                    )
                    
                except Exception as e:
                    yield stream_text(f"處理貼文時發生錯誤: {str(e)}")
                    continue
            
            processing_time = time.time() - start_time
            
            # 返回最終結果
            result = {
                "post_urls": [post.to_dict() for post in post_urls],
                "total_count": len(post_urls),
                "processing_time": processing_time,
                "username": username,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # 更新任務狀態
            if task_id:
                self.active_tasks[task_id]["status"] = "completed"
                self.active_tasks[task_id]["progress"] = 1.0
            
            yield stream_data(result, final=True)
            
        except Exception as e:
            error_msg = f"抓取貼文 URL 失敗: {str(e)}"
            
            if task_id:
                self.active_tasks[task_id]["status"] = "failed"
                self.active_tasks[task_id]["error"] = error_msg
            
            yield stream_error(error_msg)
    
    async def _run_apify_actor(self, run_input: Dict[str, Any]) -> Dict[str, Any]:
        """執行 Apify Actor"""
        try:
            # 同步調用 Apify Client（因為 apify-client 不支援 async）
            loop = asyncio.get_event_loop()
            run = await loop.run_in_executor(
                None,
                lambda: self.apify_client.actor(self.threads_actor).call(run_input=run_input)
            )
            return run
            
        except Exception as e:
            raise Exception(f"Apify Actor 執行失敗: {str(e)}")
    
    async def _get_apify_results(self, run: Dict[str, Any], task_id: Optional[str] = None) -> List[Dict]:
        """獲取 Apify 執行結果"""
        try:
            dataset_id = run.get('defaultDatasetId')
            if not dataset_id:
                raise Exception("無法獲取 Apify 結果數據集 ID")
            
            # 獲取數據集內容
            loop = asyncio.get_event_loop()
            items = await loop.run_in_executor(
                None,
                lambda: list(self.apify_client.dataset(dataset_id).iterate_items())
            )
            
            return items
            
        except Exception as e:
            raise Exception(f"獲取 Apify 結果失敗: {str(e)}")
    
    def _extract_post_url(self, raw_data: Dict[str, Any], username: str) -> Optional[PostURL]:
        """
        從 Apify 回傳的數據中提取貼文 URL
        
        基於 apify-threads-scraper.md 的數據格式：
        - id: 貼文的唯一識別碼
        - code: 貼文的短代碼
        - 構建 Threads URL: https://www.threads.net/@{username}/post/{code}
        """
        try:
            # 從 apify-threads-scraper.md 的範例數據格式提取
            post_id = raw_data.get('id', '')
            code = raw_data.get('code', '')
            
            if not code:
                # 如果沒有 code，嘗試從 id 中提取
                if '_' in post_id:
                    code = post_id.split('_')[0]
                else:
                    code = post_id
            
            if not code:
                return None
            
            # 構建 Threads 貼文 URL（基於用戶提供的範例格式）
            # 範例：https://www.threads.com/@09johan24/post/DMaHMSqTdFs
            url = f"https://www.threads.com/@{username}/post/{code}"
            
            return PostURL(
                url=url,
                post_id=post_id,
                username=username
            )
            
        except Exception as e:
            print(f"提取貼文 URL 時發生錯誤: {e}")
            return None
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """獲取任務狀態"""
        return self.active_tasks.get(task_id)
    
    def cleanup_completed_tasks(self, max_age_hours: int = 24):
        """清理已完成的任務"""
        current_time = time.time()
        tasks_to_remove = []
        
        for task_id, task_info in self.active_tasks.items():
            task_age = current_time - task_info.get('start_time', current_time)
            if task_age > max_age_hours * 3600:  # 轉換為秒
                tasks_to_remove.append(task_id)
        
        for task_id in tasks_to_remove:
            del self.active_tasks[task_id]
    
    async def health_check(self) -> Dict[str, Any]:
        """健康檢查"""
        try:
            # 檢查 Apify Token 是否有效
            if not self.settings.apify.token:
                return {
                    "status": "unhealthy",
                    "error": "Apify Token 未設置"
                }
            
            # 簡單的 API 連通性測試
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.apify.com/v2/users/me",
                    headers={"Authorization": f"Bearer {self.settings.apify.token}"},
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    return {
                        "status": "healthy",
                        "apify_connection": "ok",
                        "active_tasks": len(self.active_tasks)
                    }
                else:
                    return {
                        "status": "unhealthy",
                        "error": f"Apify API 回應錯誤: {response.status_code}"
                    }
                    
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": f"健康檢查失敗: {str(e)}"
            }