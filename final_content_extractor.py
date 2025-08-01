"""
最終完整的內容提取器
結合計數查詢和內容查詢，獲取完整的貼文數據
"""

import asyncio
import json
import httpx
import urllib.parse
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

class FinalContentExtractor:
    """最終完整的內容提取器"""
    
    def __init__(self):
        self.counts_query_captured = False
        self.counts_headers = {}
        self.counts_payload = ""
        self.counts_doc_id = ""
        
        self.auth_header = ""
        self.lsd_token = ""
    
    async def intercept_counts_query(self):
        """攔截計數查詢（已知可以獲取目標貼文）"""
        print("🎯 攔截計數查詢...")
        
        auth_file_path = get_auth_file_path()
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context(
                storage_state=str(auth_file_path),
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15",
                viewport={"width": 375, "height": 812},
                locale="zh-TW"
            )
            
            page = await context.new_page()
            
            async def response_handler(response):
                friendly_name = response.request.headers.get("x-fb-friendly-name", "")
                
                # 攔截計數查詢
                if "useBarcelonaBatchedDynamicPostCountsSubscriptionQuery" in friendly_name:
                    print(f"   🎯 攔截到計數查詢: {friendly_name}")
                    
                    # 檢查是否包含目標貼文
                    try:
                        data = await response.json()
                        data_str = json.dumps(data, ensure_ascii=False)
                        
                        if TARGET_PK in data_str:
                            print(f"   ✅ 確認包含目標貼文！")
                            
                            # 完整保存請求信息
                            self.counts_headers = dict(response.request.headers)
                            self.counts_payload = response.request.post_data
                            
                            if self.counts_payload and "doc_id=" in self.counts_payload:
                                self.counts_doc_id = self.counts_payload.split("doc_id=")[1].split("&")[0]
                            
                            self.auth_header = self.counts_headers.get("authorization", "")
                            self.lsd_token = self.counts_headers.get("x-fb-lsd", "")
                            
                            print(f"   📋 doc_id: {self.counts_doc_id}")
                            print(f"   🔑 Authorization: {'是' if self.auth_header else '否'}")
                            print(f"   🎫 LSD: {self.lsd_token[:10] if self.lsd_token else '無'}...")
                            
                            # 打印完整請求信息
                            print("\n======= COUNTS QUERY RAW REQUEST =======")
                            print("PAYLOAD:")
                            print(self.counts_payload)
                            print("\nKEY HEADERS:")
                            for key in ["x-fb-lsd", "x-ig-app-id", "authorization", "x-csrftoken", "x-asbd-id"]:
                                if key in self.counts_headers:
                                    print(f"{key}: {self.counts_headers[key]}")
                            print("=========================================\n")
                            
                            self.counts_query_captured = True
                        else:
                            print(f"   ⏭️ 不包含目標貼文")
                    except Exception as e:
                        print(f"   ❌ 解析響應失敗: {e}")
            
            page.on("response", response_handler)
            
            # 導航到頁面
            print(f"   🌐 導航到: {TEST_POST_URL}")
            await page.goto(TEST_POST_URL, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(5)
            
            # 如果沒攔截到，嘗試滾動
            if not self.counts_query_captured:
                print(f"   📜 嘗試滾動觸發更多查詢...")
                await page.evaluate("window.scrollTo(0, 300)")
                await asyncio.sleep(3)
            
            await browser.close()
        
        return self.counts_query_captured
    
    async def get_auth_from_cookies(self) -> Optional[str]:
        """從 cookies 獲取 Authorization"""
        auth_file_path = get_auth_file_path()
        auth_data = json.loads(auth_file_path.read_text())
        cookies = {cookie['name']: cookie['value'] for cookie in auth_data.get('cookies', [])}
        
        if 'ig_set_authorization' in cookies:
            auth_value = cookies['ig_set_authorization']
            if auth_value and not auth_value.startswith('Bearer'):
                return f"Bearer {auth_value}"
            return auth_value
        
        if 'sessionid' in cookies:
            sessionid = cookies['sessionid']
            return f"Bearer IGT:2:{sessionid}"
        
        return None
    
    async def extract_complete_post_data(self, target_pk: str = TARGET_PK) -> Optional[Dict[str, Any]]:
        """使用攔截到的計數查詢提取完整貼文數據"""
        if not self.counts_query_captured:
            print("❌ 沒有攔截到計數查詢")
            return None
        
        print(f"\n🎬 使用計數查詢提取完整數據...")
        
        # 獲取 cookies
        auth_file_path = get_auth_file_path()
        auth_data = json.loads(auth_file_path.read_text())
        cookies = {cookie['name']: cookie['value'] for cookie in auth_data.get('cookies', [])}
        
        # 準備 headers（完全複製）
        headers = self.counts_headers.copy()
        for header_to_remove in ["host", "content-length", "accept-encoding"]:
            headers.pop(header_to_remove, None)
        
        # 確保有 Authorization
        if not headers.get("authorization"):
            auth_from_cookies = await self.get_auth_from_cookies()
            if auth_from_cookies:
                headers["authorization"] = auth_from_cookies
                print(f"   ✅ 從 cookies 補充 Authorization")
        
        # 準備 payload（完全複製，只替換 PK）
        payload = self.counts_payload
        if target_pk != TARGET_PK:
            payload = payload.replace(TARGET_PK, target_pk)
            print(f"   🔄 替換 PK: {TARGET_PK} → {target_pk}")
        
        # 發送請求
        async with httpx.AsyncClient(
            headers=headers,
            cookies=cookies,
            timeout=30.0,
            follow_redirects=True,
            http2=True
        ) as client:
            try:
                response = await client.post(
                    "https://www.threads.com/graphql/query",
                    data=payload
                )
                
                print(f"   📡 HTTP {response.status_code}")
                
                if response.status_code == 200:
                    try:
                        result = response.json()
                        
                        if "errors" in result:
                            print(f"   ❌ GraphQL 錯誤: {result['errors'][:1]}")
                            return None
                        
                        if "data" in result and result["data"]:
                            data = result["data"]
                            
                            # 解析 batch posts 結構
                            if "data" in data and "posts" in data["data"]:
                                posts = data["data"]["posts"]
                                print(f"   📝 找到 {len(posts)} 個貼文")
                                
                                # 找到目標貼文
                                target_post = None
                                for post in posts:
                                    if post.get("pk") == target_pk:
                                        target_post = post
                                        break
                                
                                if target_post:
                                    print(f"   🎯 找到目標貼文！")
                                    return await self._extract_post_details(target_post)
                                else:
                                    print(f"   ❌ 未找到目標貼文 (PK: {target_pk})")
                                    found_pks = [p.get("pk", "unknown") for p in posts[:3]]
                                    print(f"   📋 找到的 PK: {found_pks}")
                            else:
                                print(f"   ❌ 意外的數據結構: {list(data.keys())}")
                        else:
                            print(f"   ❌ 無效響應")
                        
                        return None
                    
                    except Exception as e:
                        print(f"   ❌ 解析響應失敗: {e}")
                        return None
                
                else:
                    print(f"   ❌ HTTP 錯誤: {response.status_code}")
                    return None
            
            except Exception as e:
                print(f"   ❌ 請求失敗: {e}")
                return None
    
    async def _extract_post_details(self, post: Dict[str, Any]) -> Dict[str, Any]:
        """從貼文數據中提取詳細信息"""
        # 基本信息
        pk = post.get("pk", "")
        code = post.get("code", "")
        
        # 內容
        caption = post.get("caption", {}) or {}
        content = caption.get("text", "") if caption else ""
        
        # 計數
        like_count = post.get("like_count", 0)
        text_info = post.get("text_post_app_info", {}) or {}
        comment_count = text_info.get("direct_reply_count", 0)
        repost_count = text_info.get("repost_count", 0)
        share_count = text_info.get("reshare_count", 0)
        
        # 用戶信息
        user = post.get("user", {}) or {}
        username = user.get("username", "")
        
        # 媒體信息
        images = []
        videos = []
        
        # 單一圖片/影片
        if "image_versions2" in post and post["image_versions2"]:
            candidates = post["image_versions2"].get("candidates", [])
            if candidates:
                # 取所有解析度的圖片
                for candidate in candidates:
                    url = candidate.get("url", "")
                    if url and url not in images:
                        images.append(url)
        
        if "video_versions" in post and post["video_versions"]:
            for video in post["video_versions"]:
                url = video.get("url", "")
                if url and url not in videos:
                    videos.append(url)
        
        # 輪播媒體
        if "carousel_media" in post and post["carousel_media"]:
            for item in post["carousel_media"]:
                if "image_versions2" in item and item["image_versions2"]:
                    candidates = item["image_versions2"].get("candidates", [])
                    for candidate in candidates:
                        url = candidate.get("url", "")
                        if url and url not in images:
                            images.append(url)
                
                if "video_versions" in item and item["video_versions"]:
                    for video in item["video_versions"]:
                        url = video.get("url", "")
                        if url and url not in videos:
                            videos.append(url)
        
        # 構建結果
        result = {
            "pk": pk,
            "code": code,
            "username": username,
            "content": content,
            "like_count": like_count,
            "comment_count": comment_count,
            "repost_count": repost_count,
            "share_count": share_count,
            "images": images,
            "videos": videos,
            "url": f"https://www.threads.com/@{username}/post/{code}" if username and code else "",
            "extracted_at": datetime.now().isoformat(),
            "raw_post_data": post
        }
        
        # 顯示結果
        print(f"      📄 PK: {pk}")
        print(f"      👤 用戶: @{username}")
        print(f"      📝 內容: {len(content)} 字符")
        print(f"      👍 讚數: {like_count}")
        print(f"      💬 留言: {comment_count}")
        print(f"      🔄 轉發: {repost_count}")
        print(f"      📤 分享: {share_count}")
        print(f"      🖼️ 圖片: {len(images)} 個")
        print(f"      🎥 影片: {len(videos)} 個")
        
        if content:
            print(f"      📄 內容預覽: {content[:100]}...")
        
        # 保存結果
        result_file = Path(f"final_extraction_result_{datetime.now().strftime('%H%M%S')}.json")
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"      📁 完整結果已保存: {result_file}")
        
        return result

async def main():
    """主函數"""
    print("🚀 最終完整的內容提取器")
    
    auth_file = get_auth_file_path()
    if not auth_file.exists():
        print(f"❌ 認證檔案 {auth_file} 不存在。請先執行 save_auth.py。")
        return
    
    extractor = FinalContentExtractor()
    
    # 第一步：攔截計數查詢
    print(f"\n📡 第一步：攔截計數查詢...")
    captured = await extractor.intercept_counts_query()
    
    if not captured:
        print(f"\n😞 未能攔截到計數查詢")
        return
    
    # 第二步：提取完整數據
    print(f"\n🎯 第二步：提取完整數據...")
    result = await extractor.extract_complete_post_data()
    
    if result:
        print(f"\n🎉 提取成功！")
        print(f"💡 這個方法可以:")
        print(f"   ✅ 獲取完整的計數數據 (讚數、留言、轉發、分享)")
        print(f"   ✅ 獲取完整的內容文字")
        print(f"   ✅ 獲取所有圖片和影片 URL")
        print(f"   ✅ 獲取用戶信息")
        print(f"   ✅ 使用穩定的計數查詢API")
        print(f"\n🔧 現在可以將此方法整合到主爬蟲中！")
    else:
        print(f"\n😞 提取失敗")

if __name__ == "__main__":
    asyncio.run(main())