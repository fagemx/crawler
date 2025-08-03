#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多線程Reader解析腳本 (V14 - NBSP修正版)
解決不間斷空格導致的觀看數提取失敗問題
"""

import json
import re
import requests
import time
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Optional, List

class FinalThreadsReaderParser:
    """
    最終版 Threads Reader 解析器
    重點修正：NBSP (U+00A0) 字符問題
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
        
        print(f"🔧 NBSP修正版初始化完成")
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

    def debug_views_extraction(self, content: str, post_id: str) -> None:
        """調試模式：在找不到觀看數時打印前10行的詳細信息"""
        print(f"\n🔍 調試 {post_id} - 觀看數提取失敗")
        lines = content.split('\n')[:10]
        for i, line in enumerate(lines):
            print(f"  L{i+1}: {repr(line)}")
        print()

    def enhanced_extract_views_count(self, markdown_content: str, post_id: str = "", debug: bool = False) -> Optional[str]:
        """最終版觀看數提取 - NBSP修正 + 調試模式"""
        
        # 標準化內容
        normalized_content = self.normalize_content(markdown_content)
        
        # 1. 嘗試所有模式在標準化後的內容上
        for i, pattern in enumerate(self.view_patterns):
            match = pattern.search(normalized_content)
            if match:
                views_number = match.group(1)
                if self.validate_number_format(views_number):
                    if debug:
                        print(f"✅ Pattern {i} 成功: {views_number}")
                    return f"{views_number} views"
        
        # 2. 如果還是失敗，嘗試在原始內容上搜索（防止標準化過度）
        for i, pattern in enumerate(self.view_patterns):
            match = pattern.search(markdown_content)
            if match:
                views_number = match.group(1)
                if self.validate_number_format(views_number):
                    if debug:
                        print(f"✅ Pattern {i} (原始) 成功: {views_number}")
                    return f"{views_number} views"
        
        # 3. 如果開啟調試模式，顯示詳細信息
        if debug and post_id:
            self.debug_views_extraction(markdown_content, post_id)
        
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

    def fetch_content_official(self, post_url: str) -> str:
        """從官方 Jina Reader 服務獲取內容"""
        corrected_url = self.convert_url_to_threads_net(post_url)
        jina_url = f"{self.official_reader_url}/{corrected_url}"
        headers = {"X-Return-Format": "markdown"}
        try:
            response = self.session.get(jina_url, headers=headers, timeout=(10, 120))
            response.raise_for_status()
            return response.text
        except Exception:
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

    def parse_post_local(self, post_url: str, use_cache: bool = True, timeout: int = 60, debug: bool = False) -> Dict:
        """使用本地服務解析"""
        content = self.fetch_content_local(post_url, use_cache, timeout)
        if not content:
            return {"url": post_url, "error": "無法獲取內容"}
        
        post_id = post_url.split('/')[-1]
        engagement = self.extract_engagement_numbers(content)
        
        result = {
            "url": post_url,
            "content": self.extract_post_content(content),
            "views": self.enhanced_extract_views_count(content, post_id, debug),
            "likes": engagement.get('likes'),
            "comments": engagement.get('comments'),
            "reposts": engagement.get('reposts'),
            "shares": engagement.get('shares'),
            "raw_length": len(content)
        }
        
        # 如果觀看數提取失敗且開啟調試，額外處理
        if debug and not result.get("views") and result.get("content"):
            print(f"⚠️ {post_id}: 有內容但無觀看數")
        
        return result

    def parse_post_official(self, post_url: str) -> Dict:
        """使用官方服務解析"""
        content = self.fetch_content_official(post_url)
        if not content:
            return {"url": post_url, "error": "無法從官方API獲取內容"}
        
        post_id = post_url.split('/')[-1]
        engagement = self.extract_engagement_numbers(content)
        
        return {
            "url": post_url,
            "content": self.extract_post_content(content),
            "views": self.enhanced_extract_views_count(content, post_id),
            "likes": engagement.get('likes'),
            "comments": engagement.get('comments'),
            "reposts": engagement.get('reposts'),
            "shares": engagement.get('shares'),
            "raw_length": len(content)
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
    """主函數：NBSP修正版"""
    json_file_path = 'agents/playwright_crawler/debug/crawl_data_20250803_121452_934d52b1.json'
    
    # --- 檢測配置 ---
    backend_instances = detect_reader_instances()
    max_workers = backend_instances * 2  # 保守併發
    
    urls_to_process = load_urls_from_file(json_file_path)
    if not urls_to_process:
        return

    total_urls = len(urls_to_process)
    parser = FinalThreadsReaderParser(backend_instances)
    results = {}
    
    start_time = time.time()
    print(f"\n🚀 NBSP修正版啟動！目標：突破 90% 成功率")
    print(f"📊 配置: {backend_instances}個實例, 併發數: {max_workers}")
    print("🎯 關鍵修正: ✅NBSP字符處理 ✅內容標準化 ✅調試模式")

    # --- 第一層: 平行處理 ---
    print(f"\n⚡ (1/3) NBSP修正併發處理 {total_urls} 個 URL...")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(parser.parse_post_local, url, True, 45, False): url for url in urls_to_process}
        
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
                results[url] = result
                
                # 即時狀態顯示
                status = "✅" if (result.get("views") and result.get("content")) else "❌"
                post_id = url.split('/')[-1]
                print(f'\r進度: |{bar}| {completed}/{total_urls} ({progress:.1%}) {status} {post_id}', end='', flush=True)
            except Exception:
                results[url] = {"url": url, "error": "執行緒異常"}
                print(f'\r進度: |{bar}| {completed}/{total_urls} ({progress:.1%}) ❌ {url.split("/")[-1]}', end='', flush=True)

    # 第一輪統計
    first_round_success = sum(1 for res in results.values() if not res.get("error") and res.get("views") and res.get("content"))
    first_round_time = time.time() - start_time
    
    print(f"\n\n🎯 NBSP修正版第一輪結果: {first_round_success}/{total_urls} 成功 ({first_round_success/total_urls*100:.1f}%)")
    print(f"📊 效能: {first_round_time:.1f}s, 速度: {total_urls/first_round_time:.2f} URL/秒")
    
    # 詳細分析失敗原因
    failures_by_type = {"missing_views": 0, "missing_content": 0, "missing_both": 0, "http_error": 0}
    for res in results.values():
        if res.get("error"):
            failures_by_type["http_error"] += 1
        elif not res.get("views") and not res.get("content"):
            failures_by_type["missing_both"] += 1
        elif not res.get("views"):
            failures_by_type["missing_views"] += 1
        elif not res.get("content"):
            failures_by_type["missing_content"] += 1
    
    print(f"📋 失敗分析: 觀看數缺失={failures_by_type['missing_views']}, 內容缺失={failures_by_type['missing_content']}, HTTP錯誤={failures_by_type['http_error']}")

    # --- 第二層: 調試重試 ---
    print(f"\n🔄 (2/3) 調試模式重試失敗項目...")
    local_retries_attempted = 0
    urls_to_retry_local = [url for url, res in results.items() if res.get("error") or not res.get("views") or not res.get("content")]
    
    if urls_to_retry_local:
        print(f"📝 需要重試: {len(urls_to_retry_local)} 個項目 (調試模式+無快取+75s超時)")
        for url in urls_to_retry_local:
            local_retries_attempted += 1
            post_id = url.split('/')[-1]
            print(f"  🔍 調試重試 {local_retries_attempted}: {post_id}")
            results[url] = parser.parse_post_local(url, use_cache=False, timeout=75, debug=True)
    else:
        print("✅ 第一輪數據已完整。")

    # --- 第三層: 官方API救援 ---
    print(f"\n🌐 (3/3) 官方API最終救援...")
    official_retries_attempted = 0
    urls_to_retry_official = [url for url, res in results.items() if res.get("error") or not res.get("views") or not res.get("content")]
    
    if urls_to_retry_official:
        print(f"🔗 轉官方API: {len(urls_to_retry_official)} 個項目")
        for url in urls_to_retry_official:
            official_retries_attempted += 1
            post_id = url.split('/')[-1]
            print(f"  🌐 官方API {official_retries_attempted}: {post_id}")
            results[url] = parser.parse_post_official(url)
    else:
        print("✅ 本地重試後數據已完整。")

    end_time = time.time()
    total_time = end_time - start_time

    # --- 最終統計與保存 ---
    final_success_results = [res for res in results.values() if not res.get("error") and res.get("views") and res.get("content")]
    final_error_count = total_urls - len(final_success_results)

    if final_success_results:
        output_filename = 'parallel_reader_results_final.json'
        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(final_success_results, f, ensure_ascii=False, indent=2)
        print(f"\n💾 {len(final_success_results)} 筆完整結果已保存到: {output_filename}")

    print("\n" + "="*80)
    print("🏆 NBSP修正版執行完畢！")
    print(f"📊 處理統計:")
    print(f"   - 後端實例: {backend_instances} 個")
    print(f"   - 關鍵修正: NBSP字符 (U+00A0) 處理")
    print(f"   - 總URL數量: {total_urls}")
    print(f"   - 第一輪成功率: {first_round_success/total_urls*100:.1f}% ({first_round_success}/{total_urls})")
    print(f"   - 本地重試: {local_retries_attempted} 次")
    print(f"   - 官方API重試: {official_retries_attempted} 次")
    print(f"   - 最終成功: {len(final_success_results)} ({len(final_success_results)/total_urls*100:.1f}%)")
    print(f"   - 最終失敗: {final_error_count}")
    print(f"⚡ 效能指標:")
    print(f"   - 總耗時: {total_time:.2f} 秒")
    print(f"   - 平均速度: {total_urls/total_time:.2f} URL/秒")
    print(f"   - 第一輪速度: {total_urls/first_round_time:.2f} URL/秒")
    
    # 成功評估
    final_success_rate = len(final_success_results) / total_urls * 100
    if final_success_rate >= 90:
        print(f"\n🎉 目標達成！NBSP修正解決了觀看數提取問題")
        print(f"💡 關鍵洞察: 問題是 Unicode NBSP (U+00A0) 字符，不是併發或超時")
    elif final_success_rate >= 80:
        print(f"\n✅ 顯著改善！NBSP修正發揮了作用")
    else:
        print(f"\n⚠️ 還有其他問題需要解決")
    
    print("="*80)

if __name__ == "__main__":
    main()