"""
獨立測試 GraphQL 抓取單則貼文詳細數據
不依賴 Docker，專門測試讚、分享、留言等數據
"""

import sys
import asyncio
import json
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

# Windows asyncio 修復
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from playwright.async_api import async_playwright, Page

# 導入必要的解析函數
sys.path.append(str(Path(__file__).parent))
from common.config import get_auth_file_path
from common.utils import first_of, parse_thread_item

# --- 測試設定 ---
TEST_POST_URLS = [
    "https://www.threads.com/@star_shining0828/post/DMyvZJRz5Cz",  # 測試貼文1 - 數字型瀏覽數
    "https://www.threads.com/@star_shining0828/post/DMxwLDUy4JD",  # 測試貼文2 - 萬型瀏覽數  
    "https://www.threads.com/@star_shining0828/post/DMwKpQlThM8",  # 測試貼文3 - 少量瀏覽數
]

# 根據調試結果優化的欄位對照表
FIELD_MAP = {
    "like_count": [
        "like_count",  # ✅ 確認：data.data.posts[0].like_count
        "likeCount", 
        ["feedback_info", "aggregated_like_count"],
        ["like_info", "count"]
    ],
    "comment_count": [
        ["text_post_app_info", "direct_reply_count"],  # ✅ 確認：精確匹配
        "comment_count", "commentCount",
        ["reply_info", "count"]
    ],
    "share_count": [
        ["text_post_app_info", "reshare_count"],  # ✅ 確認：精確匹配
        "reshareCount", "share_count", "shareCount"
    ],
    "repost_count": [
        ["text_post_app_info", "repost_count"],  # ✅ 確認：精確匹配
        "repostCount", "repost_count"
    ],
    "content": [
        ["caption", "text"],
        "caption", "text", "content"
    ],
    "author": [
        ["user", "username"], 
        ["owner", "username"],
        ["user", "handle"]
    ],
    "created_at": [
        "taken_at", "taken_at_timestamp", 
        "publish_date", "created_time"
    ],
    "post_id": [
        "pk", "id", "post_id"
    ],
    "code": [
        "code", "shortcode", "media_code"
    ],
    "view_count": [
        ["feedback_info", "view_count"],
        ["video_info", "play_count"],
        "view_count",
        "views",
        "impression_count"
    ],
}

# GraphQL 查詢正則
GRAPHQL_RE = re.compile(r"/graphql/query")

def extract_post_code_from_url(url: str) -> str:
    """從 URL 中提取貼文代碼"""
    match = re.search(r'/post/([A-Za-z0-9_-]+)', url)
    return match.group(1) if match else ""

def find_post_node(payload: Any, target_post_url: str = "") -> Optional[Dict]:
    """
    從任何 Threads JSON 負載裡遞迴找出單篇貼文物件
    支援 HTML 直嵌模式和 Gate 頁 GraphQL 模式
    """
    if isinstance(payload, dict):
        t = payload.get("__typename", "")
        
        # ① 直接就是貼文物件 - 支援所有 XDT 類型
        if (t.startswith("XDT") or 
            t.endswith(("TextPost", "Photo", "Video", "Media"))):
            print(f"   🎯 找到貼文物件: {t}")
            return payload
        
        # ② Gate 頁完整版：data.media 結構
        if "media" in payload and isinstance(payload["media"], dict):
            media_obj = payload["media"]
            media_type = media_obj.get("__typename", "")
            if (media_type.startswith("XDT") or 
                media_type.endswith(("TextPost", "Photo", "Video", "Media"))):
                print(f"   🎯 在 Gate 頁 data.media 中找到貼文: {media_type}")
                return media_obj
        
        # ③ Gate 頁批次計數：data.data.posts[] (根據 post code 匹配正確的貼文)
        if "posts" in payload and isinstance(payload["posts"], list):
            posts_list = payload["posts"]
            if posts_list and len(posts_list) > 0:
                target_code = extract_post_code_from_url(target_post_url) if target_post_url else ""
                
                print(f"   🔍 在 {len(posts_list)} 個批次貼文中尋找目標: {target_code}")
                
                for i, post in enumerate(posts_list):
                    if isinstance(post, dict):
                        # 檢查是否有關鍵的計數欄位
                        has_counts = (
                            "like_count" in post or 
                            "text_post_app_info" in post
                        )
                        
                        if has_counts:
                            post_code = post.get("code", "")
                            pk = post.get("pk", "")
                            like_count = post.get("like_count", 0)
                            
                            print(f"      📝 貼文 {i}: code={post_code}, pk={pk}, 讚={like_count}")
                            
                            # 如果有目標代碼，優先匹配
                            if target_code and post_code == target_code:
                                print(f"   🎯 找到目標貼文 (索引 {i}): {post_code}")
                                return post
                            # 如果沒有目標代碼，取第一個有效的
                            elif not target_code and i == 0:
                                print(f"   🎯 使用第一個批次貼文 (索引 {i})")
                                return post
                
                # 如果沒找到匹配的，但有目標代碼，給出警告
                if target_code:
                    print(f"   ⚠️ 未找到匹配代碼 {target_code} 的貼文，使用第一個")
                    first_valid = next((post for post in posts_list if isinstance(post, dict) and ("like_count" in post or "text_post_app_info" in post)), None)
                    if first_valid:
                        return first_valid
        
        # ④ 舊式 thread_items 結構 (HTML 直嵌模式)
        if "thread_items" in payload:
            items = payload["thread_items"]
            if items and len(items) > 0:
                post = items[0].get("post") or items[0]
                if post:
                    print(f"   🎯 在 thread_items 中找到貼文")
                    return post
        
        # ⑤ 一般遞迴搜尋
        for v in payload.values():
            found = find_post_node(v)
            if found:
                return found
                
    elif isinstance(payload, list):
        for item in payload:
            found = find_post_node(item)
            if found:
                return found
    
    return None

def parse_single_post_data(post_data: Dict[str, Any], username: str) -> Dict[str, Any]:
    """
    解析單則貼文的詳細數據 - 統一處理 HTML 直嵌和 GraphQL 兩種模式
    """
    # 直接使用傳入的 post 數據，不再需要 parse_thread_item
    post = post_data
    
    if not post:
        print(f"❌ 找不到有效的 post 物件")
        return {}

    # 提取所有欄位
    result = {
        "post_id": first_of(post, *FIELD_MAP["post_id"]),
        "code": first_of(post, *FIELD_MAP["code"]),
        "author": first_of(post, *FIELD_MAP["author"]) or username,
        "content": first_of(post, *FIELD_MAP["content"]) or "",
        "like_count": first_of(post, *FIELD_MAP["like_count"]) or 0,
        "comment_count": first_of(post, *FIELD_MAP["comment_count"]) or 0,
        "share_count": first_of(post, *FIELD_MAP["share_count"]) or 0,
        "repost_count": first_of(post, *FIELD_MAP["repost_count"]) or 0,
        "view_count": first_of(post, *FIELD_MAP["view_count"]) or 0,
        "created_at": first_of(post, *FIELD_MAP["created_at"]),
        "raw_keys": list(post.keys()),  # 調試用：顯示所有可用欄位
        "typename": post.get("__typename"),  # 調試用：顯示物件類型
    }
    
    # 處理時間戳
    if result["created_at"] and isinstance(result["created_at"], (int, float)):
        result["created_at_formatted"] = datetime.fromtimestamp(result["created_at"]).isoformat()
    
    return result

async def handle_graphql_or_html(page: Page, post_url: str, username: str, context) -> Optional[Dict[str, Any]]:
    """
    統一處理 HTML 直嵌模式和 Gate 頁 GraphQL 模式
    """
    print(f"   🌐 導航到: {post_url}")
    await page.goto(post_url, wait_until="networkidle", timeout=60000)
    
    # 檢查頁面內容
    html = await page.content()
    
    # 先等待一下，確保頁面完全載入
    await asyncio.sleep(2)
    
    # 再次獲取頁面內容
    html = await page.content()
    
    print(f"   🔍 頁面長度: {len(html)} 字符")
    print(f"   🔍 __NEXT_DATA__ 檢查: {'✅ 存在' if '__NEXT_DATA__' in html else '❌ 不存在'}")
    
    # 模式1: HTML 直嵌資料 (__NEXT_DATA__ 存在)
    if "__NEXT_DATA__" in html:
        print(f"   ✅ 檢測到 HTML 直嵌模式")
        try:
            # 提取 __NEXT_DATA__ - 使用更寬鬆的正則
            next_data_patterns = [
                r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                r'__NEXT_DATA__["\']?\s*[:=]\s*({.*?})\s*[;,]?',
                r'window\.__NEXT_DATA__\s*=\s*({.*?});'
            ]
            
            data = None
            for pattern in next_data_patterns:
                next_data_match = re.search(pattern, html, re.DOTALL)
                if next_data_match:
                    try:
                        data = json.loads(next_data_match.group(1))
                        print(f"   📦 成功解析 __NEXT_DATA__ (模式: {pattern[:20]}...)")
                        break
                    except json.JSONDecodeError:
                        continue
            
            if data:
                # 使用統一的 find_post_node 找貼文
                post = find_post_node(data, post_url)
                if post:
                    print(f"   ✅ 從 HTML 直嵌找到貼文物件")
                    print(f"   🏷️ 物件類型: {post.get('__typename', 'Unknown')}")
                    return {"source": "html_embedded", "post": post}
                else:
                    print(f"   ❌ 在 __NEXT_DATA__ 中找不到貼文物件")
                    # 保存調試數據
                    debug_file = Path(f"debug_next_data_{datetime.now().strftime('%H%M%S')}.json")
                    with open(debug_file, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    print(f"   📁 已保存調試數據到: {debug_file}")
                    
                    # 顯示可用的頂層鍵以便調試
                    if isinstance(data, dict):
                        print(f"   🔍 __NEXT_DATA__ 頂層鍵: {list(data.keys())}")
            else:
                print(f"   ❌ 找到 __NEXT_DATA__ 標記但無法提取有效的 JSON")
                # 保存一小段 HTML 供調試
                html_snippet = html[html.find("__NEXT_DATA__"):html.find("__NEXT_DATA__") + 1000]
                print(f"   🔍 HTML 片段: {html_snippet[:200]}...")
                
        except Exception as e:
            print(f"   ❌ 解析 __NEXT_DATA__ 失敗: {e}")
            import traceback
            traceback.print_exc()
    
    # 模式2: Gate 頁 / 需要 GraphQL API
    else:
        print(f"   🚪 檢測到 Gate 頁模式，等待 GraphQL API...")
        
        # 設置 GraphQL 攔截器 - 分別存儲完整版和計數版
        captured_full = []     # 完整內容響應 (有 data.media)
        captured_counts = []   # 動態計數響應 (只有 counts)
        
        async def response_handler(response):
            url = response.url.lower()
            qname = response.request.headers.get("x-fb-friendly-name", "")
            is_graphql = "/graphql" in url and response.status == 200
            
            if not is_graphql:
                return
                
            try:
                data = await response.json()
                
                # ❶ 優先檢查 data.media：完整版一定會有 media
                if find_post_node(data, post_url):
                    print(f"   🟢 攔截到完整內容查詢: {qname or url}")
                    captured_full.append({
                        "data": data, 
                        "qname": qname,
                        "url": response.url
                    })
                # �②  檢查是否為動態計數查詢
                elif ("posts" in str(data) and "text_post_app_info" in str(data)) or "DynamicPostCountsSubscriptionQuery" in qname:
                    print(f"   🟡 攔截到動態計數查詢: {qname}")
                    captured_counts.append({
                        "data": data,
                        "qname": qname,
                        "url": response.url
                    })
                else:
                    print(f"   🔍 攔截到其他 GraphQL: {qname or 'Unknown'}")
                    
            except Exception as e:
                print(f"   ⚠️ 無法解析 GraphQL 響應: {e}")
        
        # 新增：自動補打完整內容 API 的函數
        async def fetch_full_post_by_pk(context, pk: str, typename: str = "XDTTextPost") -> Optional[Dict]:
            """根據 pk 自動補打完整內容 API"""
            DOC_IDS = {
                "XDTTextPost": "7248604598467997",
                "XDTPhoto": "7205124739579889", 
                "XDTVideo": "7110719515677565",
            }
            doc_id = DOC_IDS.get(typename, DOC_IDS["XDTTextPost"])
            variables = json.dumps({"postID": pk, "includePromotedPosts": False})
            
            try:
                print(f"   🔄 補打完整內容 API (pk: {pk}, type: {typename})")
                response = await context.request.post(
                    "https://www.threads.com/graphql/query",
                    data={"doc_id": doc_id, "variables": variables},
                    headers={"x-ig-app-id": "238260118697367"}
                )
                data = await response.json()
                post = find_post_node(data, "")
                if post:
                    print(f"   ✅ 成功補獲完整內容")
                    return post
                else:
                    print(f"   ❌ 補打 API 未找到貼文內容")
            except Exception as e:
                print(f"   ❌ 補打 API 失敗: {e}")
            return None
        
        page.on("response", response_handler)
        
        # 嘗試多種方式觸發 GraphQL 請求
        actions = [
            lambda: page.evaluate("window.scrollTo(0, 100)"),
            lambda: page.evaluate("window.scrollTo(0, 300)"),
            lambda: page.reload(),
            lambda: page.click("body") if page.locator("body").count() > 0 else None,
        ]
        
        for i, action in enumerate(actions):
            try:
                print(f"   🔄 嘗試觸發 GraphQL 請求 ({i+1}/{len(actions)})...")
                if action:
                    await action()
                await asyncio.sleep(3)
                
                if captured_full or captured_counts:
                    break
                    
            except Exception as e:
                print(f"   ⚠️ 動作 {i+1} 失敗: {e}")
                continue
        
        # 移除事件監聽器
        page.remove_listener("response", response_handler)
        
        # 智能分析和合併響應
        total_responses = len(captured_full) + len(captured_counts)
        print(f"   ✅ 成功攔截到 {total_responses} 個 GraphQL 響應")
        print(f"      🟢 完整內容響應: {len(captured_full)} 個")
        print(f"      🟡 動態計數響應: {len(captured_counts)} 個")
        
        final_post = None
        source_type = "unknown"
        query_name = "Unknown"
        
        # 策略1: 優先使用完整內容響應
        if captured_full:
            full_resp = captured_full[0]
            final_post = find_post_node(full_resp["data"], post_url)
            if final_post:
                print(f"   🎯 使用完整內容: {full_resp['qname']}")
                source_type = "full"
                query_name = full_resp["qname"]
                
                # 如果有計數數據，合併最新的計數
                if captured_counts:
                    count_post = find_post_node(captured_counts[0]["data"], post_url)
                    if count_post:
                        print(f"   🔄 合併最新計數數據...")
                        # 用計數版的數字覆蓋完整版
                        for key in ["like_count", "text_post_app_info"]:
                            if key in count_post:
                                final_post[key] = count_post[key]
                                print(f"      ↻ 更新 {key}")
        
        # 策略2: 回退到計數版，並嘗試補打完整內容 API
        elif captured_counts:
            count_resp = captured_counts[0]
            count_post = find_post_node(count_resp["data"], post_url)
            if count_post:
                print(f"   🟡 使用計數版: {count_resp['qname']}")
                
                # 嘗試從計數數據中提取 pk 和類型
                pk = count_post.get("pk") or count_post.get("id")
                typename = count_post.get("__typename", "XDTTextPost")
                
                if pk:
                    print(f"   🔄 嘗試補打完整內容 API...")
                    full_post_data = await fetch_full_post_by_pk(context, str(pk), typename)
                    
                    if full_post_data:
                        # 成功補獲完整內容，合併數據
                        print(f"   ✅ 成功合併 完整內容 + 最新計數")
                        # 用計數版的數字覆蓋完整版 
                        for key in ["like_count", "text_post_app_info"]:
                            if key in count_post:
                                full_post_data[key] = count_post[key]
                        
                        final_post = full_post_data
                        source_type = "merged"
                        query_name = f"{count_resp['qname']} + API補獲"
                    else:
                        # 補獲失敗，只能使用計數版
                        print(f"   ⚠️ 補獲失敗，僅使用計數數據")
                        final_post = count_post
                        source_type = "counts_only"
                        query_name = count_resp["qname"]
                else:
                    print(f"   ❌ 計數數據中找不到 pk，無法補獲完整內容")
                    final_post = count_post
                    source_type = "counts_only"
                    query_name = count_resp["qname"]
        
        if final_post:
            return {
                "source": "graphql_api",
                "post": final_post,
                "query_name": query_name,
                "source_type": source_type
            }
        
        # 如果沒找到貼文，保存調試數據
        all_responses = captured_full + captured_counts
        if all_responses:
            print(f"   ❌ 在所有 {len(all_responses)} 個 GraphQL 回應中都找不到貼文物件")
            debug_file = Path(f"debug_graphql_responses_{datetime.now().strftime('%H%M%S')}.json")
            with open(debug_file, 'w', encoding='utf-8') as f:
                json.dump(all_responses, f, indent=2, ensure_ascii=False)
            print(f"   📁 已保存所有響應數據到: {debug_file}")
        else:
            print(f"   ❌ 沒有攔截到任何 GraphQL 響應")
            print(f"   💡 建議檢查網路連線或認證狀態")
    
    return None

async def test_single_post_graphql(post_url: str, auth_file_path: Path) -> Optional[Dict[str, Any]]:
    """
    測試單則貼文的數據抓取 - 支援雙模式
    """
    print(f"\n🔍 測試貼文: {post_url}")
    
    # 從URL提取username
    parts = post_url.split("/")
    username = parts[3].replace("@", "") if len(parts) > 3 else "unknown"
    print(f"   👤 用戶: {username}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # 設為 False 以便觀察
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
        )
        
        context = await browser.new_context(
            storage_state=str(auth_file_path),
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="zh-TW",
            bypass_csp=True
        )
        
        # 隱藏 webdriver 屬性
        await context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
        
        page = await context.new_page()
        
        # 使用統一的處理函數
        result = await handle_graphql_or_html(page, post_url, username, context)
        
        await browser.close()
        
        if result:
            post_data = result["post"]
            source = result["source"]
            query_name = result.get("query_name", "Unknown")
            source_type = result.get("source_type", "unknown")
            
            print(f"\n📊 數據來源: {source}")
            print(f"   🔍 查詢名稱: {query_name}")
            print(f"   📋 來源類型: {source_type}")
            print(f"   🔄 開始解析貼文數據...")
            
            # 解析貼文數據
            parsed = parse_single_post_data(post_data, username)
            
            if parsed:
                print(f"\n✅ 解析成功:")
                print(f"   ID: {parsed.get('post_id')}")
                print(f"   類型: {parsed.get('typename')}")
                print(f"   作者: {parsed.get('author')}")
                print(f"   讚數: {parsed.get('like_count'):,}")
                print(f"   留言數: {parsed.get('comment_count'):,}")
                print(f"   分享數: {parsed.get('share_count'):,}")
                print(f"   轉發數: {parsed.get('repost_count'):,}")
                print(f"   瀏覽數: {parsed.get('view_count'):,}")
                print(f"   內容長度: {len(parsed.get('content', ''))}")
                print(f"   內容預覽: {parsed.get('content', '')[:100]}...")
                print(f"   可用欄位數量: {len(parsed.get('raw_keys', []))}")
                print(f"   可用欄位: {parsed.get('raw_keys', [])[:10]}...")  # 只顯示前10個
                
                # 加入詳細來源資訊
                parsed["data_source"] = source
                parsed["query_name"] = query_name
                parsed["source_type"] = source_type
                return {f"{source}_{source_type}_result": parsed}
            else:
                print(f"   ❌ 解析貼文數據失敗")
        else:
            print(f"   ❌ 未能獲取到貼文數據")
    
    return None

async def main():
    """
    主測試函數
    """
    print("🚀 GraphQL 單則貼文測試開始...")
    
    # 檢查認證檔案
    auth_file_path = get_auth_file_path()
    if not auth_file_path.exists():
        print(f"❌ 認證檔案不存在: {auth_file_path}")
        print("   請先執行 save_auth.py 生成認證檔案")
        return
    
    print(f"✅ 使用認證檔案: {auth_file_path}")
    
    # 測試每個貼文
    all_results = {}
    
    for i, post_url in enumerate(TEST_POST_URLS):
        print(f"\n{'='*50}")
        print(f"測試 {i+1}/{len(TEST_POST_URLS)}")
        
        try:
            results = await test_single_post_graphql(post_url, auth_file_path)
            if results:
                all_results[post_url] = results
            else:
                print(f"❌ 未能獲取到數據")
                
        except Exception as e:
            print(f"❌ 測試失敗: {e}")
            import traceback
            traceback.print_exc()
        
        # 延遲避免反爬蟲
        if i < len(TEST_POST_URLS) - 1:
            print(f"   ⏳ 延遲 3 秒...")
            await asyncio.sleep(3)
    
    # 保存結果
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_file = Path(f"graphql_test_results_{timestamp}.json")
    
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
    
    print(f"\n🎯 測試完成！")
    print(f"📁 結果已保存至: {result_file}")
    print(f"📊 成功測試貼文數: {len(all_results)}")

if __name__ == "__main__":
    asyncio.run(main())