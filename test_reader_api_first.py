#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API優先動態管線 Threads Reader 解析腳本
策略: 先用官方API (穩定但會被阻擋) → 阻擋時平行轉本地Reader
"""

import json
import re
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, Optional, List
import subprocess

class ApiFirstPipelineReader:
    """
    API優先動態管線 Reader 解析器
    1. 並行處理官方API，遇到阻擋立即送本地Reader
    2. 剩餘失敗的，本地重試
    3. 最後失敗的，再次送官方API
    """
    
    def __init__(self, backend_instances: int = 4):
        self.local_reader_url = "http://localhost:8880"
        self.official_reader_url = "https://r.jina.ai"
        self.backend_instances = backend_instances
        
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
        
        # 來自 final.py 的最 robust 的觀看數提取模式
        self.view_patterns = [
            re.compile(rf'\[Thread[\s{self.NBSP}=]*?(\d+(?:[\.,]\d+)?[KMB]?)\s*views\]', re.IGNORECASE),
            re.compile(rf'Thread[\s{self.NBSP}=]*?(\d+(?:[\.,]\d+)?[KMB]?)[\s{self.NBSP}]*views', re.IGNORECASE | re.MULTILINE),
            re.compile(r'(\d+(?:[\.,]\d+)?[KMB]?)\s*views?', re.IGNORECASE),
            re.compile(r'(\d+(?:[\.,]\d+)?[KMB]?)\s*view(?:s|ing)', re.IGNORECASE),
            re.compile(r'views?\s*[:\-]\s*(\d+(?:[\.,]\d+)?[KMB]?)', re.IGNORECASE),
        ]
    
    def normalize_content(self, text: str) -> str:
        """來自 final.py 的最 robust 的內容標準化 - 不簡化版本"""
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
        """來自 final.py 的最 robust 的觀看數提取 - 不簡化版本"""
        
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
        """將 K/M/B 格式轉換為數字"""
        number_str = number_str.upper()
        if number_str.endswith('K'):
            return int(float(number_str[:-1]) * 1000)
        elif number_str.endswith('M'):
            return int(float(number_str[:-1]) * 1000000)
        elif number_str.endswith('B'):
            return int(float(number_str[:-1]) * 1000000000)
        else:
            return int(number_str)

    def extract_post_content(self, content: str) -> Optional[str]:
        """提取貼文主要內容"""
        lines = content.split('\n')
        
        # 尋找內容開始位置
        content_start = -1
        for i, line in enumerate(lines):
            if 'Markdown Content:' in line:
                content_start = i + 1
                break
        
        if content_start == -1:
            return None
        
        # 提取前幾行作為主要內容
        content_lines = []
        for i in range(content_start, min(content_start + 10, len(lines))):
            line = lines[i].strip()
            if line and not line.startswith('[![Image') and not line.startswith('[Image'):
                content_lines.append(line)
        
        return '\n'.join(content_lines) if content_lines else None

    def is_rate_limited(self, error_msg: str) -> bool:
        """判斷是否為頻率限制/阻擋錯誤"""
        rate_limit_indicators = [
            'rate limit', 'too many requests', '429', 'quota exceeded',
            'blocked', 'forbidden', '403', 'timeout', 'slow down'
        ]
        error_lower = error_msg.lower()
        return any(indicator in error_lower for indicator in rate_limit_indicators)

    def fetch_content_official(self, url: str) -> tuple:
        """從官方 Jina Reader API 獲取內容"""
        try:
            response = requests.get(f"{self.official_reader_url}/{url}", headers=self.official_headers, timeout=60)
            if response.status_code == 200:
                return True, response.text
            elif response.status_code == 429:
                return False, "RATE_LIMITED"
            elif response.status_code == 403:
                return False, "BLOCKED"
            else:
                return False, f"HTTP {response.status_code}"
        except requests.exceptions.Timeout:
            return False, "TIMEOUT"
        except Exception as e:
            return False, str(e)

    def fetch_content_local(self, url: str, use_cache: bool = True) -> tuple:
        """從本地Reader服務獲取內容"""
        headers = self.local_headers.copy()
        if not use_cache: headers['x-no-cache'] = 'true'
        try:
            response = requests.get(f"{self.local_reader_url}/{url}", headers=headers, timeout=30)
            return (True, response.text) if response.status_code == 200 else (False, f"HTTP {response.status_code}")
        except Exception as e:
            return False, str(e)
    
    def parse_post(self, url: str, content: str, source: str) -> Dict:
        """解析貼文內容 - 完整版本"""
        # 提取 post_id
        post_id = url.split('/')[-1] if '/' in url else url
        
        # 提取觀看數和內容
        views = self.extract_views_count(content, post_id)
        main_content = self.extract_post_content(content)
        
        return {
            'post_id': post_id,
            'url': url,
            'views': views,
            'content': main_content,
            'source': source,
            'success': views is not None and main_content is not None,
            'has_views': views is not None,
            'has_content': main_content is not None,
            'content_length': len(content)
        }
    
    def api_first_pipeline(self, urls: List[str]):
        """API優先動態管線處理"""
        total_start_time = time.time()
        max_workers = 4
        
        print(f"🌐 API優先動態管線啟動，併發數: {max_workers}")
        print("策略: 官方API優先 → 遇阻擋轉本地Reader")
        print("=" * 80)
        
        stage1_results = {}
        blocked_urls_for_local = []
        
        # === 第一階段：官方API並行處理 ===
        print(f"🌐 (1/4) 官方API並行處理 {len(urls)} 個 URL...")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {executor.submit(self.fetch_content_official, url): url for url in urls}
            
            completed = 0
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                completed += 1
                progress = completed / len(urls)
                
                success, content = future.result()
                
                if success:
                    result = self.parse_post(url, content, "官方API-第一輪")
                    if result['has_views']:  # 有觀看數就算成功
                        stage1_results[url] = result
                        print(f"🌐 {completed}/{len(urls)} ({progress:.1%}) | ✅ API成功: {result['post_id']} ({result['views']})")
                        continue
                
                # API失敗，檢查是否為阻擋
                if self.is_rate_limited(content):
                    blocked_urls_for_local.append(url)
                    print(f"🌐 {completed}/{len(urls)} ({progress:.1%}) | 🚫 API被阻擋: {url.split('/')[-1]} → 轉送本地Reader")
                else:
                    blocked_urls_for_local.append(url)
                    print(f"🌐 {completed}/{len(urls)} ({progress:.1%}) | ⚠️ API失敗: {url.split('/')[-1]} → 轉送本地Reader")
        
        # === 第二階段：本地Reader並行處理（API失敗/被阻擋的） ===
        if blocked_urls_for_local:
            print(f"\n⚡ (2/4) 本地Reader並行處理 {len(blocked_urls_for_local)} 個項目...")
            
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
                        if result['has_views']:
                            print(f"⚡ {local_completed}/{len(blocked_urls_for_local)} ({local_progress:.1%}) | ✅ 本地成功: {result['post_id']} ({result['views']})")
                        else:
                            print(f"⚡ {local_completed}/{len(blocked_urls_for_local)} ({local_progress:.1%}) | ❌ 本地無觀看數: {result['post_id']}")
                    else:
                        stage1_results[url] = {'url': url, 'success': False, 'source': '本地-回退1', 'error': local_content}
                        print(f"⚡ {local_completed}/{len(blocked_urls_for_local)} ({local_progress:.1%}) | ❌ 本地失敗: {url.split('/')[-1]}")

        remaining_failed = [url for url, res in stage1_results.items() if not res.get('has_views')]
        
        # === 第三階段：本地重試並行處理（還是失敗的） ===
        if remaining_failed:
            print(f"\n🔄 (3/4) 本地重試並行處理 ({len(remaining_failed)} 個項目)")
            
            with ThreadPoolExecutor(max_workers=max_workers) as retry_executor:
                retry_future_to_url = {retry_executor.submit(self.fetch_content_local, url, False): url for url in remaining_failed}
                
                retry_completed = 0
                for retry_future in as_completed(retry_future_to_url):
                    url = retry_future_to_url[retry_future]
                    retry_completed += 1
                    retry_progress = retry_completed / len(remaining_failed)
                    
                    success, content = retry_future.result()
                    if success:
                        result = self.parse_post(url, content, "本地-重試")
                        stage1_results[url] = result
                        if result['has_views']:
                            print(f"🔄 {retry_completed}/{len(remaining_failed)} ({retry_progress:.1%}) | ✅ 本地重試成功: {result['post_id']} ({result['views']})")
                        else:
                            print(f"🔄 {retry_completed}/{len(remaining_failed)} ({retry_progress:.1%}) | ❌ 本地重試無觀看數: {result['post_id']}")
                    else:
                        print(f"🔄 {retry_completed}/{len(remaining_failed)} ({retry_progress:.1%}) | ❌ 本地重試失敗: {url.split('/')[-1]}")

        final_failed = [url for url, res in stage1_results.items() if not res.get('has_views')]
        
        # === 第四階段：最後的官方API並行重試 ===
        if final_failed:
            print(f"\n🌐 (4/4) 最後官方API並行重試 ({len(final_failed)} 個項目)")
            print("🕒 等待一段時間避免頻率限制...")
            time.sleep(2)  # 稍等避免頻率限制
            
            with ThreadPoolExecutor(max_workers=max_workers) as final_executor:
                final_future_to_url = {final_executor.submit(self.fetch_content_official, url): url for url in final_failed}
                
                final_completed = 0
                for final_future in as_completed(final_future_to_url):
                    url = final_future_to_url[final_future]
                    final_completed += 1
                    final_progress = final_completed / len(final_failed)
                    
                    success, content = final_future.result()
                    if success:
                        result = self.parse_post(url, content, "官方API-回退2")
                        stage1_results[url] = result
                        if result['has_views']:
                            print(f"🌐 {final_completed}/{len(final_failed)} ({final_progress:.1%}) | ✅ 最後API成功: {result['post_id']} ({result['views']})")
                        else:
                            print(f"🌐 {final_completed}/{len(final_failed)} ({final_progress:.1%}) | ❌ 最後API無觀看數: {result['post_id']}")
                    else:
                        print(f"🌐 {final_completed}/{len(final_failed)} ({final_progress:.1%}) | ❌ 最後API失敗: {url.split('/')[-1]}")
        
        total_end_time = time.time()
        final_results = [stage1_results.get(url, {'url': url, 'success': False}) for url in urls]
        
        print("\n" + "=" * 80)
        success_count = len([res for res in final_results if res.get('has_views')])
        api_success_count = len([res for res in final_results if res.get('has_views') and 'API' in res.get('source', '')])
        local_success_count = success_count - api_success_count
        
        print(f"✅ 最終成功: {success_count}/{len(urls)} ({success_count/len(urls)*100:.1f}%)")
        print(f"🌐 API成功: {api_success_count} | ⚡ 本地成功: {local_success_count}")
        print(f"⏱️ 總耗時: {total_end_time - total_start_time:.1f}s")
        print(f"🏎️ 平均速度: {len(urls)/(total_end_time - total_start_time):.2f} URL/s")
        
        return final_results

def load_urls_from_json(file_path: str) -> List[str]:
    try:
        with open(file_path, 'r', encoding='utf-8') as f: data = json.load(f)
        urls = [post['url'] for post in data.get('posts', []) if 'url' in post]
        print(f"✅ 從 {file_path} 成功提取 {len(urls)} 個 URL。")
        return urls
    except Exception as e:
        print(f"❌ 提取 URL 時發生錯誤: {e}")
        return []

def main():
    urls = load_urls_from_json("agents/playwright_crawler/debug/crawl_data_20250803_121452_934d52b1.json")
    if not urls: return
    
    pipeline = ApiFirstPipelineReader()
    results = pipeline.api_first_pipeline(urls)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"api_first_pipeline_results_{timestamp}.json"
    with open(filename, 'w', encoding='utf-8') as f: json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"💾 結果已保存到: {filename}")

if __name__ == '__main__':
    main()