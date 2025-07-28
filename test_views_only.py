#!/usr/bin/env python3
"""
專門測試 fill_views_from_page 功能的腳本
"""

import asyncio
import json
import logging
import sys
import os
from pathlib import Path
from datetime import datetime

# 設定日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 路徑設定
project_root = os.path.abspath(os.path.dirname(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from agents.playwright_crawler.playwright_logic import PlaywrightLogic
    from common.models import PostMetrics
except ModuleNotFoundError as e:
    logging.error(f"❌ 模組導入失敗: {e}")
    sys.exit(1)

# 測試參數
AUTH_FILE_PATH = Path(project_root) / "agents" / "playwright_crawler" / "auth.json"

async def test_views_only():
    """只測試觀看數補齊功能"""
    print("🧪 === 測試觀看數補齊功能 ===")

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

    # 創建測試用的 PostMetrics 物件
    test_posts = [
        PostMetrics(
            post_id="test_1",
            username="natgeo",
            url="https://www.threads.com/@natgeo/post/DMVsAjYNVfk",
            content="Test post 1",
            likes_count=100,
            comments_count=10,
            reposts_count=5,
            shares_count=2,
            views_count=None,  # 這個需要補齊
            created_at=datetime.now(),
            source="test",
            processing_stage="test"
        ),
        PostMetrics(
            post_id="test_2", 
            username="natgeo",
            url="https://www.threads.com/@natgeo/post/DMNjTqAtHo-",
            content="Test post 2",
            likes_count=200,
            comments_count=20,
            reposts_count=10,
            shares_count=5,
            views_count=None,  # 這個需要補齊
            created_at=datetime.now(),
            source="test",
            processing_stage="test"
        )
    ]

    # 初始化 PlaywrightLogic 並設定 context
    crawler = PlaywrightLogic()
    
    try:
        # 手動設定 browser context (模擬 fetch_posts 的設定)
        from playwright.async_api import async_playwright
        import tempfile
        import uuid
        
        # 創建臨時認證檔案
        auth_file = Path(tempfile.gettempdir()) / f"test_views_{uuid.uuid4()}_auth.json"
        with open(auth_file, 'w', encoding='utf-8') as f:
            json.dump(auth_json_content, f)

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=crawler.settings.headless,
                timeout=crawler.settings.navigation_timeout,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
            )
            crawler.context = await browser.new_context(
                storage_state=str(auth_file),
                user_agent=crawler.settings.user_agent,
                viewport={"width": 1920, "height": 1080},
                locale="zh-TW",  # 繁體中文
                has_touch=True,
                accept_downloads=False
            )

            print(f"🔍 開始測試觀看數補齊，共 {len(test_posts)} 個貼文...")
            
            # 執行觀看數補齊
            result_posts = await crawler.fill_views_from_page(test_posts)
            
            print("\n✅ === 觀看數補齊完成 ===")
            for i, post in enumerate(result_posts, 1):
                print(f"貼文 {i}: {post.url}")
                print(f"  觀看數: {post.views_count}")
                print(f"  補齊時間: {post.views_fetched_at}")
                if post.views_count and post.views_count > 0:
                    print(f"  ✅ 成功獲取觀看數")
                elif post.views_count == -1:
                    print(f"  ❌ 獲取失敗")
                else:
                    print(f"  ⚪️ 未獲取到觀看數")
                print()

            await browser.close()
            
        # 清理臨時檔案
        if auth_file.exists():
            auth_file.unlink()
            
    except Exception as e:
        logging.error(f"❌ 測試過程中發生錯誤: {e}", exc_info=True)
    finally:
        if hasattr(crawler, 'context') and crawler.context:
            try:
                await crawler.context.close()
            except:
                pass

if __name__ == "__main__":
    asyncio.run(test_views_only())