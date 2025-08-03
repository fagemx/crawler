#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整版三階段 Threads Reader 解析腳本
整合所有已驗證的修正：NBSP處理、Headers配置、增強觀看數提取、三階段重試
"""

import json
import re
import requests
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, Optional, List

class CompleteThreadsReaderParser:
    """
    完整版 Threads Reader 解析器
    包含三階段處理流程和所有已驗證的修正
    """
    
    def __init__(self):
        self.local_reader_url = "http://localhost:8880"
        self.official_reader_url = "https://r.jina.ai"
        
        # NBSP 字符常量 (參考 final 版本)
        self.NBSP = "\u00A0"
        
        # 已驗證有效的本地 headers 配置
        self.local_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'x-wait-for-selector': 'article',
            'x-timeout': '25'
        }
        
        # 官方API headers
        self.official_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'X-Return-Format': 'markdown'
        }
        
        # 修正後的觀看數提取模式 (參考 final 版本)
        self.view_patterns = [
            # 主要模式 - 修正 NBSP 問題
            re.compile(rf'\[Thread[\s{self.NBSP}=]*?(\d+(?:[\.,]\d+)?[KMB]?)\s*views\]', re.IGNORECASE),
            
            # 備用模式 - 處理分行情況
            re.compile(rf'Thread[\s{self.NBSP}=]*?(\d+(?:[\.,]\d+)?[KMB]?)[\s{self.NBSP}]*views', re.IGNORECASE | re.MULTILINE),
            
            # 通用模式
            re.compile(r'(\d+(?:[\.,]\d+)?[KMB]?)\s*views?', re.IGNORECASE),
            
            # 容錯模式
            re.compile(r'(\d+(?:[\.,]\d+)?[KMB]?)\s*view(?:s|ing)', re.IGNORECASE),
            re.compile(r'views?\s*[:\-]\s*(\d+(?:[\.,]\d+)?[KMB]?)', re.IGNORECASE),
        ]
    
    def normalize_content(self, text: str) -> str:
        """標準化文本 (參考 final 版本的 normalize 函數)"""
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
        """最終版觀看數提取 - NBSP修正 (參考 final 版本)"""
        
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
        """驗證觀看數格式是否合理"""
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
    
    def fetch_content_local(self, url: str, use_cache: bool = True) -> tuple:
        """從本地 Reader 服務獲取內容"""
        headers = self.local_headers.copy()
        if not use_cache:
            headers['x-no-cache'] = 'true'
        
        try:
            response = requests.get(f"{self.local_reader_url}/{url}", headers=headers, timeout=60)
            
            if response.status_code == 200:
                return True, response.text
            else:
                return False, f"HTTP {response.status_code}"
                
        except Exception as e:
            return False, str(e)
    
    def fetch_content_official(self, url: str) -> tuple:
        """從官方 Jina Reader API 獲取內容"""
        try:
            response = requests.get(f"{self.official_reader_url}/{url}", headers=self.official_headers, timeout=120)
            
            if response.status_code == 200:
                return True, response.text
            else:
                return False, f"HTTP {response.status_code}"
                
        except Exception as e:
            return False, str(e)
    
    def parse_post(self, url: str, content: str, source: str) -> Dict:
        """解析貼文內容"""
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
    
    def process_single_url(self, url: str, request_id: str) -> Dict:
        """處理單個 URL（第一輪並行處理）"""
        success, content = self.fetch_content_local(url, use_cache=True)
        
        if success:
            result = self.parse_post(url, content, "本地-第一輪")
            result['request_id'] = request_id
            return result
        else:
            return {
                'post_id': url.split('/')[-1],
                'url': url,
                'request_id': request_id,
                'success': False,
                'error': content,
                'source': "本地-第一輪"
            }
    
    def retry_local(self, url: str, request_id: str) -> Dict:
        """本地重試（第二輪，無緩存）"""
        success, content = self.fetch_content_local(url, use_cache=False)
        
        if success:
            result = self.parse_post(url, content, "本地-重試")
            result['request_id'] = request_id
            return result
        else:
            return {
                'post_id': url.split('/')[-1],
                'url': url,
                'request_id': request_id,
                'success': False,
                'error': content,
                'source': "本地-重試"
            }
    
    def retry_official(self, url: str, request_id: str) -> Dict:
        """官方API重試（第三輪）"""
        success, content = self.fetch_content_official(url)
        
        if success:
            result = self.parse_post(url, content, "官方API")
            result['request_id'] = request_id
            return result
        else:
            return {
                'post_id': url.split('/')[-1],
                'url': url,
                'request_id': request_id,
                'success': False,
                'error': content,
                'source': "官方API"
            }
    
    def three_stage_processing(self, urls: List[str], max_workers: int = 3) -> List[Dict]:
        """三階段處理流程"""
        total_start_time = time.time()
        all_results = []
        
        print(f"🚀 開始三階段處理 {len(urls)} 個 URL")
        print("=" * 80)
        
        # === 第一階段：並行處理 ===
        print(f"\n⚡ (1/3) 第一輪並行處理 ({max_workers} 併發)")
        print("-" * 60)
        
        stage1_start = time.time()
        stage1_results = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for i, url in enumerate(urls):
                future = executor.submit(self.process_single_url, url, f"並行-{i+1}")
                futures.append(future)
            
            completed = 0
            for future in as_completed(futures):
                result = future.result()
                stage1_results.append(result)
                completed += 1
                
                # 顯示進度
                progress = completed / len(urls) * 100
                status = f"✅ {result.get('views', '❌')}" if result.get('success') else f"❌ {result.get('error', '失敗')[:20]}"
                print(f"📊 {completed}/{len(urls)} ({progress:.1f}%) | {result['request_id']} | {status}")
        
        stage1_end = time.time()
        stage1_successful = [r for r in stage1_results if r.get('success') and r.get('has_views')]
        
        print(f"\n🎯 第一輪結果: {len(stage1_successful)}/{len(urls)} 成功 ({len(stage1_successful)/len(urls)*100:.1f}%)")
        print(f"⏱️ 第一輪耗時: {stage1_end - stage1_start:.1f}s")
        
        all_results.extend(stage1_results)
        
        # === 第二階段：本地重試 ===
        failed_or_incomplete = [r for r in stage1_results if not (r.get('success') and r.get('has_views') and r.get('has_content'))]
        
        if failed_or_incomplete:
            print(f"\n🔄 (2/3) 第二輪本地重試 ({len(failed_or_incomplete)} 個項目)")
            print("-" * 60)
            
            stage2_results = []
            for i, failed_result in enumerate(failed_or_incomplete):
                print(f"   🔄 本地重試 {i+1}/{len(failed_or_incomplete)}: {failed_result['post_id']}")
                
                result = self.retry_local(failed_result['url'], f"重試-{i+1}")
                stage2_results.append(result)
                
                # 小延遲避免過於頻繁
                if i < len(failed_or_incomplete) - 1:
                    time.sleep(1)
            
            stage2_successful = [r for r in stage2_results if r.get('success') and r.get('has_views')]
            print(f"🎯 第二輪新增成功: {len(stage2_successful)} 個")
            
            all_results.extend(stage2_results)
        
        # === 第三階段：官方API重試 ===
        all_failed = [r for r in all_results if not (r.get('success') and r.get('has_views') and r.get('has_content'))]
        unique_failed_urls = list(set([r['url'] for r in all_failed]))
        
        if unique_failed_urls:
            print(f"\n🌐 (3/3) 第三輪官方API重試 ({len(unique_failed_urls)} 個項目)")
            print("-" * 60)
            
            stage3_results = []
            for i, url in enumerate(unique_failed_urls):
                post_id = url.split('/')[-1]
                print(f"   🌐 官方API重試 {i+1}/{len(unique_failed_urls)}: {post_id}")
                
                result = self.retry_official(url, f"官方-{i+1}")
                stage3_results.append(result)
                
                # 稍長延遲避免觸發官方API限制
                if i < len(unique_failed_urls) - 1:
                    time.sleep(2)
            
            stage3_successful = [r for r in stage3_results if r.get('success') and r.get('has_views')]
            print(f"🎯 第三輪新增成功: {len(stage3_successful)} 個")
            
            all_results.extend(stage3_results)
        
        # === 統計最終結果 ===
        total_end_time = time.time()
        final_successful = self.get_best_results(all_results, urls)
        
        print("\n" + "=" * 80)
        print("🏁 三階段處理完成")
        print("=" * 80)
        
        success_count = len([r for r in final_successful if r.get('success') and r.get('has_views')])
        print(f"✅ 最終成功: {success_count}/{len(urls)} ({success_count/len(urls)*100:.1f}%)")
        print(f"⏱️ 總耗時: {total_end_time - total_start_time:.1f}s")
        print(f"🏎️ 平均速度: {len(urls)/(total_end_time - total_start_time):.2f} URL/s")
        
        return final_successful
    
    def get_best_results(self, all_results: List[Dict], original_urls: List[str]) -> List[Dict]:
        """獲取每個 URL 的最佳結果"""
        best_results = {}
        
        for result in all_results:
            url = result['url']
            
            # 如果還沒有結果，或新結果更好，就更新
            if url not in best_results or self.is_better_result(result, best_results[url]):
                best_results[url] = result
        
        # 按原始順序返回
        return [best_results.get(url, {'url': url, 'success': False}) for url in original_urls]
    
    def is_better_result(self, new_result: Dict, old_result: Dict) -> bool:
        """判斷新結果是否比舊結果更好"""
        new_score = 0
        old_score = 0
        
        # 有觀看數 +10分
        if new_result.get('has_views'):
            new_score += 10
        if old_result.get('has_views'):
            old_score += 10
        
        # 有內容 +5分
        if new_result.get('has_content'):
            new_score += 5
        if old_result.get('has_content'):
            old_score += 5
        
        # 成功 +1分
        if new_result.get('success'):
            new_score += 1
        if old_result.get('success'):
            old_score += 1
        
        return new_score > old_score

def load_urls_from_json(file_path: str) -> List[str]:
    """從JSON檔案中提取所有貼文URL (參考 final 版本)"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        urls = [post['url'] for post in data.get('posts', []) if 'url' in post]
        print(f"✅ 從 {file_path} 成功提取 {len(urls)} 個 URL。")
        return urls
    except Exception as e:
        print(f"❌ 提取 URL 時發生錯誤: {e}")
        return []

def save_results(results: List[Dict], filename: str = None):
    """保存結果到 JSON 文件"""
    if filename is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"complete_reader_results_{timestamp}.json"
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'total_urls': len(results),
                'successful_extractions': len([r for r in results if r.get('success') and r.get('has_views')]),
                'results': results
            }, f, ensure_ascii=False, indent=2)
        
        print(f"💾 結果已保存到: {filename}")
        
    except Exception as e:
        print(f"❌ 保存結果失敗: {e}")

def main():
    """主程式"""
    print("🎯 完整版三階段 Threads Reader 解析器")
    print("整合修正: NBSP處理 + Headers配置 + 增強觀看數提取 + 三階段重試")
    print("=" * 80)
    
    # 載入 URL 列表
    json_file = "agents/playwright_crawler/debug/crawl_data_20250803_121452_934d52b1.json"
    urls = load_urls_from_json(json_file)
    
    if not urls:
        print("❌ 沒有找到有效的 URL，程式結束")
        return
    
    # 創建解析器並開始處理
    parser = CompleteThreadsReaderParser()
    results = parser.three_stage_processing(urls, max_workers=3)
    
    # 保存結果
    save_results(results)
    
    # 顯示成功案例
    successful = [r for r in results if r.get('success') and r.get('has_views')]
    if successful:
        print(f"\n🎯 成功提取觀看數的貼文:")
        for r in successful:
            print(f"   ✅ {r['post_id']}: {r['views']} ({r['source']})")
    
    print(f"\n🎉 處理完成！共 {len(successful)}/{len(urls)} 個成功")

if __name__ == '__main__':
    main()