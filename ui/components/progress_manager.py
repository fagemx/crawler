"""
進度管理器 - 為 playwright_crawler_component_v2.py 提供雙軌進度支援
支援檔案進度（前台）和 Redis 進度（背景任務）
"""

import json
import time
from typing import Dict, List, Optional, Any, Union
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timezone

@dataclass
class TaskInfo:
    """任務資訊"""
    task_id: str
    username: str
    stage: str
    progress: float
    start_time: Optional[float] = None
    last_update: Optional[float] = None
    status: str = "running"
    error: Optional[str] = None
    
    @property
    def elapsed_time(self) -> str:
        """取得執行時間（加入錯誤處理）"""
        if not self.start_time:
            return "未知"
        
        try:
            current_time = time.time()
            
            # 檢查時間戳是否合理
            if self.start_time <= 0:
                return "時間戳無效"
            
            if self.start_time > current_time:
                return "未來時間"
            
            elapsed = current_time - self.start_time
            
            # 檢查是否超過合理範圍（比如一年）
            if elapsed > 365 * 24 * 3600:
                return "時間過長"
            
            if elapsed < 0:
                return "負時間"
            
            # 正常計算
            if elapsed < 60:
                return f"{elapsed:.0f}秒"
            elif elapsed < 3600:
                return f"{elapsed/60:.1f}分鐘"
            else:
                return f"{elapsed/3600:.1f}小時"
                
        except (ValueError, OverflowError) as e:
            return f"計算錯誤: {str(e)}"
    
    @property
    def display_status(self) -> str:
        """顯示狀態"""
        status_map = {
            "running": "🔄 執行中",
            "completed": "✅ 已完成", 
            "error": "❌ 錯誤",
            "paused": "⏸️ 暫停"
        }
        return status_map.get(self.status, f"❓ {self.status}")

class ProgressManager:
    """進度管理器 - 雙軌進度支援"""
    
    def __init__(self):
        self.temp_progress_dir = Path("temp_progress")
        self.temp_progress_dir.mkdir(exist_ok=True)
        
    def get_redis_client(self):
        """取得 Redis 客戶端（延遲載入）"""
        try:
            from common.redis_client import get_redis_client
            return get_redis_client()
        except Exception:
            return None
    
    def read_file_progress(self, task_id: str) -> Dict[str, Any]:
        """從檔案讀取進度"""
        progress_file = self.temp_progress_dir / f"playwright_progress_{task_id}.json"
        if not progress_file.exists():
            return {}
        
        try:
            with progress_file.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    
    def read_redis_progress(self, task_id: str) -> Dict[str, Any]:
        """從 Redis 讀取進度"""
        redis_client = self.get_redis_client()
        if not redis_client:
            return {}
        
        try:
            return redis_client.get_task_status(task_id) or {}
        except Exception:
            return {}
    
    def get_progress(self, task_id: str, prefer_redis: bool = False) -> Dict[str, Any]:
        """
        混合進度讀取：優先檔案，降級 Redis
        
        Args:
            task_id: 任務 ID
            prefer_redis: 是否優先使用 Redis
        """
        if prefer_redis:
            # 優先 Redis（背景任務恢復）
            redis_data = self.read_redis_progress(task_id)
            if redis_data:
                return redis_data
            return self.read_file_progress(task_id)
        else:
            # 優先檔案（正常前台）
            file_data = self.read_file_progress(task_id)
            if file_data:
                return file_data
            return self.read_redis_progress(task_id)
    
    def write_progress(self, task_id: str, data: Dict[str, Any], write_both: bool = True):
        """
        寫入進度到檔案和/或 Redis
        
        Args:
            task_id: 任務 ID
            data: 進度資料
            write_both: 是否同時寫入檔案和 Redis
        """
        # 1. 寫入檔案（保持原有機制）
        progress_file = self.temp_progress_dir / f"playwright_progress_{task_id}.json"
        
        try:
            # 讀取現有資料
            old_data = {}
            if progress_file.exists():
                with progress_file.open("r", encoding="utf-8") as f:
                    old_data = json.load(f)
            
            # 合併並寫入
            old_data.update(data)
            with progress_file.open("w", encoding="utf-8") as f:
                json.dump(old_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ 檔案進度寫入失敗: {e}")
        
        # 2. 寫入 Redis（新增功能）
        if write_both:
            redis_client = self.get_redis_client()
            if redis_client:
                try:
                    redis_client.set_task_status(task_id, data)
                except Exception as e:
                    print(f"⚠️ Redis 進度寫入失敗: {e}")
    
    def list_active_tasks(self) -> List[TaskInfo]:
        """列出所有活躍任務"""
        tasks = []
        
        # 1. 從檔案掃描
        file_tasks = self._scan_file_tasks()
        
        # 2. 從 Redis 掃描
        redis_tasks = self._scan_redis_tasks()
        
        # 3. 合併（檔案優先，Redis 補充）
        all_task_ids = set()
        task_dict = {}
        
        for task in file_tasks:
            all_task_ids.add(task.task_id)
            task_dict[task.task_id] = task
        
        for task in redis_tasks:
            if task.task_id not in all_task_ids:
                all_task_ids.add(task.task_id)
                task_dict[task.task_id] = task
        
        # 按最後更新時間排序
        tasks = list(task_dict.values())
        tasks.sort(key=lambda x: x.last_update or 0, reverse=True)
        
        return tasks
    
    def _scan_file_tasks(self) -> List[TaskInfo]:
        """掃描檔案任務"""
        tasks = []
        
        for progress_file in self.temp_progress_dir.glob("playwright_progress_*.json"):
            try:
                task_id = progress_file.stem.replace("playwright_progress_", "")
                data = self.read_file_progress(task_id)
                
                if data:
                    task = self._data_to_task_info(task_id, data)
                    if task:
                        tasks.append(task)
            except Exception:
                continue
        
        return tasks
    
    def _scan_redis_tasks(self) -> List[TaskInfo]:
        """掃描 Redis 任務"""
        tasks = []
        redis_client = self.get_redis_client()
        
        if not redis_client:
            return tasks
        
        try:
            # 嘗試掃描 Redis 中的任務鍵
            import redis
            r = redis.Redis.from_url("redis://localhost:6379/0")  # 直接連接掃描
            task_keys = r.keys("task:*")
            
            for key in task_keys:
                try:
                    task_id = key.decode().replace("task:", "")
                    data = self.read_redis_progress(task_id)
                    
                    if data:
                        task = self._data_to_task_info(task_id, data)
                        if task:
                            tasks.append(task)
                except Exception:
                    continue
                    
        except Exception:
            pass
        
        return tasks
    
    def _data_to_task_info(self, task_id: str, data: Dict[str, Any]) -> Optional[TaskInfo]:
        """將資料轉換為 TaskInfo"""
        try:
            # 判斷任務狀態
            stage = data.get("stage", "unknown")
            if stage == "completed" or "completed" in stage:
                status = "completed"
            elif stage == "error" or data.get("error"):
                status = "error"
            elif "start" in stage or data.get("progress", 0) > 0:
                status = "running"
            else:
                status = "pending"
            
            # 處理開始時間（改善邏輯）
            start_time = data.get("start_time")
            current_time = time.time()
            
            if not start_time or start_time <= 0:
                # 如果沒有有效的 start_time，嘗試從 timestamp 推算
                timestamp = data.get("timestamp")
                if timestamp and timestamp > 0:
                    # 如果 timestamp 是合理的（過去一年內），使用它
                    if timestamp <= current_time and (current_time - timestamp) < 365 * 24 * 3600:
                        start_time = timestamp
                    else:
                        # 否則設為當前時間（表示剛開始）
                        start_time = current_time
                else:
                    # 都沒有的話，設為 None
                    start_time = None
            
            # 驗證 start_time 是否合理
            if start_time:
                if start_time > current_time or start_time <= 0 or (current_time - start_time) > 365 * 24 * 3600:
                    # 不合理的時間戳，設為 None
                    start_time = None
            
            return TaskInfo(
                task_id=task_id,
                username=data.get("username", "unknown"),
                stage=stage,
                progress=float(data.get("progress", 0.0)),
                start_time=start_time,
                last_update=data.get("timestamp") or time.time(),
                status=status,
                error=data.get("error")
            )
        except Exception as e:
            print(f"⚠️ 轉換 TaskInfo 失敗: {e}")
            return None
    
    def cleanup_old_tasks(self, max_age_hours: int = 24):
        """清理舊任務"""
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        # 清理檔案
        for progress_file in self.temp_progress_dir.glob("playwright_progress_*.json"):
            try:
                if current_time - progress_file.stat().st_mtime > max_age_seconds:
                    progress_file.unlink()
            except Exception:
                pass
    
    def get_task_summary(self) -> Dict[str, int]:
        """取得任務摘要統計"""
        tasks = self.list_active_tasks()
        
        summary = {
            "total": len(tasks),
            "running": 0,
            "completed": 0,
            "error": 0,
            "paused": 0
        }
        
        for task in tasks:
            summary[task.status] = summary.get(task.status, 0) + 1
        
        return summary