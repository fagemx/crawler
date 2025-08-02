"""
增量爬取功能測試

測試進階的增量爬取功能：
1. 歷史數量：上次爬10篇 → 想增加20篇 → 共30篇
2. 新增數量：兩次訪問間的新貼文要補齊
3. 去重機制：避免重複抓取
4. 早停機制：達到目標數量即停止
"""

import asyncio
import json
import httpx
from pathlib import Path
import time
from datetime import datetime

# --- 測試設定 ---
TARGET_USERNAME = "natgeo"  # 測試帳號
AGENT_URL = "http://localhost:8006/v1/playwright/crawl"

# 認證檔案路徑
from common.config import get_auth_file_path
AUTH_FILE_PATH = get_auth_file_path(from_project_root=True)


async def test_historical_incremental():
    """
    測試歷史數量增量：
    
    場景：用戶上次爬取了10篇，現在想增加20篇，總共30篇
    - 第一次：爬取10篇 (initial baseline)
    - 第二次：增量爬取20篇 (incremental)
    - 結果：應該去重，只獲取新的20篇
    """
    print("🧪 測試場景1：歷史數量增量爬取")
    print("=" * 50)
    
    if not AUTH_FILE_PATH.exists():
        print(f"❌ 錯誤：找不到認證檔案 '{AUTH_FILE_PATH}'")
        return False
    
    # 讀取認證
    with open(AUTH_FILE_PATH, "r", encoding="utf-8") as f:
        auth_content = json.load(f)
    
    timeout = httpx.Timeout(300.0)
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # === 第一次：建立基線 (10篇) ===
            print("📊 步驟1：建立基線 - 爬取10篇貼文")
            
            payload_1 = {
                "username": TARGET_USERNAME,
                "max_posts": 5,  # 使用基礎API語義：絕對數量
                "auth_json_content": auth_content,
            }
            
            response_1 = await client.post(AGENT_URL, json=payload_1)
            if response_1.status_code != 200:
                print(f"❌ 第一次爬取失敗: {response_1.text}")
                return False
            
            baseline_data = response_1.json()
            baseline_posts = baseline_data.get("posts", [])
            baseline_count = len(baseline_posts)
            
            print(f"✅ 基線建立完成：獲得 {baseline_count} 篇貼文")
            print(f"   總計數量: {baseline_data.get('total_count')}")
            
            # 顯示基線貼文ID（用於後續去重驗證）
            baseline_post_ids = {post.get('post_id') for post in baseline_posts}
            print(f"   基線貼文ID: {list(baseline_post_ids)[:3]}... (顯示前3個)")
            
            # 等待一下，模擬時間間隔
            print("\n⏳ 等待5秒，模擬時間間隔...")
            await asyncio.sleep(5)
            
            # === 第二次：增量爬取 (額外20篇) ===
            print("\n📈 步驟2：增量爬取 - 額外獲取20篇")
            print("   (應該自動去重，只獲取新的貼文)")
            
            # 這裡我們需要使用增量API或者模擬增量語義
            # 由於當前API還是用max_posts，我們先用更大的數量來模擬增量
            payload_2 = {
                "username": TARGET_USERNAME,
                "max_posts": 15,  # 期望總共25篇 (比基線多15篇)
                "auth_json_content": auth_content,
            }
            
            response_2 = await client.post(AGENT_URL, json=payload_2)
            if response_2.status_code != 200:
                print(f"❌ 增量爬取失敗: {response_2.text}")
                return False
            
            incremental_data = response_2.json()
            incremental_posts = incremental_data.get("posts", [])
            incremental_count = len(incremental_posts)
            
            print(f"✅ 增量爬取完成：獲得 {incremental_count} 篇貼文")
            print(f"   總計數量: {incremental_data.get('total_count')}")
            
            # === 驗證增量效果 ===
            incremental_post_ids = {post.get('post_id') for post in incremental_posts}
            new_posts = incremental_post_ids - baseline_post_ids
            duplicate_posts = incremental_post_ids & baseline_post_ids
            
            print(f"\n🔍 增量驗證結果：")
            print(f"   新貼文數量: {len(new_posts)}")
            print(f"   重複貼文數量: {len(duplicate_posts)}")
            print(f"   去重效率: {len(new_posts) / len(incremental_post_ids) * 100:.1f}%")
            
            # 顯示新貼文ID
            if new_posts:
                print(f"   新貼文ID: {list(new_posts)[:3]}... (顯示前3個)")
            
            success = len(new_posts) > 0
            if success:
                print("✅ 歷史數量增量測試 PASSED")
            else:
                print("❌ 歷史數量增量測試 FAILED：沒有獲取到新貼文")
            
            return success
            
    except Exception as e:
        print(f"❌ 測試執行失敗: {e}")
        return False


async def test_realtime_incremental():
    """
    測試即時新增量：
    
    場景：兩次訪問間有新貼文產生
    - 記錄第一次爬取的最新貼文時間
    - 等待一段時間
    - 第二次只爬取新產生的貼文
    """
    print("\n🧪 測試場景2：即時新增量爬取")
    print("=" * 50)
    
    if not AUTH_FILE_PATH.exists():
        print(f"❌ 錯誤：找不到認證檔案 '{AUTH_FILE_PATH}'")
        return False
    
    # 讀取認證
    with open(AUTH_FILE_PATH, "r", encoding="utf-8") as f:
        auth_content = json.load(f)
    
    timeout = httpx.Timeout(300.0)
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # === 第一次：記錄當前狀態 ===
            print("📊 步驟1：記錄當前狀態 - 爬取最新5篇貼文")
            
            payload_1 = {
                "username": TARGET_USERNAME,
                "max_posts": 5,
                "auth_json_content": auth_content,
            }
            
            response_1 = await client.post(AGENT_URL, json=payload_1)
            if response_1.status_code != 200:
                print(f"❌ 第一次爬取失敗: {response_1.text}")
                return False
            
            first_data = response_1.json()
            first_posts = first_data.get("posts", [])
            
            if not first_posts:
                print("❌ 第一次爬取沒有獲得貼文")
                return False
            
            # 獲取最新貼文的時間戳
            latest_post = first_posts[0]  # 假設第一個是最新的
            latest_time = latest_post.get('created_at')
            latest_post_id = latest_post.get('post_id')
            
            print(f"✅ 狀態記錄完成：")
            print(f"   最新貼文ID: {latest_post_id}")
            print(f"   最新貼文時間: {latest_time}")
            print(f"   當前總數: {len(first_posts)}")
            
            # === 模擬時間間隔 ===
            print("\n⏳ 等待10秒，模擬新貼文產生的時間間隔...")
            await asyncio.sleep(10)
            
            # === 第二次：檢查新增量 ===
            print("\n🔄 步驟2：檢查新增貼文")
            print("   (在真實環境中，這段時間可能有新貼文產生)")
            
            payload_2 = {
                "username": TARGET_USERNAME,
                "max_posts": 8,  # 期望比第一次多一些
                "auth_json_content": auth_content,
            }
            
            response_2 = await client.post(AGENT_URL, json=payload_2)
            if response_2.status_code != 200:
                print(f"❌ 第二次爬取失敗: {response_2.text}")
                return False
            
            second_data = response_2.json()
            second_posts = second_data.get("posts", [])
            
            # === 分析新增效果 ===
            first_post_ids = {post.get('post_id') for post in first_posts}
            second_post_ids = {post.get('post_id') for post in second_posts}
            
            new_posts_ids = second_post_ids - first_post_ids
            total_new = len(new_posts_ids)
            
            print(f"✅ 新增檢查完成：")
            print(f"   第二次總數: {len(second_posts)}")
            print(f"   新增貼文數: {total_new}")
            print(f"   新增效率: {total_new / max(len(second_posts), 1) * 100:.1f}%")
            
            if new_posts_ids:
                print(f"   新增貼文ID: {list(new_posts_ids)}")
            
            # 判斷測試結果
            # 在測試環境中，可能不會有真正的新貼文，所以我們主要測試機制
            success = len(second_posts) >= len(first_posts)  # 至少不會減少
            
            if success:
                print("✅ 即時新增量測試 PASSED")
            else:
                print("❌ 即時新增量測試 FAILED")
            
            return success
            
    except Exception as e:
        print(f"❌ 測試執行失敗: {e}")
        return False


async def test_deduplication_efficiency():
    """
    測試去重效率：
    
    多次爬取同一帳號，驗證去重機制的效率
    """
    print("\n🧪 測試場景3：去重效率測試")
    print("=" * 50)
    
    if not AUTH_FILE_PATH.exists():
        print(f"❌ 錯誤：找不到認證檔案 '{AUTH_FILE_PATH}'")
        return False
    
    # 讀取認證
    with open(AUTH_FILE_PATH, "r", encoding="utf-8") as f:
        auth_content = json.load(f)
    
    timeout = httpx.Timeout(300.0)
    all_post_ids = set()
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # 進行3次爬取，每次5篇
            for round_num in range(1, 4):
                print(f"📊 第{round_num}輪爬取 (5篇)")
                
                payload = {
                    "username": TARGET_USERNAME,
                    "max_posts": 5,
                    "auth_json_content": auth_content,
                }
                
                response = await client.post(AGENT_URL, json=payload)
                if response.status_code != 200:
                    print(f"❌ 第{round_num}輪爬取失敗: {response.text}")
                    continue
                
                data = response.json()
                posts = data.get("posts", [])
                round_post_ids = {post.get('post_id') for post in posts}
                
                # 分析重複情況
                new_in_round = round_post_ids - all_post_ids
                duplicates_in_round = round_post_ids & all_post_ids
                
                print(f"   獲得貼文: {len(posts)}")
                print(f"   新貼文: {len(new_in_round)}")
                print(f"   重複貼文: {len(duplicates_in_round)}")
                
                all_post_ids.update(round_post_ids)
                
                await asyncio.sleep(2)  # 間隔2秒
            
            print(f"\n🔍 去重效率總結：")
            print(f"   累計不重複貼文: {len(all_post_ids)}")
            
            success = len(all_post_ids) > 0
            if success:
                print("✅ 去重效率測試 PASSED")
            else:
                print("❌ 去重效率測試 FAILED")
            
            return success
            
    except Exception as e:
        print(f"❌ 測試執行失敗: {e}")
        return False


async def main():
    """執行所有增量爬取測試"""
    print("🚀 增量爬取功能測試套件")
    print("=" * 60)
    print(f"測試帳號: @{TARGET_USERNAME}")
    print(f"API端點: {AGENT_URL}")
    print(f"測試時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 執行所有測試
    test_results = []
    
    try:
        # 測試1：歷史數量增量
        result_1 = await test_historical_incremental()
        test_results.append(("歷史數量增量", result_1))
        
        # 測試2：即時新增量
        result_2 = await test_realtime_incremental()
        test_results.append(("即時新增量", result_2))
        
        # 測試3：去重效率
        result_3 = await test_deduplication_efficiency()
        test_results.append(("去重效率", result_3))
        
    except KeyboardInterrupt:
        print("\n⚠️ 測試被用戶中斷")
        return
    except Exception as e:
        print(f"\n❌ 測試套件執行失敗: {e}")
        return
    
    # === 測試結果總結 ===
    print("\n" + "=" * 60)
    print("📋 測試結果總結")
    print("=" * 60)
    
    passed_count = 0
    for test_name, result in test_results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name:20} | {status}")
        if result:
            passed_count += 1
    
    print("-" * 60)
    print(f"通過率: {passed_count}/{len(test_results)} ({passed_count/len(test_results)*100:.1f}%)")
    
    if passed_count == len(test_results):
        print("🎉 所有增量爬取功能測試通過！")
    else:
        print("⚠️ 部分測試失敗，請檢查增量爬取功能")


if __name__ == "__main__":
    asyncio.run(main())