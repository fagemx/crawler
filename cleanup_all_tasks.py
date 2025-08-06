#!/usr/bin/env python3
"""
完全清理腳本 - 清理所有任務（包括真實任務）
注意：這會清理所有任務數據，請謹慎使用
"""
import asyncio
import sys
import os
from pathlib import Path
import json
from typing import List

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from common.redis_client import get_redis_client

class TaskCleaner:
    """任務清理器"""
    
    def __init__(self):
        self.redis_client = get_redis_client()
        self.temp_progress_dir = Path("temp_progress")
    
    def get_all_task_ids(self) -> List[str]:
        """獲取所有任務ID"""
        task_ids = set()
        
        # 1. 從 Redis 獲取
        try:
            # 正確的 Redis 客戶端訪問方式（使用正確的鍵值模式）
            redis_keys = self.redis_client.redis.keys("task:*")
            for key in redis_keys:
                if isinstance(key, bytes):
                    key = key.decode('utf-8')
                task_id = key.replace("task:", "")
                task_ids.add(task_id)
            print(f"📡 從 Redis 找到 {len(redis_keys)} 個任務")
        except Exception as e:
            print(f"❌ Redis 讀取失敗: {e}")
        
        # 2. 從本地文件獲取
        if self.temp_progress_dir.exists():
            for progress_file in self.temp_progress_dir.glob("*.json"):
                task_id = progress_file.stem
                task_ids.add(task_id)
            print(f"📁 從本地文件找到 {len(list(self.temp_progress_dir.glob('*.json')))} 個任務")
        
        return list(task_ids)
    
    def clean_task(self, task_id: str) -> bool:
        """清理單個任務"""
        success = True
        
        # 1. 清理 Redis
        try:
            # 正確的 Redis 客戶端訪問方式（使用正確的鍵值模式）
            result = self.redis_client.redis.delete(f"task:{task_id}")
            if result > 0:
                print(f"  📡 Redis: ✅")
            else:
                print(f"  📡 Redis: 🚫 鍵不存在")
        except Exception as e:
            print(f"  📡 Redis: ❌ {e}")
            success = False
        
        # 2. 清理本地進度文件
        progress_file = self.temp_progress_dir / f"{task_id}.json"
        if progress_file.exists():
            try:
                progress_file.unlink()
                print(f"  📁 進度文件: ✅")
            except Exception as e:
                print(f"  📁 進度文件: ❌ {e}")
                success = False
        else:
            print(f"  📁 進度文件: 🚫 不存在")
        
        return success
    
    def clean_all_tasks(self, confirm: bool = False):
        """清理所有任務"""
        task_ids = self.get_all_task_ids()
        
        if not task_ids:
            print("🎉 沒有找到任何任務")
            return
        
        print(f"\n📋 找到 {len(task_ids)} 個任務:")
        for i, task_id in enumerate(task_ids, 1):
            print(f"  {i}. {task_id}")
        
        if not confirm:
            print(f"\n⚠️  警告：這將清理所有 {len(task_ids)} 個任務")
            print("⚠️  這包括真實的任務數據，不只是測試數據")
            confirm_input = input("確定要繼續嗎？(輸入 'YES' 確認): ")
            if confirm_input != "YES":
                print("❌ 取消清理")
                return
        
        print(f"\n🧹 開始清理 {len(task_ids)} 個任務...")
        
        success_count = 0
        for i, task_id in enumerate(task_ids, 1):
            print(f"\n[{i}/{len(task_ids)}] 清理任務: {task_id}")
            if self.clean_task(task_id):
                success_count += 1
                print(f"  ✅ 成功")
            else:
                print(f"  ❌ 失敗")
        
        print(f"\n🎉 清理完成: {success_count}/{len(task_ids)} 成功")
    
    def clean_specific_tasks(self, task_ids: List[str]):
        """清理指定的任務"""
        print(f"🧹 清理指定的 {len(task_ids)} 個任務...")
        
        success_count = 0
        for i, task_id in enumerate(task_ids, 1):
            print(f"\n[{i}/{len(task_ids)}] 清理任務: {task_id}")
            if self.clean_task(task_id):
                success_count += 1
                print(f"  ✅ 成功")
            else:
                print(f"  ❌ 失敗")
        
        print(f"\n🎉 清理完成: {success_count}/{len(task_ids)} 成功")

def main():
    """主函數"""
    cleaner = TaskCleaner()
    
    # 解析命令行參數
    if len(sys.argv) > 1:
        if sys.argv[1] == "--all":
            # 清理所有任務（跳過確認）
            cleaner.clean_all_tasks(confirm=True)
        elif sys.argv[1] == "--list":
            # 只列出任務
            task_ids = cleaner.get_all_task_ids()
            if task_ids:
                print(f"📋 找到 {len(task_ids)} 個任務:")
                for i, task_id in enumerate(task_ids, 1):
                    print(f"  {i}. {task_id}")
            else:
                print("🎉 沒有找到任何任務")
        else:
            # 清理指定的任務ID
            task_ids = sys.argv[1:]
            cleaner.clean_specific_tasks(task_ids)
    else:
        # 互動式清理
        cleaner.clean_all_tasks()

if __name__ == "__main__":
    main()