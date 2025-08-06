#!/usr/bin/env python3
"""
測試背景執行和進度追蹤的腳本
"""

import asyncio
import time
import uuid
from pathlib import Path
import sys
import os

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

async def simulate_crawl_with_progress():
    """模擬爬蟲執行並回報進度"""
    try:
        from common.nats_client import publish_progress
        from common.redis_client import get_redis_client
        
        # 生成測試任務 ID
        task_id = f"test_{uuid.uuid4().hex[:8]}"
        print(f"🚀 開始測試任務: {task_id}")
        
        # 模擬爬蟲各階段
        stages = [
            ("fetch_start", {"username": "test_user", "extra_posts": 10}),
            ("process_round_1_details", {"username": "test_user", "posts_count": 50, "done": 10, "total": 50}),
            ("process_round_2_details", {"username": "test_user", "posts_count": 50, "done": 25, "total": 50}),
            ("process_round_3_details", {"username": "test_user", "posts_count": 50, "done": 40, "total": 50}),
            ("process_round_4_details", {"username": "test_user", "posts_count": 50, "done": 50, "total": 50}),
            ("completed", {"username": "test_user", "posts_count": 50}),
        ]
        
        for i, (stage, kwargs) in enumerate(stages):
            await publish_progress(task_id, stage, **kwargs)
            print(f"📊 [{i+1}/{len(stages)}] 已發布: {stage}")
            
            # 模擬處理時間
            await asyncio.sleep(2)
        
        # 驗證 Redis 中的最終狀態
        redis_client = get_redis_client()
        final_status = redis_client.get_task_status(task_id)
        
        print(f"\n✅ 測試完成！")
        print(f"📋 最終狀態: {final_status}")
        print(f"\n💡 使用以下命令監控進度:")
        print(f"   python monitor_progress.py {task_id}")
        
        return task_id
        
    except Exception as e:
        print(f"❌ 測試失敗: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_redis_connection():
    """測試 Redis 連線"""
    try:
        from common.redis_client import get_redis_client
        redis_client = get_redis_client()
        
        # 測試基本操作
        test_data = {"test": "value", "timestamp": time.time()}
        success = redis_client.set_task_status("test_connection", test_data)
        
        if success:
            retrieved = redis_client.get_task_status("test_connection")
            print(f"✅ Redis 連線正常")
            print(f"📋 測試資料: {retrieved}")
            return True
        else:
            print("❌ Redis 寫入失敗")
            return False
            
    except Exception as e:
        print(f"❌ Redis 連線測試失敗: {e}")
        return False

def check_environment():
    """檢查環境設定"""
    print("🔍 檢查環境設定...")
    
    # 檢查 Redis URL
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    print(f"📡 Redis URL: {redis_url}")
    
    # 檢查 NATS URL
    nats_url = os.getenv("NATS_URL", "nats://localhost:4222")
    print(f"📡 NATS URL: {nats_url}")
    
    # 檢查是否在 Docker 環境中
    if os.path.exists("/.dockerenv"):
        print("🐳 運行在 Docker 環境中")
    else:
        print("🖥️ 運行在本機環境中")
    
    print()

async def main():
    print("🧪 背景執行和進度追蹤測試")
    print("=" * 40)
    
    # 1. 檢查環境
    check_environment()
    
    # 2. 測試 Redis 連線
    if not test_redis_connection():
        print("❌ Redis 連線失敗，請確認 Redis 服務正在運行")
        return
    
    print()
    
    # 3. 執行模擬爬蟲測試
    print("🚀 開始模擬爬蟲測試...")
    task_id = await simulate_crawl_with_progress()
    
    if task_id:
        print(f"\n🎉 測試成功！現在你可以:")
        print(f"   1. 使用 'python monitor_progress.py {task_id}' 查看進度")
        print(f"   2. 使用 'python monitor_progress.py --list' 查看所有任務")
        print(f"   3. 在另一個終端中啟動 playwright-crawler-agent 進行真實測試")

if __name__ == "__main__":
    asyncio.run(main())