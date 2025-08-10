"""
Playwright 爬蟲核心邏輯（重構版）
"""
import json
import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Any, Literal
from datetime import datetime, timezone, timedelta

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

from common.settings import get_settings
from common.models import PostMetrics, PostMetricsBatch
from common.nats_client import publish_progress
from common.utils import generate_post_url, first_of, parse_thread_item
from common.history import crawl_history

def get_taipei_time():
    """獲取當前台北時間（無時區信息）"""
    taipei_tz = timezone(timedelta(hours=8))
    return datetime.now(taipei_tz).replace(tzinfo=None)

# 導入重構後的模組
from .parsers.number_parser import parse_number
from .parsers.post_parser import parse_post_data
from .extractors.url_extractor import URLExtractor
from .extractors.views_extractor import ViewsExtractor
from .extractors.details_extractor import DetailsExtractor
from .config.field_mappings import FIELD_MAP
from .utils.post_deduplicator import apply_deduplication
from .helpers.scrolling import (
    extract_current_post_ids, check_page_bottom, scroll_once, 
    is_anchor_visible, collect_urls_from_dom, 
    should_stop_new_mode, should_stop_hist_mode,
    enhanced_scroll_with_strategy, wait_for_content_loading,
    final_attempt_scroll, progressive_wait, should_stop_incremental_mode
)

# 調試檔案路徑
DEBUG_DIR = Path(__file__).parent / "debug"
DEBUG_DIR.mkdir(exist_ok=True)

# 設定日誌（避免重複配置），強制使用台北時區顯示 asctime
class TaipeiTimezoneFormatter(logging.Formatter):
    def converter(self, timestamp):
        tz = timezone(timedelta(hours=8))
        return datetime.fromtimestamp(timestamp, tz).timetuple()

if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    for handler in logging.getLogger().handlers:
        handler.setFormatter(TaipeiTimezoneFormatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))


class PlaywrightLogic:
    """使用 Playwright 進行爬蟲的核心邏輯（重構版）"""
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
    
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
        extra_posts: int,  # 需要的貼文數量
        auth_json_content: Dict,
        task_id: str = None,
        mode: Literal["new", "hist"] = "new",  # 爬取模式
        anchor_post_id: str = None,            # 錨點貼文ID  
        max_scroll_rounds: int = 30,           # 最大滾動輪次
        incremental: bool = True,              # 新增：增量模式
        enable_deduplication: bool = True,     # 新增：去重開關
        realtime_download: bool = False        # 🆕 新增：即時下載媒體
    ) -> PostMetricsBatch:
        """
        智能增量爬取貼文 - 支持新貼文補足和歷史回溯
        
        Args:
            username: 目標用戶名
            extra_posts: 需要額外抓取的貼文數量
            auth_json_content: 認證資訊
            task_id: 任務ID
            mode: 爬取模式 ("new"=新貼文補足, "hist"=歷史回溯)
            anchor_post_id: 錨點貼文ID，自動從crawl_state獲取
            max_scroll_rounds: 最大滾動輪次，防止無限滾動
        """
        if task_id is None:
            task_id = f"task_{get_taipei_time().strftime('%Y%m%d_%H%M%S')}"
        
        # 內部台北時間函數
        def get_taipei_time():
            """獲取當前台北時間（無時區信息）"""
            taipei_tz = timezone(timedelta(hours=8))
            return datetime.now(taipei_tz).replace(tzinfo=None)
        
        # 內部條件去重函數
        def conditional_deduplication(posts_list):
            """根據 enable_deduplication 參數決定是否執行去重"""
            if enable_deduplication:
                return apply_deduplication(posts_list)
            else:
                logging.info(f"⚠️ [Task: {task_id}] 去重已關閉，保留所有 {len(posts_list)} 篇貼文")
                return posts_list
            
        logging.info(f"🚀 [Task: {task_id}] 開始{mode.upper()}模式爬取 @{username}，目標: {extra_posts} 篇")
        logging.info(f"🧹 [Task: {task_id}] 去重功能: {'啟用' if enable_deduplication else '關閉'}")
        logging.info(f"⬇️ [Task: {task_id}] 即時下載: {'啟用' if realtime_download else '關閉'}")
        
        try:
            # 步驟1: 初始化瀏覽器和認證
            await self._setup_browser_and_auth(auth_json_content, task_id)
            
            # 步驟2: 獲取現有貼文ID和爬取狀態（增量模式）
            existing_post_ids = set()
            if incremental:
                existing_post_ids = await crawl_history.get_existing_post_ids(username)
                crawl_state = await crawl_history.get_crawl_state(username)
                
                # 確定錨點貼文ID
                if anchor_post_id is None and crawl_state:
                    anchor_post_id = crawl_state.get('latest_post_id')
                    
                logging.info(f"🔍 增量模式: 已爬取 {len(existing_post_ids)} 個貼文")
                logging.info(f"📍 錨點設定: {anchor_post_id or '無'}")
                
                # 調試：顯示已存在的貼文ID（最多顯示10個）
                if existing_post_ids:
                    sample_ids = list(existing_post_ids)[:10]
                    logging.info(f"🔍 [DEBUG] 已存在貼文範例: {sample_ids}")
                else:
                    logging.info(f"🔍 [DEBUG] 資料庫中無現有貼文")
            else:
                logging.info(f"📋 全量模式: 爬取所有找到的貼文")
            
            need_to_fetch = extra_posts
            
            # 步驟3: 採用Realtime策略 - 足額收集URLs
            logging.info(f"🔄 [Task: {task_id}] 開始智能URL收集（目標: {need_to_fetch} 篇）...")
            page = await self.context.new_page()
            await page.goto(f"https://www.threads.com/@{username}", wait_until="domcontentloaded")
            await asyncio.sleep(2)
            
            # 使用Realtime風格的URL收集
            all_collected_urls = await self._collect_urls_realtime_style(
                page, username, need_to_fetch, existing_post_ids, incremental, max_scroll_rounds
            )
            await page.close()
            
            if not all_collected_urls:
                logging.warning(f"❌ [Task: {task_id}] 沒有收集到任何新的URL")
                return PostMetricsBatch(posts=[], username=username, total_count=0)
            
            logging.info(f"✅ [Task: {task_id}] URL收集完成！收集到 {len(all_collected_urls)} 個URL")
            
            # 步驟4: 智能分批處理策略（重點：不足時從剩餘URL補足）
            final_posts = []
            url_pool = all_collected_urls.copy()
            
            # 初始化已處理的貼文ID集合（包含資料庫中的）
            processed_post_ids = set()
            if incremental:
                # 增量模式：將資料庫中已存在的貼文ID加入已處理集合
                for existing_id in existing_post_ids:
                    # existing_post_ids 已經是 username_postid 格式
                    processed_post_ids.add(existing_id)
                logging.info(f"🔍 [Task: {task_id}] 增量模式：預先排除 {len(processed_post_ids)} 個已存在貼文")
            
            max_process_rounds = 3  # 最多處理3輪
            
            for process_round in range(1, max_process_rounds + 1):
                if len(final_posts) >= need_to_fetch or not url_pool:
                    break
                    
                # 過濾掉已處理過的URL（重點修復！）
                filtered_url_pool = []
                for url in url_pool:
                    post_id = url.split('/')[-1] if url else None
                    full_post_id = f"{username}_{post_id}"
                    
                    # 跳過已處理的貼文ID
                    if full_post_id not in processed_post_ids:
                        filtered_url_pool.append(url)
                    else:
                        logging.debug(f"   ⏭️ 跳過已處理的貼文: {full_post_id}")
                
                url_pool = filtered_url_pool
                
                if not url_pool:
                    logging.warning(f"⚠️ [Task: {task_id}] 第 {process_round} 輪：過濾後無剩餘URL可處理")
                    break
                    
                # 計算這輪需要處理的數量
                shortage = need_to_fetch - len(final_posts)
                batch_size = min(shortage + 2, len(url_pool))  # 多處理2個防止去重後不足
                current_batch_urls = url_pool[:batch_size]
                url_pool = url_pool[batch_size:]
                
                # 記錄這輪將要處理的貼文ID
                for url in current_batch_urls:
                    post_id = url.split('/')[-1] if url else None
                    full_post_id = f"{username}_{post_id}"
                    processed_post_ids.add(full_post_id)
                
                logging.info(f"🔄 [Task: {task_id}] 第 {process_round} 輪處理：{len(current_batch_urls)} 個URL (還需 {shortage} 篇)")
                
                # 轉換URLs為PostMetrics並過濾非目標用戶
                batch_posts = await self._convert_urls_to_posts(current_batch_urls, username, mode, task_id)
                
                if not batch_posts:
                    logging.warning(f"⚠️ [Task: {task_id}] 第 {process_round} 輪：轉換後無有效貼文")
                    continue
                
                # 詳細數據補齊
                logging.info(f"🔍 [Task: {task_id}] 第 {process_round} 輪：開始數據補齊...")
                await publish_progress(task_id, f"process_round_{process_round}_details", username=username, posts_count=len(batch_posts))
                
                try:
                    batch_posts = await self.details_extractor.fill_post_details_from_page(batch_posts, self.context, task_id=task_id, username=username)
                    batch_posts = await self.views_extractor.fill_views_from_page(batch_posts, self.context, task_id=task_id, username=username)
                    logging.info(f"✅ [Task: {task_id}] 第 {process_round} 輪：數據補齊完成")
                    
                    # 🆕 即時下載邏輯
                    if realtime_download:
                        await self._realtime_download_media(batch_posts, task_id, username)
                        
                except Exception as e:
                    logging.warning(f"⚠️ [Task: {task_id}] 第 {process_round} 輪數據補齊失敗: {e}")
                
                # 合併並去重處理（重點：每輪都要去重檢查）
                combined_posts = final_posts + batch_posts
                before_dedup_count = len(combined_posts)
                combined_posts = conditional_deduplication(combined_posts)
                after_dedup_count = len(combined_posts)
                
                added_count = after_dedup_count - len(final_posts)
                removed_count = before_dedup_count - after_dedup_count
                final_posts = combined_posts
                
                logging.info(f"✅ [Task: {task_id}] 第 {process_round} 輪完成：新增 {added_count} 篇，去重移除 {removed_count} 篇，累計 {len(final_posts)} 篇")
                
                # 檢查是否已足夠
                if len(final_posts) >= need_to_fetch:
                    logging.info(f"🎯 [Task: {task_id}] 已達目標數量！最終: {len(final_posts)} 篇")
                    break
                elif not url_pool:
                    logging.warning(f"⚠️ [Task: {task_id}] URL池已空，但數量不足（{len(final_posts)}/{need_to_fetch}）")
                    break
            
            # 最終檢查和統計
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
                        
                        logging.info(f"🔍 [Task: {task_id}] 補足過濾：找到 {len(supplement_urls)} 個URLs，已有 {len(existing_post_ids_expanded)} 個ID")
                        
                        for url in supplement_urls:
                            # 驗證URL是否確實屬於目標用戶
                            if f"@{username}/post/" not in url:
                                logging.warning(f"⚠️ 補足階段跳過非目標用戶的URL: {url}")
                                continue
                                
                            post_id = url.split('/')[-1]
                            full_post_id = f"{username}_{post_id}"
                            
                            logging.debug(f"🔍 檢查URL: {url} → {full_post_id} → 存在: {full_post_id in existing_post_ids_expanded}")
                            
                            # 臨時修復：在測試模式下允許重新爬取（如果existing很少）
                            is_test_mode = len(existing_post_ids_expanded) < 50  # 小於50個ID認為是測試
                            should_include = (full_post_id not in existing_post_ids_expanded) or is_test_mode
                            
                            if should_include:
                                supplement_posts.append(PostMetrics(
                                    post_id=full_post_id,
                                    username=username,
                                    url=url,
                                    content="",
                                    created_at=get_taipei_time(),
                                    fetched_at=get_taipei_time(),
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
                            supplement_posts = conditional_deduplication(supplement_posts)
                            
                            # 與現有貼文合併去重
                            combined_posts = final_posts + supplement_posts
                            combined_posts = conditional_deduplication(combined_posts)
                            
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
                    final_shortage = need_to_fetch - final_count
                    logging.warning(f"⚠️ [Task: {task_id}] 補足未達標：目標: {need_to_fetch}，最終: {final_count}，仍缺: {final_shortage}")
                    
                    # === 新增：啟動增強滾動收集策略 ===
                    logging.info(f"🚀 [Task: {task_id}] 啟動增強滾動收集，使用Realtime策略...")
                    
                    try:
                        # 創建新頁面進行增強收集
                        enhanced_page = await self.context.new_page()
                        await enhanced_page.goto(f"https://www.threads.com/@{username}")
                        await asyncio.sleep(3)  # 等待頁面載入
                        
                        # 使用增強的收集策略
                        existing_post_ids_final = existing_post_ids | {p.post_id for p in final_posts}
                        extended_max_scroll_rounds = max_scroll_rounds + 30  # 額外30輪滾動
                        
                        additional_urls = await self._collect_urls_realtime_style(
                            enhanced_page, username, final_shortage + 10,  # 多收集10個作為緩衝
                            existing_post_ids_final, incremental, extended_max_scroll_rounds
                        )
                        
                        await enhanced_page.close()
                        
                        if additional_urls:
                            logging.info(f"🎯 [Task: {task_id}] 增強收集到 {len(additional_urls)} 個額外URL")
                            
                            # 處理額外收集的URLs
                            additional_posts = await self._convert_urls_to_posts(additional_urls, username, mode, task_id)
                            additional_posts = await self.details_extractor.process_posts(
                                additional_posts, task_id=task_id
                            )
                            
                            # 去重並合併
                            additional_posts = conditional_deduplication(additional_posts)
                            combined_posts = final_posts + additional_posts
                            combined_posts = conditional_deduplication(combined_posts)
                            
                            final_added = len(combined_posts) - len(final_posts)
                            final_posts = combined_posts
                            
                            logging.info(f"🎉 [Task: {task_id}] 增強收集完成：新增 {final_added} 篇，最終累計 {len(final_posts)} 篇")
                            
                            # 更新最終計數
                            final_count = len(final_posts)
                            if final_count >= need_to_fetch:
                                logging.info(f"✅ [Task: {task_id}] 增強收集達標！目標: {need_to_fetch}，最終: {final_count}")
                            else:
                                remaining_shortage = need_to_fetch - final_count
                                logging.warning(f"⚠️ [Task: {task_id}] 增強收集後仍未達標：還缺 {remaining_shortage} 篇")
                        else:
                            logging.warning(f"⚠️ [Task: {task_id}] 增強收集無新URL，可能已到達真正底部")
                            
                    except Exception as e:
                        logging.error(f"❌ [Task: {task_id}] 增強收集失敗: {e}")

            # 步驟5: 保存調試數據
            await self._save_debug_data(task_id, username, len(all_collected_urls), final_posts)
            
            # 準備完整的最終結果數據
            final_data = {
                "total_processed": len(final_posts),
                "username": username,
                "need_to_fetch": need_to_fetch,
                "success": True,
                "results": [
                    {
                        "post_id": post.post_id,
                        "url": post.url,
                        "content": post.content,
                        "views_count": post.views_count,  # 🔧 修復：使用正確的key名稱
                        "likes_count": post.likes_count,
                        "comments_count": post.comments_count,
                        "reposts_count": post.reposts_count,
                        "shares_count": post.shares_count,
                        "calculated_score": post.calculate_score(),  # 🔧 修復：調用方法計算分數
                        "post_published_at": post.post_published_at.isoformat() if post.post_published_at else None,  # 🔧 修復key名稱
                        "created_at": post.created_at.isoformat() if post.created_at else None,  # 🔧 添加創建時間
                        "tags": post.tags or [],  # 🔧 添加標籤
                        "images": post.images or [],  # 🔧 添加圖片
                        "videos": post.videos or [],  # 🔧 添加影片
                        "is_complete": post.is_complete
                    }
                    for post in final_posts
                ]
            }
            
            # 發布完成狀態和完整結果到 Redis
            await publish_progress(task_id, "completed", username=username, posts_count=len(final_posts), final_data=final_data)

            # 步驟9: 標記DOM處理狀態並保存到數據庫
            # 為所有完整處理的貼文標記DOM狀態為success
            for post in final_posts:
                if post.is_complete:
                    # 不設置 dom_status，因為 Playwright 專用表格沒有這些字段
                    # post.dom_status = "success"
                    # post.dom_processed_at = datetime.utcnow()
                    # 如果有內容但Reader狀態未設定，推斷為DOM提取的內容
                    if post.content: # and post.reader_status == "pending":
                        # 不設置 reader_status，因為 Playwright 專用表格沒有這些字段
                        # post.reader_status = "success"
                        # post.reader_processed_at = datetime.utcnow()
                        pass
                else:
                    # 不設置 dom_status，因為 Playwright 專用表格沒有這些字段
                    # post.dom_status = "failed"
                    pass
            
            # 不在後端保存到資料庫，讓前端UI處理資料庫保存
            # 這樣可以保持 Playwright 和 Realtime 爬蟲的數據分離
            # saved_count = await crawl_history.upsert_posts(final_posts)
            # logging.info(f"✅ 成功處理 {saved_count}/{len(final_posts)} 篇貼文")
            
            # 不更新爬取狀態，讓前端UI處理
            # if final_posts:
            #     latest_post_id = final_posts[0].post_id
            #     await crawl_history.update_crawl_state(username, latest_post_id, saved_count)
            #     logging.info(f"📊 更新 {username} 狀態: latest={latest_post_id}, +{saved_count}篇")
            
            logging.info(f"✅ 成功處理 {len(final_posts)} 篇貼文，資料庫保存將由前端UI處理")
            
            # 步驟10: 生成簡化的任務指標（不依賴資料庫）
            # task_metrics = await crawl_history.get_task_metrics(username, need_to_fetch, len(final_posts))
            task_metrics = {
                "total_processed": len(final_posts),
                "username": username,
                "need_to_fetch": need_to_fetch,
                "success": True
            }
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
        # 保存 playwright 實例，便於完整清理，避免 Windows Proactor 殘留管道
        self.playwright = await async_playwright().start()
        # 🎬 2025新版Threads影片提取優化 - 無手勢自動播放
        launch_args = [
            "--autoplay-policy=no-user-gesture-required",
            "--disable-background-media-suspend",
            "--disable-features=MediaSessionService",
            "--force-prefers-reduced-motion=0",
            "--disable-blink-features=AutomationControlled",
            "--disable-web-security",
            "--disable-features=VizDisplayCompositor",
        ]
        # 嚴格降級順序：channel=chrome → system 安裝 → 內建 chromium
        try:
            self.browser = await self.playwright.chromium.launch(channel="chrome", headless=True, args=launch_args)
        except Exception as e1:
            logging.warning(f"⚠️ Chrome channel 啟動失敗，嘗試 system chromium: {e1}")
            try:
                self.browser = await self.playwright.chromium.launch(executable_path="/usr/bin/chromium" , headless=True, args=launch_args)
            except Exception as e2:
                logging.warning(f"⚠️ system chromium 不可用，回退內建 chromium: {e2}")
                self.browser = await self.playwright.chromium.launch(headless=True, args=launch_args)
        # 創建context（自動播放通過launch args控制）
        self.context = await self.browser.new_context()
        
        # 設置認證
        auth_file = Path(tempfile.gettempdir()) / f"{task_id}_auth.json"
        auth_file.write_text(json.dumps(auth_json_content))
        
        await self.context.add_cookies(auth_json_content.get('cookies', []))
        logging.info(f"🔐 [Task: {task_id}] 認證設置完成")

    async def _cleanup(self, task_id: str):
        """清理資源（加強版：shield + timeout，避免 Chromium 殘留）"""
        try:
            # 先關閉 context，再關閉 browser，最後停止 playwright
            if self.context:
                try:
                    await asyncio.wait_for(asyncio.shield(self.context.close()), timeout=10)
                except Exception:
                    pass
                finally:
                    self.context = None

            if self.browser:
                try:
                    await asyncio.wait_for(asyncio.shield(self.browser.close()), timeout=10)
                except Exception:
                    pass
                finally:
                    self.browser = None
            
            # 刪除臨時認證檔案
            auth_file = Path(tempfile.gettempdir()) / f"{task_id}_auth.json"
            if auth_file.exists():
                try:
                    auth_file.unlink()
                    logging.info(f"🗑️ [Task: {task_id}] 已刪除臨時認證檔案: {auth_file}")
                except Exception:
                    pass

            if self.playwright:
                try:
                    await asyncio.wait_for(asyncio.shield(self.playwright.stop()), timeout=10)
                except Exception:
                    pass
                finally:
                    self.playwright = None
        except Exception as e:
            logging.warning(f"⚠️ [Task: {task_id}] 清理資源時發生錯誤: {e}") 

    async def _save_debug_data(self, task_id: str, username: str, total_found: int, final_posts: List[PostMetrics]):
        """保存調試數據"""
        try:
            raw_data = {
                "task_id": task_id,
                "username": username, 
                "timestamp": get_taipei_time().isoformat(),
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
                        "post_published_at": post.post_published_at.isoformat() if post.post_published_at else None,
                        "tags": post.tags,
                        "images": post.images,
                        "videos": post.videos
                    } for post in final_posts
                ]
            }
            
            timestamp = get_taipei_time().strftime("%Y%m%d_%H%M%S")
            raw_file = DEBUG_DIR / f"crawl_data_{timestamp}_{task_id[:8]}.json"
            raw_file.write_text(json.dumps(raw_data, indent=2, ensure_ascii=False), encoding="utf-8")
            logging.info(f"💾 [Task: {task_id}] 已保存原始抓取資料至: {raw_file}")
            
        except Exception as e:
            logging.warning(f"⚠️ [Task: {task_id}] 保存調試資料失敗: {e}")
    
    async def _realtime_download_media(self, posts: List, task_id: str, username: str):
        """
        即時下載媒體：在爬取完成後立即下載每個貼文的媒體檔案
        確保媒體URL的時效性，特別是Instagram影片
        """
        if not posts:
            return
            
        try:
            # 動態導入下載服務，避免循環依賴
            from agents.vision.media_download_service import MediaDownloadService
            
            logging.info(f"⬇️ [Task: {task_id}] 開始即時下載 {len(posts)} 個貼文的媒體...")
            
            # 建立下載計劃
            download_plan = {}
            media_count = 0
            
            for post in posts:
                media_urls = []
                
                # 收集圖片URL
                if hasattr(post, 'images') and post.images:
                    media_urls.extend(post.images)
                    
                # 收集影片URL
                if hasattr(post, 'videos') and post.videos:
                    media_urls.extend(post.videos)
                
                if media_urls:
                    download_plan[post.url] = media_urls
                    media_count += len(media_urls)
            
            if not download_plan:
                logging.info(f"ℹ️ [Task: {task_id}] 本批貼文沒有可下載的媒體")
                return
                
            logging.info(f"📋 [Task: {task_id}] 準備下載 {media_count} 個媒體檔案 (來自 {len(download_plan)} 個貼文)")
            
            # 執行下載
            download_service = MediaDownloadService()
            result = await download_service.run_download(download_plan, concurrency_per_post=2)
            
            # 記錄結果
            success_rate = (result['success'] / result['total'] * 100) if result['total'] > 0 else 0
            logging.info(f"✅ [Task: {task_id}] 即時下載完成：成功 {result['success']}/{result['total']} ({success_rate:.1f}%)")
            
            if result['failed'] > 0:
                logging.warning(f"⚠️ [Task: {task_id}] 失敗 {result['failed']} 個媒體，稍後可透過UI重試")
                
                # 記錄失敗的詳情（僅前5個）
                failed_details = [d for d in result.get('details', []) if d.get('status') == 'failed']
                for detail in failed_details[:5]:
                    logging.warning(f"   ❌ {detail.get('original_url', 'N/A')}: {detail.get('error', 'Unknown error')}")
                    
        except Exception as e:
            logging.error(f"❌ [Task: {task_id}] 即時下載失敗: {e}")
            # 下載失敗不影響爬蟲主流程，只記錄錯誤
            
    async def _smart_scroll_new_mode(
        self, 
        page, 
        username: str, 
        target_count: int,
        existing_post_ids: set,
        anchor_post_id: str,
        max_scroll_rounds: int
    ) -> List[str]:
        """
        NEW模式智能滾動：補足新貼文
        從最新開始，直到遇到錨點或達到目標數量
        """
        collected_urls = []
        found_anchor = False
        scroll_round = 0
        
        logging.info(f"🔄 NEW模式開始：目標 {target_count} 篇，錨點 {anchor_post_id}")
        
        while scroll_round < max_scroll_rounds:
            # 收集當前頁面的新URLs
            new_urls = await collect_urls_from_dom(page, existing_post_ids, username)
            
            # 過濾重複並添加
            for url in new_urls:
                if url not in collected_urls:
                    collected_urls.append(url)
                    
            logging.debug(f"🔄 NEW模式第 {scroll_round+1} 輪：累計 {len(collected_urls)}/{target_count}")
            
            # 檢查錨點（每3輪檢查一次以提高效率）
            if not found_anchor and scroll_round % 3 == 0:
                current_post_ids = await extract_current_post_ids(page)
                found_anchor, anchor_idx = is_anchor_visible(current_post_ids, anchor_post_id)
                
                if found_anchor and anchor_idx >= len(current_post_ids) * 0.5:
                    logging.info(f"🎯 NEW模式找到錨點在後半部，停止滾動")
                    break
                    
            # 檢查停止條件
            if should_stop_new_mode(found_anchor, collected_urls, target_count):
                break
                
            # 檢查頁面底部
            if await check_page_bottom(page):
                logging.info(f"📄 NEW模式到達頁面底部")
                break
                
            # 滾動到下一段
            await scroll_once(page)
            scroll_round += 1
            
        logging.info(f"✅ NEW模式完成：{len(collected_urls)}/{target_count}，滾動 {scroll_round} 輪")
        return collected_urls[:target_count]  # 限制數量
        
    async def _smart_scroll_hist_mode(
        self,
        page,
        username: str,
        target_count: int, 
        existing_post_ids: set,
        anchor_post_id: str,
        max_scroll_rounds: int
    ) -> List[str]:
        """
        HIST模式智能滾動：歷史回溯
        滾動到錨點位置，然後繼續往下收集更舊的貼文
        """
        collected_urls = []
        found_anchor = False
        passed_anchor = False
        scroll_round = 0
        
        logging.info(f"🔄 HIST模式開始：目標 {target_count} 篇，錨點 {anchor_post_id}")
        
        if not anchor_post_id:
            logging.warning("⚠️ HIST模式需要錨點，但未提供，退回到普通模式")
            return await collect_urls_from_dom(page, existing_post_ids, username)
            
        while scroll_round < max_scroll_rounds:
            # 滾動一次
            await scroll_once(page)
            scroll_round += 1
            
            # 檢查是否找到錨點（每2輪檢查一次）
            if not found_anchor and scroll_round % 2 == 0:
                current_post_ids = await extract_current_post_ids(page)
                found_anchor, anchor_idx = is_anchor_visible(current_post_ids, anchor_post_id)
                
                if found_anchor:
                    logging.info(f"🎯 HIST模式找到錨點在位置 {anchor_idx}")
                    if anchor_idx >= len(current_post_ids) * 0.6:
                        passed_anchor = True
                        logging.info(f"🚀 HIST模式越過錨點，開始收集歷史貼文")
                        
            # 只有越過錨點後才開始收集
            if passed_anchor:
                new_urls = await collect_urls_from_dom(page, existing_post_ids, username)
                
                # 過濾重複並添加
                for url in new_urls:
                    if url not in collected_urls:
                        collected_urls.append(url)
                        
                logging.debug(f"🔄 HIST模式第 {scroll_round} 輪：歷史貼文 {len(collected_urls)}/{target_count}")
                
            # 檢查停止條件
            if should_stop_hist_mode(found_anchor, passed_anchor, collected_urls, target_count, scroll_round, max_scroll_rounds):
                break
                
            # 檢查頁面底部
            if await check_page_bottom(page):
                logging.info(f"📄 HIST模式到達頁面底部")
                break
                
        if not found_anchor:
            logging.warning(f"⚠️ HIST模式未找到錨點 {anchor_post_id}，可能錨點太舊")
            
        logging.info(f"✅ HIST模式完成：{len(collected_urls)}/{target_count}，滾動 {scroll_round} 輪")
        return collected_urls[:target_count]  # 限制數量
    
    async def _collect_urls_realtime_style(
        self, 
        page, 
        username: str, 
        target_count: int, 
        existing_post_ids: set, 
        incremental: bool,
        max_scroll_rounds: int = 80
    ) -> List[str]:
        """
        採用Realtime Crawler風格的URL收集
        足額收集URLs，支持增量檢測
        """
        urls = []
        scroll_rounds = 0
        no_new_content_rounds = 0
        max_no_new_rounds = 15
        consecutive_existing_rounds = 0
        max_consecutive_existing = 15
        
        logging.info(f"🔄 開始Realtime風格URL收集（目標: {target_count} 篇，增量: {incremental}）")
        
        while len(urls) < target_count and scroll_rounds < max_scroll_rounds:
            # 提取當前頁面的URLs（採用Realtime的JavaScript邏輯）
            js_code = """
                function(targetUsername) {
                    const links = Array.from(document.querySelectorAll('a[href*="/post/"]'));
                    return [...new Set(links.map(link => link.href)
                        .filter(url => url.includes('/post/'))
                        .filter(url => {
                            // 檢查URL是否屬於目標用戶
                            const usernamePart = url.split('/@')[1];
                            if (!usernamePart) return false;
                            const extractedUsername = usernamePart.split('/')[0];
                            
                            const postId = url.split('/post/')[1];
                            // 過濾掉 media、無效ID等，並確保是目標用戶的貼文
                            return postId && 
                                   postId !== 'media' && 
                                   postId.length > 5 && 
                                   /^[A-Za-z0-9_-]+$/.test(postId) &&
                                   extractedUsername === targetUsername;
                        }))];
                }
            """
            current_urls = await page.evaluate(js_code, username)
            
            before_count = len(urls)
            new_urls_this_round = 0
            found_existing_this_round = False
            existing_skipped_this_round = 0
            
            # 去重並添加新URLs（支持增量檢測）
            for url in current_urls:
                # 從 URL 提取完整的 post_id (格式: username_postid)
                raw_post_id = url.split('/')[-1] if url else None
                post_id = f"{username}_{raw_post_id}" if raw_post_id else None
                
                # 跳過已收集的URL
                if url in urls:
                    continue
                    
                # 增量模式：檢查是否已存在於資料庫
                if incremental and post_id in existing_post_ids:
                    logging.info(f"   🔍 [{len(urls)+1}] 發現已爬取貼文: {post_id} - 跳過 (增量模式)")
                    found_existing_this_round = True
                    existing_skipped_this_round += 1
                    continue
                elif incremental:
                    logging.info(f"   🆕 [{len(urls)+1}] 發現新貼文: {post_id} (增量模式)")
                
                # 檢查是否已達到目標數量
                if len(urls) >= target_count:
                    break
                    
                urls.append(url)
                new_urls_this_round += 1
                
                status_icon = "🆕" if incremental else "📍"
                logging.debug(f"   {status_icon} [{len(urls)}] 發現: {post_id}")
            
            # 增量模式：使用修復後的智能停止條件
            if incremental:
                # 使用修復後的智能停止判斷（只檢查是否收集足夠）
                if should_stop_incremental_mode(
                    found_existing_this_round, consecutive_existing_rounds, 
                    len(urls), target_count, max_consecutive_existing
                ):
                    break
            
            # 檢查是否有新內容
            new_urls_found = len(urls) - before_count
            
            # 關鍵修復：重新設計停止邏輯
            if new_urls_found > 0:
                # 發現新URL，重置無新內容計數器
                no_new_content_rounds = 0
                logging.debug(f"   ✅ 第{scroll_rounds+1}輪發現 {new_urls_found} 個新URL，重置無新內容計數器")
            elif not found_existing_this_round:
                # 既沒有新URL也沒有已存在貼文，真正的無內容輪次
                no_new_content_rounds += 1
                logging.debug(f"   ⏳ 第{scroll_rounds+1}輪完全沒有發現內容 ({no_new_content_rounds}/{max_no_new_rounds})")
                
                if no_new_content_rounds >= max_no_new_rounds:
                    # 執行最後嘗試機制 - 使用新的策略
                    attempt_result = await final_attempt_scroll(page)
                    
                    if attempt_result > 0:
                        # 檢查最後嘗試是否有新內容
                        final_urls = await page.evaluate(js_code, username)
                        final_new_count = 0
                        
                        for url in final_urls:
                            raw_post_id = url.split('/')[-1] if url else None
                            post_id = f"{username}_{raw_post_id}" if raw_post_id else None
                            
                            # 檢查是否是新的URL
                            if url not in urls:
                                # 增量模式檢查
                                if incremental and post_id in existing_post_ids:
                                    continue
                                # 將新URL添加到收集列表
                                if len(urls) < target_count:
                                    urls.append(url)
                                    final_new_count += 1
                                    logging.info(f"   📍 [{len(urls)}] 最後發現: {raw_post_id}")
                        
                        if final_new_count == 0:
                            logging.info("   🛑 最後嘗試無新內容，確認到達底部")
                            break
                        else:
                            logging.info(f"   🎯 最後嘗試發現{final_new_count}個新URL，繼續收集...")
                            no_new_content_rounds = 0  # 重置計數器
                            continue
                    else:
                        logging.info("   🛑 最後嘗試執行失敗，停止收集")
                        break
                        
                    # 使用新的遞增等待策略
                    await progressive_wait(no_new_content_rounds)
            else:
                # 有已存在貼文但沒有新URL，不增加無新內容計數器（繼續尋找更舊的內容）
                logging.debug(f"   🔍 第{scroll_rounds+1}輪發現已存在貼文但無新URL，繼續尋找更舊內容...")
            
            # 使用增強的滾動策略
            await enhanced_scroll_with_strategy(page, scroll_rounds)
            scroll_rounds += 1
            
            # 定期顯示進度
            if scroll_rounds % 5 == 0:
                logging.info(f"   📊 滾動進度: 第{scroll_rounds}輪，已收集{len(urls)}個URL")
        
        logging.info(f"✅ URL收集完成：{len(urls)} 個URL，滾動 {scroll_rounds} 輪")
        return urls
    
    async def _convert_urls_to_posts(self, urls: List[str], username: str, mode: str, task_id: str) -> List[PostMetrics]:
        """轉換URLs為PostMetrics並過濾非目標用戶"""
        valid_posts = []
        
        for url in urls:
            # 驗證URL是否確實屬於目標用戶
            if f"@{username}/post/" not in url:
                logging.debug(f"⚠️ 跳過非目標用戶的URL: {url}")
                continue
                
            post_id = url.split('/')[-1]
            post_metrics = PostMetrics(
                post_id=f"{username}_{post_id}",
                username=username,
                url=url,
                content="",
                created_at=get_taipei_time(),
                fetched_at=get_taipei_time(),
                source=f"playwright_{mode}",
                processing_stage="urls_extracted",
                is_complete=False,
                likes_count=0,
                comments_count=0,
                reposts_count=0,
                shares_count=0,
                views_count=None,
            )
            valid_posts.append(post_metrics)
            
        logging.info(f"✅ [Task: {task_id}] URL轉換：{len(urls)} 個URL → {len(valid_posts)} 個有效PostMetrics")
        return valid_posts