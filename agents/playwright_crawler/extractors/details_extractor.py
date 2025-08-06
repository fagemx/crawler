"""
詳細數據提取器

負責使用三層備用策略補齊貼文詳細數據：
1. HTML正則解析 - 最穩定，直接從HTML文本提取 (優先級最高)
2. GraphQL 計數攔截 - 準確的API數據 (備用方案1) 
3. DOM 選擇器解析 - 頁面元素定位 (最後備用)

同時提取內容和媒體數據 (content, images, videos)
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
from ..parsers.html_parser import HTMLParser


class DetailsExtractor:
    """
    詳細數據提取器 - 使用混合策略提取完整的貼文數據
    """
    
    def __init__(self):
        self.html_parser = HTMLParser()  # 初始化HTML解析器
    
    async def fill_post_details_from_page(self, posts_to_fill: List[PostMetrics], context: BrowserContext, task_id: str = None, username: str = None) -> List[PostMetrics]:
        """
        使用三層備用策略補齊貼文詳細數據：
        1. HTML正則解析 - 最穩定，零額外成本 (優先級最高)
        2. GraphQL 計數攔截 - 準確的API數據 (備用方案1)
        3. DOM 選擇器解析 - 頁面元素定位 (最後備用)
        
        同時提取內容和媒體數據，這種多層架構提供最穩定可靠的數據提取。
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
                    
                    # === 步驟 1.5: 注入play()劫持腳本（新版Threads影片提取） ===
                    await page.add_init_script("""
                    (function () {
                        // 劫持HTMLMediaElement.play() 方法收集影片URL
                        const origPlay = HTMLMediaElement.prototype.play;
                        HTMLMediaElement.prototype.play = function () {
                            if (this.currentSrc || this.src) {
                                const videoUrl = this.currentSrc || this.src;
                                // 過濾真正的影片格式
                                if (videoUrl.includes('.mp4') || 
                                    videoUrl.includes('.m3u8') || 
                                    videoUrl.includes('.mpd') ||
                                    videoUrl.includes('video') ||
                                    videoUrl.includes('/v/') ||
                                    this.tagName.toLowerCase() === 'video') {
                                    window._lastVideoSrc = videoUrl;
                                    window._videoSourceInfo = {
                                        url: videoUrl,
                                        tagName: this.tagName,
                                        duration: this.duration || 0,
                                        videoWidth: this.videoWidth || 0,
                                        videoHeight: this.videoHeight || 0
                                    };
                                    console.log('[Video Hijack] 捕獲真實影片:', videoUrl);
                                }
                            }
                            return origPlay.apply(this, arguments);
                        };
                        
                        // 覆寫IntersectionObserver強制可見
                        const origObserver = window.IntersectionObserver;
                        window.IntersectionObserver = function(callback, options) {
                            const fakeObserver = new origObserver(function(entries) {
                                entries.forEach(entry => { entry.isIntersecting = true; });
                                callback(entries);
                            }, options);
                            return fakeObserver;
                        };
                        
                        window._videoHijackReady = true;
                    })();
                    """)
                    
                    # === 步驟 2: 直接導航（簡單高效） ===
                    await page.goto(post.url, wait_until="domcontentloaded", timeout=45000)
                    
                    # === 步驟 2.1: HTML解析（第一優先級，零額外成本） ===
                    html_content = None
                    try:
                        html_content = await page.content()  # 獲取完整HTML
                        html_counts = self.html_parser.extract_from_html(html_content)
                        if html_counts:
                            counts_data.update(html_counts)
                            logging.info(f"   🎯 HTML解析成功: {html_counts}")
                            # 如果HTML解析成功，記錄HTML內容供調試使用
                            post_id = post.post_id if hasattr(post, 'post_id') else 'unknown'
                            logging.debug(f"   📝 HTML解析成功，post_id: {post_id}")
                        else:
                            logging.debug(f"   📄 HTML解析未找到數據，繼續其他方法...")
                    except Exception as e:
                        logging.warning(f"   ⚠️ HTML解析失敗: {e}")
                    
                    # === 步驟 2.2: JavaScript瀏覽數提取（針對動態內容） ===
                    # 調試：檢查HTML解析是否已有瀏覽數
                    existing_views = counts_data.get("views_count")
                    logging.info(f"   🔍 [DEBUG] HTML解析瀏覽數: {existing_views}")
                    
                    if not existing_views:
                        logging.info(f"   🚀 [DEBUG] 開始JavaScript瀏覽數提取...")
                        try:
                            views_count = await self._extract_views_with_javascript(page)
                            if views_count:
                                counts_data["views_count"] = views_count
                                logging.info(f"   👁️ JavaScript提取瀏覽數成功: {views_count}")
                            else:
                                logging.warning(f"   📄 JavaScript未找到瀏覽數...")
                        except Exception as e:
                            logging.warning(f"   ⚠️ JavaScript瀏覽數提取失敗: {e}")
                    else:
                        logging.info(f"   ⏩ [DEBUG] HTML已有瀏覽數，跳過JavaScript提取")
                    
                    # 智能等待：先短暫等待，如果沒有攔截到數據再延長
                    await asyncio.sleep(1.5)  # 縮短初始等待時間
                    
                    # 檢查是否已經攔截到數據
                    if not counts_data:
                        logging.debug(f"   ⏳ 首次等待未攔截到數據，延長等待...")
                        await asyncio.sleep(1.5)  # 額外等待1.5秒（總共3秒）
                    
                    # === 檢查HTML解析是否已經成功 ===
                    html_success = counts_data and all(counts_data.get(k, 0) > 0 for k in ["likes", "comments", "reposts", "shares"])
                    if html_success:
                        logging.info(f"   ✅ HTML解析已提供完整數據，跳過GraphQL攔截: {counts_data}")
                        response_handler_active = False
                    else:
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
                    
                    # === 步驟 3.5: DOM 計數後援（當 HTML解析 和 GraphQL 攔截都失敗時） ===
                    if not counts_data or not any(counts_data.values()):
                        logging.info(f"   🔄 HTML和GraphQL都未獲取數據，啟動DOM後援...")
                        dom_counts = await self._extract_counts_from_dom_fallback(page)
                        if dom_counts:
                            counts_data.update(dom_counts)
                            logging.info(f"   🎯 DOM後援成功: {dom_counts}")
                        else:
                            logging.warning(f"   ❌ 所有提取方法都失敗了")
                    
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
            
            # 🎬 精確GraphQL攔截（根據用戶建議改進）
            if "GraphVideoPlayback" in response.url or "PolarisGraphVideoPlaybackQuery" in response.url:
                try:
                    data = await response.json()
                    logging.debug(f"   🔍 命中GraphQL影片查詢: {response.url}")
                    
                    # 直接路徑：data.video
                    video_data = data.get("data", {}).get("video", {})
                    if video_data:
                        for key in ("playable_url_hd", "playable_url"):
                            url = video_data.get(key)
                            if url:
                                video_urls.add(url)
                                logging.info(f"   🎥 GraphQL{key}: {url}")  # 顯示完整URL
                    else:
                        logging.debug(f"   ⚠️ GraphQL響應無video字段: {list(data.get('data', {}).keys())}")
                        
                except Exception as e:
                    logging.debug(f"   ⚠️ GraphQL影片解析失敗: {e}")
            
            # 🚀 第0層：直接攔截影片文件請求（最直接方法）
            url_clean = response.url.split("?")[0]  # 移除查詢參數
            if url_clean.endswith((".mp4", ".m3u8", ".mpd", ".webm", ".mov")):
                video_urls.add(response.url)
                logging.info(f"   🎯 第0層直接攔截完整URL: {response.url}")
            
            # 🎥 傳統資源攔截（備用）
            content_type = response.headers.get("content-type", "")
            resource_type = response.request.resource_type
            if (resource_type == "media" or content_type.startswith("video/")):
                if self._is_valid_video_url(response.url):
                    video_urls.add(response.url)
                    logging.info(f"   🎥 傳統資源攔截完整URL: {response.url}")
                else:
                    logging.debug(f"   🚫 跳過非影片資源: {response.url[:60]}...")
                
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
            
            # 確保有認證 - 修復版：加入關鍵token
            # 1. 設置authorization
            if not headers.get("authorization") and 'ig_set_authorization' in cookies:
                auth_value = cookies['ig_set_authorization']
                headers["authorization"] = f"Bearer {auth_value}" if not auth_value.startswith('Bearer') else auth_value
            
            # 2. 確保關鍵的fb_dtsg和lsd token存在
            if 'fb_dtsg' in cookies:
                headers["x-fb-dtsg"] = cookies['fb_dtsg']
            elif 'dtsg' in cookies:
                headers["x-fb-dtsg"] = cookies['dtsg']
            
            if 'lsd' in cookies:
                headers["x-fb-lsd"] = cookies['lsd']
            elif '_js_lsd' in cookies:
                headers["x-fb-lsd"] = cookies['_js_lsd']
            
            # 3. 確保User-Agent和其他必要header
            if 'user-agent' not in headers:
                headers["user-agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            
            logging.debug(f"   🔧 認證檢查: auth={bool(headers.get('authorization'))}, dtsg={bool(headers.get('x-fb-dtsg'))}, lsd={bool(headers.get('x-fb-lsd'))}")
            
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
    
    async def _extract_views_with_javascript(self, page) -> Optional[int]:
        """使用JavaScript從渲染後的DOM中提取瀏覽數"""
        try:
            # JavaScript代碼：搜索所有包含瀏覽數的元素
            js_code = """
            () => {
                // 搜索所有可能包含瀏覽數的文本
                const allTexts = [];
                const walker = document.createTreeWalker(
                    document.body,
                    NodeFilter.SHOW_TEXT,
                    null,
                    false
                );
                
                let node;
                while (node = walker.nextNode()) {
                    const text = node.textContent.trim();
                    if (text && (
                        text.includes('views') || 
                        text.includes('瀏覽') ||
                        text.includes('浏览') ||
                        /\\d+K\\s*views/i.test(text) ||
                        /\\d+M\\s*views/i.test(text) ||
                        /\\d+萬.*瀏覽/i.test(text) ||
                        /\\d+万.*浏览/i.test(text)
                    )) {
                        allTexts.push(text);
                    }
                }
                
                // 也搜索aria-label和data屬性
                const elements = document.querySelectorAll('*');
                for (const el of elements) {
                    const ariaLabel = el.getAttribute('aria-label') || '';
                    const title = el.getAttribute('title') || '';
                    const dataText = el.getAttribute('data-text') || '';
                    
                    for (const attr of [ariaLabel, title, dataText, el.textContent || '']) {
                        if (attr && (
                            attr.includes('views') || 
                            attr.includes('瀏覽') ||
                            attr.includes('浏览') ||
                            /\\d+K\\s*views/i.test(attr) ||
                            /\\d+M\\s*views/i.test(attr) ||
                            /\\d+萬.*瀏覽/i.test(attr) ||
                            /\\d+万.*浏览/i.test(attr)
                        )) {
                            allTexts.push(attr.trim());
                        }
                    }
                }
                
                return [...new Set(allTexts)]; // 去重
            }
            """
            
            # 執行JavaScript獲取所有可能的瀏覽數文本
            view_texts = await page.evaluate(js_code)
            
            if not view_texts:
                logging.debug(f"   🔍 JavaScript未找到任何瀏覽相關文本")
                return None
            
            logging.debug(f"   🔍 JavaScript找到 {len(view_texts)} 個瀏覽相關文本:")
            for i, text in enumerate(view_texts[:5]):  # 只記錄前5個
                logging.debug(f"      {i+1}. '{text}'")
            
            # 使用現有的瀏覽數解析邏輯
            for text in view_texts:
                views_count = self._parse_views_text(text)
                if views_count and views_count > 1000:  # 合理性檢查
                    logging.info(f"   🎯 成功解析瀏覽數: {views_count} (來源: '{text}')")
                    return views_count
            
            logging.debug(f"   ❌ 所有瀏覽文本都無法解析出有效數字")
            return None
            
        except Exception as e:
            logging.warning(f"   ⚠️ JavaScript瀏覽數提取過程失敗: {e}")
            return None
    
    def _parse_views_text(self, text: str) -> Optional[int]:
        """解析瀏覽數文本，返回數字"""
        import re
        
        try:
            # 英文格式
            patterns = [
                (r'(\d+(?:\.\d+)?)\s*K\s*views', 1000),
                (r'(\d+(?:\.\d+)?)\s*M\s*views', 1000000),
                (r'(\d+(?:,\d{3})*)\s*views', 1),
                # 中文格式  
                (r'(\d+(?:\.\d+)?)\s*萬.*瀏覽', 10000),
                (r'(\d+(?:\.\d+)?)\s*万.*浏览', 10000),
                (r'(\d+(?:,\d{3})*)\s*.*瀏覽', 1),
                (r'(\d+(?:,\d{3})*)\s*.*浏览', 1),
            ]
            
            for pattern_str, multiplier in patterns:
                pattern = re.compile(pattern_str, re.IGNORECASE)
                match = pattern.search(text)
                if match:
                    try:
                        num = float(match.group(1).replace(',', ''))
                        views = int(num * multiplier)
                        if 1000 <= views <= 50000000:  # 合理範圍
                            return views
                    except (ValueError, TypeError):
                        continue
            
            return None
            
        except Exception as e:
            logging.debug(f"   ⚠️ 解析瀏覽數文本失敗: {e}")
            return None
    
    async def _realistic_navigation_to_post(self, page: Page, post_url: str):
        """現實導航路徑：首頁 → 用戶頁 → 貼文 (避免反爬蟲)"""
        try:
            import re
            from urllib.parse import urlparse
            
            # 從貼文URL解析用戶名和貼文ID
            url_match = re.search(r'/@([^/]+)/post/([^/?]+)', post_url)
            if not url_match:
                logging.warning(f"   ⚠️ 無法解析貼文URL，回退到直接導航: {post_url}")
                await page.goto(post_url, wait_until="domcontentloaded", timeout=45000)
                return
                
            username = url_match.group(1)
            post_id = url_match.group(2)
            parsed_url = urlparse(post_url)
            base_domain = f"{parsed_url.scheme}://{parsed_url.netloc}"
            
            logging.info(f"   🌐 開始現實導航: {username} → {post_id}")
            
            # 步驟1: 導航到首頁
            logging.info(f"   📍 步驟1: 導航到首頁...")
            await page.goto(f"{base_domain}/", wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)  # 等待首頁載入
            
            # 步驟2: 模擬人類行為（滾動一下）
            logging.debug(f"   👆 模擬用戶滾動...")
            await page.mouse.wheel(0, 300)
            await asyncio.sleep(1)
            
            # 步驟3: 導航到用戶頁面
            user_profile_url = f"{base_domain}/@{username}"
            logging.info(f"   📍 步驟2: 導航到用戶頁面: {user_profile_url}")
            await page.goto(user_profile_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)  # 等待用戶頁面載入
            
            # 步驟4: 嘗試找到並點擊目標貼文
            logging.info(f"   📍 步驟3: 尋找目標貼文: {post_id}")
            
            # 嘗試多種方式找到貼文連結
            post_link_selectors = [
                f'a[href*="{post_id}"]',  # 直接包含貼文ID的連結
                f'a[href*="/post/{post_id}"]',  # 完整路徑
                f'a[href*="/{username}/post/{post_id}"]',  # 完整用戶路徑
            ]
            
            post_found = False
            for selector in post_link_selectors:
                try:
                    post_links = page.locator(selector)
                    link_count = await post_links.count()
                    
                    if link_count > 0:
                        logging.info(f"   🎯 找到目標貼文連結！點擊進入...")
                        await post_links.first.click()
                        await page.wait_for_load_state("networkidle", timeout=15000)
                        post_found = True
                        break
                        
                except Exception as e:
                    logging.debug(f"   ❌ 貼文連結查找失敗: {e}")
                    continue
            
            # 如果無法通過點擊找到，回退到直接導航
            if not post_found:
                logging.warning(f"   ⚠️ 未找到貼文連結，直接導航到目標頁面...")
                await page.goto(post_url, wait_until="networkidle", timeout=30000)
            
            logging.info(f"   ✅ 現實導航完成")
            
        except Exception as e:
            logging.error(f"   ❌ 現實導航失敗: {e}")
            # 回退到直接導航
            logging.info(f"   🔄 回退到直接導航...")
            await page.goto(post_url, wait_until="domcontentloaded", timeout=45000)
    
    async def _trigger_video_loading(self, page: Page):
        """觸發影片載入 - 增強版（基於技術報告）"""
        try:
            # 階段1: 擴展觸發選擇器（基於技術報告）
            trigger_selectors = [
                'div[data-testid="media-viewer"]',
                'video',  
                'div[role="button"][aria-label*="play"]',
                'div[role="button"][aria-label*="播放"]', 
                'div[role="button"][aria-label*="Play"]',
                '[data-pressable-container] div[style*="video"]',
                'div[aria-label*="Video"]',  # 新增
                'div[aria-label*="影片"]',    # 新增
                'div[data-testid*="video"]', # 新增
                'button[aria-label*="播放"]', # 新增
                'button[aria-label*="play"]', # 新增
            ]
            
            logging.info(f"   🎬 開始觸發影片載入...")
            video_triggered = False
            
            for i, selector in enumerate(trigger_selectors):
                try:
                    elements = page.locator(selector)
                    count = await elements.count()
                    if count > 0:
                        logging.info(f"   🎯 觸發器 {i+1}/{len(trigger_selectors)} 找到 {count} 個元素: {selector}")
                        # 嘗試點擊第一個元素
                        await elements.first.click(timeout=3000)
                        await asyncio.sleep(1.5)  # 短暫等待
                        video_triggered = True
                        break
                except Exception as e:
                    logging.debug(f"   ❌ 觸發器 {i+1} 失敗: {e}")
                    continue
            
            if video_triggered:
                logging.info(f"   ✅ 影片觸發成功，等待載入...")
                # 階段2: 延遲二階段（技術報告建議）
                await asyncio.sleep(3)  # 等待第一段 MPD/M3U8
                logging.debug(f"   🔄 延遲二階段等待 MP4 片段...")
            else:
                logging.warning(f"   ⚠️ 未找到影片觸發元素")
                
        except Exception as e:
            logging.warning(f"   ❌ 影片觸發載入失敗: {e}")
    
    def _clean_content_text(self, text: str) -> str:
        """清理內容文字，移除句尾的 \nTranslate"""
        if not text:
            return text
            
        cleaned = text.strip()
        
        # 移除句尾的翻譯標記（多種格式）
        translation_patterns = ['\nTranslate', '\n翻譯', '翻譯', 'Translate']
        
        for pattern in translation_patterns:
            if cleaned.endswith(pattern):
                cleaned = cleaned[:-len(pattern)].strip()
                logging.debug(f"   🧹 移除翻譯標記: {pattern}")
                break
        
        return cleaned
    
    def _is_valid_video_url(self, url: str) -> bool:
        """驗證URL是否為有效的影片URL"""
        if not url or not isinstance(url, str):
            return False
            
        url_lower = url.lower()
        
        # 明確的影片格式
        video_extensions = ['.mp4', '.webm', '.mov', '.avi', '.m3u8', '.mpd']
        if any(ext in url_lower for ext in video_extensions):
            return True
            
        # 包含video關鍵字的路徑
        video_keywords = ['/video/', '/v/', 'video', 'playback']
        if any(keyword in url_lower for keyword in video_keywords):
            return True
            
        # 排除明確的非影片資源
        non_video_patterns = [
            'poster', 'thumbnail', 'preview', '.jpg', '.png', '.jpeg', 
            '.gif', '.webp', '_n.jpg', '_n.png', 'stp=dst-jpg'
        ]
        if any(pattern in url_lower for pattern in non_video_patterns):
            return False
            
        # Facebook/Instagram CDN特殊判斷
        if 'fbcdn.net' in url_lower:
            # /v/ 路徑通常是影片, /p/ 或 /t/ 通常是圖片
            if '/v/' in url_lower or '/video/' in url_lower:
                return True
            elif '/p/' in url_lower or '/t/' in url_lower:
                return False
            # 其他fbcdn URL需要更多信息判斷
            return False
            
        return True
    
    async def _extract_video_from_next_data(self, page: Page) -> list:
        """從__NEXT_DATA__中提取影片URL（新版Threads Next.js架構）"""
        try:
            script_el = page.locator('script#__NEXT_DATA__')
            if await script_el.count() > 0:
                script_content = await script_el.text_content()
                if script_content:
                    import json
                    data = json.loads(script_content)
                    
                    # 簡化路徑解析（根據用戶建議改進）
                    video_urls = []
                    
                    try:
                        # 主路徑：單貼文或卡片流
                        medias = (
                            data["props"]["pageProps"]["post"].get("media", [])  # 單貼文
                            if "post" in data.get("props", {}).get("pageProps", {})
                            else data["props"]["pageProps"]["feed"]["edges"][0]["node"]["media"]  # 卡片流
                        )
                        
                        for item in medias:
                            video_url = item.get("video_url")
                            if video_url:
                                video_urls.append(video_url)
                                logging.info(f"   📹 __NEXT_DATA__影片: {video_url}")
                                
                    except (KeyError, TypeError, IndexError) as e:
                        logging.debug(f"   ⚠️ __NEXT_DATA__路徑解析失敗: {e}")
                        # 備用：直接搜索任何video_url
                        try:
                            import re
                            script_text = script_content
                            video_url_pattern = r'"video_url":"([^"]+)"'
                            matches = re.findall(video_url_pattern, script_text)
                            for match in matches:
                                video_urls.append(match)
                                logging.info(f"   📹 __NEXT_DATA__備用搜索: {match}")
                        except Exception:
                            pass
                    
                    return video_urls
        except Exception as e:
            logging.debug(f"   ⚠️ __NEXT_DATA__解析失敗: {e}")
        
        return []
    
    async def _extract_video_from_hijacked_play(self, page: Page) -> str:
        """從劫持的play()方法中獲取影片URL"""
        try:
            # 等待劫持腳本就緒
            await page.wait_for_function("window._videoHijackReady === true", timeout=5000)
            
            # 嘗試多種方式觸發影片播放以激活劫持
            try:
                # 方法1：使用鍵盤快捷鍵（很多播放器支持）
                await page.keyboard.press("k")  # 常見的播放/暫停快捷鍵
                await asyncio.sleep(0.5)
                
                # 方法2：點擊任何可能的播放元素
                trigger_selectors = [
                    'video', 'button[aria-label*="play"]', 'button[aria-label*="播放"]',
                    'div[role="button"][aria-label*="play"]'
                ]
                
                for selector in trigger_selectors:
                    try:
                        elements = page.locator(selector)
                        if await elements.count() > 0:
                            await elements.first.click(timeout=2000)
                            await asyncio.sleep(0.5)
                            break
                    except:
                        continue
                        
            except Exception as e:
                logging.debug(f"   ⚠️ 觸發播放失敗: {e}")
            
            # 等待劫持到影片URL或超時
            try:
                await page.wait_for_function("window._lastVideoSrc !== undefined", timeout=8000)
                video_url = await page.evaluate("window._lastVideoSrc")
                video_info = await page.evaluate("window._videoSourceInfo || {}")
                
                logging.info(f"   🔍 劫持詳情: 標籤={video_info.get('tagName', 'unknown')} 寬度={video_info.get('videoWidth', 0)} 高度={video_info.get('videoHeight', 0)}")
                logging.info(f"   🎬 完整URL: {video_url}")
                
                if video_url:
                    # 驗證是否為真正的影片URL
                    if self._is_valid_video_url(video_url):
                        logging.info(f"   ✅ 劫持play()獲得有效影片: {video_url[:60]}...")
                        return video_url
                    else:
                        logging.warning(f"   ❌ 劫持到非影片資源: {video_url[:60]}...")
                        return None
            except Exception:
                logging.debug(f"   ⏰ play()劫持超時，未捕獲到影片URL")
                
        except Exception as e:
            logging.debug(f"   ⚠️ play()劫持失敗: {e}")
        
        return None
    
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
                            
                            # 通過所有過濾條件，接受此內容並清理翻譯標記
                            content = self._clean_content_text(text)
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
                                        content = self._clean_content_text(backup_text)
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
            
            # 提取圖片 - 增強版（區分主貼文 vs 回應）
            images = []
            main_post_images = []
            
            # 策略1: 簡化的主貼文圖片提取（避免複雜選擇器）
            main_post_selectors = [
                'article img',  # 文章內的圖片
                'main img',     # main 標籤內的圖片
                'img[src*="t51.2885-15"]',  # Instagram圖片格式（簡單直接）
            ]
            
            for selector in main_post_selectors:
                try:
                    main_imgs = page.locator(selector)
                    main_count = await main_imgs.count()
                    logging.debug(f"   🔍 選擇器 {selector}: 找到 {main_count} 個圖片")
                    
                    # 簡化邏輯：只檢查前5個圖片
                    for i in range(min(main_count, 5)):
                        try:
                            img_elem = main_imgs.nth(i)
                            img_src = await img_elem.get_attribute("src")
                            
                            if (img_src and 
                                ("fbcdn" in img_src or "cdninstagram" in img_src) and
                                "rsrc.php" not in img_src and 
                                img_src not in main_post_images):
                                
                                main_post_images.append(img_src)
                                logging.debug(f"   🖼️ 主貼文圖片: {img_src[:50]}...")
                                
                                # 限制數量避免過多
                                if len(main_post_images) >= 3:
                                    break
                                    
                        except Exception as e:
                            logging.debug(f"   ⚠️ 圖片{i}處理失敗: {e}")
                            continue
                            
                    # 如果找到圖片就停止
                    if main_post_images:
                        break
                        
                except Exception as e:
                    logging.debug(f"   ⚠️ 選擇器失敗: {e}")
                    continue
            
            # 策略2: 如果主貼文提取失敗，簡單回退
            if not main_post_images:
                logging.debug(f"   🔄 主貼文圖片提取失敗，使用簡單回退...")
                img_elements = page.locator('img')
                img_count = await img_elements.count()
                
                # 簡單掃描前10個圖片
                for i in range(min(img_count, 10)):
                    try:
                        img_elem = img_elements.nth(i)
                        img_src = await img_elem.get_attribute("src")
                        
                        if (img_src and 
                            ("fbcdn" in img_src or "cdninstagram" in img_src) and
                            "rsrc.php" not in img_src and 
                            img_src not in images):
                            
                            images.append(img_src)
                            
                            # 限制數量
                            if len(images) >= 5:
                                break
                                
                    except:
                        continue
            
            # 使用主貼文圖片（優先）或回退圖片
            final_images = main_post_images if main_post_images else images
            content_data["images"] = final_images
            
            logging.info(f"   🖼️ 圖片提取結果: 主貼文={len(main_post_images)}個, 總計={len(final_images)}個")
            
            # 🎬 四層備援影片提取系統 - 2025年新版Threads適配
            videos = list(video_urls)
            logging.info(f"   🎬 四層備援影片提取開始...")
            logging.info(f"   🔸 第1層(GraphQL攔截): {len(video_urls)}個")
            
            # 第2層：__NEXT_DATA__ JSON解析
            next_data_videos = await self._extract_video_from_next_data(page)
            for video_url in next_data_videos:
                if video_url not in videos:
                    videos.append(video_url)
            logging.info(f"   🔸 第2層(__NEXT_DATA__): {len(next_data_videos)}個")
            
            # 第3層：play()劫持 + 自動播放
            hijacked_video = await self._extract_video_from_hijacked_play(page)
            if hijacked_video and hijacked_video not in videos:
                videos.append(hijacked_video)
            logging.info(f"   🔸 第3層(play()劫持): {'1' if hijacked_video else '0'}個")
            
            # 第4層：傳統DOM提取（備用）
            video_elements = page.locator('video')
            video_count = await video_elements.count()
            logging.info(f"   🔸 第4層(DOM備用): {video_count}個video元素")
            
            for i in range(video_count):
                try:
                    video_elem = video_elements.nth(i)
                    src = await video_elem.get_attribute("src")
                    data_src = await video_elem.get_attribute("data-src")
                    poster = await video_elem.get_attribute("poster")
                    
                    # 驗證並添加有效的影片URL
                    if src and src not in videos:
                        if self._is_valid_video_url(src):
                            videos.append(src)
                            logging.info(f"   📹 DOM video src完整URL: {src}")
                        else:
                            logging.debug(f"   🚫 跳過無效src: {src[:60]}...")
                            
                    if data_src and data_src not in videos:
                        if self._is_valid_video_url(data_src):
                            videos.append(data_src)
                            logging.info(f"   📹 DOM video data-src完整URL: {data_src}")
                        else:
                            logging.debug(f"   🚫 跳過無效data-src: {data_src[:60]}...")
                            
                    # poster單獨處理（始終保留，用於縮圖）
                    if poster and f"POSTER::{poster}" not in videos:
                        videos.append(f"POSTER::{poster}")
                        logging.debug(f"   🖼️ 影片縮圖: {poster[:60]}...")
                    
                    # source 子元素
                    sources = video_elem.locator('source')
                    source_count = await sources.count()
                    for j in range(source_count):
                        source_src = await sources.nth(j).get_attribute("src")
                        if source_src and source_src not in videos:
                            if self._is_valid_video_url(source_src):
                                videos.append(source_src)
                                logging.info(f"   📹 DOM source完整URL: {source_src}")
                            else:
                                logging.debug(f"   🚫 跳過無效source: {source_src[:60]}...")
                except Exception as e:
                    logging.debug(f"   ⚠️ video元素{i}處理失敗: {e}")
                    continue
            
            # 計算第0層（直接攔截）的貢獻
            direct_intercept_count = 0
            for url in video_urls:
                url_clean = url.split("?")[0]
                if url_clean.endswith((".mp4", ".m3u8", ".mpd", ".webm", ".mov")):
                    direct_intercept_count += 1
            
            content_data["videos"] = videos
            logging.info(f"   🎬 五層備援影片提取完成: 總計={len(videos)}個")
            logging.info(f"   📊 各層成效統計: 直接攔截={direct_intercept_count} | GraphQL={len(video_urls)-direct_intercept_count} | __NEXT_DATA__={len(next_data_videos)} | play()劫持={'1' if hijacked_video else '0'} | DOM={video_count}")
            
            # 調試：如果是影片貼文但沒找到影片URL，記錄更多信息
            if len(videos) == 0:
                logging.warning(f"   ⚠️ 影片貼文但未找到影片URL！")
                logging.debug(f"   🔍 頁面URL: {page.url}")
                logging.debug(f"   🔍 網路攔截到的URLs: {list(video_urls)}")
                
                # 嘗試查找其他可能的影片線索
                video_hints = []
                try:
                    # 查找包含"video"的元素
                    video_divs = page.locator('div[aria-label*="video"], div[aria-label*="Video"], div[aria-label*="影片"]')
                    hint_count = await video_divs.count()
                    if hint_count > 0:
                        video_hints.append(f"找到{hint_count}個video標籤")
                        
                    # 查找播放按鈕
                    play_buttons = page.locator('button[aria-label*="play"], button[aria-label*="Play"], button[aria-label*="播放"]')
                    play_count = await play_buttons.count()
                    if play_count > 0:
                        video_hints.append(f"找到{play_count}個播放按鈕")
                        
                    if video_hints:
                        logging.info(f"   💡 影片線索: {', '.join(video_hints)}")
                        
                except Exception as e:
                    logging.debug(f"   ⚠️ 影片線索查找失敗: {e}")
            
            # ← 新增: 提取真實發文時間
            try:
                post_published_at = await self._extract_post_published_at(page)
                if post_published_at:
                    content_data["post_published_at"] = post_published_at
                    logging.info(f"   📅 提取發文時間: {post_published_at}")
                else:
                    logging.warning(f"   📅 未找到發文時間")
            except Exception as e:
                logging.warning(f"   ⚠️ 發文時間提取失敗: {e}")
            
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
                # NEW: 基於頁面分析的最新選擇器
                "svg[aria-label='讚'] ~ span",
                "svg[aria-label='讚'] + span", 
                "svg[aria-label='讚']",
                "span.x1o0tod.x10l6tqk.x13vifvy",  # 從分析中發現的包含數字的span
                "button:has(svg[aria-label='讚']) span",
                # 通用數字選擇器（來自分析）
                "span:has-text('萬') span",
                "span:has-text('k') span",
                # English selectors (保留原有的)
                "button[aria-label*='likes'] span",
                "button[aria-label*='Like'] span", 
                "span:has-text(' likes')",
                "span:has-text(' like')",
                "button svg[aria-label='Like'] + span",
                "button[aria-label*='like']",
                # Chinese selectors (保留原有的)
                "button[aria-label*='個喜歡'] span",
                "button[aria-label*='喜歡']",
                # Generic patterns (保留原有的)
                "button[data-testid*='like'] span",
                "div[role='button'][aria-label*='like'] span"
            ],
            "comments": [
                # NEW: 基於頁面分析的最新選擇器
                "svg[aria-label='留言'] ~ span",
                "svg[aria-label='留言'] + span",
                "svg[aria-label='留言']",
                "svg[aria-label='comment'] ~ span",
                "svg[aria-label='comment'] + span", 
                "button:has(svg[aria-label='留言']) span",
                "button:has(svg[aria-label='comment']) span",
                # English selectors (保留原有的)
                "a[href$='#comments'] span",
                "span:has-text(' comments')",
                "span:has-text(' comment')",
                "a:has-text('comments')",
                "button[aria-label*='comment'] span",
                # Chinese selectors (保留原有的)
                "span:has-text(' 則留言')",
                "a:has-text('則留言')",
                # Generic patterns (保留原有的)
                "button[data-testid*='comment'] span",
                "div[role='button'][aria-label*='comment'] span"
            ],
            "reposts": [
                # NEW: 基於頁面分析的最新選擇器
                "svg[aria-label='轉發'] ~ span",
                "svg[aria-label='轉發'] + span",
                "svg[aria-label='轉發']",
                "button:has(svg[aria-label='轉發']) span",
                "div.x1i10hfl.x1qjc9v5.xjbqb8w span",  # 從分析中發現的轉發按鈕
                # English selectors (保留原有的)
                "span:has-text(' reposts')",
                "span:has-text(' repost')",
                "button[aria-label*='repost'] span",
                "a:has-text('reposts')",
                # Chinese selectors (保留原有的)
                "span:has-text(' 次轉發')",
                "a:has-text('轉發')",
                # Generic patterns (保留原有的)
                "button[data-testid*='repost'] span"
            ],
            "shares": [
                # NEW: 基於頁面分析的最新選擇器
                "svg[aria-label='分享'] ~ span",
                "svg[aria-label='分享'] + span",
                "svg[aria-label='分享']",
                "svg[aria-label='貼文已分享到聯邦宇宙'] ~ span",
                "svg[aria-label='貼文已分享到聯邦宇宙'] + span",
                "button:has(svg[aria-label='分享']) span",
                "div.x1i10hfl.x1qjc9v5.xjbqb8w span",  # 共用的按鈕容器類
                # English selectors (保留原有的)
                "span:has-text(' shares')",
                "span:has-text(' share')",
                "button[aria-label*='share'] span",
                "a:has-text('shares')",
                # Chinese selectors (保留原有的)
                "span:has-text(' 次分享')",
                "a:has-text('分享')",
                # Generic patterns (保留原有的)
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
            combo_found = False
            
            # 🎯 優先檢查組合數字格式 (例如: "1,230\n31\n53\n68")
            for text in number_elements:
                if '\n' in text and text.count('\n') >= 2:
                    numbers = []
                    for line in text.split('\n'):
                        line_num = parse_number(line.strip())
                        if line_num and line_num > 0:
                            numbers.append(line_num)
                    
                    if len(numbers) >= 3:  # 至少3個數字才認為是組合格式
                        logging.info(f"   🎯 發現組合數字格式: {numbers} (從 '{text}')")
                        # 通常順序：按讚, 留言, 轉發, 分享
                        if len(numbers) >= 1:
                            dom_counts["likes"] = numbers[0]
                            logging.info(f"   ❤️ 按讚數: {numbers[0]}")
                        if len(numbers) >= 2:
                            dom_counts["comments"] = numbers[1] 
                            logging.info(f"   💬 留言數: {numbers[1]}")
                        if len(numbers) >= 3:
                            dom_counts["reposts"] = numbers[2]
                            logging.info(f"   🔄 轉發數: {numbers[2]}")
                        if len(numbers) >= 4:
                            dom_counts["shares"] = numbers[3]
                            logging.info(f"   📤 分享數: {numbers[3]}")
                        combo_found = True
                        break
            
            # 如果沒找到組合格式，使用傳統方法
            if not combo_found:
                for text in number_elements:
                    # 跳過明顯不是互動數據的文字（但不跳過瀏覽數）
                    if any(skip in text for skip in ['天', '小時', '分鐘', '秒', 'on.natgeo.com', 'px', 'ms', '%']):
                        continue
                        
                    # 特殊處理：瀏覽數可能包含按讚數等信息
                    if '瀏覽' in text or '次瀏覽' in text:
                        # 如果是瀏覽數但包含有效數字，也提取（可能是按讚數）
                        number = parse_number(text)
                        if number and number > 0:
                            pure_numbers.append((number, text))
                            logging.info(f"   📊 提取瀏覽數字: {number} (從 '{text}')")
                    else:
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
            # 新增：更新瀏覽數
            if post.views_count in (None, 0) and (counts_data.get("views_count") or 0) > 0:
                post.views_count = counts_data["views_count"]
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
            
            # 計算分數 (基於所有互動數據)
            calculated_score = post.calculate_score()
            post.calculated_score = calculated_score  # 存儲計算分數
            
            # 構建補齊信息
            info_parts = [
                f"讚={post.likes_count}",
                f"內容={len(post.content)}字",
                f"圖片={len(post.images)}個",
                f"影片={len(post.videos)}個"
            ]
            
            # 如果有瀏覽數，添加到信息中
            if post.views_count:
                info_parts.insert(1, f"瀏覽={post.views_count}")
                
            # 添加計算分數到信息中
            info_parts.append(f"分數={calculated_score:.1f}")
            
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
        import logging
        
        try:
            logging.info(f"   🕒 [DEBUG] 開始時間提取...")
            
            # 方法A: 直接抓 <time> 的 datetime 屬性
            time_elements = page.locator('time[datetime]')
            count = await time_elements.count()
            logging.info(f"   🕒 [DEBUG] 找到 {count} 個time元素")
            
            if count > 0:
                for i in range(min(count, 5)):  # 檢查前5個
                    try:
                        time_el = time_elements.nth(i)
                        
                        # datetime 屬性
                        iso_time = await time_el.get_attribute('datetime')
                        logging.info(f"   🕒 [DEBUG] time[{i}] datetime屬性: {iso_time}")
                        if iso_time:
                            from dateutil import parser
                            parsed_time = parser.parse(iso_time)
                            
                            # 立即轉換為台北時間
                            from datetime import timezone, timedelta
                            taipei_tz = timezone(timedelta(hours=8))
                            taipei_time = parsed_time.astimezone(taipei_tz).replace(tzinfo=None)
                            
                            logging.info(f"   📅 [DEBUG] 解析成功時間: {parsed_time} → 台北時間: {taipei_time}")
                            return taipei_time
                        
                        # title 或 aria-label 屬性  
                        title_time = (await time_el.get_attribute('title') or 
                                    await time_el.get_attribute('aria-label'))
                        logging.info(f"   🕒 [DEBUG] time[{i}] title/aria-label: {title_time}")
                        if title_time:
                            parsed_time = self._parse_chinese_time(title_time)
                            if parsed_time:
                                # 立即轉換為台北時間（中文時間通常已經是台北時間）
                                from datetime import timezone, timedelta
                                taipei_tz = timezone(timedelta(hours=8))
                                if parsed_time.tzinfo is None:
                                    # 假設無時區信息的是台北時間
                                    taipei_time = parsed_time
                                else:
                                    taipei_time = parsed_time.astimezone(taipei_tz).replace(tzinfo=None)
                                
                                logging.info(f"   📅 [DEBUG] 中文時間解析成功: {parsed_time} → 台北時間: {taipei_time}")
                                return taipei_time
                    except Exception as e:
                        logging.info(f"   🕒 [DEBUG] time[{i}] 解析失敗: {e}")
                        continue
            
            # 方法B: 解析 __NEXT_DATA__
            logging.info(f"   🕒 [DEBUG] 嘗試__NEXT_DATA__方法...")
            try:
                script_el = page.locator('#__NEXT_DATA__')
                count = await script_el.count()
                logging.info(f"   🕒 [DEBUG] 找到 {count} 個__NEXT_DATA__元素")
                if count > 0:
                    script_content = await script_el.text_content()
                    if script_content:
                        data = json.loads(script_content)
                        logging.info(f"   🕒 [DEBUG] __NEXT_DATA__解析成功，開始查找taken_at...")
                        
                        taken_at = self._find_taken_at(data)
                        if taken_at:
                            result_time = datetime.fromtimestamp(taken_at)
                            
                            # 立即轉換為台北時間
                            from datetime import timezone, timedelta
                            taipei_tz = timezone(timedelta(hours=8))
                            # 時間戳通常是UTC，轉換為台北時間
                            utc_time = result_time.replace(tzinfo=timezone.utc)
                            taipei_time = utc_time.astimezone(taipei_tz).replace(tzinfo=None)
                            
                            logging.info(f"   📅 [DEBUG] __NEXT_DATA__時間解析成功: {result_time} → 台北時間: {taipei_time}")
                            return taipei_time
                        else:
                            logging.info(f"   🕒 [DEBUG] 在__NEXT_DATA__中未找到taken_at")
                    else:
                        logging.info(f"   🕒 [DEBUG] __NEXT_DATA__內容為空")
                        
            except Exception as e:
                logging.info(f"   🕒 [DEBUG] __NEXT_DATA__解析失敗: {e}")
                pass
            
        except Exception as e:
            logging.info(f"   🕒 [DEBUG] 時間提取總體失敗: {e}")
            pass
        
        logging.info(f"   🕒 [DEBUG] 所有時間提取方法都失敗了")
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