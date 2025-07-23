#!/usr/bin/env python3
"""
正規表示式除錯與優化腳本

功能：
1. 從 PostgreSQL 資料庫中找出被標記為 'needs_vision' 的貼文。
2. 讀取這些貼文的原始 Markdown 內容。
3. 使用當前的解析邏輯在本機進行測試，並打印詳細的對比結果。
4. 幫助開發者快速定位正規表示式失效的案例並進行優化。

如何使用：
python scripts/debug_parser.py [--limit 5]
"""

import os
import sys
import asyncio
import argparse
from pathlib import Path

# 載入 .env 檔案
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from common.db_client import get_db_client
from agents.jina_markdown.jina_markdown_logic import JinaMarkdownAgent


async def debug_failed_posts(limit: int):
    """
    從資料庫讀取解析失敗的貼文並進行本地除錯
    """
    print("=" * 80)
    print("🔬 開始對資料庫中解析失敗的貼文進行本地除錯...")
    print("=" * 80)

    db_client = None
    try:
        # 1. 初始化資料庫和 Agent
        db_client = await get_db_client()
        jina_agent = JinaMarkdownAgent() # 我們需要它的解析方法

        # 2. 查詢失敗案例
        print(f"\n[步驟 1/3] 正在從 'processing_log' 表查詢最多 {limit} 筆 'needs_vision' 的貼文...")
        
        failed_logs = await db_client.pool.fetch("""
            SELECT url FROM processing_log
            WHERE agent_name = 'jina_markdown' AND status = 'needs_vision'
            ORDER BY started_at DESC
            LIMIT $1
        """, limit)

        if not failed_logs:
            print("\n✅ 在資料庫中未找到 'needs_vision' 的案例。所有貼文都已成功解析！")
            return

        failed_urls = [log['url'] for log in failed_logs]
        print(f"🔍 找到 {len(failed_urls)} 個需要分析的 URL。")

        # 3. 提取 Markdown 內容
        print("\n[步驟 2/3] 正在從 'posts' 表中提取對應的 Markdown 內容...")
        
        posts_to_debug = await db_client.pool.fetch("""
            SELECT url, markdown, author FROM posts
            WHERE url = ANY($1)
        """, failed_urls)

        if not posts_to_debug:
            print("❌ 錯誤：在 'posts' 表中找不到對應的 Markdown 內容。")
            return

        # 4. 在本機進行解析測試
        print("\n[步驟 3/3] 開始在本機進行解析測試...")
        print("-" * 80)

        for i, post in enumerate(posts_to_debug):
            url = post['url']
            markdown = post['markdown']
            author = post['author']

            print(f"\n---案例 {i+1}: {url} ---")
            
            # 打印原始 Markdown 的關鍵部分
            print("\n📜 原始 Markdown (部分內容):")
            print("-" * 20)
            # 尋找 "Translate" 附近上下文
            translate_pos = markdown.find("Translate")
            start_pos = max(0, translate_pos - 100)
            end_pos = min(len(markdown), translate_pos + 100)
            print("..." + markdown[start_pos:end_pos] + "...")
            print("-" * 20)

            # 進行解析
            metrics = jina_agent._extract_metrics_from_markdown(markdown)

            # 打印解析結果
            print("\n🔬 解析結果:")
            for key, value in metrics.items():
                status = "✅" if value is not None else "❌"
                print(f"  {status} {key:<10}: {value}")
            
            print("-" * 80)

    except Exception as e:
        print(f"\n❌ 執行除錯腳本時發生錯誤: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if db_client and db_client.pool:
            await db_client.close_pool()
            print("\n資料庫連接池已關閉。")


def main():
    """主函數"""
    parser = argparse.ArgumentParser(
        description="從資料庫讀取解析失敗的貼文，並在本機進行除錯。",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "-l", "--limit",
        type=int,
        default=5,
        help="要分析的失敗案例數量上限 (預設: 5)"
    )
    args = parser.parse_args()

    asyncio.run(debug_failed_posts(args.limit))


if __name__ == "__main__":
    main() 