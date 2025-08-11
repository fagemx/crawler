"""
數據獲取器 - 從實時爬蟲數據庫獲取真實貼文數據
"""

from typing import List, Dict, Any, Optional
import asyncpg
import json
from common.settings import get_settings, get_database_url
import os


class PostDataFetcher:
    """從爬蟲數據庫獲取貼文數據"""
    
    def __init__(self):
        self.settings = get_settings()
        # 優先使用完整的 DATABASE_URL，避免容器內使用 localhost 造成連線失敗
        raw_url = get_database_url()
        # 在 Docker 內部時，將 localhost/127.0.0.1 自動改為 postgres（compose 服務名）
        if os.path.exists('/.dockerenv') and raw_url:
            self._database_url = (
                raw_url.replace('@localhost:', '@postgres:')
                       .replace('@127.0.0.1:', '@postgres:')
            )
        else:
            self._database_url = raw_url

    async def _connect(self) -> asyncpg.Connection:
        """建立資料庫連線，優先使用 DSN(URL)。"""
        try:
            if self._database_url:
                # 使用 DSN 方式，讓庫自動解析 host/port/user/password/name
                return await asyncpg.connect(self._database_url)
            # 後備：使用個別參數
            return await asyncpg.connect(
                host=self.settings.DATABASE_HOST,
                port=self.settings.DATABASE_PORT,
                user=self.settings.DATABASE_USER,
                password=self.settings.DATABASE_PASSWORD,
                database=self.settings.DATABASE_NAME
            )
        except Exception as exc:
            # 將錯誤上拋，呼叫端會處理並記錄
            raise exc
    
    async def get_available_users(self) -> List[str]:
        """獲取已爬取的用戶列表"""
        try:
            conn = await self._connect()
            
            # 主要來源：post_metrics_sql（已整理的內容）
            primary_query = """
            SELECT DISTINCT username 
            FROM post_metrics_sql 
            WHERE username IS NOT NULL 
              AND content IS NOT NULL 
              AND trim(content) != ''
            ORDER BY username;
            """

            rows = await conn.fetch(primary_query)

            # 後備來源：playwright_post_metrics（只要有抓到貼文就列出用戶）
            if not rows:
                fallback_query = """
                SELECT DISTINCT replace(lower(username),'@','') AS username
                FROM playwright_post_metrics 
                WHERE username IS NOT NULL AND trim(username) != ''
                ORDER BY 1;
                """
                rows = await conn.fetch(fallback_query)

            await conn.close()

            # 去重、過濾空白
            users = [r['username'] for r in rows if r and r.get('username')]
            users = [u.strip().lstrip('@') for u in users if isinstance(u, str) and u.strip()]
            # 可能兩張表大小寫不同，統一再去重
            users = sorted(list({u.lower(): u for u in users}.values()))
            return users
            
        except Exception as e:
            print(f"❌ 獲取用戶列表失敗: {e}")
            return []
    
    async def get_user_posts(self, username: str, post_count: int = 25, 
                           sort_method: str = "likes") -> List[str]:
        """獲取指定用戶的貼文內容"""
        try:
            conn = await self._connect()
            
            # 根據排序方式構建查詢
            sort_column = {
                "views": "views_count",
                "likes": "likes_count",
                "comments": "comments_count",
                "reposts": "reposts_count",
                "shares": "shares_count",
                "score": "calculated_score",
            }.get(sort_method, "views_count")
            
            query = f"""
            SELECT content
            FROM post_metrics_sql
            WHERE username = $1 
              AND content IS NOT NULL 
              AND trim(content) != ''
            ORDER BY {sort_column} DESC NULLS LAST, fetched_at DESC
            LIMIT $2;
            """
            
            rows = await conn.fetch(query, username, post_count)
            await conn.close()
            
            # 提取markdown內容
            posts_content = []
            for row in rows:
                content = row['content']
                if content and content.strip():
                    posts_content.append(content.strip())
            
            return posts_content
            
        except Exception as e:
            print(f"❌ 獲取用戶貼文失敗: {e}")
            return []
    
    async def get_user_posts_count(self, username: str) -> int:
        """獲取指定用戶的貼文總數"""
        try:
            conn = await self._connect()
            
            query = """
            SELECT COUNT(*) as total
            FROM post_metrics_sql 
            WHERE username = $1 
              AND content IS NOT NULL 
              AND trim(content) != '';
            """
            
            row = await conn.fetchrow(query, username)
            await conn.close()
            
            return row['total'] if row else 0
            
        except Exception as e:
            print(f"❌ 獲取用戶貼文數量失敗: {e}")
            return 0
