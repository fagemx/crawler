#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API-本地輪迴策略 Threads Reader 解析腳本
策略: 10個API → 20個本地 → 10個API → 20個本地 (輪迴)
避免API被持續阻擋，讓API有時間冷卻
"""

import json
import re
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, Optional, List
import random

class RotationPipelineReader:
    """
    輪迴策略 Reader 解析器
    10個API → 20個本地 → 10個API → 20個本地 輪迴
    """
    
    def __init__(self):
        self.local_reader_url = "http://localhost:8880"
        self.official_reader_url = "https://r.jina.ai"
        
        # 輪迴策略配置
        self.api_batch_size = 10    # 每次API批次大小
        self.local_batch_size = 20  # 每次本地批次大小
        # 不需要API冷卻時間，本地批次啟動時間已足夠
        
        self.NBSP = "\u00A0"
        
        # 官方API headers
        self.official_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'X-Return-Format': 'markdown'
        }
        
        # 來自 complete.py 的已驗證有效的本地 headers 配置
        self.local_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'x-wait-for-selector': 'article',
            'x-timeout': '25'
        }
        
        # 觀看數提取模式
        self.view_patterns = [
            re.compile(rf'\[Thread[\s{self.NBSP}=]*?(\d+(?:[\.,]\d+)?[KMB]?)\s*views\]', re.IGNORECASE),
            re.compile(rf'Thread[\s{self.NBSP}=]*?(\d+(?:[\.,]\d+)?[KMB]?)[\s{self.NBSP}]*views', re.IGNORECASE | re.MULTILINE),
            re.compile(r'(\d+(?:[\.,]\d+)?[KMB]?)\s*views?', re.IGNORECASE),
            re.compile(r'(\d+(?:[\.,]\d+)?[KMB]?)\s*view(?:s|ing)', re.IGNORECASE),
            re.compile(r'views?\s*[:\-]\s*(\d+(?:[\.,]\d+)?[KMB]?)', re.IGNORECASE),
        ]
    
    def normalize_content(self, text: str) -> str:
        """來自 final.py 的最 robust 的內容標準化 - 完整版本"""
        # ① 將各種空白字符統一替換為標準空格
        text = text.replace(self.NBSP, " ")  # NBSP (U+00A0) 
        text = text.replace("\u2002", " ")   # En Space
        text = text.replace("\u2003", " ")   # Em Space
        text = text.replace("\u2009", " ")   # Thin Space
        text = text.replace("\u200A", " ")   # Hair Space
        text = text.replace("\u3000", " ")   # Ideographic Space
        text = text.replace("\t", " ")       # Tab 替換為空格
        
        # ② 標準化行結束符
        text = text.replace("\r\n", "\n")
        text = text.replace("\r", "\n")
        
        # ③ 壓縮多個連續空格（但保留單個空格）
        text = re.sub(r"[ \t]{2,}", " ", text)
        
        return text

    def extract_views_count(self, markdown_content: str, post_id: str = "") -> Optional[str]:
        """來自 final.py 的最 robust 的觀看數提取 - 完整版本"""
        
        # 標準化內容
        normalized_content = self.normalize_content(markdown_content)
        
        # 1. 嘗試所有模式在標準化後的內容上
        for i, pattern in enumerate(self.view_patterns):
            match = pattern.search(normalized_content)
            if match:
                views_number = match.group(1)
                if self.validate_views_format(views_number):
                    return views_number
        
        # 2. 如果還是失敗，嘗試在原始內容上搜索（防止標準化過度）
        for i, pattern in enumerate(self.view_patterns):
            match = pattern.search(markdown_content)
            if match:
                views_number = match.group(1)
                if self.validate_views_format(views_number):
                    return views_number
        
        return None

    def validate_views_format(self, views: str) -> bool:
        """驗證觀看數格式是否合理 - 完整版本"""
        if not views:
            return False
        
        # 基本格式檢查
        pattern = re.compile(r'^\d+(?:\.\d+)?[KMB]?$', re.IGNORECASE)
        if not pattern.match(views):
            return False
        
        # 數字合理性檢查
        try:
            actual_number = self.convert_to_number(views)
            # 觀看數通常在 1-100M 範圍內
            return 1 <= actual_number <= 100_000_000
        except:
            return False
    
    def convert_to_number(self, number_str: str) -> int:
        """K/M/B轉數字"""
        number_str = number_str.upper()
        if number_str.endswith('K'): return int(float(number_str[:-1]) * 1000)
        elif number_str.endswith('M'): return int(float(number_str[:-1]) * 1000000)
        elif number_str.endswith('B'): return int(float(number_str[:-1]) * 1000000000)
        else: return int(number_str)

    def extract_post_content(self, content: str) -> Optional[str]:
        """提取貼文主要內容 - 增強版本"""
        lines = content.split('\n')
        
        # 多種策略尋找內容
        content_start = -1
        
        # 策略1: 尋找 'Markdown Content:'
        for i, line in enumerate(lines):
            if 'Markdown Content:' in line:
                content_start = i + 1
                break
        
        # 策略2: 如果沒找到，尋找第一個非空的實質內容行
        if content_start == -1:
            for i, line in enumerate(lines):
                stripped = line.strip()
                if (stripped and 
                    not stripped.startswith('#') and 
                    not stripped.startswith('[') and
                    not stripped.startswith('http') and
                    not stripped.startswith('!') and
                    len(stripped) > 20):  # 至少20字符才算實質內容
                    content_start = i
                    break
        
        if content_start == -1:
            return None
        
        # 提取前幾行作為主要內容
        content_lines = []
        for i in range(content_start, min(content_start + 15, len(lines))):
            if i >= len(lines):
                break
            line = lines[i].strip()
            if (line and 
                not line.startswith('[![Image') and 
                not line.startswith('[Image') and
                not line.startswith('http') and
                not line.startswith('![')):
                content_lines.append(line)
                # 如果已經有3行有效內容，就足夠了
                if len(content_lines) >= 3:
                    break
        
        result = '\n'.join(content_lines) if content_lines else None
        return result

    def extract_engagement_numbers(self, markdown_content: str) -> List[str]:
        """提取所有統計數字序列（按讚、留言、轉發、分享）"""
        lines = markdown_content.split('\n')
        
        # 策略1: 查找貼文內容後的第一個圖片，然後提取後續數字
        for i, line in enumerate(lines):
            stripped = line.strip()
            # 找到貼文圖片（通常在Translate之後）
            if stripped.startswith('![Image') and not 'profile picture' in stripped:
                numbers = []
                # 在這個圖片後查找連續的數字
                for j in range(i + 1, min(i + 20, len(lines))):
                    candidate = lines[j].strip()
                    if re.match(r'^\d+(?:\.\d+)?[KMB]?$', candidate):
                        numbers.append(candidate)
                    elif candidate and not re.match(r'^\d+(?:\.\d+)?[KMB]?$', candidate) and candidate != "Pinned":
                        # 遇到非數字行（但跳過Pinned），停止收集
                        break
                
                # 如果找到了數字序列，返回
                if len(numbers) >= 3:
                    return numbers
        
        # 策略2: 如果策略1失敗，查找任何連續的數字序列
        all_numbers = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if re.match(r'^\d+(?:\.\d+)?[KMB]?$', stripped):
                # 檢查前後文，確保這是統計數字
                context_valid = False
                # 檢查前面10行是否有圖片或貼文內容
                for k in range(max(0, i-10), i):
                    if "![Image" in lines[k] or "Translate" in lines[k]:
                        context_valid = True
                        break
                
                if context_valid:
                    all_numbers.append(stripped)
        
        # 如果找到4個或更多數字，取前4個
        if len(all_numbers) >= 4:
            return all_numbers[:4]
        elif len(all_numbers) >= 3:
            return all_numbers[:3]
        
        return all_numbers

    def extract_likes_count(self, markdown_content: str) -> Optional[str]:
        """提取按讚數"""
        lines = markdown_content.split('\n')
        
        # 方法1: 查找"Like"標籤後的數字（舊格式）
        for i, line in enumerate(lines):
            if line.strip() == "Like" and i + 2 < len(lines):
                next_line = lines[i + 2].strip()
                if re.match(r'^\d+(?:\.\d+)?[KMB]?$', next_line):
                    return next_line
        
        # 方法2: 新格式 - 從數字序列中取第一個
        numbers = self.extract_engagement_numbers(markdown_content)
        if len(numbers) >= 1:
            return numbers[0]
        
        return None

    def extract_comments_count(self, markdown_content: str) -> Optional[str]:
        """提取留言數"""
        lines = markdown_content.split('\n')
        
        # 方法1: 舊格式 - 查找Comment標籤
        for i, line in enumerate(lines):
            if line.strip() == "Comment" and i + 2 < len(lines):
                next_line = lines[i + 2].strip()
                if re.match(r'^\d+(?:\.\d+)?[KMB]?$', next_line):
                    return next_line
        
        # 方法2: 新格式 - 從數字序列中取第二個
        numbers = self.extract_engagement_numbers(markdown_content)
        if len(numbers) >= 2:
            return numbers[1]
        
        return None

    def extract_reposts_count(self, markdown_content: str) -> Optional[str]:
        """提取轉發數"""
        lines = markdown_content.split('\n')
        
        # 方法1: 舊格式 - 查找Repost標籤
        for i, line in enumerate(lines):
            if line.strip() == "Repost" and i + 2 < len(lines):
                next_line = lines[i + 2].strip()
                if re.match(r'^\d+(?:\.\d+)?[KMB]?$', next_line):
                    return next_line
        
        # 方法2: 新格式 - 從數字序列中取第三個
        numbers = self.extract_engagement_numbers(markdown_content)
        if len(numbers) >= 3:
            return numbers[2]
        
        return None

    def extract_shares_count(self, markdown_content: str) -> Optional[str]:
        """提取分享數"""
        lines = markdown_content.split('\n')
        
        # 方法1: 舊格式 - 查找Share標籤
        for i, line in enumerate(lines):
            if line.strip() == "Share" and i + 2 < len(lines):
                next_line = lines[i + 2].strip()
                if re.match(r'^\d+(?:\.\d+)?[KMB]?$', next_line):
                    return next_line
        
        # 方法2: 新格式 - 從數字序列中取第四個
        numbers = self.extract_engagement_numbers(markdown_content)
        if len(numbers) >= 4:
            return numbers[3]
        
        return None

    def fetch_content_official(self, url: str) -> tuple:
        """官方API請求"""
        try:
            response = requests.get(f"{self.official_reader_url}/{url}", headers=self.official_headers, timeout=60)
            if response.status_code == 200: return True, response.text
            elif response.status_code == 429: return False, "RATE_LIMITED"
            elif response.status_code == 403: return False, "BLOCKED"
            else: return False, f"HTTP {response.status_code}"
        except requests.exceptions.Timeout: return False, "TIMEOUT"
        except Exception as e: return False, str(e)

    def fetch_content_local(self, url: str, use_cache: bool = True) -> tuple:
        """本地Reader請求"""
        headers = self.local_headers.copy()
        if not use_cache: headers['x-no-cache'] = 'true'
        try:
            response = requests.get(f"{self.local_reader_url}/{url}", headers=headers, timeout=30)
            return (True, response.text) if response.status_code == 200 else (False, f"HTTP {response.status_code}")
        except Exception as e: return False, str(e)
    
    def parse_post(self, url: str, content: str, source: str) -> Dict:
        """解析貼文 - 完整版本包含互動數據"""
        post_id = url.split('/')[-1] if '/' in url else url
        views = self.extract_views_count(content, post_id)
        main_content = self.extract_post_content(content)
        
        # 提取互動數據
        likes = self.extract_likes_count(content)
        comments = self.extract_comments_count(content)
        reposts = self.extract_reposts_count(content)
        shares = self.extract_shares_count(content)
        
        return {
            'post_id': post_id, 'url': url, 'views': views, 'content': main_content, 'source': source,
            'likes': likes, 'comments': comments, 'reposts': reposts, 'shares': shares,
            'success': views is not None and main_content is not None,
            'has_views': views is not None, 'has_content': main_content is not None,
            'has_likes': likes is not None, 'has_comments': comments is not None,
            'has_reposts': reposts is not None, 'has_shares': shares is not None,
            'content_length': len(content)
        }

    def process_api_batch(self, urls: List[str], batch_num: int) -> Dict[str, Dict]:
        """處理API批次 (並行)"""
        print(f"🌐 API批次 #{batch_num}: 並行處理 {len(urls)} 個URL...")
        
        batch_results = {}
        max_workers = min(4, len(urls))
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {executor.submit(self.fetch_content_official, url): url for url in urls}
            
            completed = 0
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                completed += 1
                
                success, content = future.result()
                if success:
                    result = self.parse_post(url, content, f"API-批次{batch_num}")
                    batch_results[url] = result
                    status = f"✅ ({result['views']})" if result['has_views'] else "❌ 無觀看數"
                    print(f"   🌐 {completed}/{len(urls)}: {status} {result['post_id']}")
                else:
                    batch_results[url] = {'url': url, 'success': False, 'source': f"API-批次{batch_num}", 'error': content}
                    print(f"   🌐 {completed}/{len(urls)}: ❌ API失敗 {url.split('/')[-1]} ({content})")
        
        return batch_results

    def process_local_batch(self, urls: List[str], batch_num: int) -> Dict[str, Dict]:
        """處理本地批次 (並行 + 失敗立即轉API)"""
        print(f"⚡ 本地批次 #{batch_num}: 並行處理 {len(urls)} 個URL...")
        
        batch_results = {}
        failed_urls_for_api = []
        max_workers = min(4, len(urls))
        
        # === 第一階段：本地並行處理 ===
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {executor.submit(self.fetch_content_local, url): url for url in urls}
            
            completed = 0
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                completed += 1
                
                success, content = future.result()
                if success:
                    result = self.parse_post(url, content, f"本地-批次{batch_num}")
                    if result['has_views']:
                        batch_results[url] = result
                        print(f"   ⚡ {completed}/{len(urls)}: ✅ ({result['views']}) {result['post_id']}")
                        continue
                
                # 本地失敗，加入API待處理列表
                failed_urls_for_api.append(url)
                print(f"   ⚡ {completed}/{len(urls)}: ❌ 本地失敗 {url.split('/')[-1]} → 轉送API")
        
        # === 第二階段：失敗的URL立即平行轉送API ===
        if failed_urls_for_api:
            print(f"   🌐 本地失敗項目立即轉API: {len(failed_urls_for_api)} 個...")
            
            with ThreadPoolExecutor(max_workers=max_workers) as api_executor:
                api_future_to_url = {api_executor.submit(self.fetch_content_official, url): url for url in failed_urls_for_api}
                
                api_completed = 0
                for api_future in as_completed(api_future_to_url):
                    url = api_future_to_url[api_future]
                    api_completed += 1
                    
                    api_success, api_content = api_future.result()
                    if api_success:
                        result = self.parse_post(url, api_content, f"API-回退{batch_num}")
                        batch_results[url] = result
                        if result['has_views']:
                            print(f"      🌐 {api_completed}/{len(failed_urls_for_api)}: ✅ API救援成功 ({result['views']}) {result['post_id']}")
                        else:
                            print(f"      🌐 {api_completed}/{len(failed_urls_for_api)}: ❌ API無觀看數 {result['post_id']}")
                    else:
                        batch_results[url] = {'url': url, 'success': False, 'source': f"API-回退{batch_num}", 'error': api_content}
                        print(f"      🌐 {api_completed}/{len(failed_urls_for_api)}: ❌ API也失敗 {url.split('/')[-1]}")
        
        return batch_results

    def rotation_pipeline(self, urls: List[str]):
        """輪迴策略管線處理"""
        total_start_time = time.time()
        
        print(f"🔄 輪迴策略管線啟動")
        print(f"📊 處理 {len(urls)} 個URL")
        print(f"🌐 API批次大小: {self.api_batch_size} | ⚡ 本地批次大小: {self.local_batch_size}")
        print(f"🕒 本地批次啟動時間自動提供API冷卻")
        print("✅ 已整合最佳化: Headers配置 + NBSP正規化 + 雙重提取邏輯")
        print("=" * 80)
        
        all_results = {}
        remaining_urls = urls.copy()
        batch_counter = 1
        
        while remaining_urls:
            current_batch_size = len(remaining_urls)
            
            # === API批次處理 ===
            if current_batch_size > 0:
                api_batch_size = min(self.api_batch_size, current_batch_size)
                api_batch_urls = remaining_urls[:api_batch_size]
                remaining_urls = remaining_urls[api_batch_size:]
                
                api_results = self.process_api_batch(api_batch_urls, batch_counter)
                all_results.update(api_results)
                # 本地批次啟動時間已提供足夠的API冷卻
            
            # === 本地批次處理 ===
            if remaining_urls:
                local_batch_size = min(self.local_batch_size, len(remaining_urls))
                local_batch_urls = remaining_urls[:local_batch_size]
                remaining_urls = remaining_urls[local_batch_size:]
                
                local_results = self.process_local_batch(local_batch_urls, batch_counter)
                all_results.update(local_results)
            
            batch_counter += 1
            
            # 顯示進度
            processed_count = len(all_results)
            print(f"\n📊 已處理: {processed_count}/{len(urls)} ({processed_count/len(urls)*100:.1f}%)")
            print(f"🎯 剩餘: {len(remaining_urls)} 個URL")
            
            if remaining_urls:
                print("-" * 60)
        
        # === 最終統計 ===
        total_end_time = time.time()
        final_results = [all_results.get(url, {'url': url, 'success': False}) for url in urls]
        
        print("\n" + "=" * 80)
        success_count = len([res for res in final_results if res.get('has_views')])
        api_success_count = len([res for res in final_results if res.get('has_views') and 'API' in res.get('source', '')])
        local_success_count = success_count - api_success_count
        
        # 統計各批次的成功率
        api_batches = {}
        local_batches = {}
        api_rescue_batches = {}
        
        for res in final_results:
            if res.get('source'):
                source = res['source']
                if 'API-批次' in source:
                    batch_key = source.split('批次')[1]
                    if batch_key not in api_batches:
                        api_batches[batch_key] = {'total': 0, 'success': 0}
                    api_batches[batch_key]['total'] += 1
                    if res.get('has_views'):
                        api_batches[batch_key]['success'] += 1
                elif '本地-批次' in source:
                    batch_key = source.split('批次')[1]
                    if batch_key not in local_batches:
                        local_batches[batch_key] = {'total': 0, 'success': 0}
                    local_batches[batch_key]['total'] += 1
                    if res.get('has_views'):
                        local_batches[batch_key]['success'] += 1
                elif 'API-回退' in source:
                    batch_key = source.split('回退')[1]
                    if batch_key not in api_rescue_batches:
                        api_rescue_batches[batch_key] = {'total': 0, 'success': 0}
                    api_rescue_batches[batch_key]['total'] += 1
                    if res.get('has_views'):
                        api_rescue_batches[batch_key]['success'] += 1
        
        print(f"✅ 最終成功: {success_count}/{len(urls)} ({success_count/len(urls)*100:.1f}%)")
        print(f"🌐 API成功: {api_success_count} | ⚡ 本地成功: {local_success_count}")
        print(f"⏱️ 總耗時: {total_end_time - total_start_time:.1f}s")
        print(f"🏎️ 平均速度: {len(urls)/(total_end_time - total_start_time):.2f} URL/s")
        
        print(f"\n📈 各批次成功率:")
        for batch_key in sorted(api_batches.keys()):
            stats = api_batches[batch_key]
            rate = stats['success'] / stats['total'] * 100 if stats['total'] > 0 else 0
            print(f"   🌐 API批次{batch_key}: {stats['success']}/{stats['total']} ({rate:.1f}%)")
        for batch_key in sorted(local_batches.keys()):
            stats = local_batches[batch_key]
            rate = stats['success'] / stats['total'] * 100 if stats['total'] > 0 else 0
            print(f"   ⚡ 本地批次{batch_key}: {stats['success']}/{stats['total']} ({rate:.1f}%)")
        for batch_key in sorted(api_rescue_batches.keys()):
            stats = api_rescue_batches[batch_key]
            rate = stats['success'] / stats['total'] * 100 if stats['total'] > 0 else 0
            print(f"   🚀 API救援{batch_key}: {stats['success']}/{stats['total']} ({rate:.1f}%)")
        
        return final_results

def generate_test_urls(original_urls: List[str], target_count: int = 100) -> List[str]:
    """從原始URL生成測試用的URL列表"""
    test_urls = []
    test_urls.extend(original_urls)
    
    while len(test_urls) < target_count:
        remaining = target_count - len(test_urls)
        if remaining >= len(original_urls):
            shuffled_urls = original_urls.copy()
            random.shuffle(shuffled_urls)
            test_urls.extend(shuffled_urls)
        else:
            selected_urls = random.sample(original_urls, remaining)
            test_urls.extend(selected_urls)
    
    return test_urls[:target_count]

def load_urls_from_json(file_path: str) -> List[str]:
    try:
        with open(file_path, 'r', encoding='utf-8') as f: data = json.load(f)
        urls = [post['url'] for post in data.get('posts', []) if 'url' in post]
        print(f"✅ 從 {file_path} 成功提取 {len(urls)} 個原始 URL。")
        return urls
    except Exception as e:
        print(f"❌ 提取 URL 時發生錯誤: {e}")
        return []

def main():
    # 載入原始URL
    original_urls = load_urls_from_json("agents/playwright_crawler/debug/crawl_data_20250803_121452_934d52b1.json")
    if not original_urls: return
    
    # 生成100個測試URL
    test_urls = generate_test_urls(original_urls, 100)
    print(f"🎯 生成 {len(test_urls)} 個測試URL (從 {len(original_urls)} 個原始URL擴展)")
    
    pipeline = RotationPipelineReader()
    results = pipeline.rotation_pipeline(test_urls)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"rotation_pipeline_results_{timestamp}.json"
    with open(filename, 'w', encoding='utf-8') as f: 
        json.dump({
            'total_urls': len(results),
            'successful_extractions': len([r for r in results if r.get('has_views')]),
            'api_batch_size': 10,
            'local_batch_size': 20,
            'original_url_count': len(original_urls),
            'results': results
        }, f, ensure_ascii=False, indent=2)
    print(f"💾 結果已保存到: {filename}")

if __name__ == '__main__':
    main()