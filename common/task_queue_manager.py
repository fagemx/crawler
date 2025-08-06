"""
任務佇列管理器 - 確保依序執行爬蟲任務
"""

import json
import asyncio
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum

class TaskStatus(str, Enum):
    """任務狀態"""
    WAITING = "waiting"      # 等待中
    RUNNING = "running"      # 執行中
    COMPLETED = "completed"  # 已完成
    ERROR = "error"          # 錯誤
    CANCELLED = "cancelled"  # 已取消

@dataclass
class QueuedTask:
    """佇列中的任務"""
    task_id: str
    username: str
    max_posts: int
    mode: str
    status: TaskStatus
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error_message: Optional[str] = None
    
    @property
    def display_status(self) -> str:
        """顯示用的狀態文字"""
        status_map = {
            TaskStatus.WAITING: "⏳ 等待中",
            TaskStatus.RUNNING: "🔄 執行中", 
            TaskStatus.COMPLETED: "✅ 已完成",
            TaskStatus.ERROR: "❌ 錯誤",
            TaskStatus.CANCELLED: "🚫 已取消"
        }
        return status_map.get(self.status, "❓ 未知")
    
    @property
    def wait_time(self) -> str:
        """等待時間"""
        if self.status == TaskStatus.WAITING:
            elapsed = time.time() - self.created_at
            return f"{elapsed:.0f}秒"
        return "-"
    
    @property
    def execution_time(self) -> str:
        """執行時間"""
        if self.started_at:
            end_time = self.completed_at or time.time()
            elapsed = end_time - self.started_at
            return f"{elapsed:.0f}秒"
        return "-"

class TaskQueueManager:
    """任務佇列管理器"""
    
    def __init__(self):
        self.queue_file = Path("temp_progress/task_queue.json")
        self.queue_file.parent.mkdir(exist_ok=True)
        self._running_task_id: Optional[str] = None
        
    def _load_queue(self) -> List[QueuedTask]:
        """載入佇列"""
        try:
            if self.queue_file.exists():
                with open(self.queue_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    tasks = []
                    for task_data in data:
                        # 確保 status 是 TaskStatus Enum
                        if isinstance(task_data.get('status'), str):
                            task_data['status'] = TaskStatus(task_data['status'])
                        tasks.append(QueuedTask(**task_data))
                    return tasks
            return []
        except Exception as e:
            print(f"❌ 載入佇列失敗: {e}")
            return []
    
    def _save_queue(self, queue: List[QueuedTask]):
        """儲存佇列"""
        try:
            with open(self.queue_file, 'w', encoding='utf-8') as f:
                json.dump([asdict(task) for task in queue], f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"❌ 儲存佇列失敗: {e}")
    
    def add_task(self, task_id: str, username: str, max_posts: int, mode: str) -> bool:
        """新增任務到佇列"""
        try:
            queue = self._load_queue()
            
            # 檢查是否已經存在相同的任務
            if any(task.task_id == task_id for task in queue):
                return False
            
            new_task = QueuedTask(
                task_id=task_id,
                username=username,
                max_posts=max_posts,
                mode=mode,
                status=TaskStatus.WAITING,
                created_at=time.time()
            )
            
            queue.append(new_task)
            self._save_queue(queue)
            
            print(f"📥 任務已加入佇列: {username} (ID: {task_id[:8]}...)")
            return True
            
        except Exception as e:
            print(f"❌ 新增任務失敗: {e}")
            return False
    
    def get_next_task(self) -> Optional[QueuedTask]:
        """獲取下一個待執行的任務"""
        queue = self._load_queue()
        
        # 檢查是否有正在執行的任務
        running_tasks = [task for task in queue if task.status == TaskStatus.RUNNING]
        if running_tasks:
            return None  # 有任務正在執行，不能開始新任務
        
        # 找到第一個等待中的任務
        waiting_tasks = [task for task in queue if task.status == TaskStatus.WAITING]
        if waiting_tasks:
            # 按創建時間排序，返回最早的
            waiting_tasks.sort(key=lambda x: x.created_at)
            return waiting_tasks[0]
        
        return None
    
    def start_task(self, task_id: str) -> bool:
        """開始執行任務"""
        try:
            queue = self._load_queue()
            
            for task in queue:
                if task.task_id == task_id and task.status == TaskStatus.WAITING:
                    task.status = TaskStatus.RUNNING
                    task.started_at = time.time()
                    self._running_task_id = task_id
                    break
            else:
                return False
            
            self._save_queue(queue)
            print(f"🚀 開始執行任務: {task_id[:8]}...")
            return True
            
        except Exception as e:
            print(f"❌ 開始任務失敗: {e}")
            return False
    
    def complete_task(self, task_id: str, success: bool = True, error_message: str = None):
        """完成任務"""
        try:
            queue = self._load_queue()
            
            for task in queue:
                if task.task_id == task_id:
                    task.status = TaskStatus.COMPLETED if success else TaskStatus.ERROR
                    task.completed_at = time.time()
                    if error_message:
                        task.error_message = error_message
                    break
            
            self._running_task_id = None
            self._save_queue(queue)
            
            status_text = "完成" if success else f"失敗 ({error_message})"
            print(f"🏁 任務{status_text}: {task_id[:8]}...")
            
        except Exception as e:
            print(f"❌ 完成任務失敗: {e}")
    
    def cancel_task(self, task_id: str) -> bool:
        """取消任務（只能取消等待中的任務）"""
        try:
            queue = self._load_queue()
            
            for task in queue:
                if task.task_id == task_id:
                    if task.status == TaskStatus.WAITING:
                        task.status = TaskStatus.CANCELLED
                        task.completed_at = time.time()
                        self._save_queue(queue)
                        print(f"🚫 已取消任務: {task_id[:8]}...")
                        return True
                    else:
                        print(f"⚠️ 無法取消非等待中的任務: {task.status}")
                        return False
            
            print(f"⚠️ 找不到任務: {task_id[:8]}...")
            return False
            
        except Exception as e:
            print(f"❌ 取消任務失敗: {e}")
            return False
    
    def remove_task(self, task_id: str) -> bool:
        """移除任務（只能移除已完成/錯誤/取消的任務）"""
        try:
            queue = self._load_queue()
            
            for i, task in enumerate(queue):
                if task.task_id == task_id:
                    if task.status in [TaskStatus.COMPLETED, TaskStatus.ERROR, TaskStatus.CANCELLED]:
                        queue.pop(i)
                        self._save_queue(queue)
                        print(f"🗑️ 已移除任務: {task_id[:8]}...")
                        return True
                    else:
                        print(f"⚠️ 無法移除執行中的任務: {task.status}")
                        return False
            
            return False
            
        except Exception as e:
            print(f"❌ 移除任務失敗: {e}")
            return False
    
    def get_queue_status(self) -> Dict[str, Any]:
        """獲取佇列狀態"""
        queue = self._load_queue()
        
        status_counts = {
            "waiting": 0,
            "running": 0, 
            "completed": 0,
            "error": 0,
            "cancelled": 0
        }
        
        for task in queue:
            # 處理 status 可能是字串或 Enum 的情況
            status_value = task.status.value if hasattr(task.status, 'value') else task.status
            status_counts[status_value] += 1
        
        return {
            "total": len(queue),
            "waiting": status_counts["waiting"],
            "running": status_counts["running"],
            "completed": status_counts["completed"],
            "error": status_counts["error"],
            "cancelled": status_counts["cancelled"],
            "queue": queue
        }
    
    def get_current_running_task(self) -> Optional[QueuedTask]:
        """獲取當前執行中的任務"""
        queue = self._load_queue()
        for task in queue:
            if task.status == TaskStatus.RUNNING:
                return task
        return None
    
    def cleanup_old_tasks(self, hours: int = 24):
        """清理舊任務"""
        try:
            queue = self._load_queue()
            cutoff_time = time.time() - (hours * 3600)
            
            # 保留執行中和等待中的任務
            cleaned_queue = [
                task for task in queue 
                if (task.status in [TaskStatus.RUNNING, TaskStatus.WAITING] or 
                    task.created_at > cutoff_time)
            ]
            
            removed_count = len(queue) - len(cleaned_queue)
            if removed_count > 0:
                self._save_queue(cleaned_queue)
                print(f"🧹 已清理 {removed_count} 個舊任務")
            
            return removed_count
            
        except Exception as e:
            print(f"❌ 清理任務失敗: {e}")
            return 0

# 全域實例
_task_queue_manager = None

def get_task_queue_manager() -> TaskQueueManager:
    """獲取任務佇列管理器實例"""
    global _task_queue_manager
    if _task_queue_manager is None:
        _task_queue_manager = TaskQueueManager()
    return _task_queue_manager