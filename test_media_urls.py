#!/usr/bin/env python3
"""
專門測試圖片和影片 URL 抓取功能
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

# 測試參數 - 選擇一個通常有圖片/影片的帳號
TARGET_USERNAME = "natgeo"  # National Geographic 通常有很多圖片和影片
MAX_POSTS_TO_CRAWL = 5
AUTH_FILE_PATH = Path(project_root) / "agents" / "playwright_crawler" / "auth.json"

async def test_media_urls():
    """測試圖片和影片 URL 抓取"""
    print("🧪 === 測試圖片和影片 URL 抓取功能 ===")

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
    print(f"🚀 開始測試 '{TARGET_USERNAME}' 的媒體 URL 抓取...")
    
    try:
        result_batch: PostMetricsBatch = await crawler.fetch_posts(
            username=TARGET_USERNAME,
            max_posts=MAX_POSTS_TO_CRAWL,
            auth_json_content=auth_json_content,
            task_id="test_media_urls"
        )
        
        print("\n✅ === 爬取完成 ===")
        
        if not result_batch or not result_batch.posts:
            print("❌ 結果為空，沒有爬取到任何貼文")
            return
            
        print(f"📊 共爬取到 {len(result_batch.posts)} 篇貼文")
        
        # 檢查媒體 URL 情況
        print("\n🖼️ === 媒體 URL 檢查 ===")
        total_images = 0
        total_videos = 0
        posts_with_media = 0
        
        for i, post in enumerate(result_batch.posts, 1):
            print(f"\n貼文 {i}: {post.url.split('/')[-1]}")
            print(f"  內容: {post.content[:50]}..." if post.content else "  內容: (無)")
            print(f"  觀看數: {post.views_count}")
            
            # 檢查圖片
            if post.images:
                print(f"  📷 圖片 ({len(post.images)} 張):")
                for j, img_url in enumerate(post.images, 1):
                    print(f"    {j}. {img_url[:80]}...")
                total_images += len(post.images)
            else:
                print("  📷 圖片: 無")
            
            # 檢查影片
            if post.videos:
                print(f"  🎬 影片 ({len(post.videos)} 個):")
                for j, vid_url in enumerate(post.videos, 1):
                    print(f"    {j}. {vid_url[:80]}...")
                total_videos += len(post.videos)
            else:
                print("  🎬 影片: 無")
            
            if post.images or post.videos:
                posts_with_media += 1
        
        # 統計結果
        print(f"\n📊 === 媒體統計 ===")
        print(f"總圖片數: {total_images}")
        print(f"總影片數: {total_videos}")
        print(f"含媒體的貼文: {posts_with_media}/{len(result_batch.posts)}")
        
        if total_images > 0 or total_videos > 0:
            print("🎉 媒體 URL 抓取功能正常工作！")
        else:
            print("⚠️ 沒有抓取到任何媒體 URL，可能的原因：")
            print("  1. 選擇的貼文本身沒有圖片/影片")
            print("  2. GraphQL API 結構變化")
            print("  3. 解析邏輯需要調整")
            
        # 檢查最新的 debug 文件
        debug_dir = Path(project_root) / "agents" / "playwright_crawler" / "debug"
        debug_files = list(debug_dir.glob("crawl_data_*_test_med.json"))
        if debug_files:
            latest_debug = max(debug_files, key=lambda f: f.stat().st_mtime)
            print(f"\n📁 最新 debug 文件: {latest_debug.name}")
            
            # 檢查 debug 文件中的媒體數據
            try:
                with open(latest_debug, 'r', encoding='utf-8') as f:
                    debug_data = json.load(f)
                
                debug_images = 0
                debug_videos = 0
                for post in debug_data.get("posts", []):
                    debug_images += len(post.get("images", []))
                    debug_videos += len(post.get("videos", []))
                
                print(f"📄 Debug 文件中的媒體數據:")
                print(f"  圖片: {debug_images} 張")
                print(f"  影片: {debug_videos} 個")
                
            except Exception as e:
                print(f"⚠️ 讀取 debug 文件失敗: {e}")
            
    except Exception as e:
        logging.error(f"❌ 測試過程中發生錯誤: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(test_media_urls())