#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
測試API失敗回退機制修正
"""

from common.rotation_pipeline import RotationPipelineReader

def test_api_fallback():
    """測試API失敗的回退機制"""
    
    print("🧪 測試API失敗回退機制")
    print("=" * 50)
    
    # 創建rotation實例
    reader = RotationPipelineReader()
    
    # 測試一個可能失敗的URL和一個正常的URL
    test_urls = [
        "https://www.threads.com/@gvmonthly/post/DM2eaiJzEZ8",  # 這個之前503失敗
        "https://www.threads.com/@gvmonthly/post/DMzvu4MTpis",  # 這個應該正常
    ]
    
    print(f"📍 測試URL數量: {len(test_urls)}")
    
    # 使用rotation pipeline處理
    results = reader.rotation_pipeline(test_urls)
    
    print(f"\n📊 處理結果:")
    for result in results:
        post_id = result.get('post_id', 'N/A')
        success = result.get('success', False)
        source = result.get('source', 'N/A')
        views = result.get('views', 'N/A')
        content = result.get('content', 'N/A')
        
        status = "✅" if success else "❌"
        print(f"{status} {post_id}: {source} | 觀看: {views} | 內容: {content[:50] if content else 'N/A'}...")
        
        # 如果失敗，顯示錯誤信息
        if not success:
            api_error = result.get('api_error', '')
            local_error = result.get('local_error', '')
            if api_error:
                print(f"    API錯誤: {api_error}")
            if local_error:
                print(f"    本地錯誤: {local_error}")

if __name__ == "__main__":
    test_api_fallback()