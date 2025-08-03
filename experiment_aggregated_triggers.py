#!/usr/bin/env python3
import requests
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import re

class AggregatedPageExperiment:
    def __init__(self):
        self.base_url = "http://localhost:8880"
        self.test_urls = [
            'https://www.threads.com/@ttshow.tw/post/DMfOVeqSkM5',  # 之前出現聚合頁面的
            'https://www.threads.com/@ttshow.tw/post/DIfkbgLSjO3',  # 之前成功的
            'https://www.threads.com/@ttshow.tw/post/DL_vyT-RZQ6',  # 之前出現聚合頁面的
        ]
        self.results = []
        
    def make_request(self, url, request_id=None, delay=0):
        """執行單次請求並記錄結果"""
        if delay > 0:
            time.sleep(delay)
            
        start_time = time.time()
        try:
            response = requests.get(f"{self.base_url}/{url}", timeout=30)
            end_time = time.time()
            
            content = response.text
            
            # 檢查是否為聚合頁面的指標
            is_aggregated = self.check_if_aggregated(content, url)
            
            result = {
                'request_id': request_id,
                'url': url,
                'timestamp': datetime.now().isoformat(),
                'response_time': round(end_time - start_time, 2),
                'status_code': response.status_code,
                'content_length': len(content),
                'is_aggregated': is_aggregated,
                'has_related_threads': 'Related threads' in content,
                'other_post_ids': self.find_other_post_ids(content, url),
                'view_count': self.extract_view_count(content),
                'first_100_chars': content[:100].replace('\n', '\\n'),
            }
            
            return result
            
        except Exception as e:
            return {
                'request_id': request_id,
                'url': url,
                'timestamp': datetime.now().isoformat(),
                'error': str(e),
                'is_aggregated': None,
            }
    
    def check_if_aggregated(self, content, original_url):
        """檢查內容是否為聚合頁面"""
        # 從原始 URL 提取 post_id
        post_id_match = re.search(r'/post/([A-Za-z0-9_-]+)', original_url)
        if not post_id_match:
            return False
        
        original_post_id = post_id_match.group(1)
        
        # 檢查內容中是否包含其他 post_id
        other_post_ids = re.findall(r'/post/([A-Za-z0-9_-]+)', content)
        other_unique_ids = set(other_post_ids) - {original_post_id}
        
        # 如果包含超過 1 個其他 post_id，很可能是聚合頁面
        return len(other_unique_ids) > 1
    
    def find_other_post_ids(self, content, original_url):
        """找出內容中的其他 post_id"""
        post_id_match = re.search(r'/post/([A-Za-z0-9_-]+)', original_url)
        if not post_id_match:
            return []
        
        original_post_id = post_id_match.group(1)
        other_post_ids = re.findall(r'/post/([A-Za-z0-9_-]+)', content)
        other_unique_ids = list(set(other_post_ids) - {original_post_id})
        
        return other_unique_ids[:5]  # 只返回前5個
    
    def extract_view_count(self, content):
        """提取觀看數"""
        view_patterns = [
            r'Thread\s*={6}\s*([0-9,\.]+[KMB]?)\s*views?',
            r'(\d+(?:\.\d+)?[KMB]?)\s*views?',
        ]
        
        for pattern in view_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def experiment_1_concurrency_levels(self):
        """實驗1：測試不同併發級別"""
        print("🧪 實驗1：併發級別對聚合頁面的影響")
        print("=" * 60)
        
        concurrency_levels = [1, 2, 4, 6, 8, 10]
        
        for concurrency in concurrency_levels:
            print(f"\n📊 測試併發數: {concurrency}")
            
            # 準備相同的 URL 列表
            test_urls = self.test_urls * 3  # 每個 URL 測試3次
            
            start_time = time.time()
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = []
                for i, url in enumerate(test_urls):
                    future = executor.submit(self.make_request, url, f"{concurrency}-{i}")
                    futures.append(future)
                
                results = []
                for future in as_completed(futures):
                    result = future.result()
                    results.append(result)
            
            end_time = time.time()
            
            # 統計結果
            aggregated_count = sum(1 for r in results if r.get('is_aggregated', False))
            success_count = sum(1 for r in results if r.get('view_count') is not None)
            
            print(f"   ⏱️  總耗時: {end_time - start_time:.2f}s")
            print(f"   📊 總請求: {len(results)}")
            print(f"   ❌ 聚合頁面: {aggregated_count} ({aggregated_count/len(results)*100:.1f}%)")
            print(f"   ✅ 成功提取觀看數: {success_count} ({success_count/len(results)*100:.1f}%)")
            
            # 保存詳細結果
            self.save_experiment_results(f"concurrency_{concurrency}", results)
            
            # 等待一下避免影響下一輪測試
            time.sleep(2)

    def experiment_2_request_intervals(self):
        """實驗2：測試請求間隔"""
        print("\n🧪 實驗2：請求間隔對聚合頁面的影響")
        print("=" * 60)
        
        intervals = [0, 0.5, 1.0, 2.0, 5.0]
        
        for interval in intervals:
            print(f"\n📊 測試間隔: {interval}秒")
            
            results = []
            start_time = time.time()
            
            # 串行請求，但有間隔
            for i, url in enumerate(self.test_urls * 3):
                if i > 0:  # 第一個請求不延遲
                    time.sleep(interval)
                
                result = self.make_request(url, f"interval-{interval}-{i}")
                results.append(result)
            
            end_time = time.time()
            
            # 統計結果
            aggregated_count = sum(1 for r in results if r.get('is_aggregated', False))
            success_count = sum(1 for r in results if r.get('view_count') is not None)
            
            print(f"   ⏱️  總耗時: {end_time - start_time:.2f}s")
            print(f"   ❌ 聚合頁面: {aggregated_count} ({aggregated_count/len(results)*100:.1f}%)")
            print(f"   ✅ 成功提取觀看數: {success_count} ({success_count/len(results)*100:.1f}%)")
            
            self.save_experiment_results(f"interval_{interval}", results)

    def experiment_3_rapid_same_url(self):
        """實驗3：快速重複請求同一 URL"""
        print("\n🧪 實驗3：快速重複請求同一 URL")
        print("=" * 60)
        
        test_url = self.test_urls[0]  # 使用第一個 URL
        
        # 快速連續請求同一 URL 10 次
        results = []
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for i in range(10):
                future = executor.submit(self.make_request, test_url, f"rapid-{i}")
                futures.append(future)
            
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
        
        end_time = time.time()
        
        # 統計結果
        aggregated_count = sum(1 for r in results if r.get('is_aggregated', False))
        success_count = sum(1 for r in results if r.get('view_count') is not None)
        
        print(f"   ⏱️  總耗時: {end_time - start_time:.2f}s")
        print(f"   ❌ 聚合頁面: {aggregated_count} ({aggregated_count/len(results)*100:.1f}%)")
        print(f"   ✅ 成功提取觀看數: {success_count} ({success_count/len(results)*100:.1f}%)")
        
        self.save_experiment_results("rapid_same_url", results)

    def experiment_4_cache_headers(self):
        """實驗4：測試緩存頭的影響"""
        print("\n🧪 實驗4：緩存頭對聚合頁面的影響")
        print("=" * 60)
        
        cache_strategies = [
            {"name": "默認", "headers": {}},
            {"name": "無緩存", "headers": {"x-no-cache": "true"}},
            {"name": "強制刷新", "headers": {"Cache-Control": "no-cache, no-store, must-revalidate"}},
        ]
        
        for strategy in cache_strategies:
            print(f"\n📊 測試策略: {strategy['name']}")
            
            results = []
            
            # 併發請求測試緩存策略
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = []
                for i, url in enumerate(self.test_urls * 2):
                    future = executor.submit(self.make_request_with_headers, url, strategy['headers'], f"cache-{strategy['name']}-{i}")
                    futures.append(future)
                
                for future in as_completed(futures):
                    result = future.result()
                    results.append(result)
            
            # 統計結果
            aggregated_count = sum(1 for r in results if r.get('is_aggregated', False))
            success_count = sum(1 for r in results if r.get('view_count') is not None)
            
            print(f"   ❌ 聚合頁面: {aggregated_count} ({aggregated_count/len(results)*100:.1f}%)")
            print(f"   ✅ 成功提取觀看數: {success_count} ({success_count/len(results)*100:.1f}%)")
            
            self.save_experiment_results(f"cache_{strategy['name']}", results)

    def make_request_with_headers(self, url, headers, request_id):
        """帶自定義頭的請求"""
        try:
            response = requests.get(f"{self.base_url}/{url}", headers=headers, timeout=30)
            content = response.text
            
            is_aggregated = self.check_if_aggregated(content, url)
            
            return {
                'request_id': request_id,
                'url': url,
                'timestamp': datetime.now().isoformat(),
                'is_aggregated': is_aggregated,
                'view_count': self.extract_view_count(content),
                'headers_used': headers,
            }
        except Exception as e:
            return {
                'request_id': request_id,
                'url': url,
                'error': str(e),
                'headers_used': headers,
            }

    def save_experiment_results(self, experiment_name, results):
        """保存實驗結果"""
        filename = f"experiment_{experiment_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump({
                'experiment': experiment_name,
                'timestamp': datetime.now().isoformat(),
                'results': results
            }, f, ensure_ascii=False, indent=2)
        
        print(f"   💾 結果已保存: {filename}")

    def run_all_experiments(self):
        """運行所有實驗"""
        print("🚀 開始聚合頁面觸發條件實驗")
        print("=" * 60)
        
        self.experiment_1_concurrency_levels()
        time.sleep(5)  # 實驗間休息
        
        self.experiment_2_request_intervals()
        time.sleep(5)
        
        self.experiment_3_rapid_same_url()
        time.sleep(5)
        
        self.experiment_4_cache_headers()
        
        print("\n🎯 所有實驗完成！")
        print("請檢查生成的 experiment_*.json 文件查看詳細結果")

if __name__ == '__main__':
    experiment = AggregatedPageExperiment()
    experiment.run_all_experiments()