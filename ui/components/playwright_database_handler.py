"""
Playwright 資料庫處理器
負責所有資料庫相關操作，包括保存數據、查詢統計等
"""

import asyncio
import json
import sys
import os
import tempfile
import subprocess
from typing import Dict, Any, List
from .playwright_utils import PlaywrightUtils


class PlaywrightDatabaseHandler:
    """Playwright 資料庫處理器"""
    
    def __init__(self):
        self.log_callback = None
    
    def set_log_callback(self, callback):
        """設置日誌回調函數"""
        self.log_callback = callback
    
    def _log(self, message: str):
        """記錄日誌"""
        if self.log_callback:
            self.log_callback(message)
        print(message)
    
    async def save_to_database_async(self, results_data: Dict[str, Any]):
        """異步保存結果到 Playwright 專用資料表"""
        try:
            from common.db_client import DatabaseClient
            
            db = DatabaseClient()
            await db.init_pool()
            
            try:
                results = results_data.get("results", [])
                target_username = results_data.get("target_username", "")
                crawl_id = results_data.get("crawl_id", "")
                
                if results and target_username:
                    saved_count = 0
                    
                    async with db.get_connection() as conn:
                        # 創建 Playwright 專用資料表（如果不存在）
                        await conn.execute("""
                            CREATE TABLE IF NOT EXISTS playwright_post_metrics (
                                id SERIAL PRIMARY KEY,
                                username VARCHAR(255) NOT NULL,
                                post_id VARCHAR(255) NOT NULL,
                                url TEXT,
                                content TEXT,
                                views_count INTEGER,
                                likes_count INTEGER,
                                comments_count INTEGER,
                                reposts_count INTEGER,
                                shares_count INTEGER,
                                calculated_score DECIMAL,
                                post_published_at TIMESTAMP,
                                tags TEXT,
                                images TEXT,
                                videos TEXT,
                                source VARCHAR(100) DEFAULT 'playwright_agent',
                                crawler_type VARCHAR(50) DEFAULT 'playwright',
                                crawl_id VARCHAR(255),
                                created_at TIMESTAMP,
                                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                UNIQUE(username, post_id, crawler_type)
                            )
                        """)
                        
                        # 創建索引（如果不存在）
                        await conn.execute("""
                            CREATE INDEX IF NOT EXISTS idx_playwright_username_created 
                            ON playwright_post_metrics(username, created_at DESC)
                        """)
                        
                        await conn.execute("""
                            CREATE INDEX IF NOT EXISTS idx_playwright_crawl_id 
                            ON playwright_post_metrics(crawl_id)
                        """)
                        
                        # 插入數據
                        for result in results:
                            try:
                                # 解析數字字段
                                views_count = PlaywrightUtils.parse_number_safe(result.get('views_count', result.get('views', '')))
                                likes_count = PlaywrightUtils.parse_number_safe(result.get('likes_count', result.get('likes', '')))
                                comments_count = PlaywrightUtils.parse_number_safe(result.get('comments_count', result.get('comments', '')))
                                reposts_count = PlaywrightUtils.parse_number_safe(result.get('reposts_count', result.get('reposts', '')))
                                shares_count = PlaywrightUtils.parse_number_safe(result.get('shares_count', result.get('shares', '')))
                                calculated_score = result.get('calculated_score', 0)
                                
                                # 處理時間字段 - 轉換為台北時區
                                post_published_at = PlaywrightUtils.convert_to_taipei_time(result.get('post_published_at', ''))
                                
                                # 處理陣列字段，轉換為 JSON 字符串
                                import json
                                tags_json = json.dumps(result.get('tags', []), ensure_ascii=False)
                                images_json = json.dumps(result.get('images', []), ensure_ascii=False)
                                videos_json = json.dumps(result.get('videos', []), ensure_ascii=False)
                                
                                # 處理創建時間 - 使用台北時區
                                created_at = PlaywrightUtils.convert_to_taipei_time(result.get('created_at', ''))
                                if not created_at:
                                    created_at = PlaywrightUtils.get_current_taipei_time()
                                
                                # 使用 UPSERT 避免重複
                                await conn.execute("""
                                    INSERT INTO playwright_post_metrics (
                                        username, post_id, url, content, 
                                        views_count, likes_count, comments_count, reposts_count, shares_count,
                                        calculated_score, post_published_at, tags, images, videos,
                                        source, crawler_type, crawl_id, created_at
                                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
                                    ON CONFLICT (username, post_id, crawler_type) 
                                    DO UPDATE SET
                                        url = EXCLUDED.url,
                                        content = EXCLUDED.content,
                                        views_count = EXCLUDED.views_count,
                                        likes_count = EXCLUDED.likes_count,
                                        comments_count = EXCLUDED.comments_count,
                                        reposts_count = EXCLUDED.reposts_count,
                                        shares_count = EXCLUDED.shares_count,
                                        calculated_score = EXCLUDED.calculated_score,
                                        post_published_at = EXCLUDED.post_published_at,
                                        tags = EXCLUDED.tags,
                                        images = EXCLUDED.images,
                                        videos = EXCLUDED.videos,
                                        crawl_id = EXCLUDED.crawl_id,
                                        created_at = EXCLUDED.created_at,
                                        fetched_at = CURRENT_TIMESTAMP
                                """, 
                                    target_username,
                                    result.get('post_id', ''),
                                    result.get('url', ''),
                                    result.get('content', ''),
                                    views_count,
                                    likes_count,
                                    comments_count,
                                    reposts_count,
                                    shares_count,
                                    calculated_score,
                                    post_published_at,
                                    tags_json,
                                    images_json,
                                    videos_json,
                                    'playwright_agent',
                                    'playwright',
                                    crawl_id,
                                    created_at
                                )
                                saved_count += 1
                                
                            except Exception as e:
                                self._log(f"⚠️ 保存單個貼文失敗 {result.get('post_id', 'N/A')}: {e}")
                                continue
                        
                        # 更新 Playwright 爬取檢查點表
                        await conn.execute("""
                            CREATE TABLE IF NOT EXISTS playwright_crawl_state (
                                id SERIAL PRIMARY KEY,
                                username VARCHAR(255) UNIQUE NOT NULL,
                                latest_post_id VARCHAR(255),
                                total_crawled INTEGER DEFAULT 0,
                                last_crawl_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                crawl_id VARCHAR(255)
                            )
                        """)
                        
                        if results and saved_count > 0:
                            latest_post_id = results[0].get('post_id')
                            await conn.execute("""
                                INSERT INTO playwright_crawl_state (username, latest_post_id, total_crawled, crawl_id)
                                VALUES ($1, $2, $3, $4)
                                ON CONFLICT (username)
                                DO UPDATE SET
                                    latest_post_id = EXCLUDED.latest_post_id,
                                    total_crawled = playwright_crawl_state.total_crawled + EXCLUDED.total_crawled,
                                    last_crawl_at = CURRENT_TIMESTAMP,
                                    crawl_id = EXCLUDED.crawl_id
                            """, target_username, latest_post_id, saved_count, crawl_id)
                    
                    # 更新結果狀態
                    results_data["database_saved"] = True
                    results_data["database_saved_count"] = saved_count
                    
                    self._log(f"💾 已保存 {saved_count} 個貼文到 Playwright 專用資料表")
                    
                    # 🔧 重要：返回保存結果
                    return {
                        "success": True,
                        "saved_count": saved_count,
                        "message": f"已保存 {saved_count} 個貼文"
                    }
                else:
                    return {
                        "success": False,
                        "saved_count": 0,
                        "message": "沒有有效數據需要保存"
                    }
                    
            finally:
                await db.close_pool()
                
        except Exception as e:
            self._log(f"⚠️ 資料庫保存失敗: {e}")
            return {
                "success": False,
                "saved_count": 0,
                "message": f"保存失敗: {str(e)}"
            }
    
    def get_database_stats(self):
        """獲取 Playwright 專用資料庫統計"""
        try:
            return asyncio.run(self._get_stats_async())
        except Exception as e:
            return {"error": str(e)}
    
    async def _get_stats_async(self):
        """異步獲取統計數據"""
        try:
            from common.db_client import DatabaseClient
            
            db = DatabaseClient()
            await db.init_pool()
            
            async with db.get_connection() as conn:
                # 獲取總體統計
                total_stats_query = """
                    SELECT 
                        COUNT(*) as total_posts,
                        COUNT(DISTINCT username) as total_users,
                        COUNT(DISTINCT crawl_id) as total_crawls,
                        MAX(fetched_at) as latest_activity
                    FROM playwright_post_metrics
                """
                
                total_stats_row = await conn.fetchrow(total_stats_query)
                
                total_stats = {
                    "total_posts": total_stats_row['total_posts'] if total_stats_row else 0,
                    "total_users": total_stats_row['total_users'] if total_stats_row else 0,
                    "total_crawls": total_stats_row['total_crawls'] if total_stats_row else 0,
                    "latest_activity": total_stats_row['latest_activity'] if total_stats_row else None
                }
                
                # 獲取各用戶統計
                user_stats_query = """
                    SELECT 
                        username,
                        COUNT(*) as post_count,
                        MAX(fetched_at) as latest_crawl,
                        MAX(crawl_id) as latest_crawl_id,
                        AVG(views_count) as avg_views,
                        AVG(likes_count) as avg_likes
                    FROM playwright_post_metrics 
                    GROUP BY username 
                    ORDER BY latest_crawl DESC
                    LIMIT 50
                """
                
                user_stats_rows = await conn.fetch(user_stats_query)
                
                user_stats = []
                for row in user_stats_rows:
                    user_stats.append({
                        "username": row['username'],
                        "post_count": row['post_count'],
                        "latest_crawl": row['latest_crawl'],
                        "latest_crawl_id": row['latest_crawl_id'],
                        "avg_views": int(row['avg_views']) if row['avg_views'] else 0,
                        "avg_likes": int(row['avg_likes']) if row['avg_likes'] else 0
                    })
                
                return {
                    "total_stats": total_stats,
                    "user_stats": user_stats
                }
                
        except Exception as e:
            # 如果資料表不存在，返回空統計
            return {
                "total_stats": {
                    "total_posts": 0,
                    "total_users": 0, 
                    "latest_activity": None,
                    "total_crawls": 0
                },
                "user_stats": []
            }
    
    async def get_user_posts_async(self, username: str):
        """獲取特定用戶的所有貼文"""
        try:
            from common.db_client import DatabaseClient
            
            db = DatabaseClient()
            await db.init_pool()
            
            async with db.get_connection() as conn:
                query = """
                    SELECT username, post_id, content, views_count, 
                           likes_count, comments_count, reposts_count, shares_count,
                           calculated_score, post_published_at, tags, images, videos,
                           url, source, crawler_type, crawl_id, created_at, fetched_at
                    FROM playwright_post_metrics 
                    WHERE username = $1 
                    ORDER BY fetched_at DESC
                """
                
                rows = await conn.fetch(query, username)
                
                posts = []
                for row in rows:
                    post = dict(row)
                    
                    # 將 JSON 字符串轉換回陣列
                    import json
                    from decimal import Decimal
                    
                    try:
                        post['tags'] = json.loads(post.get('tags', '[]')) if post.get('tags') else []
                    except:
                        post['tags'] = []
                    
                    try:
                        post['images'] = json.loads(post.get('images', '[]')) if post.get('images') else []
                    except:
                        post['images'] = []
                    
                    try:
                        post['videos'] = json.loads(post.get('videos', '[]')) if post.get('videos') else []
                    except:
                        post['videos'] = []
                    
                    # 將 Decimal 類型轉換為 float 以確保 JSON 序列化相容性
                    if isinstance(post.get('calculated_score'), Decimal):
                        post['calculated_score'] = float(post['calculated_score'])
                    
                    posts.append(post)
                
                return posts
                
        except Exception as e:
            self._log(f"❌ 獲取用戶貼文失敗: {e}")
            return []
    
    async def delete_user_data_async(self, username: str):
        """刪除特定用戶的所有數據（增強錯誤處理和日誌記錄）"""
        self._log(f"開始刪除用戶 @{username} 的數據")
        
        try:
            from common.db_client import DatabaseClient
            
            self._log("初始化資料庫客戶端...")
            db = DatabaseClient()
            await db.init_pool()
            self._log("資料庫連接池初始化完成")
            
            async with db.get_connection() as conn:
                self._log(f"已獲取資料庫連接，準備查詢用戶 @{username} 的記錄數量")
                
                # 先獲取要刪除的記錄數
                count_query = "SELECT COUNT(*) FROM playwright_post_metrics WHERE username = $1"
                count_result = await conn.fetchrow(count_query, username)
                count = count_result['count'] if count_result else 0
                
                self._log(f"找到 {count} 筆用戶 @{username} 的記錄")
                
                if count == 0:
                    self._log(f"用戶 @{username} 沒有任何記錄，跳過刪除操作")
                    return {
                        "success": True,
                        "deleted_count": 0,
                        "message": f"用戶 @{username} 沒有找到任何記錄"
                    }
                
                # 刪除數據
                self._log(f"開始刪除用戶 @{username} 的 {count} 筆記錄")
                delete_query = "DELETE FROM playwright_post_metrics WHERE username = $1"
                result = await conn.execute(delete_query, username)
                
                # 解析刪除結果
                deleted_rows = int(result.split()[-1]) if result else 0
                self._log(f"實際刪除了 {deleted_rows} 筆記錄")
                
                # 驗證刪除是否成功
                verify_query = "SELECT COUNT(*) FROM playwright_post_metrics WHERE username = $1"
                verify_result = await conn.fetchrow(verify_query, username)
                remaining_count = verify_result['count'] if verify_result else 0
                
                if remaining_count == 0:
                    self._log(f"✅ 用戶 @{username} 的數據已完全刪除")
                    return {
                        "success": True,
                        "deleted_count": deleted_rows,
                        "original_count": count,
                        "remaining_count": remaining_count,
                        "message": f"成功刪除用戶 @{username} 的 {deleted_rows} 筆記錄"
                    }
                else:
                    self._log(f"⚠️ 刪除不完整，還剩餘 {remaining_count} 筆記錄")
                    return {
                        "success": False,
                        "deleted_count": deleted_rows,
                        "original_count": count,
                        "remaining_count": remaining_count,
                        "error": f"刪除不完整，預期刪除 {count} 筆，實際刪除 {deleted_rows} 筆，還剩餘 {remaining_count} 筆"
                    }
                
        except Exception as e:
            error_msg = str(e)
            self._log(f"❌ 刪除用戶 @{username} 的數據時發生錯誤: {error_msg}")
            
            # 提供更詳細的錯誤分類
            if "connection" in error_msg.lower():
                error_type = "資料庫連接錯誤"
            elif "permission" in error_msg.lower() or "access" in error_msg.lower():
                error_type = "權限錯誤"
            elif "timeout" in error_msg.lower():
                error_type = "操作超時"
            elif "table" in error_msg.lower() or "column" in error_msg.lower():
                error_type = "資料表結構錯誤"
            else:
                error_type = "未知錯誤"
            
            return {
                "success": False,
                "error": error_msg,
                "error_type": error_type,
                "username": username
            }
    
    def save_results_to_database_sync(self, results_data: Dict[str, Any]):
        """同步保存結果到資料庫（備用功能）"""
        try:
            import asyncio
            
            # 檢查results的格式
            if isinstance(results_data, dict):
                results = results_data.get('results', [])
                target_username = results_data.get('target_username', '')
            else:
                results = results_data if results_data else []
                target_username = results[0].get('username', '') if results else ''
            
            if not results:
                return {"success": False, "error": "沒有找到可保存的結果"}
            
            if not target_username:
                return {"success": False, "error": "無法識別目標用戶名"}
            
            # 使用新的事件循環執行異步保存
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(self._save_sync_helper(results_data))
                return result
            finally:
                loop.close()
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _save_sync_helper(self, results_data: Dict[str, Any]):
        """同步保存的異步幫助方法"""
        try:
            # 直接調用異步保存方法
            await self.save_to_database_async(results_data)
            
            results = results_data.get('results', [])
            return {
                "success": True,
                "saved_count": len(results),
                "target_username": results_data.get('target_username', ''),
                "message": f"成功保存 {len(results)} 個貼文到資料庫"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"保存失敗: {str(e)}",
                "saved_count": 0
            }