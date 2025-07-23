"""
Jina Markdown Agent 核心邏輯 - Plan E 專門版本

專注於單一職責：
1. 使用 Jina Reader Markdown 解析貼文數據
2. 寫入 Redis (Tier-0) 和 PostgreSQL (Tier-1)
3. 標記需要 Vision 補值的貼文

這是 Plan E 架構中的核心 Agent，負責第一階段的數據處理
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

# 僅允許數字 . , K M 的正規表示式
NUM_RE = re.compile(r'^[\d\.,]+[KkMm]?$')

class JinaMarkdownAgent:
    """
    Jina Markdown Agent - Plan E 單一職責版本
    
    專門負責：
    - Markdown 解析和指標提取
    - 雙重存儲（Redis + PostgreSQL）
    - 智能標記需要 Vision 補值的貼文
    """
    
    def __init__(self):
        """初始化 Jina Markdown Agent"""
        # Jina API 設定
        self.base_url = "https://r.jina.ai/{url}"
        self.headers_markdown = {"x-respond-with": "markdown"}
        
        # Redis 和資料庫客戶端
        self.redis_client = get_redis_client()
        
        # 根據新的解析規則，定義更精準的正規表示式
        # 1. 提取觀看數，例如: "[Thread ====== 3.9K views]"
        self.views_pattern = re.compile(
            r"\[Thread\s*======\s*([\d\.,KkMm]+)\s*views\]",
            re.IGNORECASE
        )
        
        # 任務狀態追蹤
        self.active_tasks = {}
    
    def _clean_num(self, s: str) -> str:
        """移除數字字串中的不可見字元，例如 U+FE0F"""
        return re.sub(r'[\u200d\u200c\uFE0F]', '', s)

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
    
    def _extract_metrics_from_markdown(self, md: str) -> Dict[str, Optional[int]]:
        """從 Jina Markdown 中提取互動指標"""
        
        # 1️⃣ 提取 views (從各種可能的 views 格式)
        views = None
        views_patterns = [
            r'Thread\s*=+\s*([\d.,KMB]+)\s*views?',
            r'([\d.,KMB]+)\s*views?',
            r'views?\s*[:\-]?\s*([\d.,KMB]+)'
        ]
        
        for pattern in views_patterns:
            match = re.search(pattern, md, re.IGNORECASE)
            if match:
                views = self._parse_number(match.group(1))
                break
        
        # 2️⃣ 尋找互動數據 - 簡化策略
        # 在 Translate 後尋找連續的數字行
        parts = re.split(r'translate', md, maxsplit=1, flags=re.IGNORECASE)
        after_translate = parts[1] if len(parts) > 1 else ""
        
        # 收集所有數字
        all_numbers = []
        lines = after_translate.splitlines()
        
        for line in lines:
            cleaned = self._clean_num(line.strip())
            if cleaned and re.match(r'^[\d.,KMB]+$', cleaned):
                num = self._parse_number(cleaned)
                if num is not None and num > 0:  # 排除0值
                    all_numbers.append(num)
        
        # 3️⃣ 尋找最可能的互動數據序列
        # 策略：尋找3-4個連續數字的序列
        likes = comments = reposts = shares = None
        
        if len(all_numbers) >= 3:
            # 取前4個數字作為 likes, comments, reposts, shares
            if len(all_numbers) >= 4:
                likes, comments, reposts, shares = all_numbers[0], all_numbers[1], all_numbers[2], all_numbers[3]
            else:  # 3個數字
                likes, comments, reposts = all_numbers[0], all_numbers[1], all_numbers[2]
        elif len(all_numbers) == 2:
            likes, comments = all_numbers[0], all_numbers[1]
        elif len(all_numbers) == 1:
            likes = all_numbers[0]
            
        return {
            'views': views,
            'likes': likes, 
            'comments': comments,
            'reposts': reposts,
            'shares': shares
        }
    
    def _extract_media_urls(self, markdown_text: str) -> Optional[List[str]]:
        """
        從 Markdown 文本提取媒體 URL
        
        Args:
            markdown_text: Markdown 文本
            
        Returns:
            Optional[List[str]]: 媒體 URL 列表，如果沒有則返回 None
        """
        try:
            # 提取圖片 URL
            img_pattern = r'!\[.*?\]\((https?://[^\)]+)\)'
            img_urls = re.findall(img_pattern, markdown_text)
            
            # 提取視頻 URL（如果有的話）
            video_pattern = r'<video[^>]*src=["\']([^"\']+)["\']'
            video_urls = re.findall(video_pattern, markdown_text)
            
            all_urls = img_urls + video_urls
            return all_urls if all_urls else None
            
        except Exception as e:
            print(f"提取媒體 URL 失敗: {e}")
            return None
    
    async def process_single_post_with_storage(
        self, 
        post_url: str, 
        author: str,
        task_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Plan E 核心方法：處理單一貼文並寫入雙重存儲
        
        工作流程：
        1. 調用 Jina Reader Markdown API
        2. 解析指標和內容
        3. 寫入 Redis (Tier-0 快取)
        4. 寫入 PostgreSQL (Tier-1 長期存儲)
        5. 標記是否需要 Vision 補值
        
        Args:
            post_url: 貼文 URL
            author: 作者名稱
            task_id: 任務 ID
            
        Returns:
            Dict[str, Any]: 處理結果
        """
        try:
            # 1. 調用 Jina Reader Markdown API
            jina_url = self.base_url.format(url=post_url)
            response = requests.get(
                jina_url, 
                headers=self.headers_markdown, 
                timeout=30
            )
            response.raise_for_status()
            
            markdown_text = response.text
            
            # 2. 解析指標和媒體
            metrics = self._extract_metrics_from_markdown(markdown_text)
            media_urls = self._extract_media_urls(markdown_text)
            
            # 3. 寫入 Redis (Tier-0) - 指標快取
            redis_success = self.redis_client.set_post_metrics(post_url, metrics)
            
            # 4. 寫入 PostgreSQL (Tier-1) - 長期存儲
            db_client = await get_db_client()
            
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
                    "redis_written": redis_success,
                    "markdown_length": len(markdown_text),
                    "media_count": len(media_urls) if media_urls else 0
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
                "processing_stage": "jina_markdown_completed"
            }
            
        except Exception as e:
            # 記錄錯誤到資料庫
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
    
    async def batch_process_posts_with_storage(
        self, 
        posts: List[PostMetrics], 
        task_id: Optional[str] = None
    ) -> AsyncIterable[Dict[str, Any]]:
        """
        Plan E 批次處理方法：處理多個貼文並寫入存儲
        
        這是 Plan E 工作流的核心方法，負責：
        - 批次處理 Crawler 提供的 URL
        - 寫入雙重存儲
        - 為需要 Vision 補值的貼文建立佇列
        
        Args:
            posts: PostMetrics 列表（來自 Crawler Agent）
            task_id: 任務 ID
            
        Yields:
            Dict[str, Any]: 處理進度和結果
        """
        try:
            total_posts = len(posts)
            processed_count = 0
            success_count = 0
            vision_needed_count = 0
            
            yield stream_status(TaskState.RUNNING, f"開始 Jina Markdown 批次處理 {total_posts} 個貼文")
            
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
            
            # 需要 Vision 補值的 URL 列表
            vision_queue_urls = []
            
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
                    
                    # 檢查是否需要 Vision 補值
                    if result.get("needs_vision", False):
                        vision_needed_count += 1
                        vision_queue_urls.append(post.url)
                    
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
                    
                    # 避免過於頻繁的 API 調用
                    await asyncio.sleep(0.2)
                    
                except Exception as e:
                    processed_count += 1
                    yield stream_text(f"處理貼文失敗 {post.url}: {str(e)}")
                    continue
            
            # 批次添加到 Vision 處理佇列
            if vision_queue_urls:
                queued_count = self.redis_client.push_to_queue("vision_fill", vision_queue_urls)
                yield stream_text(f"已將 {queued_count} 個需要 Vision 補值的貼文加入佇列")
            
            # 完成處理
            completion_rate = success_count / total_posts if total_posts > 0 else 0
            
            final_result = {
                "agent": "jina_markdown",
                "total_posts": total_posts,
                "success_count": success_count,
                "vision_needed_count": vision_needed_count,
                "completion_rate": completion_rate,
                "processing_time": (datetime.utcnow() - self.active_tasks.get(task_id, {}).get("start_time", datetime.utcnow())).total_seconds() if task_id else 0,
                "next_stage": "vision_fill" if vision_needed_count > 0 else "ranking",
                "vision_queue_length": self.redis_client.get_queue_length("vision_fill")
            }
            
            if task_id:
                self.active_tasks[task_id]["status"] = "completed"
                self.active_tasks[task_id]["final_result"] = final_result
            
            yield stream_data(final_result, final=True)
            
        except Exception as e:
            error_msg = f"Jina Markdown 批次處理失敗: {str(e)}"
            
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
    
    async def health_check(self) -> Dict[str, Any]:
        """健康檢查"""
        try:
            # 測試 Jina Reader 連線
            test_url = "https://r.jina.ai/https://www.threads.com"
            response = requests.get(
                test_url, 
                headers=self.headers_markdown, 
                timeout=10
            )
            
            # 檢查 Redis 連接
            redis_health = self.redis_client.health_check()
            
            # 檢查資料庫連接
            db_client = await get_db_client()
            db_health = await db_client.health_check()
            
            overall_status = "healthy" if all([
                response.status_code == 200,
                redis_health.get("status") == "healthy",
                db_health.get("status") == "healthy"
            ]) else "unhealthy"
            
            return {
                "status": overall_status,
                "service": "Jina Markdown Agent",
                "components": {
                    "jina_reader": "available" if response.status_code == 200 else "unavailable",
                    "redis": redis_health,
                    "database": db_health
                },
                "active_tasks": len(self.active_tasks)
            }
                
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": f"Jina Markdown Agent 健康檢查失敗: {str(e)}"
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
    return await agent.health_check()