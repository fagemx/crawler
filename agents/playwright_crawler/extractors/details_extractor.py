"""
詳細數據提取器

負責使用混合策略補齊貼文詳細數據：
1. GraphQL 計數查詢獲取準確的數字數據 (likes, comments等)
2. DOM 解析獲取完整的內容和媒體 (content, images, videos)
"""

import asyncio
import logging
import random
import re
from datetime import datetime
from typing import Dict, List, Optional, Any, Set
from playwright.async_api import BrowserContext, Page

from common.models import PostMetrics
from common.nats_client import publish_progress
from ..parsers.number_parser import parse_number


class DetailsExtractor:
    """
    詳細數據提取器 - 使用混合策略提取完整的貼文數據
    """
    
    def __init__(self):
        pass
    
    async def fill_post_details_from_page(self, posts_to_fill: List[PostMetrics], context: BrowserContext, task_id: str = None, username: str = None) -> List[PostMetrics]:
        """
        使用混合策略補齊貼文詳細數據：
        1. GraphQL 計數查詢獲取準確的數字數據 (likes, comments等)
        2. DOM 解析獲取完整的內容和媒體 (content, images, videos)
        這種方法結合了兩種技術的優勢，提供最穩定可靠的數據提取。
        """
        if not context:
            logging.error("❌ Browser context 未初始化，無法執行 fill_post_details_from_page。")
            return posts_to_fill

        # 保守的並發數提升：從1增加到2，平衡速度與安全性
        semaphore = asyncio.Semaphore(2)  # 輕微提升並發但保持安全
        
        async def fetch_single_details_hybrid(post: PostMetrics):
            async with semaphore:
                page = None
                try:
                    page = await context.new_page()
                    
                    logging.debug(f"📄 使用混合策略補齊詳細數據: {post.url}")
                    
                    # === 步驟 1: 混合策略 - 攔截+重發請求 ===
                    counts_data = {}
                    video_urls = set()
                    captured_graphql_request = {}
                    response_handler_active = True
                    
                    async def handle_counts_response(response):
                        if not response_handler_active:
                            return  # 停止處理響應
                        await self._handle_graphql_response(response, counts_data, video_urls, captured_graphql_request)
                    
                    page.on("response", handle_counts_response)
                    
                    # === 步驟 2: 導航和觸發載入（優化版：更快但安全的載入策略） ===
                    await page.goto(post.url, wait_until="domcontentloaded", timeout=45000)
                    
                    # 智能等待：先短暫等待，如果沒有攔截到數據再延長
                    await asyncio.sleep(1.5)  # 縮短初始等待時間
                    
                    # 檢查是否已經攔截到數據
                    if not counts_data:
                        logging.debug(f"   ⏳ 首次等待未攔截到數據，延長等待...")
                        await asyncio.sleep(1.5)  # 額外等待1.5秒（總共3秒）
                    
                    # === 步驟 2.5: 混合策略重發請求 ===
                    if captured_graphql_request and not counts_data:
                        counts_data = await self._resend_graphql_request(captured_graphql_request, post.url, context)
                    
                    # 成功獲取數據後停止監聽，避免不必要的攔截
                    if counts_data and counts_data.get("likes", 0) > 0:
                        response_handler_active = False
                        logging.debug(f"   🛑 成功獲取計數數據，停止響應監聽")
                    
                    # 嘗試觸發影片載入
                    await self._trigger_video_loading(page)
                    
                    # === 步驟 3: DOM 內容提取 ===
                    content_data = await self._extract_content_from_dom(page, username, video_urls)
                    
                    # === 步驟 3.5: DOM 計數後援（當 GraphQL 攔截失敗時） ===
                    if not counts_data:
                        counts_data = await self._extract_counts_from_dom_fallback(page)
                    
                    # === 步驟 4: 更新貼文數據 ===
                    updated = await self._update_post_data(post, counts_data, content_data, task_id, username)
                    
                    # 隨機延遲避免反爬蟲
                    delay = random.uniform(2, 4)
                    await asyncio.sleep(delay)
                    
                except Exception as e:
                    logging.error(f"  ❌ 混合策略處理 {post.post_id} 時發生錯誤: {e}")
                    post.processing_stage = "details_failed"
                finally:
                    if page:
                        await page.close()

        # 序列處理保持順序
        for post in posts_to_fill:
            await fetch_single_details_hybrid(post)
        
        return posts_to_fill
    
    async def _handle_graphql_response(self, response, counts_data: dict, video_urls: set, captured_graphql_request: dict):
        """處理 GraphQL 響應的攔截（優化版：支持去重）"""
        try:
            import json
            url = response.url.lower()
            headers = response.request.headers
            query_name = headers.get("x-fb-friendly-name", "")
            
            # 檢查是否已經有完整數據，避免重複攔截
            if (counts_data.get("likes", 0) > 0 and 
                counts_data.get("comments", 0) >= 0 and 
                counts_data.get("reposts", 0) >= 0 and 
                counts_data.get("shares", 0) >= 0):
                logging.debug(f"   ⏩ 已有完整計數數據，跳過重複攔截")
                return
            
            # 攔截計數查詢請求（保存headers和payload）
            if ("/graphql" in url and response.status == 200 and 
                "useBarcelonaBatchedDynamicPostCountsSubscriptionQuery" in query_name):
                
                # 只在第一次攔截時記錄詳細日誌
                if not captured_graphql_request.get("headers"):
                    logging.info(f"   🎯 攔截到GraphQL計數查詢，保存請求信息...")
                    
                    # 保存請求信息（模仿hybrid_content_extractor.py的成功策略）
                    captured_graphql_request.update({
                        "headers": dict(response.request.headers),
                        "payload": response.request.post_data,
                        "url": "https://www.threads.com/graphql/query"
                    })
                    
                    # 清理headers
                    clean_headers = captured_graphql_request["headers"].copy()
                    for h in ["host", "content-length", "accept-encoding"]:
                        clean_headers.pop(h, None)
                    captured_graphql_request["clean_headers"] = clean_headers
                    
                    logging.info(f"   ✅ 成功保存GraphQL請求信息，準備重發...")
                else:
                    logging.debug(f"   🔄 重複GraphQL攔截，使用已保存的請求信息")
                
                # 也嘗試直接解析當前響應（作為備用）
                try:
                    data = await response.json()
                    if "data" in data and "data" in data["data"] and "posts" in data["data"]["data"]:
                        posts_list = data["data"]["data"]["posts"]
                        if posts_list and len(posts_list) > 0:
                            post_data = posts_list[0]
                            if isinstance(post_data, dict):
                                text_info = post_data.get("text_post_app_info", {}) or {}
                                new_counts = {
                                    "likes": post_data.get("like_count") or 0,
                                    "comments": text_info.get("direct_reply_count") or 0, 
                                    "reposts": text_info.get("repost_count") or 0,
                                    "shares": text_info.get("reshare_count") or 0
                                }
                                
                                # 只在沒有數據或數據更新時才更新
                                if not counts_data or any(new_counts.get(k, 0) > counts_data.get(k, 0) for k in new_counts):
                                    counts_data.update(new_counts)
                                    logging.info(f"   ✅ 直接攔截成功: 讚={counts_data['likes']}, 留言={counts_data['comments']}, 轉發={counts_data['reposts']}, 分享={counts_data['shares']}")
                                else:
                                    logging.debug(f"   ⏩ 數據無更新，跳過重複記錄")
                except Exception as e:
                    logging.debug(f"   ⚠️ 直接解析失敗: {e}")
            
            # 攔截影片資源
            content_type = response.headers.get("content-type", "")
            resource_type = response.request.resource_type
            if (resource_type == "media" or 
                content_type.startswith("video/") or
                ".mp4" in response.url.lower() or
                ".m3u8" in response.url.lower() or
                ".mpd" in response.url.lower()):
                video_urls.add(response.url)
                logging.debug(f"   🎥 攔截到影片: {response.url[:60]}...")
                
        except Exception as e:
            logging.debug(f"   ⚠️ 響應處理失敗: {e}")
    
    async def _resend_graphql_request(self, captured_graphql_request: dict, post_url: str, context: BrowserContext) -> dict:
        """重發 GraphQL 請求"""
        logging.info(f"   🔄 使用保存的GraphQL請求信息重發請求...")
        counts_data = {}
        
        try:
            import httpx
            
            # 從URL提取PK（如果可能）
            url_match = re.search(r'/post/([^/?]+)', post_url)
            if url_match:
                logging.info(f"   🔍 URL代碼: {url_match.group(1)}")
            
            # 準備重發請求
            headers = captured_graphql_request["clean_headers"]
            payload = captured_graphql_request["payload"]
            
            # 從頁面context獲取cookies
            cookies_list = await context.cookies()
            cookies = {cookie['name']: cookie['value'] for cookie in cookies_list}
            
            # 確保有認證
            if not headers.get("authorization") and 'ig_set_authorization' in cookies:
                auth_value = cookies['ig_set_authorization']
                headers["authorization"] = f"Bearer {auth_value}" if not auth_value.startswith('Bearer') else auth_value
            
            # 發送HTTP請求到Threads API
            async with httpx.AsyncClient(headers=headers, cookies=cookies, timeout=30.0, http2=True) as client:
                api_response = await client.post("https://www.threads.com/graphql/query", data=payload)
                
                if api_response.status_code == 200:
                    result = api_response.json()
                    logging.info(f"   ✅ 重發請求成功，狀態: {api_response.status_code}")
                    
                    if "data" in result and result["data"] and "data" in result["data"] and "posts" in result["data"]["data"]:
                        posts_list = result["data"]["data"]["posts"]
                        logging.info(f"   📊 重發請求響應包含 {len(posts_list)} 個貼文")
                        
                        # 使用第一個貼文（當前頁面的主要貼文）
                        if posts_list and len(posts_list) > 0:
                            post_data = posts_list[0]
                            if isinstance(post_data, dict):
                                text_info = post_data.get("text_post_app_info", {}) or {}
                                counts_data.update({
                                    "likes": post_data.get("like_count") or 0,
                                    "comments": text_info.get("direct_reply_count") or 0, 
                                    "reposts": text_info.get("repost_count") or 0,
                                    "shares": text_info.get("reshare_count") or 0
                                })
                                logging.info(f"   🎯 重發請求成功獲取數據: 讚={counts_data['likes']}, 留言={counts_data['comments']}, 轉發={counts_data['reposts']}, 分享={counts_data['shares']}")
                else:
                    logging.warning(f"   ⚠️ 重發請求失敗，狀態: {api_response.status_code}")
                    
        except Exception as e:
            logging.warning(f"   ⚠️ 重發請求過程失敗: {e}")
        
        return counts_data
    
    async def _trigger_video_loading(self, page: Page):
        """觸發影片載入"""
        try:
            trigger_selectors = [
                'div[data-testid="media-viewer"]',
                'video',
                'div[role="button"][aria-label*="play"]',
                'div[role="button"][aria-label*="播放"]',
                '[data-pressable-container] div[style*="video"]'
            ]
            
            for selector in trigger_selectors:
                try:
                    elements = page.locator(selector)
                    count = await elements.count()
                    if count > 0:
                        await elements.first.click(timeout=3000)
                        await asyncio.sleep(2)
                        break
                except:
                    continue
        except:
            pass
    
    async def _extract_content_from_dom(self, page: Page, username: str, video_urls: set) -> dict:
        """從 DOM 提取內容數據"""
        content_data = {}
        
        try:
            # 提取用戶名（從 URL）
            url_match = re.search(r'/@([^/]+)/', page.url)
            content_data["username"] = url_match.group(1) if url_match else username or ""
            
            # 提取內容文字
            content = ""
            content_selectors = [
                'div[data-pressable-container] span',
                '[data-testid="thread-text"]',
                'article div[dir="auto"]',
                'div[role="article"] div[dir="auto"]'
            ]
            
            for selector in content_selectors:
                try:
                    elements = page.locator(selector)
                    count = await elements.count()
                    
                    for i in range(min(count, 20)):
                        try:
                            text = await elements.nth(i).inner_text()
                            
                            # 基本過濾條件
                            if not text or len(text.strip()) <= 10:
                                continue
                            if text.strip().isdigit():
                                continue
                            if text.startswith("@"):
                                continue
                            
                            # 過濾用戶名（重要修復！）
                            if text.strip() == username:
                                logging.debug(f"   ⚠️ 過濾用戶名文本: {text}")
                                continue
                            
                            # 過濾時間相關
                            if any(time_word in text for time_word in ["小時", "分鐘", "秒前", "天前", "週前", "個月前"]):
                                continue
                            
                            # 過濾系統錯誤和提示信息（重點修復！）
                            system_messages = [
                                "Sorry, we're having trouble playing this video",
                                "Learn more",
                                "Something went wrong",
                                "Video unavailable",
                                "This content isn't available",
                                "Unable to load",
                                "Error loading",
                                "播放發生錯誤",
                                "無法播放",
                                "載入失敗",
                                "發生錯誤",
                                "內容無法顯示"
                            ]
                            
                            # 檢查是否包含系統錯誤信息
                            text_lower = text.lower()
                            if any(msg.lower() in text_lower for msg in system_messages):
                                logging.debug(f"   ⚠️ 過濾系統錯誤信息: {text[:50]}...")
                                continue
                            
                            # 過濾按鈕文字和導航
                            button_texts = ["follow", "following", "like", "comment", "share", "more", "options"]
                            if any(btn in text_lower for btn in button_texts):
                                continue
                            
                            # 過濾純數字組合（讚數、分享數等）
                            if re.match(r'^[\d,.\s]+$', text.strip()):
                                continue
                                
                            # 過濾過短的內容
                            if len(text.strip()) < 5:
                                continue
                            
                            # 通過所有過濾條件，接受此內容
                            content = text.strip()
                            logging.debug(f"   ✅ 找到有效內容: {content[:50]}...")
                            break
                        except:
                            continue
                    
                    if content:
                        break
                except:
                    continue
            
            # 如果沒有找到有效內容，嘗試其他策略
            if not content:
                logging.debug(f"   🔍 主要內容提取失敗，嘗試備用策略...")
                
                # 備用策略1：查找 aria-label 或 title 屬性
                backup_selectors = [
                    'div[aria-label]',
                    'span[title]',
                    '[data-testid="thread-description"]',
                    'article[aria-label]'
                ]
                
                for backup_selector in backup_selectors:
                    try:
                        elements = page.locator(backup_selector)
                        backup_count = await elements.count()
                        
                        for i in range(min(backup_count, 10)):
                            try:
                                backup_text = await elements.nth(i).get_attribute("aria-label") or await elements.nth(i).get_attribute("title")
                                if backup_text and len(backup_text.strip()) > 5:
                                    # 過濾用戶名
                                    if backup_text.strip() == username:
                                        continue
                                    
                                    # 同樣過濾系統錯誤信息
                                    backup_text_lower = backup_text.lower()
                                    if not any(msg.lower() in backup_text_lower for msg in [
                                        "sorry, we're having trouble playing this video",
                                        "learn more", "something went wrong", "video unavailable"
                                    ]):
                                        content = backup_text.strip()
                                        logging.debug(f"   ✅ 備用策略找到內容: {content[:50]}...")
                                        break
                            except:
                                continue
                        
                        if content:
                            break
                    except:
                        continue
                
                # 如果仍然沒有內容，標記為影片貼文
                if not content:
                    logging.debug(f"   📹 可能是純影片貼文，無文字內容")
                    content = ""  # 保持空字符串而不是錯誤信息
            
            content_data["content"] = content
            
            # 調試信息：確認內容提取結果
            logging.info(f"   📝 [DEBUG] 內容提取結果: content='{content}', username='{content_data.get('username', 'N/A')}'")
            if content == content_data.get("username"):
                logging.warning(f"   ⚠️ [DEBUG] 警告：content 與 username 相同！可能存在錯誤賦值")
            
            # 提取圖片（過濾頭像）
            images = []
            img_elements = page.locator('img')
            img_count = await img_elements.count()
            
            for i in range(min(img_count, 50)):
                try:
                    img_elem = img_elements.nth(i)
                    img_src = await img_elem.get_attribute("src")
                    
                    if not img_src or not ("fbcdn" in img_src or "cdninstagram" in img_src):
                        continue
                    
                    if ("rsrc.php" in img_src or "static.cdninstagram.com" in img_src):
                        continue
                    
                    # 檢查尺寸過濾頭像
                    try:
                        width = int(await img_elem.get_attribute("width") or 0)
                        height = int(await img_elem.get_attribute("height") or 0)
                        max_size = max(width, height)
                        
                        if max_size > 150 and img_src not in images:
                            images.append(img_src)
                    except:
                        if ("t51.2885-15" in img_src or "scontent" in img_src) and img_src not in images:
                            images.append(img_src)
                except:
                    continue
            
            content_data["images"] = images
            
            # 提取影片（結合網路攔截和DOM）
            videos = list(video_urls)
            
            # DOM 中的 video 標籤
            video_elements = page.locator('video')
            video_count = await video_elements.count()
            
            for i in range(video_count):
                try:
                    video_elem = video_elements.nth(i)
                    src = await video_elem.get_attribute("src")
                    data_src = await video_elem.get_attribute("data-src")
                    poster = await video_elem.get_attribute("poster")
                    
                    if src and src not in videos:
                        videos.append(src)
                    if data_src and data_src not in videos:
                        videos.append(data_src)
                    if poster and poster not in videos:
                        videos.append(f"POSTER::{poster}")
                    
                    # source 子元素
                    sources = video_elem.locator('source')
                    source_count = await sources.count()
                    for j in range(source_count):
                        source_src = await sources.nth(j).get_attribute("src")
                        if source_src and source_src not in videos:
                            videos.append(source_src)
                except:
                    continue
            
            content_data["videos"] = videos
            
            # ← 新增: 提取真實發文時間
            try:
                post_published_at = await self._extract_post_published_at(page)
                if post_published_at:
                    content_data["post_published_at"] = post_published_at
                    logging.debug(f"   ✅ 提取發文時間: {post_published_at}")
            except Exception as e:
                logging.debug(f"   ⚠️ 發文時間提取失敗: {e}")
            
            # ← 新增: 提取主題標籤
            try:
                tags = await self._extract_tags_from_dom(page)
                if tags:
                    content_data["tags"] = tags
                    logging.debug(f"   ✅ 提取標籤: {tags}")
            except Exception as e:
                logging.debug(f"   ⚠️ 標籤提取失敗: {e}")
            
        except Exception as e:
            logging.debug(f"   ⚠️ DOM 內容提取失敗: {e}")
        
        return content_data
    
    async def _extract_counts_from_dom_fallback(self, page: Page) -> dict:
        """DOM 計數後援提取"""
        logging.warning(f"   🔄 GraphQL 計數攔截失敗，開始 DOM 計數後援...")
        
        # 先檢查頁面狀態
        page_title = await page.title()
        page_url = page.url
        logging.info(f"   📄 頁面狀態 - 標題: {page_title}, URL: {page_url}")
        
        count_selectors = {
            "likes": [
                # English selectors
                "button[aria-label*='likes'] span",
                "button[aria-label*='Like'] span", 
                "span:has-text(' likes')",
                "span:has-text(' like')",
                "button svg[aria-label='Like'] + span",
                "button[aria-label*='like']",
                # Chinese selectors
                "button[aria-label*='個喜歡'] span",
                "button[aria-label*='喜歡']",
                # Generic patterns
                "button[data-testid*='like'] span",
                "div[role='button'][aria-label*='like'] span"
            ],
            "comments": [
                # English selectors
                "a[href$='#comments'] span",
                "span:has-text(' comments')",
                "span:has-text(' comment')",
                "a:has-text('comments')",
                "button[aria-label*='comment'] span",
                # Chinese selectors
                "span:has-text(' 則留言')",
                "a:has-text('則留言')",
                # Generic patterns
                "button[data-testid*='comment'] span",
                "div[role='button'][aria-label*='comment'] span"
            ],
            "reposts": [
                # English selectors
                "span:has-text(' reposts')",
                "span:has-text(' repost')",
                "button[aria-label*='repost'] span",
                "a:has-text('reposts')",
                # Chinese selectors
                "span:has-text(' 次轉發')",
                "a:has-text('轉發')",
                # Generic patterns
                "button[data-testid*='repost'] span"
            ],
            "shares": [
                # English selectors
                "span:has-text(' shares')",
                "span:has-text(' share')",
                "button[aria-label*='share'] span",
                "a:has-text('shares')",
                # Chinese selectors
                "span:has-text(' 次分享')",
                "a:has-text('分享')",
                # Generic patterns
                "button[data-testid*='share'] span"
            ],
        }
        
        # 先進行通用元素掃描，並智能提取數字
        logging.info(f"   🔍 通用元素掃描和智能數字提取...")
        dom_counts = {}
        
        try:
            all_buttons = await page.locator('button').all_inner_texts()
            all_spans = await page.locator('span').all_inner_texts()
            number_elements = [text for text in (all_buttons + all_spans) if any(char.isdigit() for char in text)]
            logging.info(f"   🔢 找到包含數字的元素: {number_elements[:20]}")
            
            # === 🎯 智能數字識別：從找到的數字中提取社交數據 ===
            pure_numbers = []
            for text in number_elements:
                # 跳過明顯不是互動數據的文字
                if any(skip in text for skip in ['瀏覽', '次瀏覽', '觀看', '天', '小時', '分鐘', '秒', 'on.natgeo.com']):
                    continue
                    
                number = parse_number(text)
                if number and number > 0:
                    pure_numbers.append((number, text))
                    logging.info(f"   📊 提取數字: {number} (從 '{text}')")
            
            # 根據數字大小智能分配（通常：likes > comments > reposts > shares）
            pure_numbers.sort(reverse=True)  # 從大到小排序
            
            if len(pure_numbers) >= 4:
                dom_counts["likes"] = pure_numbers[0][0]
                dom_counts["comments"] = pure_numbers[1][0] 
                dom_counts["reposts"] = pure_numbers[2][0]
                dom_counts["shares"] = pure_numbers[3][0]
                logging.info(f"   🎯 智能分配4個數字: 讚={dom_counts['likes']}, 留言={dom_counts['comments']}, 轉發={dom_counts['reposts']}, 分享={dom_counts['shares']}")
            elif len(pure_numbers) >= 2:
                dom_counts["likes"] = pure_numbers[0][0]
                dom_counts["comments"] = pure_numbers[1][0]
                logging.info(f"   🎯 智能分配2個數字: 讚={dom_counts['likes']}, 留言={dom_counts['comments']}")
            elif len(pure_numbers) >= 1:
                dom_counts["likes"] = pure_numbers[0][0]
                logging.info(f"   🎯 智能分配1個數字: 讚={dom_counts['likes']}")
                
        except Exception as e:
            logging.warning(f"   ⚠️ 智能數字提取失敗: {e}")
        
        # 如果智能提取成功，跳過傳統選擇器；否則繼續嘗試
        if not dom_counts:
            logging.info(f"   ⚠️ 智能提取失敗，回到傳統選擇器...")
            for key, sels in count_selectors.items():
                logging.info(f"   🔍 嘗試提取 {key} 數據...")
                for i, sel in enumerate(sels):
                    try:
                        el = page.locator(sel).first
                        count = await el.count()
                        if count > 0:
                            text = (await el.inner_text()).strip()
                            logging.info(f"   📝 選擇器 {i+1}/{len(sels)} '{sel}' 找到文字: '{text}'")
                            n = parse_number(text)
                            if n and n > 0:
                                dom_counts[key] = n
                                logging.info(f"   ✅ DOM 成功提取 {key}: {n} (選擇器: {sel})")
                                break
                            else:
                                logging.info(f"   ⚠️ 無法解析數字: '{text}' -> {n}")
                        else:
                            logging.info(f"   ❌ 選擇器 {i+1}/{len(sels)} 未找到元素: '{sel}'")
                    except Exception as e:
                        logging.info(f"   ⚠️ 選擇器 {i+1}/{len(sels)} '{sel}' 錯誤: {e}")
                        continue
                
                if key not in dom_counts:
                    logging.warning(f"   ❌ 無法找到 {key} 數據")
        
        if dom_counts:
            counts_data = {
                "likes": dom_counts.get("likes", 0),
                "comments": dom_counts.get("comments", 0),
                "reposts": dom_counts.get("reposts", 0),
                "shares": dom_counts.get("shares", 0),
            }
            logging.info(f"   🎯 DOM 計數後援成功: {counts_data}")
            return counts_data
        else:
            # 所有方法都失敗時，記錄頁面狀態用於調試
            await self._debug_failed_page(page)
            return {}
    
    async def _debug_failed_page(self, page: Page):
        """調試失敗頁面的狀態"""
        logging.warning(f"   ❌ GraphQL攔截和DOM後援都失敗了！")
        try:
            page_title = await page.title()
            page_url = page.url
            logging.info(f"   📄 失敗頁面分析 - 標題: {page_title}")
            logging.info(f"   🔗 失敗頁面分析 - URL: {page_url}")
            
            # 檢查頁面是否正常載入
            all_text = await page.inner_text('body')
            if "登入" in all_text or "login" in all_text.lower():
                logging.warning(f"   ⚠️ 可能遇到登入頁面")
            elif len(all_text) < 100:
                logging.warning(f"   ⚠️ 頁面內容太少，可能載入失敗")
            else:
                logging.info(f"   📝 頁面內容長度: {len(all_text)} 字元")
                
                # 檢查是否有互動按鈕
                like_buttons = await page.locator('[aria-label*="like"], [aria-label*="Like"], [aria-label*="喜歡"]').count()
                comment_buttons = await page.locator('[aria-label*="comment"], [aria-label*="Comment"], [aria-label*="留言"]').count()
                logging.info(f"   📊 找到按鈕: 讚 {like_buttons} 個, 留言 {comment_buttons} 個")
                
                # 嘗試找到任何數字
                all_numbers = await page.locator(':text-matches("\\d+")').all_inner_texts()
                if all_numbers:
                    logging.info(f"   🔢 頁面所有數字: {all_numbers[:15]}")  # 顯示前15個
                
                # 檢查是否有阻擋元素
                modal_count = await page.locator('[role="dialog"], .modal, [data-testid*="modal"]').count()
                if modal_count > 0:
                    logging.warning(f"   ⚠️ 發現 {modal_count} 個模態框可能阻擋內容")
                    
        except Exception as debug_e:
            logging.warning(f"   ⚠️ 失敗頁面分析錯誤: {debug_e}")
    
    async def _update_post_data(self, post: PostMetrics, counts_data: dict, content_data: dict, task_id: str, username: str) -> bool:
        """更新貼文數據"""
        updated = False
        
        # 更新計數數據 - 只在現有數據為 None 或 0 時才更新
        if counts_data:
            if post.likes_count in (None, 0) and (counts_data.get("likes") or 0) > 0:
                post.likes_count = counts_data["likes"]
                updated = True
            if post.comments_count in (None, 0) and (counts_data.get("comments") or 0) > 0:
                post.comments_count = counts_data["comments"]
                updated = True
            if post.reposts_count in (None, 0) and (counts_data.get("reposts") or 0) > 0:
                post.reposts_count = counts_data["reposts"]
                updated = True
            if post.shares_count in (None, 0) and (counts_data.get("shares") or 0) > 0:
                post.shares_count = counts_data["shares"]
                updated = True
        
        # 更新內容數據 - 只在現有數據為空時才更新
        if content_data.get("content") and not post.content:
            logging.info(f"   📝 [DEBUG] 更新 post.content: 從 '{post.content}' → '{content_data['content']}'")
            post.content = content_data["content"]
            updated = True
        
        if content_data.get("images") and not post.images:
            post.images = content_data["images"]
            updated = True
        
        if content_data.get("videos") and not post.videos:
            # 過濾實際影片（排除 POSTER）
            actual_videos = [v for v in content_data["videos"] if not v.startswith("POSTER::")]
            if actual_videos:
                post.videos = actual_videos
                updated = True
        
        # ← 新增: 更新真實發文時間
        if content_data.get("post_published_at") and not post.post_published_at:
            post.post_published_at = content_data["post_published_at"]
            updated = True
        
        # ← 新增: 更新主題標籤
        if content_data.get("tags") and not post.tags:
            post.tags = content_data["tags"]
            updated = True
        
        if updated:
            post.processing_stage = "details_filled_hybrid"
            # 構建補齊信息
            info_parts = [
                f"讚={post.likes_count}",
                f"內容={len(post.content)}字",
                f"圖片={len(post.images)}個",
                f"影片={len(post.videos)}個"
            ]
            
            if post.post_published_at:
                info_parts.append(f"發文時間={post.post_published_at.strftime('%Y-%m-%d %H:%M')}")
            if post.tags:
                info_parts.append(f"標籤={post.tags}")
                
            logging.info(f"  ✅ 混合策略成功補齊 {post.post_id}: {', '.join(info_parts)}")
            
            # 發布進度
            if task_id:
                await publish_progress(
                    task_id, 
                    "details_fetched_hybrid",
                    username=content_data.get("username", username or "unknown"),
                    post_id=post.post_id,
                    likes_count=post.likes_count,
                    content_length=len(post.content),
                    media_count=len(post.images) + len(post.videos)
                )
        else:
            post.processing_stage = "details_failed"
            logging.warning(f"  ⚠️ 混合策略無法補齊 {post.post_id} 的數據")
        
        return updated
    
    async def _extract_post_published_at(self, page: Page) -> Optional[Any]:
        """提取貼文真實發布時間 (從DOM)"""
        from datetime import datetime
        import json
        
        try:
            # 方法A: 直接抓 <time> 的 datetime 屬性
            time_elements = page.locator('time[datetime]')
            count = await time_elements.count()
            
            if count > 0:
                for i in range(min(count, 5)):  # 檢查前5個
                    try:
                        time_el = time_elements.nth(i)
                        
                        # datetime 屬性
                        iso_time = await time_el.get_attribute('datetime')
                        if iso_time:
                            from dateutil import parser
                            return parser.parse(iso_time)
                        
                        # title 或 aria-label 屬性  
                        title_time = (await time_el.get_attribute('title') or 
                                    await time_el.get_attribute('aria-label'))
                        if title_time:
                            parsed_time = self._parse_chinese_time(title_time)
                            if parsed_time:
                                return parsed_time
                    except Exception:
                        continue
            
            # 方法B: 解析 __NEXT_DATA__
            try:
                script_el = page.locator('#__NEXT_DATA__')
                if await script_el.count() > 0:
                    script_content = await script_el.text_content()
                    data = json.loads(script_content)
                    
                    taken_at = self._find_taken_at(data)
                    if taken_at:
                        return datetime.fromtimestamp(taken_at)
                        
            except Exception:
                pass
            
        except Exception:
            pass
        
        return None
    
    def _parse_chinese_time(self, time_str: str) -> Optional[Any]:
        """解析中文時間格式"""
        from datetime import datetime
        try:
            # 處理 "2025年8月3日下午 2:36" 格式
            if "年" in time_str and "月" in time_str and "日" in time_str:
                import re
                match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日.*?(\d{1,2}):(\d{2})', time_str)
                if match:
                    year, month, day, hour, minute = map(int, match.groups())
                    
                    # 處理下午/上午
                    if "下午" in time_str and hour < 12:
                        hour += 12
                    elif "上午" in time_str and hour == 12:
                        hour = 0
                    
                    return datetime(year, month, day, hour, minute)
        except:
            pass
        return None
    
    def _find_taken_at(self, data: Any, path: str = "") -> Optional[int]:
        """遞歸搜索 taken_at 時間戳"""
        if isinstance(data, dict):
            for key, value in data.items():
                if key == "taken_at" and isinstance(value, int) and value > 1000000000:
                    return value
                result = self._find_taken_at(value, f"{path}.{key}")
                if result:
                    return result
        elif isinstance(data, list):
            for i, item in enumerate(data):
                result = self._find_taken_at(item, f"{path}[{i}]")
                if result:
                    return result
        return None
    
    async def _extract_tags_from_dom(self, page: Page) -> List[str]:
        """提取主題標籤 (專門搜索Threads標籤連結)"""
        tags = []
        
        try:
            # 策略1: 搜索標籤連結（優先級最高）
            tag_link_selectors = [
                'a[href*="/search?q="][href*="serp_type=tags"]',  # 標籤搜索連結
                'a[href*="/search"][href*="tag_id="]',  # 包含tag_id的連結
                'a[href*="serp_type=tags"]',  # 標籤類型連結
            ]
            
            for selector in tag_link_selectors:
                try:
                    tag_links = page.locator(selector)
                    count = await tag_links.count()
                    
                    if count > 0:
                        # 只檢查前3個（避免回復中的標籤）
                        for i in range(min(count, 3)):
                            try:
                                link = tag_links.nth(i)
                                href = await link.get_attribute('href')
                                text = await link.inner_text()
                                
                                if href and text:
                                    tag_name = self._extract_tag_name_from_link(href, text)
                                    if tag_name and tag_name not in tags:
                                        tags.append(tag_name)
                                        return tags  # 找到一個就返回
                                        
                            except Exception:
                                continue
                                
                except Exception:
                    continue
            
            # 策略2: 搜索主文章區域內的標籤元素
            main_post_selectors = [
                'article:first-of-type',
                '[role="article"]:first-of-type',
                'div[data-pressable-container]:first-of-type',
            ]
            
            for main_selector in main_post_selectors:
                try:
                    main_element = page.locator(main_selector)
                    if await main_element.count() > 0:
                        # 在主文章內搜索標籤連結
                        main_tag_links = main_element.locator('a[href*="/search"]')
                        main_count = await main_tag_links.count()
                        
                        if main_count > 0:
                            for i in range(min(main_count, 2)):
                                try:
                                    link = main_tag_links.nth(i)
                                    href = await link.get_attribute('href')
                                    text = await link.inner_text()
                                    
                                    if href and text:
                                        tag_name = self._extract_tag_name_from_link(href, text)
                                        if tag_name and tag_name not in tags:
                                            tags.append(tag_name)
                                            return tags
                                            
                                except Exception:
                                    continue
                        
                except Exception:
                    continue
            
        except Exception:
            pass
        
        return tags[:1] if tags else []  # 只返回第一個標籤
    
    def _extract_tag_name_from_link(self, href: str, text: str) -> Optional[str]:
        """從標籤連結中提取標籤名稱"""
        try:
            # 從URL的q參數中解析
            if "q=" in href:
                import urllib.parse
                parsed_url = urllib.parse.urlparse(href)
                query_params = urllib.parse.parse_qs(parsed_url.query)
                
                if 'q' in query_params:
                    tag_name = query_params['q'][0]
                    tag_name = urllib.parse.unquote(tag_name)
                    return tag_name
            
            # 從連結文本中取得（備用）
            if text and len(text.strip()) > 0 and len(text.strip()) <= 20:
                clean_text = text.strip()
                if clean_text.startswith('#'):
                    clean_text = clean_text[1:]
                return clean_text
                
        except Exception:
            pass
        
        return None