"""
資料庫客戶端模組

基於 Plan E 三層資料策略的 PostgreSQL 操作封裝
- Tier-1: 長期資料存儲（posts, post_metrics）
- 批次操作優化
- 與 Redis 協同工作
"""

import asyncio
import asyncpg
from asyncpg import exceptions as pg_exc
import json  # <<< 導入 json 模組
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
        else:
            # 若池已存在但處於關閉狀態，重新建立
            if getattr(self.pool, "_closed", False):
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
        # 池不存在或已關閉時重新初始化
        if not self.pool or getattr(self.pool, "_closed", False):
            await self.init_pool()
        
        async with self.pool.acquire() as conn:
            yield conn
    
    async def fetch_all(self, query: str, *args) -> List[Dict]:
        """執行查詢並返回所有結果（含連線重試）"""
        async def _op(conn):
            rows = await conn.fetch(query, *args)
            return [dict(row) for row in rows]
        return await self._run_with_retry(_op)
    
    async def fetch_one(self, query: str, *args) -> Optional[Dict]:
        """執行查詢並返回第一個結果（含連線重試）"""
        async def _op(conn):
            row = await conn.fetchrow(query, *args)
            return dict(row) if row else None
        return await self._run_with_retry(_op)
    
    async def execute(self, query: str, *args) -> str:
        """執行SQL命令（INSERT, UPDATE, DELETE等）（含連線重試）"""
        async def _op(conn):
            return await conn.execute(query, *args)
        return await self._run_with_retry(_op)

    async def _run_with_retry(self, op_coro):
        """連線操作重試：處理連線被關閉/同時操作衝突等情況"""
        last_err = None
        for attempt in range(2):
            try:
                async with self.get_connection() as conn:
                    return await op_coro(conn)
            except (pg_exc.ConnectionDoesNotExistError, pg_exc.InterfaceError, ConnectionResetError) as e:
                last_err = e
                # 重建連線池後重試一次
                try:
                    await self.close_pool()
                    await self.init_pool()
                except Exception:
                    pass
                await asyncio.sleep(0.1)
                continue
            except Exception as e:
                # 特判常見池狀態錯誤，嘗試重建一次
                msg = str(e).lower()
                if ("pool is closed" in msg) or ("another operation is in progress" in msg):
                    last_err = e
                    try:
                        await self.close_pool()
                        await self.init_pool()
                    except Exception:
                        pass
                    await asyncio.sleep(0.1)
                    continue
                raise
        # 超過重試次數，拋出原錯誤
        if last_err:
            raise last_err
        raise RuntimeError("Unknown database operation error without exception")
    
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
            # 將 list 轉換為 JSON 字串，如果存在的話
            media_urls_json = json.dumps(media_urls) if media_urls is not None else None
            
            async with self.get_connection() as conn:
                await conn.execute("""
                    SELECT upsert_post($1, $2, $3, $4)
                """, url, author, markdown, media_urls_json)
                
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
                            # 批次處理中同樣需要轉換
                            media_urls = post.get("media_urls")
                            media_urls_json = json.dumps(media_urls) if media_urls is not None else None

                            await conn.execute("""
                                SELECT upsert_post($1, $2, $3, $4)
                            """, 
                            post.get("url"),
                            post.get("author"),
                            post.get("markdown"),
                            media_urls_json
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

    async def update_post_metadata(self, url: str, metadata: Dict[str, Any]) -> bool:
        """
        更新貼文的 metadata
        
        Args:
            url: 貼文 URL
            metadata: 新的 metadata 內容
            
        Returns:
            bool: 是否成功
        """
        try:
            metadata_json = json.dumps(metadata) if metadata is not None else None
            async with self.get_connection() as conn:
                await conn.execute("""
                    UPDATE posts
                    SET metadata = $2
                    WHERE url = $1
                """, url, metadata_json)
                return True
        except Exception as e:
            print(f"更新 metadata 失敗 {url}: {e}")
            return False
    
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
    
    async def upsert_media_file(
        self,
        post_url: str,
        original_url: str,
        media_type: str,
        file_extension: str = None,
        rustfs_key: str = None,
        rustfs_url: str = None,
        file_size: int = None,
        width: int = None,
        height: int = None,
        duration: int = None,
        download_status: str = "pending",
        metadata: Dict[str, Any] = None
    ) -> int:
        """插入或更新媒體檔案記錄"""
        try:
            async with self.get_connection() as conn:
                media_id = await conn.fetchval("""
                    SELECT upsert_media_file($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                """, 
                post_url, original_url, media_type, file_extension, rustfs_key, rustfs_url,
                file_size, width, height, duration, download_status, metadata or {})
                
                return media_id
                
        except Exception as e:
            print(f"❌ Failed to upsert media file: {e}")
            return None

    async def get_media_files_by_post(self, post_url: str) -> List[Dict[str, Any]]:
        """獲取貼文的媒體檔案"""
        try:
            async with self.get_connection() as conn:
                rows = await conn.fetch("""
                    SELECT 
                        id, post_url, original_url, media_type, file_extension,
                        rustfs_key, rustfs_url, file_size, width, height, duration,
                        download_status, download_error, created_at, downloaded_at, metadata
                    FROM media_files 
                    WHERE post_url = $1
                    ORDER BY created_at
                """, post_url)
                
                return [dict(row) for row in rows]
                
        except Exception as e:
            print(f"❌ Failed to get media files: {e}")
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
    # 媒體管理 (media 表)
    # ============================================================================
    
    async def insert_media_record(
        self,
        post_id: str,
        media_type: str,
        cdn_url: str,
        storage_key: str,
        status: str = 'uploaded',
        size_bytes: Optional[int] = None
    ) -> bool:
        """
        插入媒體記錄
        
        Args:
            post_id: 貼文 ID
            media_type: 媒體類型 ('image' 或 'video')
            cdn_url: 原始 CDN URL
            storage_key: RustFS 存儲 key
            status: 狀態
            size_bytes: 檔案大小
            
        Returns:
            bool: 是否成功
        """
        try:
            async with self.get_connection() as conn:
                await conn.execute("""
                    INSERT INTO media 
                    (post_id, media_type, cdn_url, storage_key, status, size_bytes, created_at, last_updated)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $7)
                    ON CONFLICT (post_id, cdn_url) 
                    DO UPDATE SET 
                        storage_key = EXCLUDED.storage_key,
                        status = EXCLUDED.status,
                        size_bytes = EXCLUDED.size_bytes,
                        last_updated = EXCLUDED.last_updated
                """, post_id, media_type, cdn_url, storage_key, status, size_bytes, datetime.utcnow())
                
                return True
                
        except Exception as e:
            print(f"插入媒體記錄失敗 {post_id}: {e}")
            return False
    
    async def get_post_media_urls(self, post_id: str) -> List[str]:
        """
        獲取貼文的媒體 URL 列表
        
        Args:
            post_id: 貼文 ID
            
        Returns:
            List[str]: 媒體 URL 列表
        """
        try:
            async with self.get_connection() as conn:
                # 首先嘗試從 media 表獲取
                rows = await conn.fetch("""
                    SELECT cdn_url FROM media WHERE post_id = $1
                """, post_id)
                
                if rows:
                    return [row['cdn_url'] for row in rows]
                
                # 如果 media 表沒有，從 posts 表的 media_urls 欄位獲取
                row = await conn.fetchrow("""
                    SELECT media_urls FROM posts WHERE url = $1
                """, post_id)
                
                if row and row['media_urls']:
                    try:
                        media_urls = json.loads(row['media_urls'])
                        return media_urls if isinstance(media_urls, list) else []
                    except json.JSONDecodeError:
                        return []
                
                return []
                
        except Exception as e:
            print(f"獲取貼文媒體 URL 失敗 {post_id}: {e}")
            return []
    
    async def get_media_by_storage_key(self, storage_key: str) -> Optional[Dict[str, Any]]:
        """
        根據存儲 key 獲取媒體記錄
        
        Args:
            storage_key: RustFS 存儲 key
            
        Returns:
            Dict[str, Any]: 媒體記錄，如果不存在返回 None
        """
        try:
            async with self.get_connection() as conn:
                row = await conn.fetchrow("""
                    SELECT post_id, media_type, cdn_url, storage_key, status, size_bytes, created_at, last_updated
                    FROM media
                    WHERE storage_key = $1
                """, storage_key)
                
                if row:
                    return dict(row)
                return None
                
        except Exception as e:
            print(f"獲取媒體記錄失敗 {storage_key}: {e}")
            return None
    
    async def update_media_status(self, storage_key: str, status: str) -> bool:
        """
        更新媒體狀態
        
        Args:
            storage_key: RustFS 存儲 key
            status: 新狀態
            
        Returns:
            bool: 是否成功
        """
        try:
            async with self.get_connection() as conn:
                await conn.execute("""
                    UPDATE media
                    SET status = $2, last_updated = $3
                    WHERE storage_key = $1
                """, storage_key, status, datetime.utcnow())
                
                return True
                
        except Exception as e:
            print(f"更新媒體狀態失敗 {storage_key}: {e}")
            return False
    
    async def get_top_ranked_posts(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        獲取排名前 N 的貼文（用於媒體分析）
        
        Args:
            limit: 數量限制
            
        Returns:
            List[Dict[str, Any]]: 排名前 N 的貼文
        """
        try:
            async with self.get_connection() as conn:
                rows = await conn.fetch("""
                    SELECT url as post_id, author, markdown, media_urls, score
                    FROM post_metrics pm
                    JOIN posts p ON pm.url = p.url
                    WHERE pm.score IS NOT NULL
                    ORDER BY pm.score DESC
                    LIMIT $1
                """, limit)
                
                return [dict(row) for row in rows]
                
        except Exception as e:
            print(f"獲取排名貼文失敗: {e}")
            return []
    
    async def update_post_metrics(self, post_id: str, metrics: Dict[str, int]) -> bool:
        """
        更新貼文指標（從媒體分析結果）
        
        Args:
            post_id: 貼文 ID
            metrics: 指標字典
            
        Returns:
            bool: 是否成功
        """
        try:
            async with self.get_connection() as conn:
                await conn.execute("""
                    SELECT upsert_metrics($1, $2, $3, $4, $5, $6)
                """, 
                post_id,
                metrics.get("views"),
                metrics.get("likes"),
                metrics.get("comments"),
                metrics.get("reposts"),
                metrics.get("shares")
                )
                
                return True
                
        except Exception as e:
            print(f"更新貼文指標失敗 {post_id}: {e}")
            return False
    
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
            # 將 dict 轉換為 JSON 字串，如果存在的話
            metadata_json = json.dumps(metadata) if metadata is not None else None

            async with self.get_connection() as conn:
                await conn.execute("""
                    INSERT INTO processing_log 
                    (url, agent_name, stage, status, error_msg, metadata, started_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                """, url, agent_name, stage, status, error_msg, metadata_json, datetime.utcnow())
                
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


# 全域資料庫客戶端實例（按事件迴圈分槽）
# Key 為當前事件迴圈 id，Value 為對應的 DatabaseClient
_db_clients = {}


async def get_db_client() -> DatabaseClient:
    """獲取資料庫客戶端實例（每個事件迴圈一個連線池）。

    - 避免「Future attached to a different loop」。
    - 對於 Streamlit 每次互動的潛在新事件迴圈，會取得對應的連線池。
    """
    global _db_clients
    current_loop = asyncio.get_running_loop()
    loop_key = id(current_loop)

    client: DatabaseClient = _db_clients.get(loop_key)
    if client is None or (client.pool is None) or getattr(client.pool, "_closed", False):
        client = DatabaseClient()
        await client.init_pool()
        _db_clients[loop_key] = client

    # 清理已關閉或失效的舊池（保守清理）
    to_delete = []
    for k, v in _db_clients.items():
        if v is not client and (v.pool is None or getattr(v.pool, "_closed", False)):
            to_delete.append(k)
    for k in to_delete:
        _db_clients.pop(k, None)

    return client


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