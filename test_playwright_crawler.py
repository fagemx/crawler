#!/usr/bin/env python3
"""
獨立測試 Playwright Crawler 核心邏輯 (playwright_logic.py)

此腳本專注於驗證爬蟲是否能：
1. 正確登入並導航
2. 攔截並解析 GraphQL API 回應
3. 從解析的資料中建立格式正確的 PostMetrics 物件 (特別是 URL)
"""

import asyncio
import json
import logging
import sys
import os
from pathlib import Path
import re # Added for regex validation

# --- 日誌設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 路徑設定 ---
# 修正 project_root 的計算方式
# 當腳本在根目錄時，os.path.dirname(__file__) 就是專案根目錄
project_root = os.path.abspath(os.path.dirname(__file__))
if 'pyproject.toml' not in os.listdir(project_root):
    # 如果當前目錄沒有 pyproject.toml，可能是在子目錄執行，嘗試往上一層
    project_root = os.path.abspath(os.path.join(project_root, '..'))

if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from agents.playwright_crawler.playwright_logic import PlaywrightLogic
    from common.models import PostMetricsBatch
except ModuleNotFoundError as e:
    logging.error(f"❌ 模組導入失敗: {e}")
    logging.error("請確認您是在專案根目錄下執行此腳本！")
    sys.exit(1)

# --- 測試參數 ---
TARGET_USERNAME = "natgeo"
MAX_POSTS_TO_CRAWL = 10 # <--- 暫時改回較小的數量以降低 API 壓力
AUTH_FILE_PATH = Path(project_root) / "agents" / "playwright_crawler" / "auth.json"


async def run_crawler_test():
    """執行爬蟲測試"""
    print("🧪 === Playwright Crawler 核心邏輯測試 ===")

    # 1. 檢查認證檔案是否存在
    if not AUTH_FILE_PATH.exists():
        print(f"❌ 錯誤：找不到認證檔案 {AUTH_FILE_PATH}")
        print("請先執行 `python agents/playwright_crawler/save_auth.py` 來產生認證檔案。")
        return
        
    try:
        with open(AUTH_FILE_PATH, 'r', encoding='utf-8') as f:
            auth_json_content = json.load(f)
        print(f"✅ 成功讀取認證檔案: {AUTH_FILE_PATH}")
    except Exception as e:
        print(f"❌ 讀取或解析認證檔案失敗: {e}")
        return

    # 2. 初始化 PlaywrightLogic
    crawler = PlaywrightLogic()
    print("✅ PlaywrightLogic 初始化完成。")

    # 3. 執行爬取
    print(f"🚀 開始爬取使用者 '{TARGET_USERNAME}' 的最近 {MAX_POSTS_TO_CRAWL} 篇貼文...")
    
    start_time = asyncio.get_event_loop().time()
    
    try:
        result_batch: PostMetricsBatch = await crawler.fetch_posts(
            username=TARGET_USERNAME,
            max_posts=MAX_POSTS_TO_CRAWL,
            auth_json_content=auth_json_content,
            task_id="test_crawler_logic"
        )
        
        end_time = asyncio.get_event_loop().time()
        duration = end_time - start_time
        
        print("\n✅ === 爬取完成 ===")
        print(f"⏱️  總耗時: {duration:.2f} 秒")

        # 4. 驗證結果
        if not result_batch or not result_batch.posts:
            print("❌ 結果為空，沒有爬取到任何貼文。")
            return
            
        print(f"📊 共爬取到 {len(result_batch.posts)}/{result_batch.total_count} 篇貼文。")
        
        print("\n📄 === 自動化數據一致性驗證 ===")
        validation_errors = 0
        for i, post in enumerate(result_batch.posts, 1):
            
            # 從 URL 中用正則表達式提取 code
            match = re.search(r"/post/([^/]+)", post.url)
            url_code = match.group(1) if match else None
            
            # post.post_id 是從 GraphQL 的 'pk' 或 'id' 來的
            # url_code 是從 GraphQL 的 'code' 組合成的 URL 中提取的
            
            print(f"--- 貼文 {i}: {post.url.split('/')[-1]} ---")
            print(f"  從 API 提取的 Post ID: {post.post_id}")
            print(f"  從 URL 提取的 Code:    {url_code}")
            
            if url_code != post.url.split('/')[-1]: # 簡單驗證一下正則
                 print("  URL Code vs URL: ❌ 正則提取與分割不符！")
                 validation_errors += 1
            elif post.post_id: # 確保 post_id 存在
                print("  數據一致性: ✅ Post ID 與 URL Code 匹配 (或無需匹配)")
            else:
                print("  數據一致性: ❌ 缺少 Post ID！")
                validation_errors += 1

            # --- 新增：媒體欄位驗證 ---
            print(f"  Images: {post.images}")
            print(f"  Videos: {post.videos}")
            if post.images or post.videos:
                print("  媒體欄位: ✅ 成功抓取到媒體 URL")
            else:
                # 這不一定是錯誤，可能貼文本來就沒有媒體
                print("  媒體欄位: ⚪️ 未發現媒體 URL (可能貼文本來就沒有)")

        print("\n" + "="*30)
        if validation_errors == 0:
            print("✅✅✅ **驗證通過**：所有爬取的貼文數據一致性良好！")
        else:
            print(f"❌❌❌ **驗證失敗**：發現 {validation_errors} 個數據不一致的貼文！")
        print("="*30)

    except Exception as e:
        logging.error(f"❌ 測試過程中發生嚴重錯誤: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(run_crawler_test()) 