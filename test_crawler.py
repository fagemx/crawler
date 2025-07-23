#!/usr/bin/env python3
"""
簡化爬蟲測試腳本

測試 Crawler Agent 是否能正確抓取 Threads 貼文 URL
"""

import asyncio
import json
import sys
from pathlib import Path

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from agents.crawler.crawler_logic import CrawlerLogic
from common.settings import get_settings


async def test_crawler():
    """測試爬蟲功能"""
    print("🧪 測試簡化版 Crawler Agent")
    print("=" * 50)
    
    # 檢查配置
    settings = get_settings()
    if not settings.apify.token:
        print("❌ 錯誤：未設置 APIFY_TOKEN")
        print("請在 .env 檔案中設置 APIFY_TOKEN=your_token_here")
        return
    
    print(f"✅ Apify Token: {'已設置' if settings.apify.token else '未設置'}")
    print(f"📍 使用 Actor: curious_coder/threads-scraper")
    
    # 創建爬蟲實例
    crawler = CrawlerLogic()
    
    # 測試用戶（使用用戶提供的範例）
    test_username = "09johan24"
    max_posts = 5  # 測試用少量貼文
    
    print(f"\n🎯 測試目標：@{test_username}")
    print(f"📊 抓取數量：{max_posts} 則貼文")
    print("\n開始抓取...")
    
    try:
        async for result in crawler.fetch_threads_post_urls(
            username=test_username,
            max_posts=max_posts,
            task_id="test_task_001"
        ):
            # 處理不同類型的回應
            if result.get("response_type") == "status":
                content = result.get("content", {})
                status = content.get("status", "")
                message = content.get("message", "")
                progress = content.get("progress")
                
                if progress is not None:
                    print(f"📈 進度：{progress:.1%} - {message}")
                else:
                    print(f"📋 狀態：{status} - {message}")
                    
            elif result.get("response_type") == "text":
                print(f"💬 訊息：{result.get('content', '')}")
                
            elif result.get("response_type") == "data" and result.get("is_task_complete"):
                # 最終結果
                content = result.get("content", {})
                post_urls = content.get("post_urls", [])
                
                print(f"\n✅ 抓取完成！")
                print(f"📊 總共抓取：{content.get('total_count', 0)} 個 URL")
                print(f"⏱️  處理時間：{content.get('processing_time', 0):.2f} 秒")
                print(f"👤 用戶：{content.get('username', '')}")
                
                print(f"\n📋 抓取到的貼文 URL：")
                for i, post_url in enumerate(post_urls, 1):
                    print(f"  {i}. {post_url.get('url', '')}")
                    print(f"     ID: {post_url.get('post_id', '')}")
                
                # 驗證 URL 格式（基於用戶提供的範例格式）
                print(f"\n🔍 URL 格式驗證：")
                valid_urls = 0
                expected_format = "https://www.threads.com/@username/post/code"
                print(f"   預期格式：{expected_format}")
                
                for post_url in post_urls:
                    url = post_url.get('url', '')
                    if url.startswith('https://www.threads.com/@') and '/post/' in url:
                        valid_urls += 1
                        print(f"   ✅ {url}")
                    else:
                        print(f"   ⚠️  無效 URL 格式: {url}")
                
                print(f"\n✅ 有效 URL：{valid_urls}/{len(post_urls)}")
                
                # 驗證範例貼文格式
                example_url = f"https://www.threads.com/@{test_username}/post/DMaHMSqTdFs"
                print(f"\n📝 範例貼文 URL 格式：")
                print(f"   {example_url}")
                print(f"   （這應該是類似的格式）")
                
            elif result.get("response_type") == "error":
                print(f"❌ 錯誤：{result.get('content', {}).get('error', '')}")
                
    except Exception as e:
        print(f"❌ 測試失敗：{str(e)}")
        import traceback
        traceback.print_exc()


async def test_health_check():
    """測試健康檢查"""
    print("\n🏥 測試健康檢查")
    print("-" * 30)
    
    crawler = CrawlerLogic()
    health_status = await crawler.health_check()
    
    print(f"狀態：{health_status.get('status', 'unknown')}")
    if health_status.get('error'):
        print(f"錯誤：{health_status['error']}")
    else:
        print("✅ 健康檢查通過")


def main():
    """主函數"""
    print("🚀 Crawler Agent 簡化版測試")
    print("基於 apify-threads-scraper.md 的實現")
    print("只抓取貼文 URL，不處理其他數據")
    
    # 檢查是否在專案根目錄
    if not (project_root / ".env.example").exists():
        print("❌ 請在專案根目錄執行此腳本")
        sys.exit(1)
    
    # 檢查 .env 檔案
    env_file = project_root / ".env"
    if not env_file.exists():
        print("⚠️  未找到 .env 檔案")
        print("請複製 .env.example 為 .env 並設置 APIFY_TOKEN")
        sys.exit(1)
    
    # 運行測試
    asyncio.run(test_health_check())
    asyncio.run(test_crawler())


if __name__ == "__main__":
    main()