#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多線程Reader壓力測試與解析腳本 (V12 - 完全優化版)
實施所有性能和穩定性優化措施
"""

import json
import re
import requests
import time
import itertools
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Optional, List

# --- 預先編譯 Regex 模式 ---
VIEW_PATTERNS = [
    re.compile(r'\[Thread\s*={2,}\s*(\d+(?:\.\d+)?[KMB]?)\s*views\]', re.IGNORECASE),
    re.compile(r'Thread.*?(\d+(?:\.\d+)?[KMB]?)\s*views', re.IGNORECASE),
    re.compile(r'(\d+(?:\.\d+)?[KMB]?)\s*views', re.IGNORECASE)
]

ENGAGEMENT_PATTERN = re.compile(r'^\d+(?:\.\d+)?[KMB]?$')

class OptimizedThreadsReaderParser:
    """
    Threads貼文Reader解析器 - 完全優化版
    """
    
    def __init__(self, strategy: str = "lb", backend_instances: int = 2):
        self.strategy = strategy
        self.backend_instances = backend_instances
        self.official_reader_url = "https://r.jina.ai"
        
        # 根據策略配置端點
        if strategy == "lb":
            self.endpoints = ["http://localhost:8880"]
            self.endpoint_cycle = itertools.cycle(self.endpoints)
        elif strategy == "direct":
            # 直接連接兩個Reader實例（繞過LB）
            self.endpoints = ["http://localhost:18080", "http://localhost:18081"]
            self.endpoint_cycle = itertools.cycle(self.endpoints)
        
        # --- 優化的Session配置 ---
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=20,
            pool_maxsize=30,
            max_retries=0
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        
        print(f"🔧 初始化完成：{strategy.upper()} 策略")
        print(f"   端點: {self.endpoints}")
        print(f"   後端實例: {backend_instances} 個")
        print(f"   理論併發: {len(self.endpoints) * 3}")

    def convert_url_to_threads_net(self, url: str) -> str:
        """將 threads.com URL 轉換為 threads.net"""
        return url.replace("threads.com", "threads.net")

    def fetch_content_local(self, post_url: str, use_cache: bool = True, timeout: int = 60) -> str:
        """從本地Reader服務獲取內容（支援Round-Robin）"""
        # 修正URL域名
        corrected_url = self.convert_url_to_threads_net(post_url)
        
        # Round-Robin選擇端點
        endpoint = next(self.endpoint_cycle)
        reader_url = f"{endpoint}/{corrected_url}"
        
        # 智能快取策略
        headers = {}
        if not use_cache:
            headers['x-no-cache'] = 'true'
        
        try:
            response = self.session.get(reader_url, headers=headers, timeout=(10, timeout))
            response.raise_for_status()
            return response.text
        except requests.exceptions.Timeout:
            print(f"⏰ 超時({timeout}s): {post_url.split('/')[-1]}")
            return ""
        except requests.exceptions.RequestException as e:
            print(f"❌ 請求失敗: {post_url.split('/')[-1]} - {e}")
            return ""

    def fetch_content_official(self, post_url: str) -> str:
        """從官方 Jina Reader 服務獲取內容"""
        # 修正URL域名
        corrected_url = self.convert_url_to_threads_net(post_url)
        jina_url = f"{self.official_reader_url}/{corrected_url}"
        headers = {"X-Return-Format": "markdown"}
        try:
            response = self.session.get(jina_url, headers=headers, timeout=(10, 120))
            response.raise_for_status()
            return response.text
        except Exception as e:
            print(f"  - 官方API失敗: {post_url.split('/')[-1]} - {e}")
            return ""

    def extract_post_content(self, markdown_content: str) -> Optional[str]:
        """提取貼文內容"""
        lines = markdown_content.split('\n')
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

    def extract_views_count(self, markdown_content: str) -> Optional[str]:
        """提取觀看數"""
        for pattern in VIEW_PATTERNS:
            match = pattern.search(markdown_content)
            if match:
                return f"{match.group(1)} views"
        return None

    def extract_engagement_numbers(self, markdown_content: str) -> Dict[str, str]:
        """提取互動數據序列"""
        lines = markdown_content.split('\n')
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            if (stripped.startswith('![Image') and 
                'profile picture' not in stripped and 
                i > 0 and any('Translate' in lines[k] for k in range(max(0, i-3), i+1))):
                
                numbers = []
                for j in range(i + 1, min(i + 15, len(lines))):
                    candidate = lines[j].strip()
                    if ENGAGEMENT_PATTERN.match(candidate):
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

    def parse_post_local(self, post_url: str, use_cache: bool = True, timeout: int = 60) -> Dict:
        """使用本地服務解析"""
        content = self.fetch_content_local(post_url, use_cache, timeout)
        if not content:
            return {"url": post_url, "error": "無法獲取內容"}
        
        engagement = self.extract_engagement_numbers(content)
        
        return {
            "url": post_url,
            "content": self.extract_post_content(content),
            "views": self.extract_views_count(content),
            "likes": engagement.get('likes'),
            "comments": engagement.get('comments'),
            "reposts": engagement.get('reposts'),
            "shares": engagement.get('shares'),
            "raw_length": len(content)
        }

    def parse_post_official(self, post_url: str) -> Dict:
        """使用官方服務解析"""
        content = self.fetch_content_official(post_url)
        if not content:
            return {"url": post_url, "error": "無法從官方API獲取內容"}
        
        engagement = self.extract_engagement_numbers(content)
        
        return {
            "url": post_url,
            "content": self.extract_post_content(content),
            "views": self.extract_views_count(content),
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

def detect_reader_configuration():
    """檢測Reader配置 - 改進版"""
    print("🔍 檢測Reader配置...")
    
    # 檢測 Docker 容器
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
            has_lb = any('lb' in name for name in containers)
            
            print(f"   ✅ 檢測到容器: {containers}")
            print(f"   🎯 Reader實例: {reader_containers}")
            print(f"   📊 LB狀態: {'有' if has_lb else '無'}")
            
            # 決定策略
            if has_lb and len(reader_containers) >= 2:
                print(f"   🚀 使用負載均衡器策略")
                return "lb", len(reader_containers)
            elif len(reader_containers) >= 2:
                print(f"   🎯 使用直連策略")
                return "direct", len(reader_containers)
            else:
                print(f"   ⚠️ 單實例配置")
                return "lb", 1
        else:
            return "lb", 2
    except Exception as e:
        print(f"   ⚠️ 檢測失敗: {e}")
        return "lb", 2

def warm_up_readers(parser: OptimizedThreadsReaderParser):
    """暖身Reader實例"""
    print("🔥 暖身Reader實例...")
    warm_up_url = "https://www.threads.net/@meta/post/C8V8bUvMQDj"  # Meta官方貼文，相對穩定
    
    for i, endpoint in enumerate(parser.endpoints):
        try:
            # 直接對每個端點發送暖身請求
            response = requests.get(f"{endpoint}/{warm_up_url}", timeout=30)
            if response.status_code == 200:
                print(f"   ✅ Reader {i+1} 暖身成功")
            else:
                print(f"   ⚠️ Reader {i+1} 暖身回應: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Reader {i+1} 暖身失敗: {e}")

def batch_process_urls(parser: OptimizedThreadsReaderParser, urls: List[str], 
                      batch_size: int, max_workers: int) -> Dict[str, Dict]:
    """分批處理URL（避免慢請求拖累整體）"""
    results = {}
    total_batches = (len(urls) + batch_size - 1) // batch_size
    
    for batch_idx in range(total_batches):
        start_idx = batch_idx * batch_size
        end_idx = min(start_idx + batch_size, len(urls))
        batch_urls = urls[start_idx:end_idx]
        
        print(f"📦 處理批次 {batch_idx + 1}/{total_batches} ({len(batch_urls)} URLs)")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {
                executor.submit(parser.parse_post_local, url, True, 45): url 
                for url in batch_urls
            }
            
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    results[url] = future.result()
                except Exception:
                    results[url] = {"url": url, "error": "執行緒異常"}
    
    return results

def main():
    """主函數：完全優化版"""
    json_file_path = 'agents/playwright_crawler/debug/crawl_data_20250803_121452_934d52b1.json'
    
    # --- 檢測配置 ---
    strategy, backend_instances = detect_reader_configuration()
    
    # --- 動態調整併發（保守策略）---
    max_workers = backend_instances * 2  # 減少併發壓力
    batch_size = max_workers  # 批次大小等於併發數
    
    urls_to_process = load_urls_from_file(json_file_path)
    if not urls_to_process:
        return

    total_urls = len(urls_to_process)
    parser = OptimizedThreadsReaderParser(strategy, backend_instances)
    
    # 暖身
    warm_up_readers(parser)
    
    start_time = time.time()
    print(f"\n🚀 完全優化版啟動！")
    print(f"📊 配置: {strategy.upper()}策略, {backend_instances}個實例, 併發數: {max_workers}")
    print("🎯 優化項目: ✅URL修正 ✅批次處理 ✅智能暖身 ✅保守併發 ✅快速超時")

    # --- 第一層: 分批並行處理 ---
    print(f"\n⚡ (1/3) 分批並行處理 {total_urls} 個 URL...")
    results = batch_process_urls(parser, urls_to_process, batch_size, max_workers)

    # 第一輪統計
    first_round_success = sum(1 for res in results.values() if not res.get("error") and res.get("views") and res.get("content"))
    first_round_time = time.time() - start_time
    
    print(f"\n🎯 第一輪結果: {first_round_success}/{total_urls} 成功 ({first_round_success/total_urls*100:.1f}%)")
    print(f"📊 第一輪效能: {first_round_time:.1f}s, 速度: {total_urls/first_round_time:.2f} URL/秒")
    
    # --- 第二層: 單線程重試（無快取，較長超時）---
    print(f"\n🔄 (2/3) 單線程重試失敗項目...")
    local_retries_attempted = 0
    urls_to_retry_local = [url for url, res in results.items() if res.get("error") or not res.get("views") or not res.get("content")]
    
    if urls_to_retry_local:
        print(f"📝 需要重試: {len(urls_to_retry_local)} 個項目 (單線程+無快取+75s超時)")
        for url in urls_to_retry_local:
            local_retries_attempted += 1
            print(f"  - 重試 {local_retries_attempted}: {url.split('/')[-1]}")
            results[url] = parser.parse_post_local(url, use_cache=False, timeout=75)
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
            print(f"  - 官方API {official_retries_attempted}: {url.split('/')[-1]}")
            results[url] = parser.parse_post_official(url)
    else:
        print("✅ 本地重試後數據已完整。")

    end_time = time.time()
    total_time = end_time - start_time

    # --- 最終統計與保存 ---
    final_success_results = [res for res in results.values() if not res.get("error") and res.get("views") and res.get("content")]
    final_error_count = total_urls - len(final_success_results)

    if final_success_results:
        output_filename = 'parallel_reader_results_optimized.json'
        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(final_success_results, f, ensure_ascii=False, indent=2)
        print(f"\n💾 {len(final_success_results)} 筆完整結果已保存到: {output_filename}")

    print("\n" + "="*80)
    print("🏆 完全優化版執行完畢！")
    print(f"📊 處理統計:")
    print(f"   - 策略: {strategy.upper()}")
    print(f"   - 端點: {parser.endpoints}")
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
    
    # 智能建議
    if first_round_success/total_urls >= 0.9:
        print(f"\n🎉 優化成功！配置完美適配")
    elif first_round_success/total_urls >= 0.7:
        print(f"\n✅ 效果良好，成功率明顯改善")
        print(f"💡 建議: 可嘗試微調併發數或檢查慢URL模式")
    else:
        print(f"\n⚠️ 仍需優化:")
        print(f"   - 檢查Docker資源分配（CPU/RAM/SHM）")
        print(f"   - 驗證Nginx配置是否生效")
        print(f"   - 考慮調整batch_size或進一步降低併發")
    
    print("="*80)

if __name__ == "__main__":
    main()