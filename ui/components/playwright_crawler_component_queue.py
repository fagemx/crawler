"""
Playwright 爬蟲組件 - 佇列版本
整合任務佇列管理，確保依序執行
"""

import streamlit as st
import httpx
import json
import os
import uuid
import tempfile
import threading
import time
import requests
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
import asyncio

from .playwright_utils import PlaywrightUtils
from .playwright_database_handler import PlaywrightDatabaseHandler
from .playwright_user_manager import PlaywrightUserManager
from .task_queue_component import get_task_queue_component, TaskQueueComponent
from common.task_queue_manager import get_task_queue_manager, TaskStatus

# 進度管理組件
try:
    from .progress_manager import ProgressManager
    from .task_recovery_component import TaskRecoveryComponent
    PROGRESS_MANAGER_AVAILABLE = True
except ImportError:
    PROGRESS_MANAGER_AVAILABLE = False
    print("⚠️ 進度管理器不可用，將使用基本功能")

class PlaywrightCrawlerComponentQueue:
    """Playwright 爬蟲組件 - 佇列版本"""
    
    def __init__(self):
        self.agent_url = "http://localhost:8006/v1/playwright/crawl"
        self.sse_url = "http://localhost:8000/stream"
        
        # 初始化子組件
        self.db_handler = PlaywrightDatabaseHandler()
        self.user_manager = PlaywrightUserManager()
        
        # 佇列管理組件
        self.queue_component = get_task_queue_component()
        self.queue_manager = get_task_queue_manager()
        
        # 初始化進度管理組件
        if PROGRESS_MANAGER_AVAILABLE:
            self.progress_manager = ProgressManager()
            self.task_recovery = TaskRecoveryComponent()
        else:
            self.progress_manager = None
            self.task_recovery = None
        
        # 使用統一的配置管理
        from common.config import get_auth_file_path
        self.auth_file_path = get_auth_file_path(from_project_root=True)
    
    def render(self):
        """主渲染方法"""
        st.header("🎭 Playwright 智能爬蟲 (佇列版)")
        
        # 顯示佇列資訊條
        self.queue_component.render_queue_info_bar()
        st.divider()
        
        # 檢查佇列狀態並自動處理
        self._auto_process_queue()
        
        # 根據當前狀態渲染對應頁面
        crawl_status = st.session_state.get('playwright_crawl_status', 'idle')
        
        if crawl_status == "idle":
            self._render_setup_with_queue()
        elif crawl_status == "queued":
            self._render_queued_status()
        elif crawl_status == "running":
            self._render_progress()
        elif crawl_status == "completed":
            self._render_results()
        elif crawl_status == "error":
            self._render_error()
        elif crawl_status == "task_manager":
            self._render_task_manager()
        elif crawl_status == "queue_manager":
            self._render_queue_manager()
    
    def _auto_process_queue(self):
        """自動處理佇列 - 檢查是否需要開始下一個任務"""
        # 如果當前沒有任務執行，檢查佇列
        if self.queue_component.is_queue_available():
            next_task = self.queue_component.check_and_start_next_task()
            if next_task:
                # 開始執行下一個任務
                st.session_state.playwright_task_id = next_task.task_id
                st.session_state.playwright_crawl_status = "running"
                
                # 發送實際的爬蟲請求
                self._start_crawl_from_queue_task(next_task)
                st.rerun()
    
    def _start_crawl_from_queue_task(self, task):
        """從佇列任務開始爬蟲"""
        try:
            # 準備爬蟲參數
            auth_content = self._load_auth_file()
            if not auth_content:
                self.queue_manager.complete_task(task.task_id, False, "認證檔案載入失敗")
                return
            
            # 發送爬蟲請求
            payload = {
                "username": task.username,
                "max_posts": task.max_posts,
                "mode": task.mode,
                "auth_json_content": auth_content,
                "task_id": task.task_id
            }
            
            # 使用背景執行緒發送請求
            thread = threading.Thread(
                target=self._send_crawl_request_background,
                args=(payload, task.task_id)
            )
            thread.daemon = True
            thread.start()
            
        except Exception as e:
            self.queue_manager.complete_task(task.task_id, False, str(e))
    
    def _send_crawl_request_background(self, payload, task_id):
        """背景執行緒發送爬蟲請求"""
        try:
            response = requests.post(self.agent_url, json=payload, timeout=30)
            if response.status_code != 200:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                self.queue_manager.complete_task(task_id, False, error_msg)
        except Exception as e:
            self.queue_manager.complete_task(task_id, False, str(e))
    
    def _render_setup_with_queue(self):
        """渲染設定頁面（包含佇列功能）"""
        # 佇列狀態概覽
        with st.expander("📋 佇列狀態", expanded=True):
            self.queue_component.render_queue_status()
        
        st.divider()
        
        # 原有的設定介面
        col_settings, col_stats = st.columns([1, 1])
        
        with col_settings:
            st.subheader("⚙️ 爬取設定")
            username = st.text_input(
                "目標帳號", 
                value="gvmonthly",
                help="輸入要爬取的 Threads 帳號名稱"
            )
            
            max_posts = st.number_input(
                "爬取數量", 
                min_value=1, 
                max_value=200, 
                value=20,
                help="要爬取的貼文數量"
            )
            
            mode = st.selectbox(
                "爬取模式",
                ["new", "hist"],
                index=0,
                help="new: 新貼文補足, hist: 歷史回溯"
            )
            
            # 檢查認證檔案
            auth_available = os.path.exists(self.auth_file_path)
            if auth_available:
                st.success("✅ 認證檔案已就緒")
            else:
                st.error("❌ 認證檔案不存在")
                st.info("請先執行: `python agents/playwright_crawler/save_auth.py`")
            
            # 佇列啟動按鈕
            col_start, col_queue = st.columns(2)
            
            with col_start:
                start_disabled = not auth_available or not username.strip()
                if st.button(
                    "🚀 加入佇列", 
                    disabled=start_disabled,
                    help="將任務加入佇列等待執行",
                    use_container_width=True
                ):
                    self._add_task_to_queue(username, max_posts, mode)
            
            with col_queue:
                if st.button("📋 佇列管理", use_container_width=True):
                    st.session_state.playwright_crawl_status = "queue_manager"
                    st.rerun()
        
        with col_stats:
            # 統計資訊
            self._render_stats()
    
    def _add_task_to_queue(self, username: str, max_posts: int, mode: str):
        """新增任務到佇列"""
        try:
            # 生成新的任務 ID
            task_id = str(uuid.uuid4())
            
            # 加入佇列
            if self.queue_manager.add_task(task_id, username, max_posts, mode):
                st.session_state.playwright_task_id = task_id
                
                # 檢查佇列位置
                position = self.queue_component.get_queue_position(task_id)
                if position == 1:
                    st.success("✅ 任務已加入佇列，即將開始執行")
                    st.session_state.playwright_crawl_status = "queued"
                else:
                    st.success(f"✅ 任務已加入佇列，排隊位置: #{position}")
                    st.session_state.playwright_crawl_status = "queued"
                
                st.rerun()
            else:
                st.error("❌ 加入佇列失敗")
                
        except Exception as e:
            st.error(f"❌ 發生錯誤: {e}")
    
    def _render_queued_status(self):
        """渲染佇列等待狀態"""
        task_id = st.session_state.get('playwright_task_id')
        if not task_id:
            st.session_state.playwright_crawl_status = "idle"
            st.rerun()
            return
        
        st.subheader("⏳ 任務在佇列中")
        
        # 獲取任務資訊
        status = self.queue_manager.get_queue_status()
        current_task = None
        for task in status["queue"]:
            if task.task_id == task_id:
                current_task = task
                break
        
        if not current_task:
            st.error("❌ 找不到任務")
            st.session_state.playwright_crawl_status = "idle"
            st.rerun()
            return
        
        # 顯示任務資訊
        col1, col2 = st.columns(2)
        with col1:
            st.info(f"🎯 目標: @{current_task.username}")
            st.info(f"📊 數量: {current_task.max_posts} 篇貼文")
            st.info(f"🔄 模式: {current_task.mode}")
        
        with col2:
            st.info(f"🆔 任務 ID: {task_id[:8]}...")
            st.info(f"📅 創建時間: {datetime.fromtimestamp(current_task.created_at).strftime('%H:%M:%S')}")
            
            if current_task.status == TaskStatus.WAITING:
                position = self.queue_component.get_queue_position(task_id)
                if position > 0:
                    st.warning(f"⏳ 佇列位置: #{position}")
                else:
                    st.info("🔄 準備執行中...")
            elif current_task.status == TaskStatus.RUNNING:
                st.success("🚀 正在執行中...")
                st.session_state.playwright_crawl_status = "running"
                st.rerun()
        
        # 控制按鈕
        col_cancel, col_queue, col_back = st.columns(3)
        
        with col_cancel:
            if current_task.status == TaskStatus.WAITING:
                if st.button("🚫 取消任務"):
                    if self.queue_manager.cancel_task(task_id):
                        st.success("✅ 任務已取消")
                        st.session_state.playwright_crawl_status = "idle"
                        st.rerun()
                    else:
                        st.error("❌ 取消失敗")
        
        with col_queue:
            if st.button("📋 佇列管理"):
                st.session_state.playwright_crawl_status = "queue_manager"
                st.rerun()
        
        with col_back:
            if st.button("🔙 返回設定"):
                st.session_state.playwright_crawl_status = "idle"
                st.rerun()
        
        # 自動重新整理
        time.sleep(1)
        st.rerun()
    
    def _render_queue_manager(self):
        """渲染佇列管理頁面"""
        st.header("📋 任務佇列管理")
        
        # 返回按鈕
        col_back, col_refresh = st.columns([1, 1])
        with col_back:
            if st.button("← 返回設定", key="back_to_setup"):
                st.session_state.playwright_crawl_status = "idle"
                st.rerun()
        
        with col_refresh:
            if st.button("🔄 重新整理", key="refresh_queue"):
                st.rerun()
        
        st.divider()
        
        # 佇列狀態
        self.queue_component.render_queue_status()
        st.divider()
        
        # 佇列列表
        self.queue_component.render_queue_list()
        st.divider()
        
        # 佇列控制
        self.queue_component.render_queue_controls()
    
    def _render_progress(self):
        """渲染執行進度"""
        st.subheader("🔄 爬蟲執行中")
        
        task_id = st.session_state.get('playwright_task_id')
        if not task_id:
            st.error("❌ 找不到任務 ID")
            st.session_state.playwright_crawl_status = "idle"
            st.rerun()
            return
        
        # 檢查任務是否還在執行
        running_task = self.queue_manager.get_current_running_task()
        if not running_task or running_task.task_id != task_id:
            st.warning("⚠️ 任務已不在執行中")
            st.session_state.playwright_crawl_status = "idle"
            st.rerun()
            return
        
        # 顯示進度（使用現有的進度監控邏輯）
        if self.progress_manager:
            progress_data = self.progress_manager.get_progress(task_id, prefer_redis=True)
            
            if progress_data:
                stage = progress_data.get("stage", "")
                progress = progress_data.get("progress", 0.0)
                current_work = progress_data.get("current_work", "")
                
                # 顯示進度
                st.progress(progress / 100.0, text=f"{progress:.1f}%")
                if current_work:
                    st.info(f"🔄 {current_work}")
                
                # 檢查完成狀態
                if stage in ("completed", "api_completed"):
                    self.queue_manager.complete_task(task_id, True)
                    st.session_state.playwright_crawl_status = "completed"
                    st.session_state.playwright_final_data = progress_data.get("final_data", {})
                    st.rerun()
                elif stage == "error":
                    error_msg = progress_data.get("error", "未知錯誤")
                    self.queue_manager.complete_task(task_id, False, error_msg)
                    st.session_state.playwright_crawl_status = "error"
                    st.session_state.playwright_error_msg = error_msg
                    st.rerun()
            else:
                st.info("⏳ 等待進度資訊...")
        
        # 控制按鈕
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("📋 佇列管理"):
                st.session_state.playwright_crawl_status = "queue_manager"
                st.rerun()
        
        with col2:
            if st.button("🔙 返回設定"):
                st.session_state.playwright_crawl_status = "idle"
                st.rerun()
        
        with col3:
            if st.button("🗑️ 停止監控"):
                st.session_state.playwright_crawl_status = "idle"
                st.info("已停止監控，任務仍在後台運行")
                time.sleep(2)
                st.rerun()
        
        # 自動重新整理
        time.sleep(2)
        st.rerun()
    
    def _render_results(self):
        """渲染結果頁面"""
        st.subheader("✅ 爬取完成")
        
        task_id = st.session_state.get('playwright_task_id')
        final_data = st.session_state.get('playwright_final_data', {})
        
        if not final_data:
            st.warning("沒有爬取到數據")
        else:
            # 顯示結果統計
            results = final_data.get('results', [])
            st.success(f"✅ 成功爬取 {len(results)} 篇貼文")
            
            # 顯示詳細結果
            with st.expander("📊 詳細結果", expanded=False):
                st.json(final_data)
        
        # 控制按鈕
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🔙 返回設定"):
                st.session_state.playwright_crawl_status = "idle"
                st.rerun()
        
        with col2:
            if st.button("📋 佇列管理"):
                st.session_state.playwright_crawl_status = "queue_manager"
                st.rerun()
        
        with col3:
            if st.button("🔄 開始新任務"):
                st.session_state.playwright_crawl_status = "idle"
                st.rerun()
    
    def _render_error(self):
        """渲染錯誤頁面"""
        st.subheader("❌ 執行錯誤")
        
        error_msg = st.session_state.get('playwright_error_msg', '未知錯誤')
        st.error(f"錯誤訊息: {error_msg}")
        
        # 控制按鈕
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🔙 返回設定"):
                st.session_state.playwright_crawl_status = "idle"
                st.rerun()
        
        with col2:
            if st.button("📋 佇列管理"):
                st.session_state.playwright_crawl_status = "queue_manager"
                st.rerun()
    
    def _render_task_manager(self):
        """渲染任務管理頁面（舊版相容）"""
        if self.task_recovery:
            self.task_recovery.render_task_list()
        else:
            st.error("❌ 任務管理功能不可用")
    
    def _render_stats(self):
        """渲染統計資訊"""
        st.subheader("📊 統計資訊")
        try:
            stats = self.db_handler.get_user_stats()
            if stats:
                for stat in stats[:5]:  # 顯示前5名
                    st.write(f"**{stat['username']}**: {stat['post_count']} 篇")
            else:
                st.info("暫無資料")
        except Exception as e:
            st.error(f"載入統計失敗: {e}")
    
    def _load_auth_file(self) -> Optional[Dict]:
        """載入認證檔案"""
        try:
            if os.path.exists(self.auth_file_path):
                with open(self.auth_file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"載入認證檔案失敗: {e}")
        return None