#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSV導出命令行工具
支持多種導出模式的靈活CSV導出
"""

import asyncio
import argparse
import glob
from pathlib import Path
from common.csv_export_manager import CSVExportManager

async def main():
    """主函數"""
    parser = argparse.ArgumentParser(description='CSV導出工具 - 支持多種數據源')
    
    subparsers = parser.add_subparsers(dest='command', help='導出模式')
    
    # 當次結果導出
    current_parser = subparsers.add_parser('current', help='導出當次爬取結果')
    current_parser.add_argument('json_file', help='JSON結果文件路径')
    current_parser.add_argument('--output', '-o', help='輸出CSV文件路径')
    
    # 歷史數據導出
    history_parser = subparsers.add_parser('history', help='導出資料庫歷史數據')
    history_parser.add_argument('username', help='目標帳號名稱')
    history_parser.add_argument('--days', type=int, help='回溯天數')
    history_parser.add_argument('--limit', type=int, help='最大記錄數')
    history_parser.add_argument('--output', '-o', help='輸出CSV文件路径')
    
    # 統計分析導出
    analysis_parser = subparsers.add_parser('analysis', help='導出統計分析數據')
    analysis_parser.add_argument('username', help='目標帳號名稱')
    analysis_parser.add_argument('--output', '-o', help='輸出CSV文件路径')
    
    # 對比報告導出
    compare_parser = subparsers.add_parser('compare', help='導出多次爬取對比報告')
    compare_parser.add_argument('pattern', help='JSON文件匹配模式 (如: "realtime_extraction_results_*.json")')
    compare_parser.add_argument('--output', '-o', help='輸出CSV文件路径')
    
    # 批量導出最新結果
    latest_parser = subparsers.add_parser('latest', help='導出最新的爬取結果')
    latest_parser.add_argument('--output', '-o', help='輸出CSV文件路径')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    csv_manager = CSVExportManager()
    
    try:
        if args.command == 'current':
            print(f"📊 導出當次結果: {args.json_file}")
            csv_file = csv_manager.export_current_session(args.json_file, args.output)
            print(f"✅ 成功導出到: {csv_file}")
            
        elif args.command == 'history':
            print(f"📊 導出歷史數據: @{args.username}")
            if args.days:
                print(f"   回溯天數: {args.days}")
            if args.limit:
                print(f"   記錄限制: {args.limit}")
            
            csv_file = await csv_manager.export_database_history(
                args.username,
                args.output,
                args.days,
                args.limit
            )
            print(f"✅ 成功導出到: {csv_file}")
            
        elif args.command == 'analysis':
            print(f"📈 導出統計分析: @{args.username}")
            csv_file = await csv_manager.export_combined_analysis(args.username, args.output)
            print(f"✅ 成功導出到: {csv_file}")
            
        elif args.command == 'compare':
            print(f"🔍 查找匹配文件: {args.pattern}")
            json_files = glob.glob(args.pattern)
            
            if not json_files:
                print(f"❌ 未找到匹配的文件: {args.pattern}")
                return
            
            print(f"📊 找到 {len(json_files)} 個文件，生成對比報告...")
            for f in json_files:
                print(f"   - {f}")
            
            csv_file = csv_manager.export_comparison_report(json_files, args.output)
            print(f"✅ 成功導出到: {csv_file}")
            
        elif args.command == 'latest':
            print("🔍 查找最新的爬取結果...")
            json_files = glob.glob("realtime_extraction_results_*.json")
            
            if not json_files:
                print("❌ 未找到任何爬取結果文件")
                return
            
            # 找到最新的文件
            latest_file = max(json_files, key=lambda f: Path(f).stat().st_mtime)
            print(f"📊 最新文件: {latest_file}")
            
            csv_file = csv_manager.export_current_session(latest_file, args.output)
            print(f"✅ 成功導出到: {csv_file}")
            
    except Exception as e:
        print(f"❌ 導出失敗: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)