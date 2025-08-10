"""
Vision Agent 核心邏輯

使用 RustFS + Gemini 2.0 Flash 處理社交媒體圖片和影片分析
從 Playwright 爬蟲獲取的媒體 URL 進行下載、存儲和分析
"""

import os
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime

from .gemini_vision import GeminiVisionAnalyzer
from common.db_client import get_db_client
# 使用同步取得客戶端的介面，避免在 __init__ 中持有 coroutine 導致健康檢查報錯
from common.rustfs_client import get_rustfs_client

# 輕量定義以避免依賴不存在的 common.models
from dataclasses import dataclass
from enum import Enum
from typing import Any

class TaskState(str, Enum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

@dataclass
class AgentResponse:
    task_state: TaskState
    data: Any
    message: str
    artifacts: dict


class VisionAgent:
    """Vision Agent - 使用 RustFS + Gemini Vision 分析媒體內容"""
    
    def __init__(self):
        """初始化 Vision Agent"""
        self.gemini_analyzer = GeminiVisionAnalyzer()
        self.rustfs_client = get_rustfs_client()
        
        # 配置參數
        self.top_n_posts = int(os.getenv("MEDIA_TOP_N_POSTS", "5"))
    
    async def process_post_media(self, post_id: str) -> AgentResponse:
        """
        處理單一貼文的媒體分析
        
        Args:
            post_id: 貼文 ID
            
        Returns:
            AgentResponse 包含分析結果
        """
        try:
            db_client = await get_db_client()
            
            # 1. 從資料庫獲取貼文的媒體 URL
            media_urls = await db_client.get_post_media_urls(post_id)
            
            if not media_urls:
                return AgentResponse(
                    task_state=TaskState.COMPLETED,
                    data=None,
                    message=f"貼文 {post_id} 沒有媒體內容",
                    artifacts={"post_id": post_id, "media_count": 0}
                )
            
            # 2. 處理每個媒體檔案
            analysis_results = []
            
            for media_url in media_urls:
                try:
                    # 下載媒體
                    media_bytes, mime_type = await self.rustfs_client.download_media(media_url)
                    
                    # 存儲到 RustFS
                    storage_result = await self.rustfs_client.store_media(
                        post_id, media_bytes, mime_type
                    )
                    
                    # 使用 Gemini 分析
                    metrics = await self.gemini_analyzer.analyze_media(media_bytes, mime_type)
                    
                    # 記錄到資料庫
                    await db_client.insert_media_record(
                        post_id=post_id,
                        media_type='video' if mime_type.startswith('video/') else 'image',
                        cdn_url=media_url,
                        storage_key=storage_result['storage_key'],
                        status='analyzed',
                        size_bytes=storage_result['size_bytes']
                    )
                    
                    analysis_results.append({
                        "media_url": media_url,
                        "storage_key": storage_result['storage_key'],
                        "metrics": metrics,
                        "mime_type": mime_type
                    })
                    
                except Exception as media_error:
                    analysis_results.append({
                        "media_url": media_url,
                        "error": str(media_error),
                        "status": "failed"
                    })
                    continue
            
            # 3. 合併所有媒體的分析結果（取最大值）
            combined_metrics = self._combine_media_metrics(analysis_results)
            
            # 4. 更新貼文指標
            await db_client.update_post_metrics(post_id, combined_metrics)
            
            return AgentResponse(
                task_state=TaskState.COMPLETED,
                data=combined_metrics,
                message=f"成功分析貼文 {post_id} 的 {len(media_urls)} 個媒體檔案",
                artifacts={
                    "post_id": post_id,
                    "media_count": len(media_urls),
                    "analysis_results": analysis_results
                }
            )
            
        except Exception as e:
            return AgentResponse(
                task_state=TaskState.FAILED,
                data=None,
                message=f"媒體分析失敗: {str(e)}",
                artifacts={
                    "post_id": post_id,
                    "error": str(e)
                }
            )
    
    def _combine_media_metrics(self, analysis_results: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        合併多個媒體的分析結果
        
        Args:
            analysis_results: 分析結果列表
            
        Returns:
            合併後的指標
        """
        combined = {
            "views": 0,
            "likes": 0,
            "comments": 0,
            "reposts": 0,
            "shares": 0
        }
        
        for result in analysis_results:
            if "metrics" in result:
                metrics = result["metrics"]
                for key in combined.keys():
                    # 取最大值（假設多個媒體中最高的數字最準確）
                    combined[key] = max(combined[key], metrics.get(key, 0))
        
        return combined
    
    async def batch_process_posts(self, post_ids: List[str]) -> List[AgentResponse]:
        """
        批次處理多個貼文的媒體分析
        
        Args:
            post_ids: 貼文 ID 列表
            
        Returns:
            AgentResponse 列表
        """
        results = []
        
        for post_id in post_ids:
            try:
                result = await self.process_post_media(post_id)
                results.append(result)
                
                # 避免過於頻繁的 API 調用
                await asyncio.sleep(0.5)
                
            except Exception as e:
                results.append(AgentResponse(
                    task_state=TaskState.FAILED,
                    data=None,
                    message=f"批次處理失敗: {str(e)}",
                    artifacts={
                        "post_id": post_id,
                        "error": str(e)
                    }
                ))
        
        return results
    
    async def process_top_ranked_posts(self) -> AgentResponse:
        """
        處理排名前 N 的貼文媒體分析
        
        Returns:
            AgentResponse 包含處理結果
        """
        try:
            db_client = await get_db_client()
            
            # 獲取排名前 N 的貼文
            top_posts = await db_client.get_top_ranked_posts(limit=self.top_n_posts)
            
            if not top_posts:
                return AgentResponse(
                    task_state=TaskState.COMPLETED,
                    data=None,
                    message="沒有找到需要處理的貼文",
                    artifacts={"top_n_posts": self.top_n_posts}
                )
            
            # 批次處理
            post_ids = [post['post_id'] for post in top_posts]
            results = await self.batch_process_posts(post_ids)
            
            # 統計結果
            success_count = sum(1 for r in results if r.task_state == TaskState.COMPLETED)
            
            return AgentResponse(
                task_state=TaskState.COMPLETED,
                data={
                    "processed_count": len(results),
                    "success_count": success_count,
                    "top_n_posts": self.top_n_posts
                },
                message=f"成功處理 {success_count}/{len(results)} 個排名前 {self.top_n_posts} 的貼文",
                artifacts={
                    "results": results,
                    "post_ids": post_ids
                }
            )
            
        except Exception as e:
            return AgentResponse(
                task_state=TaskState.FAILED,
                data=None,
                message=f"處理排名貼文失敗: {str(e)}",
                artifacts={"error": str(e)}
            )
    
    async def health_check(self) -> Dict[str, Any]:
        """健康檢查"""
        try:
            # 檢查 Gemini Vision
            gemini_health = self.gemini_analyzer.health_check()
            
            # 檢查 RustFS
            rustfs_health = self.rustfs_client.health_check()
            
            # 檢查資料庫連接
            db_client = await get_db_client()
            db_health = await db_client.health_check()
            
            overall_status = "healthy" if all([
                gemini_health.get("status") == "healthy",
                rustfs_health.get("status") == "healthy",
                db_health.get("status") == "healthy"
            ]) else "unhealthy"
            
            return {
                "status": overall_status,
                "service": "Vision Agent",
                "components": {
                    "gemini_vision": gemini_health,
                    "rustfs": rustfs_health,
                    "database": db_health
                },
                "config": {
                    "top_n_posts": self.top_n_posts
                }
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": f"Vision Agent 健康檢查失敗: {str(e)}"
            }


# 便利函數
def create_vision_agent() -> VisionAgent:
    """創建 Vision Agent 實例"""
    return VisionAgent()


async def process_post_media(post_id: str) -> AgentResponse:
    """處理貼文媒體的便利函數"""
    agent = create_vision_agent()
    return await agent.process_post_media(post_id)


async def process_top_ranked_posts() -> AgentResponse:
    """處理排名前 N 貼文的便利函數"""
    agent = create_vision_agent()
    return await agent.process_top_ranked_posts()


async def batch_process_posts(post_ids: List[str]) -> List[AgentResponse]:
    """批次處理貼文的便利函數"""
    agent = create_vision_agent()
    return await agent.batch_process_posts(post_ids)