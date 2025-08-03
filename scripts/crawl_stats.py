#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
爬取統計查詢工具
查看帳號的爬取歷史、狀態和統計數據
"""

import asyncio
import argparse
from datetime import datetime
from common.incremental_crawl_manager import IncrementalCrawlManager

async def show_crawl_stats(username: str = None):
    """顯示爬取統計"""
    manager = IncrementalCrawlManager()
    
    if username:
        # 顯示特定帳號的統計
        print(f"📊 帳號爬取統計: @{username}")
        print("=" * 50)
        
        summary = await manager.get_crawl_summary(username)
        
        if 'error' in summary:
            print(f"❌ 錯誤: {summary['error']}")
            return
        
        checkpoint = summary['checkpoint']
        stats = summary['statistics']
        
        print(f"🔍 爬取檢查點:")
        print(f"   最新貼文ID: {checkpoint['latest_post_id'] or '無'}")
        print(f"   累計爬取數: {checkpoint['total_crawled']}")
        print(f"   上次爬取時間: {checkpoint['last_crawl_at'] or '無'}")
        
        print(f"\n📈 統計數據:")
        print(f"   總貼文數: {stats['total_posts']}")
        print(f"   有觀看數的貼文: {stats['posts_with_views']}")
        print(f"   有內容的貼文: {stats['posts_with_content']}")
        print(f"   平均觀看數: {stats['avg_views']:.0f}")
        print(f"   最高觀看數: {stats['max_views']}")
        print(f"   最後貼文時間: {stats['last_post_time'] or '無'}")
        
    else:
        # 顯示所有帳號的總覽
        print("📊 所有帳號爬取總覽")
        print("=" * 50)
        
        try:
            results = await manager.db.fetch_all("""
                SELECT 
                    cs.username,
                    cs.latest_post_id,
                    cs.total_crawled,
                    cs.last_crawl_at,
                    COUNT(pm.post_id) as db_posts_count,
                    AVG(pm.views_count) as avg_views,
                    MAX(pm.views_count) as max_views
                FROM crawl_state cs
                LEFT JOIN post_metrics_sql pm ON cs.username = pm.username
                GROUP BY cs.username, cs.latest_post_id, cs.total_crawled, cs.last_crawl_at
                ORDER BY cs.last_crawl_at DESC NULLS LAST
            """)
            
            if results:
                print(f"{'帳號':<15} {'檢查點ID':<12} {'爬取數':<6} {'資料庫貼文':<8} {'平均觀看':<8} {'最高觀看':<8} {'上次爬取時間':<20}")
                print("-" * 90)
                
                for row in results:
                    username_display = f"@{row['username']}"
                    latest_id = row['latest_post_id'][:10] + '...' if row['latest_post_id'] else '無'
                    crawled = row['total_crawled'] or 0
                    db_count = row['db_posts_count'] or 0
                    avg_views = int(row['avg_views']) if row['avg_views'] else 0
                    max_views = row['max_views'] or 0
                    last_crawl = row['last_crawl_at'].strftime('%m-%d %H:%M') if row['last_crawl_at'] else '無'
                    
                    print(f"{username_display:<15} {latest_id:<12} {crawled:<6} {db_count:<8} {avg_views:<8} {max_views:<8} {last_crawl:<20}")
            else:
                print("❌ 未找到任何爬取記錄")
                
        except Exception as e:
            print(f"❌ 查詢失敗: {e}")

async def main():
    """主函數"""
    parser = argparse.ArgumentParser(description='爬取統計查詢工具')
    parser.add_argument('--username', help='查詢特定帳號的詳細統計')
    parser.add_argument('--all', action='store_true', help='顯示所有帳號總覽（預設）')
    
    args = parser.parse_args()
    
    if args.username:
        await show_crawl_stats(args.username)
    else:
        await show_crawl_stats()

if __name__ == "__main__":
    asyncio.run(main())