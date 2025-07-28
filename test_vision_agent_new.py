"""
測試新的 Vision Agent 功能

測試流程：
1. RustFS 連接測試
2. Gemini Vision 分析測試
3. 媒體下載和存儲測試
4. 完整流程測試
"""

import asyncio
import os
from typing import Dict, Any

# 設定環境變數（測試用）
os.environ.setdefault("RUSTFS_ENDPOINT", "http://localhost:9000")
os.environ.setdefault("RUSTFS_ACCESS_KEY", "rustfsadmin")
os.environ.setdefault("RUSTFS_SECRET_KEY", "rustfssecret")
os.environ.setdefault("RUSTFS_BUCKET", "threads-media")
os.environ.setdefault("MEDIA_TOP_N_POSTS", "5")
os.environ.setdefault("MEDIA_LIFECYCLE_DAYS", "3")

from agents.vision.vision_logic import create_vision_agent
from agents.vision.gemini_vision import GeminiVisionAnalyzer
from common.rustfs_client import get_rustfs_client


async def test_rustfs_connection():
    """測試 RustFS 連接"""
    print("=== 測試 RustFS 連接 ===")
    
    try:
        client = get_rustfs_client()
        health = client.health_check()
        
        print(f"RustFS 健康狀態: {health}")
        
        if health.get("status") == "healthy":
            print("✅ RustFS 連接成功")
            return True
        else:
            print("❌ RustFS 連接失敗")
            return False
            
    except Exception as e:
        print(f"❌ RustFS 連接錯誤: {str(e)}")
        return False


async def test_gemini_vision():
    """測試 Gemini Vision 分析器"""
    print("\n=== 測試 Gemini Vision 分析器 ===")
    
    try:
        analyzer = GeminiVisionAnalyzer()
        health = analyzer.health_check()
        
        print(f"Gemini Vision 健康狀態: {health}")
        
        if health.get("status") == "healthy":
            print("✅ Gemini Vision 配置成功")
            return True
        else:
            print("❌ Gemini Vision 配置失敗")
            return False
            
    except Exception as e:
        print(f"❌ Gemini Vision 錯誤: {str(e)}")
        return False


async def test_media_download():
    """測試媒體下載功能"""
    print("\n=== 測試媒體下載功能 ===")
    
    # 使用一個測試圖片 URL（可以替換為實際的測試 URL）
    test_image_url = "https://via.placeholder.com/300x200.jpg"
    
    try:
        client = get_rustfs_client()
        
        print(f"嘗試下載測試圖片: {test_image_url}")
        media_bytes, mime_type = await client.download_media(test_image_url)
        
        print(f"✅ 下載成功:")
        print(f"   - 檔案大小: {len(media_bytes)} bytes")
        print(f"   - MIME 類型: {mime_type}")
        
        # 測試存儲到 RustFS
        test_post_id = "test_post_001"
        storage_result = await client.store_media(test_post_id, media_bytes, mime_type)
        
        print(f"✅ 存儲成功:")
        print(f"   - 存儲 key: {storage_result['storage_key']}")
        print(f"   - 狀態: {storage_result['status']}")
        
        # 測試從 RustFS 讀取
        retrieved_bytes, retrieved_mime = await client.get_media(storage_result['storage_key'])
        
        if len(retrieved_bytes) == len(media_bytes):
            print("✅ 讀取驗證成功")
        else:
            print("❌ 讀取驗證失敗")
            
        return True
        
    except Exception as e:
        print(f"❌ 媒體下載測試失敗: {str(e)}")
        return False


async def test_vision_agent():
    """測試 Vision Agent 整體功能"""
    print("\n=== 測試 Vision Agent 整體功能 ===")
    
    try:
        agent = create_vision_agent()
        health = await agent.health_check()
        
        print(f"Vision Agent 健康狀態: {health}")
        
        if health.get("status") == "healthy":
            print("✅ Vision Agent 初始化成功")
            
            # 測試配置
            print(f"配置參數:")
            print(f"   - 處理前 N 名貼文: {agent.top_n_posts}")
            
            return True
        else:
            print("❌ Vision Agent 初始化失敗")
            return False
            
    except Exception as e:
        print(f"❌ Vision Agent 測試失敗: {str(e)}")
        return False


async def test_cleanup():
    """測試清理功能"""
    print("\n=== 測試清理功能 ===")
    
    try:
        client = get_rustfs_client()
        cleanup_result = client.cleanup_expired_media()
        
        print(f"清理結果: {cleanup_result}")
        
        if cleanup_result.get("status") == "completed":
            print("✅ 清理功能正常")
            return True
        else:
            print("❌ 清理功能異常")
            return False
            
    except Exception as e:
        print(f"❌ 清理測試失敗: {str(e)}")
        return False


async def main():
    """主測試函數"""
    print("🚀 開始測試新的 Vision Agent 功能")
    print("=" * 50)
    
    test_results = []
    
    # 執行各項測試
    tests = [
        ("RustFS 連接", test_rustfs_connection),
        ("Gemini Vision", test_gemini_vision),
        ("媒體下載", test_media_download),
        ("Vision Agent", test_vision_agent),
        ("清理功能", test_cleanup)
    ]
    
    for test_name, test_func in tests:
        try:
            result = await test_func()
            test_results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} 測試異常: {str(e)}")
            test_results.append((test_name, False))
    
    # 總結測試結果
    print("\n" + "=" * 50)
    print("📊 測試結果總結:")
    
    passed = 0
    total = len(test_results)
    
    for test_name, result in test_results:
        status = "✅ 通過" if result else "❌ 失敗"
        print(f"   {test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n總計: {passed}/{total} 項測試通過")
    
    if passed == total:
        print("🎉 所有測試通過！新的 Vision Agent 功能已就緒")
    else:
        print("⚠️  部分測試失敗，請檢查配置和環境")
    
    return passed == total


if __name__ == "__main__":
    # 檢查必要的環境變數
    required_env_vars = [
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY"
    ]
    
    missing_vars = []
    for var in required_env_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print("❌ 缺少必要的環境變數:")
        for var in missing_vars:
            print(f"   - {var}")
        print("\n請在 .env 檔案中設定這些變數")
        exit(1)
    
    # 執行測試
    success = asyncio.run(main())
    exit(0 if success else 1)