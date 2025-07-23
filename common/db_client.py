"""
資料庫客戶端模組

基於 Plan E 三層資料策略的 PostgreSQL 操作封裝
- Tier-1: 長期資料存儲（posts, post_metrics）
- 批次操作優化
- 與 Redis 協同工作
"""

import asyncio
import asyncpg
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from contextlib import asynccontextmanager

from .settings import get_settings


class DatabaseClient:
    """資料庫客戶端 - Plan E Tier-1 實現"""
    
    def __init__(self):
        self.settings = get_settings()
        self.pool = None
    
    async def init_pool(self):
        """初始化連接池"""
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                self.settings.database.url,
                min_size=5,
                max_size=self.settings.database.pool_size,
                command_timeout=60
            )
    
    async def close_pool(self):
        """關閉連接池"""
        if self.pool:
            await self.pool.close()
            self.pool = None
    
    @asynccontextmanager
    async def get_connection(self):
        """獲取資料庫連接的上下文管理器"""
        if not self.pool:
            await self.init_pool()
        
        async with self.pool.acquire() as conn:
            yield conn
    
    # ============================================================================
    # Tier-1: 貼文基本資料 (posts 表)
    # ============================================================================
    
    async def upsert_post(
        self, 
        url: str, 
        author: str, 
        markdown: Optional[str] = None,
        media_urls: Optional[List[str]] = None
    ) -> bool:
        """
        插入或更新貼文基本資料
        
        Args:
            url: 貼文 URL
            author: 作者
            markdown: Markdown 內容
            media_urls: 媒體 URL 列表
            
        Returns:
            bool: 是否成功
        """
        try:
            async with self.get_connection() as conn:
                await conn.execute("""
                    SELECT upsert_post($1, $2, $3, $4)
                """, url, author, markdown, media_urls)
                
                return True
                
        except Exception as e:
            print(f"插入貼文失敗 {url}: {e}")
            return False
    
    async def batch_upsert_posts(self, posts: List[Dict[str, Any]]) -> int:
        """
        批次插入或更新貼文
        
        Args:
            posts: 貼文列表，每個包含 url, author, markdown, media_urls
            
        Returns:
            int: 成功處理的數量
        """
        try:
            if not posts:
                return 0
            
            success_count = 0
            
            async with self.get_connection() as conn:
                async with conn.transaction():
                    for post in posts:
                        try:
                            await conn.execute("""
                                SELECT upsert_post($1, $2, $3, $4)
                            """, 
                            post.get("url"),
                            post.get("author"),
                            post.get("markdown"),
                            post.get("media_urls")
                            )
                            success_count += 1
                            
                        except Exception as e:
                            print(f"批次插入單個貼文失敗 {post.get('url')}: {e}")
                            continue
            
            return success_count
            
        except Exception as e:
            print(f"批次插入貼文失敗: {e}")
            return 0
    
    async def get_post(self, url: str) -> Optional[Dict[str, Any]]:
        """
        獲取貼文基本資料
        
        Args:
            url: 貼文 URL
            
        Returns:
            Dict[str, Any]: 貼文資料，如果不存在返回 None
        """
        try:
            async with self.get_connection() as conn:
                row = await conn.fetchrow("""
                    SELECT url, author, markdown, media_urls, created_at, last_seen
                    FROM posts
                    WHERE url = $1
                """, url)
                
                if row:
                    return dict(row)
                return None
                
        except Exception as e:
            print(f"獲取貼文失敗 {url}: {e}")
            return None
    
    async def get_posts_by_author(self, author: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        獲取作者的所有貼文
        
        Args:
            author: 作者名稱
            limit: 數量限制
            
        Returns:
            List[Dict[str, Any]]: 貼文列表
        """
        try:
            async with self.get_connection() as conn:
                rows = await conn.fetch("""
                    SELECT url, author, markdown, media_urls, created_at, last_seen
                    FROM posts
                    WHERE author = $1
                    ORDER BY created_at DESC
                    LIMIT $2
                """, author, limit)
                
                return [dict(row) for row in rows]
                
        except Exception as e:
            print(f"獲取作者貼文失敗 {author}: {e}")
            return []
    
    # ============================================================================
    # Tier-1: 貼文指標 (post_metrics 表)
    # ============================================================================
    
    async def upsert_metrics(
        self,
        url: str,
        views: Optional[int] = None,
        likes: Optional[int] = None,
        comments: Optional[int] = None,
        reposts: Optional[int] = None,
        shares: Optional[int] = None
    ) -> bool:
        """
        插入或更新貼文指標
        
        Args:
            url: 貼文 URL
            views, likes, comments, reposts, shares: 各項指標
            
        Returns:
            bool: 是否成功
        """
        try:
            async with self.get_connection() as conn:
                await conn.execute("""
                    SELECT upsert_metrics($1, $2, $3, $4, $5, $6)
                """, url, views, likes, comments, reposts, shares)
                
                return True
                
        except Exception as e:
            print(f"插入指標失敗 {url}: {e}")
            return False
    
    async def batch_upsert_metrics(self, metrics_list: List[Dict[str, Any]]) -> int:
        """
        批次插入或更新指標
        
        Args:
            metrics_list: 指標列表，每個包含 url 和各項指標
            
        Returns:
            int: 成功處理的數量
        """
        try:
            if not metrics_list:
                return 0
            
            success_count = 0
            
            async with self.get_connection() as conn:
                async with conn.transaction():
                    for metrics in metrics_list:
                        try:
                            await conn.execute("""
                                SELECT upsert_metrics($1, $2, $3, $4, $5, $6)
                            """,
                            metrics.get("url"),
                            metrics.get("views"),
                            metrics.get("likes"),
                            metrics.get("comments"),
                            metrics.get("reposts"),
                            metrics.get("shares")
                            )
                            success_count += 1
                            
                        except Exception as e:
                            print(f"批次插入單個指標失敗 {metrics.get('url')}: {e}")
                            continue
            
            return success_count
            
        except Exception as e:
            print(f"批次插入指標失敗: {e}")
            return 0
    
    async def get_metrics(self, url: str) -> Optional[Dict[str, Any]]:
        """
        獲取貼文指標
        
        Args:
            url: 貼文 URL
            
        Returns:
            Dict[str, Any]: 指標資料，如果不存在返回 None
        """
        try:
            async with self.get_connection() as conn:
                row = await conn.fetchrow("""
                    SELECT url, views, likes, comments, reposts, shares, score, updated_at
                    FROM post_metrics
                    WHERE url = $1
                """, url)
                
                if row:
                    return dict(row)
                return None
                
        except Exception as e:
            print(f"獲取指標失敗 {url}: {e}")
            return None
    
    # ============================================================================
    # Plan E 核心查詢：Top-K 貼文
    # ============================================================================
    
    async def get_top_posts(self, username: str, limit: int = 30) -> List[Dict[str, Any]]:
        """
        獲取用戶的 Top-K 貼文（Plan E 核心功能）
        
        Args:
            username: 用戶名
            limit: 返回數量
            
        Returns:
            List[Dict[str, Any]]: 排序後的貼文列表，包含 markdown 和 media_urls
        """
        try:
            async with self.get_connection() as conn:
                rows = await conn.fetch("""
                    SELECT url, markdown, media_urls, score
                    FROM get_top_posts($1, $2)
                """, username, limit)
                
                return [dict(row) for row in rows]
                
        except Exception as e:
            print(f"獲取 Top 貼文失敗 {username}: {e}")
            return []
    
    async def get_posts_with_metrics(self, urls: List[str]) -> List[Dict[str, Any]]:
        """
        批次獲取貼文及其指標（用於分析階段）
        
        Args:
            urls: URL 列表
            
        Returns:
            List[Dict[str, Any]]: 完整的貼文資料列表
        """
        try:
            if not urls:
                return []
            
            async with self.get_connection() as conn:
                rows = await conn.fetch("""
                    SELECT 
                        url, author, markdown, media_urls, created_at,
                        views, likes, comments, reposts, shares, score,
                        metrics_updated_at
                    FROM posts_with_metrics
                    WHERE url = ANY($1)
                    ORDER BY score DESC NULLS LAST
                """, urls)
                
                return [dict(row) for row in rows]
                
        except Exception as e:
            print(f"批次獲取貼文指標失敗: {e}")
            return []
    
    # ============================================================================
    # 處理記錄 (processing_log 表)
    # ============================================================================
    
    async def log_processing(
        self,
        url: str,
        agent_name: str,
        stage: str,
        status: str,
        error_msg: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        記錄處理日誌
        
        Args:
            url: 貼文 URL
            agent_name: Agent 名稱
            stage: 處理階段
            status: 狀態 ('pending', 'completed', 'failed')
            error_msg: 錯誤訊息
            metadata: 額外元數據
            
        Returns:
            bool: 是否成功
        """
        try:
            async with self.get_connection() as conn:
                await conn.execute("""
                    INSERT INTO processing_log 
                    (url, agent_name, stage, status, error_msg, metadata, started_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                """, url, agent_name, stage, status, error_msg, metadata, datetime.utcnow())
                
                return True
                
        except Exception as e:
            print(f"記錄處理日誌失敗 {url}: {e}")
            return False
    
    async def update_processing_status(
        self,
        url: str,
        agent_name: str,
        stage: str,
        status: str,
        error_msg: Optional[str] = None
    ) -> bool:
        """
        更新處理狀態
        
        Args:
            url: 貼文 URL
            agent_name: Agent 名稱
            stage: 處理階段
            status: 新狀態
            error_msg: 錯誤訊息
            
        Returns:
            bool: 是否成功
        """
        try:
            async with self.get_connection() as conn:
                await conn.execute("""
                    UPDATE processing_log
                    SET status = $4, completed_at = $5, error_msg = $6
                    WHERE url = $1 AND agent_name = $2 AND stage = $3
                """, url, agent_name, stage, status, datetime.utcnow(), error_msg)
                
                return True
                
        except Exception as e:
            print(f"更新處理狀態失敗 {url}: {e}")
            return False
    
    # ============================================================================
    # 統計和監控
    # ============================================================================
    
    async def get_processing_stats(self) -> Dict[str, Any]:
        """
        獲取處理統計
        
        Returns:
            Dict[str, Any]: 統計資料
        """
        try:
            async with self.get_connection() as conn:
                # 總貼文數
                total_posts = await conn.fetchval("SELECT COUNT(*) FROM posts")
                
                # 有指標的貼文數
                posts_with_metrics = await conn.fetchval("SELECT COUNT(*) FROM post_metrics")
                
                # 各階段處理狀態
                processing_stats = await conn.fetch("""
                    SELECT agent_name, stage, status, COUNT(*) as count
                    FROM processing_log
                    WHERE started_at > NOW() - INTERVAL '24 hours'
                    GROUP BY agent_name, stage, status
                    ORDER BY agent_name, stage, status
                """)
                
                return {
                    "total_posts": total_posts,
                    "posts_with_metrics": posts_with_metrics,
                    "completion_rate": posts_with_metrics / total_posts if total_posts > 0 else 0,
                    "processing_stats": [dict(row) for row in processing_stats]
                }
                
        except Exception as e:
            print(f"獲取處理統計失敗: {e}")
            return {}
    
    async def health_check(self) -> Dict[str, Any]:
        """
        健康檢查
        
        Returns:
            Dict[str, Any]: 健康狀態
        """
        try:
            async with self.get_connection() as conn:
                # 測試查詢
                version = await conn.fetchval("SELECT version()")
                
                # 連接池狀態
                pool_info = {
                    "size": self.pool.get_size() if self.pool else 0,
                    "max_size": self.pool.get_max_size() if self.pool else 0,
                    "min_size": self.pool.get_min_size() if self.pool else 0
                }
                
                return {
                    "status": "healthy",
                    "database_version": version,
                    "connection_pool": pool_info
                }
                
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }


# 全域資料庫客戶端實例
_db_client = None


async def get_db_client() -> DatabaseClient:
    """獲取資料庫客戶端實例（單例模式）"""
    global _db_client
    if _db_client is None:
        _db_client = DatabaseClient()
        await _db_client.init_pool()
    return _db_client


# 便利函數
async def upsert_post(url: str, author: str, markdown: str = None, media_urls: List[str] = None) -> bool:
    """插入貼文的便利函數"""
    client = await get_db_client()
    return await client.upsert_post(url, author, markdown, media_urls)


async def upsert_metrics(url: str, **metrics) -> bool:
    """插入指標的便利函數"""
    client = await get_db_client()
    return await client.upsert_metrics(url, **metrics)


async def get_top_posts(username: str, limit: int = 30) -> List[Dict[str, Any]]:
    """獲取 Top 貼文的便利函數"""
    client = await get_db_client()
    return await client.get_top_posts(username, limit)


if __name__ == "__main__":
    # 測試資料庫連接
    async def test_db():
        client = await get_db_client()
        health = await client.health_check()
        print(f"資料庫健康狀態: {health}")
        await client.close_pool()
    
    asyncio.run(test_db())