"""
測試不同的變數組合來找到正確的內容查詢格式
"""

import asyncio
import json
import httpx
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List

import sys
sys.path.append(str(Path(__file__).parent))

from playwright.async_api import async_playwright
from common.config import get_auth_file_path

# 測試貼文
TEST_POST_URL = "https://www.threads.com/@star_shining0828/post/DMyvZJRz5Cz"
TARGET_PK = "3689219480905289907"

async def get_real_lsd_token():
    """快速獲取 LSD token"""
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
                    if post_data and "fb_dtsg=" in post_data:
                        import urllib.parse
                        for part in post_data.split('&'):
                            if part.startswith('fb_dtsg='):
                                lsd_token = urllib.parse.unquote(part.split('=', 1)[1])
                                break
                except:
                    pass
        
        page.on("response", response_handler)
        await page.goto("https://www.threads.com/@threads", wait_until="networkidle")
        await asyncio.sleep(3)
        await browser.close()
    
    return lsd_token

async def test_variable_combination(variables: Dict[str, Any], description: str):
    """測試特定的變數組合"""
    print(f"\n🧪 測試: {description}")
    
    # 獲取認證
    auth_file_path = get_auth_file_path()
    auth_data = json.loads(auth_file_path.read_text())
    cookies = {cookie['name']: cookie['value'] for cookie in auth_data.get('cookies', [])}
    
    lsd_token = await get_real_lsd_token()
    if not lsd_token:
        print("   ❌ 無法獲取 LSD token")
        return False
    
    # 構建請求數據
    request_data = {
        "av": "17841476182615522",
        "__user": "0",
        "__a": "1",
        "__req": "1",
        "dpr": "3",
        "__ccg": "EXCELLENT",
        "__rev": "1025400969",
        "fb_dtsg": lsd_token,
        "jazoest": "26410",
        "lsd": lsd_token,
        "fb_api_caller_class": "RelayModern",
        "fb_api_req_friendly_name": "BarcelonaPostPageRefetchableDirectQuery",
        "variables": json.dumps(variables),
        "server_timestamps": "true",
        "doc_id": "24061215210199287"
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15",
        "Accept": "*/*",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-FB-Friendly-Name": "BarcelonaPostPageRefetchableDirectQuery",
        "X-FB-LSD": lsd_token,
        "Origin": "https://www.threads.com",
        "Referer": TEST_POST_URL,
    }
    
    # 發送請求
    async with httpx.AsyncClient(cookies=cookies, timeout=30.0) as client:
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
                    
                    if "errors" in result:
                        print(f"   ❌ 錯誤: {result['errors'][:1]}")
                        return False
                    
                    if "data" in result:
                        data = result["data"]
                        if data and "data" in data and data["data"]:
                            print(f"   ✅ 成功獲取有效數據！")
                            
                            # 快速分析結構
                            inner_data = data["data"]
                            if "edges" in inner_data:
                                edges_count = len(inner_data["edges"])
                                print(f"   📝 找到 {edges_count} 個 edges")
                                
                                # 檢查是否有我們要的貼文
                                found_target = False
                                for edge in inner_data["edges"]:
                                    if "node" in edge and "thread_items" in edge["node"]:
                                        for item in edge["node"]["thread_items"]:
                                            if "post" in item and item["post"].get("pk") == TARGET_PK:
                                                found_target = True
                                                post = item["post"]
                                                
                                                # 檢查內容
                                                caption = post.get("caption", {})
                                                content_text = caption.get("text", "") if caption else ""
                                                
                                                # 檢查媒體
                                                has_images = "image_versions2" in post or "carousel_media" in post
                                                has_videos = "video_versions" in post
                                                
                                                print(f"   🎯 找到目標貼文！")
                                                print(f"      📝 內容長度: {len(content_text)} 字符")
                                                print(f"      🖼️ 有圖片: {has_images}")
                                                print(f"      🎥 有影片: {has_videos}")
                                                
                                                # 保存成功的組合
                                                success_file = Path(f"successful_variables_{datetime.now().strftime('%H%M%S')}.json")
                                                with open(success_file, 'w', encoding='utf-8') as f:
                                                    json.dump({
                                                        "description": description,
                                                        "variables": variables,
                                                        "post_data": post
                                                    }, f, indent=2, ensure_ascii=False)
                                                print(f"      📁 已保存成功組合到: {success_file}")
                                                
                                                return True
                                
                                if not found_target:
                                    print(f"   ⚠️ 有數據但未找到目標貼文")
                            else:
                                print(f"   ⚠️ 有 data 但結構不符預期: {list(inner_data.keys())}")
                        else:
                            print(f"   ❌ data.data 為空或 null")
                    else:
                        print(f"   ❌ 響應中無 data 欄位")
                    
                    return False
                
                except Exception as e:
                    print(f"   ❌ 解析失敗: {e}")
                    return False
            else:
                print(f"   ❌ HTTP 錯誤: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"   ❌ 請求失敗: {e}")
            return False

async def main():
    """測試多種變數組合"""
    print("🚀 測試多種變數組合...")
    
    # 測試組合 1: 最簡化版本
    simple_vars = {
        "postID": TARGET_PK,
        "is_logged_in": True
    }
    
    # 測試組合 2: 加上分頁參數
    pagination_vars = {
        "postID": TARGET_PK,
        "is_logged_in": True,
        "first": 10,
        "after": None,
        "before": None,
        "last": None
    }
    
    # 測試組合 3: 加上排序
    sorted_vars = {
        "postID": TARGET_PK,
        "is_logged_in": True,
        "first": 10,
        "sort_order": "TOP"
    }
    
    # 測試組合 4: 核心 relay 參數
    core_relay_vars = {
        "postID": TARGET_PK,
        "is_logged_in": True,
        "first": 4,
        "sort_order": "TOP",
        "__relay_internal__pv__BarcelonaIsLoggedInrelayprovider": True,
        "__relay_internal__pv__BarcelonaIsCrawlerrelayprovider": False
    }
    
    # 測試組合 5: 完整參數（從攔截複製）
    full_vars = {
        "after": None,
        "before": None,
        "first": 4,
        "is_logged_in": True,
        "last": None,
        "postID": TARGET_PK,
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
    
    # 依序測試
    test_cases = [
        (simple_vars, "最簡化版本"),
        (pagination_vars, "加上分頁參數"),
        (sorted_vars, "加上排序參數"),
        (core_relay_vars, "核心 relay 參數"),
        (full_vars, "完整參數集")
    ]
    
    for variables, description in test_cases:
        success = await test_variable_combination(variables, description)
        if success:
            print(f"\n🎉 找到成功組合: {description}")
            break
        await asyncio.sleep(1)  # 避免過於頻繁的請求
    else:
        print(f"\n😞 所有組合都失敗了")
        print(f"💡 可能需要檢查:")
        print(f"   1. postID 是否正確")
        print(f"   2. 是否需要其他必要參數")
        print(f"   3. API 端點或 doc_id 是否變更")

if __name__ == "__main__":
    asyncio.run(main())