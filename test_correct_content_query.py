"""
使用正確的格式測試內容查詢（基於用戶指導）
"""

import asyncio
import json
import httpx
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

import sys
sys.path.append(str(Path(__file__).parent))

from playwright.async_api import async_playwright
from common.config import get_auth_file_path

# 測試貼文
TEST_POST_URL = "https://www.threads.com/@star_shining0828/post/DMyvZJRz5Cz"
TARGET_PK = "3689219480905289907"

async def get_real_lsd_token():
    """獲取真實的 LSD token"""
    auth_file_path = get_auth_file_path()
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            storage_state=str(auth_file_path),
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15",
            viewport={"width": 375, "height": 812}
        )
        
        page = await context.new_page()
        lsd_token = None
        
        async def response_handler(response):
            nonlocal lsd_token
            if "/graphql" in response.url.lower() and response.status == 200:
                try:
                    post_data = response.request.post_data
                    if post_data and "lsd=" in post_data:
                        import urllib.parse
                        for part in post_data.split('&'):
                            if part.startswith('lsd='):
                                lsd_token = urllib.parse.unquote(part.split('=', 1)[1])
                                break
                except:
                    pass
        
        page.on("response", response_handler)
        await page.goto("https://www.threads.com/@threads", wait_until="networkidle")
        await asyncio.sleep(3)
        await browser.close()
    
    return lsd_token

async def test_with_known_doc_ids():
    """使用已知的 doc_id 測試"""
    print("🧪 使用已知 doc_id 測試...")
    
    # 獲取認證
    auth_file_path = get_auth_file_path()
    auth_data = json.loads(auth_file_path.read_text())
    cookies = {cookie['name']: cookie['value'] for cookie in auth_data.get('cookies', [])}
    
    lsd_token = await get_real_lsd_token()
    if not lsd_token:
        print("❌ 無法獲取 LSD token")
        return False
    
    print(f"✅ 獲取到 LSD token: {lsd_token[:10]}...")
    
    # 嘗試不同的 doc_id（從實際攔截中獲得）
    doc_ids_to_try = [
        ("24061215210199287", "BarcelonaPostPageRefetchableDirectQuery"),  # 攔截到的
        ("25073444793714143", "BarcelonaPostPageContentQuery"),  # 用戶提到的
        ("7428920450586442", "舊版本測試"),
    ]
    
    for doc_id, description in doc_ids_to_try:
        print(f"\n🔍 測試 {description}: {doc_id}")
        
        success = await test_content_query_with_doc_id(doc_id, lsd_token, cookies)
        if success:
            print(f"🎉 成功使用 {description}!")
            return True
        
        await asyncio.sleep(1)
    
    return False

async def test_content_query_with_doc_id(doc_id: str, lsd_token: str, cookies: dict):
    """使用特定 doc_id 測試內容查詢"""
    
    # 按照用戶指導的正確格式
    variables = {
        "postID_pk": TARGET_PK,  # 關鍵：使用 postID_pk 而不是 postID
        "withShallowTree": False,  # 關鍵：必需參數
        "includePromotedPosts": False
    }
    
    # 構建 payload（簡化版本）
    payload = f"lsd={lsd_token}&doc_id={doc_id}&variables={json.dumps(variables)}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-FB-LSD": lsd_token,  # 關鍵：LSD token 放在 header
        "X-IG-App-ID": "238260118697367",  # 按照用戶指導添加
        "Origin": "https://www.threads.com",
        "Referer": TEST_POST_URL,
    }
    
    # 使用正確的 endpoint
    endpoint = "https://www.threads.com/graphql/query"  # 關鍵：不是 /api/graphql
    
    async with httpx.AsyncClient(cookies=cookies, timeout=30.0, http2=True) as client:
        try:
            response = await client.post(endpoint, data=payload, headers=headers)
            
            print(f"   📡 HTTP {response.status_code}")
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    
                    if "errors" in result:
                        errors = result["errors"]
                        print(f"   ❌ 錯誤: {errors[:1]}")
                        return False
                    
                    if "data" in result:
                        data = result["data"]
                        
                        if data and "media" in data and data["media"]:
                            # 按照用戶指導的結構解析
                            media = data["media"]
                            print(f"   ✅ 成功獲取媒體數據！")
                            
                            # 提取基本信息
                            pk = media.get("pk", "unknown")
                            typename = media.get("__typename", "unknown")
                            
                            # 提取內容
                            caption = media.get("caption", {})
                            content_text = caption.get("text", "") if caption else ""
                            
                            # 提取計數
                            like_count = media.get("like_count", 0)
                            text_info = media.get("text_post_app_info", {})
                            comment_count = text_info.get("direct_reply_count", 0)
                            repost_count = text_info.get("repost_count", 0)
                            share_count = text_info.get("reshare_count", 0)
                            
                            # 提取媒體
                            images = []
                            videos = []
                            
                            if "image_versions2" in media:
                                candidates = media["image_versions2"].get("candidates", [])
                                if candidates:
                                    # 取最高解析度的圖片
                                    best_image = max(candidates, key=lambda c: c.get("width", 0))
                                    images.append(best_image.get("url", ""))
                            
                            if "video_versions" in media and media["video_versions"]:
                                # 取第一個影片版本
                                videos.append(media["video_versions"][0].get("url", ""))
                            
                            # 檢查輪播媒體
                            if "carousel_media" in media:
                                for carousel_item in media["carousel_media"] or []:
                                    if "image_versions2" in carousel_item:
                                        candidates = carousel_item["image_versions2"].get("candidates", [])
                                        if candidates:
                                            best_image = max(candidates, key=lambda c: c.get("width", 0))
                                            images.append(best_image.get("url", ""))
                                    if "video_versions" in carousel_item and carousel_item["video_versions"]:
                                        videos.append(carousel_item["video_versions"][0].get("url", ""))
                            
                            print(f"   📄 PK: {pk}")
                            print(f"   🏷️ 類型: {typename}")
                            print(f"   📝 內容: {content_text[:100]}...")
                            print(f"   👍 讚數: {like_count}")
                            print(f"   💬 留言: {comment_count}")
                            print(f"   🔄 轉發: {repost_count}")
                            print(f"   📤 分享: {share_count}")
                            print(f"   🖼️ 圖片: {len(images)} 個")
                            print(f"   🎥 影片: {len(videos)} 個")
                            
                            if pk == TARGET_PK:
                                print(f"   🎯 確認找到目標貼文！")
                                
                                # 保存成功數據
                                success_file = Path(f"successful_content_query_{datetime.now().strftime('%H%M%S')}.json")
                                with open(success_file, 'w', encoding='utf-8') as f:
                                    json.dump({
                                        "doc_id": doc_id,
                                        "variables": variables,
                                        "endpoint": endpoint,
                                        "media_data": media,
                                        "extracted": {
                                            "pk": pk,
                                            "content": content_text,
                                            "like_count": like_count,
                                            "comment_count": comment_count,
                                            "repost_count": repost_count,
                                            "share_count": share_count,
                                            "images": images,
                                            "videos": videos
                                        }
                                    }, f, indent=2, ensure_ascii=False)
                                print(f"   📁 已保存成功配置到: {success_file}")
                                
                                return True
                            else:
                                print(f"   ⚠️ PK 不匹配，預期: {TARGET_PK}")
                        
                        elif data and "data" in data:
                            # 可能是其他結構
                            print(f"   ⚠️ 數據結構不符預期，data 鍵: {list(data.keys())}")
                            if data["data"]:
                                print(f"   📋 內層 data 鍵: {list(data['data'].keys())}")
                        else:
                            print(f"   ❌ 無效的 data 結構")
                    else:
                        print(f"   ❌ 響應中無 data 欄位")
                    
                    return False
                
                except Exception as e:
                    print(f"   ❌ 解析響應失敗: {e}")
                    print(f"   📄 原始響應: {response.text[:500]}...")
                    return False
            else:
                print(f"   ❌ HTTP 錯誤: {response.status_code}")
                if response.status_code == 404:
                    print(f"   💡 可能 endpoint 已變更")
                return False
                
        except Exception as e:
            print(f"   ❌ 請求失敗: {e}")
            return False

async def main():
    """主函數"""
    print("🚀 使用正確格式測試內容查詢...")
    
    auth_file = get_auth_file_path()
    if not auth_file.exists():
        print(f"❌ 認證檔案 {auth_file} 不存在。請先執行 save_auth.py。")
        return

    success = await test_with_known_doc_ids()
    
    if success:
        print(f"\n🎉 內容查詢成功！")
        print(f"💡 現在可以整合到主要爬蟲邏輯中")
    else:
        print(f"\n😞 所有嘗試都失敗了")
        print(f"💡 可能需要:")
        print(f"   1. 更新 doc_id")
        print(f"   2. 檢查變數格式")
        print(f"   3. 確認 endpoint 正確性")

if __name__ == "__main__":
    asyncio.run(main())