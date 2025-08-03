#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSV預覽工具
快速查看CSV文件內容和排序效果
"""

import csv
import argparse
import pandas as pd
from pathlib import Path

def preview_csv(file_path: str, rows: int = 10, sort_by: str = None):
    """
    預覽CSV文件內容
    
    Args:
        file_path: CSV文件路径
        rows: 顯示行數
        sort_by: 排序欄位（可選）
    """
    try:
        # 讀取CSV文件
        df = pd.read_csv(file_path, encoding='utf-8-sig')
        
        print(f"📊 CSV文件預覽: {Path(file_path).name}")
        print("=" * 60)
        print(f"📈 總行數: {len(df)}")
        print(f"📋 總欄位: {len(df.columns)}")
        print(f"📝 欄位列表: {', '.join(df.columns)}")
        print("=" * 60)
        
        # 如果指定排序
        if sort_by:
            sort_mapping = {
                'views': '觀看數',
                'likes': '按讚數',
                'comments': '留言數',
                'reposts': '轉發數', 
                'shares': '分享數',
                'post_id': '貼文ID',
                'content_length': '內容長度'
            }
            
            sort_column = sort_mapping.get(sort_by, sort_by)
            
            if sort_column in df.columns:
                # 處理數字排序
                if sort_by in ['views', 'likes', 'comments', 'reposts', 'shares']:
                    def parse_number(value):
                        if pd.isna(value) or value == '' or value == 'N/A':
                            return 0
                        if isinstance(value, str):
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
                        return value
                    
                    df['_sort_key'] = df[sort_column].apply(parse_number)
                    df = df.sort_values('_sort_key', ascending=False).drop('_sort_key', axis=1)
                else:
                    df = df.sort_values(sort_column, ascending=False)
                
                print(f"🔢 已按 {sort_column} 排序（降序）")
                print("-" * 60)
        
        # 顯示數據統計
        numeric_columns = []
        for col in ['觀看數', '按讚數', '留言數', '轉發數', '分享數']:
            if col in df.columns:
                numeric_columns.append(col)
        
        if numeric_columns:
            print("📊 數據統計:")
            for col in numeric_columns:
                # 處理數字格式統計
                values = []
                for val in df[col]:
                    if pd.isna(val) or val == '' or val == 'N/A':
                        continue
                    try:
                        if isinstance(val, str):
                            if val.upper().endswith('K'):
                                values.append(float(val[:-1]) * 1000)
                            elif val.upper().endswith('M'):
                                values.append(float(val[:-1]) * 1000000)
                            else:
                                values.append(float(val))
                        else:
                            values.append(float(val))
                    except:
                        continue
                
                if values:
                    avg_val = sum(values) / len(values)
                    max_val = max(values)
                    min_val = min(values)
                    print(f"   {col}: 平均 {avg_val:.0f} | 最高 {max_val:.0f} | 最低 {min_val:.0f}")
            print("-" * 60)
        
        # 顯示前N行
        print(f"📋 前 {rows} 行數據:")
        
        # 選擇要顯示的關鍵欄位
        display_columns = []
        for col in ['貼文ID', '觀看數', '按讚數', '留言數', '內容']:
            if col in df.columns:
                display_columns.append(col)
        
        if not display_columns:
            display_columns = list(df.columns)[:5]  # 預設顯示前5欄
        
        # 格式化顯示
        print(f"{'序號':<4}", end="")
        for col in display_columns:
            if col == '內容':
                print(f"{col:<30}", end="")
            else:
                print(f"{col:<12}", end="")
        print()
        print("-" * (4 + sum(30 if col == '內容' else 12 for col in display_columns)))
        
        for i, (_, row) in enumerate(df.head(rows).iterrows()):
            print(f"{i+1:<4}", end="")
            for col in display_columns:
                value = str(row[col]) if not pd.isna(row[col]) else 'N/A'
                if col == '內容':
                    # 內容欄位截斷顯示
                    content = value[:25] + "..." if len(value) > 25 else value
                    print(f"{content:<30}", end="")
                else:
                    # 其他欄位
                    display_value = value[:10] if len(value) > 10 else value
                    print(f"{display_value:<12}", end="")
            print()
        
        print("=" * 60)
        print(f"💡 提示: 在Excel中打開此CSV可以進行更多操作")
        print(f"📁 文件位置: {Path(file_path).absolute()}")
        
    except Exception as e:
        print(f"❌ 預覽失敗: {e}")
        return False
    
    return True

def main():
    """主函數"""
    parser = argparse.ArgumentParser(description='CSV預覽工具 - 快速查看CSV文件內容和排序效果')
    parser.add_argument('csv_file', help='要預覽的CSV文件')
    parser.add_argument('--rows', '-r', type=int, default=10, help='顯示行數（預設10行）')
    parser.add_argument('--sort-by', '-s',
                       choices=['views', 'likes', 'comments', 'reposts', 'shares', 'post_id', 'content_length'],
                       help='臨時排序預覽（不修改原文件）')
    
    args = parser.parse_args()
    
    # 檢查文件
    if not Path(args.csv_file).exists():
        print(f"❌ 找不到文件: {args.csv_file}")
        return 1
    
    # 預覽文件
    success = preview_csv(args.csv_file, args.rows, args.sort_by)
    
    return 0 if success else 1

if __name__ == "__main__":
    exit(main())