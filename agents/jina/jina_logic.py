"""
Jina Markdown Agent 核心邏輯 - Plan E 重構版

專注於單一職責：
1. 使用 Jina Reader Markdown 解析貼文數據
2. 寫入 Redis (Tier-0) 和 PostgreSQL (Tier-1)
3. 標記需要 Vision 補值的貼文

不再包含 Vision 整合，符合 Plan E 的單一職責原則
"""

import re
import requests
import asyncio
from typing import Dict, Any, Optional, List, AsyncIterable
from datetime import datetime

from common.models import PostMetrics, PostMetricsBatch, TaskState
from common.redis_client import get_redis_client
from common.db_client import get_db_client
from common.a2a import stream_text, stream_status, stream_data, stream_error


class JinaMarkdownAgent:
    """Jina Markdown Agent - Plan E 單一職責版本"""
    
    def __init__(self):
        """初始化 Jina Markdown Agent"""
        # Jina API 設定
        self.base_url = "https://r.jina.ai/{url}"
        self.headers_markdown = {"x-respond-with": "markdown"}
        
        # Redis 和資料庫客戶端
        self.redis_client = get_redis_client()
        
        # 正則表達式模式
        self.metrics_pattern = re.compile(
            r'\*\*?Thread.*? (?P<views>[\d\.KM,]+) views.*?'
            r'愛心.*? (?P<likes>[\d\.KM,]*) .*?'
            r'留言.*? (?P<comments>[\d\.KM,]*) .*?'
            r'轉發.*? (?P<reposts>[\d\.KM,]*) .*?'
            r'分享.*? (?P<shares>[\d\.KM,]*)', 
            re.S
        )
        
        # 任務狀態追蹤
        self.active_tasks = {}
    
    def _parse_number(self, text: str) -> Optional[int]:
        """解析數字字串（支援 K, M 後綴）"""
        if not text:
            return None
        
        text = text.strip()
        if not text:
            return None
            
        try:
            if text.lower().endswith(('k', 'K')):
                return int(float(text[:-1]) * 1_000)
            elif text.lower().endswith(('m', 'M')):
                return int(float(text[:-1]) * 1_000_000)
            else:
                return int(text.replace(',', ''))
        except (ValueError, TypeError):
            return None
    
    def get_markdown_metrics(self, post_url: str) -> Dict[str, Optional[int]]:
        """從 Markdown 解析貼文指標"""
        try:
            jina_url = self.base_url.format(url=post_url)
            response = requests.get(
                jina_url, 
                headers=self.headers_markdown, 
                timeout=30
            )
            response.raise_for_status()
            
            markdown_text = response.text
            match = self.metrics_pattern.search(markdown_text)
            
            if not match:
                return {
                    "views": None,
                    "likes": None, 
                    "comments": None,
                    "reposts": None,
                    "shares": None
                }
            
            groups = match.groupdict()
            return {
                "views": self._parse_number(groups.get("views")),
                "likes": self._parse_number(groups.get("likes")),
                "comments": self._parse_number(groups.get("comments")),
                "reposts": self._parse_number(groups.get("reposts")),
                "shares": self._parse_number(groups.get("shares"))
            }
            
        except Exception as e:
            raise Exception(f"Markdown 解析失敗 {post_url}: {str(e)}")
    
    async def process_single_post_with_storage(
        self, 
        post_url: str, 
        author: str,
        task_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Plan E 核心方法：處理單一貼文並寫入 Redis + PostgreSQL
        
        Args:
            post_url: 貼文 URL
            author: 作者名稱
            task_id: 任務 ID
            
        Returns:
            Dict[str, Any]: 處理結果
        """
        try:
            # 1. 獲取 Markdown 內容和指標
            jina_url = self.base_url.format(url=post_url)
            response = requests.get(
                jina_url, 
                headers=self.headers_markdown, 
                timeout=30
            )
            response.raise_for_status()
            
            markdown_text = response.text
            
            # 2. 解析指標
            metrics = self._extract_metrics_from_markdown(markdown_text)
            
            # 3. 寫入 Redis (Tier-0)
            redis_success = self.redis_client.set_post_metrics(post_url, metrics)
            
            # 4. 寫入 PostgreSQL (Tier-1)
            db_client = await get_db_client()
            
            # 提取媒體 URL（簡單實現）
            media_urls = self._extract_media_urls(markdown_text)
            
            # 插入貼文基本資料
            await db_client.upsert_post(
                url=post_url,
                author=author,
                markdown=markdown_text,
                media_urls=media_urls
            )
            
            # 插入指標
            await db_client.upsert_metrics(
                url=post_url,
                views=metrics.get("views"),
                likes=metrics.get("likes"),
                comments=metrics.get("comments"),
                reposts=metrics.get("reposts"),
                shares=metrics.get("shares")
            )
            
            # 5. 檢查是否需要 Vision 補值
            missing_fields = [k for k, v in metrics.items() if v is None]
            needs_vision = len(missing_fields) > 0
            
            # 6. 記錄處理日誌
            await db_client.log_processing(
                url=post_url,
                agent_name="jina_markdown",
                stage="markdown_extraction",
                status="completed" if not needs_vision else "needs_vision",
                metadata={
                    "metrics_extracted": len([v for v in metrics.values() if v is not None]),
                    "missing_fields": missing_fields,
                    "redis_written": redis_success
                }
            )
            
            return {
                "url": post_url,
                "metrics": metrics,
                "markdown_length": len(markdown_text),
                "media_urls_count": len(media_urls) if media_urls else 0,
                "needs_vision": needs_vision,
                "missing_fields": missing_fields,
                "redis_success": redis_success,
                "processing_stage": "jina_completed"
            }
            
        except Exception as e:
            # 記錄錯誤
            try:
                db_client = await get_db_client()
                await db_client.log_processing(
                    url=post_url,
                    agent_name="jina_markdown",
                    stage="markdown_extraction",
                    status="failed",
                    error_msg=str(e)
                )
            except:
                pass
            
            raise Exception(f"處理貼文失敗 {post_url}: {str(e)}")
    
    def _extract_metrics_from_markdown(self, markdown_text: str) -> Dict[str, Optional[int]]:
        """從 Markdown 文本提取指標"""
        match = self.metrics_pattern.search(markdown_text)
        
        if not match:
            return {
                "views": None,
                "likes": None, 
                "comments": None,
                "reposts": None,
                "shares": None
            }
        
        groups = match.groupdict()
        return {
            "views": self._parse_number(groups.get("views")),
            "likes": self._parse_number(groups.get("likes")),
            "comments": self._parse_number(groups.get("comments")),
            "reposts": self._parse_number(groups.get("reposts")),
            "shares": self._parse_number(groups.get("shares"))
        }
    
    def _extract_media_urls(self, markdown_text: str) -> Optional[List[str]]:
        """從 Markdown 文本提取媒體 URL（簡單實現）"""
        try:
            # 簡單的圖片 URL 提取
            import re
            img_pattern = r'!\[.*?\]\((https?://[^\)]+)\)'
            urls = re.findall(img_pattern, markdown_text)
            return urls if urls else None
        except:
            return None

    async def enrich_batch(self, batch: PostMetricsBatch) -> PostMetricsBatch:
        """
        Plan F 核心方法：接收一個可能不完整的 batch，
        使用 Jina Reader 進行資料豐富化和後備填補。
        """
        for post in batch.posts:
            try:
                # 1. 呼叫 Jina API (這部分邏輯可以複用)
                jina_url = self.base_url.format(url=post.url)
                response = requests.get(jina_url, headers=self.headers_markdown, timeout=30)
                response.raise_for_status()
                markdown_text = response.text

                # 2. 從 Markdown 中解析所有 Jina 能找到的指標
                jina_metrics = self._extract_metrics_from_markdown(markdown_text)

                # 3. 執行「補洞」邏輯
                
                # 任務 1: 無條件更新/填補 views
                if jina_metrics.get("views") is not None:
                    post.views_count = jina_metrics["views"]
                
                # 任務 2: 檢查 Playwright 提供的四大指標是否缺失，如果缺失，才用 Jina 的值
                if post.likes_count is None and jina_metrics.get("likes") is not None:
                    post.likes_count = jina_metrics["likes"]
                
                if post.comments_count is None and jina_metrics.get("comments") is not None:
                    post.comments_count = jina_metrics["comments"]

                if post.reposts_count is None and jina_metrics.get("reposts") is not None:
                    post.reposts_count = jina_metrics["reposts"]
                
                if post.shares_count is None and jina_metrics.get("shares") is not None:
                    post.shares_count = jina_metrics["shares"]

                # 4. 更新貼文的處理狀態
                post.processing_stage = "jina_enriched"
                post.last_updated = datetime.utcnow()

            except Exception as e:
                # 如果 Jina 處理失敗，保持原樣，僅記錄錯誤
                print(f"Jina enrich 失敗 for {post.url}: {e}")
                continue # 繼續處理下一個 post
        
        # 返回被 Jina "加持" 過的 batch
        batch.processing_stage = "jina_completed"
        return batch

    async def batch_process_posts_with_storage(
        self, 
        posts: List[PostMetrics], 
        task_id: Optional[str] = None
    ) -> AsyncIterable[Dict[str, Any]]:
        """
        Plan E 批次處理方法：處理多個貼文並寫入存儲
        
        Args:
            posts: PostMetrics 列表
            task_id: 任務 ID
            
        Yields:
            Dict[str, Any]: 處理進度和結果
        """
        try:
            total_posts = len(posts)
            processed_count = 0
            success_count = 0
            vision_needed_count = 0
            
            yield stream_status(TaskState.RUNNING, f"開始批次處理 {total_posts} 個貼文")
            
            # 更新任務狀態
            if task_id:
                self.active_tasks[task_id] = {
                    "status": "running",
                    "total": total_posts,
                    "processed": 0,
                    "success": 0,
                    "vision_needed": 0,
                    "start_time": datetime.utcnow()
                }
            
            for i, post in enumerate(posts):
                try:
                    yield stream_text(f"處理貼文 {i+1}/{total_posts}: {post.url}")
                    
                    # 處理單一貼文
                    result = await self.process_single_post_with_storage(
                        post_url=post.url,
                        author=post.username,
                        task_id=task_id
                    )
                    
                    processed_count += 1
                    success_count += 1
                    
                    if result.get("needs_vision", False):
                        vision_needed_count += 1
                        # 添加到 Vision 處理佇列
                        self.redis_client.push_to_queue("vision_fill", [post.url])
                    
                    # 更新進度
                    progress = processed_count / total_posts
                    
                    if task_id:
                        self.active_tasks[task_id].update({
                            "processed": processed_count,
                            "success": success_count,
                            "vision_needed": vision_needed_count,
                            "progress": progress
                        })
                    
                    yield stream_status(
                        TaskState.RUNNING,
                        f"已處理 {processed_count}/{total_posts}，成功 {success_count}，需要 Vision {vision_needed_count}",
                        progress
                    )
                    
                except Exception as e:
                    processed_count += 1
                    yield stream_text(f"處理貼文失敗 {post.url}: {str(e)}")
                    continue
            
            # 完成處理
            completion_rate = success_count / total_posts if total_posts > 0 else 0
            
            final_result = {
                "total_posts": total_posts,
                "success_count": success_count,
                "vision_needed_count": vision_needed_count,
                "completion_rate": completion_rate,
                "processing_time": (datetime.utcnow() - self.active_tasks.get(task_id, {}).get("start_time", datetime.utcnow())).total_seconds() if task_id else 0,
                "next_stage": "vision_fill" if vision_needed_count > 0 else "ranking"
            }
            
            if task_id:
                self.active_tasks[task_id]["status"] = "completed"
                self.active_tasks[task_id]["final_result"] = final_result
            
            yield stream_data(final_result, final=True)
            
        except Exception as e:
            error_msg = f"批次處理失敗: {str(e)}"
            
            if task_id:
                self.active_tasks[task_id]["status"] = "failed"
                self.active_tasks[task_id]["error"] = error_msg
            
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
    
    def health_check(self) -> Dict[str, Any]:
        """健康檢查"""
        try:
            # 測試 Jina Reader 連線
            test_url = "https://r.jina.ai/https://www.threads.com"
            response = requests.get(
                test_url, 
                headers=self.headers_markdown, 
                timeout=10
            )
            
            if response.status_code == 200:
                return {
                    "status": "healthy",
                    "service": "Jina Agent",
                    "jina_reader": "available"
                }
            else:
                return {
                    "status": "unhealthy",
                    "error": f"Jina Reader 回應異常: {response.status_code}"
                }
                
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": f"Jina Agent 健康檢查失敗: {str(e)}"
            }


# Plan E 便利函數
def create_jina_markdown_agent() -> JinaMarkdownAgent:
    """創建 Jina Markdown Agent 實例"""
    return JinaMarkdownAgent()


async def process_posts_batch(posts: List[PostMetrics], task_id: str = None) -> AsyncIterable[Dict[str, Any]]:
    """批次處理貼文的便利函數"""
    agent = create_jina_markdown_agent()
    async for result in agent.batch_process_posts_with_storage(posts, task_id):
        yield result


async def health_check() -> Dict[str, Any]:
    """健康檢查便利函數"""
    agent = create_jina_markdown_agent()
    return agent.health_check()