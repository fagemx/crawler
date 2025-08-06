#!/usr/bin/env python3
"""
簡單的進度監控腳本
用法: python monitor_progress.py <job_id>
"""

import time
import sys
import os
import json
from typing import Optional, Dict, Any

def get_redis_client():
    """獲取 Redis 客戶端"""
    try:
        from common.redis_client import get_redis_client
        return get_redis_client()
    except ImportError as e:
        print(f"❌ 無法匯入 Redis 客戶端: {e}")
        sys.exit(1)

def format_progress_bar(progress: float, width: int = 30) -> str:
    """產生進度條"""
    filled = int(width * progress / 100)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {progress:.1f}%"

def format_status(status: Dict[str, Any]) -> str:
    """格式化狀態資訊"""
    stage = status.get("stage", "unknown")
    progress = status.get("progress", 0.0)
    username = status.get("username", "")
    posts_count = status.get("posts_count", "")
    error = status.get("error", "")
    
    result = []
    
    # 基本資訊
    if username:
        result.append(f"用戶: {username}")
    if posts_count:
        result.append(f"貼文數: {posts_count}")
    
    # 進度條
    if progress > 0:
        result.append(format_progress_bar(progress))
    
    # 階段
    result.append(f"階段: {stage}")
    
    # 錯誤
    if error:
        result.append(f"❌ 錯誤: {error}")
    
    return " | ".join(result)

def monitor_task(task_id: str):
    """監控指定任務的進度"""
    redis_client = get_redis_client()
    
    print(f"📊 開始監控任務: {task_id}")
    print("按 Ctrl+C 停止監控\n")
    
    last_status = None
    
    try:
        while True:
            status = redis_client.get_task_status(task_id)
            
            if status is None:
                print(f"\r⏳ 等待任務開始... ({task_id})", end="", flush=True)
            else:
                # 只在狀態改變時更新顯示
                if status != last_status:
                    print(f"\r{format_status(status)}", flush=True)
                    last_status = status
                    
                    # 如果任務完成或發生錯誤，停止監控
                    if (status.get("progress", 0) >= 100 or 
                        "completed" in status.get("stage", "") or 
                        status.get("status") == "error"):
                        print("\n✅ 任務結束")
                        break
            
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\n🛑 監控已停止")

def list_active_tasks():
    """列出所有活躍的任務"""
    redis_client = get_redis_client()
    
    # 嘗試尋找所有任務鍵
    try:
        import redis
        r = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        task_keys = r.keys("task:*")
        
        if not task_keys:
            print("📋 目前沒有活躍的任務")
            return
        
        print("📋 活躍的任務:")
        for key in task_keys:
            task_id = key.decode().replace("task:", "")
            status = redis_client.get_task_status(task_id)
            if status:
                print(f"  - {task_id}: {status.get('stage', 'unknown')}")
        print()
        
    except Exception as e:
        print(f"⚠️ 無法列出任務: {e}")

def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python monitor_progress.py <job_id>     # 監控指定任務")
        print("  python monitor_progress.py --list       # 列出所有活躍任務")
        print()
        print("範例:")
        print("  python monitor_progress.py job_c45351e48907")
        sys.exit(1)
    
    if sys.argv[1] == "--list":
        list_active_tasks()
    else:
        task_id = sys.argv[1]
        monitor_task(task_id)

if __name__ == "__main__":
    main()