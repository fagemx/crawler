#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSV排序工具
對現有的CSV文件進行排序處理
"""

import csv
import argparse
import pandas as pd
from pathlib import Path

def sort_csv_file(input_file: str, output_file: str = None, sort_by: str = 'views', reverse: bool = True):
    """
    對CSV文件進行排序
    
    Args:
        input_file: 輸入CSV文件
        output_file: 輸出CSV文件（可選）
        sort_by: 排序欄位
        reverse: 是否降序
    """
    try:
        # 讀取CSV文件
        df = pd.read_csv(input_file, encoding='utf-8-sig')
        
        print(f"📊 讀取CSV文件: {input_file}")
        print(f"📈 數據行數: {len(df)}")
        print(f"📋 欄位列表: {list(df.columns)}")
        
        # 映射排序欄位
        sort_mapping = {
            'views': '觀看數',
            'likes': '按讚數',
            'comments': '留言數', 
            'reposts': '轉發數',
            'shares': '分享數',
            'post_id': '貼文ID',
            'content_length': '內容長度'
        }
        
        # 確定排序欄位
        if sort_by in sort_mapping:
            sort_column = sort_mapping[sort_by]
        else:
            sort_column = sort_by
            
        if sort_column not in df.columns:
            print(f"❌ 找不到欄位: {sort_column}")
            print(f"可用欄位: {list(df.columns)}")
            return False
        
        # 處理數字欄位的特殊格式
        if sort_by in ['views', 'likes', 'comments', 'reposts', 'shares']:
            def parse_number(value):
                if pd.isna(value) or value == '' or value == 'N/A':
                    return 0
                
                if isinstance(value, str):
                    value = value.strip()
                    if value.upper().endswith('K'):
                        try:
                            return float(value[:-1]) * 1000
                        except:
                            return 0
                    elif value.upper().endswith('M'):
                        try:
                            return float(value[:-1]) * 1000000
                        except:
                            return 0
                    else:
                        try:
                            return float(value)
                        except:
                            return 0
                elif isinstance(value, (int, float)):
                    return value
                else:
                    return 0
            
            # 創建排序用的數字欄位
            df[f'{sort_column}_numeric'] = df[sort_column].apply(parse_number)
            actual_sort_column = f'{sort_column}_numeric'
        else:
            actual_sort_column = sort_column
        
        # 排序
        df_sorted = df.sort_values(by=actual_sort_column, ascending=not reverse)
        
        # 移除臨時欄位
        if f'{sort_column}_numeric' in df_sorted.columns:
            df_sorted = df_sorted.drop(columns=[f'{sort_column}_numeric'])
        
        # 生成輸出文件名
        if not output_file:
            input_path = Path(input_file)
            output_file = input_path.parent / f"{input_path.stem}_sorted_by_{sort_by}{input_path.suffix}"
        
        # 保存排序後的文件
        df_sorted.to_csv(output_file, index=False, encoding='utf-8-sig')
        
        print(f"✅ 排序完成！")
        print(f"🔢 排序欄位: {sort_column}")
        print(f"📊 排序方式: {'降序' if reverse else '升序'}")
        print(f"💾 輸出文件: {output_file}")
        
        # 顯示排序結果預覽
        print(f"\n📋 排序結果預覽（前5行）:")
        print(f"{'序號':<4} {'貼文ID':<12} {sort_column:<10}")
        print("-" * 30)
        
        for i, row in df_sorted.head().iterrows():
            post_id = str(row.get('貼文ID', 'N/A'))[:10]
            sort_value = str(row.get(sort_column, 'N/A'))[:8]
            print(f"{i+1:<4} {post_id:<12} {sort_value:<10}")
        
        return True
        
    except Exception as e:
        print(f"❌ 排序失敗: {e}")
        return False

def main():
    """主函數"""
    parser = argparse.ArgumentParser(description='CSV排序工具 - 快速對CSV文件按指定欄位排序')
    parser.add_argument('input_file', help='輸入的CSV文件')
    parser.add_argument('--output', '-o', help='輸出的CSV文件（可選）')
    parser.add_argument('--sort-by', '-s', 
                       choices=['views', 'likes', 'comments', 'reposts', 'shares', 'post_id', 'content_length'],
                       default='views',
                       help='排序欄位（預設：觀看數）')
    parser.add_argument('--ascending', '-a', action='store_true', 
                       help='升序排列（預設為降序）')
    
    args = parser.parse_args()
    
    # 檢查輸入文件
    if not Path(args.input_file).exists():
        print(f"❌ 找不到文件: {args.input_file}")
        return 1
    
    # 執行排序
    success = sort_csv_file(
        args.input_file,
        args.output,
        args.sort_by,
        reverse=not args.ascending
    )
    
    return 0 if success else 1

if __name__ == "__main__":
    exit(main())