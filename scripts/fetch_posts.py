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

import asyncio
import argparse
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agents.crawler.crawler_logic import CrawlerLogic
from agents.jina_markdown.jina_markdown_logic import JinaMarkdownAgent
from agents.post_analyzer.analyzer_logic import PostAnalyzerAgent
from common.db_client import get_db_client
from common.settings import get_settings

# Load environment variables from .env file
settings = get_settings()
print("✅ 已載入 .env 檔案")

async def fetch_and_store_posts(author_id: str, max_posts: int = 50):
    """
    完整的三階段處理流程：
    1. CrawlerLogic - 爬取 URL
    2. JinaMarkdownAgent - 解析 markdown 和基礎數值
    3. PostAnalyzerAgent - 智能分析（包括五欄位檢查、vision 判斷等）
    """
    print(f"--- Starting complete post fetching and analysis for author: {author_id} ---")
    
    # 初始化所有三個 Agent
    crawler = CrawlerLogic()
    markdown_agent = JinaMarkdownAgent()
    analyzer_agent = PostAnalyzerAgent()
    db_client = await get_db_client()

    try:
        # === 第一階段：爬取 URL ===
        print(f"Stage 1: Crawling up to {max_posts} posts for {author_id}...")
        
        crawled_urls = []
        async for result in crawler.fetch_threads_post_urls(username=author_id.lstrip('@'), max_posts=max_posts):
            if result.get("response_type") == "data" and result.get("is_task_complete"):
                posts_data = result.get("content", {}).get("post_urls", [])
                crawled_urls = [post['url'] for post in posts_data]
                break
            elif result.get("response_type") == "error":
                print(f"Crawler Error: {result.get('content', {}).get('error')}")
                return

        if not crawled_urls:
            print("No posts found or an error occurred during crawling.")
            return
        print(f"✅ Stage 1 complete. Found {len(crawled_urls)} post URLs.")

        # === 第二階段：Markdown 解析 ===
        print(f"\nStage 2: Processing markdown and extracting basic metrics...")
        
        batch_size = 3  # 保持批次處理以避免 API 限流
        stage2_success = 0
        stage2_failed = 0
        
        for i in range(0, len(crawled_urls), batch_size):
            batch = crawled_urls[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(crawled_urls) + batch_size - 1) // batch_size
            
            print(f"  Processing batch {batch_num}/{total_batches} ({len(batch)} URLs)...")
            
            # 第二階段：JinaMarkdownAgent 批次處理
            tasks = []
            for url in batch:
                task = asyncio.create_task(
                    markdown_agent.process_single_post_with_storage(
                        post_url=url,
                        author=author_id
                    )
                )
                tasks.append(task)

            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            # 統計第二階段結果
            for j, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    stage2_failed += 1
                    print(f"    -> Failed: {batch[j]} - {result}")
                else:
                    stage2_success += 1
                    # 顯示第二階段的結果摘要
                    missing_fields = result.get('missing_fields', [])
                    needs_vision = result.get('needs_vision', False)
                    print(f"    -> Processed: {batch[j]} - Missing: {len(missing_fields)} fields, Needs vision: {needs_vision}")
            
            # 批次間延遲
            if i + batch_size < len(crawled_urls):
                await asyncio.sleep(1.0)
        
        print(f"✅ Stage 2 complete. Success: {stage2_success}, Failed: {stage2_failed}.")

        # === 第三階段：智能分析 ===
        print(f"\nStage 3: Intelligent analysis and processing...")
        
        # 獲取所有成功處理的 URL 進行第三階段分析
        successful_urls = []
        for i in range(0, len(crawled_urls), batch_size):
            batch = crawled_urls[i:i + batch_size]
            tasks = []
            for url in batch:
                task = asyncio.create_task(
                    db_client.get_post(url)  # 使用 get_post 檢查
                )
                tasks.append(task)
            
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            for j, post_data in enumerate(batch_results):
                # 如果 get_post 回傳非 None 值，代表貼文存在
                if not isinstance(post_data, Exception) and post_data:
                    successful_urls.append(batch[j])
        
        print(f"  Found {len(successful_urls)} posts ready for Stage 3 analysis...")
        
        # 第三階段：智能分析（包含五欄位檢查、vision 判斷、LLM 分析等）
        stage3_success = 0
        if successful_urls:
            try:
                print("  Starting intelligent analysis with PostAnalyzerAgent...")
                
                # 使用 PostAnalyzerAgent 進行智能分析
                # 預設使用 mode 1 進行分析，您可以根據需要調整
                analysis_result = await analyzer_agent.analyze_posts(
                    post_urls=successful_urls, 
                    analysis_mode=1
                )
                
                if analysis_result.get("status") == "success":
                    stage3_success = len(successful_urls)
                    print(f"  ✅ Stage 3 intelligent analysis completed successfully.")
                    print(f"     Analysis mode: {analysis_result.get('analysis_mode')}")
                    print(f"     Result: {analysis_result.get('message')}")
                else:
                    print(f"  ❌ Stage 3 analysis failed: {analysis_result.get('message')}")
                    
            except Exception as e:
                print(f"  ❌ Stage 3 analysis failed: {e}")
        
        print(f"\n🎉 Complete three-stage processing finished!")
        print(f"   Stage 1 (Crawling): {len(crawled_urls)} URLs found")
        print(f"   Stage 2 (Markdown): {stage2_success} success, {stage2_failed} failed")
        print(f"   Stage 3 (Analysis): {stage3_success} posts analyzed")

    except Exception as e:
        print(f"An unexpected error occurred in the main process: {e}")
    finally:
        await db_client.close_pool()
        print("\n--- Complete processing script finished. ---")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch and store Threads posts for a specific author.")
    parser.add_argument(
        "--author-id",
        type=str,
        required=True,
        help="The Threads author ID to fetch posts from (e.g., '@wanyu_npp')."
    )
    parser.add_argument(
        "--max-posts",
        type=int,
        default=50,
        help="The maximum number of posts to fetch."
    )
    args = parser.parse_args()

    author_id_clean = args.author_id
    if not author_id_clean.startswith('@'):
        author_id_clean = '@' + author_id_clean

    asyncio.run(fetch_and_store_posts(author_id=author_id_clean, max_posts=args.max_posts)) 