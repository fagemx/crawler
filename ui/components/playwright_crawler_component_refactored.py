"""
Playwright 爬蟲組件 - 重構版
基於 Playwright Agent API，拆分為多個模組以提高可維護性
"""

import streamlit as st
import asyncio
import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
import sys
import os

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

# 導入拆分後的模組
from .playwright_utils import PlaywrightUtils
from .playwright_sse_handler import PlaywrightSSEHandler
from .playwright_database_handler import PlaywrightDatabaseHandler


class PlaywrightCrawlerComponent:
    """Playwright 爬蟲組件 - 重構版"""
    
    def __init__(self):
        self.is_running = False
        self.current_task = None
        self.agent_url = "http://localhost:8006/v1/playwright/crawl"
        self.sse_url = "http://localhost:8000/stream"
        
        # 初始化子組件
        self.sse_handler = PlaywrightSSEHandler(self.sse_url, self.agent_url)
        self.db_handler = PlaywrightDatabaseHandler()
        
        # 設置日誌回調
        self.sse_handler.set_log_callback(self._add_log_safe)
        self.db_handler.set_log_callback(self._add_log_safe)
        
        # 使用統一的配置管理
        from common.config import get_auth_file_path
        self.auth_file_path = get_auth_file_path(from_project_root=True)
        
    def render(self):
        """渲染Playwright爬蟲組件"""
        st.header("🎭 Playwright 智能爬蟲")
        st.markdown("**基於 Playwright Agent API + SSE實時進度 + 完整互動數據 + 資料庫整合**")
        
        # 檢查認證文件
        if not self._check_auth_file():
            st.error("❌ 找不到認證檔案")
            st.info("請先執行: `python tests/threads_fetch/save_auth.py` 來產生認證檔案")
            return
        
        st.success("✅ 認證檔案已就緒")
        
        # 參數設定區域
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("⚙️ 爬取設定")
            username = st.text_input(
                "目標帳號", 
                value="gvmonthly",
                help="要爬取的Threads帳號用戶名",
                key="playwright_username"
            )
            
            max_posts = st.number_input(
                "爬取數量", 
                min_value=1, 
                max_value=500, 
                value=50,
                help="要爬取的貼文數量",
                key="playwright_max_posts"
            )
            
            # 顯示爬取過程日誌
            if 'playwright_crawl_logs' in st.session_state and st.session_state.playwright_crawl_logs:
                with st.expander("📋 爬取過程日誌", expanded=False):
                    log_lines = st.session_state.playwright_crawl_logs[-50:] if len(st.session_state.playwright_crawl_logs) > 50 else st.session_state.playwright_crawl_logs
                    st.code('\n'.join(log_lines), language='text')
            
        with col2:
            col_title, col_refresh = st.columns([3, 1])
            with col_title:
                st.subheader("📊 資料庫統計")
            with col_refresh:
                if st.button("🔄 刷新", key="refresh_playwright_db_stats", help="刷新資料庫統計信息", type="secondary"):
                    if 'playwright_db_stats_cache' in st.session_state:
                        del st.session_state.playwright_db_stats_cache
                    st.success("🔄 正在刷新統計...")
                    st.rerun()
            
            self._display_database_stats()
        
        # 初始化爬蟲狀態
        self._init_crawl_state()
        
        # 控制按鈕
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            # 檢查是否正在爬取
            is_running = st.session_state.get("playwright_crawl_running", False)
            
            if st.button("🚀 開始爬取", key="start_playwright", disabled=is_running):
                # 啟動爬蟲（不等待完成）
                self._start_crawling_task(username, max_posts)
                st.rerun()  # 立即刷新界面
                
        with col2:
            uploaded_file = st.file_uploader(
                "📁 載入CSV文件", 
                type=['csv'], 
                key="playwright_csv_uploader",
                help="上傳之前導出的CSV文件來查看結果"
            )
            if uploaded_file is not None:
                self._load_csv_file(uploaded_file)
        
        with col3:
            if 'playwright_results' in st.session_state:
                if st.button("🗑️ 清除結果", key="clear_playwright_results", help="清除當前顯示的結果"):
                    self._clear_results()
        
        # 實時監控區域（主線程輪詢）
        self._render_realtime_monitoring()
        
        # 結果顯示
        self._render_results_area()
    
    def _check_auth_file(self):
        """檢查認證檔案是否存在"""
        return self.auth_file_path.exists()
    
    def _init_crawl_state(self):
        """初始化爬蟲狀態"""
        import threading
        
        if "playwright_crawl_running" not in st.session_state:
            st.session_state.playwright_crawl_running = False
        
        if "playwright_crawl_progress" not in st.session_state:
            st.session_state.playwright_crawl_progress = 0.0
        
        if "playwright_crawl_stage" not in st.session_state:
            st.session_state.playwright_crawl_stage = "等待開始"
        
        if "playwright_crawl_logs" not in st.session_state:
            st.session_state.playwright_crawl_logs = []
        
        if "playwright_crawl_lock" not in st.session_state:
            st.session_state.playwright_crawl_lock = threading.Lock()
        
        if "playwright_crawl_task_id" not in st.session_state:
            st.session_state.playwright_crawl_task_id = None
    
    def _start_crawling_task(self, username: str, max_posts: int):
        """啟動背景爬蟲任務"""
        import threading
        import uuid
        
        # 重置狀態
        with st.session_state.playwright_crawl_lock:
            st.session_state.playwright_crawl_running = True
            st.session_state.playwright_crawl_progress = 0.0
            st.session_state.playwright_crawl_stage = "正在啟動..."
            st.session_state.playwright_crawl_logs = []
            st.session_state.playwright_crawl_task_id = str(uuid.uuid4())
        
        # 啟動背景線程
        task_thread = threading.Thread(
            target=self._background_crawler_worker,
            args=(username, max_posts, st.session_state.playwright_crawl_task_id),
            daemon=True
        )
        task_thread.start()
        
        self._add_log_safe("🚀 爬蟲任務已啟動...")
    
    def _add_log_safe(self, message: str):
        """線程安全的日誌添加"""
        try:
            with st.session_state.playwright_crawl_lock:
                timestamp = datetime.now().strftime("%H:%M:%S")
                log_message = f"[{timestamp}] {message}"
                st.session_state.playwright_crawl_logs.append(log_message)
                
                # 限制日誌長度
                if len(st.session_state.playwright_crawl_logs) > 200:
                    st.session_state.playwright_crawl_logs = st.session_state.playwright_crawl_logs[-150:]
        except Exception as e:
            print(f"⚠️ 添加日誌失敗: {e}")
    
    def _update_progress_safe(self, progress: float, stage: str, log_message: str = None):
        """線程安全的進度更新"""
        try:
            with st.session_state.playwright_crawl_lock:
                st.session_state.playwright_crawl_progress = progress
                st.session_state.playwright_crawl_stage = stage
                
                if log_message:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    full_log = f"[{timestamp}] {log_message}"
                    st.session_state.playwright_crawl_logs.append(full_log)
                    
                    # 限制日誌長度
                    if len(st.session_state.playwright_crawl_logs) > 200:
                        st.session_state.playwright_crawl_logs = st.session_state.playwright_crawl_logs[-150:]
        except Exception as e:
            print(f"⚠️ 更新進度失敗: {e}")
    
    def _render_realtime_monitoring(self):
        """渲染實時監控區域（主線程輪詢）"""
        is_running = st.session_state.get("playwright_crawl_running", False)
        
        if is_running:
            # 創建固定的UI容器
            progress_container = st.empty()
            stage_container = st.empty() 
            log_container = st.empty()
            
            # 讀取當前狀態
            with st.session_state.playwright_crawl_lock:
                progress = st.session_state.playwright_crawl_progress
                stage = st.session_state.playwright_crawl_stage
                logs = st.session_state.playwright_crawl_logs[-30:]  # 最近30條
            
            # 更新UI
            with progress_container.container():
                st.subheader("📊 爬蟲進度")
                progress_percent = int(progress * 100)
                st.progress(progress, text=f"{progress_percent}% - {stage}")
            
            with stage_container.container():
                stage_names = {
                    "等待開始": "⏳ 等待開始",
                    "正在啟動": "🔧 正在啟動",
                    "初始化": "🔧 初始化",
                    "發送API請求": "🚀 發送API請求",
                    "post_parsed": "📝 解析貼文",
                    "fill_views_start": "👁️ 補充觀看數",
                    "fill_views_completed": "✅ 觀看數完成",
                    "completed": "🎉 全部完成",
                    "error": "❌ 發生錯誤"
                }
                stage_display = stage_names.get(stage, f"🔄 {stage}")
                st.info(f"**當前階段**: {stage_display}")
            
            with log_container.container():
                with st.expander("📋 爬取過程日誌", expanded=True):
                    if logs:
                        st.code('\n'.join(logs), language='text')
                    else:
                        st.text("等待日誌...")
            
            # 自動刷新（每0.5秒）
            time.sleep(0.5)
            st.rerun()
    
    def _background_crawler_worker(self, username: str, max_posts: int, task_id: str):
        """背景爬蟲工作線程"""
        try:
            self._update_progress_safe(0.1, "初始化", f"🔧 準備爬取 @{username}...")
            self._update_progress_safe(0.1, "初始化", f"📊 目標貼文數: {max_posts}")
            self._update_progress_safe(0.1, "初始化", f"🆔 任務ID: {task_id}")
            
            # 讀取認證文件
            try:
                with open(self.auth_file_path, "r", encoding="utf-8") as f:
                    auth_content = json.load(f)
            except Exception as e:
                self._update_progress_safe(0.0, "error", f"❌ 讀取認證檔案失敗: {e}")
                return
            
            # 準備進度文件
            progress_dir = Path("temp_progress")
            progress_dir.mkdir(exist_ok=True)
            progress_file = progress_dir / f"playwright_crawl_{task_id}.json"
            
            # 設置SSE進度回調
            self.sse_handler.set_progress_callback(self._update_progress_safe)
            
            # 啟動SSE監聽器
            self._update_progress_safe(0.2, "初始化", "🔄 啟動SSE監聽器...")
            sse_thread = self.sse_handler.start_sse_listener(task_id, str(progress_file))
            
            # 準備API請求
            payload = {
                "username": username,
                "max_posts": max_posts,
                "auth_json_content": auth_content,
                "task_id": task_id
            }
            
            self._update_progress_safe(0.3, "發送API請求", "🚀 發送API請求...")
            
            # 發送API請求
            api_result = asyncio.run(self.sse_handler.execute_async_api_request(payload))
            
            if api_result:
                self._update_progress_safe(0.9, "處理結果", f"💾 API結果已獲取：{len(api_result.get('posts', []))} 篇貼文")
                
                # 轉換結果
                converted_results = PlaywrightUtils.convert_playwright_results(api_result)
                converted_results["target_username"] = username
                
                # 保存結果
                st.session_state.playwright_results = converted_results
                
                # 保存到資料庫
                asyncio.run(self.db_handler.save_to_database_async(converted_results))
                
                posts_count = len(converted_results.get("results", []))
                self._update_progress_safe(1.0, "completed", f"✅ 爬取完成！處理了 {posts_count} 篇貼文")
                
            else:
                self._update_progress_safe(0.0, "error", "❌ API請求失敗")
                
        except Exception as e:
            self._update_progress_safe(0.0, "error", f"❌ 爬蟲錯誤: {e}")
        finally:
            # 任務完成，重置運行狀態
            time.sleep(2)  # 讓用戶看到完成消息
            with st.session_state.playwright_crawl_lock:
                st.session_state.playwright_crawl_running = False
    



    
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
    
    def _load_csv_file(self, uploaded_file):
        """載入CSV文件並轉換為結果格式（簡化版本）"""
        try:
            import pandas as pd
            import io
            
            content = uploaded_file.getvalue()
            df = pd.read_csv(io.StringIO(content.decode('utf-8-sig')))
            
            # 檢查CSV格式是否正確（更靈活的驗證）
            # 核心必要欄位
            core_required = ['username', 'post_id', 'content']
            missing_core = [col for col in core_required if col not in df.columns]
            
            if missing_core:
                st.error(f"❌ CSV格式不正確，缺少核心欄位: {', '.join(missing_core)}")
                return
            
            # 檢查可選欄位，如果沒有則提供預設值
            optional_columns = ['views', 'likes_count', 'comments_count', 'reposts_count', 'shares_count']
            for col in optional_columns:
                if col not in df.columns:
                    if col == 'views':
                        df[col] = df.get('views_count', 0)  # 嘗試使用 views_count 作為 views
                    else:
                        df[col] = 0  # 預設值為 0
            
            st.info(f"✅ 成功載入CSV，包含 {len(df)} 筆記錄")
            
            # 簡化轉換（完整版本請參考原組件）
            results = []
            for _, row in df.iterrows():
                result = {
                    'post_id': str(row.get('post_id', '')),
                    'content': str(row.get('content', '')),
                    'views': str(row.get('views', '')),
                    'source': 'csv_import',
                    'success': True
                }
                results.append(result)
            
            st.session_state.playwright_results = {
                'results': results,
                'total_count': len(results),
                'source': f"CSV文件: {uploaded_file.name}"
            }
            
            st.success(f"✅ 成功載入 {len(results)} 筆記錄")
            
        except Exception as e:
            st.error(f"❌ 載入CSV文件失敗: {str(e)}")
    
    def _clear_results(self):
        """清除當前結果"""
        keys_to_clear = [
            'playwright_results', 'playwright_results_file', 
            'playwright_error', 'latest_playwright_csv_file'
        ]
        for key in keys_to_clear:
            if key in st.session_state:
                del st.session_state[key]
        st.success("🗑️ 結果已清除")
        st.rerun()
    
    def _render_results_area(self):
        """渲染結果區域"""
        if 'playwright_results' in st.session_state:
            self._show_results()
        elif 'playwright_error' in st.session_state:
            st.error(f"❌ 爬取錯誤：{st.session_state.playwright_error}")
        else:
            st.info("👆 點擊「開始爬取」來開始，或上傳CSV文件查看之前的結果")
    
    def _show_results(self):
        """顯示爬取結果（完整版本）"""
        playwright_results = st.session_state.playwright_results
        
        if isinstance(playwright_results, dict):
            results = playwright_results.get('results', [])
        else:
            results = playwright_results if playwright_results else []
        
        st.subheader("📊 爬取結果")
        
        if not isinstance(results, list):
            st.error("❌ 結果格式錯誤，請重新載入")
            return
        
        if not results:
            st.warning("⚠️ 沒有找到任何結果")
            return
        
        # 詳細統計
        total_posts = len(results)
        success_posts = sum(1 for r in results if r.get('success', False))
        content_posts = sum(1 for r in results if r.get('content'))
        views_posts = sum(1 for r in results if r.get('views') and r.get('views') != 'N/A')
        
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
            
            for r in results:
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
        if st.checkbox("📋 顯示詳細結果", key="show_playwright_detailed_results"):
            st.write("**📋 詳細結果:**")
            
            table_data = []
            for i, r in enumerate(results, 1):
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
        if isinstance(playwright_results, dict):
            db_saved = playwright_results.get('database_saved', False)
            saved_count = playwright_results.get('database_saved_count', 0)
            if db_saved:
                st.success(f"✅ 已保存到資料庫 ({saved_count} 個貼文)")
            else:
                col_info, col_save = st.columns([3, 1])
                with col_info:
                    st.info("ℹ️ 如果統計中沒有看到新數據，您可以使用備用保存功能")
                with col_save:
                    if st.button("💾 備用保存", key="save_playwright_to_database"):
                        result = self.db_handler.save_results_to_database_sync(playwright_results)
                        if result.get("success"):
                            st.success(f"✅ 保存成功！保存了 {result.get('saved_count', 0)} 個貼文")
                        else:
                            st.error(f"❌ 保存失敗: {result.get('error', '未知錯誤')}")
        
        st.divider()
        
        # 更多導出功能
        st.subheader("📤 更多導出")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("💾 下載JSON", key="download_playwright_json"):
                self._show_json_download_button()
        
        with col2:
            if st.button("📊 導出CSV", key="export_playwright_csv"):
                self._export_csv_results(results)
        
        with col3:
            if st.button("📋 複製結果", key="copy_playwright_results"):
                self._copy_results_to_clipboard(results)
    
    def _show_json_download_button(self):
        """顯示JSON下載按鈕"""
        if 'playwright_results' in st.session_state:
            try:
                json_content = json.dumps(
                    st.session_state.playwright_results, 
                    ensure_ascii=False, 
                    indent=2
                )
                
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                download_filename = f"playwright_crawl_results_{timestamp}.json"
                
                st.download_button(
                    label="💾 下載JSON",
                    data=json_content,
                    file_name=download_filename,
                    mime="application/json",
                    help="下載爬取結果JSON文件",
                    key="download_playwright_json_btn"
                )
                
            except Exception as e:
                st.error(f"❌ 準備下載文件失敗: {e}")
        else:
            st.button("💾 下載JSON", disabled=True, help="暫無可下載的結果文件")
    
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
    
    def _export_csv_results(self, results):
        """導出CSV結果"""
        try:
            import pandas as pd
            import io
            
            # 準備CSV數據
            csv_data = []
            for i, r in enumerate(results, 1):
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
            
            df = pd.DataFrame(csv_data)
            
            # 轉換為CSV
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
            csv_content = csv_buffer.getvalue()
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"playwright_crawl_results_{timestamp}.csv"
            
            st.download_button(
                label="📊 下載CSV文件",
                data=csv_content,
                file_name=filename,
                mime="text/csv",
                help="下載爬取結果CSV文件",
                key="download_playwright_csv_btn"
            )
            
        except Exception as e:
            st.error(f"❌ 導出CSV失敗: {e}")
    
    def _copy_results_to_clipboard(self, results):
        """複製結果到剪貼板"""
        try:
            # 生成簡化的文本格式
            text_lines = ["Playwright 爬蟲結果", "=" * 30]
            
            for i, r in enumerate(results, 1):
                text_lines.append(f"\n{i}. 貼文ID: {r.get('post_id', 'N/A')}")
                text_lines.append(f"   觀看數: {r.get('views', 'N/A')}")
                text_lines.append(f"   按讚數: {r.get('likes', 'N/A')}")
                text_lines.append(f"   內容: {(r.get('content', '')[:100] + '...') if len(r.get('content', '')) > 100 else r.get('content', 'N/A')}")
            
            text_content = '\n'.join(text_lines)
            
            # 使用 st.code 顯示可複製的文本
            st.code(text_content, language='text')
            st.info("📋 結果已顯示在上方，您可以手動選擇複製")
            
        except Exception as e:
            st.error(f"❌ 複製結果失敗: {e}")