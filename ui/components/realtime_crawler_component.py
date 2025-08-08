"""
實時爬蟲組件 - 智能URL收集 + 輪迴策略提取
包含完整互動數據提取功能
"""

import streamlit as st
import asyncio
import json
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
import sys
import os

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

class RealtimeDatabaseHandler:
    """處理 Realtime Crawler 資料庫操作的輔助類"""

    def __init__(self):
        # 延遲導入，避免循環依賴和啟動問題
        from common.incremental_crawl_manager import IncrementalCrawlManager
        self.crawl_manager = IncrementalCrawlManager()

    async def _get_connection(self):
        await self.crawl_manager.db.init_pool()
        return self.crawl_manager.db.get_connection()

    async def delete_user_data_async(self, username: str) -> dict:
        """異步刪除特定用戶的所有數據並返回詳細結果"""
        if not username:
            return {"success": False, "error": "用戶名不能為空"}

        try:
            async with await self._get_connection() as conn:
                async with conn.transaction():
                    # 1. 獲取要刪除的記錄數
                    posts_count = await conn.fetchval(
                        "SELECT COUNT(*) FROM post_metrics_sql WHERE username = $1", username
                    )
                    crawl_state_count = await conn.fetchval(
                        "SELECT COUNT(*) FROM crawl_state WHERE username = $1", username
                    )

                    # 2. 執行刪除
                    await conn.execute("DELETE FROM post_metrics_sql WHERE username = $1", username)
                    await conn.execute("DELETE FROM crawl_state WHERE username = $1", username)
                    
                    # 3. 驗證刪除
                    remaining_posts = await conn.fetchval(
                        "SELECT COUNT(*) FROM post_metrics_sql WHERE username = $1", username
                    )
                    
                    if remaining_posts == 0:
                        return {
                            "success": True, 
                            "deleted_posts": posts_count, 
                            "deleted_states": crawl_state_count
                        }
                    else:
                        return {
                            "success": False, 
                            "error": "刪除後驗證失敗，仍有數據殘留",
                            "remaining_posts": remaining_posts
                        }

        except Exception as e:
            return {"success": False, "error": str(e)}

        finally:
            await self.crawl_manager.db.close_pool()

class RealtimeCrawlerComponent:
    def __init__(self):
        self.is_running = False
        self.current_task = None
        self.db_handler = RealtimeDatabaseHandler() # 初始化新的資料庫處理器
        
    def render(self):
        """渲染實時爬蟲組件"""
        st.header("🚀 實時智能爬蟲")
        st.markdown("**智能滾動收集URLs + 輪迴策略快速提取 + 完整互動數據**")
        
        # 參數設定區域
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("⚙️ 爬取設定")
            username = st.text_input(
                "目標帳號", 
                value="gvmonthly",
                help="要爬取的Threads帳號用戶名",
                key="realtime_username"
            )
            
            max_posts = st.number_input(
                "爬取數量", 
                min_value=1, 
                max_value=500, 
                value=50,
                help="要爬取的貼文數量",
                key="realtime_max_posts"
            )
            
            # 增量爬取模式選項
            crawl_mode = st.radio(
                "爬取模式",
                options=["增量爬取", "全量爬取"],
                index=0,
                help="增量爬取：只抓取新貼文，避免重複；全量爬取：抓取所有找到的貼文",
                key="crawl_mode"
            )
            
            # 顯示爬取過程日誌（移到這裡，避免重新渲染影響）
            if 'realtime_crawl_logs' in st.session_state and st.session_state.realtime_crawl_logs:
                with st.expander("📋 爬取過程日誌", expanded=False):
                    # 顯示最後50行日誌
                    log_lines = st.session_state.realtime_crawl_logs[-50:] if len(st.session_state.realtime_crawl_logs) > 50 else st.session_state.realtime_crawl_logs
                    st.code('\n'.join(log_lines), language='text')
            
        with col2:
            col_title, col_refresh = st.columns([3, 1])
            with col_title:
                st.subheader("📊 資料庫統計")
            with col_refresh:
                if st.button("🔄 刷新", key="refresh_db_stats", help="刷新資料庫統計信息", type="secondary"):
                    # 清理可能的緩存狀態
                    if 'db_stats_cache' in st.session_state:
                        del st.session_state.db_stats_cache
                    st.success("🔄 正在刷新統計...")
                    st.rerun()  # 重新運行頁面來刷新統計
            
            self._display_database_stats()
        
        # 控制按鈕
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            if st.button("🚀 開始爬取", key="start_realtime"):
                with st.spinner("正在執行爬取..."):
                    is_incremental = crawl_mode == "增量爬取"
                    self._execute_crawling_simple(username, max_posts, is_incremental)
                
        with col2:
            # 載入CSV文件功能
            uploaded_file = st.file_uploader(
                "📁 載入CSV文件", 
                type=['csv'], 
                key="csv_uploader",
                help="上傳之前導出的CSV文件來查看結果"
            )
            if uploaded_file is not None:
                self._load_csv_file(uploaded_file)
        
        with col3:
            # 清除結果按鈕 (只在有結果時顯示)
            if 'realtime_results' in st.session_state:
                if st.button("🗑️ 清除結果", key="clear_results", help="清除當前顯示的結果"):
                    self._clear_results()
        
        # 結果顯示
        self._render_results_area()
    
    def _load_csv_file(self, uploaded_file):
        """載入CSV文件並轉換為結果格式"""
        try:
            import pandas as pd
            import io
            
            # 讀取CSV文件
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
            
            # 轉換為結果格式
            results = []
            for _, row in df.iterrows():
                # 轉換數據並處理空值
                views = str(row.get('views', '')).strip()
                likes = str(row.get('likes', '')).strip()
                comments = str(row.get('comments', '')).strip()
                reposts = str(row.get('reposts', '')).strip()
                shares = str(row.get('shares', '')).strip()
                content = str(row.get('content', '')).strip()
                
                # 🔧 修復：處理用戶ID分離
                original_post_id = str(row.get('post_id', ''))
                username_from_csv = str(row.get('username', ''))
                user_id_from_csv = str(row.get('user_id', '')).strip()
                
                # 提取用戶ID和真實貼文ID
                if '_' in original_post_id and len(original_post_id.split('_')) >= 2:
                    parts = original_post_id.split('_', 1)
                    user_id = parts[0] if len(parts) > 1 else ''
                    real_post_id = parts[1] if len(parts) > 1 else original_post_id
                else:
                    # 優先使用CSV中的user_id，其次使用username
                    user_id = user_id_from_csv or username_from_csv
                    real_post_id = original_post_id
                
                # 如果仍然沒有user_id，從post_id提取
                if not user_id and original_post_id:
                    if '_' in original_post_id:
                        user_id = original_post_id.split('_')[0]
                
                result = {
                    'username': user_id or username_from_csv,  # 🔧 修復：使用分離的user_id
                    'user_id': user_id,  # 🔧 新增：分離的用戶ID
                    'post_id': original_post_id,
                    'real_post_id': real_post_id,  # 🔧 新增：真實貼文ID
                    'content': content,
                    'views': views,
                    'likes': likes,
                    'comments': comments,
                    'reposts': reposts,
                    'shares': shares,
                    'url': str(row.get('url', '')),
                    'source': str(row.get('source', 'csv_import')),
                    'created_at': str(row.get('created_at', '')),
                    'fetched_at': str(row.get('fetched_at', '')),
                    'success': True,
                    # 添加has_*欄位以兼容顯示邏輯
                    'has_views': bool(views and views != 'nan' and views != ''),
                    'has_content': bool(content and content != 'nan' and content != ''),
                    'has_likes': bool(likes and likes != 'nan' and likes != ''),
                    'has_comments': bool(comments and comments != 'nan' and comments != ''),
                    'has_reposts': bool(reposts and reposts != 'nan' and reposts != ''),
                    'has_shares': bool(shares and shares != 'nan' and shares != ''),
                    'content_length': len(content) if content else 0,
                    'extracted_at': datetime.now().isoformat()
                }
                results.append(result)
            
            # 保存到會話狀態
            st.session_state.realtime_results = {
                'results': results,
                'total_count': len(results),
                'username': results[0]['username'] if results else '',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'source': f"CSV文件: {uploaded_file.name}"
            }
            
            st.success(f"✅ 成功載入 {len(results)} 筆記錄")
            st.info(f"📊 來源: {uploaded_file.name}")
            
        except Exception as e:
            st.error(f"❌ 載入CSV文件失敗: {str(e)}")
    
    def _execute_crawling_simple(self, username: str, max_posts: int, is_incremental: bool = True):
        """簡化的爬取執行方法 - 使用同步版本避免asyncio衝突"""
        if not username.strip():
            st.error("請輸入目標帳號！")
            return
            
        try:
            # 記錄開始時間
            import time
            start_time = time.time()
            st.session_state.realtime_crawl_start_time = start_time
            
            mode_text = "增量爬取" if is_incremental else "全量爬取"
            st.info(f"🔄 正在執行{mode_text}，請稍候...")
            
            # 使用subprocess來避免asyncio衝突
            import subprocess
            import json
            import sys
            import os
            
            # 構建命令
            script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '..', 'scripts', 'realtime_crawler_extractor.py')
            
            # 修改腳本以接受命令行參數
            cmd = [
                sys.executable, 
                script_path,
                '--username', username,
                '--max_posts', str(max_posts)
            ]
            
            # 添加爬取模式參數
            if is_incremental:
                cmd.append('--incremental')  # 增量模式
            else:
                cmd.append('--full')  # 全量模式
            
            # 執行腳本 - 設置UTF-8編碼
            import locale
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            env['PYTHONUTF8'] = '1'
            
            # 創建一個日志容器來實時顯示輸出
            log_container = st.empty()
            # 將日誌保存到會話狀態，避免頁面重新渲染時丟失
            # 每次新的爬取開始時清空之前的日誌
            st.session_state.realtime_crawl_logs = []
            log_text = st.session_state.realtime_crawl_logs
            
            with st.expander("📋 爬取過程日志", expanded=True):
                log_placeholder = st.empty()
                
                # 使用Popen來實時捕獲輸出
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,  # 合併stderr到stdout
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    env=env,
                    cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                    bufsize=1,  # 行緩衝
                    universal_newlines=True
                )
                
                # 實時讀取輸出
                all_output = []
                while process.poll() is None:
                    output = process.stdout.readline()
                    if output:
                        line = output.strip()
                        all_output.append(line)
                        log_text.append(line)
                        
                        # 只顯示最後30行，避免界面過長
                        display_lines = log_text[-30:] if len(log_text) > 30 else log_text
                        log_placeholder.code('\n'.join(display_lines), language='text')
                    else:
                        # 短暫休眠，避免主線程完全阻塞
                        time.sleep(0.1)

                # 捕獲進程結束後剩餘的輸出
                for output in process.stdout.readlines():
                    line = output.strip()
                    all_output.append(line)
                    log_text.append(line)
                
                # 最後再更新一次UI
                display_lines = log_text[-30:] if len(log_text) > 30 else log_text
                log_placeholder.code('\n'.join(display_lines), language='text')

                return_code = process.poll()
                
            if return_code == 0:
                # 成功執行，尋找最新的結果文件
                import glob
                from pathlib import Path
                
                # 先檢查新的資料夾位置
                extraction_dir = Path("extraction_results")
                if extraction_dir.exists():
                    results_files = list(extraction_dir.glob("realtime_extraction_results_*.json"))
                else:
                    # 回退到根目錄查找（向後兼容）
                    results_files = [Path(f) for f in glob.glob("realtime_extraction_results_*.json")]
                
                if results_files:
                    # 取最新的文件
                    latest_file = max(results_files, key=lambda f: f.stat().st_mtime)
                    
                    # 讀取結果
                    with open(latest_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # 保存到session_state
                    st.session_state.realtime_results = data.get('results', [])
                    st.session_state.realtime_results_file = latest_file
                    
                    total_processed = len(st.session_state.realtime_results)
                    
                    # 計算總耗時
                    end_time = time.time()
                    start_time = st.session_state.get('realtime_crawl_start_time', end_time)
                    total_duration = end_time - start_time
                    
                    # 將耗時信息保存到單獨的session state
                    st.session_state.realtime_crawl_duration = total_duration
                    
                    # 格式化耗時顯示
                    if total_duration < 60:
                        duration_text = f"{total_duration:.1f} 秒"
                    else:
                        duration_text = f"{total_duration/60:.1f} 分鐘"
                    
                    st.success(f"✅ 爬取完成！處理了 {total_processed} 篇貼文，耗時: {duration_text}")
                    
                    # 清理資料庫統計緩存，下次會自動刷新
                    if 'db_stats_cache' in st.session_state:
                        del st.session_state.db_stats_cache
                    
                    st.info("📊 增量爬取已自動保存到資料庫，您可以點擊右側「🔄 刷新」查看更新的統計")
                    st.balloons()
                else:
                    st.error("❌ 未找到結果文件")
            else:
                st.error(f"❌ 爬取失敗 (返回碼: {return_code})")
                # 顯示最後的錯誤日志
                if all_output:
                    error_lines = [line for line in all_output if '❌' in line or 'Error' in line or 'Exception' in line]
                    if error_lines:
                        st.error("錯誤詳情：")
                        for error_line in error_lines[-5:]:  # 顯示最後5條錯誤
                            st.text(error_line)
                
        except Exception as e:
            st.error(f"❌ 執行錯誤：{str(e)}")
            st.session_state.realtime_error = str(e)
    
    def _display_database_stats(self):
        """顯示資料庫統計信息"""
        # 檢查是否有緩存的統計信息
        if 'db_stats_cache' in st.session_state:
            self._render_cached_stats(st.session_state.db_stats_cache)
            return
        
        try:
            # 使用 asyncio 和 subprocess 來獲取資料庫統計
            import subprocess
            import json
            import sys
            import os
            
            # 創建一個臨時腳本來獲取資料庫統計
            script_content = '''
import asyncio
import sys
import os
import json
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from common.incremental_crawl_manager import IncrementalCrawlManager

async def get_database_stats():
    crawl_manager = IncrementalCrawlManager()
    try:
        await crawl_manager.db.init_pool()
        
        # 獲取所有用戶的統計信息
        async with crawl_manager.db.get_connection() as conn:
            # 統計每個用戶的貼文數量
            user_stats = await conn.fetch("""
                SELECT 
                    username,
                    COUNT(*) as post_count,
                    MAX(created_at) as latest_crawl,
                    MIN(created_at) as first_crawl
                FROM post_metrics_sql 
                GROUP BY username 
                ORDER BY post_count DESC, latest_crawl DESC
                LIMIT 20
            """)
            
            # 總體統計
            total_stats = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total_posts,
                    COUNT(DISTINCT username) as total_users,
                    MAX(created_at) as latest_activity
                FROM post_metrics_sql
            """)
            
            stats = {
                "total_stats": dict(total_stats) if total_stats else {},
                "user_stats": [dict(row) for row in user_stats] if user_stats else []
            }
            
            print(json.dumps(stats, default=str))
            
    except Exception as e:
        print(json.dumps({"error": str(e)}))
    finally:
        await crawl_manager.db.close_pool()

if __name__ == "__main__":
    asyncio.run(get_database_stats())
'''
            
            # 將腳本寫入臨時文件
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                f.write(script_content)
                temp_script = f.name
            
            try:
                # 執行腳本獲取統計信息
                result = subprocess.run(
                    [sys.executable, temp_script],
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                    timeout=10
                )
                
                if result.returncode == 0 and result.stdout.strip():
                    stats = json.loads(result.stdout.strip())
                    
                    if "error" in stats:
                        st.error(f"❌ 資料庫錯誤: {stats['error']}")
                        return
                    
                    # 保存到緩存
                    st.session_state.db_stats_cache = stats
                    
                    # 渲染統計信息
                    self._render_cached_stats(stats)
                    
                else:
                    st.warning("⚠️ 無法獲取資料庫統計信息")
                    if result.stderr:
                        st.text(f"錯誤: {result.stderr}")
                        
            finally:
                # 清理臨時文件
                try:
                    os.unlink(temp_script)
                except:
                    pass
                    
        except Exception as e:
            st.error(f"❌ 獲取統計信息失敗: {str(e)}")
    
    def _execute_user_deletion(self, username: str):
        """執行實際的用戶刪除操作，直接調用 Database Handler"""
        try:
            with st.spinner(f"🗑️ 正在刪除用戶 @{username} 的資料..."):
                result = asyncio.run(self.db_handler.delete_user_data_async(username))

            if result.get("success"):
                st.success(f"""
                ✅ **刪除成功！**
                用戶 @{username} 的資料已被完全刪除：
                - 🗑️ 刪除貼文數: {result.get('deleted_posts', 0)} 個
                - 🗑️ 刪除爬取狀態: {result.get('deleted_states', 0)} 個
                """)
                # 清理相關 session state
                if 'realtime_confirm_delete_user' in st.session_state:
                    del st.session_state['realtime_confirm_delete_user']
                if 'db_stats_cache' in st.session_state:
                    del st.session_state['db_stats_cache']
                
                st.info("📊 正在刷新統計資料...")
                time.sleep(1)
                st.rerun()
            else:
                st.error(f"❌ 刪除失敗: {result.get('error', '未知錯誤')}")

        except Exception as e:
            st.error(f"❌ 刪除過程中發生嚴重錯誤: {e}")
            import traceback
            st.code(traceback.format_exc())

    def handle_delete_button(self, username: str):
        """管理刪除按鈕的顯示和兩步確認流程"""
        delete_confirm_key = "realtime_confirm_delete_user"

        # 自訂紅色樣式
        st.markdown("""
        <style>
        div.stButton > button[key*="realtime_delete_"] {
            background-color: #ff4b4b !important; color: white !important; border-color: #ff4b4b !important;
        }
        div.stButton > button[key*="realtime_delete_"]:hover {
            background-color: #ff2b2b !important; border-color: #ff2b2b !important;
        }
        </style>
        """, unsafe_allow_html=True)

        if st.session_state.get(delete_confirm_key) == username:
            # 第二步：最終確認
            st.error(f"⚠️ **最終確認: 確定刪除 @{username} 的所有 Realtime 資料?**")
            
            if st.button(f"🗑️ 是，永久刪除 @{username}", key=f"realtime_delete_confirm_final_{username}", use_container_width=True):
                self._execute_user_deletion(username)
                # 執行刪除後會自動 rerun
            
            if st.button("❌ 取消", key=f"realtime_delete_cancel_{username}", use_container_width=True):
                del st.session_state[delete_confirm_key]
                st.success("✅ 已取消刪除操作。")
                st.rerun()
        else:
            # 第一步：觸發確認
            if st.button("🗑️ 刪除用戶資料", key=f"realtime_delete_init_{username}", help=f"刪除 @{username} 的所有 Realtime 爬蟲資料", use_container_width=True):
                st.session_state[delete_confirm_key] = username
                st.rerun()
    

    
    def _export_user_csv(self, username: str):
        """導出指定用戶的所有貼文為CSV格式"""
        if not username:
            st.error("❌ 請選擇一個有效的用戶")
            return
        
        try:
            import subprocess
            import json
            import sys
            import os
            import tempfile
            from datetime import datetime
            
            # 創建導出腳本
            export_script_content = f'''
import asyncio
import sys
import os
import json
import csv
from datetime import datetime
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from common.incremental_crawl_manager import IncrementalCrawlManager

async def export_user_csv(username):
    crawl_manager = IncrementalCrawlManager()
    try:
        await crawl_manager.db.init_pool()
        
        async with crawl_manager.db.get_connection() as conn:
            # 查詢用戶的所有貼文數據
            posts = await conn.fetch("""
                SELECT 
                    post_id,
                    url,
                    content,
                    views_count,
                    likes_count,
                    comments_count,
                    reposts_count,
                    shares_count,
                    source,
                    created_at,
                    fetched_at
                FROM post_metrics_sql 
                WHERE username = $1
                ORDER BY created_at DESC
            """, username)
            
            if not posts:
                print(json.dumps({{"success": False, "error": "用戶沒有貼文資料"}}))
                return
            
            # 準備CSV文件路徑
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            csv_filename = f"user_posts_{{username}}_{{timestamp}}.csv"
            csv_filepath = os.path.join("exports", csv_filename)
            
            # 確保exports目錄存在
            os.makedirs("exports", exist_ok=True)
            
            # 寫入CSV文件
            with open(csv_filepath, 'w', newline='', encoding='utf-8-sig') as csvfile:
                fieldnames = [
                    'username', 'user_id', 'post_id', 'real_post_id', 'url', 'content', 'views', 
                    'likes', 'comments', 'reposts', 'shares', 'source', 'created_at', 'fetched_at'
                ]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                # 寫入標題行
                writer.writeheader()
                
                # 寫入數據
                for post in posts:
                    # 🔧 修復：分離post_id為user_id和real_post_id
                    original_post_id = post['post_id']
                    if '_' in original_post_id and len(original_post_id.split('_')) >= 2:
                        parts = original_post_id.split('_', 1)
                        user_id = parts[0] if len(parts) > 1 else username
                        real_post_id = parts[1] if len(parts) > 1 else original_post_id
                    else:
                        user_id = username
                        real_post_id = original_post_id
                    
                    writer.writerow({
                        'username': username,
                        'user_id': user_id,  # 🔧 新增：分離的用戶ID
                        'post_id': original_post_id,
                        'real_post_id': real_post_id,  # 🔧 新增：真實貼文ID
                        'url': post['url'],
                        'content': post['content'] or '',
                        'views': post['views_count'] or '',
                        'likes': post['likes_count'] or '',
                        'comments': post['comments_count'] or '',
                        'reposts': post['reposts_count'] or '',
                        'shares': post['shares_count'] or '',
                        'source': post['source'] or '',
                        'created_at': str(post['created_at']) if post['created_at'] else '',
                        'fetched_at': str(post['fetched_at']) if post['fetched_at'] else ''
                    })
            
            result = {
                "success": True,
                "csv_file": csv_filepath,
                "post_count": len(posts),
                "username": username
            }
            
            print(json.dumps(result))
            
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}))
    finally:
        await crawl_manager.db.close_pool()

if __name__ == "__main__":
    asyncio.run(export_user_csv("{username}"))
'''
            
            # 寫入臨時文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                f.write(export_script_content)
                temp_script = f.name
            
            try:
                # 執行導出腳本
                with st.spinner(f"📊 正在導出用戶 @{username} 的貼文資料..."):
                    result = subprocess.run(
                        [sys.executable, temp_script],
                        capture_output=True,
                        text=True,
                        encoding='utf-8',
                        cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                        timeout=60
                    )
                
                if result.returncode == 0 and result.stdout.strip():
                    export_result = json.loads(result.stdout.strip())
                    
                    if export_result.get("success"):
                        csv_file_path = export_result.get("csv_file")
                        post_count = export_result.get("post_count", 0)
                        
                        st.success(f"""
                        ✅ **導出成功！**
                        
                        用戶 @{username} 的貼文已導出為CSV：
                        - 📊 導出貼文數: {post_count:,} 個
                        - 📁 文件路徑: {csv_file_path}
                        """)
                        
                        # 提供下載按鈕
                        if os.path.exists(csv_file_path):
                            with open(csv_file_path, 'rb') as f:
                                csv_content = f.read()
                            
                            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                            download_filename = f"user_posts_{username}_{timestamp}.csv"
                            
                            st.download_button(
                                label="📥 下載CSV文件",
                                data=csv_content,
                                file_name=download_filename,
                                mime="text/csv",
                                key=f"download_user_csv_{username}"
                            )
                        
                    else:
                        st.error(f"❌ 導出失敗: {export_result.get('error', '未知錯誤')}")
                else:
                    st.error(f"❌ 導出腳本執行失敗")
                    if result.stderr:
                        st.text(f"錯誤詳情: {result.stderr}")
                        
            finally:
                # 清理臨時文件
                try:
                    os.unlink(temp_script)
                except:
                    pass
                    
        except Exception as e:
            st.error(f"❌ 導出操作失敗: {str(e)}")
    
    def _show_json_download_button(self, results_file):
        """顯示JSON下載按鈕"""
        if results_file and Path(results_file).exists():
            try:
                # 讀取JSON文件內容
                with open(results_file, 'r', encoding='utf-8') as f:
                    json_content = f.read()
                
                # 生成下載文件名（包含時間戳）
                file_path = Path(results_file)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                download_filename = f"crawl_results_{timestamp}.json"
                
                # 使用 st.download_button 提供下載
                st.download_button(
                    label="💾 下載JSON",
                    data=json_content,
                    file_name=download_filename,
                    mime="application/json",
                    help="下載爬取結果JSON文件到您的下載資料夾",
                    key="download_json_btn"
                )
                
            except Exception as e:
                st.error(f"❌ 準備下載文件失敗: {e}")
        else:
            st.button("💾 下載JSON", disabled=True, help="暫無可下載的結果文件")
    
    def _clear_results(self):
        """清除當前結果"""
        if 'realtime_results' in st.session_state:
            del st.session_state.realtime_results
        if 'realtime_results_file' in st.session_state:
            del st.session_state.realtime_results_file
        if 'realtime_error' in st.session_state:
            del st.session_state.realtime_error
        if 'latest_csv_file' in st.session_state:
            del st.session_state.latest_csv_file
        st.success("🗑️ 結果已清除")
        st.rerun()  # 重新運行頁面來刷新UI
    
    def _render_results_area(self):
        """渲染結果區域"""
        if 'realtime_results' in st.session_state:
            self._show_results()
        elif 'realtime_error' in st.session_state:
            st.error(f"❌ 爬取錯誤：{st.session_state.realtime_error}")
        else:
            st.info("👆 點擊「開始爬取」來開始，或上傳CSV文件查看之前的結果")
    
    def _show_results(self):
        """顯示爬取結果"""
        # 從session state獲取結果（可能是字典格式）
        realtime_results = st.session_state.realtime_results
        
        # 檢查results的格式，如果是字典則提取results列表
        if isinstance(realtime_results, dict):
            results = realtime_results.get('results', [])
        else:
            results = realtime_results if realtime_results else []
        
        results_file = st.session_state.get('realtime_results_file', 'unknown.json')
        
        st.subheader("📊 爬取結果")
        
        # 確保results是列表
        if not isinstance(results, list):
            st.error("❌ 結果格式錯誤，請重新載入")
            return
        
        # 基本統計
        total_posts = len(results)
        successful_views = len([r for r in results if isinstance(r, dict) and r.get('has_views')])
        successful_content = len([r for r in results if isinstance(r, dict) and r.get('has_content')])
        successful_likes = len([r for r in results if isinstance(r, dict) and r.get('has_likes')])
        successful_comments = len([r for r in results if isinstance(r, dict) and r.get('has_comments')])
        
        # 統計指標
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("總貼文數", total_posts)
        with col2:
            st.metric("觀看數成功", f"{successful_views}/{total_posts}")
        with col3:
            st.metric("內容成功", f"{successful_content}/{total_posts}")
        with col4:
            st.metric("互動數據", f"{successful_likes}/{total_posts}")
        
        # 顯示爬取耗時
        crawl_duration = st.session_state.get('realtime_crawl_duration')
        if crawl_duration is not None:
            st.markdown("---")
            if crawl_duration < 60:
                duration_display = f"{crawl_duration:.1f} 秒"
            else:
                duration_display = f"{crawl_duration/60:.1f} 分鐘"
            
            col_time = st.columns(1)[0]
            with col_time:
                st.metric(
                    label="⏱️ 爬取耗時", 
                    value=duration_display,
                    help="從開始爬取到完成的總時間"
                )
        
        # 成功率指標
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            view_rate = (successful_views / total_posts * 100) if total_posts > 0 else 0
            st.metric("觀看數成功率", f"{view_rate:.1f}%")
        with col2:
            content_rate = (successful_content / total_posts * 100) if total_posts > 0 else 0
            st.metric("內容成功率", f"{content_rate:.1f}%")
        with col3:
            like_rate = (successful_likes / total_posts * 100) if total_posts > 0 else 0
            st.metric("按讚數成功率", f"{like_rate:.1f}%")
        with col4:
            comment_rate = (successful_comments / total_posts * 100) if total_posts > 0 else 0
            st.metric("留言數成功率", f"{comment_rate:.1f}%")
        
        # 重複處理功能
        st.divider()
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            st.write("**🔄 重複處理**")
            st.caption("檢測重複貼文，觀看數低的用API重新提取")
        with col2:
            if st.button("🔍 檢測重複", key="detect_duplicates"):
                self._detect_duplicates()
        with col3:
            if st.button("🔄 處理重複", key="process_duplicates"):
                self._process_duplicates()
        
        # 詳細結果表格
        if st.checkbox("📋 顯示詳細結果", key="show_detailed_results"):
            self._show_detailed_table(results)
        
        # 資料庫狀態和備用保存
        if isinstance(realtime_results, dict):
            db_saved = realtime_results.get('database_saved', False)
            saved_count = realtime_results.get('database_saved_count', 0)
            if db_saved:
                st.success(f"✅ 已保存到資料庫 ({saved_count} 個貼文)")
            else:
                # 顯示備用保存選項
                col_info, col_save = st.columns([3, 1])
                with col_info:
                    st.info("ℹ️ 爬蟲通常會自動保存到資料庫。如果統計中沒有看到新數據，您可以使用備用保存功能")
                with col_save:
                    if st.button("💾 備用保存", key="save_to_database", help="手動保存到資料庫（備用功能）"):
                        self._save_results_to_database()
        else:
            st.info("💡 增量爬取模式會自動保存到資料庫並更新統計")

        st.divider()
        
        # 下載和導出按鈕
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            self._show_json_download_button(results_file)
        
        with col2:
            if st.button("📊 導出CSV", key="export_csv"):
                # 切換CSV導出面板的可見性
                st.session_state.show_realtime_csv_export = not st.session_state.get('show_realtime_csv_export', False)
                st.rerun()
        
        with col3:
            if st.button("📈 歷史分析", key="export_history"):
                # 切換歷史分析面板的可見性
                st.session_state.show_realtime_history_analysis = not st.session_state.get('show_realtime_history_analysis', False)
                st.rerun()
            
        # 顯示CSV導出面板（如果啟用）
        if st.session_state.get('show_realtime_csv_export', False):
            self._show_csv_export_options(results_file)
            
        # 顯示歷史分析面板（如果啟用）
        if st.session_state.get('show_realtime_history_analysis', False):
            self._show_export_history_options()
        
        with col4:
            if st.button("🔍 更多導出", key="more_exports"):
                # 切換更多導出面板的可見性
                st.session_state.show_realtime_advanced_exports = not st.session_state.get('show_realtime_advanced_exports', False)
                st.rerun()
        
        # 顯示更多導出面板（如果啟用）
        if st.session_state.get('show_realtime_advanced_exports', False):
            self._show_advanced_export_options()
    
    def _detect_duplicates(self):
        """檢測重複貼文"""
        if 'realtime_results' not in st.session_state:
            st.error("❌ 沒有可檢測的結果")
            return
        
        results = st.session_state.realtime_results
        
        # 按 post_id 分組
        from collections import defaultdict
        grouped = defaultdict(list)
        for result in results:
            if result.get('post_id'):
                grouped[result['post_id']].append(result)
        
        # 找出重複項
        duplicates = {k: v for k, v in grouped.items() if len(v) > 1}
        
        if not duplicates:
            st.success("✅ 沒有發現重複貼文")
            return
        
        st.warning(f"⚠️ 發現 {len(duplicates)} 組重複貼文")
        
        for post_id, items in duplicates.items():
            with st.expander(f"📋 重複組: {post_id} ({len(items)} 個版本)"):
                for i, item in enumerate(items):
                    views = item.get('views', 'N/A')
                    source = item.get('source', 'unknown')
                    content = item.get('content', 'N/A')[:100] + '...' if item.get('content') else 'N/A'
                    
                    col1, col2, col3 = st.columns([1, 1, 3])
                    with col1:
                        st.write(f"**版本 {i+1}**")
                        st.write(f"觀看數: {views}")
                    with col2:
                        st.write(f"來源: {source}")
                    with col3:
                        st.write(f"內容: {content}")
    
    def _process_duplicates(self):
        """處理重複貼文"""
        if 'realtime_results' not in st.session_state:
            st.error("❌ 沒有可處理的結果")
            return
        
        # 調用重複處理腳本
        try:
            import subprocess
            import sys
            import os
            
            st.info("🔄 正在處理重複貼文...")
            
            # 執行重複處理腳本
            script_path = "fix_duplicates_reextract.py"
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                cwd=os.getcwd()
            )
            
            if result.returncode == 0:
                # 查找處理後的文件
                import glob
                from pathlib import Path
                
                # 檢查新的資料夾位置
                extraction_dir = Path("extraction_results")
                if extraction_dir.exists():
                    dedup_files = list(extraction_dir.glob("realtime_extraction_results_*_dedup.json"))
                else:
                    dedup_files = [Path(f) for f in glob.glob("realtime_extraction_results_*_dedup.json")]
                
                if dedup_files:
                    latest_dedup = max(dedup_files, key=lambda f: f.stat().st_mtime)
                    
                    # 讀取處理後的結果
                    import json
                    with open(latest_dedup, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # 更新session_state
                    st.session_state.realtime_results = data.get('results', [])
                    st.session_state.realtime_results_file = latest_dedup
                    
                    duplicates_count = data.get('duplicates_processed', 0)
                    reextracted_count = data.get('reextracted_count', 0)
                    
                    st.success(f"✅ 重複處理完成！")
                    st.info(f"📊 處理了 {duplicates_count} 組重複，重新提取 {reextracted_count} 個項目")
                    st.balloons()
                    
                    # 自動刷新頁面以顯示更新結果
                    st.rerun()
                else:
                    st.error("❌ 未找到處理後的結果文件")
            else:
                st.error(f"❌ 處理失敗：{result.stderr}")
                st.code(result.stdout)
                
        except Exception as e:
            st.error(f"❌ 處理錯誤：{str(e)}")
    
    def _show_csv_export_options(self, json_file_path: str):
        """顯示CSV導出選項"""
        with st.expander("📊 CSV導出選項", expanded=True):
            # 添加關閉按鈕
            col_header1, col_header2 = st.columns([4, 1])
            with col_header1:
                st.write("**選擇排序方式（建議按觀看數排序）**")
            with col_header2:
                if st.button("❌ 關閉", key="close_realtime_csv_export"):
                    st.session_state.show_realtime_csv_export = False
                    st.rerun()
            
            sort_options = {
                "觀看數 (高→低)": "views",
                "按讚數 (高→低)": "likes", 
                "留言數 (高→低)": "comments",
                "轉發數 (高→低)": "reposts",
                "分享數 (高→低)": "shares",
                "貼文ID (A→Z)": "post_id",
                "原始順序 (不排序)": "none"
            }
            
            selected_sort = st.selectbox(
                "排序方式",
                options=list(sort_options.keys()),
                index=0,  # 預設選擇觀看數排序
                help="選擇CSV文件中數據的排序方式，建議選擇觀看數以便分析最受歡迎的貼文"
            )
            
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("📥 生成CSV", key="export_csv_generate"):
                    sort_by = sort_options[selected_sort]
                    self._export_current_to_csv(json_file_path, sort_by)
                
                # 檢查是否有生成好的CSV可以下載
                self._show_csv_download_if_available()
            
            with col2:
                st.info("💡 **CSV使用提示：**\n- 用Excel或Google Sheets打開\n- 可以進一步篩選和分析\n- 支援中文顯示")
    
    def _export_current_to_csv(self, json_file_path: str, sort_by: str = 'views'):
        """導出當次結果到CSV"""
        try:
            from common.csv_export_manager import CSVExportManager
            import os
            
            csv_manager = CSVExportManager()
            
            # 確保exports目錄存在（使用絕對路徑，適合Ubuntu部署）
            import tempfile
            
            # 在生產環境中，優先使用 /app/exports，開發環境使用相對路徑
            if os.path.exists('/app'):  # Docker 容器環境
                exports_dir = "/app/exports"
            else:  # 開發環境
                exports_dir = os.path.abspath("exports")
            
            if not os.path.exists(exports_dir):
                os.makedirs(exports_dir, mode=0o755)  # 設置適當權限
            
            # 生成完整的輸出路徑
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            with open(json_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            username = data.get('target_username', 'unknown')
            
            csv_filename = f"export_current_{username}_{timestamp}.csv"
            csv_output_path = os.path.join(exports_dir, csv_filename)
            
            # 調用CSV生成（使用絕對路徑）
            csv_file = csv_manager.export_current_session(json_file_path, output_path=csv_output_path, sort_by=sort_by)
            
            # 驗證文件是否真的被創建
            if not os.path.exists(csv_file):
                raise FileNotFoundError(f"CSV文件創建失敗: {csv_file}")
            
            # 檢查文件大小
            file_size = os.path.getsize(csv_file)
            if file_size == 0:
                raise ValueError(f"CSV文件為空: {csv_file}")
            
            # 檢查文件權限（Ubuntu環境重要）
            if not os.access(csv_file, os.R_OK):
                raise PermissionError(f"CSV文件無讀取權限: {csv_file}")
            
            # 驗證文件內容的UTF-8編碼（Ubuntu環境驗證）
            try:
                with open(csv_file, 'r', encoding='utf-8-sig') as test_f:
                    test_f.read(100)  # 讀取前100個字符測試編碼
            except UnicodeDecodeError as e:
                raise ValueError(f"CSV文件編碼問題: {e}")
            
            # 保存CSV文件路徑到會話狀態
            st.session_state.latest_csv_file = csv_file
            
            st.success(f"✅ CSV生成成功！")
            st.info(f"📁 文件位置: {csv_file}")
            st.info(f"📏 文件大小: {file_size} bytes")
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            st.error(f"❌ CSV生成失敗: {str(e)}")
            st.error(f"🔍 詳細錯誤: {error_details}")
            if 'latest_csv_file' in st.session_state:
                del st.session_state.latest_csv_file
    
    def _show_csv_download_if_available(self):
        """顯示CSV下載按鈕（如果有可用的CSV文件）"""
        if 'latest_csv_file' in st.session_state:
            csv_file = st.session_state.latest_csv_file
            if csv_file and Path(csv_file).exists():
                try:
                    with open(csv_file, 'rb') as f:
                        csv_content = f.read()
                    
                    # 生成時間戳文件名
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    download_filename = f"crawl_results_{timestamp}.csv"
                    
                    st.download_button(
                        label="📥 下載CSV文件",
                        data=csv_content,
                        file_name=download_filename,
                        mime="text/csv",
                        help="下載CSV文件到您的下載資料夾",
                        key="download_csv_file_btn"
                    )
                    
                except Exception as e:
                    st.error(f"❌ 準備CSV下載失敗: {e}")
    
    def _show_export_history_options(self):
        """顯示歷史導出選項"""
        # 添加關閉按鈕
        col_header1, col_header2 = st.columns([4, 1])
        with col_header1:
            st.write("**📈 歷史數據分析**")
        with col_header2:
            if st.button("❌ 關閉", key="close_realtime_history_analysis"):
                st.session_state.show_realtime_history_analysis = False
                st.rerun()
        
        if 'realtime_results' not in st.session_state:
            st.error("❌ 請先執行爬取以獲取帳號信息")
            return
        
        # 獲取當前帳號
        results = st.session_state.realtime_results
        if not results:
            st.error("❌ 無法獲取帳號信息")
            return
        
        # 🔧 修復：從結果中提取用戶名和用戶ID
        target_username = None
        target_user_id = None
        
        if 'realtime_results_file' in st.session_state:
            try:
                import json
                with open(st.session_state.realtime_results_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                target_username = data.get('target_username')
                target_user_id = data.get('target_user_id')
            except:
                pass
        
        # 🔧 修復：從當前結果中嘗試獲取用戶信息
        if not target_username and isinstance(results, dict) and 'results' in results:
            first_result = results['results'][0] if results['results'] else None
            if first_result:
                target_username = first_result.get('username')
                target_user_id = first_result.get('user_id') or target_username
        elif not target_username and isinstance(results, list) and results:
            first_result = results[0] if results else None
            if first_result:
                target_username = first_result.get('username')
                target_user_id = first_result.get('user_id') or target_username
        
        if not target_username:
            st.error("❌ 無法識別目標帳號")
            return
        
        # 如果沒有user_id，使用username作為fallback
        if not target_user_id:
            target_user_id = target_username
        
        # 添加排序設定
        st.write("**📊 排序設定**")
        col_sort1, col_sort2 = st.columns(2)
        
        with col_sort1:
            sort_by = st.selectbox(
                "排序依據",
                options=["fetched_at", "views_count", "likes_count", "comments_count", "calculated_score"],
                format_func=lambda x: {
                    "fetched_at": "爬取時間",
                    "views_count": "觀看數", 
                    "likes_count": "按讚數",
                    "comments_count": "留言數",
                    "calculated_score": "計算分數"
                }.get(x, x),
                key="realtime_history_sort_by",
                help="選擇排序的依據欄位"
            )
        
        with col_sort2:
            sort_order = st.selectbox(
                "排序順序",
                options=["DESC", "ASC"],
                format_func=lambda x: "降序 (高到低)" if x == "DESC" else "升序 (低到高)",
                key="realtime_history_sort_order",
                help="選擇排序順序"
            )
        
        # 導出類型選擇
        export_type = st.radio(
            "選擇導出類型",
            options=["最近數據", "全部歷史", "統計分析"],
            help="選擇要導出的歷史數據範圍",
            key="realtime_export_type"
        )
        
        # 最大記錄數設定
        max_records = st.number_input(
            "最大記錄數",
            min_value=100,
            max_value=50000,
            value=5000,
            help="限制導出的最大記錄數",
            key="realtime_max_records"
        )
        
        # 導出按鈕和操作
        if export_type == "最近數據":
            col1, col2 = st.columns(2)
            with col1:
                days_back = st.number_input("回溯天數", min_value=1, max_value=365, value=7, key="realtime_days_back")
            
            if st.button("📊 導出最近數據", key="realtime_export_recent"):
                self._export_history_data(target_user_id, "recent", 
                                        days_back=days_back, limit=max_records, 
                                        sort_by=sort_by, sort_order=sort_order)
        
        elif export_type == "全部歷史":
            if st.button("📊 導出全部歷史", key="realtime_export_all"):
                self._export_history_data(target_user_id, "all", 
                                        limit=max_records, sort_by=sort_by, sort_order=sort_order)
        
        elif export_type == "統計分析":
            st.info("按日期統計的分析報告，包含平均觀看數、成功率等指標")
            
            if st.button("📈 導出統計分析", key="realtime_export_analysis"):
                self._export_history_data(target_user_id, "analysis", 
                                        sort_by=sort_by, sort_order=sort_order)
    
    def _export_history_data(self, username: str, export_type: str, **kwargs):
        """導出歷史數據"""
        try:
            import asyncio
            import json
            import pandas as pd
            from datetime import datetime
            
            # 獲取排序參數
            sort_by = kwargs.get('sort_by', 'fetched_at')
            sort_order = kwargs.get('sort_order', 'DESC')
            
            with st.spinner(f"🔄 正在從資料庫獲取 @{username} 的{export_type}數據..."):
                # 從資料庫獲取數據
                posts_data = asyncio.run(self._fetch_realtime_history_from_db(username, export_type, **kwargs))
            
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
            
            # 添加統計信息
            summary = self._calculate_realtime_stats(posts_data)
            
            # 顯示統計概覽
            st.write("**📊 數據概覽**")
            col_s1, col_s2, col_s3, col_s4 = st.columns(4)
            with col_s1:
                st.metric("總記錄數", f"{len(posts_data):,}")
            with col_s2:
                st.metric("平均觀看數", f"{summary.get('avg_views', 0):,.0f}")
            with col_s3:
                st.metric("平均按讚數", f"{summary.get('avg_likes', 0):,.0f}")
            with col_s4:
                st.metric("最高觀看數", f"{summary.get('max_views', 0):,.0f}")
            
            # 顯示前10筆數據預覽
            if posts_data:
                st.write("**前10筆數據：**")
                preview_data = []
                for i, post in enumerate(posts_data[:10], 1):
                    content_preview = (post.get('content', '')[:40] + "...") if post.get('content') and len(post.get('content', '')) > 40 else post.get('content', 'N/A')
                    preview_data.append({
                        "#": i,
                        "貼文ID": post.get('post_id', 'N/A')[:20] + "..." if len(post.get('post_id', '')) > 20 else post.get('post_id', 'N/A'),
                        "內容預覽": content_preview,
                        "觀看數": f"{post.get('views_count', 0):,}",
                        "按讚數": f"{post.get('likes_count', 0):,}",
                        "爬取時間": str(post.get('fetched_at', 'N/A'))[:19]
                    })
                st.dataframe(preview_data, use_container_width=True)
            
            st.success(f"✅ {export_type}數據導出完成！共 {len(posts_data)} 筆記錄")
            
            # 準備下載數據
            data = {
                "username": username,
                "export_type": export_type,
                "exported_at": datetime.now().isoformat(),
                "sort_by": sort_by,
                "sort_order": sort_order,
                "total_records": len(posts_data),
                "summary": summary,
                "data": posts_data
            }
            
            # 提供 JSON 和 CSV 下載
            col1, col2 = st.columns(2)
            
            with col1:
                # JSON 下載
                json_data = json.dumps(data, ensure_ascii=False, indent=2, default=str)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                json_filename = f"realtime_history_{username}_{export_type}_{timestamp}.json"
                
                st.download_button(
                    label="📥 下載 JSON",
                    data=json_data,
                    file_name=json_filename,
                    mime="application/json",
                    help="下載完整的JSON格式數據",
                    use_container_width=True
                )
            
            with col2:
                # CSV 下載
                df = pd.DataFrame(posts_data)
                csv_content = df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
                csv_filename = f"realtime_history_{username}_{export_type}_{timestamp}.csv"
                
                st.download_button(
                    label="📥 下載 CSV",
                    data=csv_content,
                    file_name=csv_filename,
                    mime="text/csv",
                    help="下載CSV格式數據（適合Excel開啟）",
                    use_container_width=True
                )
                
        except Exception as e:
            st.error(f"❌ 歷史數據導出失敗: {str(e)}")
            import traceback
            st.error(f"詳細錯誤: {traceback.format_exc()}")
    
    async def _fetch_realtime_history_from_db(self, user_identifier: str, export_type: str, **kwargs):
        """從資料庫獲取實時爬蟲的歷史數據"""
        try:
            from common.db_client import DatabaseClient
            
            db = DatabaseClient()
            await db.init_pool()
            
            async with db.get_connection() as conn:
                # 🔧 修復：構建更智能的查詢，支援用戶ID和用戶名查詢
                base_query = """
                    SELECT post_id, username, content, views_count, likes_count, comments_count, 
                           reposts_count, shares_count, calculated_score, tags, images, videos, url, 
                           created_at, fetched_at, post_published_at
                    FROM post_metrics_sql 
                    WHERE (username = $1 OR post_id LIKE $2)
                """
                
                # 🔧 修復：支援用戶ID模式查詢 (user_id_%)
                params = [user_identifier, f"{user_identifier}_%"]
                
                # 根據導出類型添加條件
                if export_type == "recent":
                    days_back = kwargs.get('days_back', 7)
                    base_query += f" AND fetched_at >= NOW() - INTERVAL '{days_back} days'"
                
                # 添加排序和限制
                sort_by = kwargs.get('sort_by', 'fetched_at')
                sort_order = kwargs.get('sort_order', 'DESC')
                limit = kwargs.get('limit', 5000)
                
                base_query += f" ORDER BY {sort_by} {sort_order} LIMIT $" + str(len(params) + 1)
                params.append(limit)
                
                # 執行查詢
                rows = await conn.fetch(base_query, *params)
                
                # 轉換為字典列表
                posts = []
                for row in rows:
                    post_dict = dict(row)
                    # 處理陣列字段
                    for field in ['tags', 'images', 'videos']:
                        if isinstance(post_dict.get(field), str):
                            try:
                                post_dict[field] = json.loads(post_dict[field])
                            except:
                                post_dict[field] = []
                    posts.append(post_dict)
                
                return posts
                
        except Exception as e:
            st.error(f"資料庫查詢失敗: {e}")
            return []
    
    def _calculate_realtime_stats(self, posts_data):
        """計算實時爬蟲數據的統計信息"""
        if not posts_data:
            return {}
        
        views = [post.get('views_count', 0) for post in posts_data if post.get('views_count')]
        likes = [post.get('likes_count', 0) for post in posts_data if post.get('likes_count')]
        comments = [post.get('comments_count', 0) for post in posts_data if post.get('comments_count')]
        
        return {
            "total_posts": len(posts_data),
            "avg_views": sum(views) / len(views) if views else 0,
            "max_views": max(views) if views else 0,
            "min_views": min(views) if views else 0,
            "avg_likes": sum(likes) / len(likes) if likes else 0,
            "max_likes": max(likes) if likes else 0,
            "avg_comments": sum(comments) / len(comments) if comments else 0,
            "max_comments": max(comments) if comments else 0
        }
    
    def _show_advanced_export_options(self):
        """顯示進階導出選項"""
        # 添加關閉按鈕
        col_header1, col_header2 = st.columns([4, 1])
        with col_header1:
            st.write("**🔍 進階導出功能**")
        with col_header2:
            if st.button("❌ 關閉", key="close_realtime_advanced_exports"):
                st.session_state.show_realtime_advanced_exports = False
                st.rerun()
        
        st.markdown("**更多導出選項和批量操作**")
        
        tab1, tab2, tab3 = st.tabs(["📊 對比報告", "🔄 批量導出", "⚡ 快速工具"])
        
        with tab1:
            st.subheader("📊 多次爬取對比報告")
            st.info("比較多次爬取結果的效能和成功率")
            
            # 查找所有JSON文件
            import glob
            import os
            # 檢查新的資料夾位置
            extraction_dir = Path("extraction_results")
            if extraction_dir.exists():
                json_files = list(extraction_dir.glob("realtime_extraction_results_*.json"))
            else:
                json_files = [Path(f) for f in glob.glob("realtime_extraction_results_*.json")]
            
            if len(json_files) >= 2:
                st.write(f"🔍 找到 {len(json_files)} 個爬取結果文件：")
                
                st.info("📊 對比報告功能：比較多次爬取結果的效能和成功率")
                st.write(f"🔍 找到 {len(json_files)} 個結果文件")
                
                # 簡化的文件選擇
                file_names = [f.name for f in sorted(json_files, reverse=True)[:5]]
                if file_names:
                    selected_file = st.selectbox(
                        "選擇一個文件查看詳情：",
                        options=file_names,
                        help="查看文件的基本信息"
                    )
                    
                    if selected_file:
                        st.success(f"✅ 選中文件: {selected_file}")
                        # 這裡可以添加更多文件詳情展示
            else:
                st.warning("⚠️ 需要至少2個爬取結果文件才能進行對比")
            
            with tab2:
                st.subheader("🔄 批量導出功能")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    if st.button("📥 導出所有最新結果", key="export_all_latest"):
                        self._export_all_latest_results()
                
                with col2:
                    if st.button("📈 導出所有帳號統計", key="export_all_stats"):
                        self._export_all_account_stats()
                
                st.divider()
                
                # 自動化導出設定
                st.write("**自動化導出設定**")
                auto_sort = st.selectbox(
                    "預設排序方式",
                    ["觀看數", "按讚數", "留言數", "時間順序"],
                    help="批量導出時使用的預設排序"
                )
                
                if st.button("💾 保存設定", key="save_export_settings"):
                    st.session_state.default_sort = auto_sort
                    st.success(f"✅ 已保存預設排序: {auto_sort}")
            
            with tab3:
                st.subheader("⚡ 快速工具")
                
                # 快速預覽
                st.write("**快速預覽CSV文件**")
                uploaded_csv = st.file_uploader(
                    "上傳CSV文件進行預覽",
                    type=['csv'],
                    help="上傳任何CSV文件，快速查看前幾行數據"
                )
                
                if uploaded_csv:
                    try:
                        import pandas as pd
                        df = pd.read_csv(uploaded_csv, encoding='utf-8-sig')
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.metric("總行數", len(df))
                        with col2:
                            st.metric("總欄位", len(df.columns))
                        
                        st.write("**前10行預覽：**")
                        st.dataframe(df.head(10), use_container_width=True)
                        
                    except Exception as e:
                        st.error(f"❌ 預覽失敗: {e}")
                
                st.divider()
                
                # 清理工具
                st.write("**清理工具**")
                if st.button("🗑️ 清理舊的導出文件", key="cleanup_exports"):
                    self._cleanup_old_exports()
    
    def _extract_time_from_filename(self, filename: str) -> str:
        """從文件名提取時間"""
        try:
            import re
            match = re.search(r'_(\d{8}_\d{6})\.json$', filename)
            if match:
                time_str = match.group(1)
                # 格式化為可讀時間
                date_part = time_str[:8]
                time_part = time_str[9:]
                return f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]} {time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}"
        except:
            pass
        return "未知時間"
    
    def _generate_comparison_report(self, selected_files: List[str]):
        """生成對比報告"""
        try:
            from common.csv_export_manager import CSVExportManager
            
            csv_manager = CSVExportManager()
            csv_file = csv_manager.export_comparison_report(selected_files)
            
            st.success("✅ 對比報告生成成功！")
            st.info(f"📁 文件位置: {csv_file}")
            
            # 提供下載
            import os
            if os.path.exists(csv_file):
                with open(csv_file, 'r', encoding='utf-8-sig') as f:
                    csv_content = f.read()
                
                st.download_button(
                    label="📥 下載對比報告",
                    data=csv_content,
                    file_name=os.path.basename(csv_file),
                    mime="text/csv"
                )
                
                # 顯示摘要
                st.write("**📊 對比摘要：**")
                import pandas as pd
                df = pd.read_csv(csv_file, encoding='utf-8-sig')
                
                # 顯示完整表格
                st.dataframe(df, use_container_width=True)
                
                # 顯示關鍵指標對比
                if len(df) >= 2:
                    st.write("**🔍 關鍵指標分析：**")
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        avg_success_rate = df['成功率(%)'].mean()
                        max_success_rate = df['成功率(%)'].max()
                        min_success_rate = df['成功率(%)'].min()
                        st.metric("平均成功率", f"{avg_success_rate:.1f}%", 
                                 f"{max_success_rate - min_success_rate:.1f}% 差距")
                    
                    with col2:
                        if '總耗時(秒)' in df.columns:
                            avg_time = df['總耗時(秒)'].mean()
                            fastest = df['總耗時(秒)'].min()
                            slowest = df['總耗時(秒)'].max()
                            st.metric("平均耗時", f"{avg_time:.1f}s", 
                                     f"{slowest - fastest:.1f}s 差距")
                    
                    with col3:
                        if '觀看數提取率(%)' in df.columns:
                            avg_views_rate = df['觀看數提取率(%)'].mean()
                            st.metric("平均觀看數提取率", f"{avg_views_rate:.1f}%")
                
                # 顯示趨勢分析
                if len(df) >= 3:
                    st.write("**📈 趨勢分析：**")
                    
                    # 按時間排序
                    df_sorted = df.sort_values('爬取時間') if '爬取時間' in df.columns else df
                    
                    # 成功率趨勢
                    success_trend = df_sorted['成功率(%)'].diff().iloc[-1] if len(df_sorted) > 1 else 0
                    if success_trend > 0:
                        st.success(f"📈 成功率呈上升趨勢 (+{success_trend:.1f}%)")
                    elif success_trend < 0:
                        st.error(f"📉 成功率呈下降趨勢 ({success_trend:.1f}%)")
                    else:
                        st.info("📊 成功率保持穩定")
                
        except Exception as e:
            st.error(f"❌ 生成對比報告失敗: {e}")
    
    def _export_all_latest_results(self):
        """導出所有最新結果"""
        try:
            import glob
            # 檢查新的資料夾位置  
            extraction_dir = Path("extraction_results")
            if extraction_dir.exists():
                json_files = list(extraction_dir.glob("realtime_extraction_results_*.json"))
            else:
                json_files = [Path(f) for f in glob.glob("realtime_extraction_results_*.json")]
            
            if not json_files:
                st.warning("⚠️ 未找到任何爬取結果文件")
                return
            
            # 找最新的文件
            latest_file = max(json_files, key=lambda f: f.stat().st_mtime)
            
            from common.csv_export_manager import CSVExportManager
            csv_manager = CSVExportManager()
            
            # 使用預設排序
            default_sort = getattr(st.session_state, 'default_sort', '觀看數')
            sort_mapping = {"觀看數": "views", "按讚數": "likes", "留言數": "comments", "時間順序": "none"}
            sort_by = sort_mapping.get(default_sort, "views")
            
            csv_file = csv_manager.export_current_session(latest_file, sort_by=sort_by)
            
            st.success("✅ 最新結果導出成功！")
            st.info(f"📁 使用了 {latest_file}")
            st.info(f"📊 按 {default_sort} 排序")
            
            # 提供下載
            import os
            if os.path.exists(csv_file):
                with open(csv_file, 'r', encoding='utf-8-sig') as f:
                    csv_content = f.read()
                
                st.download_button(
                    label="📥 下載最新結果CSV",
                    data=csv_content,
                    file_name=os.path.basename(csv_file),
                    mime="text/csv"
                )
                
        except Exception as e:
            st.error(f"❌ 導出失敗: {e}")
    
    def _export_all_account_stats(self):
        """導出所有帳號統計"""
        try:
            from common.incremental_crawl_manager import IncrementalCrawlManager
            import asyncio
            
            # 創建事件循環
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                manager = IncrementalCrawlManager()
                
                # 獲取所有帳號
                results = loop.run_until_complete(manager.db.fetch_all("""
                    SELECT DISTINCT username FROM crawl_state ORDER BY last_crawl_at DESC
                """))
                
                if not results:
                    st.warning("⚠️ 未找到任何爬取記錄")
                    return
                
                all_stats = []
                for row in results:
                    username = row['username']
                    summary = loop.run_until_complete(manager.get_crawl_summary(username))
                    
                    if 'error' not in summary:
                        checkpoint = summary['checkpoint']
                        stats = summary['statistics']
                        
                        all_stats.append({
                            '帳號': f"@{username}",
                            '最新貼文ID': checkpoint['latest_post_id'] or 'N/A',
                            '累計爬取': checkpoint['total_crawled'],
                            '資料庫貼文數': stats['total_posts'],
                            '有觀看數貼文': stats['posts_with_views'],
                            '平均觀看數': round(stats['avg_views'], 0),
                            '最高觀看數': stats['max_views'],
                            '上次爬取': checkpoint['last_crawl_at'].strftime('%Y-%m-%d %H:%M') if checkpoint['last_crawl_at'] else 'N/A'
                        })
                
                if all_stats:
                    # 轉換為CSV
                    import pandas as pd
                    df = pd.DataFrame(all_stats)
                    
                    from datetime import datetime
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    csv_file = f"export_all_accounts_stats_{timestamp}.csv"
                    
                    # 使用字節流導出並提供下載
                    import io
                    output = io.BytesIO()
                    df.to_csv(output, index=False, encoding='utf-8-sig')
                    csv_content = output.getvalue().encode('utf-8-sig')
                    
                    st.download_button(
                        label="📥 下載所有帳號統計",
                        data=csv_content,
                        file_name=csv_file,
                        mime="text/csv",
                        help="下載所有帳號的統計數據"
                    )
                    st.success("✅ 所有帳號統計準備完成！")
                    
                    # 顯示預覽
                    st.write("**統計預覽：**")
                    st.dataframe(df, use_container_width=True)
                    
                    # 提供下載 - 使用字節流確保正確編碼
                    import io
                    output = io.BytesIO()
                    df.to_csv(output, index=False, encoding='utf-8-sig')
                    csv_content = output.getvalue().encode('utf-8-sig')
                    st.download_button(
                        label="📥 下載帳號統計",
                        data=csv_content,
                        file_name=csv_file,
                        mime="text/csv"
                    )
                else:
                    st.warning("⚠️ 未找到有效的統計數據")
                    
            finally:
                loop.close()
                
        except Exception as e:
            st.error(f"❌ 導出帳號統計失敗: {e}")
    
    def _cleanup_old_exports(self):
        """清理舊的導出文件"""
        try:
            import glob
            import os
            from datetime import datetime, timedelta
            
            # 找到所有導出文件
            export_patterns = [
                "export_current_*.csv",
                "export_history_*.csv", 
                "export_analysis_*.csv",
                "export_comparison_*.csv"
            ]
            
            old_files = []
            cutoff_date = datetime.now() - timedelta(days=7)  # 7天前
            
            for pattern in export_patterns:
                files = glob.glob(pattern)
                for file in files:
                    file_time = datetime.fromtimestamp(os.path.getmtime(file))
                    if file_time < cutoff_date:
                        old_files.append(file)
            
            if old_files:
                st.write(f"🔍 找到 {len(old_files)} 個7天前的導出文件：")
                
                for file in old_files[:5]:  # 只顯示前5個
                    st.text(f"- {file}")
                
                if len(old_files) > 5:
                    st.text(f"... 以及其他 {len(old_files) - 5} 個文件")
                
                if st.button("🗑️ 確認刪除", key="confirm_cleanup"):
                    deleted_count = 0
                    for file in old_files:
                        try:
                            os.remove(file)
                            deleted_count += 1
                        except:
                            pass
                    
                    st.success(f"✅ 已刪除 {deleted_count} 個舊文件")
            else:
                st.info("✨ 沒有找到需要清理的舊文件")
                
        except Exception as e:
            st.error(f"❌ 清理失敗: {e}")
    
    def _show_detailed_table(self, results: List[Dict]):
        """顯示詳細結果表格"""
        st.subheader("📋 詳細結果")
        
        # 準備表格數據
        table_data = []
        for r in results:
            table_data.append({
                "貼文ID": r.get('post_id', 'N/A'),
                "觀看數": r.get('views', 'N/A'),
                "按讚數": r.get('likes', 'N/A'),
                "留言數": r.get('comments', 'N/A'),
                "轉發數": r.get('reposts', 'N/A'),
                "分享數": r.get('shares', 'N/A'),
                "內容預覽": (r.get('content', '')[:50] + "...") if r.get('content') else 'N/A',
                "來源": r.get('source', 'N/A'),
                "重新提取": "✅" if r.get('reextracted', False) else ""
            })
        
        # 顯示表格
        st.dataframe(
            table_data,
            use_container_width=True,
            height=400
        )
        
        # 互動數據分析
        if st.checkbox("📈 互動數據分析", key="show_engagement_analysis"):
            self._show_engagement_analysis(results)
    
    def _show_engagement_analysis(self, results: List[Dict]):
        """顯示互動數據分析"""
        st.subheader("📈 互動數據分析")
        
        # 收集有效的互動數據
        valid_results = [r for r in results if isinstance(r, dict) and r.get('has_views') and r.get('has_likes')]
        
        if not valid_results:
            st.warning("無足夠的互動數據進行分析")
            return
        
        # 簡單統計
        avg_likes = []
        avg_comments = []
        for r in valid_results:
            if r.get('likes') and r['likes'] != 'N/A':
                try:
                    # 簡化的數字轉換
                    likes_str = str(r['likes']).replace('K', '000').replace('M', '000000')
                    if likes_str.replace('.', '').isdigit():
                        avg_likes.append(float(likes_str))
                except:
                    pass
        
        if avg_likes:
            col1, col2 = st.columns(2)
            with col1:
                st.metric("平均按讚數", f"{sum(avg_likes)/len(avg_likes):.0f}")
            with col2:
                st.metric("最高按讚數", f"{max(avg_likes):.0f}")
    
    def _render_cached_stats(self, stats):
        """渲染緩存的統計信息，並整合新的用戶管理 UI"""
        total_stats = stats.get("total_stats", {})
        if total_stats:
            st.info(f"""
            **📈 總體統計 (Realtime)**
            - 📊 總貼文數: {total_stats.get('total_posts', 0):,}
            - 👥 已爬取用戶: {total_stats.get('total_users', 0)} 個
            - ⏰ 最後活動: {str(total_stats.get('latest_activity', 'N/A'))[:16] if total_stats.get('latest_activity') else 'N/A'}
            """)
        
        user_stats = stats.get("user_stats", [])
        if user_stats:
            st.write("**👥 各用戶統計 (Realtime):**")
            
            import pandas as pd
            df_data = [{
                "用戶名": f"@{user.get('username', 'N/A')}",
                "貼文數": f"{user.get('post_count', 0):,}",
                "最後爬取": str(user.get('latest_crawl', 'N/A'))[:16] if user.get('latest_crawl') else 'N/A'
            } for user in user_stats]

            st.dataframe(
                pd.DataFrame(df_data),
                use_container_width=True,
                hide_index=True,
                height=min(300, len(df_data) * 35 + 38)
            )
            
            # --- 用戶資料管理 ---
            st.markdown("---")
            with st.expander("🗂️ 用戶資料管理 (Realtime)", expanded=False):
                user_options = [user.get('username') for user in user_stats if user.get('username')]
                
                # 使用 session state 持久化選擇
                if 'realtime_selected_user' not in st.session_state or st.session_state.realtime_selected_user not in user_options:
                    st.session_state.realtime_selected_user = user_options[0] if user_options else None

                selected_user = st.selectbox(
                    "選擇要管理的用戶:",
                    options=user_options,
                    key="realtime_user_selector",
                    index=user_options.index(st.session_state.realtime_selected_user) if st.session_state.realtime_selected_user in user_options else 0,
                )

                if selected_user and st.session_state.realtime_selected_user != selected_user:
                    st.session_state.realtime_selected_user = selected_user
                    if 'realtime_confirm_delete_user' in st.session_state:
                        del st.session_state['realtime_confirm_delete_user']
                    st.rerun()

                if selected_user:
                    selected_user_info = next((u for u in user_stats if u.get('username') == selected_user), None)
                    if selected_user_info:
                        st.info(f"""
                        **📋 用戶 @{selected_user} 的詳細信息:**
                        - 📊 貼文總數: {selected_user_info.get('post_count', 0):,} 個
                        - ⏰ 最後爬取: {str(selected_user_info.get('latest_crawl', 'N/A'))[:16] if selected_user_info.get('latest_crawl') else 'N/A'}
                        """)
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("📊 導出CSV", key=f"realtime_export_csv_{selected_user}", use_container_width=True):
                            self._export_user_csv(selected_user)
                    with col2:
                        self.handle_delete_button(selected_user) # 呼叫新的刪除處理器
        else:
            st.warning("📝 Realtime 資料庫中暫無爬取記錄")
    
    def _save_results_to_database(self):
        """將當前爬取結果保存到資料庫"""
        if 'realtime_results' not in st.session_state:
            st.error("❌ 沒有可保存的結果")
            return
        
        # 從session state獲取結果
        realtime_results = st.session_state.realtime_results
        
        # 檢查results的格式，如果是字典則提取results列表
        if isinstance(realtime_results, dict):
            results = realtime_results.get('results', [])
            target_username = realtime_results.get('target_username', '')
        else:
            results = realtime_results if realtime_results else []
            target_username = results[0].get('username', '') if results else ''
        
        if not results:
            st.error("❌ 沒有找到可保存的結果")
            return
        
        if not target_username:
            st.error("❌ 無法識別目標用戶名")
            return
        
        try:
            import subprocess
            import json
            import sys
            import os
            import tempfile
            
            # 創建保存腳本
            save_script_content = f'''
import asyncio
import sys
import os
import json
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from common.incremental_crawl_manager import IncrementalCrawlManager

async def save_to_database():
    crawl_manager = IncrementalCrawlManager()
    try:
        await crawl_manager.db.init_pool()
        
        # 準備結果數據
        results = {json.dumps(results, ensure_ascii=False)}
        target_username = "{target_username}"
        
        # 保存結果到資料庫
        saved_count = await crawl_manager.save_quick_crawl_results(results, target_username)
        
        # 更新檢查點（使用最新的貼文ID）
        if results and saved_count > 0:
            latest_post_id = results[0].get('post_id')  # 第一個是最新的
            if latest_post_id:
                await crawl_manager.update_crawl_checkpoint(
                    target_username, 
                    latest_post_id, 
                    saved_count
                )
        
        result = {{
            "success": True,
            "saved_count": saved_count,
            "target_username": target_username
        }}
        
        print(json.dumps(result))
        
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}))
    finally:
        await crawl_manager.db.close_pool()

if __name__ == "__main__":
    asyncio.run(save_to_database())
'''
            
            # 寫入臨時文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                f.write(save_script_content)
                temp_script = f.name
            
            try:
                # 執行保存腳本
                with st.spinner(f"💾 正在保存 {len(results)} 個貼文到資料庫..."):
                    result = subprocess.run(
                        [sys.executable, temp_script],
                        capture_output=True,
                        text=True,
                        encoding='utf-8',
                        cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                        timeout=60
                    )
                
                if result.returncode == 0 and result.stdout.strip():
                    save_result = json.loads(result.stdout.strip())
                    
                    if save_result.get("success"):
                        saved_count = save_result.get("saved_count", 0)
                        
                        st.success(f"""
                        ✅ **保存成功！**
                        
                        已成功將 @{target_username} 的貼文保存到資料庫：
                        - 💾 保存貼文數: {saved_count} 個
                        - 🔄 檢查點已更新
                        """)
                        
                        # 更新session state，標記為已保存
                        if isinstance(st.session_state.realtime_results, dict):
                            st.session_state.realtime_results['database_saved'] = True
                            st.session_state.realtime_results['database_saved_count'] = saved_count
                        
                        # 清理資料庫統計緩存，下次查看會更新
                        if 'db_stats_cache' in st.session_state:
                            del st.session_state.db_stats_cache
                        
                        st.info("📊 資料庫統計已更新，您可以點擊刷新按鈕查看最新數據")
                        
                    else:
                        st.error(f"❌ 保存失敗: {save_result.get('error', '未知錯誤')}")
                else:
                    st.error(f"❌ 保存腳本執行失敗")
                    if result.stderr:
                        st.text(f"錯誤詳情: {result.stderr}")
                        
            finally:
                # 清理臨時文件
                try:
                    os.unlink(temp_script)
                except:
                    pass
                    
        except Exception as e:
            st.error(f"❌ 保存操作失敗: {str(e)}")