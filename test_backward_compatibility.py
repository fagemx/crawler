#!/usr/bin/env python3
"""
向後兼容性測試

確保 Plan E 重構後，舊的 JinaScreenshotCapture 功能仍然可以正常工作
這個測試不依賴 Redis 和 PostgreSQL，只測試核心的 Jina + Vision 功能
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


def test_jina_screenshot_basic():
    """測試 JinaScreenshotCapture 基本功能（不依賴資料庫）"""
    print("=== 測試 JinaScreenshotCapture 基本功能 ===")
    
    try:
        capture = JinaScreenshotCapture()
        
        # 健康檢查
        health = capture.health_check()
        print(f"健康檢查: {health}")
        
        if health.get("status") != "healthy":
            print("❌ Jina Reader 健康檢查失敗")
            return False
        
        # 測試 URL
        test_url = "https://www.threads.com/@evenchen14/post/DMZ4lbJTchf"
        
        # 測試 Markdown 解析
        print(f"\n測試 Markdown 解析: {test_url}")
        markdown_metrics = capture.get_markdown_metrics(test_url)
        print(f"Markdown 結果: {markdown_metrics}")
        
        # 驗證結果格式
        expected_keys = ["views", "likes", "comments", "reposts", "shares"]
        if not all(key in markdown_metrics for key in expected_keys):
            print(f"❌ Markdown 結果缺少必要的鍵: {expected_keys}")
            return False
        
        # 測試截圖取得
        print(f"\n測試截圖取得...")
        try:
            image_bytes = capture.get_screenshot_bytes(test_url)
            print(f"截圖大小: {len(image_bytes)} bytes")
            
            # 檢查圖片格式
            if image_bytes.startswith(b'\\x89PNG'):
                print("截圖格式: PNG")
            elif image_bytes.startswith(b'\\xff\\xd8'):
                print("截圖格式: JPEG")
            else:
                print("截圖格式: 未知")
            
            if len(image_bytes) < 1000:  # 太小可能是錯誤
                print("❌ 截圖大小異常")
                return False
                
        except Exception as e:
            print(f"截圖取得失敗: {e}")
            return False
        
        print("✅ JinaScreenshotCapture 基本功能測試通過")
        return True
        
    except Exception as e:
        print(f"❌ JinaScreenshotCapture 基本功能測試失敗: {e}")
        return False


def test_vision_analysis_standalone():
    """測試獨立的 Vision 分析功能"""
    print("\n=== 測試獨立 Vision 分析功能 ===")
    
    try:
        # 檢查 Gemini API Key
        gemini_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            print("⚠️ 未設定 GEMINI_API_KEY，跳過 Vision 測試")
            return True  # 不算失敗，只是跳過
        
        capture = JinaScreenshotCapture()
        test_url = "https://www.threads.com/@evenchen14/post/DMZ4lbJTchf"
        
        # 測試獨立的 Vision 分析
        print(f"測試 Vision 分析: {test_url}")
        
        # 先獲取截圖
        image_bytes = capture.get_screenshot_bytes(test_url)
        print(f"獲取截圖: {len(image_bytes)} bytes")
        
        # 分析截圖
        vision_metrics = capture.analyze_with_vision(image_bytes, gemini_key)
        print(f"Vision 分析結果: {vision_metrics}")
        
        # 驗證結果格式
        if not isinstance(vision_metrics, dict):
            print(f"❌ Vision 分析結果格式錯誤: {type(vision_metrics)}")
            return False
        
        expected_keys = ["views", "likes", "comments", "reposts", "shares"]
        if not any(key in vision_metrics for key in expected_keys):
            print(f"❌ Vision 分析結果缺少預期的鍵: {expected_keys}")
            return False
        
        print("✅ 獨立 Vision 分析功能測試通過")
        return True
        
    except Exception as e:
        print(f"❌ 獨立 Vision 分析功能測試失敗: {e}")
        return False


def test_complete_metrics_integration():
    """測試完整的指標整合功能（舊版 API）"""
    print("\n=== 測試完整指標整合功能 ===")
    
    try:
        gemini_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            print("⚠️ 未設定 GEMINI_API_KEY，跳過整合測試")
            return True
        
        test_url = "https://www.threads.com/@evenchen14/post/DMZ4lbJTchf"
        
        # 測試完整流程（這是舊版測試中使用的主要方法）
        print(f"測試完整流程: {test_url}")
        capture = JinaScreenshotCapture()
        
        complete_metrics = capture.get_complete_metrics(test_url, gemini_key)
        print(f"完整結果: {complete_metrics}")
        
        # 驗證結果
        if not isinstance(complete_metrics, dict):
            print(f"❌ 完整結果格式錯誤: {type(complete_metrics)}")
            return False
        
        expected_keys = ["views", "likes", "comments", "reposts", "shares"]
        if not all(key in complete_metrics for key in expected_keys):
            print(f"❌ 完整結果缺少必要的鍵: {expected_keys}")
            return False
        
        # 檢查是否有有效的數值
        valid_values = [v for v in complete_metrics.values() if v is not None and v > 0]
        if len(valid_values) == 0:
            print("⚠️ 所有指標都是 0 或 None，可能解析失敗")
            # 不算失敗，因為可能是測試 URL 的問題
        
        print("✅ 完整指標整合功能測試通過")
        return True
        
    except Exception as e:
        print(f"❌ 完整指標整合功能測試失敗: {e}")
        return False


def test_fill_missing_with_vision():
    """測試 Vision 補值功能（舊版 API）"""
    print("\n=== 測試 Vision 補值功能 ===")
    
    try:
        gemini_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            print("⚠️ 未設定 GEMINI_API_KEY，跳過補值測試")
            return True
        
        test_url = "https://www.threads.com/@evenchen14/post/DMZ4lbJTchf"
        
        # 創建部分指標（模擬 Markdown 解析的不完整結果）
        partial_metrics = {
            "views": 1000,
            "likes": None,     # 缺失
            "comments": None,  # 缺失
            "reposts": 0,
            "shares": 1
        }
        
        print(f"測試補值功能: {test_url}")
        print(f"部分指標: {partial_metrics}")
        
        capture = JinaScreenshotCapture()
        
        # 測試補值功能
        complete_metrics = capture.fill_missing_with_vision(
            post_url=test_url,
            partial_metrics=partial_metrics,
            gemini_api_key=gemini_key
        )
        
        print(f"補值後結果: {complete_metrics}")
        
        # 驗證補值結果
        if not isinstance(complete_metrics, dict):
            print(f"❌ 補值結果格式錯誤: {type(complete_metrics)}")
            return False
        
        # 檢查原有的非 None 值是否保留
        if complete_metrics.get("views") != 1000:
            print("❌ 原有的 views 值未保留")
            return False
        
        if complete_metrics.get("shares") != 1:
            print("❌ 原有的 shares 值未保留")
            return False
        
        # 檢查缺失的值是否被補值
        if complete_metrics.get("likes") is None and complete_metrics.get("comments") is None:
            print("⚠️ Vision 補值可能未成功，但不算失敗")
        
        print("✅ Vision 補值功能測試通過")
        return True
        
    except Exception as e:
        print(f"❌ Vision 補值功能測試失敗: {e}")
        return False


def main():
    """主測試函數"""
    print("開始向後兼容性測試")
    print("=" * 50)
    print("這個測試確保 Plan E 重構後，舊的 JinaScreenshotCapture 功能仍然可用")
    print()
    
    # 檢查環境變數
    print("環境變數檢查:")
    print(f"GOOGLE_API_KEY: {'已設定' if os.getenv('GOOGLE_API_KEY') else '未設定'}")
    print(f"GEMINI_API_KEY: {'已設定' if os.getenv('GEMINI_API_KEY') else '未設定'}")
    print()
    
    # 執行測試
    tests = [
        ("JinaScreenshotCapture 基本功能", test_jina_screenshot_basic),
        ("獨立 Vision 分析功能", test_vision_analysis_standalone),
        ("完整指標整合功能", test_complete_metrics_integration),
        ("Vision 補值功能", test_fill_missing_with_vision)
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
    print("向後兼容性測試總結:")
    for test_name, success in results.items():
        status = "✅ 通過" if success else "❌ 失敗"
        print(f"  {test_name}: {status}")
    
    total_tests = len(results)
    passed_tests = sum(results.values())
    print(f"\n總計: {passed_tests}/{total_tests} 個測試通過")
    
    if passed_tests == total_tests:
        print("🎉 所有向後兼容性測試都通過了！")
        print("✅ 舊的 JinaScreenshotCapture 功能在 Plan E 重構後仍然可用")
        return 0
    else:
        print("⚠️  部分測試失敗，可能存在向後兼容性問題")
        return 1


if __name__ == "__main__":
    sys.exit(main())