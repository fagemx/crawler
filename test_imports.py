#!/usr/bin/env python3
"""
測試所有核心模組的導入

檢查是否有導入錯誤
"""

def test_imports():
    """測試核心模組導入"""
    print("🧪 測試模組導入")
    print("=" * 40)
    
    # 載入環境變數
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("✅ 環境變數載入成功")
    except ImportError:
        print("⚠️  python-dotenv 未安裝，跳過環境變數載入")
    
    try:
        print("📦 測試 common.settings...")
        from common.settings import get_settings
        settings = get_settings()
        print("✅ common.settings 導入成功")
        
        print("📦 測試 common.a2a...")
        from common.a2a import A2AMessage, stream_text, TaskState
        print("✅ common.a2a 導入成功")
        
        print("📦 測試 agents.crawler.crawler_logic...")
        from agents.crawler.crawler_logic import CrawlerLogic
        print("✅ agents.crawler.crawler_logic 導入成功")
        
        print("📦 測試 apify_client...")
        from apify_client import ApifyClient
        print("✅ apify_client 導入成功")
        
        print("📦 測試 fastapi...")
        from fastapi import FastAPI
        print("✅ fastapi 導入成功")
        
        print("📦 測試 pydantic...")
        from pydantic import BaseModel
        from pydantic_settings import BaseSettings
        print("✅ pydantic 和 pydantic_settings 導入成功")
        
        print("\n🎉 所有核心模組導入成功！")
        return True
        
    except ImportError as e:
        print(f"❌ 導入錯誤: {e}")
        return False
    except Exception as e:
        print(f"❌ 其他錯誤: {e}")
        return False


if __name__ == "__main__":
    success = test_imports()
    if success:
        print("\n✅ 可以繼續執行 test_crawler.py")
    else:
        print("\n❌ 請先解決導入問題")