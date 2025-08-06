"""
任務恢復組件 - 為用戶提供背景任務恢復查看功能
"""

import streamlit as st
import time
from typing import Optional
from .progress_manager import ProgressManager, TaskInfo

class TaskRecoveryComponent:
    """任務恢復組件"""
    
    def __init__(self):
        self.progress_manager = ProgressManager()
    
    def render_task_list(self):
        """渲染任務列表"""
        st.subheader("📋 任務管理")
        
        # 任務摘要
        summary = self.progress_manager.get_task_summary()
        
        if summary["total"] == 0:
            st.info("目前沒有任何任務記錄")
            return
        
        # 顯示摘要統計
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("總任務", summary["total"])
        with col2:
            st.metric("執行中", summary["running"], help="🔄")
        with col3:
            st.metric("已完成", summary["completed"], help="✅")
        with col4:
            st.metric("錯誤", summary["error"], help="❌")
        
        st.divider()
        
        # 獲取任務列表
        tasks = self.progress_manager.list_active_tasks()
        
        if not tasks:
            st.info("沒有找到任務")
            return
        
        # 顯示任務列表
        for i, task in enumerate(tasks):
            self._render_task_card(task, i)
    
    def _render_task_card(self, task: TaskInfo, index: int):
        """渲染單個任務卡片"""
        with st.container():
            col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
            
            with col1:
                st.write(f"**@{task.username}**")
                # 顯示完整的任務 ID，但用可複製的格式
                if len(task.task_id) > 16:
                    display_id = f"{task.task_id[:8]}...{task.task_id[-8:]}"
                else:
                    display_id = task.task_id
                st.caption(f"任務 ID: `{display_id}`")
                
                # 如果是真實 UUID 格式，提供完整 ID 的可複製版本
                if len(task.task_id) > 20:
                    with st.expander("完整 ID", expanded=False):
                        st.code(task.task_id, language=None)
            
            with col2:
                st.write(task.display_status)
                if task.progress > 0:
                    st.progress(task.progress / 100.0, text=f"{task.progress:.1f}%")
                else:
                    st.progress(0.0, text="0.0%")
            
            with col3:
                # 改善時間顯示（加入錯誤處理）
                if task.start_time:
                    try:
                        # 檢查時間戳是否合理（不能是負數或過大的值）
                        current_time = time.time()
                        if task.start_time > 0 and task.start_time <= current_time and (current_time - task.start_time) < 365 * 24 * 3600:  # 不超過一年
                            st.write(f"⏱️ {task.elapsed_time}")
                            # 顯示更詳細的時間信息
                            import datetime
                            start_dt = datetime.datetime.fromtimestamp(task.start_time)
                            st.caption(f"開始: {start_dt.strftime('%H:%M:%S')}")
                        else:
                            st.write("⏱️ 時間無效")
                            st.caption(f"無效時間戳: {task.start_time}")
                    except (ValueError, OSError, OverflowError) as e:
                        st.write("⏱️ 時間解析錯誤")
                        st.caption(f"錯誤: {str(e)}")
                else:
                    st.write("⏱️ 時間未知")
                
                # 改善階段顯示
                stage_display = task.stage
                if len(stage_display) > 20:
                    stage_display = stage_display[:17] + "..."
                st.caption(f"階段: {stage_display}")
            
            with col4:
                # 主要操作按鈕
                if task.status == "running":
                    if st.button("👁️ 查看", key=f"view_task_{index}"):
                        self._recover_task(task.task_id)
                elif task.status == "completed":
                    if st.button("📊 結果", key=f"result_task_{index}"):
                        self._show_task_results(task.task_id)
                elif task.status == "error":
                    if st.button("❌ 錯誤", key=f"error_task_{index}"):
                        st.error(f"錯誤詳情: {task.error or 'Unknown'}")
                else:
                    st.write("-")
                
                # 刪除按鈕
                if st.button("🗑️ 刪除", key=f"delete_task_{index}", type="secondary"):
                    if self._delete_single_task(task.task_id):
                        st.success(f"✅ 已刪除任務 {task.task_id[:8]}...")
                        st.rerun()
                    else:
                        st.error("❌ 刪除失敗")
            
            # 錯誤信息顯示
            if task.error:
                st.error(f"❌ {task.error}")
            
            st.divider()
    
    def _recover_task(self, task_id: str):
        """恢復查看任務"""
        # 設定 session state 來恢復任務
        st.session_state.playwright_task_id = task_id
        st.session_state.playwright_progress_file = str(
            self.progress_manager.temp_progress_dir / f"playwright_progress_{task_id}.json"
        )
        st.session_state.playwright_crawl_status = "running"
        st.session_state.recovered_from_background = True
        
        st.success(f"✅ 已恢復任務 {task_id[:8]}...")
        time.sleep(1)
        st.rerun()
    
    def _show_task_results(self, task_id: str):
        """顯示任務結果"""
        progress_data = self.progress_manager.get_progress(task_id, prefer_redis=True)
        final_data = progress_data.get("final_data", {})
        
        if final_data:
            st.session_state.playwright_final_data = final_data
            st.session_state.playwright_crawl_status = "completed"
            st.session_state.playwright_task_id = task_id
            st.rerun()
        else:
            st.error("無法載入任務結果")
    
    def render_task_monitor(self, task_id: str):
        """渲染任務監控（用於恢復的任務）"""
        st.info("📡 這是一個從背景恢復的任務")
        
        # 顯示恢復提示
        col1, col2 = st.columns([3, 1])
        with col1:
            st.caption(f"任務 ID: {task_id}")
        with col2:
            if st.button("🔄 重新整理"):
                st.rerun()
        
        # 從 Redis 獲取最新進度
        progress_data = self.progress_manager.get_progress(task_id, prefer_redis=True)
        
        if not progress_data:
            st.warning("⚠️ 無法從 Redis 取得任務進度，任務可能已經結束")
            if st.button("返回任務列表"):
                st.session_state.playwright_crawl_status = "idle"
                st.rerun()
            return False
        
        # 更新 session state
        st.session_state.playwright_progress = progress_data.get("progress", 0.0)
        st.session_state.playwright_current_work = progress_data.get("current_work", "")
        
        # 檢查任務狀態
        stage = progress_data.get("stage", "")
        if stage in ("completed", "api_completed"):
            st.session_state.playwright_crawl_status = "completed"
            st.session_state.playwright_final_data = progress_data.get("final_data", {})
            st.rerun()
        elif stage == "error":
            st.session_state.playwright_crawl_status = "error"
            st.session_state.playwright_error_msg = progress_data.get("error", "未知錯誤")
            st.rerun()
        
        return True
    
    def render_cleanup_controls(self):
        """渲染清理控制"""
        st.subheader("🧹 任務清理")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("清理 24 小時前的任務"):
                self.progress_manager.cleanup_old_tasks(24)
                st.success("✅ 已清理舊任務")
                st.rerun()
        
        with col2:
            if st.button("清理所有已完成任務"):
                cleaned_count = self._cleanup_completed_tasks()
                st.success(f"✅ 已清理 {cleaned_count} 個完成任務")
                st.rerun()
    
    def _cleanup_completed_tasks(self):
        """清理所有已完成的任務"""
        tasks = self.progress_manager.list_active_tasks()
        cleaned_count = 0
        
        for task in tasks:
            if task.status in ("completed", "error"):
                if self._delete_single_task(task.task_id):
                    cleaned_count += 1
        
        return cleaned_count
    
    def _delete_single_task(self, task_id: str) -> bool:
        """刪除單個任務（同時清理 Redis 和本地文件）"""
        success = True
        
        try:
            # 1. 清理 Redis
            from common.redis_client import get_redis_client
            redis_client = get_redis_client()
            redis_client.redis.delete(f"task:{task_id}")
            
            # 2. 清理本地進度文件（嘗試多種可能的文件名格式）
            possible_files = [
                self.progress_manager.temp_progress_dir / f"{task_id}.json",
                self.progress_manager.temp_progress_dir / f"playwright_progress_{task_id}.json",
                self.progress_manager.temp_progress_dir / f"playwright_crawl_{task_id}.json"
            ]
            
            for progress_file in possible_files:
                if progress_file.exists():
                    progress_file.unlink()
            
        except Exception as e:
            print(f"❌ 刪除任務 {task_id} 失敗: {e}")
            success = False
        
        return success