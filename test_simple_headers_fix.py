#!/usr/bin/env python3
"""
Simple Header Fix Test - 基於測試結果的最小修正
"""
import requests
import json
import time
import re
import uuid
from datetime import datetime

class SimpleHeadersFix:
    def __init__(self):
        self.base_url = "http://localhost:8880"
        
    def normalize_content(self, content):
        """標準化內容處理 NBSP"""
        content = content.replace('\u00a0', ' ')  # NBSP
        content = content.replace('\u2002', ' ')  # En space
        content = content.replace('\u2003', ' ')  # Em space
        content = re.sub(r' +', ' ', content)
        return content
    
    def extract_views(self, content):
        """提取觀看數"""
        content = self.normalize_content(content)
        
        patterns = [
            r'Thread\s*={6}\s*([0-9,\.]+[KMB]?)\s*views?',
            r'Thread\s*={6}\s*([0-9,\.]+[KMB]?)',
            r'(\d+(?:\.\d+)?[KMB]?)\s*views?',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(1)
        return None
    
    def is_aggregated_page(self, content, url):
        """檢查是否為聚合頁面"""
        if 'Related threads' in content:
            return True
        
        # 提取原始 post_id
        post_id_match = re.search(r'/post/([A-Za-z0-9_-]+)', url)
        if not post_id_match:
            return False
        
        original_post_id = post_id_match.group(1)
        other_post_ids = re.findall(r'/post/([A-Za-z0-9_-]+)', content)
        other_unique_ids = set(other_post_ids) - {original_post_id}
        
        return len(other_unique_ids) > 1
    
    def fetch_with_optimal_headers(self, url):
        """使用最佳化的 headers 獲取內容"""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "x-wait-for-selector": "article",
            "x-timeout": "25"
        }
        
        try:
            response = requests.get(f"{self.base_url}/{url}", headers=headers, timeout=60)
            
            if response.status_code != 200:
                return None, f"HTTP {response.status_code}"
            
            content = response.text
            
            # 檢查是否為聚合頁面
            if self.is_aggregated_page(content, url):
                return None, "聚合頁面"
            
            # 提取觀看數
            views = self.extract_views(content)
            
            if views:
                return {
                    'views': views,
                    'content': content[:500] + '...' if len(content) > 500 else content,
                    'content_length': len(content)
                }, "成功"
            else:
                return None, "未找到觀看數"
                
        except Exception as e:
            return None, f"請求錯誤: {str(e)}"
    
    def test_urls_list(self, urls):
        """測試 URL 列表"""
        print("🚀 簡化版 Header 修正測試")
        print("=" * 60)
        
        results = []
        
        for i, url in enumerate(urls, 1):
            print(f"\n📄 測試 {i}/{len(urls)}: {url.split('/')[-1]}")
            
            result, reason = self.fetch_with_optimal_headers(url)
            
            if result:
                print(f"✅ 成功提取觀看數: {result['views']}")
                print(f"   內容長度: {result['content_length']:,} 字符")
                success = True
            else:
                print(f"❌ 失敗: {reason}")
                success = False
            
            results.append({
                'url': url,
                'success': success,
                'views': result['views'] if result else None,
                'reason': reason,
                'timestamp': datetime.now().isoformat()
            })
            
            # 間隔避免過於頻繁
            if i < len(urls):
                time.sleep(2)
        
        # 統計結果
        success_count = sum(1 for r in results if r['success'])
        total_count = len(results)
        success_rate = success_count / total_count * 100
        
        print("\n" + "=" * 60)
        print("📊 測試結果總結")
        print("=" * 60)
        print(f"✅ 成功: {success_count}/{total_count} ({success_rate:.1f}%)")
        
        # 顯示成功案例
        successful = [r for r in results if r['success']]
        if successful:
            print("\n🎯 成功案例:")
            for r in successful:
                post_id = r['url'].split('/')[-1]
                print(f"   • {post_id}: {r['views']}")
        
        # 顯示失敗原因
        failed = [r for r in results if not r['success']]
        if failed:
            print("\n❌ 失敗原因統計:")
            reasons = {}
            for r in failed:
                reason = r['reason']
                reasons[reason] = reasons.get(reason, 0) + 1
            
            for reason, count in reasons.items():
                print(f"   • {reason}: {count} 次")
        
        # 保存結果
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"simple_headers_test_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump({
                'test_name': '簡化版Header修正測試',
                'timestamp': datetime.now().isoformat(),
                'success_rate': success_rate,
                'results': results
            }, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 詳細結果已保存: {filename}")
        
        return success_rate >= 70  # 如果成功率 >= 70% 就算通過

def main():
    # 使用原始測試 URL
    test_urls = [
        'https://www.threads.com/@ttshow.tw/post/DMfOVeqSkM5',
        'https://www.threads.com/@ttshow.tw/post/DIfkbgLSjO3',
        'https://www.threads.com/@ttshow.tw/post/DL_vyT-RZQ6',
    ]
    
    tester = SimpleHeadersFix()
    success = tester.test_urls_list(test_urls)
    
    if success:
        print("\n🎉 測試通過！可以將這些 headers 整合到主程式中")
    else:
        print("\n⚠️ 成功率仍需改善，建議進一步調整策略")

if __name__ == '__main__':
    main()