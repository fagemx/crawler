#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
重構後的實時爬蟲+提取器
使用模組化設計，將功能分散到不同模組中
"""

import asyncio
import argparse
import sys
from pathlib import Path

# 添加專案根目錄到路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.core import RealtimeCrawler
from scripts.utils import safe_print

# Windows相容性設定
import os
if os.name == 'nt':  # Windows
    try:
        os.system('chcp 65001')  # 設定為UTF-8編碼
    except:
        pass

async def main():
    """主函數"""
    try:
        # 設定命令行參數
        parser = argparse.ArgumentParser(description='實時爬蟲+提取器 - 支持增量爬取')
        parser.add_argument('--username', default='gvmonthly', help='目標帳號用戶名')
        parser.add_argument('--max_posts', type=int, default=100, help='要爬取的貼文數量')
        parser.add_argument('--incremental', action='store_true', help='啟用增量爬取模式')
        parser.add_argument('--full', action='store_true', help='強制全量爬取模式（忽略已存在的貼文）')
        
        args = parser.parse_args()
        
        # 決定爬取模式（預設增量，除非明確指定全量）
        if args.full:
            incremental_mode = False  # 強制全量
        elif args.incremental:
            incremental_mode = True   # 明確增量
        else:
            incremental_mode = True   # 預設增量
        mode_desc = "增量爬取" if incremental_mode else "全量爬取"
        
        safe_print(f"🚀 啟動實時爬蟲+提取器")
        safe_print(f"👤 目標帳號: @{args.username}")
        safe_print(f"📊 目標數量: {args.max_posts} 個貼文")
        safe_print(f"📋 爬取模式: {mode_desc}")
        safe_print("=" * 60)
        
        # 創建並執行實時提取器
        crawler = RealtimeCrawler(args.username, args.max_posts, incremental_mode)
        results_file = await crawler.run_realtime_extraction()
        
        if results_file:
            safe_print(f"🎉 爬取成功完成！結果保存至: {results_file}")
            return results_file
        else:
            safe_print("❌ 爬取失敗或無結果")
            return None
            
    except KeyboardInterrupt:
        safe_print("\n⚠️ 用戶中斷爬取")
        return None
    except Exception as e:
        safe_print(f"❌ 執行錯誤: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    # Windows 環境相容性
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    result = asyncio.run(main())