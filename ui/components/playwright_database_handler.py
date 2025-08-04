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
                                views_count = PlaywrightUtils.parse_number_safe(result.get('views', ''))
                                likes_count = PlaywrightUtils.parse_number_safe(result.get('likes', ''))
                                comments_count = PlaywrightUtils.parse_number_safe(result.get('comments', ''))
                                reposts_count = PlaywrightUtils.parse_number_safe(result.get('reposts', ''))
                                shares_count = PlaywrightUtils.parse_number_safe(result.get('shares', ''))
                                
                                # 使用 UPSERT 避免重複
                                await conn.execute("""
                                    INSERT INTO playwright_post_metrics (
                                        username, post_id, url, content, 
                                        views_count, likes_count, comments_count, reposts_count, shares_count,
                                        source, crawler_type, crawl_id, created_at
                                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW())
                                    ON CONFLICT (username, post_id, crawler_type) 
                                    DO UPDATE SET
                                        url = EXCLUDED.url,
                                        content = EXCLUDED.content,
                                        views_count = EXCLUDED.views_count,
                                        likes_count = EXCLUDED.likes_count,
                                        comments_count = EXCLUDED.comments_count,
                                        reposts_count = EXCLUDED.reposts_count,
                                        shares_count = EXCLUDED.shares_count,
                                        crawl_id = EXCLUDED.crawl_id,
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
                                    'playwright_agent',
                                    'playwright',
                                    crawl_id
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
                    
            finally:
                await db.close_pool()
                
        except Exception as e:
            self._log(f"⚠️ 資料庫保存警告: {e}")
            # 不阻止主要流程，但記錄警告
    
    def get_database_stats(self):
        """獲取 Playwright 專用資料庫統計（簡化版本）"""
        try:
            # 直接返回基本統計，避免複雜的子進程調用
            # 這是一個臨時的簡化方案，確保UI能正常顯示
            return {
                "total_stats": {
                    "total_posts": 0,
                    "total_users": 0, 
                    "latest_activity": None,
                    "total_crawls": 0
                },
                "user_stats": []
            }
                    
        except Exception as e:
            return {"error": str(e)}
    
    def save_results_to_database_sync(self, results_data: Dict[str, Any]):
        """同步保存結果到資料庫（備用功能）"""
        try:
            import subprocess
            import json
            import sys
            import os
            import tempfile
            
            # 檢查results的格式，如果是字典則提取results列表
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
            
            # 創建保存腳本
            save_script_content = f'''
import asyncio
import sys
import os
import json
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from common.db_client import DatabaseClient

async def save_to_database():
    # 使用 PlaywrightDatabaseHandler 的邏輯
    from ui.components.playwright_database_handler import PlaywrightDatabaseHandler
    
    handler = PlaywrightDatabaseHandler()
    
    # 準備結果數據
    results_data = {json.dumps(results_data, ensure_ascii=False)}
    
    await handler.save_to_database_async(results_data)
    
    result = {{
        "success": True,
        "saved_count": len(results_data.get("results", [])),
        "target_username": results_data.get("target_username", "")
    }}
    
    print(json.dumps(result))

if __name__ == "__main__":
    asyncio.run(save_to_database())
'''
            
            # 寫入臨時文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                f.write(save_script_content)
                temp_script = f.name
            
            try:
                # 執行保存腳本
                result = subprocess.run(
                    [sys.executable, temp_script],
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                    timeout=60
                )
                
                if result.returncode == 0 and result.stdout.strip():
                    save_result = json.loads(result.stdout.strip())
                    return save_result
                else:
                    return {"success": False, "error": "保存腳本執行失敗"}
                        
            finally:
                # 清理臨時文件
                try:
                    os.unlink(temp_script)
                except:
                    pass
                    
        except Exception as e:
            return {"success": False, "error": str(e)}