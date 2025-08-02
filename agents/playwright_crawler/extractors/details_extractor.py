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

        # 減少並發數以避免觸發反爬蟲機制
        semaphore = asyncio.Semaphore(1)  # 更保守的並發數
        
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
                    
                    async def handle_counts_response(response):
                        await self._handle_graphql_response(response, counts_data, video_urls, captured_graphql_request)
                    
                    page.on("response", handle_counts_response)
                    
                    # === 步驟 2: 導航和觸發載入 ===
                    await page.goto(post.url, wait_until="networkidle", timeout=60000)
                    await asyncio.sleep(3)
                    
                    # === 步驟 2.5: 混合策略重發請求 ===
                    if captured_graphql_request and not counts_data:
                        counts_data = await self._resend_graphql_request(captured_graphql_request, post.url)
                    
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
        """處理 GraphQL 響應的攔截"""
        try:
            import json
            url = response.url.lower()
            headers = response.request.headers
            query_name = headers.get("x-fb-friendly-name", "")
            
            # 攔截計數查詢請求（保存headers和payload）
            if ("/graphql" in url and response.status == 200 and 
                "useBarcelonaBatchedDynamicPostCountsSubscriptionQuery" in query_name):
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
                
                # 也嘗試直接解析當前響應（作為備用）
                try:
                    data = await response.json()
                    if "data" in data and "data" in data["data"] and "posts" in data["data"]["data"]:
                        posts_list = data["data"]["data"]["posts"]
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
                                logging.info(f"   ✅ 直接攔截成功: 讚={counts_data['likes']}, 留言={counts_data['comments']}, 轉發={counts_data['reposts']}, 分享={counts_data['shares']}")
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
    
    async def _resend_graphql_request(self, captured_graphql_request: dict, post_url: str) -> dict:
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
                            if (text and len(text.strip()) > 10 and 
                                not text.strip().isdigit() and
                                "小時" not in text and "分鐘" not in text and
                                not text.startswith("@")):
                                content = text.strip()
                                break
                        except:
                            continue
                    
                    if content:
                        break
                except:
                    continue
            
            content_data["content"] = content
            
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
        
        if updated:
            post.processing_stage = "details_filled_hybrid"
            logging.info(f"  ✅ 混合策略成功補齊 {post.post_id}: 讚={post.likes_count}, 內容={len(post.content)}字, 圖片={len(post.images)}個, 影片={len(post.videos)}個")
            
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