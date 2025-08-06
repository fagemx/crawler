#!/usr/bin/env python3
"""
測試完整的保存流程 - 從 Redis 到 PostgreSQL
"""
import sys
from pathlib import Path

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import asyncio
from common.redis_client import get_redis_client
from ui.components.playwright_utils import PlaywrightUtils
from ui.components.playwright_database_handler import PlaywrightDatabaseHandler

async def test_save_flow():
    """測試完整的保存流程"""
    task_id = "28ebc0e7-95b7-4c87-9e6a-31404b257a67"
    
    print("🔍 步驟1: 從 Redis 取得數據")
    redis_client = get_redis_client()
    data = redis_client.get_task_status(task_id)
    
    if not data:
        print("❌ Redis 中沒有數據")
        return
    
    final_data = data.get('final_data', {})
    print(f"✅ Redis 數據: {len(final_data.get('results', []))} 篇貼文")
    
    print("\n🔄 步驟2: 數據轉換")
    converted_results = PlaywrightUtils.convert_playwright_results(final_data)
    converted_results["target_username"] = "netflixtw"  # 設置用戶名
    
    results_count = len(converted_results.get("results", []))
    print(f"✅ 轉換結果: {results_count} 篇貼文")
    
    if results_count == 0:
        print("❌ 轉換後沒有數據")
        return
    
    print("\n💾 步驟3: 保存到資料庫")
    db_handler = PlaywrightDatabaseHandler()
    
    try:
        result = await db_handler.save_to_database_async(converted_results)
        print(f"✅ 保存成功!")
        
        # 檢查統計
        print("\n📊 步驟4: 檢查統計")
        stats = await db_handler._get_stats_async()  # 直接調用 async 方法
        print(f"✅ 總貼文數: {stats.get('total_posts', 0)}")
        user_stats = stats.get('user_stats', [])
        for user in user_stats:
            if user['username'] == 'netflixtw':
                print(f"✅ netflixtw: {user['post_count']} 篇貼文")
                break
            
    except Exception as e:
        print(f"❌ 保存失敗: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_save_flow())