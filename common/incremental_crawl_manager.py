"""
增量爬取管理器
管理快速爬取的增量狀態，避免重複爬取，支持斷點續爬
"""

import json
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass

from .db_client import DatabaseClient
from .settings import get_settings

@dataclass
class CrawlCheckpoint:
    """爬取檢查點"""
    username: str
    latest_post_id: str
    total_crawled: int
    last_crawl_at: datetime

class IncrementalCrawlManager:
    """增量爬取管理器"""
    
    def __init__(self):
        self.db = DatabaseClient()
        self.settings = get_settings()
    
    async def get_crawl_checkpoint(self, username: str) -> Optional[CrawlCheckpoint]:
        """獲取帳號的爬取檢查點"""
        try:
            result = await self.db.fetch_one("""
                SELECT username, latest_post_id, total_crawled, last_crawl_at
                FROM crawl_state 
                WHERE username = $1
            """, username)
            
            if result:
                return CrawlCheckpoint(
                    username=result['username'],
                    latest_post_id=result['latest_post_id'],
                    total_crawled=result['total_crawled'],
                    last_crawl_at=result['last_crawl_at']
                )
            return None
        except Exception as e:
            print(f"❌ 獲取爬取檢查點失敗: {e}")
            return None
    
    async def update_crawl_checkpoint(self, username: str, latest_post_id: str, new_count: int):
        """更新爬取檢查點"""
        try:
            await self.db.execute("""
                INSERT INTO crawl_state (username, latest_post_id, total_crawled, last_crawl_at)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (username) 
                DO UPDATE SET 
                    latest_post_id = $2,
                    total_crawled = crawl_state.total_crawled + $3,
                    last_crawl_at = NOW()
            """, username, latest_post_id, new_count)
            print(f"✅ 更新爬取檢查點: {username} -> {latest_post_id} (+{new_count})")
        except Exception as e:
            print(f"❌ 更新爬取檢查點失敗: {e}")
    
    async def get_existing_post_ids(self, username: str) -> Set[str]:
        """獲取已爬取的貼文ID集合"""
        try:
            results = await self.db.fetch_all("""
                SELECT post_id FROM post_metrics_sql 
                WHERE username = $1
            """, username)
            return {row['post_id'] for row in results}
        except Exception as e:
            print(f"❌ 獲取已存在貼文ID失敗: {e}")
            return set()
    
    async def save_quick_crawl_results(self, results: List[Dict], username: str) -> int:
        """保存快速爬取結果到資料庫"""
        saved_count = 0
        
        try:
            for result in results:
                post_id = result.get('post_id')
                if not post_id:
                    continue
                
                # 檢查是否已存在（避免重複）
                existing = await self.db.fetch_one("""
                    SELECT id FROM post_metrics_sql WHERE post_id = $1
                """, post_id)
                
                if existing:
                    # 如果已存在，更新某些字段
                    await self.db.execute("""
                        UPDATE post_metrics_sql SET
                            views_count = COALESCE($1, views_count),
                            likes_count = COALESCE($2, likes_count),
                            comments_count = COALESCE($3, comments_count),
                            reposts_count = COALESCE($4, reposts_count),
                            shares_count = COALESCE($5, shares_count),
                            content = COALESCE($6, content),
                            source = $7,
                            views_fetched_at = NOW()
                        WHERE post_id = $8
                    """, 
                        result.get('views'),
                        result.get('likes'),
                        result.get('comments'),
                        result.get('reposts'),
                        result.get('shares'),
                        result.get('content'),
                        result.get('source', 'realtime_crawler'),
                        post_id
                    )
                    print(f"🔄 更新現有貼文: {post_id}")
                else:
                    # 新增貼文
                    await self.db.execute("""
                        INSERT INTO post_metrics_sql (
                            post_id, username, url, content,
                            likes_count, comments_count, reposts_count, shares_count, views_count,
                            created_at, fetched_at, views_fetched_at,
                            source, processing_stage, is_complete
                        ) VALUES (
                            $1, $2, $3, $4,
                            $5, $6, $7, $8, $9,
                            NOW(), NOW(), NOW(),
                            $10, 'quick_crawl', $11
                        )
                    """,
                        post_id,
                        username,
                        result.get('url', f"https://www.threads.net/@{username}/post/{post_id}"),
                        result.get('content'),
                        result.get('likes'),
                        result.get('comments'),
                        result.get('reposts'),
                        result.get('shares'),
                        result.get('views'),
                        result.get('source', 'realtime_crawler'),
                        result.get('success', False)
                    )
                    saved_count += 1
                    print(f"✅ 新增貼文: {post_id}")
        
        except Exception as e:
            print(f"❌ 保存爬取結果失敗: {e}")
        
        return saved_count

    def detect_new_posts_boundary(self, crawled_urls: List[str], existing_post_ids: Set[str]) -> Tuple[List[str], int]:
        """
        檢測新貼文邊界
        返回: (新貼文URL列表, 找到已存在貼文的位置)
        """
        new_urls = []
        stop_position = len(crawled_urls)  # 預設處理全部
        
        for i, url in enumerate(crawled_urls):
            # 提取post_id
            post_id = url.split('/')[-1] if url else None
            
            if post_id in existing_post_ids:
                # 找到已存在的貼文，停止收集
                stop_position = i
                print(f"🔍 檢測到已爬取貼文: {post_id} (位置: {i})")
                break
            else:
                new_urls.append(url)
        
        print(f"📊 邊界檢測結果: 新貼文 {len(new_urls)} 個，停止位置 {stop_position}")
        return new_urls, stop_position

    async def get_crawl_summary(self, username: str) -> Dict:
        """獲取爬取摘要統計"""
        try:
            # 爬取狀態
            checkpoint = await self.get_crawl_checkpoint(username)
            
            # 貼文統計
            stats = await self.db.fetch_one("""
                SELECT 
                    COUNT(*) as total_posts,
                    COUNT(CASE WHEN views_count > 0 THEN 1 END) as posts_with_views,
                    COUNT(CASE WHEN content IS NOT NULL AND content != '' THEN 1 END) as posts_with_content,
                    AVG(views_count) as avg_views,
                    MAX(views_count) as max_views,
                    MAX(fetched_at) as last_post_time
                FROM post_metrics_sql 
                WHERE username = $1
            """, username)
            
            return {
                "username": username,
                "checkpoint": {
                    "latest_post_id": checkpoint.latest_post_id if checkpoint else None,
                    "total_crawled": checkpoint.total_crawled if checkpoint else 0,
                    "last_crawl_at": checkpoint.last_crawl_at if checkpoint else None
                },
                "statistics": {
                    "total_posts": stats['total_posts'] if stats else 0,
                    "posts_with_views": stats['posts_with_views'] if stats else 0,
                    "posts_with_content": stats['posts_with_content'] if stats else 0,
                    "avg_views": float(stats['avg_views']) if stats and stats['avg_views'] else 0,
                    "max_views": stats['max_views'] if stats else 0,
                    "last_post_time": stats['last_post_time'] if stats else None
                }
            }
        except Exception as e:
            print(f"❌ 獲取爬取摘要失敗: {e}")
            return {"username": username, "error": str(e)}