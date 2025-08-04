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

class PlaywrightCrawlerComponentV2:
    def __init__(self):
        self.agent_url = "http://localhost:8006/v1/playwright/crawl"
        self.sse_url = "http://localhost:8000/stream"
        
        # 初始化子組件
        self.db_handler = PlaywrightDatabaseHandler()
        
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
    
    # ---------- 2. 主渲染方法 ----------
    def render(self):
        """渲染Playwright爬蟲組件"""
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
        # 參數設定區域
        col1, col2 = st.columns(2)
        
        with col1:
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
            
            if st.button("🚀 開始爬取", key="start_playwright_v2"):
                # 啟動爬蟲
                self._start_crawling(username, max_posts)
                
        with col2:
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
                    "initialization": "🔧 初始化",
                    "fetch_start": "🔍 開始爬取",
                    "post_parsed": "📝 解析貼文",
                    "batch_parsed": "📦 批次處理",
                    "fill_views_start": "👁️ 補充觀看數",
                    "fill_views_completed": "✅ 觀看數完成",
                    "api_completed": "🎯 API完成",
                    "completed": "🎉 全部完成",
                    "error": "❌ 發生錯誤"
                }
                stage_display = stage_names.get(stage, f"🔄 {stage}")
                st.info(f"**當前階段**: {stage_display}")
                
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
                st.rerun()
            return
        
        # 處理並顯示結果
        try:
            # 轉換結果格式
            converted_results = PlaywrightUtils.convert_playwright_results(final_data)
            target = st.session_state.get('playwright_target', {})
            converted_results["target_username"] = target.get('username', 'unknown')
            
            # 保存JSON文件
            json_file_path = PlaywrightUtils.save_json_results(converted_results)
            
            # 自動保存到資料庫
            asyncio.run(self.db_handler.save_to_database_async(converted_results))
            
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
        
        if st.button("🔙 返回設定"):
            st.session_state.playwright_crawl_status = "idle"
            st.rerun()
    
    # ---------- 3. 爬蟲啟動邏輯 ----------
    def _start_crawling(self, username: str, max_posts: int):
        """啟動爬蟲"""
        # 設定目標參數
        st.session_state.playwright_target = {
            'username': username,
            'max_posts': max_posts
        }
        
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
            args=(username, max_posts, task_id, progress_file),
            daemon=True
        )
        task_thread.start()
        
        # 切換到進度頁面
        st.session_state.playwright_crawl_status = "running"
        st.rerun()
    
    def _background_crawler_worker(self, username: str, max_posts: int, task_id: str, progress_file: str):
        """背景爬蟲工作線程 - 只寫檔案，不做任何 st.* 操作"""
        try:
            # 準備 API 請求
            self._log_to_file(progress_file, "🔧 準備爬取參數...")
            self._update_progress_file(progress_file, 0.1, "initialization", "準備API請求...")
            
            # 讀取認證文件
            try:
                with open(self.auth_file_path, "r", encoding="utf-8") as f:
                    auth_content = json.load(f)
            except Exception as e:
                self._update_progress_file(progress_file, 0.0, "error", f"❌ 讀取認證檔案失敗: {e}")
                return
            
            # 構建 API 請求
            payload = {
                "username": username,
                "max_posts": max_posts,
                "auth_file_content": auth_content
            }
            
            self._log_to_file(progress_file, f"📊 目標: @{username}, 數量: {max_posts}")
            self._update_progress_file(progress_file, 0.2, "fetch_start", "發送API請求...")
            
            # 發送 API 請求（同步）
            try:
                import httpx
                with httpx.Client(timeout=600.0) as client:
                    response = client.post(self.agent_url, json=payload)
                    response.raise_for_status()
                    result = response.json()
                
                self._log_to_file(progress_file, "✅ API請求成功")
                self._update_progress_file(progress_file, 1.0, "api_completed", "處理完成", final_data=result)
                
            except Exception as e:
                self._log_to_file(progress_file, f"❌ API請求失敗: {e}")
                self._update_progress_file(progress_file, 0.0, "error", f"API請求失敗: {e}")
                
        except Exception as e:
            self._update_progress_file(progress_file, 0.0, "error", f"背景任務失敗: {e}")
    
    def _update_progress_file(self, progress_file: str, progress: float, stage: str, current_work: str, final_data: Dict = None):
        """更新進度檔案"""
        data = {
            "progress": progress,
            "stage": stage,
            "current_work": current_work
        }
        if final_data:
            data["final_data"] = final_data
        
        self._write_progress(progress_file, data)
    
    def _log_to_file(self, progress_file: str, message: str):
        """將日誌寫入檔案"""
        timestamp = datetime.now().strftime("%H:%M:%S")
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
        views_posts = sum(1 for r in posts if r.get('views') and r.get('views') != 'N/A')
        
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
                views = self._safe_int(r.get('views', 0))
                likes = self._safe_int(r.get('likes', 0))
                comments = self._safe_int(r.get('comments', 0))
                reposts = self._safe_int(r.get('reposts', 0))
                
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
            st.write("**📋 詳細結果:**")
            
            table_data = []
            for i, r in enumerate(posts, 1):
                table_data.append({
                    "#": i,
                    "貼文ID": r.get('post_id', 'N/A')[:15] + "..." if len(r.get('post_id', '')) > 15 else r.get('post_id', 'N/A'),
                    "觀看數": r.get('views', 'N/A'),
                    "按讚": r.get('likes', 'N/A'),
                    "留言": r.get('comments', 'N/A'),
                    "分享": r.get('reposts', 'N/A'),
                    "內容預覽": (r.get('content', '')[:50] + "...") if r.get('content') else 'N/A',
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
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("💾 下載JSON", key="download_playwright_json_v2"):
                self._show_json_download_button(results)
        
        with col2:
            if st.button("📊 導出CSV", key="export_playwright_csv_v2"):
                self._export_csv_results(posts)
        
        with col3:
            if st.button("📋 複製結果", key="copy_playwright_results_v2"):
                self._copy_results_to_clipboard(posts)
    
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
    
    def _show_json_download_button(self, results):
        """顯示JSON下載按鈕"""
        try:
            json_content = json.dumps(results, ensure_ascii=False, indent=2)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            download_filename = f"playwright_crawl_results_{timestamp}.json"
            
            st.download_button(
                label="💾 下載JSON",
                data=json_content,
                file_name=download_filename,
                mime="application/json",
                help="下載爬取結果JSON文件",
                key="download_playwright_json_btn_v2"
            )
            
        except Exception as e:
            st.error(f"❌ 準備下載文件失敗: {e}")
    
    def _export_csv_results(self, posts):
        """導出CSV結果"""
        try:
            import pandas as pd
            import io
            
            # 準備CSV數據
            csv_data = []
            for i, r in enumerate(posts, 1):
                csv_data.append({
                    "序號": i,
                    "貼文ID": r.get('post_id', ''),
                    "URL": r.get('url', ''),
                    "內容": r.get('content', ''),
                    "觀看數": r.get('views', ''),
                    "按讚數": r.get('likes', ''),
                    "留言數": r.get('comments', ''),
                    "分享數": r.get('reposts', ''),
                    "來源": r.get('source', ''),
                    "爬取時間": r.get('extracted_at', ''),
                    "用戶名": r.get('username', ''),
                    "成功": "是" if r.get('success') else "否"
                })
            
            if csv_data:
                df = pd.DataFrame(csv_data)
                
                # 轉換為CSV
                output = io.StringIO()
                df.to_csv(output, index=False, encoding='utf-8-sig')
                csv_content = output.getvalue()
                
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                download_filename = f"playwright_crawl_results_{timestamp}.csv"
                
                st.download_button(
                    label="📊 下載CSV",
                    data=csv_content,
                    file_name=download_filename,
                    mime="text/csv",
                    help="下載爬取結果CSV文件",
                    key="download_playwright_csv_btn_v2"
                )
            else:
                st.error("❌ 沒有數據可導出")
                
        except Exception as e:
            st.error(f"❌ 導出CSV失敗: {e}")
    
    def _copy_results_to_clipboard(self, posts):
        """複製結果到剪貼板"""
        try:
            # 構建可複製的文本
            text_lines = ["Playwright 爬蟲結果", "=" * 30]
            
            for i, r in enumerate(posts, 1):
                text_lines.append(f"\n{i}. 貼文ID: {r.get('post_id', 'N/A')}")
                text_lines.append(f"   觀看數: {r.get('views', 'N/A')}")
                text_lines.append(f"   按讚: {r.get('likes', 'N/A')}")
                text_lines.append(f"   留言: {r.get('comments', 'N/A')}")
                text_lines.append(f"   分享: {r.get('reposts', 'N/A')}")
                if r.get('content'):
                    content = r.get('content', '')[:100] + "..." if len(r.get('content', '')) > 100 else r.get('content', '')
                    text_lines.append(f"   內容: {content}")
            
            result_text = '\n'.join(text_lines)
            
            # 顯示複製框
            st.text_area(
                "📋 複製下方文本:",
                value=result_text,
                height=300,
                key="playwright_copy_text_v2",
                help="選中全部文本並複製 (Ctrl+A, Ctrl+C)"
            )
            
            st.info("💡 請選中上方文本並手動複製 (Ctrl+A 全選，Ctrl+C 複製)")
            
        except Exception as e:
            st.error(f"❌ 準備複製文本失敗: {e}")