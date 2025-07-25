#!/usr/bin/env python3
"""
(信任重建計畫 - 步驟 2)
直接測試 Jina Agent 優化效果 (由已驗證的真實爬蟲數據驅動)

此腳本會自動載入最新的、且已被驗證過的爬蟲原始數據，
專注於找出並解決 Jina 解析 'views' 失敗的問題。
"""

import asyncio
import json
import time
import sys
import os
import logging
import re
from pathlib import Path

# --- 日誌設定：捕獲所有偵錯細節 ---
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s')

# --- 路徑設定 ---
project_root = os.path.abspath(os.path.dirname(__file__))
if 'pyproject.toml' not in os.listdir(project_root):
    project_root = os.path.abspath(os.path.join(project_root, '..'))

if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from agents.jina.jina_logic import JinaMarkdownAgent
    from common.models import PostMetrics, PostMetricsBatch
    from common.settings import get_settings
except ModuleNotFoundError as e:
    logging.error(f"❌ 模組導入失敗: {e}", exc_info=True)
    sys.exit(1)


def load_verified_crawl_data() -> list:
    """自動尋找並載入最新的、已驗證的爬蟲原始數據"""
    debug_dir = Path(project_root) / "agents" / "playwright_crawler" / "debug"
    if not debug_dir.exists():
        logging.error(f"❌ 找不到爬蟲除錯目錄: {debug_dir}")
        return []

    crawl_files = sorted(debug_dir.glob("crawl_data_*.json"), key=os.path.getmtime, reverse=True)
    if not crawl_files:
        logging.error(f"❌ 在 {debug_dir} 中找不到任何 'crawl_data_*.json' 檔案。")
        logging.error("請先執行 `python test_playwright_crawler.py` 來產生數據。")
        return []

    latest_file = crawl_files[0]
    logging.info(f"🚚 正在從已驗證的爬蟲紀錄載入數據: {latest_file.name}")
    try:
        with open(latest_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            top_level_username = data.get("username")
            posts_data = data.get("posts", [])
            if top_level_username:
                for post in posts_data:
                    post['username'] = top_level_username
            return posts_data
    except (json.JSONDecodeError, IOError) as e:
        logging.error(f"❌ 讀取或解析檔案失敗 {latest_file}: {e}")
        return []

async def test_jina_parsing():
    """測試 Jina 解析能力"""
    
    # 1. 載入已驗證的真實數據
    source_posts = load_verified_crawl_data()
    if not source_posts:
        return

    test_posts = [PostMetrics(**post_data) for post_data in source_posts]
    
    print("🧪 === Jina 解析能力測試 (由已驗證數據驅動) ===")
    
    # 2. 初始化 Agent
    print("正在初始化 Agent...")
    try:
        agent = JinaMarkdownAgent()
    except Exception as e:
        import traceback
        print(f"❌ 初始化失敗: {e}")
        traceback.print_exc()
        return
        
    # 3. 建立測試批次
    test_batch = PostMetricsBatch(
        batch_id="verified_data_test",
        username=test_posts[0].username,
        posts=test_posts,
        total_count=len(test_posts),
        processing_stage="playwright_completed"
    )
    
    print(f"\n🎯 開始用 {len(test_posts)} 篇已驗證貼文測試 Jina 解析...")
    
    # 4. 執行測試
    try:
        start_time = time.time()
        enriched_batch = await agent.enrich_batch(test_batch)
        duration = time.time() - start_time
        
        # 5. 統計結果
        views_found_count = sum(1 for p in enriched_batch.posts if p.views_count is not None)
        
        print(f"\n✅ === 解析測試完成 ===")
        print(f"⏱️  總耗時: {duration:.2f} 秒")
        if len(test_posts) > 0:
            print(f"📈 平均每篇耗時: {duration/len(test_posts):.2f} 秒")
        print(f"👁️  取得 views 成功率: {views_found_count}/{len(test_posts)} 個")
        
        # 6. 自動單點偵錯失敗案例
        if views_found_count < len(test_posts):
            print(f"\n🔬 === 自動單點偵錯 (尋找失敗的 Markdown) ===")
            failed_posts = [p for p in enriched_batch.posts if p.views_count is None]
            
            for i, post in enumerate(failed_posts, 1):
                print(f"\n--- 偵錯貼文 {i}/{len(failed_posts)}: {post.url} ---")
                
                # 重新建立只含單一失敗貼文的批次，以觸發詳細日誌
                single_batch = PostMetricsBatch(
                    batch_id=f"debug_{post.post_id}", username=post.username,
                    posts=[post], total_count=1, processing_stage="playwright_completed"
                )
                await agent.enrich_batch(single_batch)
        else:
            print("✅✅✅ **所有貼文的 'views' 均成功解析！**")

    except Exception as e:
        import traceback
        print(f"❌ 測試過程中發生錯誤: {e}")
        traceback.print_exc()
    finally:
        if hasattr(agent, '_cleanup_session'):
            await agent._cleanup_session()

if __name__ == "__main__":
    asyncio.run(test_jina_parsing()) 