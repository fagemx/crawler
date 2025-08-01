"""
使用真實的 BarcelonaPostPageRefetchableDirectQuery 格式測試內容查詢
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
TARGET_PK = "3689219480905289907"  # 我們知道的真實 PK

async def get_real_lsd_token():
    """獲取真實的 LSD token"""
    print("   🔑 獲取真實 LSD token...")
    
    auth_file_path = get_auth_file_path()
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            storage_state=str(auth_file_path),
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15",
            viewport={"width": 375, "height": 812},
            locale="zh-TW"
        )
        
        page = await context.new_page()
        
        lsd_token = None
        
        async def response_handler(response):
            nonlocal lsd_token
            if "/graphql" in response.url.lower() and response.status == 200:
                try:
                    # 從響應 headers 或 cookies 中獲取 LSD token
                    fb_dtsg = None
                    for cookie in await context.cookies():
                        if cookie['name'] == 'fb_dtsg':
                            fb_dtsg = cookie['value']
                            break
                    
                    if not fb_dtsg:
                        # 從請求數據中提取
                        post_data = response.request.post_data
                        if post_data and "fb_dtsg=" in post_data:
                            import urllib.parse
                            for part in post_data.split('&'):
                                if part.startswith('fb_dtsg='):
                                    fb_dtsg = urllib.parse.unquote(part.split('=', 1)[1])
                                    break
                    
                    if fb_dtsg and not lsd_token:
                        lsd_token = fb_dtsg
                        print(f"      🔑 獲取到 LSD token: {lsd_token[:10]}...")
                except Exception as e:
                    pass
        
        page.on("response", response_handler)
        
        # 訪問 Gate 頁面來觸發請求
        gate_url = "https://www.threads.com/@threads"
        await page.goto(gate_url, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(3)
        
        await browser.close()
    
    return lsd_token

async def test_real_content_query():
    """使用真實格式測試內容查詢"""
    print("🚀 使用真實格式測試內容查詢...")
    
    # 獲取認證信息
    auth_file_path = get_auth_file_path()
    auth_data = json.loads(auth_file_path.read_text())
    cookies = {cookie['name']: cookie['value'] for cookie in auth_data.get('cookies', [])}
    
    # 獲取真實 LSD token
    lsd_token = await get_real_lsd_token()
    if not lsd_token:
        print("❌ 無法獲取 LSD token")
        return
    
    print(f"✅ 獲取到 LSD token: {lsd_token[:10]}...")
    
    # 真實的變數格式（基於攔截到的數據）
    variables = {
        "after": None,  # 設為 None 獲取第一頁
        "before": None,
        "first": 4,
        "is_logged_in": True,
        "last": None,
        "postID": TARGET_PK,  # 使用真實的 PK
        "sort_order": "TOP",
        "__relay_internal__pv__BarcelonaIsLoggedInrelayprovider": True,
        "__relay_internal__pv__BarcelonaHasSelfReplyContextrelayprovider": False,
        "__relay_internal__pv__BarcelonaShouldShowFediverseM1Featuresrelayprovider": True,
        "__relay_internal__pv__BarcelonaHasInlineReplyComposerrelayprovider": False,
        "__relay_internal__pv__BarcelonaHasEventBadgerelayprovider": False,
        "__relay_internal__pv__BarcelonaIsSearchDiscoveryEnabledrelayprovider": False,
        "__relay_internal__pv__IsTagIndicatorEnabledrelayprovider": True,
        "__relay_internal__pv__BarcelonaOptionalCookiesEnabledrelayprovider": True,
        "__relay_internal__pv__BarcelonaHasSelfThreadCountrelayprovider": False,
        "__relay_internal__pv__BarcelonaHasSpoilerStylingInforelayprovider": True,
        "__relay_internal__pv__BarcelonaHasDeepDiverelayprovider": False,
        "__relay_internal__pv__BarcelonaQuotedPostUFIEnabledrelayprovider": False,
        "__relay_internal__pv__BarcelonaHasTopicTagsrelayprovider": True,
        "__relay_internal__pv__BarcelonaIsCrawlerrelayprovider": False,
        "__relay_internal__pv__BarcelonaHasDisplayNamesrelayprovider": False,
        "__relay_internal__pv__BarcelonaCanSeeSponsoredContentrelayprovider": False,
        "__relay_internal__pv__BarcelonaShouldShowFediverseM075Featuresrelayprovider": True,
        "__relay_internal__pv__BarcelonaImplicitTrendsGKrelayprovider": False,
        "__relay_internal__pv__BarcelonaIsInternalUserrelayprovider": False,
        "__relay_internal__pv__BarcelonaInlineComposerEnabledrelayprovider": False
    }
    
    # 真實的 doc_id
    doc_id = "24061215210199287"
    
    # 構建請求數據（使用真實格式）
    request_data = {
        "av": "17841476182615522",
        "__user": "0",
        "__a": "1",
        "__req": "1",
        "__hs": "20301.HYP:barcelona_web_pkg.2.1..0",
        "dpr": "3",
        "__ccg": "EXCELLENT",
        "__rev": "1025400969",
        "__s": "test:test:test",
        "__hsi": "7533563618356429818",
        "__dyn": "7xeUmwlEnwn8K2Wmh0no6u5U4e0yoW3q32360CEbo1nEhw2nVE4W0qa0FE2awgo9oO0n24oaEd82lwv89k2C1Fwc60D85m1mzXwae4UaEW0Loco5G0zK5o4q0HU420n6azo7u0zE2ZwrUdUbGw4mwr86C2q6oe84J0lEbUaUuwhUyu4Q2-qfwio2own85SU7y",
        "__csr": "test",
        "__hsdp": "test",
        "__hblp": "test",
        "__sjsp": "test",
        "__comet_req": "29",
        "fb_dtsg": lsd_token,
        "jazoest": "26410",
        "lsd": lsd_token,  # 重要：使用真實的 LSD token
        "__spin_r": "1025400969",
        "__spin_b": "trunk",
        "__spin_t": str(int(datetime.now().timestamp())),
        "__jssesw": "2",
        "__crn": "comet.threads.BarcelonaPostColumnRoute",
        "fb_api_caller_class": "RelayModern",
        "fb_api_req_friendly_name": "BarcelonaPostPageRefetchableDirectQuery",
        "variables": json.dumps(variables),
        "server_timestamps": "true",
        "doc_id": doc_id
    }
    
    # 準備 headers
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15",
        "Accept": "*/*",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-FB-Friendly-Name": "BarcelonaPostPageRefetchableDirectQuery",
        "X-FB-LSD": lsd_token,
        "Origin": "https://www.threads.com",
        "Referer": TEST_POST_URL,
    }
    
    # 發送請求
    async with httpx.AsyncClient(
        cookies=cookies,
        timeout=30.0,
        follow_redirects=True
    ) as client:
        print(f"\n🧪 測試真實格式內容查詢...")
        print(f"   📋 doc_id: {doc_id}")
        print(f"   🎯 postID: {TARGET_PK}")
        
        try:
            response = await client.post(
                "https://www.threads.com/api/graphql",
                data=request_data,
                headers=headers
            )
            
            print(f"   📡 HTTP {response.status_code}")
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    print(f"   📋 響應鍵: {list(result.keys())}")
                    
                    if "errors" in result:
                        errors = result["errors"]
                        print(f"   ❌ 錯誤: {errors[:1]}")
                        return False
                    
                    if "data" in result and result["data"]:
                        print(f"   ✅ 成功獲取數據！")
                        data = result["data"]
                        print(f"   📊 data 鍵: {list(data.keys())}")
                        
                        # 分析內容結構
                        if "data" in data and data["data"] and "edges" in data["data"]:
                            edges = data["data"]["edges"]
                            print(f"   📝 找到 {len(edges)} 個 edges")
                            
                            for i, edge in enumerate(edges):
                                if "node" in edge and "thread_items" in edge["node"]:
                                    thread_items = edge["node"]["thread_items"]
                                    print(f"   📜 Edge {i}: {len(thread_items)} 個 thread_items")
                                    
                                    for j, item in enumerate(thread_items):
                                        if "post" in item:
                                            post = item["post"]
                                            pk = post.get("pk", "unknown")
                                            caption_text = ""
                                            
                                            # 提取內容
                                            if "caption" in post and post["caption"]:
                                                caption_text = post["caption"].get("text", "")[:100]
                                            
                                            # 提取媒體
                                            images = []
                                            videos = []
                                            
                                            if "image_versions2" in post:
                                                candidates = post["image_versions2"].get("candidates", [])
                                                if candidates:
                                                    images.append(candidates[0].get("url", ""))
                                            
                                            if "video_versions" in post:
                                                if post["video_versions"]:
                                                    videos.append(post["video_versions"][0].get("url", ""))
                                            
                                            # 檢查輪播媒體
                                            if "carousel_media" in post:
                                                for media in post["carousel_media"] or []:
                                                    if "image_versions2" in media:
                                                        candidates = media["image_versions2"].get("candidates", [])
                                                        if candidates:
                                                            images.append(candidates[0].get("url", ""))
                                                    if "video_versions" in media:
                                                        if media["video_versions"]:
                                                            videos.append(media["video_versions"][0].get("url", ""))
                                            
                                            print(f"      📄 Item {j}: PK={pk}")
                                            print(f"         📝 內容: {caption_text}...")
                                            print(f"         🖼️ 圖片: {len(images)} 個")
                                            print(f"         🎥 影片: {len(videos)} 個")
                                            
                                            if pk == TARGET_PK:
                                                print(f"         🎯 找到目標貼文！")
                                                
                                                # 保存完整數據
                                                debug_file = Path(f"target_post_content_{datetime.now().strftime('%H%M%S')}.json")
                                                with open(debug_file, 'w', encoding='utf-8') as f:
                                                    json.dump(post, f, indent=2, ensure_ascii=False)
                                                print(f"         📁 已保存完整數據到: {debug_file}")
                                                
                                                return True
                        
                        # 保存完整響應用於分析
                        debug_file = Path(f"real_content_response_{datetime.now().strftime('%H%M%S')}.json")
                        with open(debug_file, 'w', encoding='utf-8') as f:
                            json.dump(result, f, indent=2, ensure_ascii=False)
                        print(f"   📁 已保存完整響應到: {debug_file}")
                        
                        return True
                    else:
                        print(f"   ❌ 空 data 或無效響應")
                        return False
                
                except Exception as e:
                    print(f"   ❌ 解析響應失敗: {e}")
                    print(f"   📄 原始響應: {response.text[:500]}...")
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
    auth_file = get_auth_file_path()
    if not auth_file.exists():
        print(f"❌ 認證檔案 {auth_file} 不存在。請先執行 save_auth.py。")
        return

    success = await test_real_content_query()
    
    if success:
        print(f"\n🎉 成功獲取內容數據！")
        print(f"💡 現在可以將此邏輯整合到主要爬蟲中")
    else:
        print(f"\n😞 內容查詢失敗")
        print(f"💡 可能需要進一步調整變數格式或認證方式")

if __name__ == "__main__":
    asyncio.run(main())