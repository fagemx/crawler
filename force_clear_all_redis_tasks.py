#!/usr/bin/env python3
"""
強制清理所有 Redis 任務
"""
import sys
from pathlib import Path

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from common.redis_client import get_redis_client

def force_clear_all_tasks():
    """強制清理所有 Redis 任務"""
    try:
        redis_client = get_redis_client()
        
        # 獲取所有任務鍵
        task_keys = redis_client.redis.keys("task:*")
        
        if not task_keys:
            print("🎉 沒有找到任何 Redis 任務")
            return
        
        print(f"📋 找到 {len(task_keys)} 個 Redis 任務:")
        for key in task_keys:
            if isinstance(key, bytes):
                key = key.decode('utf-8')
            task_id = key.replace("task:", "")
            print(f"  - {task_id}")
        
        confirm = input(f"\n⚠️  確定要清理所有 {len(task_keys)} 個 Redis 任務嗎？(輸入 'YES' 確認): ")
        if confirm != "YES":
            print("❌ 取消清理")
            return
        
        # 批量刪除
        deleted_count = redis_client.redis.delete(*task_keys)
        print(f"\n✅ 成功清理 {deleted_count} 個 Redis 任務")
        
        # 驗證清理結果
        remaining_keys = redis_client.redis.keys("task:*")
        if remaining_keys:
            print(f"⚠️  仍有 {len(remaining_keys)} 個任務未清理")
        else:
            print("🎉 所有 Redis 任務已清理完成")
            
    except Exception as e:
        print(f"❌ 清理失敗: {e}")

if __name__ == "__main__":
    force_clear_all_tasks()