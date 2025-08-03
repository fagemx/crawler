#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
處理重複貼文：保留觀看數高的，觀看數低的用API重新提取
"""

import json
import requests
import time
from typing import Dict, List, Optional
from collections import defaultdict

class DuplicateProcessor:
    def __init__(self):
        self.official_reader_url = "https://r.jina.ai"
        self.official_headers = {'X-Return-Format': 'markdown'}
        
    def convert_views_to_number(self, views_str: str) -> int:
        """將觀看數字符串轉換為數字以便比較"""
        if not views_str:
            return 0
        
        views_str = views_str.upper().replace(',', '')
        
        if views_str.endswith('K'):
            return int(float(views_str[:-1]) * 1000)
        elif views_str.endswith('M'):
            return int(float(views_str[:-1]) * 1000000)
        elif views_str.endswith('B'):
            return int(float(views_str[:-1]) * 1000000000)
        else:
            try:
                return int(views_str)
            except:
                return 0

    def fetch_content_jina_api(self, url: str) -> tuple:
        """使用Jina API重新獲取內容"""
        try:
            print(f"    🌐 API重新提取: {url.split('/')[-1]}...", end=" ")
            response = requests.get(f"{self.official_reader_url}/{url}", 
                                  headers=self.official_headers, timeout=30)
            if response.status_code == 200:
                print("✅")
                return True, response.text
            else:
                print(f"❌ HTTP {response.status_code}")
                return False, f"HTTP {response.status_code}"
        except Exception as e:
            print(f"❌ {str(e)}")
            return False, str(e)

    def extract_post_content_smart(self, content: str) -> Optional[str]:
        """智能提取貼文內容"""
        lines = content.split('\n')
        
        # 策略1: 如果第一行是回覆，直接使用
        if lines and lines[0].strip().startswith('>>>'):
            reply_content = lines[0].strip()
            if len(reply_content) > 10:
                return reply_content
        
        # 策略2: 尋找主貼文內容
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # 跳過明顯的非內容行
            if (not stripped or
                stripped.startswith('[') or
                stripped.startswith('![') or
                stripped.startswith('http') or
                stripped.startswith('Log in') or
                stripped.startswith('Thread') or
                stripped.startswith('gvmonthly') or
                stripped.isdigit() or
                stripped in ['Translate', 'views', '===============']):
                continue
            
            # 檢查是否是有效的貼文內容
            if (len(stripped) > 15 and
                not stripped.startswith('>>>') and
                ('。' in stripped or '，' in stripped or '!' in stripped or 
                 '?' in stripped or '😆' in stripped or '😅' in stripped)):
                
                # 檢查後續是否有 Translate 標識
                for j in range(i + 1, min(i + 3, len(lines))):
                    if 'Translate' in lines[j]:
                        return stripped
                
                # 如果內容合理且長度足夠，也返回
                if len(stripped) > 25:
                    return stripped
        
        return None

    def extract_views_count(self, content: str, post_id: str) -> Optional[str]:
        """提取觀看數"""
        # 正規化內容
        content = content.replace('\u00a0', ' ').replace('\xa0', ' ')
        
        # 觀看數模式
        view_patterns = [
            r'(\d+(?:\.\d+)?[KMB]?)\s*views',
            r'Thread\s*=+\s*(\d+(?:\.\d+)?[KMB]?)\s*views',
        ]
        
        import re
        for pattern in view_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                return matches[0]
        
        return None

    def extract_engagement_data(self, content: str) -> Dict[str, Optional[str]]:
        """提取互動數據"""
        lines = content.split('\n')
        numbers = []
        
        # 尋找數字序列
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('![Image') and 'profile picture' not in stripped:
                # 在圖片後查找數字
                for j in range(i + 1, min(i + 20, len(lines))):
                    candidate = lines[j].strip()
                    import re
                    if re.match(r'^\d+(?:\.\d+)?[KMB]?$', candidate):
                        numbers.append(candidate)
                    elif candidate and candidate != "Pinned":
                        break
                
                if len(numbers) >= 3:
                    break
        
        return {
            'likes': numbers[0] if len(numbers) >= 1 else None,
            'comments': numbers[1] if len(numbers) >= 2 else None,
            'reposts': numbers[2] if len(numbers) >= 3 else None,
            'shares': numbers[3] if len(numbers) >= 4 else None,
        }

    def parse_post_complete(self, url: str, content: str, source: str) -> Dict:
        """完整解析貼文"""
        post_id = url.split('/')[-1] if '/' in url else url
        views = self.extract_views_count(content, post_id)
        main_content = self.extract_post_content_smart(content)
        engagement = self.extract_engagement_data(content)
        
        return {
            'post_id': post_id,
            'url': url,
            'views': views,
            'content': main_content,
            'source': source,
            'likes': engagement['likes'],
            'comments': engagement['comments'],
            'reposts': engagement['reposts'],
            'shares': engagement['shares'],
            'success': views is not None and main_content is not None,
            'has_views': views is not None,
            'has_content': main_content is not None,
            'has_likes': engagement['likes'] is not None,
            'has_comments': engagement['comments'] is not None,
            'has_reposts': engagement['reposts'] is not None,
            'has_shares': engagement['shares'] is not None,
            'content_length': len(content),
            'reextracted': True  # 標記為重新提取
        }

    def process_duplicates(self, filename: str):
        """處理重複貼文"""
        
        print(f"📂 處理文件: {filename}")
        
        # 讀取結果
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        results = data.get('results', [])
        print(f"📊 原始項目數: {len(results)}")
        
        # 按 post_id 分組，找出重複項
        grouped = defaultdict(list)
        for result in results:
            if result.get('post_id'):
                grouped[result['post_id']].append(result)
        
        # 處理重複項
        processed_results = []
        duplicates_found = 0
        reextracted_count = 0
        
        for post_id, items in grouped.items():
            if len(items) > 1:
                duplicates_found += 1
                print(f"\n🔍 發現重複: {post_id} ({len(items)} 個版本)")
                
                # 顯示所有版本
                for i, item in enumerate(items):
                    views = item.get('views', 'N/A')
                    views_num = self.convert_views_to_number(views)
                    source = item.get('source', 'unknown')
                    content_preview = item.get('content', 'N/A')[:30] + '...' if item.get('content') else 'N/A'
                    print(f"   版本{i+1}: {views} ({views_num:,}) | {source} | {content_preview}")
                
                # 找出觀看數最高的
                best_item = max(items, key=lambda x: self.convert_views_to_number(x.get('views', '0')))
                best_views = self.convert_views_to_number(best_item.get('views', '0'))
                
                print(f"   ✅ 保留最高觀看數版本: {best_item.get('views')}")
                processed_results.append(best_item)
                
                # 對觀看數較低的版本用API重新提取
                for item in items:
                    if item != best_item:
                        item_views = self.convert_views_to_number(item.get('views', '0'))
                        print(f"   🔄 觀看數較低 ({item.get('views')})，API重新提取...")
                        
                        # 用API重新提取
                        success, content = self.fetch_content_jina_api(item['url'])
                        
                        if success:
                            # 重新解析
                            reextracted_result = self.parse_post_complete(
                                item['url'], content, 'jina_api_reextract'
                            )
                            
                            # 比較內容是否不同
                            old_content = item.get('content', '')[:50] + '...' if item.get('content') else 'N/A'
                            new_content = reextracted_result.get('content', '')[:50] + '...' if reextracted_result.get('content') else 'N/A'
                            
                            if old_content != new_content:
                                print(f"      📝 內容已更新:")
                                print(f"         舊: {old_content}")
                                print(f"         新: {new_content}")
                            else:
                                print(f"      📝 內容相同，數據已更新")
                            
                            processed_results.append(reextracted_result)
                            reextracted_count += 1
                        else:
                            print(f"      ❌ API重新提取失敗: {content}")
                            # 保留原始數據
                            item['reextract_failed'] = True
                            item['reextract_error'] = content
                            processed_results.append(item)
                        
                        # 短暫等待，避免API限制
                        time.sleep(1)
            
            else:
                # 沒有重複，直接保留
                processed_results.append(items[0])
        
        print(f"\n📊 處理結果:")
        print(f"   🔄 發現重複組: {duplicates_found}")
        print(f"   🌐 API重新提取: {reextracted_count}")
        print(f"   📝 最終項目數: {len(processed_results)}")
        
        # 保存結果
        data['results'] = processed_results
        data['total_processed'] = len(processed_results)
        data['duplicates_processed'] = duplicates_found
        data['reextracted_count'] = reextracted_count
        
        # 重新計算統計
        successful = [r for r in processed_results if r.get('success', False)]
        data['overall_success_rate'] = len(successful) / len(processed_results) * 100 if processed_results else 0
        
        output_filename = filename.replace('.json', '_dedup.json')
        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"💾 處理結果已保存到: {output_filename}")
        
        # 顯示最終結果樣本
        print(f"\n🎯 處理後的樣本 (前5個):")
        for i, result in enumerate(processed_results[:5]):
            post_id = result.get('post_id', 'N/A')
            views = result.get('views', 'N/A')
            source = result.get('source', 'N/A')
            reextracted = result.get('reextracted', False)
            content = result.get('content', 'N/A')
            content_preview = content[:50] + '...' if len(content) > 50 else content
            reext_mark = " [重新提取]" if reextracted else ""
            
            print(f"   {i+1}. {post_id} | {views} | {source}{reext_mark}")
            print(f"      📝 {content_preview}")

if __name__ == "__main__":
    processor = DuplicateProcessor()
    
    # 處理最新的結果文件
    import glob
    result_files = glob.glob("realtime_extraction_results_*.json")
    if result_files:
        latest_file = max(result_files, key=lambda x: x.split('_')[-1])
        print(f"🎯 處理最新文件: {latest_file}")
        processor.process_duplicates(latest_file)
    else:
        print("❌ 未找到結果文件")