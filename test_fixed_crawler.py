#!/usr/bin/env python3
"""
測試修復後的 Playwright Crawler
專注於驗證觀看數補齊功能是否正常工作
"""

import asyncio
import json
import logging
import sys
import os
from pathlib import Path

# 設定日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 路徑設定
project_root = os.path.abspath(os.path.dirname(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from agents.playwright_crawler.playwright_logic import PlaywrightLogic
    from common.models import PostMetricsBatch
except ModuleNotFoundError as e:
    logging.error(f"❌ 模組導入失敗: {e}")
    sys.exit(1)

# 測試參數
TARGET_USERNAME = "natgeo"
MAX_POSTS_TO_CRAWL = 3  # 減少數量以快速測試
AUTH_FILE_PATH = Path(project_root) / "agents" / "playwright_crawler" / "auth.json"

async def test_fixed_crawler():
    """測試修復後的爬蟲"""
    print("🧪 === 測試修復後的 Playwright Crawler ===")

    # 檢查認證檔案
    if not AUTH_FILE_PATH.exists():
        print(f"❌ 找不到認證檔案 {AUTH_FILE_PATH}")
        return
        
    try:
        with open(AUTH_FILE_PATH, 'r', encoding='utf-8') as f:
            auth_json_content = json.load(f)
        print(f"✅ 成功讀取認證檔案")
    except Exception as e:
        print(f"❌ 讀取認證檔案失敗: {e}")
        return

    # 初始化爬蟲
    crawler = PlaywrightLogic()
    print("✅ PlaywrightLogic 初始化完成")

    # 執行爬取
    print(f"🚀 開始測試爬取 '{TARGET_USERNAME}' 的最近 {MAX_POSTS_TO_CRAWL} 篇貼文...")
    
    try:
        result_batch: PostMetricsBatch = await crawler.fetch_posts(
            username=TARGET_USERNAME,
            max_posts=MAX_POSTS_TO_CRAWL,
            auth_json_content=auth_json_content,
            task_id="test_fixed_crawler"
        )
        
        print("\n✅ === 爬取完成 ===")
        
        if not result_batch or not result_batch.posts:
            print("❌ 結果為空，沒有爬取到任何貼文")
            return
            
        print(f"📊 共爬取到 {len(result_batch.posts)} 篇貼文")
        
        # 檢查觀看數補齊情況
        print("\n🔍 === 觀看數補齊檢查 ===")
        views_success = 0
        views_failed = 0
        views_null = 0
        
        for i, post in enumerate(result_batch.posts, 1):
            print(f"貼文 {i}: {post.url.split('/')[-1]}")
            print(f"  觀看數: {post.views_count}")
            print(f"  補齊時間: {post.views_fetched_at}")
            
            if post.views_count is None:
                print("  狀態: ⚪️ 未補齊（可能 API 已有數據）")
                views_null += 1
            elif post.views_count == -1:
                print("  狀態: ❌ 補齊失敗")
                views_failed += 1
            elif post.views_count > 0:
                print("  狀態: ✅ 補齊成功")
                views_success += 1
            else:
                print("  狀態: ⚪️ 觀看數為 0")
                views_success += 1
            print()
        
        # 統計結果
        total = len(result_batch.posts)
        print("📊 === 補齊統計 ===")
        print(f"成功補齊: {views_success}/{total}")
        print(f"補齊失敗: {views_failed}/{total}")
        print(f"未需補齊: {views_null}/{total}")
        
        if views_success > 0:
            print("🎉 觀看數補齊功能正常工作！")
        elif views_failed == total:
            print("❌ 所有觀看數補齊都失敗，可能是 selector 或網路問題")
        else:
            print("⚠️ 部分觀看數補齊成功，需要進一步調試")
            
    except Exception as e:
        logging.error(f"❌ 測試過程中發生錯誤: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(test_fixed_crawler())