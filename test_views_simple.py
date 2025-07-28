#!/usr/bin/env python3
"""
簡單測試觀看數解析功能
"""

import sys
import os

# 路徑設定
project_root = os.path.abspath(os.path.dirname(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from agents.playwright_crawler.playwright_logic import parse_views_text

def test_parse_views_text():
    """測試觀看數文字解析功能"""
    print("🧪 === 測試觀看數文字解析功能 ===")
    
    test_cases = [
        # 中文格式
        ("161.9萬次瀏覽", 1619000),
        ("1.2萬次瀏覽", 12000),
        ("5000次瀏覽", 5000),
        ("2.5億次瀏覽", 250000000),
        
        # 英文格式
        ("1.2M views", 1200000),
        ("500K views", 500000),
        ("1,234 views", 1234),
        ("2.5M views", 2500000),
        
        # 邊界情況
        ("", None),
        (None, None),
        ("無效文字", None),
        ("123", 123),
    ]
    
    success_count = 0
    total_count = len(test_cases)
    
    for input_text, expected in test_cases:
        result = parse_views_text(input_text)
        status = "✅" if result == expected else "❌"
        print(f"{status} '{input_text}' -> {result} (期望: {expected})")
        if result == expected:
            success_count += 1
    
    print(f"\n📊 測試結果: {success_count}/{total_count} 通過")
    return success_count == total_count

if __name__ == "__main__":
    test_parse_views_text()