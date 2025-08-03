#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多線程Reader解析腳本 (V15 - 完整調試版)
保存第一輪所有內容以分析失敗原因
"""

import json
import re
import requests
import time
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Optional, List

class DebugThreadsReaderParser:
    """
    調試版 Threads Reader 解析器
    重點：保存所有原始內容進行分析
    """
    
    def __init__(self, backend_instances: int = 4):
        self.backend_instances = backend_instances
        self.lb_url = "http://localhost:8880"
        self.official_reader_url = "https://r.jina.ai"
        
        # NBSP 字符常量
        self.NBSP = "\u00A0"
        
        # --- 修正後的觀看數提取模式 ---
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
        
        self.engagement_pattern = re.compile(r'^\d+(?:\.\d+)?[KMB]?$')
        
        # --- 優化的Session配置 ---
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=20,
            pool_maxsize=30,
            max_retries=0
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        
        print(f"🔧 調試版初始化完成")
        print(f"   後端實例: {backend_instances} 個")
        print(f"   觀看數模式: {len(self.view_patterns)} 個 (含NBSP修正)")

    def normalize_content(self, text: str) -> str:
        """內容標準化 - 處理各種空格和換行問題"""
        # ① 將NBSP、全形空格轉為普通空格
        text = text.replace(self.NBSP, " ").replace("\u3000", " ")
        
        # ② 統一換行符
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        
        # ③ 壓縮多個連續空格（但保留單個空格）
        text = re.sub(r"[ \t]{2,}", " ", text)
        
        return text

    def analyze_views_extraction_detailed(self, content: str, post_id: str) -> dict:
        """詳細分析觀看數提取失敗的原因"""
        
        # 標準化內容
        normalized_content = self.normalize_content(content)
        
        analysis = {
            'post_id': post_id,
            'content_length': len(content),
            'normalized_length': len(normalized_content),
            'pattern_results': [],
            'first_10_lines_raw': [],
            'first_10_lines_normalized': [],
            'lines_with_thread': [],
            'lines_with_view': [],
            'all_numbers_found': [],
            'potential_views': []
        }
        
        # 保存前10行原始內容
        raw_lines = content.split('\n')[:10]
        for i, line in enumerate(raw_lines):
            analysis['first_10_lines_raw'].append({
                'line_num': i + 1,
                'content': line,
                'repr': repr(line),
                'length': len(line)
            })
        
        # 保存前10行標準化內容
        norm_lines = normalized_content.split('\n')[:10]
        for i, line in enumerate(norm_lines):
            analysis['first_10_lines_normalized'].append({
                'line_num': i + 1,
                'content': line,
                'repr': repr(line),
                'length': len(line)
            })
        
        # 測試每個模式
        for i, pattern in enumerate(self.view_patterns):
            # 在原始內容上測試
            raw_matches = pattern.findall(content)
            # 在標準化內容上測試
            norm_matches = pattern.findall(normalized_content)
            
            analysis['pattern_results'].append({
                'pattern_index': i,
                'pattern': pattern.pattern,
                'raw_matches': raw_matches,
                'normalized_matches': norm_matches,
                'success': len(norm_matches) > 0 or len(raw_matches) > 0
            })
        
        # 找出包含 "thread" 的行
        all_lines = content.split('\n')
        for i, line in enumerate(all_lines):
            if 'thread' in line.lower():
                analysis['lines_with_thread'].append({
                    'line_num': i + 1,
                    'content': line.strip(),
                    'repr': repr(line)
                })
        
        # 找出包含 "view" 的行
        for i, line in enumerate(all_lines):
            if 'view' in line.lower():
                analysis['lines_with_view'].append({
                    'line_num': i + 1,
                    'content': line.strip(),
                    'repr': repr(line)
                })
        
        # 找出所有數字
        number_pattern = re.compile(r'(\d+(?:[\.,]\d+)?[KMB]?)', re.IGNORECASE)
        all_numbers = number_pattern.findall(content)
        analysis['all_numbers_found'] = list(set(all_numbers))
        
        # 找出可能的觀看數
        for num in analysis['all_numbers_found']:
            try:
                actual_val = self.convert_number_to_int(num)
                if actual_val >= 100:  # 可能是觀看數
                    analysis['potential_views'].append({
                        'number': num,
                        'value': actual_val
                    })
            except:
                pass
        
        return analysis

    def enhanced_extract_views_count(self, markdown_content: str, post_id: str = "", debug: bool = False) -> Optional[str]:
        """增強版觀看數提取 - 返回詳細分析"""
        
        # 標準化內容
        normalized_content = self.normalize_content(markdown_content)
        
        # 1. 嘗試所有模式在標準化後的內容上
        for i, pattern in enumerate(self.view_patterns):
            match = pattern.search(normalized_content)
            if match:
                views_number = match.group(1)
                if self.validate_number_format(views_number):
                    return f"{views_number} views"
        
        # 2. 如果還是失敗，嘗試在原始內容上搜索
        for i, pattern in enumerate(self.view_patterns):
            match = pattern.search(markdown_content)
            if match:
                views_number = match.group(1)
                if self.validate_number_format(views_number):
                    return f"{views_number} views"
        
        return None

    def validate_number_format(self, number: str) -> bool:
        """驗證數字格式是否合理"""
        if not number:
            return False
        
        # 基本格式檢查 - 支援逗號和點作為小數分隔符
        pattern = re.compile(r'^\d+(?:[,\.]\d+)?[KMB]?$', re.IGNORECASE)
        if not pattern.match(number):
            return False
        
        # 轉換為實際數字進行合理性檢查
        try:
            actual_number = self.convert_number_to_int(number)
            # 觀看數通常在 1-100M 範圍內
            return 1 <= actual_number <= 100_000_000
        except:
            return False

    def convert_number_to_int(self, number_str: str) -> int:
        """將 K/M/B 格式的數字轉換為整數 - 支援逗號分隔符"""
        number_str = number_str.upper().replace(',', '.')  # 統一小數分隔符
        
        if number_str.endswith('K'):
            return int(float(number_str[:-1]) * 1000)
        elif number_str.endswith('M'):
            return int(float(number_str[:-1]) * 1000000)
        elif number_str.endswith('B'):
            return int(float(number_str[:-1]) * 1000000000)
        else:
            return int(float(number_str))

    def convert_url_to_threads_net(self, url: str) -> str:
        """將 threads.com URL 轉換為 threads.net"""
        return url.replace("threads.com", "threads.net")

    def fetch_content_local(self, post_url: str, use_cache: bool = True, timeout: int = 60) -> str:
        """從本地Reader服務獲取內容"""
        corrected_url = self.convert_url_to_threads_net(post_url)
        reader_url = f"{self.lb_url}/{corrected_url}"
        
        headers = {}
        if not use_cache:
            headers['x-no-cache'] = 'true'
        
        try:
            response = self.session.get(reader_url, headers=headers, timeout=(10, timeout))
            response.raise_for_status()
            return response.text
        except requests.exceptions.Timeout:
            return ""
        except requests.exceptions.RequestException:
            return ""

    def extract_post_content(self, markdown_content: str) -> Optional[str]:
        """提取貼文內容"""
        normalized_content = self.normalize_content(markdown_content)
        lines = normalized_content.split('\n')
        content_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith("Title:") or line.startswith("URL Source:") or line.startswith("Markdown Content:"):
                continue
            if "===============" in line or "---" in line:
                break
            if not line.startswith("[") and not line.startswith("!") and len(line) > 10:
                content_lines.append(line)
                if len(content_lines) >= 3:
                    break
        
        return ' '.join(content_lines) if content_lines else None

    def extract_engagement_numbers(self, markdown_content: str) -> Dict[str, str]:
        """提取互動數據序列"""
        normalized_content = self.normalize_content(markdown_content)
        lines = normalized_content.split('\n')
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            if (stripped.startswith('![Image') and 
                'profile picture' not in stripped and 
                i > 0 and any('Translate' in lines[k] for k in range(max(0, i-3), i+1))):
                
                numbers = []
                for j in range(i + 1, min(i + 15, len(lines))):
                    candidate = lines[j].strip()
                    if self.engagement_pattern.match(candidate):
                        numbers.append(candidate)
                    elif candidate and candidate not in ["Pinned", "", "Translate"]:
                        break
                
                engagement_data = {}
                if len(numbers) >= 1: engagement_data['likes'] = numbers[0]
                if len(numbers) >= 2: engagement_data['comments'] = numbers[1]  
                if len(numbers) >= 3: engagement_data['reposts'] = numbers[2]
                if len(numbers) >= 4: engagement_data['shares'] = numbers[3]
                
                if len(numbers) >= 3:
                    return engagement_data
        return {}

    def parse_post_local_debug(self, post_url: str, use_cache: bool = True, timeout: int = 60) -> Dict:
        """使用本地服務解析 - 完整調試版"""
        content = self.fetch_content_local(post_url, use_cache, timeout)
        post_id = post_url.split('/')[-1]
        
        if not content:
            return {
                "url": post_url,
                "post_id": post_id,
                "error": "無法獲取內容",
                "raw_content": "",
                "analysis": None
            }
        
        engagement = self.extract_engagement_numbers(content)
        extracted_content = self.extract_post_content(content)
        extracted_views = self.enhanced_extract_views_count(content, post_id)
        
        # 如果觀看數提取失敗，進行詳細分析
        analysis = None
        if not extracted_views:
            analysis = self.analyze_views_extraction_detailed(content, post_id)
        
        return {
            "url": post_url,
            "post_id": post_id,
            "content": extracted_content,
            "views": extracted_views,
            "likes": engagement.get('likes'),
            "comments": engagement.get('comments'),
            "reposts": engagement.get('reposts'),
            "shares": engagement.get('shares'),
            "raw_length": len(content),
            "raw_content": content,  # 保存完整原始內容
            "analysis": analysis,    # 失敗分析（僅在失敗時有值）
            "success": bool(extracted_views and extracted_content),
            "error": None
        }

def load_urls_from_file(file_path: str) -> List[str]:
    """從JSON檔案中提取所有貼文URL"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        urls = [post['url'] for post in data.get('posts', []) if 'url' in post]
        print(f"✅ 從 {file_path} 成功提取 {len(urls)} 個 URL。")
        return urls
    except Exception as e:
        print(f"❌ 提取 URL 時發生錯誤: {e}")
        return []

def detect_reader_instances():
    """檢測Reader實例數量"""
    try:
        result = subprocess.run([
            'docker', 'ps', 
            '--filter', 'name=reader', 
            '--filter', 'status=running',
            '--format', '{{.Names}}'
        ], capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            containers = result.stdout.strip().split('\n')
            reader_containers = [name for name in containers if 'reader-' in name and 'lb' not in name and name.strip()]
            return len(reader_containers)
        return 4  # 預設值
    except:
        return 4  # 預設值

def main():
    """主函數：完整調試版"""
    json_file_path = 'agents/playwright_crawler/debug/crawl_data_20250803_121452_934d52b1.json'
    
    # --- 檢測配置 ---
    backend_instances = detect_reader_instances()
    max_workers = backend_instances * 2  # 保守併發
    
    urls_to_process = load_urls_from_file(json_file_path)
    if not urls_to_process:
        return

    total_urls = len(urls_to_process)
    parser = DebugThreadsReaderParser(backend_instances)
    results = []
    
    start_time = time.time()
    print(f"\n🚀 完整調試版啟動！目標：分析所有失敗原因")
    print(f"📊 配置: {backend_instances}個實例, 併發數: {max_workers}")
    print("🎯 重點: ✅保存所有內容 ✅詳細失敗分析 ✅完整調試信息")

    # --- 第一層: 平行處理並保存所有內容 ---
    print(f"\n⚡ 完整調試併發處理 {total_urls} 個 URL...")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(parser.parse_post_local_debug, url, True, 45): url for url in urls_to_process}
        
        completed = 0
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            completed += 1
            progress = completed / total_urls
            bar_length = 40
            filled_length = int(bar_length * progress)
            bar = '█' * filled_length + '-' * (bar_length - filled_length)
            
            try:
                result = future.result()
                results.append(result)
                
                # 即時狀態顯示
                status = "✅" if result['success'] else "❌"
                post_id = result['post_id']
                print(f'\r進度: |{bar}| {completed}/{total_urls} ({progress:.1%}) {status} {post_id}', end='', flush=True)
            except Exception as e:
                error_result = {
                    "url": url,
                    "post_id": url.split('/')[-1],
                    "error": f"執行緒異常: {str(e)}",
                    "success": False
                }
                results.append(error_result)
                print(f'\r進度: |{bar}| {completed}/{total_urls} ({progress:.1%}) ❌ {url.split("/")[-1]}', end='', flush=True)

    end_time = time.time()
    total_time = end_time - start_time
    
    # 統計結果
    successful = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]
    
    print(f"\n\n🎯 完整調試版結果:")
    print(f"   總處理數量: {total_urls}")
    print(f"   成功: {len(successful)} ({len(successful)/total_urls*100:.1f}%)")
    print(f"   失敗: {len(failed)} ({len(failed)/total_urls*100:.1f}%)")
    print(f"   總耗時: {total_time:.1f}s")
    print(f"   平均速度: {total_urls/total_time:.2f} URL/秒")

    # 保存完整結果
    output_filename = 'parallel_reader_debug_results.json'
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n💾 完整調試結果已保存到: {output_filename}")
    
    # 保存失敗案例的詳細分析
    if failed:
        failed_analysis = []
        for item in failed:
            if item.get('analysis'):
                failed_analysis.append(item['analysis'])
        
        if failed_analysis:
            analysis_filename = 'failed_views_analysis.json'
            with open(analysis_filename, 'w', encoding='utf-8') as f:
                json.dump(failed_analysis, f, ensure_ascii=False, indent=2)
            print(f"🔍 失敗案例詳細分析已保存到: {analysis_filename}")
    
    # 顯示失敗案例摘要
    print(f"\n📋 失敗案例摘要:")
    for item in failed:
        post_id = item['post_id']
        if item.get('analysis'):
            analysis = item['analysis']
            potential_views = analysis.get('potential_views', [])
            print(f"   ❌ {post_id}: 內容長度={analysis['content_length']}, 潛在觀看數={len(potential_views)}")
            if potential_views:
                for pv in potential_views[:3]:  # 只顯示前3個
                    print(f"      - {pv['number']} ({pv['value']:,})")
        else:
            error = item.get('error', '未知錯誤')
            print(f"   ❌ {post_id}: {error}")
    
    print("\n" + "="*80)
    print("🔍 完整調試版執行完畢！")
    print(f"📂 請檢查以下檔案進行深入分析:")
    print(f"   • {output_filename} - 完整結果（包含所有原始內容）")
    if failed:
        print(f"   • failed_views_analysis.json - 失敗案例詳細分析")
    print("="*80)

if __name__ == "__main__":
    main()