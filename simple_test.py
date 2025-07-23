#!/usr/bin/env python3
"""
簡化測試腳本

測試 Jina Reader 的基本功能，不依賴 Google GenAI
"""

import requests
import re
from typing import Dict, Optional


def parse_number(text: str) -> Optional[int]:
    """解析數字字串（支援 K, M 後綴）"""
    if not text:
        return None
    
    text = text.strip()
    if not text:
        return None
        
    try:
        if text.lower().endswith(('k', 'K')):
            return int(float(text[:-1]) * 1_000)
        elif text.lower().endswith(('m', 'M')):
            return int(float(text[:-1]) * 1_000_000)
        else:
            return int(text.replace(',', ''))
    except (ValueError, TypeError):
        return None


def test_jina_markdown():
    """測試 Jina Reader Markdown 功能"""
    print("=== 測試 Jina Reader Markdown ===")
    
    try:
        # 測試 URL
        test_url = "https://www.threads.com/@evenchen14/post/DMZ4lbJTchf"
        jina_url = f"https://r.jina.ai/{test_url}"
        
        print(f"測試 URL: {test_url}")
        print(f"Jina URL: {jina_url}")
        
        # 發送請求
        headers = {"x-respond-with": "markdown"}
        response = requests.get(jina_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        markdown_text = response.text
        print(f"Markdown 長度: {len(markdown_text)} 字符")
        
        # 顯示前 500 字符
        print(f"Markdown 內容預覽:")
        print("-" * 50)
        print(markdown_text[:500])
        print("-" * 50)
        
        # 嘗試解析指標 - 調整正則表達式匹配實際格式
        # 從測試看到格式是: [Thread ====== 4K views]
        views_pattern = re.compile(r'Thread.*?(\d+(?:\.\d+)?[KM]?)\s*views', re.I)
        
        # 先嘗試提取 views
        views_match = views_pattern.search(markdown_text)
        views = parse_number(views_match.group(1)) if views_match else None
        
        print(f"Views 匹配結果: {views_match.group(1) if views_match else 'None'} -> {views}")
        
        # 嘗試找其他指標的模式（可能在不同位置）
        # 顯示更多內容來分析
        print(f"\n更多 Markdown 內容:")
        print("-" * 50)
        print(markdown_text[500:1500])  # 顯示中間部分
        print("-" * 50)
        
        # 簡化的指標結果
        metrics = {
            "views": views,
            "likes": None,    # 需要進一步分析 markdown 結構
            "comments": None,
            "reposts": None,
            "shares": None
        }
        
        # 嘗試更通用的數字提取
        numbers = re.findall(r'\b(\d+(?:\.\d+)?[KM]?)\b', markdown_text)
        print(f"找到的所有數字: {numbers}")
        
        print(f"解析結果: {metrics}")
        
        # 如果至少找到 views，就算成功
        if views is not None:
            print("✅ 成功提取 views 數據")
            return True
        else:
            print("❌ 無法解析 views 數據")
            return False
            
    except Exception as e:
        print(f"❌ 測試失敗: {e}")
        return False


def test_jina_screenshot():
    """測試 Jina Reader Screenshot 功能"""
    print("\n=== 測試 Jina Reader Screenshot ===")
    
    try:
        # 測試 URL
        test_url = "https://www.threads.com/@evenchen14/post/DMZ4lbJTchf"
        jina_url = f"https://r.jina.ai/{test_url}"
        
        print(f"測試 URL: {test_url}")
        print(f"Jina URL: {jina_url}")
        
        # 發送請求
        headers = {"x-respond-with": "screenshot"}
        response = requests.get(jina_url, headers=headers, timeout=45)
        response.raise_for_status()
        
        image_bytes = response.content
        print(f"截圖大小: {len(image_bytes)} bytes")
        
        # 檢查圖片格式
        if image_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
            print("圖片格式: PNG")
        elif image_bytes.startswith(b'\xff\xd8\xff'):
            print("圖片格式: JPEG")
        else:
            print("圖片格式: 未知")
            # 顯示前 16 bytes 來調試
            print(f"前 16 bytes: {image_bytes[:16]}")
            print(f"前 16 bytes (hex): {image_bytes[:16].hex()}")
        
        # 檢查 Content-Type
        content_type = response.headers.get('content-type', 'unknown')
        print(f"Content-Type: {content_type}")
        
        return True
        
    except Exception as e:
        print(f"❌ 測試失敗: {e}")
        return False


def main():
    """主測試函數"""
    print("開始測試 Jina Reader 基本功能")
    print("=" * 50)
    
    # 執行測試
    tests = [
        ("Jina Markdown", test_jina_markdown),
        ("Jina Screenshot", test_jina_screenshot)
    ]
    
    results = {}
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"{test_name} 執行異常: {e}")
            results[test_name] = False
    
    # 總結
    print(f"\n{'='*50}")
    print("測試總結:")
    for test_name, success in results.items():
        status = "✅ 通過" if success else "❌ 失敗"
        print(f"  {test_name}: {status}")
    
    total_tests = len(results)
    passed_tests = sum(results.values())
    print(f"\n總計: {passed_tests}/{total_tests} 個測試通過")
    
    if passed_tests == total_tests:
        print("🎉 所有測試都通過了！")
        print("\n接下來可以:")
        print("1. 執行 python install_genai.py 安裝 Google GenAI")
        print("2. 設定 GEMINI_API_KEY 環境變數")
        print("3. 執行 python test_jina_vision_integration.py 測試完整功能")
        return 0
    else:
        print("⚠️ 部分測試失敗，請檢查網路連線和 Jina Reader 服務狀態")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())