#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API優先動態管線 - 速率限制版本
每分鐘最多60個請求，測試100個URL（從17個原始URL擴展）
"""

import json
import re
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, Optional, List
import random

class RateLimitedApiFirstReader:
    """
    API優先管線 - 速率限制版本
    限制：每分鐘最多60個請求
    """
    
    def __init__(self):
        self.local_reader_url = "http://localhost:8880"
        self.official_reader_url = "https://r.jina.ai"
        
        # 速率限制設定：每分鐘60個請求 = 每秒1個請求
        self.max_requests_per_minute = 60
        self.min_interval_between_requests = 60.0 / self.max_requests_per_minute  # 1.0秒
        self.last_request_time = 0
        
        self.NBSP = "\u00A0"
        
        # 官方API headers (主要策略)
        self.official_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'X-Return-Format': 'markdown'
        }
        
        # 本地 headers (備用策略)
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
        """內容標準化"""
        text = text.replace(self.NBSP, " ").replace("\u2002", " ").replace("\u2003", " ")
        text = text.replace("\u2009", " ").replace("\u200A", " ").replace("\u3000", " ").replace("\t", " ")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]{2,}", " ", text)
        return text

    def extract_views_count(self, markdown_content: str, post_id: str = "") -> Optional[str]:
        """觀看數提取"""
        normalized_content = self.normalize_content(markdown_content)
        
        for pattern in self.view_patterns:
            match = pattern.search(normalized_content)
            if match:
                views_number = match.group(1)
                if self.validate_views_format(views_number):
                    return views_number
        
        for pattern in self.view_patterns:
            match = pattern.search(markdown_content)
            if match:
                views_number = match.group(1)
                if self.validate_views_format(views_number):
                    return views_number
        return None

    def validate_views_format(self, views: str) -> bool:
        """驗證觀看數格式"""
        if not views: return False
        pattern = re.compile(r'^\d+(?:\.\d+)?[KMB]?$', re.IGNORECASE)
        if not pattern.match(views): return False
        try:
            actual_number = self.convert_to_number(views)
            return 1 <= actual_number <= 100_000_000
        except: return False
    
    def convert_to_number(self, number_str: str) -> int:
        """K/M/B轉數字"""
        number_str = number_str.upper()
        if number_str.endswith('K'): return int(float(number_str[:-1]) * 1000)
        elif number_str.endswith('M'): return int(float(number_str[:-1]) * 1000000)
        elif number_str.endswith('B'): return int(float(number_str[:-1]) * 1000000000)
        else: return int(number_str)

    def extract_post_content(self, content: str) -> Optional[str]:
        """提取貼文內容"""
        lines = content.split('\n')
        content_start = -1
        for i, line in enumerate(lines):
            if 'Markdown Content:' in line:
                content_start = i + 1
                break
        if content_start == -1: return None
        
        content_lines = []
        for i in range(content_start, min(content_start + 10, len(lines))):
            line = lines[i].strip()
            if line and not line.startswith('[![Image') and not line.startswith('[Image'):
                content_lines.append(line)
        return '\n'.join(content_lines) if content_lines else None

    def wait_for_rate_limit(self):
        """等待速率限制"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_interval_between_requests:
            sleep_time = self.min_interval_between_requests - time_since_last
            time.sleep(sleep_time)
        self.last_request_time = time.time()

    def fetch_content_official_rate_limited(self, url: str) -> tuple:
        """速率限制的官方API請求"""
        self.wait_for_rate_limit()
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
        """解析貼文"""
        post_id = url.split('/')[-1] if '/' in url else url
        views = self.extract_views_count(content, post_id)
        main_content = self.extract_post_content(content)
        
        return {
            'post_id': post_id, 'url': url, 'views': views, 'content': main_content, 'source': source,
            'success': views is not None and main_content is not None,
            'has_views': views is not None, 'has_content': main_content is not None,
            'content_length': len(content)
        }
    
    def is_rate_limited(self, error_msg: str) -> bool:
        """檢測是否被阻擋"""
        indicators = ['rate limit', 'too many requests', '429', 'quota exceeded', 'blocked', 'forbidden', '403', 'timeout']
        return any(indicator in error_msg.lower() for indicator in indicators)

    def rate_limited_pipeline(self, urls: List[str]):
        """速率限制版API優先管線"""
        total_start_time = time.time()
        
        print(f"🌐 速率限制版API優先管線啟動")
        print(f"📊 處理 {len(urls)} 個URL，限制每分鐘{self.max_requests_per_minute}個請求")
        print(f"⏱️ 預估最少耗時: {len(urls) * self.min_interval_between_requests:.1f}秒")
        print("=" * 80)
        
        stage1_results = {}
        blocked_urls_for_local = []
        
        # === 第一階段：序列化API處理（避免超過速率限制） ===
        print(f"🌐 (1/4) 序列化官方API處理...")
        
        for i, url in enumerate(urls):
            print(f"🌐 API請求 {i+1}/{len(urls)} ({(i+1)/len(urls)*100:.1f}%): {url.split('/')[-1]}", end=" ")
            
            success, content = self.fetch_content_official_rate_limited(url)
            
            if success:
                result = self.parse_post(url, content, "官方API-第一輪")
                if result['has_views']:
                    stage1_results[url] = result
                    print(f"✅ ({result['views']})")
                    continue
            
            # API失敗
            blocked_urls_for_local.append(url)
            if self.is_rate_limited(content):
                print(f"🚫 被阻擋 → 轉本地")
            else:
                print(f"❌ 失敗 → 轉本地")
        
        # === 第二階段：本地Reader並行處理 ===
        if blocked_urls_for_local:
            print(f"\n⚡ (2/4) 本地Reader並行處理 {len(blocked_urls_for_local)} 個項目...")
            
            # 本地不需要速率限制，可以並行
            max_workers = min(4, len(blocked_urls_for_local))
            with ThreadPoolExecutor(max_workers=max_workers) as local_executor:
                local_future_to_url = {local_executor.submit(self.fetch_content_local, url): url for url in blocked_urls_for_local}
                
                local_completed = 0
                for local_future in as_completed(local_future_to_url):
                    url = local_future_to_url[local_future]
                    local_completed += 1
                    local_progress = local_completed / len(blocked_urls_for_local)
                    
                    local_success, local_content = local_future.result()
                    if local_success:
                        result = self.parse_post(url, local_content, "本地-回退1")
                        stage1_results[url] = result
                        status = f"✅ ({result['views']})" if result['has_views'] else "❌ 無觀看數"
                        print(f"⚡ {local_completed}/{len(blocked_urls_for_local)} ({local_progress:.1%}) | {status}: {result['post_id']}")
                    else:
                        stage1_results[url] = {'url': url, 'success': False, 'source': '本地-回退1', 'error': local_content}
                        print(f"⚡ {local_completed}/{len(blocked_urls_for_local)} ({local_progress:.1%}) | ❌ 本地失敗: {url.split('/')[-1]}")

        remaining_failed = [url for url, res in stage1_results.items() if not res.get('has_views')]
        
        # === 第三階段：本地重試並行處理 ===
        if remaining_failed:
            print(f"\n🔄 (3/4) 本地重試並行處理 ({len(remaining_failed)} 個項目)")
            
            max_workers = min(4, len(remaining_failed))
            with ThreadPoolExecutor(max_workers=max_workers) as retry_executor:
                retry_future_to_url = {retry_executor.submit(self.fetch_content_local, url, False): url for url in remaining_failed}
                
                retry_completed = 0
                for retry_future in as_completed(retry_future_to_url):
                    url = retry_future_to_url[retry_future]
                    retry_completed += 1
                    
                    success, content = retry_future.result()
                    if success:
                        result = self.parse_post(url, content, "本地-重試")
                        stage1_results[url] = result
                        status = f"✅ ({result['views']})" if result['has_views'] else "❌ 無觀看數"
                        print(f"🔄 {retry_completed}/{len(remaining_failed)}: {status} {result['post_id']}")

        final_failed = [url for url, res in stage1_results.items() if not res.get('has_views')]
        
        # === 第四階段：最後API重試（序列化） ===
        if final_failed:
            print(f"\n🌐 (4/4) 最後官方API重試 ({len(final_failed)} 個項目)")
            print("🕒 序列化處理避免頻率限制...")
            
            for i, url in enumerate(final_failed):
                print(f"🌐 最後API {i+1}/{len(final_failed)}: {url.split('/')[-1]}", end=" ")
                
                success, content = self.fetch_content_official_rate_limited(url)
                if success:
                    result = self.parse_post(url, content, "官方API-回退2")
                    stage1_results[url] = result
                    status = f"✅ ({result['views']})" if result['has_views'] else "❌ 無觀看數"
                    print(status)
                else:
                    print("❌ 失敗")
        
        total_end_time = time.time()
        final_results = [stage1_results.get(url, {'url': url, 'success': False}) for url in urls]
        
        print("\n" + "=" * 80)
        success_count = len([res for res in final_results if res.get('has_views')])
        api_success_count = len([res for res in final_results if res.get('has_views') and 'API' in res.get('source', '')])
        local_success_count = success_count - api_success_count
        
        print(f"✅ 最終成功: {success_count}/{len(urls)} ({success_count/len(urls)*100:.1f}%)")
        print(f"🌐 API成功: {api_success_count} | ⚡ 本地成功: {local_success_count}")
        print(f"⏱️ 總耗時: {total_end_time - total_start_time:.1f}s")
        print(f"🏎️ 實際速度: {len(urls)/(total_end_time - total_start_time):.2f} URL/s")
        print(f"📊 平均API請求間隔: {(total_end_time - total_start_time)/len(urls):.2f}s")
        
        return final_results

def generate_test_urls(original_urls: List[str], target_count: int = 100) -> List[str]:
    """從原始URL生成測試用的URL列表"""
    test_urls = []
    
    # 先加入所有原始URL
    test_urls.extend(original_urls)
    
    # 如果需要更多URL，重複使用原始URL（可以改變順序）
    while len(test_urls) < target_count:
        remaining = target_count - len(test_urls)
        if remaining >= len(original_urls):
            # 重新排列原始URL並全部加入
            shuffled_urls = original_urls.copy()
            random.shuffle(shuffled_urls)
            test_urls.extend(shuffled_urls)
        else:
            # 隨機選擇剩餘數量的URL
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
    # 載入原始17個URL
    original_urls = load_urls_from_json("agents/playwright_crawler/debug/crawl_data_20250803_121452_934d52b1.json")
    if not original_urls: return
    
    # 生成100個測試URL
    test_urls = generate_test_urls(original_urls, 100)
    print(f"🎯 生成 {len(test_urls)} 個測試URL (從 {len(original_urls)} 個原始URL擴展)")
    
    pipeline = RateLimitedApiFirstReader()
    results = pipeline.rate_limited_pipeline(test_urls)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"rate_limited_api_results_{timestamp}.json"
    with open(filename, 'w', encoding='utf-8') as f: 
        json.dump({
            'total_urls': len(results),
            'successful_extractions': len([r for r in results if r.get('has_views')]),
            'original_url_count': len(original_urls),
            'generated_url_count': len(test_urls),
            'results': results
        }, f, ensure_ascii=False, indent=2)
    print(f"💾 結果已保存到: {filename}")

if __name__ == '__main__':
    main()