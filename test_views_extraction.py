#!/usr/bin/env python3
"""
快速測試瀏覽數提取功能
"""

import re
from agents.playwright_crawler.parsers.html_parser import HTMLParser

def test_views_extraction():
    print("🧪 測試瀏覽數提取功能...")
    
    # 測試數據
    test_cases = [
        # 新增：英文格式 (Jina發現的格式)
        ("113K views", 113000),
        ("113 K views", 113000), 
        ("1.1M views", 1100000),
        ("36000 views", 36000),
        
        # 原有：中文格式
        ("11萬次瀏覽", 110000),
        ("3.6萬次瀏覽", 36000), 
        ("36,100次瀏覽", 36100),
        ("110000次瀏覽", 110000),
        ("10萬 次瀏覽", 100000),
        ("8万次浏览", 80000),  # 簡體中文
    ]
    
    # 創建HTML內容模擬器
    parser = HTMLParser()
    
    for test_text, expected in test_cases:
        print(f"\n🔍 測試: '{test_text}' -> 期望: {expected}")
        
        # 創建包含測試文本的HTML
        html_content = f'<div>其他內容</div><span>{test_text}</span><div>更多內容</div>'
        
        # 提取瀏覽數
        result = parser._extract_views_count(html_content)
        
        if result == expected:
            print(f"   ✅ 成功: {result}")
        else:
            print(f"   ❌ 失敗: 實際={result}, 期望={expected}")
    
    print("\n" + "="*50)
    print("🎯 測試實際HTML中的'113K views'模式...")
    
    # 模擬真實HTML結構 (基於Jina發現的格式)
    real_html = '''
    <div class="post-content">
        <div>一些內容...</div>
        <a href="#" class="stats-link">Thread ====== 113K views</a>
        <div class="stats">
            <span>1.2K</span>
            <span>33</span>
            <span>53</span>
            <span>73</span>
        </div>
    </div>
    '''
    
    result = parser._extract_views_count(real_html)
    print(f"📊 真實HTML測試結果: {result}")
    if result == 113000:
        print("   ✅ 真實HTML測試成功！")
    else:
        print(f"   ❌ 真實HTML測試失敗，期望: 113000")

if __name__ == "__main__":
    test_views_extraction()