"""
任務佇列 UI 組件 - 顯示和管理爬蟲任務佇列
"""

import streamlit as st
import time
from typing import Optional
from datetime import datetime

from common.task_queue_manager import get_task_queue_manager, TaskStatus, QueuedTask

class TaskQueueComponent:
    """任務佇列 UI 組件"""
    
    def __init__(self):
        self.queue_manager = get_task_queue_manager()
    
    def render_queue_status(self):
        """渲染佇列狀態概覽"""
        status = self.queue_manager.get_queue_status()
        
        if status["total"] == 0:
            st.info("🔄 佇列為空，可以開始新任務")
            return
        
        # 佇列統計
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("等待中", status["waiting"], help="⏳")
        with col2:
            st.metric("執行中", status["running"], help="🔄")
        with col3:
            st.metric("已完成", status["completed"], help="✅")
        with col4:
            st.metric("錯誤", status["error"], help="❌")
        with col5:
            st.metric("已取消", status["cancelled"], help="🚫")
    
    def render_queue_list(self):
        """渲染佇列詳細列表"""
        status = self.queue_manager.get_queue_status()
        queue = status.get("queue", [])
        
        if not queue:
            return
        
        st.subheader("📋 任務佇列")
        
        # 依狀態分組顯示
        self._render_task_group(queue, [TaskStatus.RUNNING], "🔄 執行中", expanded=True)
        self._render_task_group(queue, [TaskStatus.WAITING], "⏳ 等待中", expanded=True)
        self._render_task_group(queue, [TaskStatus.COMPLETED], "✅ 已完成", expanded=False)
        self._render_task_group(queue, [TaskStatus.ERROR, TaskStatus.CANCELLED], "❌ 錯誤/取消", expanded=False)
    
    def _render_task_group(self, queue: list, statuses: list, title: str, expanded: bool = True):
        """渲染任務群組"""
        tasks = [task for task in queue if task.status in statuses]
        
        if not tasks:
            return
        
        with st.expander(f"{title} ({len(tasks)})", expanded=expanded):
            for i, task in enumerate(tasks):
                self._render_task_card(task, i)
    
    def _render_task_card(self, task: QueuedTask, index: int):
        """渲染單個任務卡片"""
        with st.container():
            col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
            
            with col1:
                st.write(f"**@{task.username}**")
                st.caption(f"任務 ID: `{task.task_id[:8]}...`")
                st.caption(f"模式: {task.mode} | 貼文數: {task.max_posts}")
            
            with col2:
                st.write(task.display_status)
                
                # 顯示進度條（僅執行中）
                if task.status == TaskStatus.RUNNING:
                    # 模擬進度（實際應該從 progress 檔案讀取）
                    progress_placeholder = st.empty()
                    progress_placeholder.progress(0.5, text="執行中...")
            
            with col3:
                # 時間資訊
                if task.status == TaskStatus.WAITING:
                    st.write(f"⏰ 等待: {task.wait_time}")
                elif task.status == TaskStatus.RUNNING:
                    st.write(f"⏱️ 執行: {task.execution_time}")
                elif task.status in [TaskStatus.COMPLETED, TaskStatus.ERROR, TaskStatus.CANCELLED]:
                    st.write(f"⏱️ 總計: {task.execution_time}")
                
                # 創建時間
                created_time = datetime.fromtimestamp(task.created_at)
                st.caption(f"創建: {created_time.strftime('%H:%M:%S')}")
            
            with col4:
                # 操作按鈕
                if task.status == TaskStatus.WAITING:
                    if st.button("🚫 取消", key=f"cancel_task_{task.task_id}"):
                        if self.queue_manager.cancel_task(task.task_id):
                            st.success(f"✅ 已取消任務 {task.task_id[:8]}...")
                            st.rerun()
                        else:
                            st.error("❌ 取消失敗")
                
                elif task.status == TaskStatus.RUNNING:
                    st.write("🔄 執行中")
                    st.caption("無法取消")
                
                elif task.status in [TaskStatus.COMPLETED, TaskStatus.ERROR, TaskStatus.CANCELLED]:
                    if st.button("🗑️ 移除", key=f"remove_task_{task.task_id}"):
                        if self.queue_manager.remove_task(task.task_id):
                            st.success(f"✅ 已移除任務 {task.task_id[:8]}...")
                            st.rerun()
                        else:
                            st.error("❌ 移除失敗")
            
            # 錯誤訊息顯示
            if task.status == TaskStatus.ERROR and task.error_message:
                st.error(f"❌ 錯誤: {task.error_message}")
            
            st.divider()
    
    def render_queue_controls(self):
        """渲染佇列控制按鈕"""
        st.subheader("🛠️ 佇列管理")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🔄 重新整理"):
                st.rerun()
        
        with col2:
            if st.button("🧹 清理舊任務"):
                removed_count = self.queue_manager.cleanup_old_tasks(24)
                if removed_count > 0:
                    st.success(f"✅ 已清理 {removed_count} 個舊任務")
                else:
                    st.info("ℹ️ 沒有需要清理的任務")
                st.rerun()
        
        with col3:
            if st.button("📊 佇列統計"):
                status = self.queue_manager.get_queue_status()
                st.json(status)
    
    def check_and_start_next_task(self) -> Optional[QueuedTask]:
        """檢查並開始下一個任務"""
        next_task = self.queue_manager.get_next_task()
        if next_task:
            if self.queue_manager.start_task(next_task.task_id):
                return next_task
        return None
    
    def is_queue_available(self) -> bool:
        """檢查佇列是否可用（沒有任務執行中）"""
        running_task = self.queue_manager.get_current_running_task()
        return running_task is None
    
    def get_queue_position(self, task_id: str) -> int:
        """獲取任務在佇列中的位置"""
        status = self.queue_manager.get_queue_status()
        waiting_tasks = [task for task in status["queue"] if task.status == TaskStatus.WAITING]
        waiting_tasks.sort(key=lambda x: x.created_at)
        
        for i, task in enumerate(waiting_tasks):
            if task.task_id == task_id:
                return i + 1  # 位置從 1 開始
        
        return -1  # 不在等待佇列中
    
    def render_queue_info_bar(self):
        """渲染佇列資訊條（在頁面頂部顯示）"""
        running_task = self.queue_manager.get_current_running_task()
        status = self.queue_manager.get_queue_status()
        
        if running_task:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.info(f"🔄 正在執行: @{running_task.username} (ID: {running_task.task_id[:8]}...)")
            with col2:
                if status["waiting"] > 0:
                    st.info(f"⏳ 等待中: {status['waiting']} 個任務")
        elif status["waiting"] > 0:
            st.info(f"⏳ 佇列中有 {status['waiting']} 個任務等待執行")
        elif status["total"] == 0:
            st.success("✅ 佇列為空，可以開始新任務")

# 全域實例
_task_queue_component = None

def get_task_queue_component() -> TaskQueueComponent:
    """獲取任務佇列組件實例"""
    global _task_queue_component
    if _task_queue_component is None:
        _task_queue_component = TaskQueueComponent()
    return _task_queue_component