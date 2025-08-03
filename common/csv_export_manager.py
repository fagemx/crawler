"""
CSV導出管理器
支持多種數據源和導出模式的靈活CSV導出系統
"""

import csv
import json
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Union
from pathlib import Path
import pandas as pd

from .db_client import DatabaseClient
from .incremental_crawl_manager import IncrementalCrawlManager

class CSVExportManager:
    """CSV導出管理器"""
    
    def __init__(self):
        self.db = DatabaseClient()
        self.crawl_manager = IncrementalCrawlManager()
    
    def export_current_session(self, json_file_path: str, output_path: str = None, sort_by: str = 'views') -> str:
        """
        導出當次爬取結果到CSV
        
        Args:
            json_file_path: JSON結果文件路径
            output_path: 輸出CSV文件路径（可選）
            sort_by: 排序欄位 ('views', 'likes', 'comments', 'post_id', 'none')
        
        Returns:
            生成的CSV文件路径
        """
        try:
            # 讀取JSON結果
            with open(json_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            results = data.get('results', [])
            if not results:
                raise ValueError("JSON文件中沒有找到結果數據")
            
            # 生成輸出文件名
            if not output_path:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                username = data.get('target_username', 'unknown')
                output_path = f"export_current_{username}_{timestamp}.csv"
            
            # 準備CSV數據
            csv_data = []
            for item in results:
                csv_row = {
                    '貼文ID': item.get('post_id', ''),
                    'URL': item.get('url', ''),
                    '觀看數': item.get('views', ''),
                    '按讚數': item.get('likes', ''),
                    '留言數': item.get('comments', ''),
                    '轉發數': item.get('reposts', ''),
                    '分享數': item.get('shares', ''),
                    '內容': item.get('content', ''),
                    '數據來源': item.get('source', ''),
                    '成功狀態': '成功' if item.get('success', False) else '失敗',
                    '內容長度': item.get('content_length', 0),
                    '提取時間': item.get('extracted_at', '')
                }
                csv_data.append(csv_row)
            
            # 排序處理
            if sort_by and sort_by != 'none' and csv_data:
                sort_mapping = {
                    'views': '觀看數',
                    'likes': '按讚數', 
                    'comments': '留言數',
                    'reposts': '轉發數',
                    'shares': '分享數',
                    'post_id': '貼文ID'
                }
                
                if sort_by in sort_mapping:
                    sort_column = sort_mapping[sort_by]
                    
                    # 數字欄位需要特殊處理（空值轉為0）
                    if sort_by in ['views', 'likes', 'comments', 'reposts', 'shares']:
                        def sort_key(row):
                            value = row[sort_column]
                            try:
                                # 處理數字格式（如 "1.2K" -> 1200）
                                if isinstance(value, str):
                                    if value.upper().endswith('K'):
                                        return float(value[:-1]) * 1000
                                    elif value.upper().endswith('M'):
                                        return float(value[:-1]) * 1000000
                                    elif value == '' or value == 'N/A':
                                        return 0
                                    else:
                                        return float(value)
                                elif isinstance(value, (int, float)):
                                    return value
                                else:
                                    return 0
                            except:
                                return 0
                        
                        csv_data.sort(key=sort_key, reverse=True)  # 數字降序
                    else:
                        csv_data.sort(key=lambda x: x[sort_column] or '', reverse=False)  # 文字升序
                    
                    print(f"📊 已按 {sort_column} 排序")
                else:
                    print(f"⚠️ 不支持的排序欄位: {sort_by}")
            else:
                print("📋 使用原始順序（未排序）")
            
            # 寫入CSV
            with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
                if csv_data:
                    writer = csv.DictWriter(f, fieldnames=csv_data[0].keys())
                    writer.writeheader()
                    writer.writerows(csv_data)
            
            print(f"✅ 當次結果已導出到: {output_path}")
            return output_path
            
        except Exception as e:
            print(f"❌ 導出當次結果失敗: {e}")
            raise
    
    async def export_database_history(self, username: str, output_path: str = None, 
                                     days_back: int = None, limit: int = None) -> str:
        """
        導出資料庫歷史數據到CSV
        
        Args:
            username: 帳號名稱
            output_path: 輸出CSV文件路径（可選）
            days_back: 回溯天數（可選）
            limit: 限制記錄數（可選）
        
        Returns:
            生成的CSV文件路径
        """
        try:
            # 生成輸出文件名
            if not output_path:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                suffix = f"_{days_back}days" if days_back else f"_top{limit}" if limit else "_all"
                output_path = f"export_history_{username}{suffix}_{timestamp}.csv"
            
            # 構建查詢條件
            where_conditions = ["username = $1"]
            params = [username]
            
            if days_back:
                where_conditions.append("fetched_at >= $2")
                params.append(datetime.now() - timedelta(days=days_back))
            
            where_clause = " AND ".join(where_conditions)
            limit_clause = f" LIMIT {limit}" if limit else ""
            
            # 查詢資料庫
            query = f"""
                SELECT 
                    post_id,
                    url,
                    content,
                    likes_count,
                    comments_count,
                    reposts_count,
                    shares_count,
                    views_count,
                    source,
                    processing_stage,
                    is_complete,
                    created_at,
                    fetched_at,
                    views_fetched_at,
                    calculated_score
                FROM post_metrics_sql 
                WHERE {where_clause}
                ORDER BY fetched_at DESC
                {limit_clause}
            """
            
            results = await self.db.fetch_all(query, *params)
            
            if not results:
                raise ValueError(f"未找到帳號 @{username} 的歷史數據")
            
            # 準備CSV數據
            csv_data = []
            for row in results:
                csv_row = {
                    '貼文ID': row['post_id'],
                    'URL': row['url'],
                    '觀看數': row['views_count'] or '',
                    '按讚數': row['likes_count'] or '',
                    '留言數': row['comments_count'] or '',
                    '轉發數': row['reposts_count'] or '',
                    '分享數': row['shares_count'] or '',
                    '內容': row['content'] or '',
                    '數據來源': row['source'] or '',
                    '處理階段': row['processing_stage'] or '',
                    '數據完整': '是' if row['is_complete'] else '否',
                    '計算分數': row['calculated_score'] or '',
                    '創建時間': row['created_at'].strftime('%Y-%m-%d %H:%M:%S') if row['created_at'] else '',
                    '爬取時間': row['fetched_at'].strftime('%Y-%m-%d %H:%M:%S') if row['fetched_at'] else '',
                    '觀看數更新時間': row['views_fetched_at'].strftime('%Y-%m-%d %H:%M:%S') if row['views_fetched_at'] else ''
                }
                csv_data.append(csv_row)
            
            # 寫入CSV
            with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
                if csv_data:
                    writer = csv.DictWriter(f, fieldnames=csv_data[0].keys())
                    writer.writeheader()
                    writer.writerows(csv_data)
            
            print(f"✅ 歷史數據已導出到: {output_path} ({len(csv_data)} 條記錄)")
            return output_path
            
        except Exception as e:
            print(f"❌ 導出歷史數據失敗: {e}")
            raise
    
    async def export_combined_analysis(self, username: str, output_path: str = None) -> str:
        """
        導出組合分析數據到CSV（統計摘要）
        
        Args:
            username: 帳號名稱
            output_path: 輸出CSV文件路径（可選）
        
        Returns:
            生成的CSV文件路径
        """
        try:
            # 生成輸出文件名
            if not output_path:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                output_path = f"export_analysis_{username}_{timestamp}.csv"
            
            # 獲取統計數據
            stats_query = """
                SELECT 
                    DATE(fetched_at) as date,
                    COUNT(*) as posts_count,
                    COUNT(CASE WHEN views_count > 0 THEN 1 END) as posts_with_views,
                    COUNT(CASE WHEN content IS NOT NULL AND content != '' THEN 1 END) as posts_with_content,
                    AVG(views_count) as avg_views,
                    MAX(views_count) as max_views,
                    AVG(likes_count) as avg_likes,
                    MAX(likes_count) as max_likes,
                    AVG(comments_count) as avg_comments,
                    MAX(comments_count) as max_comments,
                    COUNT(DISTINCT source) as source_types
                FROM post_metrics_sql 
                WHERE username = $1
                GROUP BY DATE(fetched_at)
                ORDER BY DATE(fetched_at) DESC
            """
            
            results = await self.db.fetch_all(stats_query, username)
            
            if not results:
                raise ValueError(f"未找到帳號 @{username} 的統計數據")
            
            # 準備CSV數據
            csv_data = []
            for row in results:
                csv_row = {
                    '日期': row['date'].strftime('%Y-%m-%d'),
                    '爬取貼文數': row['posts_count'],
                    '有觀看數的貼文': row['posts_with_views'],
                    '有內容的貼文': row['posts_with_content'],
                    '平均觀看數': round(row['avg_views'], 2) if row['avg_views'] else 0,
                    '最高觀看數': row['max_views'] or 0,
                    '平均按讚數': round(row['avg_likes'], 2) if row['avg_likes'] else 0,
                    '最高按讚數': row['max_likes'] or 0,
                    '平均留言數': round(row['avg_comments'], 2) if row['avg_comments'] else 0,
                    '最高留言數': row['max_comments'] or 0,
                    '數據來源種類': row['source_types'],
                    '觀看數成功率': f"{(row['posts_with_views'] / row['posts_count'] * 100):.1f}%" if row['posts_count'] > 0 else "0%",
                    '內容成功率': f"{(row['posts_with_content'] / row['posts_count'] * 100):.1f}%" if row['posts_count'] > 0 else "0%"
                }
                csv_data.append(csv_row)
            
            # 寫入CSV
            with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
                if csv_data:
                    writer = csv.DictWriter(f, fieldnames=csv_data[0].keys())
                    writer.writeheader()
                    writer.writerows(csv_data)
            
            print(f"✅ 分析數據已導出到: {output_path} ({len(csv_data)} 天數據)")
            return output_path
            
        except Exception as e:
            print(f"❌ 導出分析數據失敗: {e}")
            raise
    
    def export_comparison_report(self, json_files: List[str], output_path: str = None) -> str:
        """
        導出多次爬取的對比報告
        
        Args:
            json_files: 多個JSON結果文件路径
            output_path: 輸出CSV文件路径（可選）
        
        Returns:
            生成的CSV文件路径
        """
        try:
            # 生成輸出文件名
            if not output_path:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                output_path = f"export_comparison_{timestamp}.csv"
            
            csv_data = []
            
            for i, json_file in enumerate(json_files):
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # 提取摘要信息
                    csv_row = {
                        '文件名': Path(json_file).name,
                        '順序': i + 1,
                        '目標帳號': data.get('target_username', ''),
                        '爬取時間': data.get('timestamp', ''),
                        '總處理數': data.get('total_processed', 0),
                        'API成功數': data.get('api_success_count', 0),
                        '本地成功數': data.get('local_success_count', 0),
                        '整體成功率': f"{data.get('overall_success_rate', 0):.1f}%",
                        '觀看數提取率': f"{data.get('views_extraction_rate', 0):.1f}%",
                        '內容提取率': f"{data.get('content_extraction_rate', 0):.1f}%",
                        'URL收集時間': f"{data.get('timing', {}).get('url_collection_time', 0):.1f}s",
                        '內容提取時間': f"{data.get('timing', {}).get('content_extraction_time', 0):.1f}s",
                        '總耗時': f"{data.get('timing', {}).get('total_time', 0):.1f}s",
                        '整體速度': f"{data.get('timing', {}).get('overall_speed', 0):.2f} 篇/秒"
                    }
                    csv_data.append(csv_row)
                    
                except Exception as e:
                    print(f"⚠️ 處理文件 {json_file} 時出錯: {e}")
                    continue
            
            if not csv_data:
                raise ValueError("沒有成功處理任何JSON文件")
            
            # 寫入CSV
            with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=csv_data[0].keys())
                writer.writeheader()
                writer.writerows(csv_data)
            
            print(f"✅ 對比報告已導出到: {output_path} ({len(csv_data)} 次爬取)")
            return output_path
            
        except Exception as e:
            print(f"❌ 導出對比報告失敗: {e}")
            raise