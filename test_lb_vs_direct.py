#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LB vs 直連效能比較測試
"""

import requests
import time

def test_endpoint(endpoint: str, url: str, description: str):
    """測試單一端點"""
    full_url = f"{endpoint}/{url}"
    print(f"\n🔍 測試 {description}: {endpoint}")
    
    try:
        start_time = time.time()
        response = requests.get(full_url, timeout=30)
        end_time = time.time()
        
        elapsed = end_time - start_time
        status = response.status_code
        content_length = len(response.text) if response.text else 0
        
        print(f"   ✅ 狀態: {status}")
        print(f"   ⏱️ 耗時: {elapsed:.2f}s")
        print(f"   📊 內容長度: {content_length} 字符")
        
        return status == 200, elapsed, content_length
        
    except Exception as e:
        print(f"   ❌ 失敗: {e}")
        return False, 0, 0

def main():
    """主測試函數"""
    # 測試URL（修正為threads.net）
    test_url = "https://www.threads.net/@ttshow.tw/post/DIfkbgLSjO3"
    
    print("🚀 開始效能比較測試...")
    
    # 測試各端點
    results = []
    
    # 1. 負載均衡器
    success, elapsed, length = test_endpoint("http://localhost:8880", test_url, "負載均衡器")
    results.append(("LB", success, elapsed, length))
    
    # 2. 直連Reader-1 (假設在18080)
    success, elapsed, length = test_endpoint("http://localhost:18080", test_url, "直連Reader-1")
    results.append(("Reader-1", success, elapsed, length))
    
    # 3. 直連Reader-2 (假設在18081)
    success, elapsed, length = test_endpoint("http://localhost:18081", test_url, "直連Reader-2")
    results.append(("Reader-2", success, elapsed, length))
    
    # 分析結果
    print("\n" + "="*60)
    print("📊 效能比較結果:")
    print("="*60)
    
    for name, success, elapsed, length in results:
        status_icon = "✅" if success else "❌"
        print(f"{status_icon} {name:12} | 耗時: {elapsed:6.2f}s | 長度: {length:8} 字符")
    
    # 找出最快的
    successful_results = [(name, elapsed) for name, success, elapsed, length in results if success]
    if successful_results:
        fastest = min(successful_results, key=lambda x: x[1])
        print(f"\n🏆 最快: {fastest[0]} ({fastest[1]:.2f}s)")
        
        # 給出建議
        if fastest[0] == "LB":
            print("💡 建議: 負載均衡器表現良好，使用LB策略")
        else:
            print("💡 建議: 直連比LB快，考慮使用直連策略")
    else:
        print("\n❌ 所有端點都失敗了")

if __name__ == "__main__":
    main()