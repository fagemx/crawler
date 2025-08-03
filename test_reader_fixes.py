#!/usr/bin/env python3
import requests
import json
import time
import uuid
import random
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

class ReaderFixesTest:
    def __init__(self):
        self.base_url = "http://localhost:8880"
        self.test_urls = [
            'https://www.threads.com/@ttshow.tw/post/DMfOVeqSkM5',
            'https://www.threads.com/@ttshow.tw/post/DIfkbgLSjO3',
            'https://www.threads.com/@ttshow.tw/post/DL_vyT-RZQ6',
        ]
        self.results = []
        
    def normalize_content(self, content):
        """標準化內容，處理 NBSP 等特殊字符"""
        # 替換不同類型的空白字符
        content = content.replace('\u00a0', ' ')  # NBSP
        content = content.replace('\u2002', ' ')  # En space
        content = content.replace('\u2003', ' ')  # Em space
        content = content.replace('\u3000', ' ')  # Ideographic space
        
        # 標準化行結束符
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        
        # 移除多餘空白
        content = re.sub(r' +', ' ', content)
        
        return content
    
    def extract_views(self, content):
        """提取觀看數，使用增強的正則表達式"""
        # 先標準化內容
        content = self.normalize_content(content)
        
        # 多種觀看數模式
        view_patterns = [
            r'Thread\s*={6}\s*([0-9,\.]+[KMB]?)\s*views?',  # Thread ====== 313K views
            r'Thread\s*={6}\s*([0-9,\.]+[KMB]?)',  # Thread ====== 313K
            r'(\d+(?:\.\d+)?[KMB]?)\s*views?',  # 313K views
            r'views?\s*[:\-]?\s*([0-9,\.]+[KMB]?)',  # views: 313K
            r'觀看數[:\-]?\s*([0-9,\.]+[KMB]?)',  # 觀看數: 313K
        ]
        
        for pattern in view_patterns:
            match = re.search(pattern, content, re.IGNORECASE | re.MULTILINE)
            if match:
                return match.group(1)
        
        return None
    
    def check_content_validity(self, content, original_url):
        """檢查內容是否匹配原始 URL"""
        # 提取原始 post_id
        post_id_match = re.search(r'/post/([A-Za-z0-9_-]+)', original_url)
        if not post_id_match:
            return True, "無法提取 post_id"
        
        original_post_id = post_id_match.group(1)
        
        # 檢查內容是否包含其他 post_id
        other_post_ids = re.findall(r'/post/([A-Za-z0-9_-]+)', content)
        other_unique_ids = set(other_post_ids) - {original_post_id}
        
        if len(other_unique_ids) > 1:
            return False, f"聚合頁面，包含其他 post_id: {list(other_unique_ids)[:3]}"
        
        if 'Related threads' in content:
            return False, "包含 'Related threads'"
        
        return True, "正常單一貼文"

    def make_request_strategy_1(self, url, request_id):
        """策略1：增強 User-Agent + 等待策略"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'x-wait-for-selector': 'article, [data-testid="Thread"]',
            'x-timeout': '20',
            'x-no-cache': 'true'
        }
        
        return self.make_request(url, headers, request_id, "策略1-增強User-Agent")

    def make_request_strategy_2(self, url, request_id):
        """策略2：會話隔離 + 代理"""
        session_id = str(uuid.uuid4())[:8]
        headers = {
            'User-Agent': f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'x-set-cookie': f'session_id={session_id}; thread_prefs=desktop',
            'x-proxy-url': 'auto',
            'x-timeout': '25',
            'x-wait-for-selector': '[data-testid="Thread"], article',
        }
        
        return self.make_request(url, headers, request_id, "策略2-會話隔離")

    def make_request_strategy_3(self, url, request_id):
        """策略3：模擬真實瀏覽器行為"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'x-wait-for-selector': 'main, [role="main"], article',
            'x-timeout': '30'
        }
        
        return self.make_request(url, headers, request_id, "策略3-真實瀏覽器")

    def make_request_baseline(self, url, request_id):
        """基準測試：原始請求"""
        return self.make_request(url, {}, request_id, "基準-原始")

    def make_request(self, url, headers, request_id, strategy_name):
        """執行請求並分析結果"""
        start_time = time.time()
        
        try:
            response = requests.get(f"{self.base_url}/{url}", headers=headers, timeout=60)
            end_time = time.time()
            
            content = response.text
            
            # 檢查內容有效性
            is_valid, validity_reason = self.check_content_validity(content, url)
            
            # 提取觀看數
            views = self.extract_views(content)
            
            # 分析成功與否
            success = is_valid and views is not None
            
            result = {
                'request_id': request_id,
                'strategy': strategy_name,
                'url': url,
                'timestamp': datetime.now().isoformat(),
                'response_time': round(end_time - start_time, 2),
                'status_code': response.status_code,
                'content_length': len(content),
                'is_valid_content': is_valid,
                'validity_reason': validity_reason,
                'views': views,
                'success': success,
                'headers_sent': dict(headers),
                'first_200_chars': content[:200].replace('\n', '\\n'),
            }
            
            print(f"✅ {strategy_name} | {request_id} | {views or '❌'} | {response.status_code} | {end_time - start_time:.1f}s")
            return result
            
        except Exception as e:
            print(f"❌ {strategy_name} | {request_id} | 錯誤: {str(e)}")
            return {
                'request_id': request_id,
                'strategy': strategy_name,
                'url': url,
                'timestamp': datetime.now().isoformat(),
                'error': str(e),
                'success': False,
            }

    def test_all_strategies(self):
        """測試所有策略"""
        print("🚀 開始測試 Reader 修正策略")
        print("=" * 80)
        
        strategies = [
            ('基準測試', self.make_request_baseline),
            ('策略1-增強User-Agent', self.make_request_strategy_1),
            ('策略2-會話隔離', self.make_request_strategy_2),
            ('策略3-真實瀏覽器', self.make_request_strategy_3),
        ]
        
        all_results = []
        
        for strategy_name, strategy_func in strategies:
            print(f"\n📊 測試 {strategy_name}")
            print("-" * 60)
            
            strategy_results = []
            
            for i, url in enumerate(self.test_urls):
                # 隨機延遲避免觸發反爬蟲
                if i > 0:
                    delay = random.uniform(1, 3)
                    time.sleep(delay)
                
                request_id = f"{strategy_name}-{i+1}"
                result = strategy_func(url, request_id)
                strategy_results.append(result)
                all_results.append(result)
            
            # 統計該策略結果
            success_count = sum(1 for r in strategy_results if r.get('success', False))
            total_count = len(strategy_results)
            success_rate = success_count / total_count * 100
            
            print(f"   📈 {strategy_name} 成功率: {success_count}/{total_count} ({success_rate:.1f}%)")
            
            # 策略間休息
            time.sleep(2)
        
        # 保存結果
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"reader_fixes_test_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump({
                'test_name': 'Reader修正策略測試',
                'timestamp': datetime.now().isoformat(),
                'strategies_tested': len(strategies),
                'urls_per_strategy': len(self.test_urls),
                'total_requests': len(all_results),
                'results': all_results
            }, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 結果已保存: {filename}")
        
        # 分析總體結果
        self.analyze_results(all_results, strategies)

    def analyze_results(self, all_results, strategies):
        """分析測試結果"""
        print("\n" + "=" * 80)
        print("📊 總體結果分析")
        print("=" * 80)
        
        strategy_names = [name for name, _ in strategies]
        
        for strategy_name in strategy_names:
            strategy_results = [r for r in all_results if r.get('strategy', '').startswith(strategy_name)]
            
            if not strategy_results:
                continue
            
            success_count = sum(1 for r in strategy_results if r.get('success', False))
            total_count = len(strategy_results)
            success_rate = success_count / total_count * 100
            
            # 計算平均響應時間
            response_times = [r.get('response_time', 0) for r in strategy_results if 'response_time' in r]
            avg_response_time = sum(response_times) / len(response_times) if response_times else 0
            
            # 檢查內容有效性
            valid_content_count = sum(1 for r in strategy_results if r.get('is_valid_content', False))
            valid_content_rate = valid_content_count / total_count * 100
            
            print(f"\n🎯 {strategy_name}:")
            print(f"   ✅ 成功率: {success_count}/{total_count} ({success_rate:.1f}%)")
            print(f"   📄 內容有效率: {valid_content_count}/{total_count} ({valid_content_rate:.1f}%)")
            print(f"   ⏱️ 平均響應時間: {avg_response_time:.1f}s")
            
            # 顯示失敗原因
            failed_results = [r for r in strategy_results if not r.get('success', False)]
            if failed_results:
                reasons = {}
                for r in failed_results:
                    reason = r.get('validity_reason', r.get('error', '未知錯誤'))
                    reasons[reason] = reasons.get(reason, 0) + 1
                
                print(f"   ❌ 失敗原因:")
                for reason, count in reasons.items():
                    print(f"      - {reason}: {count} 次")

    def test_parallel_vs_serial(self):
        """測試並行 vs 串行的差異"""
        print("\n🧪 並行 vs 串行比較測試")
        print("=" * 80)
        
        # 串行測試
        print("\n📊 串行測試 (策略1)")
        serial_results = []
        for i, url in enumerate(self.test_urls):
            if i > 0:
                time.sleep(1)  # 短延遲
            result = self.make_request_strategy_1(url, f"serial-{i}")
            serial_results.append(result)
        
        # 並行測試
        print("\n📊 並行測試 (策略1)")
        parallel_results = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = []
            for i, url in enumerate(self.test_urls):
                future = executor.submit(self.make_request_strategy_1, url, f"parallel-{i}")
                futures.append(future)
            
            for future in as_completed(futures):
                result = future.result()
                parallel_results.append(result)
        
        # 比較結果
        serial_success = sum(1 for r in serial_results if r.get('success', False))
        parallel_success = sum(1 for r in parallel_results if r.get('success', False))
        
        print(f"\n🎯 比較結果:")
        print(f"   📈 串行成功率: {serial_success}/{len(serial_results)} ({serial_success/len(serial_results)*100:.1f}%)")
        print(f"   📈 並行成功率: {parallel_success}/{len(parallel_results)} ({parallel_success/len(parallel_results)*100:.1f}%)")

if __name__ == '__main__':
    tester = ReaderFixesTest()
    tester.test_all_strategies()
    tester.test_parallel_vs_serial()