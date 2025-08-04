"""
瀏覽數提取器

負責從貼文頁面提取瀏覽數，支持多種策略：
1. GraphQL API 攔截
2. DOM 選擇器解析
"""

import asyncio
import logging
import random
from datetime import datetime
from typing import List, Optional
from playwright.async_api import BrowserContext

from common.models import PostMetrics
from common.nats_client import publish_progress
from ..parsers.number_parser import parse_number


class ViewsExtractor:
    """
    瀏覽數提取器
    """
    
    def __init__(self):
        pass
    
    async def fill_views_from_page(self, posts_to_fill: List[PostMetrics], context: BrowserContext, task_id: str = None, username: str = None) -> List[PostMetrics]:
        """
        遍歷貼文列表，導航到每個貼文的頁面以補齊 views_count。
        整合了成功的 Gate 頁面處理和雙策略提取方法。
        """
        if not context:
            logging.error("❌ Browser context 未初始化，無法執行 fill_views_from_page。")
            return posts_to_fill

        # 減少並發數以避免觸發反爬蟲機制
        semaphore = asyncio.Semaphore(2)
        
        async def fetch_single_view(post: PostMetrics):
            async with semaphore:
                page = None
                try:
                    page = await context.new_page()
                    # 禁用圖片和影片載入以加速
                    await page.route("**/*.{png,jpg,jpeg,gif,mp4,webp}", lambda r: r.abort())
                    
                    logging.debug(f"📄 正在處理: {post.url}")
                    
                    # 導航到貼文頁面（優化版：更快的載入策略）
                    await page.goto(post.url, wait_until="domcontentloaded", timeout=25000)
                    
                    # 檢查頁面類型（完整頁面 vs Gate 頁面）
                    page_content = await page.content()
                    is_gate_page = "__NEXT_DATA__" not in page_content
                    
                    if is_gate_page:
                        logging.debug(f"   ⚠️ 檢測到 Gate 頁面，直接使用 DOM 選擇器...")
                    
                    views_count = None
                    extraction_method = None
                    
                    # 策略 1: GraphQL 攔截（只在非 Gate 頁面時）
                    if not is_gate_page:
                        views_count, extraction_method = await self._extract_views_from_graphql(page)
                    
                    # 策略 2: DOM 選擇器（Gate 頁面的主要方法）
                    if views_count is None or views_count == 0:
                        views_count, extraction_method = await self._extract_views_from_dom(page)
                    
                    # 更新結果 - 只在現有瀏覽數為 None 或 <= 0 時才更新
                    if views_count and views_count > 0:
                        if post.views_count is None or post.views_count <= 0:
                            post.views_count = views_count
                            post.views_fetched_at = datetime.utcnow()
                            logging.info(f"  ✅ 成功獲取 {post.post_id} 的瀏覽數: {views_count:,} (方法: {extraction_method})")
                            
                            # 發布進度
                            if task_id:
                                await publish_progress(
                                    task_id, 
                                    "views_fetched",
                                    username=username or "unknown",
                                    post_id=post.post_id,
                                    views_count=views_count,
                                    extraction_method=extraction_method,
                                    is_gate_page=is_gate_page
                                )
                        else:
                            logging.info(f"  ℹ️ {post.post_id} 已有瀏覽數 {post.views_count:,}，跳過更新")
                    else:
                        if post.views_count is None:
                            logging.warning(f"  ❌ 無法獲取 {post.post_id} 的瀏覽數")
                            post.views_count = -1
                            post.views_fetched_at = datetime.utcnow()
                    
                    # 保守的隨機延遲避免反爬蟲（稍微縮短但保持安全）
                    delay = random.uniform(1.5, 3.5)  # 縮短0.5秒但保持隨機性
                    await asyncio.sleep(delay)
                    
                except Exception as e:
                    logging.error(f"  ❌ 處理 {post.post_id} 時發生錯誤: {e}")
                    post.views_count = -1
                    post.views_fetched_at = datetime.utcnow()
                finally:
                    if page:
                        await page.close()

        # 序列處理避免並發問題（根據成功經驗）
        for post in posts_to_fill:
            await fetch_single_view(post)
        
        return posts_to_fill
    
    async def _extract_views_from_graphql(self, page) -> tuple[Optional[int], Optional[str]]:
        """
        從 GraphQL API 提取瀏覽數
        """
        try:
            response = await page.wait_for_response(
                lambda r: "containing_thread" in r.url and r.status == 200, 
                timeout=8000
            )
            data = await response.json()
            
            # 解析瀏覽數
            thread_items = data["data"]["containing_thread"]["thread_items"]
            post_data = thread_items[0]["post"]
            views_count = (post_data.get("feedback_info", {}).get("view_count") or
                          post_data.get("video_info", {}).get("play_count") or 0)
            
            if views_count > 0:
                logging.debug(f"   ✅ GraphQL API 獲取瀏覽數: {views_count:,}")
                return views_count, "graphql_api"
        except Exception as e:
            logging.debug(f"   ⚠️ GraphQL 攔截失敗: {str(e)[:100]}")
        
        return None, None
    
    async def _extract_views_from_dom(self, page) -> tuple[Optional[int], Optional[str]]:
        """
        從 DOM 元素提取瀏覽數
        """
        selectors = [
            "a:has-text(' 次瀏覽'), a:has-text(' views')",    # 主要選擇器
            "*:has-text('次瀏覽'), *:has-text('views')",      # 通用選擇器
            "span:has-text('次瀏覽'), span:has-text('views')", # span 元素
            "text=/\\d+[\\.\\d]*[^\\d]?次瀏覽/, text=/\\d+.*views?/",  # 處理「4 萬次瀏覽」空格問題
        ]
        
        for i, selector in enumerate(selectors):
            try:
                element = await page.wait_for_selector(selector, timeout=3000)
                if element:
                    view_text = await element.inner_text()
                    parsed_views = parse_number(view_text)
                    if parsed_views and parsed_views > 0:
                        logging.debug(f"   ✅ DOM 選擇器 {i+1} 獲取瀏覽數: {parsed_views:,}")
                        return parsed_views, f"dom_selector_{i+1}"
            except Exception:
                continue
        
        return None, None