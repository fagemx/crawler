"""
混合內容提取器 - 結合計數查詢和 DOM 解析
獲取最完整和準確的貼文數據
"""

import asyncio
import json
import httpx
import urllib.parse
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

import sys
sys.path.append(str(Path(__file__).parent))

from playwright.async_api import async_playwright
from common.config import get_auth_file_path

# 測試貼文
TEST_POST_URL = "https://www.threads.com/@star_shining0828/post/DMyvZJRz5Cz"
TARGET_PK = "3689219480905289907"

class HybridContentExtractor:
    """混合內容提取器 - 計數查詢 + DOM 解析"""
    
    def __init__(self):
        self.counts_captured = False
        self.counts_headers = {}
        self.counts_payload = ""
        self.auth_header = ""
        self.lsd_token = ""
    
    async def intercept_counts_query(self):
        """攔截計數查詢（用於準確的數字數據）"""
        print("📊 攔截計數查詢...")
        
        auth_file_path = get_auth_file_path()
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                storage_state=str(auth_file_path),
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15",
                viewport={"width": 375, "height": 812}
            )
            
            page = await context.new_page()
            
            async def response_handler(response):
                friendly_name = response.request.headers.get("x-fb-friendly-name", "")
                
                if "useBarcelonaBatchedDynamicPostCountsSubscriptionQuery" in friendly_name:
                    try:
                        data = await response.json()
                        if TARGET_PK in json.dumps(data, ensure_ascii=False):
                            print(f"   ✅ 攔截到計數查詢")
                            
                            self.counts_headers = dict(response.request.headers)
                            self.counts_payload = response.request.post_data
                            self.auth_header = self.counts_headers.get("authorization", "")
                            self.lsd_token = self.counts_headers.get("x-fb-lsd", "")
                            
                            self.counts_captured = True
                    except:
                        pass
            
            page.on("response", response_handler)
            await page.goto(TEST_POST_URL, wait_until="networkidle")
            await asyncio.sleep(3)
            await browser.close()
        
        return self.counts_captured
    
    async def get_counts_data(self, target_pk: str) -> Optional[Dict[str, int]]:
        """使用計數查詢獲取準確的數字數據"""
        if not self.counts_captured:
            return None
        
        print(f"   📊 查詢計數數據...")
        
        # 獲取認證
        auth_file_path = get_auth_file_path()
        auth_data = json.loads(auth_file_path.read_text())
        cookies = {cookie['name']: cookie['value'] for cookie in auth_data.get('cookies', [])}
        
        # 準備請求
        headers = self.counts_headers.copy()
        for h in ["host", "content-length", "accept-encoding"]:
            headers.pop(h, None)
        
        if not headers.get("authorization"):
            if 'ig_set_authorization' in cookies:
                auth_value = cookies['ig_set_authorization']
                headers["authorization"] = f"Bearer {auth_value}" if not auth_value.startswith('Bearer') else auth_value
        
        payload = self.counts_payload.replace(TARGET_PK, target_pk) if target_pk != TARGET_PK else self.counts_payload
        
        # 發送請求
        async with httpx.AsyncClient(headers=headers, cookies=cookies, timeout=30.0, http2=True) as client:
            try:
                response = await client.post("https://www.threads.com/graphql/query", data=payload)
                
                if response.status_code == 200:
                    result = response.json()
                    if "data" in result and result["data"] and "data" in result["data"] and "posts" in result["data"]["data"]:
                        posts = result["data"]["data"]["posts"]
                        
                        for post in posts:
                            if post.get("pk") == target_pk:
                                text_info = post.get("text_post_app_info", {}) or {}
                                return {
                                    "like_count": post.get("like_count", 0),
                                    "comment_count": text_info.get("direct_reply_count", 0),
                                    "repost_count": text_info.get("repost_count", 0),
                                    "share_count": text_info.get("reshare_count", 0)
                                }
            except Exception as e:
                print(f"   ❌ 計數查詢失敗: {e}")
        
        return None
    
    async def get_content_and_media_from_dom(self, post_url: str) -> Optional[Dict[str, Any]]:
        """從 DOM 獲取內容和媒體數據（增強版：支援影片攔截）"""
        print(f"   🌐 從 DOM 解析內容和媒體...")
        
        auth_file_path = get_auth_file_path()
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                storage_state=str(auth_file_path),
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15",
                viewport={"width": 375, "height": 812}
            )
            
            page = await context.new_page()
            
            try:
                # 步驟 0: 設置網路攔截器抓取影片響應
                video_urls = set()
                
                async def response_handler(response):
                    try:
                        content_type = response.headers.get("content-type", "")
                        resource_type = response.request.resource_type
                        
                        # 攔截影片資源
                        if (resource_type == "media" or 
                            content_type.startswith("video/") or
                            ".mp4" in response.url.lower() or
                            ".m3u8" in response.url.lower() or
                            ".mpd" in response.url.lower()):
                            video_urls.add(response.url)
                            print(f"      🎥 攔截到影片: {response.url[:80]}...")
                    except Exception as e:
                        pass
                
                page.on("response", response_handler)
                
                # 步驟 1: 載入頁面
                await page.goto(post_url, wait_until="networkidle", timeout=60000)
                await asyncio.sleep(3)
                
                # 步驟 2: 模擬點擊觸發影片載入
                print(f"      🖱️ 嘗試觸發影片載入...")
                try:
                    # 嘗試多種可能的影片觸發器
                    trigger_selectors = [
                        'div[data-testid="media-viewer"]',
                        'video',
                        'div[role="button"][aria-label*="play"]',
                        'div[role="button"][aria-label*="播放"]',
                        '[data-pressable-container] div[style*="video"]',
                        'div[style*="cursor: pointer"]'
                    ]
                    
                    for selector in trigger_selectors:
                        try:
                            elements = page.locator(selector)
                            count = await elements.count()
                            if count > 0:
                                await elements.first.click(timeout=3000)
                                print(f"      ✅ 點擊觸發器: {selector}")
                                await asyncio.sleep(2)  # 等待影片載入
                                break
                        except:
                            continue
                            
                except Exception as e:
                    print(f"      ⚠️ 觸發影片載入失敗: {e}")
                
                # 給更多時間讓影片載入
                await asyncio.sleep(3)
                
                # 提取用戶名（從 URL 中直接解析，更準確）
                username = ""
                try:
                    # 從 URL 中提取用戶名
                    import re
                    url_match = re.search(r'/@([^/]+)/', post_url)
                    if url_match:
                        username = url_match.group(1)
                    else:
                        # 備用方案：從 DOM 中尋找
                        username_elem = await page.locator('a[href*="/@"]').first.get_attribute("href")
                        if username_elem:
                            username = username_elem.split("/@")[1].split("/")[0]
                except:
                    pass
                
                # 提取內容文字（基於調試結果）
                content = ""
                try:
                    # 使用調試中發現的有效選擇器
                    content_selectors = [
                        'div[data-pressable-container] span',  # 調試中找到 305 個元素
                        '[data-testid="thread-text"]',
                        'article div[dir="auto"]',
                        'div[role="article"] div[dir="auto"]',
                        'span[style*="text-overflow"]'
                    ]
                    
                    for selector in content_selectors:
                        try:
                            elements = page.locator(selector)
                            count = await elements.count()
                            
                            if count > 0:
                                # 尋找包含主要內容的元素（長度超過10字符且不是數字）
                                for i in range(min(count, 20)):  # 檢查前20個元素
                                    try:
                                        text = await elements.nth(i).inner_text()
                                        if (text and len(text.strip()) > 10 and 
                                            not text.strip().isdigit() and
                                            "小時" not in text and  # 排除時間
                                            "分鐘" not in text and
                                            not text.startswith("@")):  # 排除用戶名
                                            content = text.strip()
                                            break
                                    except:
                                        continue
                                
                                if content:
                                    break
                        except:
                            continue
                except:
                    pass
                
                # 步驟 4: 提取圖片（過濾頭像和 UI 小圖）
                images = []
                try:
                    print(f"      🖼️ 提取圖片（過濾頭像）...")
                    img_elements = page.locator('img')
                    img_count = await img_elements.count()
                    
                    for i in range(min(img_count, 50)):  # 檢查更多圖片但過濾
                        try:
                            img_elem = img_elements.nth(i)
                            img_src = await img_elem.get_attribute("src")
                            
                            if not img_src or not ("fbcdn" in img_src or "cdninstagram" in img_src):
                                continue
                            
                            # 排除界面元素
                            if ("rsrc.php" in img_src or 
                                "static.cdninstagram.com" in img_src):
                                continue
                            
                            # 檢查圖片尺寸（過濾頭像）
                            try:
                                width = int(await img_elem.get_attribute("width") or 0)
                                height = int(await img_elem.get_attribute("height") or 0)
                                max_size = max(width, height)
                                
                                # 只保留尺寸 > 150x150 的圖片（排除頭像）
                                if max_size > 150 and img_src not in images:
                                    images.append(img_src)
                                    print(f"         📸 圖片 {len(images)}: {max_size}px")
                            except:
                                # 如果無法獲取尺寸，按 URL 特徵判斷
                                if ("t51.2885-15" in img_src or  # 貼文媒體
                                    "scontent" in img_src) and img_src not in images:
                                    images.append(img_src)
                        except:
                            continue
                            
                    print(f"      ✅ 找到 {len(images)} 個有效圖片")
                except Exception as e:
                    print(f"      ❌ 圖片提取失敗: {e}")
                
                # 步驟 3: 提取影片（結合網路攔截和 DOM）
                print(f"      🎥 提取影片...")
                videos = list(video_urls)  # 從網路攔截獲取的影片 URL
                
                try:
                    # 檢查影片指示器
                    video_error_text = await page.locator('text="很抱歉，播放此影片時發生問題"').count()
                    if video_error_text > 0:
                        print(f"      🎥 檢測到影片載入錯誤訊息")
                    
                    # 從 DOM 中提取 video 標籤（包含 poster）
                    video_elements = page.locator('video')
                    video_count = await video_elements.count()
                    
                    if video_count > 0:
                        print(f"      🎥 找到 {video_count} 個 video 標籤")
                        
                        for i in range(video_count):
                            try:
                                video_elem = video_elements.nth(i)
                                
                                # 獲取各種可能的影片 URL
                                src = await video_elem.get_attribute("src")
                                data_src = await video_elem.get_attribute("data-src")
                                poster = await video_elem.get_attribute("poster")
                                
                                if src and src not in videos:
                                    videos.append(src)
                                    print(f"         🎬 src: {src[:60]}...")
                                
                                if data_src and data_src not in videos:
                                    videos.append(data_src)
                                    print(f"         🎬 data-src: {data_src[:60]}...")
                                
                                if poster and poster not in videos:
                                    videos.append(f"POSTER::{poster}")
                                    print(f"         🖼️ poster: {poster[:60]}...")
                                
                                # 檢查 source 子元素
                                sources = video_elem.locator('source')
                                source_count = await sources.count()
                                for j in range(source_count):
                                    source_src = await sources.nth(j).get_attribute("src")
                                    if source_src and source_src not in videos:
                                        videos.append(source_src)
                                        print(f"         🎬 source: {source_src[:60]}...")
                            except:
                                continue
                    
                    # 統計結果
                    actual_videos = [v for v in videos if not v.startswith("POSTER::")]
                    poster_videos = [v for v in videos if v.startswith("POSTER::")]
                    
                    print(f"      ✅ 網路攔截: {len(video_urls)} 個影片 URL")
                    print(f"      ✅ DOM 影片: {len(actual_videos)} 個")
                    print(f"      ✅ 封面圖: {len(poster_videos)} 個")
                    
                    # 如果有影片指示器但沒有找到影片，標記
                    if video_error_text > 0 and not actual_videos:
                        videos.append("VIDEO_DETECTED_BUT_FAILED_TO_LOAD")
                        
                except Exception as e:
                    print(f"      ❌ 影片提取失敗: {e}")
                
                await browser.close()
                
                return {
                    "username": username,
                    "content": content,
                    "images": images,
                    "videos": videos
                }
            
            except Exception as e:
                print(f"   ❌ DOM 解析失敗: {e}")
                await browser.close()
                return None
    
    def extract_code_from_url(self, url: str) -> str:
        """從 URL 提取貼文代碼"""
        match = re.search(r'/post/([A-Za-z0-9_-]+)', url)
        return match.group(1) if match else ""
    
    async def extract_complete_post(self, post_url: str, target_pk: str = TARGET_PK) -> Optional[Dict[str, Any]]:
        """提取完整的貼文數據（計數 + 內容 + 媒體）"""
        print(f"🎯 提取完整貼文數據: {post_url}")
        
        # 第一步：獲取準確的計數數據
        counts_data = await self.get_counts_data(target_pk)
        if not counts_data:
            print(f"   ⚠️ 無法獲取計數數據，使用預設值")
            counts_data = {"like_count": 0, "comment_count": 0, "repost_count": 0, "share_count": 0}
        else:
            print(f"   ✅ 計數數據: 讚{counts_data['like_count']}, 留言{counts_data['comment_count']}, 轉發{counts_data['repost_count']}, 分享{counts_data['share_count']}")
        
        # 第二步：獲取內容和媒體數據
        content_data = await self.get_content_and_media_from_dom(post_url)
        if not content_data:
            print(f"   ⚠️ 無法獲取內容數據，使用預設值")
            content_data = {"username": "", "content": "", "images": [], "videos": []}
        else:
            print(f"   ✅ 內容數據: @{content_data['username']}, {len(content_data['content'])}字符, {len(content_data['images'])}圖片, {len(content_data['videos'])}影片")
        
        # 合併數據
        code = self.extract_code_from_url(post_url)
        
        result = {
            "pk": target_pk,
            "code": code,
            "username": content_data["username"],
            "content": content_data["content"],
            "like_count": counts_data["like_count"],
            "comment_count": counts_data["comment_count"],
            "repost_count": counts_data["repost_count"],
            "share_count": counts_data["share_count"],
            "images": content_data["images"],
            "videos": content_data["videos"],
            "url": post_url,
            "extracted_at": datetime.now().isoformat(),
            "extraction_method": "hybrid_counts_and_dom"
        }
        
        # 顯示最終結果
        print(f"\n📋 最終結果:")
        print(f"   📄 PK: {result['pk']}")
        print(f"   👤 用戶: @{result['username']}")
        print(f"   📝 內容: {len(result['content'])} 字符")
        print(f"   👍 讚數: {result['like_count']}")
        print(f"   💬 留言: {result['comment_count']}")
        print(f"   🔄 轉發: {result['repost_count']}")
        print(f"   📤 分享: {result['share_count']}")
        print(f"   🖼️ 圖片: {len(result['images'])} 個")
        print(f"   🎥 影片: {len(result['videos'])} 個")
        
        if result['content']:
            print(f"   📄 內容預覽: {result['content'][:100]}...")
        
        # 保存結果
        result_file = Path(f"hybrid_extraction_result_{datetime.now().strftime('%H%M%S')}.json")
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"   📁 完整結果已保存: {result_file}")
        
        return result

async def main():
    """主函數"""
    print("🚀 混合內容提取器 - 計數查詢 + DOM 解析")
    
    auth_file = get_auth_file_path()
    if not auth_file.exists():
        print(f"❌ 認證檔案 {auth_file} 不存在。請先執行 save_auth.py。")
        return
    
    extractor = HybridContentExtractor()
    
    # 第一步：攔截計數查詢
    print(f"\n📡 第一步：攔截計數查詢...")
    captured = await extractor.intercept_counts_query()
    
    if not captured:
        print(f"   ⚠️ 未攔截到計數查詢，將只使用 DOM 解析")
    
    # 第二步：提取完整數據
    print(f"\n🎯 第二步：混合提取...")
    result = await extractor.extract_complete_post(TEST_POST_URL, TARGET_PK)
    
    if result:
        print(f"\n🎉 混合提取成功！")
        print(f"💡 這個方法結合了兩種技術的優勢:")
        print(f"   ✅ 計數查詢: 準確的數字數據")
        print(f"   ✅ DOM 解析: 完整的內容和媒體")
        print(f"   ✅ 穩定可靠: 即使一個方法失敗，另一個可以補足")
        print(f"\n🔧 現在可以將此混合方法整合到主爬蟲中！")
    else:
        print(f"\n😞 混合提取失敗")

if __name__ == "__main__":
    asyncio.run(main())