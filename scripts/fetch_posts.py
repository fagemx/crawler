#!/usr/bin/env python3
"""
專用資料抓取腳本 - 為 Plan E 分析階段準備素材

功能：
1. 抓取指定 Threads 用戶的最新 N 筆貼文 URL。
2. 使用 JinaMarkdownAgent 處理這些 URL，將 Markdown 內容和指標分別寫入
   PostgreSQL (Tier-1) 和 Redis (Tier-0)。

如何使用：
python scripts/fetch_posts.py --username <threads_username> --count <post_count>
"""

import os
import sys
import asyncio
import argparse
from pathlib import Path
from typing import List, Dict, Any

# 載入 .env 檔案
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ 已載入 .env 檔案")
except ImportError:
    print("⚠️ 未安裝 python-dotenv，可能無法從 .env 檔案載入環境變數")

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agents.crawler.crawler_logic import CrawlerLogic
from agents.jina_markdown.jina_markdown_logic import JinaMarkdownAgent
from common.models import PostMetrics


async def fetch_and_store_posts(username: str, count: int):
    """
    執行完整的資料抓取和儲存流程
    
    Args:
        username: Threads 用戶名
        count: 要抓取的貼文數量
    """
    print("=" * 60)
    print(f"🚀 開始為用戶 @{username} 抓取 {count} 筆貼文")
    print("=" * 60)

    # --------------------------------------------------------------------------
    # 步驟 1: 呼叫 CrawlerAgent 獲取貼文 URL
    # --------------------------------------------------------------------------
    print("\n[步驟 1/2] 呼叫 CrawlerAgent 獲取貼文 URL...")
    
    crawler = CrawlerLogic()
    crawled_posts: List[PostMetrics] = []
    
    try:
        task_id = f"fetch_{username}_{count}"
        
        async for result in crawler.fetch_threads_post_urls(
            username=username,
            max_posts=count,
            task_id=task_id
        ):
            if result.get("response_type") == "status":
                content = result.get("content", {})
                progress = content.get("progress")
                message = content.get("message", "")
                
                if progress is not None:
                    print(f"  Crawler 進度: {progress:.0%} - {message}")
                else:
                    print(f"  Crawler 狀態: {message}")
            
            elif result.get("response_type") == "data" and result.get("is_task_complete"):
                post_urls = result["content"].get("post_urls", [])
                for post_data in post_urls:
                    crawled_posts.append(
                        PostMetrics(
                            url=post_data.get("url"),
                            post_id=post_data.get("post_id"),
                            username=username
                        )
                    )
                print(f"✅ CrawlerAgent 成功獲取 {len(crawled_posts)} 個貼文 URL。")
                break # 獲取到最終數據後退出
                
            elif result.get("response_type") == "error":
                print(f"❌ CrawlerAgent 錯誤: {result['content'].get('error')}")
                return # 如果第一步就失敗，則終止

        if not crawled_posts:
            print("❌ 未能從 CrawlerAgent 獲取任何 URL，腳本終止。")
            return
            
    except Exception as e:
        print(f"❌ 執行 CrawlerAgent 時發生嚴重錯誤: {e}")
        import traceback
        traceback.print_exc()
        return

    # --------------------------------------------------------------------------
    # 步驟 2: 呼叫 JinaMarkdownAgent 處理 URL 並儲存
    # --------------------------------------------------------------------------
    print("\n[步驟 2/2] 呼叫 JinaMarkdownAgent 處理並儲存資料...")
    
    jina_agent = JinaMarkdownAgent()
    final_jina_result = None

    try:
        task_id = f"jina_{username}_{count}"
        
        async for result in jina_agent.batch_process_posts_with_storage(
            posts=crawled_posts,
            task_id=task_id
        ):
            if result.get("response_type") == "status":
                content = result.get("content", {})
                progress = content.get("progress")
                message = content.get("message", "")

                if progress is not None:
                    print(f"  Jina 進度: {progress:.0%} - {message}")
                else:
                    print(f"  Jina 狀態: {message}")
            
            elif result.get("response_type") == "data" and result.get("is_task_complete"):
                final_jina_result = result["content"]
                break

        if final_jina_result:
            success_count = final_jina_result.get('success_count', 0)
            vision_needed = final_jina_result.get('vision_needed_count', 0)
            print(f"✅ JinaMarkdownAgent 處理完成。")
            print(f"  - 成功處理並儲存: {success_count} 則貼文")
            print(f"  - 需要 Vision 補值: {vision_needed} 則貼文")
        else:
            print("❌ JinaMarkdownAgent 未返回最終處理結果。")

    except Exception as e:
        print(f"❌ 執行 JinaMarkdownAgent 時發生嚴重錯誤: {e}")
        import traceback
        traceback.print_exc()
        return

    print("\n" + "=" * 60)
    print("🎉 資料抓取與儲存任務完成！")
    print(f"分析素材已準備就緒，請在資料庫 `posts` 表中查看 @{username} 的貼文。")
    print("=" * 60)


def main():
    """主函數，解析命令行參數並運行抓取任務"""
    parser = argparse.ArgumentParser(
        description="為 Plan E 分析階段抓取並儲存 Threads 貼文素材。",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "-u", "--username",
        type=str,
        required=True,
        help="要抓取的 Threads 用戶名 (例如: victor31429)"
    )
    parser.add_argument(
        "-c", "--count",
        type=int,
        required=True,
        help="要抓取的最新貼文數量"
    )
    args = parser.parse_args()

    # 檢查環境變數
    if not os.getenv("APIFY_TOKEN"):
        print("❌ 錯誤：環境變數 APIFY_TOKEN 未設定。")
        print("請在 .env 檔案中設定 APIFY_TOKEN。")
        sys.exit(1)

    try:
        asyncio.run(fetch_and_store_posts(args.username, args.count))
    except KeyboardInterrupt:
        print("\n操作被用戶中斷。")
    # finally 區塊在新版 asyncio 中可能導致問題，且通常非必要，故移除
    # finally:
    #     # 確保非同步資源被正確關閉
    #     loop = asyncio.get_event_loop()
    #     if loop.is_running():
    #         loop.close()


if __name__ == "__main__":
    main() 