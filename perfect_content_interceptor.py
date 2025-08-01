"""
完美的內容攔截器 - 完全複製真實請求，不做任何"簡化"
按照用戶指導實現最穩定的方法
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

class PerfectContentInterceptor:
    """完美攔截器 - 完全複製真實請求"""
    
    def __init__(self):
        self.raw_headers = {}
        self.raw_payload = ""
        self.doc_id = ""
        self.auth_header = ""
        self.captured = False
    
    async def intercept_and_copy_everything(self):
        """攔截並完整複製所有請求信息"""
        print("🎯 攔截並完整複製真實請求...")
        
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
                url = response.url.lower()
                friendly_name = response.request.headers.get("x-fb-friendly-name", "")
                
                # 攔截內容查詢 - 尋找主貼文查詢而非留言查詢
                if "/graphql/query" in url:
                    print(f"   📡 GraphQL 查詢: {friendly_name}")
                    
                    # 檢查 x-root-field-name 來確定查詢類型
                    root_field = response.request.headers.get("x-root-field-name", "")
                    
                    # 優先攔截主貼文查詢，避免留言查詢
                    is_main_post_query = (
                        "BarcelonaPostPageContentQuery" in friendly_name or
                        ("BarcelonaPostPageRefetchableDirectQuery" in friendly_name and 
                         "replies" not in root_field and "media_id__replies" not in root_field)
                    )
                    
                    if is_main_post_query:
                        print(f"   🎯 攔截到主貼文查詢: {friendly_name}")
                        print(f"   🔍 Root field: {root_field}")
                        
                        # === 完整列印 RAW REQUEST ===
                        print("\n======= RAW POST PAYLOAD =======")
                        print(response.request.post_data)
                        print("\n======= RAW HEADERS =======")
                        for k, v in response.request.headers.items():
                            print(f"{k}: {v}")
                        print("===============================\n")
                        
                        # 完整保存（不做任何修改）
                        self.raw_headers = dict(response.request.headers)
                        self.raw_payload = response.request.post_data
                        
                        # 提取關鍵信息用於記錄
                        if self.raw_payload and "doc_id=" in self.raw_payload:
                            self.doc_id = self.raw_payload.split("doc_id=")[1].split("&")[0]
                        
                        self.auth_header = self.raw_headers.get("authorization", "")
                        
                        print(f"   📋 doc_id: {self.doc_id}")
                        print(f"   🔑 Authorization: {'是' if self.auth_header else '否'}")
                        print(f"   📦 完整保存 headers: {len(self.raw_headers)} 個")
                        print(f"   📦 完整保存 payload: {len(self.raw_payload)} 字符")
                        
                        self.captured = True
                    elif "replies" in root_field:
                        print(f"   ⏭️ 跳過留言查詢: {friendly_name} (root: {root_field})")
                    else:
                        print(f"   ⏭️ 跳過其他查詢: {friendly_name}")
            
            page.on("response", response_handler)
            
            # 導航並等待攔截
            print(f"   🌐 導航到: {TEST_POST_URL}")
            await page.goto(TEST_POST_URL, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(5)
            
            # 如果沒攔截到，嘗試刷新
            if not self.captured:
                print(f"   🔄 刷新頁面重新攔截...")
                await page.reload(wait_until="networkidle")
                await asyncio.sleep(5)
            
            await browser.close()
        
        return self.captured
    
    async def _process_media_data(self, media: dict, replay_headers: dict, replay_payload: str, full_result: dict) -> bool:
        """處理媒體數據並提取關鍵信息"""
        print(f"   🎉 成功！獲取媒體數據")
        
        # 提取關鍵信息
        pk = media.get("pk", "")
        caption = media.get("caption", {}) or {}
        content = caption.get("text", "") if caption else ""
        like_count = media.get("like_count", 0)
        
        text_info = media.get("text_post_app_info", {}) or {}
        comment_count = text_info.get("direct_reply_count", 0)
        repost_count = text_info.get("repost_count", 0)
        share_count = text_info.get("reshare_count", 0)
        
        # 媒體信息
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
        print(f"      📝 內容: {len(content)} 字符")
        print(f"      👍 讚數: {like_count}")
        print(f"      💬 留言: {comment_count}")
        print(f"      🔄 轉發: {repost_count}")
        print(f"      📤 分享: {share_count}")
        print(f"      🖼️ 圖片: {len(images)} 個")
        print(f"      🎥 影片: {len(videos)} 個")
        
        if content:
            print(f"      📄 內容預覽: {content[:100]}...")
        
        # 保存成功配置
        success_file = Path(f"perfect_replay_success_{datetime.now().strftime('%H%M%S')}.json")
        with open(success_file, 'w', encoding='utf-8') as f:
            json.dump({
                "method": "perfect_replay",
                "doc_id": self.doc_id,
                "headers_count": len(replay_headers),
                "payload_size": len(replay_payload),
                "test_result": {
                    "pk": pk,
                    "content": content,
                    "like_count": like_count,
                    "comment_count": comment_count,
                    "repost_count": repost_count,
                    "share_count": share_count,
                    "images_count": len(images),
                    "videos_count": len(videos),
                    "images": images[:3],  # 只保存前3個URL
                    "videos": videos[:3]
                },
                "raw_headers": replay_headers,
                "raw_payload": replay_payload,
                "media_data": media,
                "full_response": full_result
            }, f, indent=2, ensure_ascii=False)
        
        print(f"      📁 成功配置已保存: {success_file}")
        return True
    
    async def get_authorization_from_cookies(self) -> Optional[str]:
        """從 cookies 獲取 Authorization（如果 header 中沒有）"""
        auth_file_path = get_auth_file_path()
        auth_data = json.loads(auth_file_path.read_text())
        cookies = {cookie['name']: cookie['value'] for cookie in auth_data.get('cookies', [])}
        
        # 方法1: ig_set_authorization cookie
        if 'ig_set_authorization' in cookies:
            auth_value = cookies['ig_set_authorization']
            if auth_value and not auth_value.startswith('Bearer'):
                return f"Bearer {auth_value}"
            return auth_value
        
        # 方法2: 從 sessionid 構建
        if 'sessionid' in cookies:
            sessionid = cookies['sessionid']
            return f"Bearer IGT:2:{sessionid}"
        
        return None
    
    async def perfect_replay(self, new_pk: str = None):
        """完美重放請求 - 完全按照攔截到的格式"""
        if not self.captured:
            print("❌ 沒有攔截到請求")
            return False
        
        print(f"\n🎬 完美重放攔截到的請求...")
        
        # 獲取 cookies
        auth_file_path = get_auth_file_path()
        auth_data = json.loads(auth_file_path.read_text())
        cookies = {cookie['name']: cookie['value'] for cookie in auth_data.get('cookies', [])}
        
        # 準備 headers（完全複製，只刪除會干擾的）
        replay_headers = self.raw_headers.copy()
        
        # 只刪除這些會讓 httpx 自動處理的 headers
        for header_to_remove in ["host", "content-length", "accept-encoding"]:
            replay_headers.pop(header_to_remove, None)
        
        print(f"   📦 使用 headers: {len(replay_headers)} 個")
        
        # 檢查 Authorization
        if not replay_headers.get("authorization"):
            print(f"   🔍 header 中無 Authorization，從 cookies 獲取...")
            auth_from_cookies = await self.get_authorization_from_cookies()
            if auth_from_cookies:
                replay_headers["authorization"] = auth_from_cookies
                print(f"   ✅ 從 cookies 補充 Authorization")
            else:
                print(f"   ⚠️ 警告：無法獲取 Authorization，可能導致 403")
        
        # 準備 payload（完全複製，只替換 PK 如果需要）
        replay_payload = self.raw_payload
        if new_pk and new_pk != TARGET_PK:
            # 只替換 PK，其他保持原樣
            replay_payload = replay_payload.replace(TARGET_PK, new_pk)
            print(f"   🔄 替換 PK: {TARGET_PK} → {new_pk}")
        
        print(f"   📦 使用 payload: {len(replay_payload)} 字符")
        
        # 發送請求（最小可行版本）
        url = "https://www.threads.com/graphql/query"
        
        async with httpx.AsyncClient(
            headers=replay_headers,
            cookies=cookies,
            timeout=30.0,
            follow_redirects=True,
            http2=True
        ) as client:
            try:
                print(f"   📡 發送請求到: {url}")
                response = await client.post(url, data=replay_payload)
                
                print(f"   📡 HTTP {response.status_code}")
                
                if response.status_code == 200:
                    try:
                        result = response.json()
                        
                        if "errors" in result:
                            print(f"   ❌ GraphQL 錯誤: {result['errors'][:1]}")
                            return False
                        
                        if "data" in result and result["data"]:
                            data = result["data"]
                            
                            # 檢查不同的數據結構
                            if "media" in data and data["media"]:
                                # 方法1: 直接的 media 結構
                                media = data["media"]
                                return await self._process_media_data(media, replay_headers, replay_payload, result)
                            
                            elif "data" in data and data["data"]:
                                # 方法2: edges 結構（留言或相關貼文）
                                inner_data = data["data"]
                                if "edges" in inner_data and inner_data["edges"]:
                                    print(f"   📝 發現 edges 結構: {len(inner_data['edges'])} 個")
                                    
                                    # 嘗試在 edges 中找到目標貼文
                                    target_found = False
                                    for i, edge in enumerate(inner_data["edges"]):
                                        if "node" in edge:
                                            node = edge["node"]
                                            
                                            # 檢查是否為貼文節點
                                            if "post" in node:
                                                post = node["post"]
                                                post_pk = post.get("pk", "")
                                                if post_pk == TARGET_PK:
                                                    print(f"   🎯 在 edge[{i}] 中找到目標貼文!")
                                                    return await self._process_media_data(post, replay_headers, replay_payload, result)
                                            
                                            # 檢查是否為直接的媒體節點
                                            elif node.get("pk") == TARGET_PK:
                                                print(f"   🎯 在 edge[{i}] 中找到目標媒體!")
                                                return await self._process_media_data(node, replay_headers, replay_payload, result)
                                            
                                            # 檢查 thread_items 結構
                                            elif "thread_items" in node:
                                                for j, item in enumerate(node["thread_items"]):
                                                    if "post" in item and item["post"].get("pk") == TARGET_PK:
                                                        print(f"   🎯 在 edge[{i}].thread_items[{j}] 中找到目標貼文!")
                                                        return await self._process_media_data(item["post"], replay_headers, replay_payload, result)
                                    
                                    if not target_found:
                                        print(f"   ⚠️ edges 中未找到目標貼文 (PK: {TARGET_PK})")
                                        print(f"   💡 這可能是留言查詢，而不是主貼文查詢")
                                        
                                        # 顯示找到的 PK 用於調試
                                        found_pks = []
                                        for edge in inner_data["edges"][:3]:  # 只檢查前3個
                                            if "node" in edge:
                                                node = edge["node"]
                                                pk = (node.get("post", {}).get("pk") or 
                                                     node.get("pk") or 
                                                     "unknown")
                                                found_pks.append(pk)
                                        print(f"   📋 找到的 PK 範例: {found_pks}")
                                
                                print(f"   📋 數據結構: {list(data.keys())}")
                                print(f"   📋 內層結構: {list(inner_data.keys())}")
                            
                            else:
                                print(f"   📋 未知數據結構: {list(data.keys())}")
                        
                        else:
                            print(f"   ❌ 無效響應結構")
                        
                        return False
                    
                    except Exception as e:
                        print(f"   ❌ 解析響應失敗: {e}")
                        print(f"   📄 響應片段: {response.text[:300]}...")
                        return False
                
                elif response.status_code == 403:
                    print(f"   ❌ 403 錯誤分析:")
                    response_text = response.text
                    
                    if "login_required" in response_text:
                        print(f"      💡 需要登入")
                    elif "www_claims" in response_text:
                        print(f"      💡 x-ig-www-claim 問題")
                    elif "<!DOCTYPE html>" in response_text:
                        print(f"      💡 返回 HTML 頁面而非 JSON")
                    
                    print(f"      🔍 可能原因:")
                    print(f"         1. doc_id 過期 ({self.doc_id})")
                    print(f"         2. Authorization header 格式錯誤")
                    print(f"         3. 缺少關鍵 headers (x-ig-www-claim 等)")
                    
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
    print("🚀 完美內容攔截器 - 完全複製真實請求")
    
    auth_file = get_auth_file_path()
    if not auth_file.exists():
        print(f"❌ 認證檔案 {auth_file} 不存在。請先執行 save_auth.py。")
        return
    
    interceptor = PerfectContentInterceptor()
    
    # 第一步：攔截並完整複製
    print(f"\n📡 第一步：攔截真實請求...")
    captured = await interceptor.intercept_and_copy_everything()
    
    if not captured:
        print(f"\n😞 未能攔截到請求")
        return
    
    # 第二步：完美重放
    print(f"\n🎬 第二步：完美重放...")
    success = await interceptor.perfect_replay()
    
    if success:
        print(f"\n🎉 完美重放成功！")
        print(f"💡 這證明了「完全複製」的方法是正確的")
        print(f"🔧 現在可以:")
        print(f"   1. 將此邏輯整合到主爬蟲")
        print(f"   2. 實現批量內容查詢")
        print(f"   3. 添加自動重新攔截機制")
    else:
        print(f"\n😞 重放失敗")
        print(f"💡 如果是 403，可能需要:")
        print(f"   1. 重新攔截獲取新的 doc_id")
        print(f"   2. 檢查 Authorization 格式")
        print(f"   3. 確保所有必要 headers 都已複製")

if __name__ == "__main__":
    asyncio.run(main())