"""
Playwright 爬蟲核心邏輯（重構版）
使用模塊化架構，從1377行縮減到精簡的協調層
"""

import asyncio
import json
import logging
import tempfile
import uuid
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from playwright.async_api import async_playwright, BrowserContext

from common.settings import get_settings
from common.models import PostMetrics, PostMetricsBatch
from common.nats_client import publish_progress
from common.history import crawl_history

# 導入拆分後的模塊
from .extractors import URLExtractor, ViewsExtractor, DetailsExtractor

# 調試檔案路徑
DEBUG_DIR = Path(__file__).parent / "debug"
DEBUG_DIR.mkdir(exist_ok=True)

# 設定日誌（避免重複配置）
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class PlaywrightLogic:
    """使用 Playwright 進行爬蟲的核心邏輯（重構版）"""
    
    def __init__(self):
        self.settings = get_settings().playwright
        self.context: Optional[BrowserContext] = None
        
        # 提取器將在context建立後初始化
        self.url_extractor = None
        self.views_extractor = None
        self.details_extractor = None

    def _init_extractors(self):
        """初始化所有提取器（需要在context建立後呼叫）"""
        if self.context:
            self.url_extractor = URLExtractor()
            self.views_extractor = ViewsExtractor(self.context)
            self.details_extractor = DetailsExtractor(self.context)

    async def fetch_posts(
        self,
        username: str,
        extra_posts: int,
        auth_json_content: Dict,
        task_id: str = None
    ) -> PostMetricsBatch:
        """使用指定的認證內容進行增量爬取。"""
        if task_id is None:
            task_id = str(uuid.uuid4())
        
        # 增量爬取邏輯
        if extra_posts <= 0:
            logging.info(f"🟢 {username} 無需額外爬取 (extra_posts={extra_posts})")
            existing_state = await crawl_history.get_crawl_state(username)
            total_existing = existing_state.get("total_crawled", 0) if existing_state else 0
            return PostMetricsBatch(posts=[], username=username, total_count=total_existing)
        
        existing_post_ids = await crawl_history.get_existing_post_ids(username)
        already_count = len(existing_post_ids)
        need_to_fetch = extra_posts
        
        logging.info(f"📊 {username} 增量狀態: 已有={already_count}, 需要新增={need_to_fetch}")
        
        await publish_progress(task_id, "fetch_start", username=username, extra_posts=extra_posts)
        
        # 安全地將 auth.json 內容寫入臨時檔案
        auth_file = Path(tempfile.gettempdir()) / f"{task_id or uuid.uuid4()}_auth.json"
        try:
            with open(auth_file, 'w', encoding='utf-8') as f:
                json.dump(auth_json_content, f)

            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=self.settings.headless,
                    timeout=self.settings.navigation_timeout,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
                )
                self.context = await browser.new_context(
                    storage_state=str(auth_file),
                    user_agent=self.settings.user_agent,
                    viewport={"width": 1920, "height": 1080},
                    locale="zh-TW",
                    has_touch=True,
                    accept_downloads=False,
                    bypass_csp=True
                )
                await self.context.add_init_script(
                    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
                )
                
                # 初始化提取器
                self._init_extractors()
                
                page = await self.context.new_page()
                page.on("console", lambda m: logging.info(f"CONSOLE [{m.type}] {m.text}"))

                # 步驟1: 使用URLExtractor獲取有序URLs
                logging.info(f"🎯 [Task: {task_id}] 增量爬取: 需要{need_to_fetch}篇新貼文")
                buffer_size = min(need_to_fetch + 10, 50)
                ordered_post_urls = await self.url_extractor.get_ordered_post_urls_from_page(page, username, buffer_size)
                
                if not ordered_post_urls:
                    logging.warning(f"⚠️ [Task: {task_id}] 無法從用戶頁面獲取貼文 URLs")
                    return PostMetricsBatch(posts=[], username=username, total_count=already_count)

                # 步驟2: 增量優化：去重+精確早停
                logging.info(f"✅ [Task: {task_id}] 增量篩選: 從{len(ordered_post_urls)}個URL中尋找{need_to_fetch}篇新貼文")
                ordered_posts = []
                new_posts_found = 0
                
                for i, post_url in enumerate(ordered_post_urls):
                    url_parts = post_url.split('/')
                    if len(url_parts) >= 2:
                        code = url_parts[-1] if url_parts[-1] != 'media' else url_parts[-2]
                        post_id = f"{username}_{code}"
                        
                        # 核心去重邏輯
                        if post_id in existing_post_ids:
                            logging.debug(f"⏭️ 跳過已存在: {post_id}")
                            continue
                        
                        # 精確早停機制
                        if new_posts_found >= need_to_fetch:
                            logging.info(f"🎯 提早停止: 已收集到{need_to_fetch}篇新貼文")
                            break
                        
                        # 創建新的PostMetrics
                        post_metrics = PostMetrics(
                            url=post_url,
                            post_id=post_id,
                            username=username,
                            source="playwright_incremental",
                            processing_stage="url_extracted",
                            likes_count=0,
                            comments_count=0,
                            reposts_count=0,
                            shares_count=0,
                            content="",
                            created_at=datetime.utcnow(),
                            images=[],
                            videos=[],
                            views_count=None,
                        )
                        ordered_posts.append(post_metrics)
                        new_posts_found += 1
                        
                        logging.info(f"✅ 發現新貼文 {new_posts_found}/{need_to_fetch}: {post_id}")
                
                logging.info(f"✅ [Task: {task_id}] 創建了 {len(ordered_posts)} 個有序的基礎PostMetrics")
                await page.close()

                # 步驟3: 使用DetailsExtractor補齊詳細數據
                final_posts = ordered_posts
                logging.info(f"🔍 [Task: {task_id}] 開始 DOM 數據補齊...")
                await publish_progress(task_id, "fill_details_start", username=username, posts_count=len(final_posts))
                
                try:
                    final_posts = await self.details_extractor.fill_post_details_from_page(final_posts, task_id=task_id, username=username)
                    logging.info(f"✅ [Task: {task_id}] 詳細數據補齊完成")
                    await publish_progress(task_id, "fill_details_completed", username=username, posts_count=len(final_posts))
                except Exception as e:
                    logging.warning(f"⚠️ [Task: {task_id}] 補齊詳細數據時發生錯誤: {e}")
                
                # 步驟4: 使用ViewsExtractor補齊觀看數
                logging.info(f"🔍 [Task: {task_id}] 開始補齊觀看數...")
                await publish_progress(task_id, "fill_views_start", username=username, posts_count=len(final_posts))
                
                try:
                    final_posts = await self.views_extractor.fill_views_from_page(final_posts, task_id=task_id, username=username)
                    logging.info(f"✅ [Task: {task_id}] 觀看數補齊完成")
                    await publish_progress(task_id, "fill_views_completed", username=username, posts_count=len(final_posts))
                except Exception as e:
                    logging.warning(f"⚠️ [Task: {task_id}] 補齊觀看數時發生錯誤: {e}")

                await self.context.close()
                await browser.close()
                self.context = None
            
            # 保存調試數據
            await self._save_debug_data(task_id, username, len(final_posts), final_posts)
            
            await publish_progress(task_id, "completed", username=username, total_posts=len(final_posts), success=True)

            # 更新爬取狀態
            if final_posts:
                saved_count = await crawl_history.upsert_posts(final_posts)
                latest_post_id = final_posts[0].post_id if final_posts else None
                if latest_post_id:
                    await crawl_history.update_crawl_state(username, latest_post_id, saved_count)
                
                task_metrics = await crawl_history.get_task_metrics(username, need_to_fetch, len(final_posts))
                logging.info(f"📊 任務完成: {task_metrics}")
            
            return PostMetricsBatch(
                posts=final_posts,
                username=username,
                total_count=already_count + len(final_posts),
                processing_stage="playwright_incremental_completed"
            )
            
        except Exception as e:
            error_message = f"Playwright 核心邏輯出錯: {e}"
            logging.error(error_message, exc_info=True)
            await publish_progress(task_id, "error", username=username, error=error_message, success=False)
            raise
        
        finally:
            if auth_file.exists():
                auth_file.unlink()
                logging.info(f"🗑️ [Task: {task_id}] 已刪除臨時認證檔案: {auth_file}")
            self.context = None 

    async def _save_debug_data(self, task_id: str, username: str, total_found: int, final_posts: List[PostMetrics]):
        """保存調試數據"""
        try:
            raw_data = {
                "task_id": task_id,
                "username": username, 
                "timestamp": datetime.now().isoformat(),
                "total_found": total_found,
                "returned_count": len(final_posts),
                "posts": [
                    {
                        "url": post.url,
                        "post_id": post.post_id,
                        "likes_count": post.likes_count,
                        "comments_count": post.comments_count,
                        "reposts_count": post.reposts_count,
                        "shares_count": post.shares_count,
                        "views_count": post.views_count,
                        "calculated_score": post.calculate_score(),
                        "content": post.content,
                        "created_at": post.created_at.isoformat() if post.created_at else None,
                        "images": post.images,
                        "videos": post.videos
                    } for post in final_posts
                ]
            }
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            raw_file = DEBUG_DIR / f"crawl_data_{timestamp}_{task_id[:8]}.json"
            raw_file.write_text(json.dumps(raw_data, indent=2, ensure_ascii=False), encoding="utf-8")
            logging.info(f"💾 [Task: {task_id}] 已保存原始抓取資料至: {raw_file}")
            
        except Exception as e:
            logging.warning(f"⚠️ [Task: {task_id}] 保存調試資料失敗: {e}")