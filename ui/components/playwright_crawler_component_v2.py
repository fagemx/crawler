"""
Playwright 爬蟲組件 - V2 版本
採用與 crawler_component_refactored.py 相同的檔案讀寫架構
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
from .playwright_data_export_handler import PlaywrightDataExportHandler

# 新增進度管理組件
try:
    from .progress_manager import ProgressManager
    from .task_recovery_component import TaskRecoveryComponent
    PROGRESS_MANAGER_AVAILABLE = True
except ImportError:
    PROGRESS_MANAGER_AVAILABLE = False
    print("⚠️ 進度管理器不可用，將使用基本功能")

# 新增佇列管理組件
try:
    from .task_queue_component import get_task_queue_component
    from common.task_queue_manager import get_task_queue_manager, TaskStatus
    QUEUE_MANAGER_AVAILABLE = True
except ImportError:
    QUEUE_MANAGER_AVAILABLE = False
    print("⚠️ 佇列管理器不可用，將使用基本功能")

class PlaywrightCrawlerComponentV2:
    def __init__(self):
        self.agent_url = "http://localhost:8006/v1/playwright/crawl"
        self.sse_url = "http://localhost:8000/stream"
        
        # 初始化子組件
        self.db_handler = PlaywrightDatabaseHandler()
        self.user_manager = PlaywrightUserManager()
        self.export_handler = PlaywrightDataExportHandler(self.db_handler)
        
        # 初始化進度管理組件
        if PROGRESS_MANAGER_AVAILABLE:
            self.progress_manager = ProgressManager()
            self.task_recovery = TaskRecoveryComponent()
        else:
            self.progress_manager = None
            self.task_recovery = None
        
        # 初始化佇列管理組件
        if QUEUE_MANAGER_AVAILABLE:
            self.queue_component = get_task_queue_component()
            self.queue_manager = get_task_queue_manager()
        else:
            self.queue_component = None
            self.queue_manager = None
        
        # 使用統一的配置管理
        from common.config import get_auth_file_path
        self.auth_file_path = get_auth_file_path(from_project_root=True)
    
    # ---------- 1. 進度檔案讀寫工具 ----------
    def _write_progress(self, path, data: Dict[str, Any]):
        """
        線程安全寫入進度（增強版）：
        - 使用 tempfile + shutil.move 實現原子寫入，避免讀取到不完整的檔案
        - 同時寫入 Redis（如果可用）支援背景任務監控
        """
        # 處理 Path 對象
        path_str = str(path)
        old: Dict[str, Any] = {}
        if os.path.exists(path_str):
            try:
                with open(path_str, "r", encoding="utf-8") as f:
                    old = json.load(f)
            except Exception:
                pass

        # 合併邏輯
        stage_priority = {
            "initialization": 0, "fetch_start": 1, "post_parsed": 2,
            "batch_parsed": 3, "fill_views_start": 4, "fill_views_completed": 5,
            "api_completed": 6, "completed": 7, "error": 8
        }
        old_stage = old.get("stage", "")
        new_stage = data.get("stage", old_stage)
        if stage_priority.get(new_stage, 0) < stage_priority.get(old_stage, 0):
            data.pop("stage", None)

        old.update(data)

        # 原子寫入檔案
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(old, f, ensure_ascii=False, indent=2)
            shutil.move(tmp_path, path_str)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
        
        # 同時寫入 Redis（新增功能）
        if self.progress_manager and hasattr(st.session_state, 'playwright_task_id'):
            task_id = st.session_state.playwright_task_id
            try:
                # 準備 Redis 資料
                redis_data = old.copy()
                redis_data['timestamp'] = time.time()
                
                # 使用進度管理器寫入
                self.progress_manager.write_progress(task_id, redis_data, write_both=False)  # 檔案已寫入
            except Exception as e:
                # Redis 寫入失敗不影響檔案功能
                print(f"⚠️ Redis 進度寫入失敗: {e}")

    def _read_progress(self, path) -> Dict[str, Any]:
        """讀取進度檔案"""
        path_str = str(path)
        if not os.path.exists(path_str):
            return {}
        try:
            with open(path_str, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    
    def _cleanup_invalid_file_references(self):
        """清理無效的文件引用，避免 MediaFileStorageError"""
        try:
            # 清理可能導致 MediaFileStorageError 的舊文件引用
            keys_to_check = list(st.session_state.keys())
            for key in keys_to_check:
                # 跳過重要的狀態
                if key in ['playwright_results', 'playwright_crawl_status', 'show_playwright_history_analysis', 
                          'show_playwright_advanced_exports', 'playwright_results_saved']:
                    continue
                
                # 檢查是否是文件相關的key，但保留當前上傳器
                if ('file' in key.lower() or 'upload' in key.lower()) and key != "playwright_csv_uploader_v2":
                    try:
                        # 嘗試訪問這個值，如果有問題就刪除
                        value = st.session_state[key]
                        # 如果是文件對象且已經無效，清理它
                        if hasattr(value, 'file_id') or str(value).startswith('UploadedFile'):
                            del st.session_state[key]
                    except:
                        # 如果訪問時出錯，直接刪除
                        try:
                            del st.session_state[key]
                        except:
                            pass
        except Exception:
            # 如果清理過程出錯，忽略
            pass
    
    # ---------- 2. 主渲染方法 ----------
    def render(self):
        """渲染Playwright爬蟲組件"""
        # 初始化時清理無效的文件引用，避免 MediaFileStorageError
        self._cleanup_invalid_file_references()
        
        st.header("🎭 Playwright 智能爬蟲")
        st.markdown("**基於檔案讀寫架構 + 狀態機驅動的實時進度顯示 + 任務佇列管理**")
        
        # 顯示佇列資訊條
        if self.queue_component:
            self.queue_component.render_queue_info_bar()
            st.divider()
        
        # 檢查佇列狀態並自動處理
        self._auto_process_queue()
        
        # 檢查認證文件
        if not self._check_auth_file():
            st.error("❌ 找不到認證檔案")
            st.info("請先執行: `python tests/threads_fetch/save_auth.py` 來產生認證檔案")
            return
        
        st.success("✅ 認證檔案已就緒")
        
        # 初始化狀態
        if "playwright_crawl_status" not in st.session_state:
            st.session_state.playwright_crawl_status = "idle"
        
        # 檢查是否有從背景恢復的任務需要特殊處理
        if (st.session_state.playwright_crawl_status == "running" and 
            hasattr(st.session_state, 'recovered_from_background') and 
            st.session_state.recovered_from_background):
            self._handle_recovered_task()
        
        # 🔥 簡化：移除複雜的佇列自動啟動邏輯
        
        # 🔧 Redis鎖機制：不需要複雜的殭屍檢測了
        
        # 根據狀態渲染不同內容
        if st.session_state.playwright_crawl_status == "idle":
            self._render_setup()
        else:
            self.render_status_content()
    
    def _safe_decode(self, value, default=''):
        """安全地將bytes或str轉換為str"""
        if value is None:
            return default
        if isinstance(value, bytes):
            return value.decode('utf-8')
        return str(value)
    
    def _show_existing_task_progress(self, job_id: str):
        """顯示現有任務的進度"""
        try:
            from common.redis_client import get_redis_client
            redis_conn = get_redis_client().redis
            
            if redis_conn:
                # 檢查Redis中的任務狀態
                job_data = redis_conn.hgetall(f"job:{job_id}")
                if job_data:
                    status = self._safe_decode(job_data.get(b'status') or job_data.get('status'), 'running')
                    progress_raw = job_data.get(b'progress') or job_data.get('progress') or '0'
                    progress = float(self._safe_decode(progress_raw, '0'))
                    
                    if status == 'completed':
                        st.success(f"✅ 任務已完成 (進度: {progress:.1%})")
                        st.info("💡 您可以在「管理任務」中查看結果")
                    elif status == 'error':
                        error_raw = job_data.get(b'error') or job_data.get('error')
                        error_msg = self._safe_decode(error_raw, '未知錯誤')
                        st.error(f"❌ 任務失敗: {error_msg}")
                    else:
                        st.info(f"🔄 任務執行中 (進度: {progress:.1%})")
                        st.info("💡 頁面會自動更新進度")
                        
                    # 設置session state以顯示進度
                    st.session_state.playwright_task_id = job_id
                    st.session_state.playwright_crawl_status = "running"
                    st.rerun()
                else:
                    st.warning("⚠️ 找不到任務進度信息")
            else:
                st.error("❌ Redis連接失敗")
                
        except Exception as e:
            st.error(f"❌ 檢查任務狀態失敗: {e}")

    # 根據狀態渲染不同內容的其餘部分
    def render_status_content(self):
        """渲染狀態相關內容"""
        if st.session_state.playwright_crawl_status == "running":
            self._render_progress()
        elif st.session_state.playwright_crawl_status == "monitoring":
            self._render_monitoring()
        elif st.session_state.playwright_crawl_status == "completed":
            self._render_results()
        elif st.session_state.playwright_crawl_status == "error":
            self._render_error()
        elif st.session_state.playwright_crawl_status == "task_manager":
            self._render_task_manager()

    
    # ---------- 新增的任務管理方法 ----------
    def _check_and_cleanup_zombie_state(self):
        """檢查並清理殭屍狀態，防止UI陷入不可恢復狀態"""
        try:
            # 只在 running 狀態下檢查
            if st.session_state.playwright_crawl_status != "running":
                return
            
            current_task_id = st.session_state.get('playwright_task_id')
            if not current_task_id:
                return
            
            # 檢查當前任務是否在佇列中且已失敗
            if self.queue_manager:
                queue_status = self.queue_manager.get_queue_status()
                for task in queue_status.get('queue', []):
                    if task.task_id == current_task_id and task.status.value == "error":
                        # 任務已失敗，但UI還在 running 狀態
                        st.warning(f"🔧 檢測到失敗任務 {current_task_id[:8]}，正在清理UI狀態...")
                        
                        # 重置UI狀態
                        st.session_state.playwright_crawl_status = "idle"
                        
                        # 清理相關session state
                        cleanup_keys = [
                            'playwright_task_id', 
                            'playwright_progress_file',
                            'playwright_target',
                            'playwright_auto_start_from_queue',
                            'from_task_manager'
                        ]
                        for key in cleanup_keys:
                            if key in st.session_state:
                                del st.session_state[key]
                        
                        st.error(f"❌ 任務 {current_task_id[:8]} 已失敗，已重置為可用狀態")
                        st.info("💡 您現在可以重新開始新的爬取任務")
                        st.rerun()
                        return
                        
        except Exception as e:
            # 靜默處理錯誤，避免影響主流程
            pass
    
    def _handle_recovered_task(self):
        """處理從背景恢復的任務"""
        if not hasattr(st.session_state, 'playwright_task_id'):
            st.error("❌ 恢復任務失敗：找不到任務 ID")
            st.session_state.playwright_crawl_status = "idle"
            return
        
        task_id = st.session_state.playwright_task_id
        
        if self.task_recovery:
            # 使用任務恢復組件監控
            if not self.task_recovery.render_task_monitor(task_id):
                # 監控失敗，返回空閒狀態
                st.session_state.playwright_crawl_status = "idle"
                return
        
        # 清除恢復標記
        if hasattr(st.session_state, 'recovered_from_background'):
            del st.session_state.recovered_from_background
    
    def _render_task_manager(self):
        """渲染任務管理頁面"""
        st.header("📋 任務管理")
        
        # 控制按鈕區域
        col_back, col_refresh, col_clear_all = st.columns([1, 1, 1])
        
        with col_back:
            if st.button("← 返回設定", key="back_to_setup"):
                st.session_state.playwright_crawl_status = "idle"
                st.rerun()
        
        with col_refresh:
            if st.button("🔄 重新整理", key="refresh_tasks"):
                st.rerun()
        
        with col_clear_all:
            if st.button("🗑️ 全部清空", key="clear_all_tasks", help="清空所有任務和佇列，重置到最乾淨狀態", type="primary"):
                self._show_clear_all_confirmation()
        
        st.divider()
        
        if not self.task_recovery:
            st.error("❌ 任務管理功能不可用")
            return
        
        # 渲染任務列表
        self.task_recovery.render_task_list()
        
        st.divider()
        
        # 渲染清理控制
        self.task_recovery.render_cleanup_controls()
        
        # 處理全部清空確認
        if st.session_state.get('show_clear_all_confirmation', False):
            self._render_clear_all_confirmation()
    
    def _show_clear_all_confirmation(self):
        """顯示全部清空確認對話框"""
        st.session_state.show_clear_all_confirmation = True
        st.rerun()
    
    def _render_clear_all_confirmation(self):
        """渲染全部清空確認對話框"""
        st.warning("⚠️ 全部清空操作")
        st.markdown("""
        **此操作將會：**
        - 🗑️ 清空所有歷史任務記錄
        - 📋 清空任務佇列
        - 🔄 重置所有UI狀態
        - 🧹 清理所有進度檔案
        - 💾 重置系統到最乾淨狀態
        
        **⚠️ 注意：此操作不可逆！**
        """)
        
        col_confirm, col_cancel = st.columns([1, 1])
        
        with col_confirm:
            if st.button("✅ 確認清空", key="confirm_clear_all", type="primary"):
                self._execute_clear_all()
                
        with col_cancel:
            if st.button("❌ 取消", key="cancel_clear_all"):
                st.session_state.show_clear_all_confirmation = False
                st.rerun()
    
    def _execute_clear_all(self):
        """執行全部清空操作"""
        try:
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # 1. 清空佇列系統 (20%)
            status_text.text("🗑️ 正在清空任務佇列...")
            progress_bar.progress(0.2)
            if self.queue_manager:
                # 清空佇列檔案
                queue_file = self.queue_manager.queue_file
                if os.path.exists(queue_file):
                    os.remove(queue_file)
                    print("✅ 佇列檔案已清除")
            
            # 2. 清空歷史任務 (40%)
            status_text.text("📋 正在清空歷史任務...")
            progress_bar.progress(0.4)
            if self.task_recovery:
                # 清空任務記錄
                temp_progress_dir = self.task_recovery.progress_manager.temp_progress_dir
                if os.path.exists(temp_progress_dir):
                    import shutil
                    shutil.rmtree(temp_progress_dir)
                    os.makedirs(temp_progress_dir, exist_ok=True)
                    print("✅ 歷史任務已清除")
            
            # 3. 清理Redis緩存 (60%)
            status_text.text("🔄 正在清理Redis緩存...")
            progress_bar.progress(0.6)
            try:
                if hasattr(self, 'progress_manager') and self.progress_manager:
                    # 清理Redis中的所有進度數據
                    import common.redis_client as redis_client
                    redis_conn = redis_client.get_redis_client().redis
                    if redis_conn:
                        # 刪除所有playwright相關的keys
                        keys = redis_conn.keys("playwright:*")
                        if keys:
                            redis_conn.delete(*keys)
                            print(f"✅ 已清理 {len(keys)} 個Redis鍵")
            except Exception as e:
                print(f"⚠️ Redis清理警告: {e}")
            
            # 4. 重置UI狀態 (80%)
            status_text.text("🎛️ 正在重置UI狀態...")
            progress_bar.progress(0.8)
            
            # 清理所有playwright相關的session state
            playwright_keys = [key for key in st.session_state.keys() if key.startswith('playwright')]
            for key in playwright_keys:
                del st.session_state[key]
            
            # 清理其他相關狀態
            cleanup_keys = [
                'show_clear_all_confirmation',
                'from_task_manager',
                'recovered_from_background'
            ]
            for key in cleanup_keys:
                if key in st.session_state:
                    del st.session_state[key]
            
            # 5. 完成 (100%)
            status_text.text("✅ 清空完成！")
            progress_bar.progress(1.0)
            
            # 重置到最乾淨狀態
            st.session_state.playwright_crawl_status = "idle"
            
            # 驗證清空效果
            status_text.text("🔍 正在驗證清空效果...")
            
            # 檢查佇列是否為空
            queue_empty = True
            if self.queue_manager:
                queue_status = self.queue_manager.get_queue_status()
                queue_empty = queue_status['total'] == 0
            
            # 檢查進度目錄是否為空
            progress_empty = True
            if self.task_recovery:
                temp_progress_dir = self.task_recovery.progress_manager.temp_progress_dir
                if os.path.exists(temp_progress_dir):
                    progress_files = os.listdir(temp_progress_dir)
                    progress_empty = len(progress_files) == 0
            
            if queue_empty and progress_empty:
                st.success("🎉 系統已重置到最乾淨狀態！")
                st.success("✅ 驗證通過：佇列已清空，歷史任務已清除")
                st.info("💡 您現在可以正常使用爬蟲功能了")
            else:
                st.warning("⚠️ 部分清空可能不完整，但基本功能應該可用")
            
            time.sleep(2)  # 讓用戶看到完成信息
            st.rerun()
            
        except Exception as e:
            st.error(f"❌ 清空操作失敗: {e}")
            st.session_state.show_clear_all_confirmation = False
    
    def _render_setup(self):
        """渲染設定頁面"""
        # 參數設定區域 - 修復佈局問題
        col_settings, col_stats = st.columns([1, 1])
        
        with col_settings:
            st.subheader("⚙️ 爬取設定")
            username = st.text_input(
                "目標帳號", 
                value="gvmonthly",
                help="要爬取的Threads帳號用戶名",
                key="playwright_username_v2"
            )
            
            max_posts = st.number_input(
                "爬取數量", 
                min_value=1, 
                max_value=500, 
                value=50,
                help="要爬取的貼文數量",
                key="playwright_max_posts_v2"
            )
            
            # 爬取模式設定
            crawl_mode = st.radio(
                "🔄 爬取模式",
                ["增量模式", "全量模式"],
                index=0,  # 預設增量模式
                help="增量模式：只爬取新貼文，跳過已存在的貼文｜全量模式：重新爬取所有貼文，更新現有資料",
                key="playwright_crawl_mode_v2",
                horizontal=True
            )
            
            if crawl_mode == "增量模式":
                st.info("💡 增量模式：智能跳過資料庫中已存在的貼文，只收集新內容")
            else:
                st.warning("⚠️ 全量模式：將重新爬取所有貼文，可能會獲得重複數據，適用於資料更新需求")
            
            # 去重設定
            enable_deduplication = st.checkbox(
                "🧹 啟用去重功能",
                value=False,
                help="開啟時會過濾相似內容的重複貼文，保留主貼文；關閉時保留所有抓取到的貼文",
                key="playwright_enable_dedup_v2"
            )

            # 防禦性守門：顯示/存前去重 + 指紋紀錄（供增量跳過）
            defensive_dedup = st.checkbox(
                "🔒 防禦性守門（顯示/存前去重＋指紋）",
                value=True,
                help="顯示與入庫前會根據同內容去重，只保留觀看數較高者；被丟棄者以指紋寫入（source=playwright_dedup_filtered），供增量模式跳過。全量模式不跳過但不會顯示或入庫重複。",
                key="playwright_defensive_dedup_v2"
            )

            # 新增：完成後自動下載媒體
            auto_download_media = st.checkbox(
                "⬇️ 完成後自動下載媒體",
                value=False,
                help="爬蟲完成並保存到資料庫後，自動把本批貼文的圖片/影片下載到 RustFS",
                key="playwright_auto_download_media_v2"
            )
            
            # 🆕 新增：即時下載媒體
            realtime_download = st.checkbox(
                "🚀 即時下載媒體 (推薦)",
                value=False,
                help="在爬取過程中立即下載媒體，確保URL時效性，特別適合影片下載",
                key="playwright_realtime_download_v2"
            )
            
            if enable_deduplication:
                st.info("💡 將根據觀看數、互動數、內容長度等維度保留主貼文，過濾回應")
            else:
                st.warning("⚠️ 關閉去重可能會獲得大量相似內容，建議僅在特殊需求時使用")
            
            # 控制按鈕區域（佇列版本）
            col1, col2, col3 = st.columns([1, 1, 1])
            
            with col1:
                if st.button("🚀 開始爬取", key="start_playwright_v2", help="開始爬取任務"):
                    # 🔥 Redis鎖機制：防重複+排隊
                    is_incremental = (crawl_mode == "增量模式")
                    # 記錄是否要自動下載
                    st.session_state.playwright_auto_download_media_v2_selected = auto_download_media
                    
                    try:
                        # 生成任務唯一鍵
                        import hashlib
                        job_key = hashlib.sha256(f"{username}:{max_posts}:{is_incremental}".encode()).hexdigest()[:16]
                        job_id = str(uuid.uuid4())
                        
                        # 嘗試獲取鎖
                        try:
                            from common.redis_client import get_redis_client
                            redis_conn = get_redis_client().redis
                            
                            if redis_conn and redis_conn.set(f"lock:{job_key}", job_id, nx=True, ex=7200):
                                # 獲得鎖，啟動新任務
                                st.info("✅ 任務鎖定成功，正在啟動...")
                                self._start_crawling(username, max_posts, enable_deduplication, is_incremental, job_id)
                                st.success("🚀 任務已啟動")
                            else:
                                # 任務已存在
                                existing_job_id = redis_conn.get(f"lock:{job_key}")
                                if existing_job_id:
                                    existing_job_id = self._safe_decode(existing_job_id)
                                    st.warning(f"⏳ 相同任務正在執行中: {existing_job_id[:8]}...")
                                    st.info("💡 請等待當前任務完成或使用「管理任務」查看進度")
                                else:
                                    st.warning("⚠️ 獲取鎖失敗，可能有其他任務執行中")
                        except Exception as redis_error:
                            # Redis連接失敗，降級為直接執行
                            st.warning(f"⚠️ Redis不可用({redis_error})，直接執行")
                            self._start_crawling(username, max_posts, enable_deduplication, is_incremental)
                                
                    except Exception as e:
                        st.error(f"❌ 啟動失敗: {e}")
                        import traceback
                        st.code(traceback.format_exc())
                    
            with col2:
                try:
                    uploaded_file = st.file_uploader(
                        "📁 載入CSV文件", 
                        type=['csv'], 
                        key="playwright_csv_uploader_v2",
                        help="上傳之前導出的CSV文件來查看結果"
                    )
                    if uploaded_file is not None:
                        self.export_handler.load_csv_file(uploaded_file)
                except Exception as e:
                    # 如果文件上傳器出錯，清理並重新顯示
                    if "MediaFileStorageError" in str(e) or "file_id" in str(e):
                        st.warning("⚠️ 偵測到舊的文件引用，正在清理...")
                        # 清理相關狀態
                        for key in list(st.session_state.keys()):
                            if 'uploader' in key.lower() or 'file' in key.lower():
                                try:
                                    del st.session_state[key]
                                except:
                                    pass
                        st.rerun()
                    else:
                        st.error(f"❌ 文件上傳器錯誤: {e}")
            
            with col3:
                if 'playwright_results' in st.session_state:
                    if st.button("🗑️ 清除結果", key="clear_playwright_results_v2", help="清除當前顯示的結果"):
                        self.export_handler.clear_results()
        
        # 任務管理區域（新增）
        if self.progress_manager:
            st.divider()
            st.subheader("📋 任務管理")
            
            col_tasks, col_manage = st.columns([2, 1])
            
            with col_tasks:
                # 顯示任務摘要
                try:
                    summary = self.progress_manager.get_task_summary()
                    if summary["total"] > 0:
                        summary_text = f"共 {summary['total']} 個任務 | "
                        if summary["running"] > 0:
                            summary_text += f"🔄 {summary['running']} 執行中 "
                        if summary["completed"] > 0:
                            summary_text += f"✅ {summary['completed']} 已完成 "
                        if summary["error"] > 0:
                            summary_text += f"❌ {summary['error']} 錯誤"
                        st.info(summary_text)
                    else:
                        st.info("目前沒有任務記錄")
                except Exception as e:
                    st.info("任務管理功能初始化中...")
            
            with col_manage:
                col_manage_task, col_reset = st.columns([2, 1])
                
                with col_manage_task:
                    if st.button("📊 管理任務", key="manage_tasks", help="查看和管理歷史任務"):
                        st.session_state.playwright_crawl_status = "task_manager"
                        st.rerun()
                
                with col_reset:
                    if st.button("🔄 重置", key="force_reset", help="強制重置系統狀態", type="secondary"):
                        # 強制清理所有狀態
                        cleanup_keys = [
                            'playwright_task_id', 
                            'playwright_progress_file',
                            'playwright_target',
                            'playwright_auto_start_from_queue',
                            'from_task_manager',
                            'playwright_db_saved',
                            'playwright_results_saved'
                        ]
                        for key in cleanup_keys:
                            if key in st.session_state:
                                del st.session_state[key]
                        
                        st.session_state.playwright_crawl_status = "idle"
                        st.success("✅ 系統狀態已重置")
                        st.rerun()
                
        with col_stats:
            col_title, col_refresh = st.columns([3, 1])
            with col_title:
                st.subheader("📊 資料庫統計")
            with col_refresh:
                if st.button("🔄 刷新", key="refresh_playwright_db_stats_v2", help="刷新資料庫統計信息", type="secondary"):
                    if 'playwright_db_stats_cache' in st.session_state:
                        del st.session_state.playwright_db_stats_cache
                    st.success("🔄 正在刷新統計...")
                    st.rerun()
            
            self._display_database_stats()
        
        # 顯示已載入的 CSV 結果（如果有的話）
        if 'playwright_results' in st.session_state:
            st.divider()
            results = st.session_state.playwright_results
            st.info(f"📁 已載入 CSV 文件：{results.get('total_processed', 0)} 筆記錄")
            
            col_view, col_clear = st.columns([1, 1])
            with col_view:
                if st.button("👁️ 查看載入的結果", key="view_loaded_results"):
                    st.session_state.playwright_crawl_status = "completed"
                    st.rerun()
            
            with col_clear:
                if st.button("🗑️ 清除載入的結果", key="clear_loaded_results"):
                    if 'playwright_results' in st.session_state:
                        del st.session_state.playwright_results
                    st.rerun()
    
    def _render_progress(self):
        """渲染進度頁面（新版架構）"""
        progress_file = st.session_state.get('playwright_progress_file', '')
        
        # -- 數據更新邏輯 --
        # 讀取最新進度狀態（優先從 Redis 讀取後台任務）
        task_id = st.session_state.get('playwright_task_id')
        progress_data = None
        
        # 嘗試從 Redis 獲取最新狀態（後台任務可能已完成）
        if task_id:
            try:
                redis_progress = self.progress_manager.get_progress(task_id, prefer_redis=True)
                if redis_progress and redis_progress.get("stage") in ("completed", "error"):
                    # 如果 Redis 中任務已完成或錯誤，使用 Redis 數據
                    progress_data = redis_progress
                    # 更新本地進度文件以保持同步
                    if progress_file:
                        self._update_progress_file(progress_file, 
                                                 redis_progress.get("progress", 100.0), 
                                                 redis_progress.get("stage", "completed"), 
                                                 "後台任務已完成",
                                                 final_data=redis_progress.get("final_data", {}))
            except Exception as e:
                pass  # Redis 讀取失敗時靜默處理
        
        # 如果 Redis 沒有完成狀態，使用本地文件
        if not progress_data and progress_file and os.path.exists(progress_file):
            progress_data = self._read_progress(progress_file)
            
        if progress_data:
                # 總是以最新檔案內容更新 session state
                st.session_state.playwright_progress = progress_data.get("progress", 0.0)
                st.session_state.playwright_current_work = progress_data.get("current_work", "")
                
                # 檢查是否達到需要切換頁面的最終狀態
                stage = progress_data.get("stage")
                if stage in ("api_completed", "completed"):
                    st.session_state.playwright_crawl_status = "completed"
                    st.session_state.playwright_final_data = progress_data.get("final_data", {})
                    st.rerun() # 切換到結果頁面
                elif stage == "error":
                    st.session_state.playwright_crawl_status = "error"
                    st.session_state.playwright_error_msg = progress_data.get("error", "未知錯誤")
                    st.rerun() # 切換到錯誤頁面

        # -- UI 顯示邏輯 --
        target = st.session_state.get('playwright_target', {})
        username = target.get('username', 'unknown')
        progress = st.session_state.get('playwright_progress', 0.0)
        current_work = st.session_state.get('playwright_current_work', '')

        # 添加導航按鈕
        col_back, col_title = st.columns([1, 4])
        with col_back:
            if st.button("← 返回", key="back_from_progress", help="返回上一頁"):
                # 檢查是否從管理任務頁面進入
                if st.session_state.get('from_task_manager', False):
                    st.session_state.playwright_crawl_status = "task_manager"
                    st.session_state.from_task_manager = False
                else:
                    st.session_state.playwright_crawl_status = "idle"
                st.rerun()
        
        with col_title:
            st.info(f"🔄 正在爬取 @{username} 的貼文...")
        
        st.progress(max(0.0, min(1.0, progress)), text=f"{progress:.1%} - {current_work}")
        
        # 顯示詳細階段信息
        if progress_file and os.path.exists(progress_file):
            progress_data = self._read_progress(progress_file)
            if progress_data:
                stage = progress_data.get("stage", "unknown")
                stage_names = {
                    # 排隊等待階段
                    "waiting_queue": "⏳ 等待排隊中",
                    "queued": "📋 已排隊等待",
                    
                    # 初始階段
                    "initialization": "🔧 初始化爬蟲環境",
                    "auth_loading": "🔐 載入認證檔案",
                    "request_preparation": "📋 準備API請求",
                    "api_request": "🚀 發送API請求",
                    "api_processing": "⏳ API處理中",
                    
                    # Playwright 處理階段
                    "browser_launch": "🌐 啟動瀏覽器",
                    "page_navigation": "🧭 導航到用戶頁面",
                    "page_loading": "⏳ 頁面載入中",
                    "scroll_start": "📜 開始智能滾動",
                    "url_collection": "🔗 收集貼文URLs",
                    "url_processing": "🔄 處理URLs",
                    
                    # 數據補齊階段
                    "fill_details_start": "🔍 開始補齊詳細數據",
                    "fill_details_progress": "📝 補齊貼文內容和互動",
                    "fill_views_start": "👁️ 開始補齊觀看數",
                    "fill_views_progress": "📊 補齊觀看數據",
                    "deduplication": "🧹 去重處理",
                    
                    # 完成階段
                    "response_processing": "📦 處理API響應",
                    "completed": "🎉 爬取完成",
                    "error": "❌ 發生錯誤"
                }
                stage_display = stage_names.get(stage, f"🔄 {stage}")
                
                # 根據進度顯示不同的顏色和樣式
                if progress >= 0.9:
                    st.success(f"**當前階段**: {stage_display}")
                elif progress >= 0.5:
                    st.info(f"**當前階段**: {stage_display}")
                elif stage == "error":
                    st.error(f"**當前階段**: {stage_display}")
                else:
                    st.warning(f"**當前階段**: {stage_display}")
                
                # 顯示進度階段圖
                self._render_progress_stages(progress, stage)
                
                # 顯示日誌
                log_messages = progress_data.get("log_messages", [])
                if log_messages:
                    with st.expander("📋 爬取過程日誌", expanded=True):
                        recent_logs = log_messages[-30:] if len(log_messages) > 30 else log_messages
                        st.code('\n'.join(recent_logs), language='text')
        
        st.info("⏱️ 進度將自動更新，無需手動操作。")

        # -- 自動刷新機制 --
        # 只要還在 running 狀態，就安排一個延遲刷新
        if st.session_state.playwright_crawl_status in ['running', 'monitoring']:
            time.sleep(1) # 降低刷新頻率
            st.rerun()
    
    def _render_monitoring(self):
        """渲染任務監控頁面 - 用於超時後的任務恢復"""
        st.subheader("🔍 後台任務監控")
        st.info("⏰ 由於請求超時，已切換到後台任務監控模式。任務仍在後台繼續執行...")
        
        task_id = st.session_state.get('playwright_task_id')
        if not task_id:
            st.error("❌ 無法找到任務ID")
            if st.button("🔙 返回設定"):
                st.session_state.playwright_crawl_status = "idle"
                st.rerun()
            return
        
        # 顯示任務信息
        col1, col2 = st.columns(2)
        with col1:
            st.metric("任務ID", f"{task_id[:8]}...")
        with col2:
            monitoring_duration = time.time() - st.session_state.get('playwright_monitoring_start', time.time())
            st.metric("監控時間", f"{monitoring_duration:.0f}秒")
        
        # 從 Redis 或進度管理器獲取實際進度
        try:
            progress_data = self.progress_manager.get_progress(task_id, prefer_redis=True)
            
            if progress_data:
                stage = progress_data.get("stage", "unknown")
                progress = progress_data.get("progress", 0)
                username = progress_data.get("username", "unknown")
                
                # 顯示當前狀態
                st.write("### 📊 當前狀態")
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric("用戶", username)
                with col2:
                    st.metric("階段", stage)
                with col3:
                    st.metric("進度", f"{progress:.1f}%")
                
                # 進度條
                st.progress(progress / 100.0 if progress > 0 else 0.0)
                
                # 檢查任務是否完成
                if stage == "completed":
                    st.success("🎉 任務已完成！")
                    
                    # 設定結果並切換到結果頁面
                    final_data = progress_data.get("final_data", {})
                    if final_data:
                        st.session_state.playwright_final_data = final_data
                        st.session_state.playwright_crawl_status = "completed"
                        st.rerun()
                    else:
                        st.warning("任務完成但無法獲取結果數據")
                
                elif "error" in stage:
                    st.error(f"❌ 任務執行錯誤: {progress_data.get('error', 'Unknown error')}")
                    st.session_state.playwright_crawl_status = "error"
                    st.session_state.playwright_error_msg = progress_data.get('error', 'Unknown error')
                    st.rerun()
                    
                # 顯示詳細日誌（如果有）
                log_messages = progress_data.get("log_messages", [])
                if log_messages:
                    with st.expander("📋 任務日誌", expanded=False):
                        recent_logs = log_messages[-20:] if len(log_messages) > 20 else log_messages
                        st.code('\n'.join(recent_logs), language='text')
            else:
                st.warning("⚠️ 無法獲取任務進度，任務可能已完成或發生錯誤")
                
                # 提供手動選項
                if st.button("🔄 重新嘗試獲取進度"):
                    st.rerun()
                    
        except Exception as e:
            st.error(f"❌ 獲取進度時發生錯誤: {str(e)}")
        
        # 控制按鈕
        st.write("### 🎛️ 控制選項")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("📋 任務管理"):
                st.session_state.playwright_crawl_status = "task_manager"
                st.rerun()
        
        with col2:
            if st.button("🔙 返回設定"):
                st.session_state.playwright_crawl_status = "idle"
                st.rerun()
        
        with col3:
            if st.button("🗑️ 停止監控"):
                # 不刪除任務，只是停止監控
                st.session_state.playwright_crawl_status = "idle"
                st.info("已停止監控，任務仍在後台運行。可在任務管理中查看。")
                time.sleep(2)
                st.rerun()
    
    def _render_results(self):
        """渲染結果頁面"""
        st.subheader("✅ 爬取完成")
        
        # 優先檢查 final_data（來自正常爬取），然後檢查 playwright_results（來自CSV導入）
        final_data = st.session_state.get('playwright_final_data', {})
        csv_results = st.session_state.get('playwright_results', {})
        
        # 如果沒有任何數據
        if not final_data and not csv_results:
            st.warning("沒有爬取到數據")
            if st.button("🔙 返回設定"):
                # 檢查是否從管理任務頁面進入
                if st.session_state.get('from_task_manager', False):
                    st.session_state.playwright_crawl_status = "task_manager"
                    st.session_state.from_task_manager = False
                else:
                    st.session_state.playwright_crawl_status = "idle"
                # 重置保存標記，準備下次爬取
                st.session_state.playwright_results_saved = False
                st.rerun()
            return
        
        # 統一數據格式：如果有CSV導入的結果，使用它；否則使用final_data
        if csv_results:
            final_data = csv_results
            st.info("📁 顯示CSV導入的結果")
        else:
            st.info("🎯 顯示爬取的結果")
        
        # 處理並顯示結果
        try:
            # 轉換結果格式
            converted_results = PlaywrightUtils.convert_playwright_results(final_data)
            # 顯示前去重（內容相同、不同貼文ID → 保留觀看數高者）依 UI 開關
            if st.session_state.get('playwright_defensive_dedup_v2', True):
                converted_results = PlaywrightUtils.deduplicate_results_by_content_keep_max_views(converted_results)
            
            # 🔧 修復：優先使用轉換後的用戶名，避免覆蓋正確數據
            if not converted_results.get("target_username"):
                # 只有當轉換後沒有用戶名時才從其他地方獲取
                target = st.session_state.get('playwright_target', {})
                session_username = target.get('username')
                final_data_username = final_data.get('username')
                converted_results["target_username"] = session_username or final_data_username or 'unknown'
            
            # 檢查是否已經保存過，避免重複保存
            if not st.session_state.get('playwright_results_saved', False):
                # 保存JSON文件
                json_file_path = PlaywrightUtils.save_json_results(converted_results)
                st.session_state.playwright_results_saved = True  # 標記為已保存
            else:
                # 如果已經保存過，不再重新保存，但仍需要顯示結果
                json_file_path = None
            
            # 自動保存到資料庫
            save_attempted = False
            try:
                # 檢查是否已經保存過到資料庫
                if not st.session_state.get('playwright_db_saved', False):
                    st.info("🔄 正在保存到資料庫...")
                    # 使用 nest_asyncio 與既有事件迴圈，避免 Streamlit/Windows 衝突
                    import nest_asyncio
                    import asyncio as _asyncio
                    nest_asyncio.apply()
                    loop = _asyncio.get_event_loop()
                    result = loop.run_until_complete(self.db_handler.save_to_database_async(converted_results))
                    
                    if result and result.get("success", False):
                        converted_results["database_saved"] = True
                        converted_results["database_saved_count"] = result.get("saved_count", len(converted_results.get("results", [])))
                        st.session_state.playwright_db_saved = True  # 標記資料庫已保存
                        
                        # 🔧 重要：清除資料庫統計緩存，確保數據更新
                        if 'playwright_db_stats_cache' in st.session_state:
                            del st.session_state.playwright_db_stats_cache
                        
                        st.success(f"✅ 已自動保存 {converted_results['database_saved_count']} 個貼文到資料庫")
                        st.info("📊 統計數據將在下次查看時更新")
                    else:
                        raise Exception(f"保存失敗: {result}")
                else:
                    converted_results["database_saved"] = True
                    converted_results["database_saved_count"] = len(converted_results.get("results", []))
                    st.info("✅ 資料庫保存已完成（避免重複保存）")
                
            except Exception as db_error:
                converted_results["database_saved"] = False
                converted_results["database_saved_count"] = 0
                st.warning(f"⚠️ 自動保存到資料庫失敗: {db_error}")
                st.info("💡 您可以稍後使用 '💾 備用保存' 按鈕重試")
                st.error(f"🔍 詳細錯誤: {str(db_error)}")  # 顯示詳細錯誤供調試
            
            # 顯示結果（顯示時也排除 dedup_filtered 指紋）
            if converted_results.get('results'):
                converted_results['results'] = [
                    r for r in converted_results['results']
                    if (r.get('source') or 'playwright_agent') != 'playwright_dedup_filtered'
                ]
            self._show_results(converted_results)

            # 若資料庫保存成功且勾選自動下載，立即觸發下載
            if converted_results.get("database_saved") and st.session_state.get('playwright_auto_download_media_v2_selected', False):
                try:
                    from agents.vision.media_download_service import MediaDownloadService
                    import asyncio, nest_asyncio
                    nest_asyncio.apply()
                    svc = MediaDownloadService()
                    posts = converted_results.get('results', []) or []
                    plan = {}
                    for r in posts:
                        post_url = (r.get('url') or "").strip()
                        if not post_url:
                            continue
                        urls = []
                        urls.extend(r.get('images') or [])
                        urls.extend(r.get('videos') or [])
                        if urls:
                            plan[post_url] = urls
                    if plan:
                        res = asyncio.get_event_loop().run_until_complete(svc.run_download(plan, concurrency_per_post=3))
                        st.info(f"⬇️ 自動下載完成：成功 {res['success']}，失敗 {res['failed']} / 共 {res['total']}")
                    else:
                        st.info("本批貼文沒有可下載的媒體 URL")
                except Exception as e:
                    st.warning(f"自動下載失敗：{e}")
            
        except Exception as e:
            st.error(f"❌ 處理結果時發生錯誤: {e}")
        
        # 返回按鈕
        if st.button("🔙 返回設定"):
            st.session_state.playwright_crawl_status = "idle"
            st.rerun()
    
    def _render_error(self):
        """渲染錯誤頁面"""
        st.subheader("❌ 爬取失敗")
        
        error_msg = st.session_state.get('playwright_error_msg', '未知錯誤')
        st.error(f"錯誤信息: {error_msg}")
        
        # 顯示詳細錯誤信息
        progress_file = st.session_state.get('playwright_progress_file', '')
        if progress_file and os.path.exists(progress_file):
            progress_data = self._read_progress(progress_file)
            if progress_data:
                st.subheader("🔍 詳細錯誤信息")
                
                # 顯示錯誤詳情
                if 'error' in progress_data:
                    st.code(progress_data['error'], language='text')
                
                # 顯示日誌
                log_messages = progress_data.get("log_messages", [])
                if log_messages:
                    with st.expander("📋 錯誤日誌", expanded=True):
                        recent_logs = log_messages[-20:] if len(log_messages) > 20 else log_messages
                        st.code('\n'.join(recent_logs), language='text')
                
                # 顯示完整進度數據
                with st.expander("🔧 調試信息", expanded=False):
                    st.json(progress_data)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔙 返回設定"):
                # 清理進度檔案
                if progress_file and os.path.exists(progress_file):
                    try:
                        os.remove(progress_file)
                    except:
                        pass
                # 檢查是否從管理任務頁面進入
                if st.session_state.get('from_task_manager', False):
                    st.session_state.playwright_crawl_status = "task_manager"
                    st.session_state.from_task_manager = False
                else:
                    st.session_state.playwright_crawl_status = "idle"
                st.rerun()
        
        with col2:
            if st.button("🔄 重試"):
                # 清理進度檔案
                if progress_file and os.path.exists(progress_file):
                    try:
                        os.remove(progress_file)
                    except:
                        pass
                st.session_state.playwright_crawl_status = "idle"
                st.rerun()
    
    # ---------- 3. 爬蟲啟動邏輯 ----------
    def _start_waiting_mode(self, username: str, max_posts: int, enable_deduplication: bool = True, is_incremental: bool = True):
        """啟動等待模式 - 有其他任務執行時"""
        # 設定目標參數
        st.session_state.playwright_target = {
            'username': username,
            'max_posts': max_posts,
            'enable_deduplication': enable_deduplication,
            'is_incremental': is_incremental
        }
        
        # 重置保存標記
        st.session_state.playwright_results_saved = False
        st.session_state.playwright_db_saved = False
        
        # 創建等待狀態的進度檔案
        task_id = str(uuid.uuid4())
        from pathlib import Path
        temp_progress_dir = Path("temp_progress")
        temp_progress_dir.mkdir(exist_ok=True)
        progress_file = temp_progress_dir / f"playwright_progress_{task_id}.json"
        st.session_state.playwright_progress_file = str(progress_file)
        st.session_state.playwright_task_id = task_id
        
        # 初始化等待狀態的進度檔案
        self._write_progress(progress_file, {
            "progress": 0.0,
            "stage": "waiting_queue",
            "current_work": "等待前面的任務完成...",
            "log_messages": [
                "🚀 任務已建立...",
                "⏳ 檢測到有其他任務正在執行",
                "📋 將在5秒後自動加入排隊系統",
                "💡 請稍候，無需手動操作"
            ],
            "start_time": time.time(),
            "username": username,
            "waiting_for_queue": True  # 標記為等待排隊狀態
        })
        
        # 啟動背景延遲線程，5秒後加入排隊
        import threading
        delay_thread = threading.Thread(
            target=self._delayed_queue_add,
            args=(username, max_posts, enable_deduplication, is_incremental, task_id, progress_file),
            daemon=True
        )
        delay_thread.start()
        
        # 切換到進度頁面（顯示等待狀態）
        st.session_state.playwright_crawl_status = "running"
        st.rerun()
    
    def _delayed_queue_add(self, username: str, max_posts: int, enable_deduplication: bool, is_incremental: bool, task_id: str, progress_file: str):
        """延遲5秒後加入排隊系統"""
        import time
        
        # 等待5秒
        for i in range(5, 0, -1):
            self._log_to_file(progress_file, f"⏳ {i}秒後自動加入排隊...")
            self._update_progress_file(progress_file, 0.0, "waiting_queue", f"⏳ {i}秒後加入排隊...")
            time.sleep(1)
        
        # 5秒後，加入排隊系統
        try:
            self._log_to_file(progress_file, "📋 正在加入任務排隊...")
            self._update_progress_file(progress_file, 0.0, "waiting_queue", "正在加入排隊系統...")
            
            if self.queue_manager:
                mode = "new" if is_incremental else "hist"
                success = self.queue_manager.add_task(task_id, username, max_posts, mode)
                
                if success:
                    self._log_to_file(progress_file, "✅ 已成功加入任務排隊")
                    self._update_progress_file(progress_file, 0.0, "queued", "已加入排隊，等待執行...")
                else:
                    self._log_to_file(progress_file, "❌ 加入排隊失敗")
                    self._update_progress_file(progress_file, 0.0, "error", "加入排隊失敗", error="無法加入排隊系統")
            else:
                # 如果沒有排隊系統，直接啟動
                self._log_to_file(progress_file, "🚀 排隊系統不可用，直接啟動任務...")
                self._background_crawler_worker(username, max_posts, enable_deduplication, is_incremental, task_id, progress_file)
                
        except Exception as e:
            self._log_to_file(progress_file, f"❌ 處理排隊時發生錯誤: {e}")
            self._update_progress_file(progress_file, 0.0, "error", f"排隊處理錯誤: {e}", error=str(e))
    def _start_from_queue(self):
        """從排隊系統啟動下一個任務"""
        if not self.queue_manager:
            st.error("❌ 排隊管理器不可用")
            return
            
        # 獲取下一個等待中的任務
        next_task = self.queue_manager.get_next_waiting_task()
        if next_task:
            try:
                st.info(f"🚀 正在從佇列啟動任務: {next_task.username} (ID: {next_task.task_id[:8]}...)")
                
                # 標記任務為執行中
                success = self.queue_manager.start_task(next_task.task_id)
                if not success:
                    st.error(f"❌ 無法標記任務為執行中: {next_task.task_id[:8]}")
                    return
                
                # 啟動任務
                self._start_crawl_from_queue_task(next_task)
                st.success(f"✅ 任務已啟動: {next_task.username}")
                
            except Exception as e:
                st.error(f"❌ 啟動佇列任務失敗: {e}")
                # 將任務標記為失敗
                if self.queue_manager:
                    self.queue_manager.complete_task(next_task.task_id, False, str(e))
        else:
            # 沒有等待任務時，確保UI狀態正確
            if st.session_state.playwright_crawl_status == "running":
                st.info("📋 佇列為空，返回設定頁面")
                st.session_state.playwright_crawl_status = "idle"
                st.rerun()
    
    def _start_crawling(self, username: str, max_posts: int, enable_deduplication: bool = True, is_incremental: bool = True, task_id: str = None):
        """啟動爬蟲"""
        # 記錄爬取開始時間
        start_time = time.time()
        st.session_state.playwright_crawl_start_time = start_time
        
        # 設定目標參數
        st.session_state.playwright_target = {
            'username': username,
            'max_posts': max_posts,
            'enable_deduplication': enable_deduplication,
            'is_incremental': is_incremental
        }
        
        # 重置保存標記，允許新的爬取結果被保存
        st.session_state.playwright_results_saved = False
        st.session_state.playwright_db_saved = False  # 🔧 重置資料庫保存標記
        
        # 創建進度檔案 - 使用專門的資料夾
        # 🔧 重要修復：支援外部提供的 task_id（用於佇列任務）
        if task_id is None:
            task_id = str(uuid.uuid4())
        from pathlib import Path
        temp_progress_dir = Path("temp_progress")
        temp_progress_dir.mkdir(exist_ok=True)
        progress_file = temp_progress_dir / f"playwright_progress_{task_id}.json"
        st.session_state.playwright_progress_file = str(progress_file)
        st.session_state.playwright_progress_file_obj = progress_file
        st.session_state.playwright_task_id = task_id
        
        # 初始化進度檔案
        target = st.session_state.get('playwright_target', {})
        username = target.get('username', 'unknown')
        
        self._write_progress(progress_file, {
            "progress": 0.0,
            "stage": "initialization",
            "current_work": "正在啟動...",
            "log_messages": ["🚀 爬蟲任務已啟動..."],
            "start_time": time.time(),
            "username": username  # 🔧 修復：添加用戶名，避免創建@unknown任務
        })
        
        # 啟動背景線程
        print(f"🚀 正在啟動背景線程: {username} (ID: {task_id[:8]}...)")
        print(f"📂 進度檔案: {progress_file}")
        
        # 獲取即時下載設定
        realtime_download = st.session_state.get('playwright_realtime_download_v2', False)
        
        task_thread = threading.Thread(
            target=self._background_crawler_worker,
            args=(username, max_posts, enable_deduplication, is_incremental, task_id, progress_file, realtime_download),
            daemon=True
        )
        task_thread.start()
        
        print(f"✅ 背景線程已啟動: {task_thread.name}")
        
        # 切換到進度頁面
        st.session_state.playwright_crawl_status = "running"
        st.rerun()
    
    def _background_crawler_worker(self, username: str, max_posts: int, enable_deduplication: bool, is_incremental: bool, task_id: str, progress_file: str, realtime_download: bool = False):
        """背景爬蟲工作線程 - 只寫檔案，不做任何 st.* 操作"""
        try:
            print(f"🔥 背景線程開始執行: {username} (ID: {task_id[:8]}...)")
            print(f"📂 進度檔案路徑: {progress_file}")
            
            # 階段1: 初始化 (0-5%)
            self._log_to_file(progress_file, "🔧 初始化爬蟲環境...")
            self._update_progress_file(progress_file, 0.02, "initialization", "初始化爬蟲環境...")
            print(f"✅ 初始化階段完成: {task_id[:8]}")
            
            # 階段2: 讀取認證 (5-10%)
            self._log_to_file(progress_file, "🔐 讀取認證檔案...")
            self._update_progress_file(progress_file, 0.05, "auth_loading", "讀取認證檔案...")
            
            try:
                with open(self.auth_file_path, "r", encoding="utf-8") as f:
                    auth_content = json.load(f)
                self._log_to_file(progress_file, f"✅ 認證檔案讀取成功，包含 {len(auth_content.get('cookies', []))} 個 cookies")
            except Exception as e:
                self._update_progress_file(progress_file, 0.0, "error", f"❌ 讀取認證檔案失敗: {e}")
                return
            
            # 階段3: 準備請求 (10-15%)
            self._log_to_file(progress_file, "📋 構建API請求參數...")
            self._update_progress_file(progress_file, 0.10, "request_preparation", "構建API請求...")
            
            payload = {
                "username": username,
                "max_posts": max_posts,
                "auth_json_content": auth_content,
                "enable_deduplication": enable_deduplication,
                "incremental": is_incremental,
                "task_id": task_id,  # 🔧 修復：傳遞task_id給後端，避免重複創建任務
                "realtime_download": realtime_download  # 🆕 即時下載參數
            }
            
            self._log_to_file(progress_file, f"📊 目標用戶: @{username}")
            self._log_to_file(progress_file, f"📝 目標貼文數: {max_posts}")
            self._log_to_file(progress_file, f"🔄 爬取模式: {'增量模式' if is_incremental else '全量模式'}")
            self._log_to_file(progress_file, f"🧹 去重功能: {'啟用' if enable_deduplication else '關閉'}")
            
            # 階段4: 發送請求 (15-20%)
            self._log_to_file(progress_file, "🚀 發送API請求到Playwright Agent...")
            self._update_progress_file(progress_file, 0.15, "api_request", "發送API請求...")
            
            # 發送 API 請求並監控進度
            try:
                import httpx
                import time
                
                # 開始API請求
                start_time = time.time()
                
                with httpx.Client(timeout=1800.0) as client:  # 30分鐘超時，支援大型任務
                    # 階段5: 等待響應 (20-25%)
                    self._log_to_file(progress_file, "⏳ 等待Playwright處理...")
                    self._update_progress_file(progress_file, 0.20, "api_processing", "Playwright正在處理...")
                    
                    # 模擬進度更新（因為我們無法直接監控Playwright的內部進度）
                    self._simulate_processing_progress(progress_file, start_time)
                    
                    response = client.post(self.agent_url, json=payload)
                    response.raise_for_status()
                    result = response.json()
                
                # 階段9: 處理響應 (95-100%)
                self._log_to_file(progress_file, "✅ API請求成功，正在處理響應...")
                self._update_progress_file(progress_file, 0.95, "response_processing", "處理API響應...")
                
                posts_count = len(result.get('posts', []))
                self._log_to_file(progress_file, f"📦 獲取到 {posts_count} 篇貼文")
                
                # 階段10: 完成 (100%)
                # 計算總耗時
                end_time = time.time()
                existing_data = self._read_progress(progress_file)
                start_time = existing_data.get("start_time", end_time)
                total_duration = end_time - start_time
                
                # 在結果中加入計時信息
                result["crawl_duration"] = total_duration
                
                # 保存計時到 session state
                st.session_state.playwright_crawl_duration = total_duration
                
                duration_text = f"{total_duration:.1f} 秒" if total_duration < 60 else f"{total_duration/60:.1f} 分鐘"
                self._log_to_file(progress_file, f"🎉 爬取任務完成！總耗時: {duration_text}")
                self._update_progress_file(progress_file, 1.0, "completed", "爬取完成", final_data=result)
                
                # 🔥 關鍵修復：設定 session_state 觸發結果頁面和自動保存
                st.session_state.playwright_final_data = result
                st.session_state.playwright_crawl_status = "completed"
                st.rerun()
                
            except Exception as e:
                # 檢查是否為超時錯誤，如果是則切換到監控模式
                if "timeout" in str(e).lower() or "TimeoutError" in str(e):
                    # 超時了，切換到任務監控模式
                    self._log_to_file(progress_file, "⏰ API請求超時，切換到後台任務監控模式...")
                    self._update_progress_file(progress_file, 0.25, "monitoring", "切換到監控模式...")
                    
                    # 設定為監控模式，嘗試恢復任務
                    st.session_state.playwright_crawl_status = "monitoring"
                    st.session_state.playwright_task_id = st.session_state.get('playwright_task_id', task_id)
                    st.session_state.playwright_monitoring_start = time.time()
                    st.warning("⏰ 請求超時，已切換到後台任務監控模式。任務仍在後台繼續執行...")
                    st.rerun()
                else:
                    # 檢查是否為並發執行錯誤
                    error_str = str(e).lower()
                    if "busy" in error_str or "running" in error_str or "concurrent" in error_str:
                        error_msg = "已有任務正在執行中，請等待完成後再試"
                        self._log_to_file(progress_file, f"⚠️ {error_msg}")
                        self._update_progress_file(progress_file, 0.0, "error", error_msg, error=str(e))
                    else:
                        # 其他錯誤，記錄並更新狀態
                        error_msg = f"API請求失敗: {e}"
                        self._log_to_file(progress_file, f"❌ {error_msg}")
                        self._update_progress_file(progress_file, 0.0, "error", error_msg, error=str(e))
                
        except Exception as e:
            error_msg = f"背景任務失敗: {e}"
            self._log_to_file(progress_file, f"❌ {error_msg}")
            self._update_progress_file(progress_file, 0.0, "error", error_msg, error=str(e))
    
    def _simulate_processing_progress(self, progress_file: str, start_time: float):
        """模擬處理進度更新"""
        import time
        import threading
        
        def update_progress():
            stages = [
                (0.25, "browser_launch", "啟動瀏覽器..."),
                (0.30, "page_navigation", "導航到用戶頁面..."),
                (0.35, "page_loading", "等待頁面加載..."),
                (0.40, "scroll_start", "開始智能滾動..."),
                (0.50, "url_collection", "收集貼文URLs..."),
                (0.60, "url_processing", "處理貼文URLs..."),
                (0.65, "fill_details_start", "開始補齊詳細數據..."),
                (0.75, "fill_details_progress", "補齊貼文內容和互動數據..."),
                (0.80, "fill_views_start", "開始補齊觀看數..."),
                (0.85, "fill_views_progress", "補齊觀看數據..."),
                (0.90, "deduplication", "去重處理...")
            ]
            
            for progress, stage, description in stages:
                elapsed = time.time() - start_time
                # 如果API已經完成，就不再更新模擬進度
                if elapsed > 900:  # 15分鐘後停止模擬（配合30分鐘超時）
                    break
                    
                self._log_to_file(progress_file, f"📊 {description}")
                self._update_progress_file(progress_file, progress, stage, description)
                time.sleep(8)  # 每8秒更新一次
        
        # 在背景線程中運行進度模擬
        progress_thread = threading.Thread(target=update_progress, daemon=True)
        progress_thread.start()
    
    def _render_progress_stages(self, progress: float, current_stage: str):
        """渲染進度階段圖"""
        st.subheader("📊 爬取流程進度")
        
        # 定義階段及其進度範圍
        stages = [
            ("🔧", "初始化", 0.0, 0.10, ["initialization", "auth_loading"]),
            ("🚀", "發送請求", 0.10, 0.20, ["request_preparation", "api_request"]),
            ("🌐", "瀏覽器處理", 0.20, 0.40, ["api_processing", "browser_launch", "page_navigation", "page_loading"]),
            ("📜", "智能滾動", 0.40, 0.60, ["scroll_start", "url_collection", "url_processing"]),
            ("📝", "補齊數據", 0.60, 0.90, ["fill_details_start", "fill_details_progress", "fill_views_start", "fill_views_progress", "deduplication"]),
            ("✅", "完成處理", 0.90, 1.00, ["response_processing", "completed"])
        ]
        
        # 創建階段顯示
        cols = st.columns(len(stages))
        
        for i, (icon, name, start_progress, end_progress, stage_names) in enumerate(stages):
            with cols[i]:
                # 判斷階段狀態
                if current_stage in stage_names:
                    # 當前階段 - 黃色進行中
                    st.markdown(f"""
                    <div style='text-align: center; padding: 10px; background-color: #FFF3CD; border: 2px solid #FFC107; border-radius: 8px; margin: 5px 0;'>
                        <div style='font-size: 24px;'>{icon}</div>
                        <div style='font-weight: bold; color: #856404;'>{name}</div>
                        <div style='font-size: 12px; color: #856404;'>進行中...</div>
                    </div>
                    """, unsafe_allow_html=True)
                elif progress > end_progress:
                    # 已完成階段 - 綠色
                    st.markdown(f"""
                    <div style='text-align: center; padding: 10px; background-color: #D4EDDA; border: 2px solid #28A745; border-radius: 8px; margin: 5px 0;'>
                        <div style='font-size: 24px;'>{icon}</div>
                        <div style='font-weight: bold; color: #155724;'>{name}</div>
                        <div style='font-size: 12px; color: #155724;'>✓ 完成</div>
                    </div>
                    """, unsafe_allow_html=True)
                elif progress >= start_progress:
                    # 部分完成階段 - 藍色
                    stage_progress = (progress - start_progress) / (end_progress - start_progress)
                    st.markdown(f"""
                    <div style='text-align: center; padding: 10px; background-color: #CCE5FF; border: 2px solid #007BFF; border-radius: 8px; margin: 5px 0;'>
                        <div style='font-size: 24px;'>{icon}</div>
                        <div style='font-weight: bold; color: #004085;'>{name}</div>
                        <div style='font-size: 12px; color: #004085;'>{stage_progress:.0%}</div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    # 未開始階段 - 灰色
                    st.markdown(f"""
                    <div style='text-align: center; padding: 10px; background-color: #F8F9FA; border: 2px solid #DEE2E6; border-radius: 8px; margin: 5px 0;'>
                        <div style='font-size: 24px; opacity: 0.5;'>{icon}</div>
                        <div style='font-weight: bold; color: #6C757D;'>{name}</div>
                        <div style='font-size: 12px; color: #6C757D;'>等待中</div>
                    </div>
                    """, unsafe_allow_html=True)
        
        # 顯示當前階段的詳細信息
        for icon, name, start_progress, end_progress, stage_names in stages:
            if current_stage in stage_names:
                stage_progress = (progress - start_progress) / (end_progress - start_progress) if end_progress > start_progress else 1.0
                stage_progress = max(0.0, min(1.0, stage_progress))
                
                st.info(f"📍 **{name}** 階段進度: {stage_progress:.1%}")
                st.progress(stage_progress)
                break
    
    def _update_progress_file(self, progress_file: str, progress: float, stage: str, current_work: str, final_data: Dict = None, error: str = None):
        """更新進度檔案 + Redis狀態"""
        data = {
            "progress": progress,
            "stage": stage,
            "current_work": current_work
        }
        if final_data:
            data["final_data"] = final_data
        if error:
            data["error"] = error
        
        # 1. 更新本地檔案
        self._write_progress(progress_file, data)
        
        # 2. 同步更新Redis
        self._update_redis_progress(progress_file, progress, stage, current_work, final_data, error)
    
    def _update_redis_progress(self, progress_file: str, progress: float, stage: str, current_work: str = "", final_data: Dict = None, error: str = None):
        """更新Redis中的任務進度"""
        try:
            # 從進度檔案路徑提取 job_id (處理Path物件)
            progress_file_str = str(progress_file) if hasattr(progress_file, '__fspath__') else progress_file
            job_id = progress_file_str.split('_')[-1].replace('.json', '')
            
            from common.redis_client import get_redis_client
            redis_conn = get_redis_client().redis
            
            if redis_conn:
                # 確定任務狀態
                if error:
                    status = 'error'
                elif stage in ['completed', 'api_completed'] or progress >= 1.0:
                    status = 'completed'
                else:
                    status = 'running'
                
                # 更新Redis hash
                redis_data = {
                    'progress': str(progress),
                    'stage': stage,
                    'current_work': current_work,
                    'status': status,
                    'updated': str(time.time())
                }
                
                if error:
                    redis_data['error'] = error
                if final_data:
                    redis_data['final_data'] = json.dumps(final_data)
                
                redis_conn.hset(f"job:{job_id}", mapping=redis_data)
                print(f"📊 Redis進度更新: {job_id[:8]} - {progress:.1%} - {stage}")
                
                # 如果任務完成或失敗，釋放鎖
                if status in ['completed', 'error']:
                    lock_keys = redis_conn.keys("lock:*")
                    for lock_key in lock_keys:
                        lock_value = redis_conn.get(lock_key)
                        if lock_value and self._safe_decode(lock_value) == job_id:
                            redis_conn.delete(lock_key)
                            print(f"🔓 釋放任務鎖: {self._safe_decode(lock_key)}")
                            break
                
        except Exception as e:
            print(f"⚠️ 更新Redis進度失敗: {e}")  # 不中斷主流程
    
    def _log_to_file(self, progress_file: str, message: str):
        """將日誌寫入檔案"""
        timestamp = PlaywrightUtils.get_current_taipei_time().strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] {message}"
        
        # 讀取現有數據
        existing_data = self._read_progress(progress_file)
        log_messages = existing_data.get("log_messages", [])
        log_messages.append(log_msg)
        
        # 限制日誌數量
        if len(log_messages) > 100:
            log_messages = log_messages[-100:]
        
        # 寫回檔案
        self._write_progress(progress_file, {"log_messages": log_messages})
    
    # ---------- 4. 輔助方法 ----------
    def _check_auth_file(self):
        """檢查認證檔案是否存在"""
        return self.auth_file_path.exists()
    
    def _display_database_stats(self):
        """顯示資料庫統計信息"""
        # 檢查是否有緩存的統計信息
        if 'playwright_db_stats_cache' in st.session_state:
            self._render_cached_stats(st.session_state.playwright_db_stats_cache)
            return
        
        # 獲取統計信息
        stats = self.db_handler.get_database_stats()
        
        if "error" in stats:
            st.error(f"❌ 資料庫錯誤: {stats['error']}")
            return
        
        # 保存到緩存
        st.session_state.playwright_db_stats_cache = stats
        
        # 渲染統計信息
        self._render_cached_stats(stats)
    
    def _render_cached_stats(self, stats):
        """渲染 Playwright 專用緩存統計信息"""
        # 顯示總體統計
        total_stats = stats.get("total_stats", {})
        if total_stats:
            st.info(f"""
            **🎭 Playwright 爬蟲統計**
            - 📊 總貼文數: {total_stats.get('total_posts', 0):,}
            - 👥 已爬取用戶: {total_stats.get('total_users', 0)} 個
            - 🔄 總爬取次數: {total_stats.get('total_crawls', 0):,}
            - ⏰ 最後活動: {str(total_stats.get('latest_activity', 'N/A'))[:16] if total_stats.get('latest_activity') else 'N/A'}
            """)
        
        # 顯示用戶統計
        user_stats = stats.get("user_stats", [])
        if user_stats:
            st.write("**👥 各用戶統計 (Playwright):**")
            
            import pandas as pd
            df_data = []
            for user in user_stats:
                latest = str(user.get('latest_crawl', 'N/A'))[:16] if user.get('latest_crawl') else 'N/A'
                crawl_id = user.get('latest_crawl_id', 'N/A')[:12] + '...' if user.get('latest_crawl_id') else 'N/A'
                df_data.append({
                    "用戶名": f"@{user.get('username', 'N/A')}",
                    "貼文數": f"{user.get('post_count', 0):,}",
                    "最後爬取": latest,
                    "最新爬取ID": crawl_id
                })
            
            if df_data:
                df = pd.DataFrame(df_data)
                st.dataframe(
                    df, 
                    use_container_width=True,
                    hide_index=True,
                    height=min(300, len(df_data) * 35 + 38)
                )
                
                st.caption("💡 這是 Playwright 爬蟲的專用統計，與 Realtime 爬蟲分離儲存")
                
                # 添加用戶資料管理功能（折疊形式）
                st.markdown("---")
                self.user_manager.manage_user_data(user_stats)
        else:
            st.warning("📝 Playwright 資料庫中暫無爬取記錄")
    
    def _show_results(self, results: Dict):
        """顯示爬取結果（完整版本）"""
        posts = results.get("results", [])
        
        st.subheader("📊 爬取結果")
        
        if not isinstance(posts, list):
            st.error("❌ 結果格式錯誤，請重新載入")
            return
        
        if not posts:
            st.warning("⚠️ 沒有找到任何結果")
            return
        
        # 詳細統計
        total_posts = len(posts)
        success_posts = sum(1 for r in posts if r.get('success', False))
        content_posts = sum(1 for r in posts if r.get('content'))
        views_posts = sum(1 for r in posts if r.get('views_count') or r.get('views'))
        
        # 統計區域
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("總貼文數", total_posts)
        with col2:
            st.metric("成功獲取", success_posts)
        with col3:
            st.metric("有內容", content_posts)
        with col4:
            st.metric("有觀看數", views_posts)
        
        # 顯示爬取耗時
        crawl_duration = results.get("crawl_duration") or st.session_state.get('playwright_crawl_duration')
        if crawl_duration is not None:
            st.markdown("---")
            if crawl_duration < 60:
                duration_display = f"{crawl_duration:.1f} 秒"
                delta_color = "normal" if crawl_duration <= 30 else "inverse"
            else:
                duration_display = f"{crawl_duration/60:.1f} 分鐘"
                delta_color = "inverse"
            
            col_time = st.columns(1)[0]
            with col_time:
                st.metric(
                    label="⏱️ 爬取耗時", 
                    value=duration_display,
                    help="從開始爬取到完成的總時間"
                )
        
        # 互動統計
        if views_posts > 0:
            st.subheader("📈 互動統計")
            
            total_views = 0
            total_likes = 0
            total_comments = 0
            total_reposts = 0
            
            for r in posts:
                views = self._safe_int(r.get('views_count', r.get('views', 0)))
                likes = self._safe_int(r.get('likes_count', r.get('likes', 0)))
                comments = self._safe_int(r.get('comments_count', r.get('comments', 0)))
                reposts = self._safe_int(r.get('reposts_count', r.get('reposts', 0)))
                
                total_views += views
                total_likes += likes
                total_comments += comments
                total_reposts += reposts
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("總觀看數", f"{total_views:,}")
            with col2:
                st.metric("總按讚數", f"{total_likes:,}")
            with col3:
                st.metric("總留言數", f"{total_comments:,}")
            with col4:
                st.metric("總分享數", f"{total_reposts:,}")
        
        # 詳細結果表格
        if st.checkbox("📋 顯示詳細結果", key="show_playwright_detailed_results_v2"):
            # 內容顯示選項
            col_option1, col_option2 = st.columns([1, 1])
            with col_option1:
                show_full_content = st.checkbox("📖 顯示完整內容", key="show_full_content_v2", help="勾選後將顯示完整貼文內容，而非預覽")
            
            st.write("**📋 詳細結果:**")
            
            table_data = []
            for i, r in enumerate(posts, 1):
                # 🔧 修復：分離 post_id 顯示
                original_post_id = r.get('post_id', 'N/A')
                if '_' in original_post_id and original_post_id != 'N/A':
                    # 分離格式：username_realpostid
                    parts = original_post_id.split('_', 1)
                    extracted_username = parts[0] if len(parts) > 1 else ''
                    real_post_id = parts[1] if len(parts) > 1 else original_post_id
                else:
                    extracted_username = ''
                    real_post_id = original_post_id
                
                # 處理 tags 顯示
                tags = r.get('tags', [])
                tags_display = ", ".join(tags) if tags else "無"
                
                # 🔧 修復：處理圖片詳細資訊
                images = r.get('images', [])
                images_count = len(images) if images else 0
                images_display = "、".join(images[:3]) + (f"...等{images_count}個" if images_count > 3 else "") if images else "無"
                
                # 🔧 修復：處理影片詳細資訊
                videos = r.get('videos', [])
                videos_count = len(videos) if videos else 0
                videos_display = "、".join(videos[:3]) + (f"...等{videos_count}個" if videos_count > 3 else "") if videos else "無"
                
                # 🔧 新增：貼文URL顯示
                post_url = r.get('url', '')
                post_url_display = post_url if post_url else "無"
                
                # 處理時間顯示 - 轉換為台北時間
                created_at = r.get('created_at', '')
                if created_at:
                    taipei_created = PlaywrightUtils.convert_to_taipei_time(created_at)
                    created_at = taipei_created.isoformat() if taipei_created else created_at
                
                published_at = r.get('post_published_at', '')
                if published_at:
                    taipei_published = PlaywrightUtils.convert_to_taipei_time(published_at)
                    published_at = taipei_published.isoformat() if taipei_published else published_at
                
                # 格式化計算分數
                calc_score = r.get('calculated_score', 'N/A')
                if calc_score != 'N/A' and calc_score is not None:
                    try:
                        calc_score_formatted = f"{float(calc_score):,.1f}"
                    except:
                        calc_score_formatted = str(calc_score)
                else:
                    calc_score_formatted = 'N/A'
                
                # 格式化數量顯示
                def format_count(value):
                    if value in [None, '', 'N/A']:
                        return 'N/A'
                    try:
                        return f"{int(value):,}"
                    except:
                        return str(value)
                
                # 處理時間字段 - 轉換為台北時間
                published_taipei = 'N/A'
                created_taipei = 'N/A'
                
                if published_at:
                    try:
                        taipei_published = PlaywrightUtils.convert_to_taipei_time(published_at)
                        if taipei_published:
                            published_taipei = taipei_published.strftime('%Y-%m-%d %H:%M:%S')
                    except:
                        published_taipei = published_at[:19]
                
                if created_at:
                    try:
                        taipei_created = PlaywrightUtils.convert_to_taipei_time(created_at)
                        if taipei_created:
                            created_taipei = taipei_created.strftime('%Y-%m-%d %H:%M:%S')
                    except:
                        created_taipei = created_at[:19]
                
                table_data.append({
                    "#": i,
                    "用戶ID": extracted_username or r.get('username', 'N/A'),  # 🔧 修復：顯示分離的用戶ID
                    "貼文ID": real_post_id,  # 🔧 修復：顯示真實的貼文ID
                    "貼文URL": post_url_display,  # 🔧 新增：貼文URL
                    "內容" if show_full_content else "內容預覽": r.get('content', 'N/A') if show_full_content else ((r.get('content', '')[:60] + "...") if r.get('content') and len(r.get('content', '')) > 60 else r.get('content', 'N/A')),
                    "觀看數": format_count(r.get('views_count', r.get('views', 'N/A'))),
                    "按讚": format_count(r.get('likes_count', r.get('likes', 'N/A'))),
                    "留言": format_count(r.get('comments_count', r.get('comments', 'N/A'))),
                    "轉發": format_count(r.get('reposts_count', r.get('reposts', 'N/A'))),
                    "分享": format_count(r.get('shares_count', r.get('shares', 'N/A'))),
                    "計算分數": calc_score_formatted,
                    "標籤": tags_display,
                    "圖片": images_display,  # 🔧 修復：顯示圖片URL詳細資訊
                    "影片": videos_display,  # 🔧 修復：顯示影片URL詳細資訊
                    "發布時間": published_taipei,  # 🔧 台北時間
                    "爬取時間": created_taipei,    # 🔧 台北時間
                    "狀態": "✅" if r.get('success') else "❌"
                })
            
            # 🔧 優化dataframe顯示，避免截斷
            st.dataframe(
                table_data, 
                use_container_width=True, 
                height=400,
                column_config={
                    "用戶ID": st.column_config.TextColumn(width="small"),
                    "貼文ID": st.column_config.TextColumn(width="medium"),
                    "貼文URL": st.column_config.LinkColumn(width="medium"),  # 🔧 新增：URL欄位
                    "內容" if show_full_content else "內容預覽": st.column_config.TextColumn(width="large"),
                    "標籤": st.column_config.TextColumn(width="medium"),
                    "圖片": st.column_config.TextColumn(width="medium"),  # 🔧 新增：圖片欄位
                    "影片": st.column_config.TextColumn(width="medium"),  # 🔧 新增：影片欄位
                    "發布時間": st.column_config.TextColumn(width="small"),
                    "爬取時間": st.column_config.TextColumn(width="small")
                }
            )
        
        # 資料庫狀態
        db_saved = results.get('database_saved', False)
        saved_count = results.get('database_saved_count', 0)
        if db_saved:
            st.success(f"✅ 已保存到資料庫 ({saved_count} 個貼文)")
        else:
            col_info, col_save = st.columns([3, 1])
            with col_info:
                st.info("ℹ️ 如果統計中沒有看到新數據，您可以使用備用保存功能")
            with col_save:
                if st.button("💾 備用保存", key="save_playwright_to_database_v2"):
                    result = self.db_handler.save_results_to_database_sync(results)
                    if result.get("success"):
                        st.success(f"✅ 保存成功！保存了 {result.get('saved_count', 0)} 個貼文")
                    else:
                        st.error(f"❌ 保存失敗: {result.get('error', '未知錯誤')}")
        
        st.divider()
        
        # 更多導出功能
        st.subheader("📤 更多導出")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            # 直接下載JSON（使用安全的序列化器）
            def safe_json_serializer(obj):
                from decimal import Decimal
                from datetime import datetime, date
                if isinstance(obj, Decimal):
                    return float(obj)
                elif isinstance(obj, (datetime, date)):
                    return obj.isoformat()
                raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
            
            json_content = json.dumps(results, ensure_ascii=False, indent=2, default=safe_json_serializer)
            timestamp = PlaywrightUtils.get_current_taipei_time().strftime('%Y%m%d_%H%M%S')
            download_filename = f"playwright_crawl_results_{timestamp}.json"
            
            st.download_button(
                label="💾 下載JSON",
                data=json_content,
                file_name=download_filename,
                mime="application/json",
                help="直接下載爬取結果JSON文件",
                key="download_playwright_json_v2"
            )
        
        with col2:
            # 直接下載CSV
            if posts:
                import pandas as pd
                import io
                
                # 準備CSV數據（與 JSON 格式完全一致）
                csv_data = []
                
                # 🔧 修復：從結果中獲取正確的目標用戶名稱
                target_username = results.get("target_username", "")
                if not target_username:
                    # 嘗試從 session state 中獲取
                    target = st.session_state.get('playwright_target', {})
                    target_username = target.get('username', "")
                
                for r in posts:
                    # 🔧 修復：分離 post_id 為 user_id 和 real_post_id
                    original_post_id = r.get('post_id', '')
                    if '_' in original_post_id and original_post_id:
                        parts = original_post_id.split('_', 1)
                        user_id = parts[0] if len(parts) > 1 else ''
                        real_post_id = parts[1] if len(parts) > 1 else original_post_id
                    else:
                        user_id = r.get('username', '') or target_username
                        real_post_id = original_post_id
                    
                    # 處理 tags 陣列
                    tags_str = "|".join(r.get('tags', [])) if r.get('tags') else ""
                    
                    # 處理 images 陣列
                    images_str = "|".join(r.get('images', [])) if r.get('images') else ""
                    
                    # 處理 videos 陣列
                    videos_str = "|".join(r.get('videos', [])) if r.get('videos') else ""
                    
                    # 🔧 處理時間字段 - 轉換為台北時間
                    created_at = r.get('created_at', '')
                    if created_at:
                        try:
                            taipei_created = PlaywrightUtils.convert_to_taipei_time(created_at)
                            created_at = taipei_created.isoformat() if taipei_created else created_at
                        except:
                            pass  # 保持原始值
                    
                    post_published_at = r.get('post_published_at', '')
                    if post_published_at:
                        try:
                            taipei_published = PlaywrightUtils.convert_to_taipei_time(post_published_at)
                            post_published_at = taipei_published.isoformat() if taipei_published else post_published_at
                        except:
                            pass  # 保持原始值
                    
                    extracted_at = r.get('extracted_at', '')
                    if extracted_at:
                        try:
                            taipei_extracted = PlaywrightUtils.convert_to_taipei_time(extracted_at)
                            extracted_at = taipei_extracted.isoformat() if taipei_extracted else extracted_at
                        except:
                            pass  # 保持原始值
                    
                    csv_data.append({
                        "url": r.get('url', ''),
                        "post_id": original_post_id,  # 🔧 保留原始格式供向後兼容
                        "user_id": user_id,  # 🔧 新增：分離的用戶ID
                        "real_post_id": real_post_id,  # 🔧 新增：真實的貼文ID
                        "username": user_id or (r.get('username', '') or target_username),  # 🔧 修復：使用分離的user_id
                        "content": r.get('content', ''),  # 🔧 保持完整內容，不截斷
                        "likes_count": r.get('likes_count', r.get('likes', '')),
                        "comments_count": r.get('comments_count', r.get('comments', '')),
                        "reposts_count": r.get('reposts_count', r.get('reposts', '')),
                        "shares_count": r.get('shares_count', r.get('shares', '')),
                        "views_count": r.get('views_count', r.get('views', '')),
                        "calculated_score": r.get('calculated_score', ''),
                        "created_at": created_at,          # 🔧 台北時間
                        "post_published_at": post_published_at,  # 🔧 台北時間
                        "tags": tags_str,
                        "images": images_str,  # 🔧 圖片URL清單
                        "videos": videos_str,  # 🔧 影片URL清單
                        "source": r.get('source', 'playwright_agent'),
                        "crawler_type": r.get('crawler_type', 'playwright'),
                        "crawl_id": r.get('crawl_id', ''),
                        "extracted_at": extracted_at,     # 🔧 台北時間
                        "success": r.get('success', True)
                    })
                
                df = pd.DataFrame(csv_data)
                # 修復 CSV 編碼問題 - 直接生成帶BOM的UTF-8字節內容
                csv_content = df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
                
                csv_filename = f"playwright_crawl_results_{timestamp}.csv"
                
                st.download_button(
                    label="📊 下載CSV",
                    data=csv_content,
                    file_name=csv_filename,
                    mime="text/csv",
                    help="直接下載爬取結果CSV文件",
                    key="download_playwright_csv_v2"
                )
            else:
                st.button("📊 下載CSV", disabled=True, help="沒有數據可下載")
        
        with col3:
            if st.button("📈 歷史分析", key="playwright_history_analysis_v2"):
                # 切換歷史分析面板的可見性
                st.session_state.show_playwright_history_analysis = not st.session_state.get('show_playwright_history_analysis', False)
                st.rerun()
            
        # 顯示歷史分析面板（如果啟用）
        if st.session_state.get('show_playwright_history_analysis', False):
            self._show_history_analysis_options()
        
        with col4:
            if st.button("🔍 更多導出", key="playwright_more_exports_v2"):
                # 切換更多導出面板的可見性
                st.session_state.show_playwright_advanced_exports = not st.session_state.get('show_playwright_advanced_exports', False)
                st.rerun()
            
        # 顯示更多導出面板（如果啟用）
        if st.session_state.get('show_playwright_advanced_exports', False):
            self.export_handler.show_advanced_export_options()
    
    def _safe_int(self, value):
        """安全轉換為整數"""
        try:
            if isinstance(value, (int, float)):
                return int(value)
            if isinstance(value, str):
                # 處理 1.2K, 1.5M 格式
                value = value.replace(',', '').replace(' ', '')
                if 'K' in value:
                    return int(float(value.replace('K', '')) * 1000)
                elif 'M' in value:
                    return int(float(value.replace('M', '')) * 1000000)
                elif 'B' in value:
                    return int(float(value.replace('B', '')) * 1000000000)
                else:
                    return int(float(value))
            return 0
        except:
            return 0
    

    
    def _show_history_analysis_options(self):
        """顯示歷史分析選項"""
        # 嘗試從多個來源獲取用戶名
        target_username = None
        
        # 方法1：從當前結果獲取
        if 'playwright_results' in st.session_state:
            results = st.session_state.playwright_results
            if results:
                target_username = results.get('target_username')
        
        # 方法2：從當前爬取目標獲取
        if not target_username and 'playwright_target' in st.session_state:
            target = st.session_state.playwright_target
            if target:
                target_username = target.get('username')
        
        # 方法3：讓用戶手動輸入
        if not target_username:
            st.info("💡 請輸入要分析的帳號名稱")
            target_username = st.text_input(
                "帳號名稱", 
                placeholder="例如: natgeo", 
                key="playwright_history_username_input"
            )
            
            if not target_username:
                st.warning("⚠️ 請輸入帳號名稱以繼續歷史分析")
                return
        
        with st.expander("📈 歷史數據導出選項", expanded=True):
            # 添加關閉按鈕
            col_title, col_close = st.columns([4, 1])
            with col_title:
                st.write(f"**目標帳號:** @{target_username}")
            with col_close:
                if st.button("❌ 關閉", key="close_playwright_history_analysis"):
                    st.session_state.show_playwright_history_analysis = False
                    st.rerun()
            
            # 排序選項
            st.subheader("📊 排序設定")
            col_sort1, col_sort2 = st.columns(2)
            
            with col_sort1:
                sort_by = st.selectbox(
                    "排序依據",
                    options=["fetched_at", "views_count", "likes_count", "comments_count", "calculated_score", "post_published_at"],
                    format_func=lambda x: {
                        "fetched_at": "爬取時間",
                        "views_count": "觀看數",
                        "likes_count": "按讚數", 
                        "comments_count": "留言數",
                        "calculated_score": "計算分數",
                        "post_published_at": "發布時間"
                    }.get(x, x),
                    key="playwright_history_sort_by"
                )
            
            with col_sort2:
                sort_order = st.selectbox(
                    "排序順序",
                    options=["DESC", "ASC"],
                    format_func=lambda x: "降序 (高到低)" if x == "DESC" else "升序 (低到高)",
                    key="playwright_history_sort_order"
                )
            
            st.divider()
            
            # 導出類型
            export_type = st.radio(
                "選擇導出類型",
                options=["最近數據", "全部歷史", "統計分析"],
                help="選擇要導出的歷史數據範圍",
                key="playwright_history_export_type"
            )
            
            col1, col2 = st.columns(2)
            
            if export_type == "最近數據":
                with col1:
                    days_back = st.number_input("回溯天數", min_value=1, max_value=365, value=7, key="playwright_days_back")
                with col2:
                    limit = st.number_input("最大記錄數", min_value=10, max_value=10000, value=1000, key="playwright_limit_recent")
                
                if st.button("📊 導出最近數據", key="playwright_export_recent"):
                    self.export_handler.export_history_data(target_username, "recent", 
                                            days_back=days_back, limit=limit, 
                                            sort_by=sort_by, sort_order=sort_order)
            
            elif export_type == "全部歷史":
                with col1:
                    limit = st.number_input("最大記錄數", min_value=100, max_value=50000, value=5000, key="playwright_limit_all")
                
                if st.button("📊 導出全部歷史", key="playwright_export_all"):
                    self.export_handler.export_history_data(target_username, "all", 
                                            limit=limit, sort_by=sort_by, sort_order=sort_order)
            
            elif export_type == "統計分析":
                st.info("按日期統計的分析報告，包含平均觀看數、成功率等指標")
                
                if st.button("📈 導出統計分析", key="playwright_export_analysis"):
                    self.export_handler.export_history_data(target_username, "analysis", 
                                            sort_by=sort_by, sort_order=sort_order)
    
    # _export_history_data 方法已移至 PlaywrightDataExportHandler
    
    # _fetch_history_from_db 方法已移至 PlaywrightDataExportHandler
    
    # _calculate_stats 方法已移至 PlaywrightDataExportHandler
    
    # _convert_to_csv 方法已移至 PlaywrightDataExportHandler (公開為 convert_to_csv)
    
    # _show_advanced_export_options 方法已移至 PlaywrightDataExportHandler (公開為 show_advanced_export_options)
    
    # _extract_time_from_filename 方法已移至 PlaywrightDataExportHandler
    
    # _generate_comparison_report 方法已移至 PlaywrightDataExportHandler
    
    # _export_all_latest_results 方法已移至 PlaywrightDataExportHandler
    
    # _export_all_account_stats 方法已移至 PlaywrightDataExportHandler
    
    # _cleanup_temp_files 方法已移至 PlaywrightDataExportHandler
    
    # _copy_results_summary 方法已移至 PlaywrightDataExportHandler
    
    # _generate_share_link 方法已移至 PlaywrightDataExportHandler
    
    # _clear_results 方法已移至 PlaywrightDataExportHandler (公開為 clear_results)
    
    # _load_csv_file 方法已移至 PlaywrightDataExportHandler (公開為 load_csv_file)
    
    # ---------- 佇列管理方法 ----------
    def _auto_process_queue(self):
        """自動處理佇列 - 檢查是否需要開始下一個任務"""
        if not self.queue_component:
            return
        
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
    
    def _add_to_queue(self, username: str, max_posts: int, enable_deduplication: bool, is_incremental: bool):
        """將任務加入佇列"""
        if not self.queue_manager:
            st.error("❌ 佇列管理器不可用，使用原版爬蟲")
            self._start_crawling(username, max_posts, enable_deduplication, is_incremental)
            return
        
        try:
            # 生成新的任務 ID
            task_id = str(uuid.uuid4())
            
            # 確定爬取模式
            mode = "new" if is_incremental else "hist"
            
            # 加入佇列
            if self.queue_manager.add_task(task_id, username, max_posts, mode):
                st.session_state.playwright_task_id = task_id
                
                # 檢查佇列位置
                position = self.queue_component.get_queue_position(task_id)
                if position == 1:
                    st.success("✅ 任務已加入佇列，即將開始執行")
                    st.session_state.playwright_crawl_status = "running"
                else:
                    st.success(f"✅ 任務已加入佇列，排隊位置: #{position}")
                    st.session_state.playwright_crawl_status = "running"
                    st.rerun()
            else:
                st.error("❌ 加入佇列失敗")
            
        except Exception as e:
            st.error(f"❌ 發生錯誤: {e}")
    
    def _start_crawl_from_queue_task(self, task):
        """從佇列任務開始爬蟲"""
        try:
            # 🔧 修復：將模式轉換為布林值
            is_incremental = (task.mode == "new")
            enable_deduplication = True  # 預設啟用去重
            
            # 🔧 重要修復：使用佇列中的 task_id，確保進度文件和任務ID一致
            self._start_crawling(
                username=task.username,
                max_posts=task.max_posts,
                enable_deduplication=enable_deduplication,
                is_incremental=is_incremental,
                task_id=task.task_id  # 🔥 關鍵修復：使用佇列中的 task_id
            )
            
            # task_id 已經在 _start_crawling 中正確設置了
            print(f"✅ 佇列任務已啟動: {task.username} (ID: {task.task_id[:8]}...)")
            
        except Exception as e:
            print(f"❌ 佇列任務啟動失敗: {e}")
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
    

    

