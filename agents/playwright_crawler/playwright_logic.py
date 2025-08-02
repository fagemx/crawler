"""
Playwright 爬蟲核心邏輯（重構版）
"""
import json
import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

from common.settings import get_settings
from common.models import PostMetrics, PostMetricsBatch
from common.nats_client import publish_progress
from common.utils import generate_post_url, first_of, parse_thread_item
from common.history import crawl_history

# 導入重構後的模組
from .parsers.number_parser import parse_number
from .parsers.post_parser import parse_post_data
from .extractors.url_extractor import URLExtractor
from .extractors.views_extractor import ViewsExtractor
from .extractors.details_extractor import DetailsExtractor
from .config.field_mappings import FIELD_MAP
from .utils.post_deduplicator import apply_deduplication

# 調試檔案路徑
DEBUG_DIR = Path(__file__).parent / "debug"
DEBUG_DIR.mkdir(exist_ok=True)

# 設定日誌（避免重複配置）
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class PlaywrightLogic:
    """使用 Playwright 進行爬蟲的核心邏輯（重構版）"""
    
    def __init__(self):
        self.browser = None
        self.context = None
        self.settings = get_settings()
        
        # 初始化提取器
        self.url_extractor = URLExtractor()
        self.views_extractor = ViewsExtractor()
        self.details_extractor = DetailsExtractor()

    async def fetch_posts(
        self,
        username: str,
        extra_posts: int,  # 改為增量語義
        auth_json_content: Dict,
        task_id: str = None
    ) -> PostMetricsBatch:
        """
        增量爬取貼文
        
        Args:
            username: 目標用戶名
            extra_posts: 需要額外抓取的貼文數量
            auth_json_content: 認證資訊
            task_id: 任務ID
        """
        if task_id is None:
            task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
        logging.info(f"🚀 [Task: {task_id}] 開始增量爬取 @{username}，目標: {extra_posts} 篇新貼文")
        
        try:
            # 步驟1: 初始化瀏覽器和認證
            await self._setup_browser_and_auth(auth_json_content, task_id)
            
            # 步驟2: 獲取現有貼文ID，計算需要抓取的數量
            existing_post_ids = await crawl_history.get_existing_post_ids(username)
            need_to_fetch = extra_posts
            
            logging.info(f"📚 {username} 已有 {len(existing_post_ids)} 篇貼文，需要新增 {need_to_fetch} 篇")
            
            # 步驟3: 使用URLExtractor獲取URL列表（帶早停機制）
            page = await self.context.new_page()
            await page.goto(f"https://www.threads.com/@{username}")
            
            ordered_urls = await self.url_extractor.get_ordered_post_urls_from_page(
                page, username, max_posts=need_to_fetch + 10  # 多抓一些以防重複
            )
            
            # 步驟4: 過濾出新貼文URLs（增量邏輯）
            ordered_posts = []
            new_posts_found = 0
            
            for url in ordered_urls:
                if new_posts_found >= need_to_fetch:
                    break  # 早停機制
                    
                post_id = url.split('/')[-1]
                if post_id not in existing_post_ids:
                    # 創建基礎PostMetrics
                    post_metrics = PostMetrics(
                        post_id=f"{username}_{post_id}",
                        username=username,
                        url=url,
                        content="",
                        created_at=datetime.utcnow(),
                        fetched_at=datetime.utcnow(),
                        source="playwright_incremental",
                        processing_stage="urls_extracted",
                        is_complete=False,
                        likes_count=0,
                        comments_count=0,
                        reposts_count=0,
                        shares_count=0,
                        views_count=None,
                    )
                    ordered_posts.append(post_metrics)
                    new_posts_found += 1
                    
                    logging.info(f"✅ 發現新貼文 {new_posts_found}/{need_to_fetch}: {post_id}")
            
            logging.info(f"✅ [Task: {task_id}] 創建了 {len(ordered_posts)} 個有序的基礎PostMetrics")
            await page.close()

            # 步驟5: 使用DetailsExtractor補齊詳細數據
            final_posts = ordered_posts
            logging.info(f"🔍 [Task: {task_id}] 開始 DOM 數據補齊...")
            await publish_progress(task_id, "fill_details_start", username=username, posts_count=len(final_posts))
            
            try:
                final_posts = await self.details_extractor.fill_post_details_from_page(final_posts, self.context, task_id=task_id, username=username)
                logging.info(f"✅ [Task: {task_id}] 詳細數據補齊完成")
                await publish_progress(task_id, "fill_details_completed", username=username, posts_count=len(final_posts))
            except Exception as e:
                logging.warning(f"⚠️ [Task: {task_id}] 補齊詳細數據時發生錯誤: {e}")
            
            # 步驟6: 使用ViewsExtractor補齊觀看數
            logging.info(f"🔍 [Task: {task_id}] 開始補齊觀看數...")
            await publish_progress(task_id, "fill_views_start", username=username, posts_count=len(final_posts))
            
            try:
                final_posts = await self.views_extractor.fill_views_from_page(final_posts, self.context, task_id=task_id, username=username)
                logging.info(f"✅ [Task: {task_id}] 觀看數補齊完成")
                await publish_progress(task_id, "fill_views_completed", username=username, posts_count=len(final_posts))
            except Exception as e:
                logging.warning(f"⚠️ [Task: {task_id}] 補齊觀看數時發生錯誤: {e}")

            # 步驟7: 去重處理（保留主貼文，過濾回應）
            logging.info(f"🔄 [Task: {task_id}] 開始去重處理...")
            final_posts = apply_deduplication(final_posts)
            logging.info(f"✅ [Task: {task_id}] 去重完成，最終貼文數: {len(final_posts)}")

            # 步驟7.5: 補足機制（如果去重後不足目標數量）
            if len(final_posts) < need_to_fetch:
                shortage = need_to_fetch - len(final_posts)
                logging.info(f"⚠️ [Task: {task_id}] 去重後貼文不足！需要: {need_to_fetch}，實際: {len(final_posts)}，缺少: {shortage}")
                
                # 實施補足策略
                max_supplement_rounds = 2  # 最多2輪補足
                
                for supplement_round in range(1, max_supplement_rounds + 1):
                    current_shortage = need_to_fetch - len(final_posts)
                    if current_shortage <= 0:
                        break
                        
                    # 動態增加爬取數量：缺幾則就多爬幾倍
                    supplement_target = current_shortage * (2 + supplement_round)  # 第1輪×3，第2輪×4
                    
                    logging.info(f"🔄 [Task: {task_id}] 補足第 {supplement_round} 輪：還缺 {current_shortage} 則，將爬 {supplement_target} 則")
                    
                    try:
                        # 重新爬取更多貼文
                        supplement_page = await self.context.new_page()
                        await supplement_page.goto(f"https://www.threads.com/@{username}")
                        
                        supplement_urls = await self.url_extractor.get_ordered_post_urls_from_page(
                            supplement_page, username, max_posts=supplement_target
                        )
                        await supplement_page.close()
                        
                        # 過濾出新的貼文URLs
                        existing_post_ids_expanded = existing_post_ids | {p.post_id for p in final_posts}
                        supplement_posts = []
                        
                        for url in supplement_urls:
                            post_id = url.split('/')[-1]
                            full_post_id = f"{username}_{post_id}"
                            
                            if full_post_id not in existing_post_ids_expanded:
                                supplement_posts.append(PostMetrics(
                                    post_id=full_post_id,
                                    username=username,
                                    url=url,
                                    content="",
                                    created_at=datetime.utcnow(),
                                    fetched_at=datetime.utcnow(),
                                    source=f"playwright_supplement_r{supplement_round}",
                                    processing_stage="urls_extracted",
                                    is_complete=False,
                                    likes_count=0, comments_count=0, reposts_count=0, shares_count=0, views_count=None,
                                ))
                        
                        if supplement_posts:
                            # 補齊數據
                            supplement_posts = await self.details_extractor.fill_post_details_from_page(supplement_posts, self.context, task_id=task_id, username=username)
                            supplement_posts = await self.views_extractor.fill_views_from_page(supplement_posts, self.context, task_id=task_id, username=username)
                            
                            # 本輪去重
                            supplement_posts = apply_deduplication(supplement_posts)
                            
                            # 與現有貼文合併去重
                            combined_posts = final_posts + supplement_posts
                            combined_posts = apply_deduplication(combined_posts)
                            
                            added_count = len(combined_posts) - len(final_posts)
                            final_posts = combined_posts
                            
                            logging.info(f"✅ [Task: {task_id}] 補足第 {supplement_round} 輪完成：新增 {added_count} 則，累計 {len(final_posts)} 則")
                            
                        else:
                            logging.info(f"⚠️ [Task: {task_id}] 補足第 {supplement_round} 輪：無新貼文可補充")
                            break
                            
                    except Exception as e:
                        logging.warning(f"⚠️ [Task: {task_id}] 補足第 {supplement_round} 輪失敗: {e}")
                        break
                
                final_count = len(final_posts)
                if final_count >= need_to_fetch:
                    logging.info(f"🎯 [Task: {task_id}] 補足成功！目標: {need_to_fetch}，最終: {final_count}")
                else:
                    logging.warning(f"⚠️ [Task: {task_id}] 補足未達標：目標: {need_to_fetch}，最終: {final_count}")

            # 步驟8: 保存調試數據
            await self._save_debug_data(task_id, username, len(ordered_urls), final_posts)
            await publish_progress(task_id, "completed", username=username, posts_count=len(final_posts))

            # 步驟9: 保存到數據庫並更新狀態
            saved_count = await crawl_history.upsert_posts(final_posts)
            logging.info(f"✅ 成功處理 {saved_count}/{len(final_posts)} 篇貼文")
            
            # 更新爬取狀態
            if final_posts:
                latest_post_id = final_posts[0].post_id
                await crawl_history.update_crawl_state(username, latest_post_id, saved_count)
                logging.info(f"📊 更新 {username} 狀態: latest={latest_post_id}, +{saved_count}篇")
            
            # 步驟10: 生成任務指標
            task_metrics = await crawl_history.get_task_metrics(username, need_to_fetch, len(final_posts))
            logging.info(f"📊 任務完成: {task_metrics}")

            return PostMetricsBatch(
                posts=final_posts,
                batch_id=task_id,
                username=username,
                total_count=len(final_posts),
                processing_stage="playwright_incremental_completed"
            )

        except Exception as e:
            logging.error(f"❌ [Task: {task_id}] 爬取過程發生錯誤: {e}")
            await publish_progress(task_id, "error", message=f"爬取失敗: {str(e)}")
            raise e
        finally:
            await self._cleanup(task_id)

    async def _setup_browser_and_auth(self, auth_json_content: Dict, task_id: str):
        """設置瀏覽器和認證"""
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=True)
        self.context = await self.browser.new_context()
        
        # 設置認證
        auth_file = Path(tempfile.gettempdir()) / f"{task_id}_auth.json"
        auth_file.write_text(json.dumps(auth_json_content))
        
        await self.context.add_cookies(auth_json_content.get('cookies', []))
        logging.info(f"🔐 [Task: {task_id}] 認證設置完成")

    async def _cleanup(self, task_id: str):
        """清理資源"""
        try:
            if self.browser:
                await self.browser.close()
            
            # 刪除臨時認證檔案
            auth_file = Path(tempfile.gettempdir()) / f"{task_id}_auth.json"
            if auth_file.exists():
                auth_file.unlink()
                logging.info(f"🗑️ [Task: {task_id}] 已刪除臨時認證檔案: {auth_file}")
            self.context = None
        except Exception as e:
            logging.warning(f"⚠️ [Task: {task_id}] 清理資源時發生錯誤: {e}") 

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