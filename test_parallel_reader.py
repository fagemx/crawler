#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多線程Reader壓力測試與解析腳本 (V11 - 檢測邏輯修正版)
修正負載均衡器後端實例檢測邏輯
"""

import json
import re
import requests
import time
import itertools
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Optional, List

# --- 預先編譯 Regex 模式 ---
VIEW_PATTERNS = [
    re.compile(r'\[Thread\s*={2,}\s*(\d+(?:\.\d+)?[KMB]?)\s*views\]', re.IGNORECASE),
    re.compile(r'Thread.*?(\d+(?:\.\d+)?[KMB]?)\s*views', re.IGNORECASE),
    re.compile(r'(\d+(?:\.\d+)?[KMB]?)\s*views', re.IGNORECASE)
]

ENGAGEMENT_PATTERN = re.compile(r'^\d+(?:\.\d+)?[KMB]?$')

class ThreadsReaderParser:
    """
    Threads貼文Reader解析器 - 負載均衡器優化版
    """
    
    def __init__(self, reader_base_url: str = "http://localhost:8880", backend_instances: int = 2):
        self.reader_base_url = reader_base_url
        self.backend_instances = backend_instances
        self.official_reader_url = "https://r.jina.ai"
        
        # --- 優化的Session配置 ---
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=20,
            pool_maxsize=30,
            max_retries=0
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        
        print(f"🔧 初始化完成：負載均衡器架構")
        print(f"   LB端點: {reader_base_url}")
        print(f"   後端Reader實例: {backend_instances} 個")
        print(f"   理論併發能力: {backend_instances * 3} (每實例3併發)")

    def fetch_content_local(self, post_url: str, use_cache: bool = True) -> str:
        """從負載均衡器獲取內容"""
        reader_url = f"{self.reader_base_url}/{post_url}"
        
        # 智能快取策略
        headers = {}
        if not use_cache:
            headers['x-no-cache'] = 'true'
        
        try:
            response = self.session.get(reader_url, headers=headers, timeout=90)
            response.raise_for_status()
            return response.text
        except requests.exceptions.Timeout:
            print(f"⏰ 超時(90s): {post_url.split('/')[-1]}")
            return ""
        except requests.exceptions.RequestException as e:
            print(f"❌ 請求失敗: {post_url.split('/')[-1]} - {e}")
            return ""

    def fetch_content_official(self, post_url: str) -> str:
        """從官方 Jina Reader 服務獲取內容"""
        jina_url = f"{self.official_reader_url}/{post_url}"
        headers = {"X-Return-Format": "markdown"}
        try:
            response = self.session.get(jina_url, headers=headers, timeout=120)
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

    def parse_post_local(self, post_url: str, use_cache: bool = True) -> Dict:
        """使用本地服務解析"""
        content = self.fetch_content_local(post_url, use_cache)
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

def detect_lb_configuration():
    """檢測負載均衡器配置 - 改進版"""
    lb_url = "http://localhost:8880"
    
    print("🔍 檢測負載均衡器配置...")
    
    # 檢測 Docker 容器來確定後端實例數
    try:
        import subprocess
        result = subprocess.run([
            'docker', 'ps', 
            '--filter', 'name=reader', 
            '--filter', 'status=running',
            '--format', '{{.Names}}'
        ], capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            containers = result.stdout.strip().split('\n')
            reader_containers = [name for name in containers if 'reader-' in name and 'lb' not in name and name.strip()]
            backend_count = len(reader_containers)
            
            print(f"   ✅ 檢測到 Docker 容器: {containers}")
            print(f"   🎯 後端Reader實例: {reader_containers}")
            print(f"   📊 實例數量: {backend_count}")
            
            if backend_count >= 2:
                print(f"   🚀 多實例配置！可使用高併發")
                return lb_url, backend_count
            elif backend_count == 1:
                print(f"   ⚠️ 只有 1 個Reader實例，使用保守併發")
                return lb_url, 1
            else:
                print(f"   ❌ 沒有檢測到Reader實例，使用預設配置")
                return lb_url, 1
        else:
            print(f"   ⚠️ Docker 檢測失敗，使用預設配置")
            return lb_url, 2
    except Exception as e:
        print(f"   ⚠️ 容器檢測出錯: {e}，假設有2個實例")
        return lb_url, 2

def main():
    """主函數：負載均衡器優化版"""
    json_file_path = 'agents/playwright_crawler/debug/crawl_data_20250803_121452_934d52b1.json'
    
    # --- 檢測負載均衡器配置 ---
    lb_url, backend_instances = detect_lb_configuration()
    
    # --- 動態調整併發數 ---
    max_workers = backend_instances * 3
    
    urls_to_process = load_urls_from_file(json_file_path)
    if not urls_to_process:
        return

    total_urls = len(urls_to_process)
    parser = ThreadsReaderParser(lb_url, backend_instances)
    results = {}
    
    start_time = time.time()
    print(f"\n🚀 負載均衡器優化版啟動！")
    print(f"📊 配置: 1個LB + {backend_instances}個後端實例, 總併發數: {max_workers}")
    print("🎯 優化項目: ✅Docker容器檢測 ✅智能併發 ✅快取策略 ✅timeout=90s")

    # --- 第一層: 透過負載均衡器的平行處理 ---
    print(f"\n⚡ (1/3) 第一輪透過LB平行處理 {total_urls} 個 URL...")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(parser.parse_post_local, url, True): url for url in urls_to_process}
        
        completed = 0
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            completed += 1
            progress = completed / total_urls
            bar_length = 40
            filled_length = int(bar_length * progress)
            bar = '█' * filled_length + '-' * (bar_length - filled_length)
            print(f'\r進度: |{bar}| {completed}/{total_urls} ({progress:.1%})', end='', flush=True)
            try:
                results[url] = future.result()
            except Exception:
                results[url] = {"url": url, "error": "執行緒異常"}

    # 第一輪統計
    first_round_success = sum(1 for res in results.values() if not res.get("error") and res.get("views") and res.get("content"))
    first_round_time = time.time() - start_time
    
    print(f"\n🎯 第一輪結果: {first_round_success}/{total_urls} 成功 ({first_round_success/total_urls*100:.1f}%)")
    print(f"📊 第一輪效能: {first_round_time:.1f}s, 速度: {total_urls/first_round_time:.2f} URL/秒")
    
    # 效能評估
    if first_round_success/total_urls >= 0.9:
        print("🎉 優秀！負載均衡器配置效果顯著")
    elif first_round_success/total_urls >= 0.7:
        print("✅ 良好！成功率明顯改善")
    else:
        print("⚠️ 成功率仍需優化，可能需要調整併發數")

    # --- 第二層: 無快取重試 ---
    print(f"\n🔄 (2/3) 無快取重試失敗項目...")
    local_retries_attempted = 0
    urls_to_retry_local = [url for url, res in results.items() if res.get("error") or not res.get("views") or not res.get("content")]
    
    if urls_to_retry_local:
        print(f"📝 需要重試: {len(urls_to_retry_local)} 個項目 (跳過快取)")
        for url in urls_to_retry_local:
            local_retries_attempted += 1
            print(f"  - 重試 {local_retries_attempted}: {url.split('/')[-1]} (no-cache)")
            results[url] = parser.parse_post_local(url, use_cache=False)
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
        output_filename = 'parallel_reader_results.json'
        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(final_success_results, f, ensure_ascii=False, indent=2)
        print(f"\n💾 {len(final_success_results)} 筆完整結果已保存到: {output_filename}")

    print("\n" + "="*70)
    print("🏆 負載均衡器優化版執行完畢！")
    print(f"📊 處理統計:")
    print(f"   - 負載均衡器: {lb_url}")
    print(f"   - 後端Reader實例: {backend_instances} 個")
    print(f"   - 總併發數: {max_workers}")
    print(f"   - 總URL數量: {total_urls}")
    print(f"   - 第一輪成功率: {first_round_success/total_urls*100:.1f}% ({first_round_success}/{total_urls})")
    print(f"   - 無快取重試: {local_retries_attempted} 次")
    print(f"   - 官方API重試: {official_retries_attempted} 次")
    print(f"   - 最終成功: {len(final_success_results)} ({len(final_success_results)/total_urls*100:.1f}%)")
    print(f"   - 最終失敗: {final_error_count}")
    print(f"⚡ 效能指標:")
    print(f"   - 總耗時: {total_time:.2f} 秒")
    print(f"   - 平均速度: {total_urls/total_time:.2f} URL/秒")
    print(f"   - 第一輪速度: {total_urls/first_round_time:.2f} URL/秒")
    
    # 智能建議系統
    if backend_instances >= 2 and first_round_success/total_urls >= 0.9:
        print(f"\n🎉 配置完美！負載均衡器 + {backend_instances}個Reader實例發揮了最佳效果")
        print(f"   - 併發數 {max_workers} 完全發揮了硬體優勢")
    elif backend_instances >= 2:
        print(f"\n💡 雙Reader配置良好，但仍有優化空間:")
        print(f"   - 當前併發: {max_workers} (每實例 {max_workers//backend_instances})")
        print(f"   - 建議檢查Docker資源分配或考慮微調併發數")
    else:
        print(f"\n💡 建議: 目前只有{backend_instances}個後端實例")
        print(f"   - 確認 social-media-reader-1 和 social-media-reader-2 都在運行")
        print(f"   - 當前併發受限於單實例能力")
    
    print("="*70)

if __name__ == "__main__":
    main()