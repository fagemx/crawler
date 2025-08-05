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

class PlaywrightCrawlerComponentV2:
    def __init__(self):
        self.agent_url = "http://localhost:8006/v1/playwright/crawl"
        self.sse_url = "http://localhost:8000/stream"
        
        # 初始化子組件
        self.db_handler = PlaywrightDatabaseHandler()
        self.user_manager = PlaywrightUserManager()
        
        # 使用統一的配置管理
        from common.config import get_auth_file_path
        self.auth_file_path = get_auth_file_path(from_project_root=True)
    
    # ---------- 1. 進度檔案讀寫工具 ----------
    def _write_progress(self, path: str, data: Dict[str, Any]):
        """
        線程安全寫入進度：
        - 使用 tempfile + shutil.move 實現原子寫入，避免讀取到不完整的檔案。
        """
        old: Dict[str, Any] = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
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

        # 原子寫入
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(old, f, ensure_ascii=False, indent=2)
            shutil.move(tmp_path, path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def _read_progress(self, path: str) -> Dict[str, Any]:
        """讀取進度檔案"""
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
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
        
        st.header("🎭 Playwright 智能爬蟲 V2")
        st.markdown("**基於檔案讀寫架構 + 狀態機驅動的實時進度顯示**")
        
        # 檢查認證文件
        if not self._check_auth_file():
            st.error("❌ 找不到認證檔案")
            st.info("請先執行: `python tests/threads_fetch/save_auth.py` 來產生認證檔案")
            return
        
        st.success("✅ 認證檔案已就緒")
        
        # 初始化狀態
        if "playwright_crawl_status" not in st.session_state:
            st.session_state.playwright_crawl_status = "idle"
        
        # 根據狀態渲染不同內容
        if st.session_state.playwright_crawl_status == "idle":
            self._render_setup()
        elif st.session_state.playwright_crawl_status == "running":
            self._render_progress()
        elif st.session_state.playwright_crawl_status == "completed":
            self._render_results()
        elif st.session_state.playwright_crawl_status == "error":
            self._render_error()
    
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
            
            if enable_deduplication:
                st.info("💡 將根據觀看數、互動數、內容長度等維度保留主貼文，過濾回應")
            else:
                st.warning("⚠️ 關閉去重可能會獲得大量相似內容，建議僅在特殊需求時使用")
            
            # 控制按鈕區域
            col1, col2, col3 = st.columns([1, 1, 2])
            
            with col1:
                if st.button("🚀 開始爬取", key="start_playwright_v2"):
                    # 啟動爬蟲
                    is_incremental = (crawl_mode == "增量模式")
                    self._start_crawling(username, max_posts, enable_deduplication, is_incremental)
                    
            with col2:
                try:
                    uploaded_file = st.file_uploader(
                        "📁 載入CSV文件", 
                        type=['csv'], 
                        key="playwright_csv_uploader_v2",
                        help="上傳之前導出的CSV文件來查看結果"
                    )
                    if uploaded_file is not None:
                        self._load_csv_file(uploaded_file)
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
                        self._clear_results()
                
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
        if progress_file and os.path.exists(progress_file):
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

        st.info(f"🔄 正在爬取 @{username} 的貼文...")
        st.progress(max(0.0, min(1.0, progress)), text=f"{progress:.1%} - {current_work}")
        
        # 顯示詳細階段信息
        if progress_file and os.path.exists(progress_file):
            progress_data = self._read_progress(progress_file)
            if progress_data:
                stage = progress_data.get("stage", "unknown")
                stage_names = {
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
        if st.session_state.playwright_crawl_status == 'running':
            time.sleep(1) # 降低刷新頻率
            st.rerun()
    
    def _render_results(self):
        """渲染結果頁面"""
        st.subheader("✅ 爬取完成")
        
        final_data = st.session_state.get('playwright_final_data', {})
        if not final_data:
            st.warning("沒有爬取到數據")
            if st.button("🔙 返回設定"):
                st.session_state.playwright_crawl_status = "idle"
                # 重置保存標記，準備下次爬取
                st.session_state.playwright_results_saved = False
                st.rerun()
            return
        
        # 處理並顯示結果
        try:
            # 轉換結果格式
            converted_results = PlaywrightUtils.convert_playwright_results(final_data)
            target = st.session_state.get('playwright_target', {})
            converted_results["target_username"] = target.get('username', 'unknown')
            
            # 檢查是否已經保存過，避免重複保存
            if not st.session_state.get('playwright_results_saved', False):
                # 保存JSON文件
                json_file_path = PlaywrightUtils.save_json_results(converted_results)
                st.session_state.playwright_results_saved = True  # 標記為已保存
            else:
                # 如果已經保存過，不再重新保存，但仍需要顯示結果
                json_file_path = None
            
            # 自動保存到資料庫
            try:
                asyncio.run(self.db_handler.save_to_database_async(converted_results))
                converted_results["database_saved"] = True
                converted_results["database_saved_count"] = len(converted_results.get("results", []))
                st.success(f"✅ 已自動保存 {converted_results['database_saved_count']} 個貼文到資料庫")
            except Exception as db_error:
                converted_results["database_saved"] = False
                converted_results["database_saved_count"] = 0
                st.warning(f"⚠️ 自動保存到資料庫失敗: {db_error}")
                st.info("💡 您可以稍後使用 '💾 備用保存' 按鈕重試")
            
            # 顯示結果
            self._show_results(converted_results)
            
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
    def _start_crawling(self, username: str, max_posts: int, enable_deduplication: bool = True, is_incremental: bool = True):
        """啟動爬蟲"""
        # 設定目標參數
        st.session_state.playwright_target = {
            'username': username,
            'max_posts': max_posts,
            'enable_deduplication': enable_deduplication,
            'is_incremental': is_incremental
        }
        
        # 重置保存標記，允許新的爬取結果被保存
        st.session_state.playwright_results_saved = False
        
        # 創建進度檔案
        task_id = str(uuid.uuid4())
        progress_file = f"temp_playwright_progress_{task_id}.json"
        st.session_state.playwright_progress_file = progress_file
        st.session_state.playwright_task_id = task_id
        
        # 初始化進度檔案
        self._write_progress(progress_file, {
            "progress": 0.0,
            "stage": "initialization",
            "current_work": "正在啟動...",
            "log_messages": ["🚀 爬蟲任務已啟動..."]
        })
        
        # 啟動背景線程
        task_thread = threading.Thread(
            target=self._background_crawler_worker,
            args=(username, max_posts, enable_deduplication, is_incremental, task_id, progress_file),
            daemon=True
        )
        task_thread.start()
        
        # 切換到進度頁面
        st.session_state.playwright_crawl_status = "running"
        st.rerun()
    
    def _background_crawler_worker(self, username: str, max_posts: int, enable_deduplication: bool, is_incremental: bool, task_id: str, progress_file: str):
        """背景爬蟲工作線程 - 只寫檔案，不做任何 st.* 操作"""
        try:
            # 階段1: 初始化 (0-5%)
            self._log_to_file(progress_file, "🔧 初始化爬蟲環境...")
            self._update_progress_file(progress_file, 0.02, "initialization", "初始化爬蟲環境...")
            
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
                "incremental": is_incremental
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
                
                with httpx.Client(timeout=600.0) as client:
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
                self._log_to_file(progress_file, "🎉 爬取任務完成！")
                self._update_progress_file(progress_file, 1.0, "completed", "爬取完成", final_data=result)
                
            except Exception as e:
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
                if elapsed > 300:  # 5分鐘後停止模擬
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
        """更新進度檔案"""
        data = {
            "progress": progress,
            "stage": stage,
            "current_work": current_work
        }
        if final_data:
            data["final_data"] = final_data
        if error:
            data["error"] = error
        
        self._write_progress(progress_file, data)
    
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
                # 處理 tags 顯示
                tags = r.get('tags', [])
                tags_display = ", ".join(tags) if tags else "無"
                
                # 處理圖片數量
                images = r.get('images', [])
                images_count = len(images) if images else 0
                
                # 處理影片數量
                videos = r.get('videos', [])
                videos_count = len(videos) if videos else 0
                
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
                
                table_data.append({
                    "#": i,
                    "貼文ID": r.get('post_id', 'N/A')[:20] + "..." if len(r.get('post_id', '')) > 20 else r.get('post_id', 'N/A'),
                    "用戶名": r.get('username', 'N/A'),
                    "內容" if show_full_content else "內容預覽": r.get('content', 'N/A') if show_full_content else ((r.get('content', '')[:60] + "...") if r.get('content') and len(r.get('content', '')) > 60 else r.get('content', 'N/A')),
                    "觀看數": format_count(r.get('views_count', r.get('views', 'N/A'))),
                    "按讚": format_count(r.get('likes_count', r.get('likes', 'N/A'))),
                    "留言": format_count(r.get('comments_count', r.get('comments', 'N/A'))),
                    "轉發": format_count(r.get('reposts_count', r.get('reposts', 'N/A'))),
                    "分享": format_count(r.get('shares_count', r.get('shares', 'N/A'))),
                    "計算分數": calc_score_formatted,
                    "標籤": tags_display,
                    "圖片數": images_count,
                    "影片數": videos_count,
                    "發布時間": published_at[:19] if published_at else 'N/A',
                    "爬取時間": created_at[:19] if created_at else 'N/A',
                    "狀態": "✅" if r.get('success') else "❌"
                })
            
            st.dataframe(table_data, use_container_width=True, height=400)
        
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
                for r in posts:
                    # 處理 tags 陣列
                    tags_str = "|".join(r.get('tags', [])) if r.get('tags') else ""
                    
                    # 處理 images 陣列
                    images_str = "|".join(r.get('images', [])) if r.get('images') else ""
                    
                    # 處理 videos 陣列
                    videos_str = "|".join(r.get('videos', [])) if r.get('videos') else ""
                    
                    csv_data.append({
                        "url": r.get('url', ''),
                        "post_id": r.get('post_id', ''),
                        "username": r.get('username', ''),
                        "content": r.get('content', ''),
                        "likes_count": r.get('likes_count', r.get('likes', '')),
                        "comments_count": r.get('comments_count', r.get('comments', '')),
                        "reposts_count": r.get('reposts_count', r.get('reposts', '')),
                        "shares_count": r.get('shares_count', r.get('shares', '')),
                        "views_count": r.get('views_count', r.get('views', '')),
                        "calculated_score": r.get('calculated_score', ''),
                        "created_at": r.get('created_at', ''),
                        "post_published_at": r.get('post_published_at', ''),
                        "tags": tags_str,
                        "images": images_str,
                        "videos": videos_str,
                        "source": r.get('source', 'playwright_agent'),
                        "crawler_type": r.get('crawler_type', 'playwright'),
                        "crawl_id": r.get('crawl_id', ''),
                        "extracted_at": r.get('extracted_at', ''),
                        "success": r.get('success', True)
                    })
                
                df = pd.DataFrame(csv_data)
                # 修復 CSV 編碼問題 - 使用字節流確保正確編碼
                import io
                output = io.BytesIO()
                df.to_csv(output, index=False, encoding='utf-8-sig')
                csv_content = output.getvalue()
                
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
            self._show_advanced_export_options()
    
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
                    self._export_history_data(target_username, "recent", 
                                            days_back=days_back, limit=limit, 
                                            sort_by=sort_by, sort_order=sort_order)
            
            elif export_type == "全部歷史":
                with col1:
                    limit = st.number_input("最大記錄數", min_value=100, max_value=50000, value=5000, key="playwright_limit_all")
                
                if st.button("📊 導出全部歷史", key="playwright_export_all"):
                    self._export_history_data(target_username, "all", 
                                            limit=limit, sort_by=sort_by, sort_order=sort_order)
            
            elif export_type == "統計分析":
                st.info("按日期統計的分析報告，包含平均觀看數、成功率等指標")
                
                if st.button("📈 導出統計分析", key="playwright_export_analysis"):
                    self._export_history_data(target_username, "analysis", 
                                            sort_by=sort_by, sort_order=sort_order)
    
    def _export_history_data(self, username: str, export_type: str, **kwargs):
        """導出歷史數據"""
        try:
            import asyncio
            
            # 獲取排序參數
            sort_by = kwargs.get('sort_by', 'fetched_at')
            sort_order = kwargs.get('sort_order', 'DESC')
            
            with st.spinner(f"🔄 正在從資料庫獲取 @{username} 的{export_type}數據..."):
                # 異步獲取資料庫數據
                posts_data = asyncio.run(self._fetch_history_from_db(username, export_type, **kwargs))
            
            if not posts_data:
                st.warning(f"⚠️ 沒有找到用戶 @{username} 的歷史數據")
                return
            
            # 排序數據
            def get_sort_key(post):
                value = post.get(sort_by, 0)
                if value is None:
                    return 0
                if isinstance(value, str):
                    try:
                        return float(value)
                    except:
                        return 0
                return value
            
            posts_data.sort(key=get_sort_key, reverse=(sort_order == 'DESC'))
            
            # 準備數據結構
            data = {
                "username": username,
                "export_type": export_type,
                "exported_at": PlaywrightUtils.get_current_taipei_time().isoformat(),
                "sort_by": sort_by,
                "sort_order": sort_order,
                "total_records": len(posts_data),
                "data": posts_data
            }
            
            # 添加統計信息
            if export_type == "analysis":
                data["summary"] = self._calculate_stats(posts_data)
            
            # 同時提供 JSON 和 CSV 下載
            col1, col2 = st.columns(2)
            
            with col1:
                # JSON 下載
                import json
                from decimal import Decimal
                from datetime import datetime, date
                
                # 自定義JSON編碼器處理Decimal和datetime類型
                def json_serializer(obj):
                    if isinstance(obj, Decimal):
                        return float(obj)
                    elif isinstance(obj, (datetime, date)):
                        return obj.isoformat()
                    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
                
                json_content = json.dumps(data, ensure_ascii=False, indent=2, default=json_serializer)
                timestamp = PlaywrightUtils.get_current_taipei_time().strftime('%Y%m%d_%H%M%S')
                json_filename = f"playwright_history_{username}_{export_type}_{timestamp}.json"
                
                st.download_button(
                    label=f"📥 下載JSON ({len(posts_data)}筆)",
                    data=json_content,
                    file_name=json_filename,
                    mime="application/json",
                    help="下載歷史數據JSON文件"
                )
            
            with col2:
                # CSV 下載
                csv_content = self._convert_to_csv(posts_data)
                csv_filename = f"playwright_history_{username}_{export_type}_{timestamp}.csv"
                
                st.download_button(
                    label=f"📊 下載CSV ({len(posts_data)}筆)",
                    data=csv_content,
                    file_name=csv_filename,
                    mime="text/csv",
                    help="下載歷史數據CSV文件"
                )
            
            # 顯示數據預覽
            st.subheader("📊 數據預覽")
            if export_type == "analysis" and "summary" in data:
                col_s1, col_s2, col_s3, col_s4 = st.columns(4)
                summary = data["summary"]
                with col_s1:
                    st.metric("總貼文數", summary.get("total_posts", 0))
                with col_s2:
                    st.metric("平均觀看數", f"{summary.get('avg_views', 0):,.0f}")
                with col_s3:
                    st.metric("平均按讚數", f"{summary.get('avg_likes', 0):,.0f}")
                with col_s4:
                    st.metric("最高分數", f"{summary.get('max_score', 0):,.0f}")
            
            # 顯示前10筆數據
            if posts_data:
                col_preview1, col_preview2 = st.columns([1, 1])
                with col_preview1:
                    st.write("**前10筆數據：**")
                with col_preview2:
                    show_full_history_content = st.checkbox("📖 顯示完整內容", key="show_full_history_content_v2", help="勾選後將顯示完整貼文內容")
                
                preview_data = []
                for i, post in enumerate(posts_data[:10], 1):
                    content = post.get('content', '')
                    content_display = content if show_full_history_content else ((content[:40] + "...") if content and len(content) > 40 else content or 'N/A')
                    
                    preview_data.append({
                        "#": i,
                        "貼文ID": post.get('post_id', 'N/A')[:20] + "..." if len(post.get('post_id', '')) > 20 else post.get('post_id', 'N/A'),
                        "內容" if show_full_history_content else "內容預覽": content_display,
                        "觀看數": f"{post.get('views_count', 0):,}",
                        "按讚數": f"{post.get('likes_count', 0):,}",
                        "分數": f"{post.get('calculated_score', 0):,.1f}" if post.get('calculated_score') else 'N/A',
                        "爬取時間": str(post.get('fetched_at', 'N/A'))[:19]
                    })
                st.dataframe(preview_data, use_container_width=True)
            
            st.success(f"✅ {export_type}數據導出完成！共 {len(posts_data)} 筆記錄")
            
        except Exception as e:
            st.error(f"❌ 歷史數據導出失敗: {str(e)}")
    
    async def _fetch_history_from_db(self, username: str, export_type: str, **kwargs):
        """從資料庫獲取歷史數據"""
        try:
            posts = await self.db_handler.get_user_posts_async(username)
            
            # 轉換所有時間字段為台北時間
            for post in posts:
                for time_field in ['created_at', 'fetched_at', 'post_published_at']:
                    if post.get(time_field):
                        taipei_time = PlaywrightUtils.convert_to_taipei_time(post[time_field])
                        if taipei_time:
                            post[time_field] = taipei_time.isoformat()
            
            if export_type == "recent":
                days_back = kwargs.get('days_back', 7)
                limit = kwargs.get('limit', 1000)
                
                # 過濾最近的數據
                from datetime import datetime, timedelta
                cutoff_date = PlaywrightUtils.get_current_taipei_time() - timedelta(days=days_back)
                
                filtered_posts = []
                for post in posts:
                    try:
                        if post.get('fetched_at'):
                            fetch_time = datetime.fromisoformat(str(post['fetched_at']).replace('Z', '+00:00'))
                            if fetch_time >= cutoff_date:
                                filtered_posts.append(post)
                    except:
                        continue
                
                return filtered_posts[:limit]
                
            elif export_type == "all":
                limit = kwargs.get('limit', 5000)
                return posts[:limit]
                
            elif export_type == "analysis":
                return posts
                
        except Exception as e:
            st.error(f"❌ 資料庫查詢失敗: {e}")
            return []
    
    def _calculate_stats(self, posts_data):
        """計算統計數據"""
        if not posts_data:
            return {
                "total_posts": 0,
                "avg_views": 0,
                "avg_likes": 0,
                "avg_comments": 0,
                "max_score": 0,
                "min_score": 0
            }
        
        total_posts = len(posts_data)
        views = [post.get('views_count', 0) for post in posts_data if post.get('views_count')]
        likes = [post.get('likes_count', 0) for post in posts_data if post.get('likes_count')]
        comments = [post.get('comments_count', 0) for post in posts_data if post.get('comments_count')]
        scores = [post.get('calculated_score', 0) for post in posts_data if post.get('calculated_score')]
        
        return {
            "total_posts": total_posts,
            "avg_views": sum(views) / len(views) if views else 0,
            "avg_likes": sum(likes) / len(likes) if likes else 0,
            "avg_comments": sum(comments) / len(comments) if comments else 0,
            "max_score": max(scores) if scores else 0,
            "min_score": min(scores) if scores else 0
        }
    
    def _convert_to_csv(self, posts_data):
        """將數據轉換為CSV格式"""
        import pandas as pd
        import io
        
        # 準備CSV數據，與主要導出格式一致
        csv_data = []
        for post in posts_data:
            # 處理陣列字段
            tags = post.get('tags', [])
            if isinstance(tags, str):
                try:
                    import json
                    tags = json.loads(tags)
                except:
                    tags = []
            tags_str = "|".join(tags) if tags else ""
            
            images = post.get('images', [])
            if isinstance(images, str):
                try:
                    import json
                    images = json.loads(images)
                except:
                    images = []
            images_str = "|".join(images) if images else ""
            
            videos = post.get('videos', [])
            if isinstance(videos, str):
                try:
                    import json
                    videos = json.loads(videos)
                except:
                    videos = []
            videos_str = "|".join(videos) if videos else ""
            
            # 處理時間字段 - 轉換為台北時間
            created_at = post.get('created_at', '')
            if created_at:
                taipei_created = PlaywrightUtils.convert_to_taipei_time(created_at)
                created_at = taipei_created.isoformat() if taipei_created else created_at
            
            post_published_at = post.get('post_published_at', '')
            if post_published_at:
                taipei_published = PlaywrightUtils.convert_to_taipei_time(post_published_at)
                post_published_at = taipei_published.isoformat() if taipei_published else post_published_at
            
            fetched_at = post.get('fetched_at', '')
            if fetched_at:
                taipei_fetched = PlaywrightUtils.convert_to_taipei_time(fetched_at)
                fetched_at = taipei_fetched.isoformat() if taipei_fetched else fetched_at
            
            csv_data.append({
                "url": post.get('url', ''),
                "post_id": post.get('post_id', ''),
                "username": post.get('username', ''),
                "content": post.get('content', ''),
                "likes_count": post.get('likes_count', 0),
                "comments_count": post.get('comments_count', 0),
                "reposts_count": post.get('reposts_count', 0),
                "shares_count": post.get('shares_count', 0),
                "views_count": post.get('views_count', 0),
                "calculated_score": post.get('calculated_score', ''),
                "created_at": created_at,
                "post_published_at": post_published_at,
                "tags": tags_str,
                "images": images_str,
                "videos": videos_str,
                "source": post.get('source', 'playwright_agent'),
                "crawler_type": post.get('crawler_type', 'playwright'),
                "crawl_id": post.get('crawl_id', ''),
                "fetched_at": fetched_at
            })
        
        # 轉換為CSV
        df = pd.DataFrame(csv_data)
        output = io.BytesIO()
        df.to_csv(output, index=False, encoding='utf-8-sig')
        return output.getvalue()
    
    def _show_advanced_export_options(self):
        """顯示進階導出選項"""
        with st.expander("🔍 進階導出功能", expanded=True):
            # 添加關閉按鈕
            col_title, col_close = st.columns([4, 1])
            with col_title:
                st.markdown("**更多導出選項和批量操作**")
            with col_close:
                if st.button("❌ 關閉", key="close_playwright_advanced_exports"):
                    st.session_state.show_playwright_advanced_exports = False
                    st.rerun()
            
            tab1, tab2, tab3 = st.tabs(["📊 對比報告", "🔄 批量導出", "⚡ 快速工具"])
            
            with tab1:
                st.subheader("📊 多次爬取對比報告")
                st.info("比較多次爬取結果的效能和成功率")
                
                # 查找所有Playwright JSON文件
                import glob
                from pathlib import Path
                
                # 檢查新的資料夾位置
                extraction_dir = Path("crawl_data")
                if extraction_dir.exists():
                    json_files = list(extraction_dir.glob("crawl_data_*.json"))
                else:
                    json_files = [Path(f) for f in glob.glob("crawl_data_*.json")]
                
                if len(json_files) >= 2:
                    st.write(f"🔍 找到 {len(json_files)} 個Playwright爬取結果文件：")
                    
                    # 顯示文件列表
                    file_options = {}
                    for file in sorted(json_files, reverse=True)[:10]:  # 最新的10個
                        file_time = self._extract_time_from_filename(str(file))
                        display_name = f"{file.name} ({file_time})"
                        file_options[display_name] = str(file)
                    
                    selected_displays = st.multiselect(
                        "選擇要比對的文件（至少2個）：",
                        options=list(file_options.keys()),
                        default=[],
                        help="選擇多個文件進行比對分析",
                        key="playwright_comparison_file_selector"
                    )
                    
                    selected_files = [file_options[display] for display in selected_displays]
                    
                    if len(selected_files) >= 2:
                        if st.button("📊 生成對比報告", key="playwright_generate_comparison", type="primary"):
                            self._generate_comparison_report(selected_files)
                    else:
                        st.info("💡 請選擇至少2個文件進行比對分析")
                else:
                    st.warning("⚠️ 需要至少2個Playwright爬取結果文件才能進行對比")
            
            with tab2:
                st.subheader("🔄 批量導出功能")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    if st.button("📥 導出所有最新結果", key="playwright_export_all_latest"):
                        self._export_all_latest_results()
                
                with col2:
                    if st.button("📈 導出所有帳號統計", key="playwright_export_all_stats"):
                        self._export_all_account_stats()
            
            with tab3:
                st.subheader("⚡ 快速工具")
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    if st.button("🧹 清理暫存檔案", key="playwright_cleanup_temp"):
                        self._cleanup_temp_files()
                
                with col2:
                    if st.button("📋 複製結果摘要", key="playwright_copy_summary"):
                        if 'playwright_results' in st.session_state:
                            self._copy_results_summary()
                        else:
                            st.error("❌ 沒有可複製的結果")
                
                with col3:
                    if st.button("🔗 生成分享連結", key="playwright_share_link"):
                        self._generate_share_link()
    
    def _extract_time_from_filename(self, filename: str) -> str:
        """從檔案名提取時間"""
        import re
        match = re.search(r'(\d{8}_\d{6})', filename)
        if match:
            time_str = match.group(1)
            return f"{time_str[:4]}-{time_str[4:6]}-{time_str[6:8]} {time_str[9:11]}:{time_str[11:13]}"
        return "未知時間"
    
    def _generate_comparison_report(self, selected_files: list):
        """生成對比報告"""
        try:
            import pandas as pd
            
            comparison_data = []
            
            for file_path in selected_files:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                comparison_data.append({
                    "檔案名": Path(file_path).name,
                    "時間戳": data.get('timestamp', 'N/A'),
                    "用戶名": data.get('target_username', 'N/A'),
                    "爬蟲類型": data.get('crawler_type', 'playwright'),
                    "總貼文數": len(data.get('results', [])),
                    "成功數": data.get('api_success_count', 0),
                    "失敗數": data.get('api_failure_count', 0),
                    "成功率": data.get('overall_success_rate', 0),
                })
            
            df = pd.DataFrame(comparison_data)
            
            st.subheader("📊 對比報告")
            st.dataframe(df, use_container_width=True)
            
            # 提供下載
            csv_content = df.to_csv(index=False, encoding='utf-8-sig')
            timestamp = PlaywrightUtils.get_current_taipei_time().strftime('%Y%m%d_%H%M%S')
            filename = f"playwright_comparison_report_{timestamp}.csv"
            
            st.download_button(
                label="📥 下載對比報告",
                data=csv_content,
                file_name=filename,
                mime="text/csv"
            )
            
        except Exception as e:
            st.error(f"❌ 生成對比報告失敗: {e}")
    
    def _export_all_latest_results(self):
        """導出所有最新結果"""
        st.info("📦 批量導出功能開發中...")
    
    def _export_all_account_stats(self):
        """導出所有帳號統計"""
        st.info("📈 帳號統計導出功能開發中...")
    
    def _cleanup_temp_files(self):
        """清理暫存檔案"""
        import glob
        temp_files = glob.glob("temp_playwright_progress_*.json")
        cleaned = 0
        for file in temp_files:
            try:
                os.remove(file)
                cleaned += 1
            except:
                pass
        st.success(f"🧹 已清理 {cleaned} 個暫存檔案")
    
    def _copy_results_summary(self):
        """複製結果摘要"""
        results = st.session_state.get('playwright_results', {})
        posts = results.get('results', [])
        
        summary = f"""Playwright 爬蟲結果摘要
用戶: @{results.get('target_username', 'unknown')}
時間: {results.get('timestamp', 'N/A')}
總貼文: {len(posts)}
成功率: {results.get('overall_success_rate', 0):.1f}%
"""
        
        st.text_area("📋 結果摘要（請複製）", value=summary, key="playwright_summary_copy")
    
    def _generate_share_link(self):
        """生成分享連結"""
        st.info("🔗 分享連結功能開發中...")
    
    def _clear_results(self):
        """清除結果"""
        if 'playwright_results' in st.session_state:
            del st.session_state.playwright_results
        if 'playwright_results_file' in st.session_state:
            del st.session_state.playwright_results_file
        # 重置保存標記
        st.session_state.playwright_results_saved = False
        st.success("🗑️ 結果已清除")
        st.rerun()
    
    def _load_csv_file(self, uploaded_file):
        """載入CSV文件"""
        try:
            import pandas as pd
            import io
            
            # 清理可能的舊文件引用，避免 MediaFileStorageError
            if hasattr(st.session_state, 'get'):
                file_related_keys = [k for k in st.session_state.keys() if 'file' in k.lower() or 'upload' in k.lower()]
                for key in file_related_keys:
                    if key != "playwright_csv_uploader_v2":  # 保留當前上傳器
                        try:
                            del st.session_state[key]
                        except:
                            pass
            
            # 讀取CSV文件
            content = uploaded_file.getvalue()
            df = pd.read_csv(io.StringIO(content.decode('utf-8-sig')))
            
            # 檢查CSV格式是否正確（與 JSON 格式一致）
            required_columns = ['url', 'post_id', 'username', 'content']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                st.error(f"❌ CSV格式不正確，缺少欄位: {', '.join(missing_columns)}")
                return
            
            # 轉換為結果格式
            results = []
            for _, row in df.iterrows():
                # 處理陣列字段 (tags, images, videos)
                tags_str = str(row.get('tags', '')).strip()
                tags = tags_str.split('|') if tags_str else []
                
                images_str = str(row.get('images', '')).strip()
                images = images_str.split('|') if images_str else []
                
                videos_str = str(row.get('videos', '')).strip()
                videos = videos_str.split('|') if videos_str else []
                
                result = {
                    "url": str(row.get('url', '')).strip(),
                    "post_id": str(row.get('post_id', '')).strip(),
                    "username": str(row.get('username', '')).strip(),
                    "content": str(row.get('content', '')).strip(),
                    "likes_count": row.get('likes_count', 0) if pd.notna(row.get('likes_count')) else 0,
                    "comments_count": row.get('comments_count', 0) if pd.notna(row.get('comments_count')) else 0,
                    "reposts_count": row.get('reposts_count', 0) if pd.notna(row.get('reposts_count')) else 0,
                    "shares_count": row.get('shares_count', 0) if pd.notna(row.get('shares_count')) else 0,
                    "views_count": row.get('views_count', 0) if pd.notna(row.get('views_count')) else 0,
                    "calculated_score": row.get('calculated_score', 0) if pd.notna(row.get('calculated_score')) else 0,
                    "created_at": str(row.get('created_at', '')).strip(),
                    "post_published_at": str(row.get('post_published_at', '')).strip(),
                    "tags": tags,
                    "images": images,
                    "videos": videos,
                    "source": str(row.get('source', 'playwright_agent')).strip(),
                    "crawler_type": str(row.get('crawler_type', 'playwright')).strip(),
                    "crawl_id": str(row.get('crawl_id', '')).strip(),
                    "extracted_at": str(row.get('extracted_at', '')).strip(),
                    "success": row.get('success', True) if pd.notna(row.get('success')) else True
                }
                results.append(result)
            
            # 包裝為完整結果格式
            final_results = {
                            "crawl_id": f"imported_{PlaywrightUtils.get_current_taipei_time().strftime('%Y%m%d_%H%M%S')}",
            "timestamp": PlaywrightUtils.get_current_taipei_time().isoformat(),
                "target_username": results[0].get('username', '') if results else '',
                "source": "csv_import",
                "crawler_type": "playwright",
                "total_processed": len(results),
                "results": results
            }
            
            st.session_state.playwright_results = final_results
            st.session_state.playwright_crawl_status = "completed"  # 設置狀態為完成
            st.success(f"✅ 成功載入 {len(results)} 筆記錄")
            st.rerun()
            
        except Exception as e:
            st.error(f"❌ 載入CSV失敗: {e}")
