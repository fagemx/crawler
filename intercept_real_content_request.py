"""
用 Playwright 攔截真實的內容查詢請求，獲取 doc_id 和 Authorization header
"""

import asyncio
import json
import httpx
import urllib.parse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

import sys
sys.path.append(str(Path(__file__).parent))

from playwright.async_api import async_playwright
from common.config import get_auth_file_path

# 測試貼文
TEST_POST_URL = "https://www.threads.com/@star_shining0828/post/DMyvZJRz5Cz"
TARGET_PK = "3689219480905289907"

class ContentQueryInterceptor:
    """攔截並複製真實的內容查詢請求"""
    
    def __init__(self):
        self.doc_id = None
        self.auth_header = None
        self.lsd_token = None
        self.full_headers = {}
        self.full_payload = None
        self.captured = False
    
    async def intercept_real_request(self):
        """攔截真實的內容查詢請求"""
        print("🔍 攔截真實的內容查詢請求...")
        
        auth_file_path = get_auth_file_path()
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)  # 設為 False 便於觀察
            context = await browser.new_context(
                storage_state=str(auth_file_path),
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15",
                viewport={"width": 375, "height": 812},
                locale="zh-TW"
            )
            
            page = await context.new_page()
            
            async def response_handler(response):
                url = response.url.lower()
                friendly_name = response.request.headers.get("x-fb-friendly-name", "")
                
                # 尋找內容相關的查詢
                if ("/graphql/query" in url and 
                    ("BarcelonaPostPageContentQuery" in friendly_name or 
                     "BarcelonaPostPageRefetchableDirectQuery" in friendly_name)):
                    
                    print(f"   🎯 攔截到內容查詢: {friendly_name}")
                    
                    # 提取 doc_id
                    post_data = response.request.post_data
                    if post_data and "doc_id=" in post_data:
                        self.doc_id = post_data.split("doc_id=")[1].split("&")[0]
                        print(f"      📋 doc_id: {self.doc_id}")
                    
                    # 提取 Authorization header（多種可能的名稱）
                    auth = (response.request.headers.get("authorization") or 
                           response.request.headers.get("Authorization") or
                           response.request.headers.get("x-ig-authorization"))
                    if auth:
                        self.auth_header = auth
                        print(f"      🔑 Authorization: {auth[:20]}...")
                    else:
                        print(f"      ⚠️ 未找到 Authorization header")
                        # 列出所有 headers 用於調試
                        auth_related = {k: v for k, v in response.request.headers.items() 
                                      if 'auth' in k.lower() or 'bearer' in str(v).lower()}
                        if auth_related:
                            print(f"      📋 認證相關 headers: {list(auth_related.keys())}")
                    
                    # 提取 LSD token
                    lsd_from_header = response.request.headers.get("x-fb-lsd")
                    if lsd_from_header:
                        self.lsd_token = lsd_from_header
                        print(f"      🎫 LSD (header): {lsd_from_header[:10]}...")
                    
                    # 從 POST 數據中提取 LSD
                    if post_data and "lsd=" in post_data:
                        lsd_from_data = None
                        for part in post_data.split('&'):
                            if part.startswith('lsd='):
                                lsd_from_data = urllib.parse.unquote(part.split('=', 1)[1])
                                break
                        if lsd_from_data:
                            self.lsd_token = lsd_from_data
                            print(f"      🎫 LSD (data): {lsd_from_data[:10]}...")
                    
                    # 複製完整 headers
                    self.full_headers = dict(response.request.headers)
                    self.full_payload = post_data
                    
                    print(f"      ✅ 成功攔截完整請求信息")
                    self.captured = True
            
            page.on("response", response_handler)
            
            # 導航到貼文頁面
            print(f"   🌐 導航到: {TEST_POST_URL}")
            await page.goto(TEST_POST_URL, wait_until="networkidle", timeout=60000)
            
            # 等待攔截
            await asyncio.sleep(5)
            
            # 如果還沒攔截到，嘗試刷新頁面
            if not self.captured:
                print(f"   🔄 未攔截到，嘗試刷新頁面...")
                await page.reload(wait_until="networkidle")
                await asyncio.sleep(5)
            
            # 嘗試滾動觸發更多請求
            if not self.captured:
                print(f"   📜 嘗試滾動觸發請求...")
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(3)
            
            await browser.close()
        
        return self.captured
    
    async def get_auth_from_cookies(self, cookies: dict) -> Optional[str]:
        """從 cookies 中構建 Authorization header"""
        # 方法1: 從 ig_set_authorization cookie 獲取
        if 'ig_set_authorization' in cookies:
            auth_value = cookies['ig_set_authorization']
            if auth_value and not auth_value.startswith('Bearer'):
                return f"Bearer {auth_value}"
            return auth_value
        
        # 方法2: 從 sessionid 構建（某些情況下可用）
        if 'sessionid' in cookies:
            sessionid = cookies['sessionid']
            return f"Bearer IGT:2:{sessionid}"
        
        return None
    
    async def test_intercepted_request(self):
        """使用攔截到的信息測試請求"""
        if not self.captured:
            print("❌ 沒有攔截到有效的請求信息")
            return False
        
        print(f"\n🧪 使用攔截到的信息測試請求...")
        print(f"   📋 doc_id: {self.doc_id}")
        print(f"   🔑 有 Authorization: {'是' if self.auth_header else '否'}")
        print(f"   🎫 LSD token: {self.lsd_token[:10] if self.lsd_token else '無'}...")
        
        # 獲取 cookies
        auth_file_path = get_auth_file_path()
        auth_data = json.loads(auth_file_path.read_text())
        cookies = {cookie['name']: cookie['value'] for cookie in auth_data.get('cookies', [])}
        
        # 如果沒有攔截到 Authorization，嘗試從 cookies 獲取
        if not self.auth_header:
            print(f"   🔍 嘗試從 cookies 構建 Authorization...")
            self.auth_header = await self.get_auth_from_cookies(cookies)
            if self.auth_header:
                print(f"   ✅ 從 cookies 獲取到 Authorization: {self.auth_header[:20]}...")
            else:
                print(f"   ❌ 無法從 cookies 獲取 Authorization")
                print(f"   🍪 可用 cookies: {list(cookies.keys())}")
        
        # 構建變數（按照指導的格式）
        variables = {
            "postID_pk": TARGET_PK,
            "withShallowTree": False,
            "includePromotedPosts": False
        }
        
        # 構建 payload
        payload_data = {
            "lsd": self.lsd_token,
            "doc_id": self.doc_id,
            "variables": json.dumps(variables, separators=(",", ":"))
        }
        payload = urllib.parse.urlencode(payload_data)
        
        # 構建 headers（複製攔截到的重要 headers）
        headers = {
            "User-Agent": self.full_headers.get("user-agent", "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15"),
            "Content-Type": "application/x-www-form-urlencoded",
            "X-FB-LSD": self.lsd_token,
            "X-IG-App-ID": "238260118697367",
            "Referer": TEST_POST_URL,
            "Origin": "https://www.threads.com",
            "Accept": "*/*",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        }
        
        # 只在有 Authorization 時才添加
        if self.auth_header:
            headers["Authorization"] = self.auth_header
        else:
            print(f"   ⚠️ 警告：沒有 Authorization header，可能會導致 403 錯誤")
        
        # 複製其他可能重要的 headers
        for key in ["x-ig-www-claim", "x-requested-with", "sec-fetch-dest", "sec-fetch-mode", "sec-fetch-site"]:
            if key in self.full_headers:
                headers[key] = self.full_headers[key]
        
        # 發送請求
        async with httpx.AsyncClient(cookies=cookies, timeout=30.0, http2=True) as client:
            try:
                response = await client.post(
                    "https://www.threads.com/graphql/query",
                    data=payload,
                    headers=headers
                )
                
                print(f"   📡 HTTP {response.status_code}")
                
                if response.status_code == 200:
                    try:
                        result = response.json()
                        
                        if "errors" in result:
                            errors = result["errors"]
                            print(f"   ❌ GraphQL 錯誤: {errors[:1]}")
                            return False
                        
                        if "data" in result and result["data"]:
                            data = result["data"]
                            
                            if "media" in data and data["media"]:
                                # 成功！按照指導的結構解析
                                media = data["media"]
                                print(f"   🎉 成功獲取媒體數據！")
                                
                                # 提取關鍵信息
                                pk = media.get("pk", "")
                                typename = media.get("__typename", "")
                                
                                # 內容
                                caption = media.get("caption", {}) or {}
                                content_text = caption.get("text", "") if caption else ""
                                
                                # 計數
                                like_count = media.get("like_count", 0)
                                text_info = media.get("text_post_app_info", {}) or {}
                                comment_count = text_info.get("direct_reply_count", 0)
                                repost_count = text_info.get("repost_count", 0)
                                share_count = text_info.get("reshare_count", 0)
                                
                                # 媒體
                                images = []
                                videos = []
                                
                                # 單一圖片/影片
                                if "image_versions2" in media and media["image_versions2"]:
                                    candidates = media["image_versions2"].get("candidates", [])
                                    if candidates:
                                        best_image = max(candidates, key=lambda c: c.get("width", 0))
                                        images.append(best_image.get("url", ""))
                                
                                if "video_versions" in media and media["video_versions"]:
                                    videos.append(media["video_versions"][0].get("url", ""))
                                
                                # 輪播媒體
                                if "carousel_media" in media and media["carousel_media"]:
                                    for item in media["carousel_media"]:
                                        if "image_versions2" in item and item["image_versions2"]:
                                            candidates = item["image_versions2"].get("candidates", [])
                                            if candidates:
                                                best_image = max(candidates, key=lambda c: c.get("width", 0))
                                                images.append(best_image.get("url", ""))
                                        if "video_versions" in item and item["video_versions"]:
                                            videos.append(item["video_versions"][0].get("url", ""))
                                
                                print(f"      📄 PK: {pk}")
                                print(f"      🏷️ 類型: {typename}")
                                print(f"      📝 內容長度: {len(content_text)} 字符")
                                print(f"      👍 讚數: {like_count}")
                                print(f"      💬 留言: {comment_count}")
                                print(f"      🔄 轉發: {repost_count}")
                                print(f"      📤 分享: {share_count}")
                                print(f"      🖼️ 圖片: {len(images)} 個")
                                print(f"      🎥 影片: {len(videos)} 個")
                                
                                if content_text:
                                    print(f"      📄 內容預覽: {content_text[:100]}...")
                                
                                # 保存成功的配置
                                config_file = Path(f"working_content_config_{datetime.now().strftime('%H%M%S')}.json")
                                config_data = {
                                    "doc_id": self.doc_id,
                                    "endpoint": "https://www.threads.com/graphql/query",
                                    "variables_format": {
                                        "postID_pk": "PK_HERE",
                                        "withShallowTree": False,
                                        "includePromotedPosts": False
                                    },
                                    "required_headers": {
                                        "Authorization": self.auth_header,
                                        "X-FB-LSD": "LSD_TOKEN_HERE",
                                        "X-IG-App-ID": "238260118697367",
                                        "Content-Type": "application/x-www-form-urlencoded"
                                    },
                                    "test_result": {
                                        "pk": pk,
                                        "content": content_text,
                                        "like_count": like_count,
                                        "comment_count": comment_count,
                                        "repost_count": repost_count,
                                        "share_count": share_count,
                                        "images_count": len(images),
                                        "videos_count": len(videos)
                                    },
                                    "full_media_data": media
                                }
                                
                                with open(config_file, 'w', encoding='utf-8') as f:
                                    json.dump(config_data, f, indent=2, ensure_ascii=False)
                                
                                print(f"      📁 已保存工作配置到: {config_file}")
                                return True
                            
                            else:
                                print(f"   ⚠️ 數據結構不符預期，data 鍵: {list(data.keys())}")
                                if "data" in data:
                                    print(f"   📋 內層結構: {list(data['data'].keys()) if data['data'] else 'null'}")
                        else:
                            print(f"   ❌ 無效的響應結構")
                        
                        return False
                    
                    except Exception as e:
                        print(f"   ❌ 解析響應失敗: {e}")
                        print(f"   📄 響應片段: {response.text[:300]}...")
                        return False
                
                elif response.status_code == 403:
                    print(f"   ❌ 403 錯誤，可能原因:")
                    print(f"      1. Authorization header 不正確")
                    print(f"      2. doc_id 已過期")
                    print(f"      3. 缺少其他必要 headers")
                    
                    # 顯示響應片段用於診斷
                    response_text = response.text[:500]
                    if "login_required" in response_text:
                        print(f"      💡 響應提示需要登入")
                    elif "www_claims" in response_text:
                        print(f"      💡 響應提示 www_claims 問題")
                    
                    print(f"   📄 響應片段: {response_text}...")
                    return False
                
                else:
                    print(f"   ❌ HTTP 錯誤: {response.status_code}")
                    print(f"   📄 響應: {response.text[:200]}...")
                    return False
            
            except Exception as e:
                print(f"   ❌ 請求失敗: {e}")
                return False

async def main():
    """主函數"""
    print("🚀 攔截並測試真實的內容查詢...")
    
    auth_file = get_auth_file_path()
    if not auth_file.exists():
        print(f"❌ 認證檔案 {auth_file} 不存在。請先執行 save_auth.py。")
        return
    
    interceptor = ContentQueryInterceptor()
    
    # 第一步：攔截真實請求
    captured = await interceptor.intercept_real_request()
    
    if not captured:
        print(f"\n😞 未能攔截到內容查詢請求")
        print(f"💡 可能需要:")
        print(f"   1. 手動觸發內容加載")
        print(f"   2. 嘗試不同的貼文 URL")
        print(f"   3. 檢查網絡連接")
        return
    
    # 第二步：使用攔截的信息測試
    success = await interceptor.test_intercepted_request()
    
    if success:
        print(f"\n🎉 內容查詢測試成功！")
        print(f"💡 可以將這個配置整合到主要爬蟲中")
        print(f"🔧 關鍵要素:")
        print(f"   - doc_id: {interceptor.doc_id}")
        print(f"   - Authorization header: 必需")
        print(f"   - 變數格式: postID_pk, withShallowTree: False")
        print(f"   - endpoint: /graphql/query")
    else:
        print(f"\n😞 內容查詢測試失敗")
        print(f"💡 可能需要進一步調試 headers 或變數格式")

if __name__ == "__main__":
    asyncio.run(main())