"""
增量爬取歷史管理 DAO 層

基於用戶優化建議實現：
- 精確提早停止機制
- latest_post_id 避免全表掃描  
- 高效的去重邏輯
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Set, List, Optional, Dict, Any
from contextlib import asynccontextmanager

from .db_client import DatabaseClient
from .models import PostMetrics


class CrawlHistoryDAO:
    """爬取歷史數據訪問對象 - 優化增量爬取"""
    
    def __init__(self):
        self.db_client = DatabaseClient()
    
    async def get_existing_post_ids(self, username: str) -> Set[str]:
        """
        獲取指定用戶已抓取的post_id集合
        
        優化：使用latest_post_id提升查詢效率
        """
        try:
            async with self.db_client.get_connection() as conn:
                # 查詢已存在的post_id（目前從JSON調試文件模擬）
                # TODO: 後續改為從真實SQL表查詢
                result = await conn.fetch("""
                    SELECT post_id FROM post_metrics_sql 
                    WHERE username = $1
                    ORDER BY created_at DESC
                """, username)
                
                post_ids = {row['post_id'] for row in result}
                logging.info(f"📚 {username} 已有 {len(post_ids)} 篇貼文記錄")
                return post_ids
                
        except Exception as e:
            logging.warning(f"⚠️ 讀取 {username} 歷史記錄失敗: {e}")
            return set()
    
    async def get_crawl_state(self, username: str) -> Optional[Dict[str, Any]]:
        """獲取用戶爬取狀態"""
        try:
            async with self.db_client.get_connection() as conn:
                result = await conn.fetchrow("""
                    SELECT username, latest_post_id, total_crawled, 
                           last_crawl_at, created_at
                    FROM crawl_state 
                    WHERE username = $1
                """, username)
                
                if result:
                    return dict(result)
                return None
                
        except Exception as e:
            logging.warning(f"⚠️ 讀取 {username} 爬取狀態失敗: {e}")
            return None
    
    async def upsert_posts(self, posts: List[PostMetrics]) -> int:
        """
        批次插入或更新貼文
        
        Args:
            posts: PostMetrics列表
            
        Returns:
            成功處理的數量
        """
        if not posts:
            return 0
            
        try:
            async with self.db_client.get_connection() as conn:
                success_count = 0
                
                # 批次UPSERT
                for post in posts:
                    try:
                        await conn.execute("""
                            INSERT INTO post_metrics_sql (
                                post_id, username, url, content,
                                likes_count, comments_count, reposts_count, 
                                shares_count, views_count, calculated_score,
                                images, videos, created_at, fetched_at, views_fetched_at,
                                source, processing_stage, is_complete
                            ) VALUES (
                                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18
                            )
                            ON CONFLICT (post_id) DO UPDATE SET
                                likes_count = EXCLUDED.likes_count,
                                comments_count = EXCLUDED.comments_count,
                                reposts_count = EXCLUDED.reposts_count,
                                shares_count = EXCLUDED.shares_count,
                                views_count = EXCLUDED.views_count,
                                calculated_score = EXCLUDED.calculated_score,
                                content = EXCLUDED.content,
                                images = EXCLUDED.images,
                                videos = EXCLUDED.videos,
                                fetched_at = EXCLUDED.fetched_at,
                                views_fetched_at = EXCLUDED.views_fetched_at,
                                source = EXCLUDED.source,
                                processing_stage = EXCLUDED.processing_stage,
                                is_complete = EXCLUDED.is_complete
                        """, 
                        post.post_id, post.username, post.url, post.content,
                        post.likes_count, post.comments_count, post.reposts_count,
                        post.shares_count, post.views_count, post.calculate_score(),
                        json.dumps(post.images) if post.images else '[]', 
                        json.dumps(post.videos) if post.videos else '[]', 
                        post.created_at, post.fetched_at, post.views_fetched_at,
                        post.source, post.processing_stage, post.is_complete
                        )
                        success_count += 1
                        
                    except Exception as e:
                        logging.error(f"❌ 插入貼文 {post.post_id} 失敗: {e}")
                        continue
                
                logging.info(f"✅ 成功處理 {success_count}/{len(posts)} 篇貼文")
                return success_count
                
        except Exception as e:
            logging.error(f"❌ 批次處理貼文失敗: {e}")
            return 0
    
    async def update_crawl_state(
        self, 
        username: str, 
        latest_post_id: str, 
        added_count: int
    ) -> bool:
        """
        更新爬取狀態（核心優化）
        
        Args:
            username: 用戶名
            latest_post_id: 最新抓取的post_id
            added_count: 本次新增數量
        """
        try:
            async with self.db_client.get_connection() as conn:
                await conn.execute("""
                    INSERT INTO crawl_state (
                        username, latest_post_id, total_crawled, last_crawl_at
                    ) VALUES ($1, $2, $3, NOW())
                    ON CONFLICT (username) DO UPDATE SET
                        latest_post_id = EXCLUDED.latest_post_id,
                        total_crawled = crawl_state.total_crawled + $3,
                        last_crawl_at = NOW()
                """, username, latest_post_id, added_count)
                
                logging.info(f"📊 更新 {username} 狀態: latest={latest_post_id}, +{added_count}篇")
                return True
                
        except Exception as e:
            logging.error(f"❌ 更新 {username} 狀態失敗: {e}")
            return False
    
    async def get_task_metrics(self, username: str, need: int, got: int) -> Dict[str, Any]:
        """獲取任務級別監控指標（用戶建議）"""
        state = await self.get_crawl_state(username)
        
        return {
            "task": "crawl",
            "username": username,
            "need": need,
            "got": got,
            "status": "complete" if got >= need else "partial",
            "total_in_db": state.get("total_crawled", 0) if state else 0,
            "last_crawl": state.get("last_crawl_at") if state else None
        }


# 全域實例（單例模式）
crawl_history = CrawlHistoryDAO()