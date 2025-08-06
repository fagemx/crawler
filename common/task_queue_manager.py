"""
任務佇列管理器 - 確保依序執行爬蟲任務
"""

import json
import asyncio
import os
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
    
    def get_next_waiting_task(self) -> Optional[QueuedTask]:
        """獲取下一個等待中的任務"""
        queue = self._load_queue()
        waiting_tasks = [task for task in queue if task.status == TaskStatus.WAITING]
        if waiting_tasks:
            # 按創建時間排序，返回最早的任務
            waiting_tasks.sort(key=lambda x: x.created_at)
            return waiting_tasks[0]
        return None
    
    def start_task(self, task_id: str) -> bool:
        """將任務標記為執行中"""
        try:
            queue = self._load_queue()
            for task in queue:
                if task.task_id == task_id and task.status == TaskStatus.WAITING:
                    task.status = TaskStatus.RUNNING
                    self._save_queue(queue)
                    print(f"▶️ 任務開始執行: {task.username} (ID: {task_id[:8]}...)")
                    return True
            return False
        except Exception as e:
            print(f"❌ 啟動任務失敗: {e}")
            return False
    
    def can_start_new_task(self) -> bool:
        """檢查是否可以啟動新任務（沒有執行中的任務）"""
        current_running = self.get_current_running_task()
        return current_running is None
    
    def try_auto_start_next_task(self) -> bool:
        """嘗試自動啟動下一個等待中的任務"""
        if not self.can_start_new_task():
            return False
            
        next_task = self.get_next_waiting_task()
        if next_task:
            return self.start_task(next_task.task_id)
        return False

    def get_current_running_task(self) -> Optional[QueuedTask]:
        """獲取當前真正執行中的任務"""
        queue = self._load_queue()
        for task in queue:
            if task.status == TaskStatus.RUNNING:
                # 檢查任務是否真的在執行中
                if self._is_task_actually_running(task):
                    return task
                else:
                    # 任務已停止但狀態沒更新，標記為失敗
                    self._mark_task_failed(task.task_id, "任務進程已停止")
        return None
    
    def _is_task_actually_running(self, task: QueuedTask) -> bool:
        """檢查任務是否真的在執行中（有活躍的進度更新）"""
        try:
            progress_file = f"temp_progress/playwright_progress_{task.task_id}.json"
            
            # 1. 檢查進度檔案是否存在
            if not os.path.exists(progress_file):
                print(f"🔍 任務 {task.task_id[:8]} 進度檔案不存在")
                return False
            
            # 2. 檢查檔案最後修改時間
            last_modified = os.path.getmtime(progress_file)
            current_time = time.time()
            time_diff = current_time - last_modified
            
            # 如果超過2分鐘沒更新，認為任務已停止
            MAX_IDLE_TIME = 120  # 2分鐘
            if time_diff > MAX_IDLE_TIME:
                print(f"🔍 任務 {task.task_id[:8]} 超過 {time_diff:.0f} 秒未更新，認為已停止")
                return False
            
            # 3. 檢查進度內容是否為完成或錯誤狀態
            try:
                with open(progress_file, 'r', encoding='utf-8') as f:
                    progress_data = json.load(f)
                    
                stage = progress_data.get("stage", "")
                # 如果階段是完成或錯誤，任務應該已結束
                if stage in ["completed", "error"]:
                    print(f"🔍 任務 {task.task_id[:8]} 進度顯示已完成/錯誤: {stage}")
                    return False
                    
                # 檢查是否有錯誤信息
                if progress_data.get("error"):
                    print(f"🔍 任務 {task.task_id[:8]} 進度檔案包含錯誤信息")
                    return False
                    
            except (json.JSONDecodeError, IOError):
                print(f"🔍 任務 {task.task_id[:8]} 進度檔案無法讀取")
                return False
            
            # 所有檢查都通過，任務真的在執行
            print(f"✅ 任務 {task.task_id[:8]} 確認執行中（{time_diff:.0f}秒前更新）")
            return True
            
        except Exception as e:
            print(f"❌ 檢查任務執行狀態失敗: {e}")
            return False
    
    def _mark_task_failed(self, task_id: str, error_message: str):
        """標記任務為失敗狀態"""
        try:
            queue = self._load_queue()
            for task in queue:
                if task.task_id == task_id:
                    task.status = TaskStatus.ERROR
                    task.error_message = error_message
                    break
            self._save_queue(queue)
            print(f"🔄 任務 {task_id[:8]} 已標記為失敗: {error_message}")
        except Exception as e:
            print(f"❌ 標記任務失敗時出錯: {e}")
    
    def cleanup_zombie_tasks(self):
        """清理殭屍任務 - 清理已停止但狀態未更新的 RUNNING 任務"""
        try:
            queue = self._load_queue()
            updated = False
            
            for task in queue:
                if task.status == TaskStatus.RUNNING:
                    # 使用詳細檢查判斷任務是否真的在執行
                    if not self._is_task_actually_running(task):
                        # 任務已停止，標記為失敗
                        task.status = TaskStatus.ERROR
                        task.error_message = task.error_message or "任務進程已停止或超時"
                        updated = True
                        print(f"🧹 清理殭屍任務: {task.username} (ID: {task.task_id[:8]}...)")
            
            if updated:
                self._save_queue(queue)
                print("✅ 殭屍任務清理完成")
                
        except Exception as e:
            print(f"❌ 清理殭屍任務失敗: {e}")
    
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