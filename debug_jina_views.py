#!/usr/bin/env python3
"""
調試 Jina Views 提取邏輯
"""
import sys
sys.path.append('.')

import re
import requests
from common.settings import get_settings

def test_jina_markdown_extraction():
    """測試實際的 Jina markdown 回應和提取邏輯"""
    settings = get_settings()
    
    # 測試 URL（從您的結果中選一個沒有 views 的）
    test_url = "https://www.threads.net/t/DJUFfR-tpaO"
    
    print(f"🔍 測試 URL: {test_url}")
    print("=" * 60)
    
    # 呼叫 Jina API
    jina_url = f"https://r.jina.ai/{test_url}"
    headers = {}
    if settings.jina_api_key:
        headers["Authorization"] = f"Bearer {settings.jina_api_key}"
        print("✅ 使用 API Key")
    else:
        print("⚠️  使用免費版")
    
    try:
        response = requests.get(jina_url, headers=headers, timeout=30)
        response.raise_for_status()
        markdown_text = response.text
        
        print("📄 Jina Markdown 回應:")
        print("-" * 40)
        print(markdown_text[:1000] + "..." if len(markdown_text) > 1000 else markdown_text)
        print("-" * 40)
        
        # 測試現有的 views 正則表達式
        views_pattern = re.compile(r'Thread.*?(?P<views>[\d\.KM,]+)\s*views', re.IGNORECASE | re.DOTALL)
        views_match = views_pattern.search(markdown_text)
        
        if views_match:
            views_value = views_match.groupdict().get("views")
            print(f"✅ 找到 views: {views_value}")
        else:
            print("❌ 現有正則表達式找不到 views")
            
            # 嘗試其他可能的 views 模式
            alternative_patterns = [
                r'(\d+[\d,]*\.?\d*[KMB]?)\s*views',
                r'views?\s*[:\-]?\s*(\d+[\d,]*\.?\d*[KMB]?)',
                r'(\d+[\d,]*\.?\d*[KMB]?)\s*view',
                r'Thread.*?(\d+[\d,]*\.?\d*[KMB]?)\s*views',
                r'\[Thread.*?(\d+[\d,]*\.?\d*[KMB]?)\s*views',
            ]
            
            print("\n🔍 嘗試其他 views 模式:")
            for i, pattern in enumerate(alternative_patterns):
                match = re.search(pattern, markdown_text, re.IGNORECASE)
                if match:
                    print(f"  ✅ 模式 {i+1}: {pattern} → {match.group(1)}")
                else:
                    print(f"  ❌ 模式 {i+1}: {pattern}")
                    
            # 顯示所有包含 "view" 的行
            print("\n📋 所有包含 'view' 的行:")
            for i, line in enumerate(markdown_text.splitlines()):
                if 'view' in line.lower():
                    print(f"  行 {i+1}: {line.strip()}")
                    
    except Exception as e:
        print(f"❌ 錯誤: {e}")

if __name__ == "__main__":
    test_jina_markdown_extraction() 