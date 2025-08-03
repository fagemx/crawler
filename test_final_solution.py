#!/usr/bin/env python3
"""
最終解決方案測試 - 使用已驗證有效的 headers
"""
import requests
import json
import time
import re
import random
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

class FinalReaderSolution:
    def __init__(self):
        self.base_url = "http://localhost:8880"
        
        # 已驗證有效的 headers 配置
        self.optimal_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'x-wait-for-selector': 'article',
            'x-timeout': '25'
        }
        
    def normalize_content(self, content):
        """標準化內容處理 NBSP"""
        content = content.replace('\u00a0', ' ')  # NBSP
        content = content.replace('\u2002', ' ')  # En space
        content = content.replace('\u2003', ' ')  # Em space
        content = re.sub(r' +', ' ', content)
        return content
    
    def extract_views(self, content):
        """提取觀看數 - 使用增強的正則表達式"""
        content = self.normalize_content(content)
        
        patterns = [
            r'Thread\s*={6}\s*([0-9,\.]+[KMB]?)\s*views?',  # Thread ====== 313K views
            r'Thread\s*={6}\s*([0-9,\.]+[KMB]?)',           # Thread ====== 313K
            r'(\d+(?:\.\d+)?[KMB]?)\s*views?',              # 313K views
        ]
        
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(1)
        return None
    
    def extract_content(self, content):
        """提取主要內容"""
        lines = content.split('\n')
        
        # 尋找內容開始位置
        content_start = -1
        for i, line in enumerate(lines):
            if 'Markdown Content:' in line:
                content_start = i + 1
                break
        
        if content_start == -1:
            return None
        
        # 提取內容直到遇到其他結構
        content_lines = []
        for i in range(content_start, len(lines)):
            line = lines[i].strip()
            if line and not line.startswith('[![Image') and not line.startswith('[Image'):
                content_lines.append(line)
                if len(content_lines) >= 10:  # 取前幾行作為主要內容
                    break
        
        return '\n'.join(content_lines) if content_lines else None
    
    def fetch_post_data(self, url, request_id=None):
        """使用最佳化配置獲取貼文數據"""
        try:
            response = requests.get(
                f"{self.base_url}/{url}", 
                headers=self.optimal_headers, 
                timeout=60
            )
            
            if response.status_code != 200:
                return {
                    'success': False,
                    'error': f"HTTP {response.status_code}",
                    'url': url,
                    'request_id': request_id
                }
            
            content = response.text
            
            # 提取觀看數和內容
            views = self.extract_views(content)
            main_content = self.extract_content(content)
            
            return {
                'success': True,
                'url': url,
                'request_id': request_id,
                'views': views,
                'content': main_content,
                'content_length': len(content),
                'has_views': views is not None,
                'has_content': main_content is not None,
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'url': url,
                'request_id': request_id
            }
    
    def test_single_url(self, url):
        """測試單個 URL"""
        print(f"🔍 測試: {url.split('/')[-1]}")
        
        result = self.fetch_post_data(url, "single-test")
        
        if result['success']:
            print(f"✅ 成功!")
            print(f"   觀看數: {result['views'] or '❌ 未找到'}")
            print(f"   內容: {result['content'][:100] + '...' if result['content'] else '❌ 未找到'}")
            print(f"   內容長度: {result['content_length']:,} 字符")
        else:
            print(f"❌ 失敗: {result['error']}")
        
        return result
    
    def test_parallel_processing(self, urls, max_workers=3):
        """測試並行處理"""
        print(f"\n🚀 並行處理測試 (併發數: {max_workers})")
        print("=" * 60)
        
        results = []
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任務
            futures = []
            for i, url in enumerate(urls):
                future = executor.submit(self.fetch_post_data, url, f"parallel-{i+1}")
                futures.append(future)
            
            # 收集結果
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                
                # 顯示進度
                completed = len(results)
                total = len(urls)
                progress = completed / total * 100
                
                if result['success']:
                    views_status = f"✅ {result['views']}" if result['views'] else "❌ 無觀看數"
                    content_status = "✅" if result['content'] else "❌"
                    print(f"📊 {completed}/{total} ({progress:.1f}%) | {result['request_id']} | {views_status} | 內容: {content_status}")
                else:
                    print(f"📊 {completed}/{total} ({progress:.1f}%) | {result['request_id']} | ❌ {result['error']}")
        
        end_time = time.time()
        
        # 統計結果
        successful = [r for r in results if r['success']]
        with_views = [r for r in successful if r['has_views']]
        with_content = [r for r in successful if r['has_content']]
        
        total_count = len(results)
        success_count = len(successful)
        views_count = len(with_views)
        content_count = len(with_content)
        
        print("\n" + "=" * 60)
        print("📊 並行處理結果總結")
        print("=" * 60)
        print(f"⏱️ 總耗時: {end_time - start_time:.1f} 秒")
        print(f"🏎️ 平均速度: {total_count / (end_time - start_time):.2f} URL/秒")
        print(f"✅ 請求成功率: {success_count}/{total_count} ({success_count/total_count*100:.1f}%)")
        print(f"👀 觀看數提取率: {views_count}/{total_count} ({views_count/total_count*100:.1f}%)")
        print(f"📄 內容提取率: {content_count}/{total_count} ({content_count/total_count*100:.1f}%)")
        
        # 顯示成功案例
        if with_views:
            print(f"\n🎯 成功提取觀看數的貼文:")
            for r in with_views:
                post_id = r['url'].split('/')[-1]
                print(f"   • {post_id}: {r['views']}")
        
        # 顯示失敗原因
        failed = [r for r in results if not r['success']]
        if failed:
            print(f"\n❌ 失敗原因統計:")
            errors = {}
            for r in failed:
                error = r['error']
                errors[error] = errors.get(error, 0) + 1
            
            for error, count in errors.items():
                print(f"   • {error}: {count} 次")
        
        # 保存結果
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"final_solution_test_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump({
                'test_name': '最終解決方案測試',
                'timestamp': datetime.now().isoformat(),
                'headers_used': self.optimal_headers,
                'max_workers': max_workers,
                'total_time': end_time - start_time,
                'success_rate': success_count/total_count*100,
                'views_extraction_rate': views_count/total_count*100,
                'results': results
            }, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 詳細結果已保存: {filename}")
        
        return views_count/total_count >= 0.8  # 如果觀看數提取率 >= 80% 就算成功

def main():
    # 測試 URL 列表
    test_urls = [
        'https://www.threads.com/@ttshow.tw/post/DMfOVeqSkM5',  # 已驗證有觀看數
        'https://www.threads.com/@ttshow.tw/post/DIfkbgLSjO3',
        'https://www.threads.com/@ttshow.tw/post/DL_vyT-RZQ6',
    ]
    
    solution = FinalReaderSolution()
    
    print("🎯 最終解決方案測試")
    print("=" * 80)
    print("使用已驗證的最佳 headers 配置:")
    print(json.dumps(solution.optimal_headers, indent=2, ensure_ascii=False))
    print("=" * 80)
    
    # 1. 先測試單個 URL
    print("\n🔍 單個 URL 測試")
    print("-" * 40)
    single_result = solution.test_single_url(test_urls[0])
    
    if single_result['success'] and single_result['has_views']:
        print("\n✅ 單個測試成功！開始並行測試...")
        
        # 2. 測試並行處理
        success = solution.test_parallel_processing(test_urls, max_workers=3)
        
        if success:
            print("\n🎉 最終解決方案測試成功！")
            print("💡 建議將這些 headers 整合到您的主程式中:")
            print("```python")
            print("headers = {")
            for key, value in solution.optimal_headers.items():
                print(f"    '{key}': '{value}',")
            print("}")
            print("```")
        else:
            print("\n⚠️ 並行測試仍需調整，建議降低併發數或增加延遲")
    else:
        print("\n❌ 單個測試失敗，請檢查 Reader 服務狀態")

if __name__ == '__main__':
    main()