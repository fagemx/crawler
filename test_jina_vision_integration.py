#!/usr/bin/env python3
"""
測試 Jina + Vision 整合功能

測試新的 Jina Reader Screenshot + Gemini Vision 整合流程
"""

import os
import sys
from pathlib import Path

# 載入 .env 檔案
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ 已載入 .env 檔案")
except ImportError:
    print("⚠️ 未安裝 python-dotenv，無法載入 .env 檔案")

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from agents.vision.screenshot_utils import JinaScreenshotCapture


def test_jina_screenshot_capture():
    """測試 JinaScreenshotCapture 基本功能"""
    print("=== 測試 JinaScreenshotCapture ===")
    
    try:
        capture = JinaScreenshotCapture()
        
        # 健康檢查
        health = capture.health_check()
        print(f"健康檢查: {health}")
        
        # 測試 URL
        test_url = "https://www.threads.com/@evenchen14/post/DMZ4lbJTchf"
        
        # 測試 Markdown 解析
        print(f"\n測試 Markdown 解析: {test_url}")
        markdown_metrics = capture.get_markdown_metrics(test_url)
        print(f"Markdown 結果: {markdown_metrics}")
        
        # 測試截圖取得
        print(f"\n測試截圖取得...")
        try:
            image_bytes = capture.get_screenshot_bytes(test_url)
            print(f"截圖大小: {len(image_bytes)} bytes")
            print(f"截圖格式: {'PNG' if image_bytes.startswith(b'\\x89PNG') else 'JPEG' if image_bytes.startswith(b'\\xff\\xd8') else '未知'}")
        except Exception as e:
            print(f"截圖取得失敗: {e}")
        
        return True
        
    except Exception as e:
        print(f"JinaScreenshotCapture 測試失敗: {e}")
        return False


def test_vision_analysis():
    """測試 Vision 分析功能"""
    print("\n=== 測試 Vision 分析 ===")
    
    try:
        # 檢查 Gemini API Key
        gemini_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            print("警告: 未設定 GEMINI_API_KEY，跳過 Vision 測試")
            return False
        
        capture = JinaScreenshotCapture()
        test_url = "https://www.threads.com/@evenchen14/post/DMZ4lbJTchf"
        
        # 測試完整流程（Markdown + Vision 補值）
        print(f"測試完整流程: {test_url}")
        complete_metrics = capture.get_complete_metrics(test_url, gemini_key)
        print(f"完整結果: {complete_metrics}")
        
        return True
        
    except Exception as e:
        print(f"Vision 分析測試失敗: {e}")
        return False


def test_integrated_function():
    """測試整合函數"""
    print("\n=== 測試整合函數 ===")
    
    try:
        gemini_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            print("警告: 未設定 GEMINI_API_KEY，跳過整合測試")
            return False
        
        test_url = "https://www.threads.com/@evenchen14/post/DMZ4lbJTchf"
        
        # 測試基本的 JinaScreenshotCapture 整合功能
        print(f"測試 JinaScreenshotCapture 整合功能: {test_url}")
        capture = JinaScreenshotCapture()
        
        # 先測試 Markdown 解析
        markdown_metrics = capture.get_markdown_metrics(test_url)
        print(f"Markdown 結果: {markdown_metrics}")
        
        # 測試完整流程
        complete_metrics = capture.get_complete_metrics(test_url, gemini_key)
        print(f"完整結果: {complete_metrics}")
        
        return True
        
    except Exception as e:
        print(f"整合函數測試失敗: {e}")
        return False


def test_batch_processing():
    """測試批次處理"""
    print("\n=== 測試批次處理 ===")
    
    try:
        gemini_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            print("警告: 未設定 GEMINI_API_KEY，跳過批次處理測試")
            return False
        
        test_urls = [
            "https://www.threads.com/@evenchen14/post/DMZ4lbJTchf",
            "https://www.threads.com/@evenchen14/post/DMZ4lbJTchf"  # 重複測試
        ]
        
        print(f"批次處理 {len(test_urls)} 個 URL")
        capture = JinaScreenshotCapture()
        
        for i, url in enumerate(test_urls):
            print(f"處理 URL {i+1}: {url}")
            try:
                result = capture.get_complete_metrics(url, gemini_key)
                print(f"結果 {i+1}: 成功 - {result}")
            except Exception as e:
                print(f"結果 {i+1}: 失敗 - {e}")
        
        return True
        
    except Exception as e:
        print(f"批次處理測試失敗: {e}")
        return False


def main():
    """主測試函數"""
    print("開始測試 Jina + Vision 整合功能")
    print("=" * 50)
    
    # 檢查環境變數
    print("環境變數檢查:")
    print(f"GOOGLE_API_KEY: {'已設定' if os.getenv('GOOGLE_API_KEY') else '未設定'}")
    print(f"GEMINI_API_KEY: {'已設定' if os.getenv('GEMINI_API_KEY') else '未設定'}")
    print()
    
    # 執行測試
    tests = [
        ("JinaScreenshotCapture 基本功能", test_jina_screenshot_capture),
        ("Vision 分析功能", test_vision_analysis),
        ("整合函數", test_integrated_function),
        ("批次處理", test_batch_processing)
    ]
    
    results = {}
    for test_name, test_func in tests:
        try:
            print(f"\n{'='*20} {test_name} {'='*20}")
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
        return 0
    else:
        print("⚠️  部分測試失敗，請檢查錯誤訊息")
        return 1


if __name__ == "__main__":
    sys.exit(main())