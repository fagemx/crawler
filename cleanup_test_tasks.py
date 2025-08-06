#!/usr/bin/env python3
"""
清理測試任務資料
"""

import os
import glob
from pathlib import Path

def cleanup_test_tasks():
    """清理所有測試任務資料"""
    
    # 1. 清理檔案
    temp_progress_dir = Path("temp_progress")
    
    test_patterns = [
        "playwright_progress_test_*.json",
        "playwright_progress_ui_test_*.json", 
        "playwright_progress_test_connection.json"
    ]
    
    cleaned_files = 0
    for pattern in test_patterns:
        files = list(temp_progress_dir.glob(pattern))
        for file in files:
            try:
                file.unlink()
                print(f"✅ 已刪除: {file.name}")
                cleaned_files += 1
            except Exception as e:
                print(f"❌ 刪除失敗: {file.name} - {e}")
    
    # 2. 清理 Redis（如果可能）
    try:
        from common.redis_client import get_redis_client
        import redis
        
        redis_client = get_redis_client()
        r = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        
        # 刪除測試相關的任務
        test_task_patterns = ["ui_test_", "test_connection", "test_312a423e"]
        
        all_keys = r.keys("task:*")
        cleaned_redis = 0
        
        for key in all_keys:
            task_id = key.decode().replace("task:", "")
            
            # 檢查是否是測試任務
            is_test_task = any(pattern in task_id for pattern in test_task_patterns)
            
            if is_test_task:
                try:
                    r.delete(key)
                    print(f"✅ Redis 已刪除: {task_id}")
                    cleaned_redis += 1
                except Exception as e:
                    print(f"❌ Redis 刪除失敗: {task_id} - {e}")
        
        print(f"\n📊 清理統計:")
        print(f"   檔案: {cleaned_files} 個")
        print(f"   Redis: {cleaned_redis} 個")
        
    except Exception as e:
        print(f"⚠️ Redis 清理失敗: {e}")
    
    print(f"\n✅ 測試資料清理完成！")

if __name__ == "__main__":
    cleanup_test_tasks()