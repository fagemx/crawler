import asyncio
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Any
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# --- 設定 ---
# 用戶名稱（從您想查看的貼文 URL 中提取）
TARGET_USERNAME = "starettoday"  # 從 @starettoday/post/DMuhToby7Ip 提取
# 改為訪問用戶首頁，這樣能觸發 GraphQL 請求
TARGET_URL = f"https://www.threads.com/@{TARGET_USERNAME}"

# 認證檔案的路徑 (與 test_playwright_agent.py 同步)
try:
    from common.config import get_auth_file_path
    AUTH_FILE_PATH = get_auth_file_path(from_project_root=True)
except (ImportError, ModuleNotFoundError):
    print("⚠️ 警告：無法從 common.config 導入。將使用相對路徑。")
    # 當作為獨立腳本執行時，提供一個備用路徑
    AUTH_FILE_PATH = Path(__file__).parent.parent / "secrets" / "auth.json"


# 輸出檔案名稱
OUTPUT_FILE = "graphql_output.json"

async def main():
    """主執行函式"""
    if not AUTH_FILE_PATH.exists():
        print(f"❌ 錯誤：找不到認證檔案，請確認 '{AUTH_FILE_PATH}' 是否存在。")
        return

    print(f"🚀 準備啟動瀏覽器，目標 URL: {TARGET_URL}")

    # 用來儲存我們攔截到的 GraphQL 回應
    graphql_response_future = asyncio.Future()

    # 用來收集所有的 GraphQL 回應
    all_graphql_responses = []
    
    def parse_timestamp(ts: Any) -> Optional[datetime]:
        """傳回 datetime，或 None"""
        if ts is None:
            return None
        try:
            ts = int(ts)
            return datetime.utcfromtimestamp(ts)
        except (ValueError, TypeError):
            return None

    def is_root_post(item: dict) -> bool:
        """檢查這筆 thread_item 是不是主文（非回覆）"""
        return (
            item.get("thread_item_type") in (3, "post")      # 3 = main post
            or item.get("is_head") is True                    # 有些 schema 直接給布林
            or item.get("reply_to_author") is None            # 沒有回覆對象
            or item.get("reply_to") is None                   # 另一種回覆檢查
        )

    def extract_and_sort_posts(all_responses: list) -> list:
        """從所有 GraphQL 回應中提取並排序貼文（模仿前端完整流程）"""
        all_posts = {}  # 使用字典去重
        
        print(f"🔍 開始處理 {len(all_responses)} 個 GraphQL 回應...")
        
        # ① 遍歷所有回應，提取所有可能的 edges
        for resp_idx, response in enumerate(all_responses):
            data = response["data"]
            data_content = data.get("data", {})
            
            if not isinstance(data_content, dict):
                continue
                
            # 檢查多種可能的 edges 路徑
            edges_sources = [
                # 一般貼文
                ("mediaData", data_content.get("mediaData", {}).get("edges", [])),
                # 用戶資料中的貼文
                ("userData.user.mediaData", 
                 data_content.get("userData", {}).get("user", {}).get("mediaData", {}).get("edges", [])),
                # 其他可能的路徑
                ("viewerMediaData", data_content.get("viewerMediaData", {}).get("edges", [])),
            ]
            
            for source_name, edges in edges_sources:
                if not edges:
                    continue
                    
                print(f"  📡 回應 {resp_idx+1} - {source_name}: 找到 {len(edges)} 個 edges")
                
                for edge in edges:
                    if not isinstance(edge, dict) or "node" not in edge:
                        continue
                        
                    node = edge["node"]
                    
                    # 處理 thread_items 結構
                    thread_items = node.get("thread_items") or node.get("items") or []
                    
                    # ② 只保留主文，過濾回覆
                    for thread_item in filter(is_root_post, thread_items):
                        # 除錯：顯示 thread_item 的頂層結構
                        if thread_item and isinstance(thread_item, dict):
                            print(f"    🔍 除錯: thread_item 頂層鍵值: {list(thread_item.keys())}")
                        
                        # 解析時間戳
                        raw_ts = None
                        for time_field in ["taken_at", "taken_at_timestamp", "created_time", "publish_date"]:
                            if time_field in thread_item:
                                raw_ts = thread_item[time_field]
                                print(f"    📅 找到時間欄位 {time_field}: {raw_ts}")
                                break
                        
                        created_at = parse_timestamp(raw_ts)
                        
                        # 更強健的 ID 提取（加強除錯）
                        id_fields = ["pk", "id", "post_id", "code", "code_media_tree"]
                        post_id = "unknown"
                        for id_field in id_fields:
                            if id_field in thread_item and thread_item[id_field]:
                                post_id = str(thread_item[id_field])
                                print(f"    🆔 找到 ID 欄位 {id_field}: {post_id}")
                                break
                        
                        if post_id == "unknown":
                            print(f"    ⚠️ 未找到有效的 ID，可用欄位: {list(thread_item.keys())}")
                        
                        # 檢查是否為置頂貼文
                        is_pinned = bool(
                            thread_item.get("is_highlighted") or 
                            thread_item.get("highlight_info") or
                            (thread_item.get("badge", {}).get("text") == "Pinned")
                        )
                        
                        # 提取內容（加強除錯）
                        content = ""
                        if "caption" in thread_item and isinstance(thread_item["caption"], dict):
                            content = thread_item["caption"].get("text", "")
                            print(f"    📝 從 caption.text 找到內容: {content[:30]}...")
                        elif "text" in thread_item:
                            content = str(thread_item["text"])
                            print(f"    📝 從 text 找到內容: {content[:30]}...")
                        else:
                            print(f"    ⚠️ 未找到內容，可用欄位: {[k for k in thread_item.keys() if 'text' in k.lower() or 'caption' in k.lower()]}")
                        
                        # 去重：同一篇貼文可能出現在多個回應中
                        if post_id not in all_posts:
                            all_posts[post_id] = {
                                "post_id": post_id,
                                "created_at": created_at,
                                "timestamp": raw_ts,
                                "is_pinned": is_pinned,
                                "content": content[:50] + "..." if len(content) > 50 else content,
                                "source": f"回應{resp_idx+1}-{source_name}",
                                "raw_data": thread_item
                            }
                            print(f"    ✅ 成功解析貼文: ID={post_id}, 時間={raw_ts}, 內容長度={len(content)}")
                        else:
                            print(f"    🔄 跳過重複貼文: {post_id}")
        
        print(f"  🎯 去重後共找到 {len(all_posts)} 篇獨特貼文")
        
        # ③ 統一排序：置頂最前，其餘依時間倒序
        final_posts = list(all_posts.values())
        final_posts.sort(
            key=lambda p: (
                0 if p["is_pinned"] else 1,                          # 先置頂
                -(p["created_at"].timestamp() if p["created_at"] else 0)  # 再依時間倒序
            )
        )
        
        return final_posts


    def convert_to_playwright_format(posts: list, username: str) -> dict:
        """
        將 GraphQL 解析的貼文轉換為 playwright_logic.py 的 PostMetricsBatch 格式
        """
        playwright_posts = []
        
        for post in posts:
            # 計算權重分數 (使用與 PostMetrics.calculate_score 相同的邏輯)
            views = post.get('views_count', 0) or 0
            likes = post.get('likes_count', 0) or 0
            comments = post.get('comments_count', 0) or 0
            reposts = post.get('reposts_count', 0) or 0
            shares = post.get('shares_count', 0) or 0
            
            calculated_score = (
                views * 1.0 +           # 主要權重
                likes * 0.3 +           # 次要權重
                comments * 0.3 +        # 次要權重
                reposts * 0.1 +         # 較低權重
                shares * 0.1            # 較低權重
            )
            
            # 轉換為 PostMetrics 格式
            playwright_post = {
                "post_id": post.get('post_id', 'unknown'),
                "username": username,
                "url": f"https://www.threads.com/@{username}/post/{post.get('post_id', '')}",
                "content": post.get('content', ''),
                "likes_count": likes,
                "comments_count": comments,
                "reposts_count": reposts,
                "shares_count": shares,
                "views_count": views,
                "images": post.get('images', []),
                "videos": post.get('videos', []),
                "created_at": post.get('created_at').isoformat() if post.get('created_at') else datetime.now().isoformat(),
                "fetched_at": datetime.now().isoformat(),
                "views_fetched_at": None,
                "source": "graphql",
                "processing_stage": "graphql_parsed",
                "is_complete": views > 0,  # 如果有瀏覽數就算完整
                "last_updated": datetime.now().isoformat(),
                "calculated_score": calculated_score,
                "is_pinned": post.get('is_pinned', False)
            }
            
            playwright_posts.append(playwright_post)
        
        # 建立 PostMetricsBatch 格式
        batch_data = {
            "batch_id": f"graphql-test-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            "username": username,
            "total_count": len(playwright_posts),
            "current_count": len(playwright_posts),
            "processing_stage": "completed",
            "posts": playwright_posts,
            "created_at": datetime.now().isoformat(),
            "completed_at": datetime.now().isoformat(),
            "metadata": {
                "source": "graphql_direct",
                "extraction_method": "view_single_post_graphql.py",
                "total_posts_found": len(playwright_posts)
            }
        }
        
        return batch_data

    def _analyze_post_order(items, structure_name, is_edges=True):
        """分析貼文排序"""
        print(f"    📊 分析 {structure_name} 的貼文順序:")
        
        # 先過濾出主文
        main_posts = []
        for i, item in enumerate(items):
            # 如果是 edges 格式，提取 node
            if is_edges and isinstance(item, dict) and "node" in item:
                post_data = item["node"]
            else:
                post_data = item
            
            # 檢查是否有 thread_items（Threads 的特殊結構）
            if isinstance(post_data, dict) and "thread_items" in post_data:
                thread_items = post_data.get("thread_items", [])
                # 只取主文（通常是第一個，且符合 is_root_post 條件）
                for thread_item in thread_items:
                    if is_root_post(thread_item):
                        main_posts.append((i, thread_item))
                        break  # 每個 post_data 只取一個主文
            else:
                # 直接是貼文資料
                if is_root_post(post_data):
                    main_posts.append((i, post_data))
        
        print(f"      🎯 過濾後找到 {len(main_posts)} 個主文（原始 {len(items)} 個項目）")
        
        # 分析主文的時間順序
        posts_with_time = []
        for original_index, post_data in main_posts:
            # 尋找可能的時間欄位
            timestamp = None
            for time_field in ["taken_at", "taken_at_timestamp", "created_time", "publish_date"]:
                if time_field in post_data:
                    timestamp = post_data[time_field]
                    break
            
            # 尋找可能的 ID 欄位
            post_id = post_data.get("pk") or post_data.get("id") or post_data.get("post_id", "unknown")
            
            # 尋找可能的內容欄位
            content = ""
            if "caption" in post_data and isinstance(post_data["caption"], dict):
                content = post_data["caption"].get("text", "")[:30]
            elif "text" in post_data:
                content = str(post_data["text"])[:30]
            
            posts_with_time.append({
                "original_index": original_index,
                "post_id": post_id,
                "timestamp": timestamp,
                "content": content
            })
        
        # 按時間排序（最新在前）
        posts_with_time.sort(key=lambda x: x["timestamp"] or 0, reverse=True)
        
        print(f"      📅 按時間排序後的順序（最新→最舊）:")
        for i, post in enumerate(posts_with_time):
            # 轉換時間戳為可讀格式
            if post["timestamp"]:
                try:
                    from datetime import datetime
                    dt = datetime.fromtimestamp(post["timestamp"])
                    time_str = dt.strftime("%m-%d %H:%M")
                except:
                    time_str = str(post["timestamp"])
            else:
                time_str = "無時間"
            
            print(f"        {i+1}. ID: {post['post_id']}, 時間: {time_str}, 內容: {post['content']}...")
        
        # 檢查是否已經是時間順序
        original_order = [p["timestamp"] or 0 for p in posts_with_time]
        api_order = [posts_with_time[i]["timestamp"] or 0 for i in range(len(posts_with_time))]
        
        if original_order == sorted(original_order, reverse=True):
            print(f"      ✅ API 回傳順序已經是時間順序（最新→最舊）")
        else:
            print(f"      ⚠️ API 回傳順序不是時間順序，需要前端重新排序")
    
    async def handle_response(response):
        """處理並攔截 GraphQL 回應"""
        # 我們關心所有包含 'graphql' 的 API 請求
        if "graphql" in response.url.lower():
            try:
                data = await response.json()
                print(f"🔍 發現 GraphQL 回應 from: {response.url}")
                print(f"📊 回應大小: {len(str(data))} 字元")
                
                # 顯示回應的頂層結構
                if isinstance(data, dict):
                    top_keys = list(data.keys())
                    print(f"🗂️ 頂層鍵值: {top_keys}")
                    
                    # 檢查是否包含貼文相關資料
                    data_section = data.get("data", {})
                    if data_section:
                        data_keys = list(data_section.keys()) if isinstance(data_section, dict) else []
                        print(f"📁 data 區塊的鍵值: {data_keys}")
                
                # 收集所有回應
                all_graphql_responses.append({
                    "url": response.url,
                    "data": data
                })
                
                # 如果這是第一個看起來有意義的回應，就使用它
                if not graphql_response_future.done():
                    # 檢查多種可能的貼文資料結構
                    has_thread_data = (
                        data.get("data", {}).get("data", {}).get("thread_items") or  # 原本的檢查
                        data.get("data", {}).get("thread_items") or  # 可能的變化
                        data.get("data", {}).get("data", {}).get("post") or  # 單篇貼文
                        data.get("data", {}).get("post") or  # 另一種可能
                        data.get("data", {}).get("mediaData") or  # 媒體資料
                        data.get("data", {}).get("user") or  # 用戶資料
                        data.get("data", {}) and len(str(data)) > 2000  # 任何大型回應都可能包含我們要的資料
                    )
                    
                    # 嘗試找出貼文相關的內容並顯示概要
                    data_content = data.get("data", {})
                    if isinstance(data_content, dict):
                        for key, value in data_content.items():
                            if isinstance(value, dict) and "edges" in value:
                                edges = value.get("edges", [])
                                if edges:
                                    print(f"🎯 發現可能的貼文資料結構: {key} (包含 {len(edges)} 個項目)")
                                    
                                    # 檢查分頁資訊
                                    page_info = value.get("page_info", {})
                                    if page_info:
                                        has_next = page_info.get("has_next_page", False)
                                        end_cursor = page_info.get("end_cursor", "")
                                        print(f"📄 分頁資訊:")
                                        print(f"    has_next_page: {has_next}")
                                        if end_cursor:
                                            print(f"    end_cursor: {end_cursor[:50]}...")
                                        else:
                                            print(f"    end_cursor: None")
                                        
                                        if has_next:
                                            print(f"    ⚠️ 警告：這只是第一頁！還有更多貼文在後續頁面")
                                        else:
                                            print(f"    ✅ 這是完整的資料（無更多頁面）")
                                    else:
                                        print(f"    ⚠️ 未找到分頁資訊")
                                    
                                    # 嘗試提取前幾篇貼文的時間來檢查排序
                                    _analyze_post_order(edges[:3], key)
                            elif isinstance(value, list) and len(value) > 0:
                                print(f"🎯 發現列表資料: {key} (包含 {len(value)} 個項目)")
                                # 如果是直接的貼文列表，也分析排序
                                if len(value) > 0 and isinstance(value[0], dict):
                                    _analyze_post_order(value[:3], key, is_edges=False)
                        
                        if has_thread_data:
                            print(f"✅ 選定此回應作為主要資料來源")
                            graphql_response_future.set_result(data)
                        
            except Exception as e:
                print(f"⚠️ 解析 GraphQL 回應時發生錯誤: {e}")
                print(f"   回應 URL: {response.url}")
                print(f"   狀態碼: {response.status}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(storage_state=str(AUTH_FILE_PATH))
        page = await context.new_page()

        # 設定回應監聽器
        page.on("response", handle_response)

        try:
            print(f"🧭 正在導覽至頁面...")
            await page.goto(TARGET_URL, wait_until="networkidle", timeout=30000)

            print("⏳ 頁面已載入，開始滾動以觸發貼文載入...")
            
            # 進行幾次滾動來觸發貼文載入
            for i in range(3):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)  # 等待網路請求
                print(f"📜 完成滾動 {i+1}/3")
                
                # 檢查是否已經得到我們想要的資料
                if graphql_response_future.done():
                    break
                
                print("⏳ 等待 GraphQL 回應...")
            
            # 等待 GraphQL 回應
            result_json = await asyncio.wait_for(graphql_response_future, timeout=20.0)
            
            print("\n" + "="*50)
            print("🎉 成功獲取 GraphQL 完整內容！")
            print("="*50 + "\n")
            
            # 提取並排序所有找到的貼文
            print(f"🔍 開始處理 {len(all_graphql_responses)} 個 GraphQL 回應...")
            sorted_posts = extract_and_sort_posts(all_graphql_responses)
            
            if sorted_posts:
                print("📋 提取並排序後的貼文列表（正確的時間順序）:")
                print("-" * 60)
                for i, post in enumerate(sorted_posts[:10]):  # 只顯示前10篇
                    time_str = "無時間"
                    if post["created_at"]:
                        time_str = post["created_at"].strftime("%m-%d %H:%M")
                    
                    pin_indicator = "📌" if post["is_pinned"] else "  "
                    print(f"{pin_indicator} {i+1:2d}. ID: {post['post_id']}")
                    print(f"      時間: {time_str} | 來源: {post['source']}")
                    print(f"      內容: {post['content']}")
                    print()
                
                print(f"✅ 總共提取到 {len(sorted_posts)} 篇主文貼文")
                print("📌 = 置頂貼文")
                
                # 檢查順序是否正確
                non_pinned = [p for p in sorted_posts if not p["is_pinned"]]
                if len(non_pinned) > 1:
                    timestamps = [p["created_at"].timestamp() if p["created_at"] else 0 for p in non_pinned]
                    is_desc_order = all(timestamps[i] >= timestamps[i+1] for i in range(len(timestamps)-1))
                    if is_desc_order:
                        print("✅ 非置頂貼文已按時間正確排序（最新→最舊）")
                    else:
                        print("⚠️ 非置頂貼文的時間順序仍有問題")
            else:
                print("⚠️ 未能從 GraphQL 回應中提取到貼文資料")

            # 美化並顯示原始 JSON
            print("\n" + "="*50)
            print("📄 原始 GraphQL 回應內容:")
            print("="*50 + "\n")
            pretty_json = json.dumps(result_json, indent=2, ensure_ascii=False)
            print(pretty_json)

            # 儲存到檔案
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                f.write(pretty_json)
            print(f"\n✅ 原始內容已儲存至檔案: {OUTPUT_FILE}")
            
            # 儲存排序後的貼文（使用 Playwright 格式）
            if sorted_posts:
                sorted_file = "sorted_posts.json"
                
                # 轉換為 playwright_logic 格式
                playwright_format = convert_to_playwright_format(sorted_posts, TARGET_USERNAME)
                
                with open(sorted_file, 'w', encoding='utf-8') as f:
                    json.dump(playwright_format, f, indent=2, ensure_ascii=False, default=str)
                print(f"✅ Playwright 格式的貼文已儲存至檔案: {sorted_file}")
                
                # 顯示與 test_playwright_agent.py 相同的摘要格式
                posts = playwright_format.get("posts", [])
                print("\n--- 測試結果摘要 (Playwright 格式) ---")
                print(f"批次 ID: {playwright_format.get('batch_id')}")
                print(f"使用者: {playwright_format.get('username')}")
                print(f"處理階段: {playwright_format.get('processing_stage')}")
                print(f"總計數量: {playwright_format.get('total_count')}")
                print(f"成功爬取貼文數: {len(posts)}")
                print("----------------------\n")
                
                if posts:
                    print("--- 前 3 則貼文預覽 (Playwright 格式) ---")
                    for i, post in enumerate(posts[:3]):
                        print(f"{i+1}. ID: {post.get('post_id', 'N/A')}")
                        print(f"   作者: {post.get('username', 'N/A')}")
                        print(f"   ❤️ 讚: {post.get('likes_count', 0):,}")
                        print(f"   💬 留言: {post.get('comments_count', 0):,}")
                        print(f"   🔄 轉發: {post.get('reposts_count', 0):,}")
                        print(f"   📤 分享: {post.get('shares_count', 0):,}")
                        print(f"   👁️ 瀏覽: {post.get('views_count', 0):,}")
                        print(f"   ⭐ 分數: {post.get('calculated_score', 0):.1f}")
                        print(f"   📌 置頂: {post.get('is_pinned', False)}")
                        print(f"   網址: {post.get('url', 'N/A')}")
                        content_preview = post.get('content', '')[:50] + "..." if len(post.get('content', '')) > 50 else post.get('content', '')
                        print(f"   內容: {content_preview}")
                        print()

        except asyncio.TimeoutError:
            print("\n❌ 錯誤：在 20 秒內沒有攔截到有效的 GraphQL 回應。")
            print("   可能原因：")
            print("   1. 該貼文可能不存在或為私人內容。")
            print("   2. Threads API 結構可能已變更。")
            print("   3. 您的網路連線或認證可能已過期。")
            
            # 顯示我們收集到的所有 GraphQL 回應摘要
            if all_graphql_responses:
                print(f"\n📋 但我們確實攔截到了 {len(all_graphql_responses)} 個 GraphQL 回應：")
                for i, resp in enumerate(all_graphql_responses, 1):
                    print(f"   {i}. URL: {resp['url']}")
                    print(f"      大小: {len(str(resp['data']))} 字元")
                    if isinstance(resp['data'], dict):
                        data_keys = list(resp['data'].get('data', {}).keys()) if resp['data'].get('data') else []
                        print(f"      資料鍵值: {data_keys}")
                    print()
                
                # 如果有回應但沒有符合我們條件的，就使用最大的那個
                if all_graphql_responses:
                    largest_response = max(all_graphql_responses, key=lambda x: len(str(x['data'])))
                    print(f"\n💡 將使用最大的回應 ({len(str(largest_response['data']))} 字元) 作為輸出...")
                    result_json = largest_response['data']
            else:
                print("\n🔍 沒有攔截到任何 GraphQL 回應。")
                print("   這可能表示認證已過期或網站結構已大幅變更。")
                result_json = None
                
            # 如果有找到任何資料，就輸出它
            if result_json:
                print("\n" + "="*50)
                print("🎉 找到 GraphQL 內容（來自回退邏輯）！")
                print("="*50 + "\n")
                
                # 即使是回退邏輯，也嘗試提取並排序貼文
                sorted_posts = extract_and_sort_posts(all_graphql_responses)
                
                if sorted_posts:
                    print("📋 提取並排序後的貼文列表（正確的時間順序）:")
                    print("-" * 60)
                    for i, post in enumerate(sorted_posts[:10]):  # 只顯示前10篇
                        time_str = "無時間"
                        if post["created_at"]:
                            time_str = post["created_at"].strftime("%m-%d %H:%M")
                        
                        pin_indicator = "📌" if post["is_pinned"] else "  "
                        print(f"{pin_indicator} {i+1:2d}. ID: {post['post_id']}")
                        print(f"      時間: {time_str} | 來源: {post['source']}")
                        print(f"      內容: {post['content']}")
                        print()
                    
                    print(f"✅ 總共提取到 {len(sorted_posts)} 篇主文貼文")
                
                pretty_json = json.dumps(result_json, indent=2, ensure_ascii=False)
                print(f"\n📄 原始 GraphQL 回應內容:")
                print(pretty_json)
                
                # 儲存到檔案
                with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                    f.write(pretty_json)
                print(f"\n✅ 內容已儲存至檔案: {OUTPUT_FILE}")
                
                # 儲存排序後的貼文（使用 Playwright 格式）
                if sorted_posts:
                    sorted_file = "sorted_posts.json"
                    
                    # 轉換為 playwright_logic 格式
                    playwright_format = convert_to_playwright_format(sorted_posts, TARGET_USERNAME)
                    
                    with open(sorted_file, 'w', encoding='utf-8') as f:
                        json.dump(playwright_format, f, indent=2, ensure_ascii=False, default=str)
                    print(f"✅ Playwright 格式的貼文已儲存至檔案: {sorted_file}")
                    
                    # 顯示摘要格式
                    posts = playwright_format.get("posts", [])
                    print(f"\n--- 回退結果摘要 (Playwright 格式) ---")
                    print(f"批次 ID: {playwright_format.get('batch_id')}")
                    print(f"使用者: {playwright_format.get('username')}")
                    print(f"總計數量: {playwright_format.get('total_count')}")
                    print(f"成功提取貼文數: {len(posts)}")
                    print("----------------------")
        except Exception as e:
            print(f"\n❌ 發生未預期的錯誤: {e}")
        finally:
            await browser.close()
            print("\n🛑 瀏覽器已關閉。")

if __name__ == "__main__":
    asyncio.run(main())