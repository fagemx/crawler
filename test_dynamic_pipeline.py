#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
動態管線 Threads Reader 解析腳本
速度優先，快速失敗，快速回退到官方API
"""

import json
import re
import requests
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, Optional, List

class DynamicPipelineReader:
    """
    動態管線 Reader 解析器
    1. 並行處理，失敗立即送官方API
    2. 剩餘失敗的，本地重試
    3. 最後失敗的，再次送官方API
    """
    
    def __init__(self, backend_instances: int = 4):
        self.local_reader_url = "http://localhost:8880"
        self.official_reader_url = "https://r.jina.ai"
        self.backend_instances = backend_instances
        
        self.NBSP = "\u00a0"
        
        self.local_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'x-wait-for-selector': 'article',
            'x-timeout': '25'
        }
        
        self.official_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'X-Return-Format': 'markdown'
        }
        
        self.view_patterns = [
            re.compile(rf'\[Thread[\s{self.NBSP}=]*?(\d+(?:[\.,]\d+)?[KMB]?)\s*views\]', re.IGNORECASE),
            re.compile(rf'Thread[\s{self.NBSP}=]*?(\d+(?:[\.,]\d+)?[KMB]?)[\s{self.NBSP}]*views', re.IGNORECASE | re.MULTILINE),
            re.compile(r'(\d+(?:[\.,]\d+)?[KMB]?)\s*views?', re.IGNORECASE),
            re.compile(r'(\d+(?:[\.,]\d+)?[KMB]?)\s*view(?:s|ing)', re.IGNORECASE),
            re.compile(r'views?\s*[:\-]\s*(\d+(?:[\.,]\d+)?[KMB]?)', re.IGNORECASE),
        ]
    
    # --- 核心函數 (與之前版本相同) ---
    def normalize_content(self, text: str) -> str:
        text = text.replace(self.NBSP, " ")
        text = text.replace("\u2002", " ").replace("\u2003", " ").replace("\u2009", " ").replace("\u200A", " ").replace("\u3000", " ")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]{2,}", " ", text)
        return text

    def extract_views_count(self, content: str) -> Optional[str]:
        normalized_content = self.normalize_content(content)
        for pattern in self.view_patterns:
            match = pattern.search(normalized_content)
            if match:
                views = match.group(1)
                if self.validate_views_format(views):
                    return views
        
        # Fallback to raw content
        for pattern in self.view_patterns:
            match = pattern.search(content)
            if match:
                views = match.group(1)
                if self.validate_views_format(views):
                    return views
        return None
    
    def validate_views_format(self, views: str) -> bool:
        """驗證觀看數格式是否合理"""
        if not views: return False
        pattern = re.compile(r'^\d+(?:\.\d+)?[KMB]?$', re.IGNORECASE)
        return bool(pattern.match(views))

    def fetch_content_local(self, url: str, use_cache: bool = True) -> tuple:
        headers = self.local_headers.copy()
        if not use_cache:
            headers['x-no-cache'] = 'true'
        try:
            response = requests.get(f"{self.local_reader_url}/{url}", headers=headers, timeout=30)
            return (True, response.text) if response.status_code == 200 else (False, f"HTTP {response.status_code}")
        except Exception as e:
            return False, str(e)

    def fetch_content_official(self, url: str) -> tuple:
        try:
            response = requests.get(f"{self.official_reader_url}/{url}", headers=self.official_headers, timeout=60)
            return (True, response.text) if response.status_code == 200 else (False, f"HTTP {response.status_code}")
        except Exception as e:
            return False, str(e)
    
    def parse_post(self, url: str, content: str, source: str) -> Dict:
        views = self.extract_views_count(content)
        post_id = url.split('/')[-1]
        return {
            'post_id': post_id,
            'url': url,
            'views': views,
            'source': source,
            'success': views is not None
        }
    
    # --- 新的動態管線邏輯 ---
    def dynamic_pipeline(self, urls: List[str]):
        """動態管線處理"""
        total_start_time = time.time()
        max_workers = self.backend_instances * 2  # 提高併發數
        
        print(f"🚀 動態管線啟動，併發數: {max_workers}")
        print("=" * 80)
        
        # --- 第一階段：並行處理 + 立即API回退 ---
        print(f"\n⚡ (1/3) 第一輪並行處理 + 快速API回退")
        print("-" * 60)
        
        stage1_results = {}
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {executor.submit(self.fetch_content_local, url): url for url in urls}
            
            completed = 0
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                completed += 1
                progress = completed / len(urls) * 100
                
                success, content = future.result()
                
                # 本地成功
                if success:
                    result = self.parse_post(url, content, "本地-第一輪")
                    if result['success']:
                        stage1_results[url] = result
                        print(f"📊 {completed}/{len(urls)} ({progress:.1f}%) | ✅ 本地成功: {result['post_id']} ({result['views']})")
                        continue
                
                # 本地失敗 → 立即送官方API
                print(f"📊 {completed}/{len(urls)} ({progress:.1f}%) | ⚠️ 本地失敗: {url.split('/')[-1]} → 轉送官方API")
                
                api_success, api_content = self.fetch_content_official(url)
                if api_success:
                    result = self.parse_post(url, api_content, "官方API-回退1")
                    stage1_results[url] = result
                    if result['success']:
                        print(f"   └── ✅ 官方API成功: {result['post_id']} ({result['views']})")
                    else:
                        print(f"   └── ❌ 官方API無觀看數: {result['post_id']}")
                else:
                    stage1_results[url] = {'url': url, 'success': False, 'source': '官方API-回退1', 'error': api_content}
                    print(f"   └── ❌ 官方API失敗: {url.split('/')[-1]} ({api_content})")

        # --- 第二階段：剩餘失敗的，本地重試 ---
        remaining_failed = [url for url, res in stage1_results.items() if not res.get('success')]
        
        if remaining_failed:
            print(f"\n🔄 (2/3) 第二輪本地重試 ({len(remaining_failed)} 個項目)")
            print("-" * 60)
            
            for i, url in enumerate(remaining_failed):
                print(f"   🔄 本地重試 {i+1}/{len(remaining_failed)}: {url.split('/')[-1]}")
                success, content = self.fetch_content_local(url, use_cache=False)
                if success:
                    result = self.parse_post(url, content, "本地-重試")
                    stage1_results[url] = result # 更新結果
        
        # --- 第三階段：最後失敗的，再次送API ---
        final_failed = [url for url, res in stage1_results.items() if not res.get('success')]
        
        if final_failed:
            print(f"\n🌐 (3/3) 最後一輪官方API重試 ({len(final_failed)} 個項目)")
            print("-" * 60)
            
            for i, url in enumerate(final_failed):
                print(f"   🌐 官方API重試 {i+1}/{len(final_failed)}: {url.split('/')[-1]}")
                success, content = self.fetch_content_official(url)
                if success:
                    result = self.parse_post(url, content, "官方API-回退2")
                    stage1_results[url] = result # 更新結果
        
        # --- 總結 ---
        total_end_time = time.time()
        final_results = [stage1_results.get(url, {'url': url, 'success': False}) for url in urls]
        
        print("\n" + "=" * 80)
        print("🏁 動態管線處理完成")
        print("=" * 80)
        
        success_count = len([res for res in final_results if res.get('success')])
        print(f"✅ 最終成功: {success_count}/{len(urls)} ({success_count/len(urls)*100:.1f}%)")
        print(f"⏱️ 總耗時: {total_end_time - total_start_time:.1f}s")
        print(f"🏎️ 平均速度: {len(urls)/(total_end_time - total_start_time):.2f} URL/s")
        
        return final_results

def load_urls_from_json(file_path: str) -> List[str]:
    """從 JSON 文件載入 URL"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        urls = [post['url'] for post in data.get('posts', []) if 'url' in post]
        print(f"✅ 從 {file_path} 成功提取 {len(urls)} 個 URL。")
        return urls
    except Exception as e:
        print(f"❌ 提取 URL 時發生錯誤: {e}")
        return []

def main():
    json_file = "agents/playwright_crawler/debug/crawl_data_20250803_121452_934d52b1.json"
    urls = load_urls_from_json(json_file)
    
    if not urls:
        print("❌ 沒有找到有效的 URL，程式結束")
        return
    
    # 假設有4個閱讀器實例
    pipeline = DynamicPipelineReader(backend_instances=4)
    results = pipeline.dynamic_pipeline(urls)
    
    # 保存結果
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"dynamic_pipeline_results_{timestamp}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"💾 結果已保存到: {filename}")

if __name__ == '__main__':
    main()