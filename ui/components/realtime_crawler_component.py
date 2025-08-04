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

class RealtimeCrawlerComponent:
    def __init__(self):
        self.is_running = False
        self.current_task = None
        
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
            
        with col2:
            col_title, col_refresh = st.columns([3, 1])
            with col_title:
                st.subheader("📊 資料庫統計")
            with col_refresh:
                if st.button("🔄", key="refresh_db_stats", help="刷新統計信息"):
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
            if st.button("🔄 重置", key="reset_realtime"):
                self._reset_results()
        
        # 結果顯示
        self._render_results_area()
    
    def _execute_crawling_simple(self, username: str, max_posts: int, is_incremental: bool = True):
        """簡化的爬取執行方法 - 使用同步版本避免asyncio衝突"""
        if not username.strip():
            st.error("請輸入目標帳號！")
            return
            
        try:
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
            log_text = []
            
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
                while True:
                    output = process.stdout.readline()
                    if output == '' and process.poll() is not None:
                        break
                    if output:
                        line = output.strip()
                        all_output.append(line)
                        log_text.append(line)
                        
                        # 只顯示最後30行，避免界面過長
                        display_lines = log_text[-30:] if len(log_text) > 30 else log_text
                        log_placeholder.code('\n'.join(display_lines), language='text')
                
                # 等待進程完成
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
                    st.success(f"✅ 爬取完成！處理了 {total_processed} 篇貼文")
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
                    
                    # 顯示總體統計
                    total_stats = stats.get("total_stats", {})
                    if total_stats:
                        st.info(f"""
                        **📈 總體統計**
                        - 📊 總貼文數: {total_stats.get('total_posts', 0):,}
                        - 👥 已爬取用戶: {total_stats.get('total_users', 0)} 個
                        - ⏰ 最後活動: {str(total_stats.get('latest_activity', 'N/A'))[:16] if total_stats.get('latest_activity') else 'N/A'}
                        """)
                    
                    # 顯示用戶統計
                    user_stats = stats.get("user_stats", [])
                    if user_stats:
                        st.write("**👥 各用戶統計:**")
                        
                        # 使用表格顯示
                        import pandas as pd
                        df_data = []
                        for user in user_stats:
                            latest = str(user.get('latest_crawl', 'N/A'))[:16] if user.get('latest_crawl') else 'N/A'
                            df_data.append({
                                "用戶名": f"@{user.get('username', 'N/A')}",
                                "貼文數": f"{user.get('post_count', 0):,}",
                                "最後爬取": latest
                            })
                        
                        if df_data:
                            df = pd.DataFrame(df_data)
                            st.dataframe(
                                df, 
                                use_container_width=True,
                                hide_index=True,
                                height=min(300, len(df_data) * 35 + 38)  # 動態高度
                            )
                    else:
                        st.warning("📝 資料庫中暫無爬取記錄")
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
    
    def _reset_results(self):
        """重置結果"""
        if 'realtime_results' in st.session_state:
            del st.session_state.realtime_results
        if 'realtime_results_file' in st.session_state:
            del st.session_state.realtime_results_file
        if 'realtime_error' in st.session_state:
            del st.session_state.realtime_error
        st.success("🔄 結果已重置")
    
    def _render_results_area(self):
        """渲染結果區域"""
        if 'realtime_results' in st.session_state:
            self._show_results()
        elif 'realtime_error' in st.session_state:
            st.error(f"❌ 爬取錯誤：{st.session_state.realtime_error}")
        else:
            st.info("👆 點擊「開始爬取」來開始")
    
    def _show_results(self):
        """顯示爬取結果"""
        results = st.session_state.realtime_results
        results_file = st.session_state.get('realtime_results_file', 'unknown.json')
        
        st.subheader("📊 爬取結果")
        
        # 基本統計
        total_posts = len(results)
        successful_views = len([r for r in results if r.get('has_views')])
        successful_content = len([r for r in results if r.get('has_content')])
        successful_likes = len([r for r in results if r.get('has_likes')])
        successful_comments = len([r for r in results if r.get('has_comments')])
        
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
        
        # 下載和導出按鈕
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            self._show_json_download_button(results_file)
        
        with col2:
            if st.button("📊 導出CSV", key="export_csv"):
                self._show_csv_export_options(results_file)
        
        with col3:
            if st.button("📈 歷史分析", key="export_history"):
                self._show_export_history_options()
        
        with col4:
            if st.button("🔍 更多導出", key="more_exports"):
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
            st.write("**選擇排序方式（建議按觀看數排序）**")
            
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
            
            csv_manager = CSVExportManager()
            csv_file = csv_manager.export_current_session(json_file_path, sort_by=sort_by)
            
            # 保存CSV文件路徑到會話狀態
            st.session_state.latest_csv_file = csv_file
            
            st.success(f"✅ CSV生成成功！")
            st.info(f"📁 文件位置: {csv_file}")
            
        except Exception as e:
            st.error(f"❌ CSV生成失敗: {str(e)}")
            if 'latest_csv_file' in st.session_state:
                del st.session_state.latest_csv_file
    
    def _show_csv_download_if_available(self):
        """顯示CSV下載按鈕（如果有可用的CSV文件）"""
        if 'latest_csv_file' in st.session_state:
            csv_file = st.session_state.latest_csv_file
            if csv_file and Path(csv_file).exists():
                try:
                    with open(csv_file, 'r', encoding='utf-8-sig') as f:
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
        if 'realtime_results' not in st.session_state:
            st.error("❌ 請先執行爬取以獲取帳號信息")
            return
        
        # 獲取當前帳號
        results = st.session_state.realtime_results
        if not results:
            st.error("❌ 無法獲取帳號信息")
            return
        
        # 假設從第一個結果中提取用戶名
        target_username = None
        if 'realtime_results_file' in st.session_state:
            try:
                import json
                with open(st.session_state.realtime_results_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                target_username = data.get('target_username')
            except:
                pass
        
        if not target_username:
            st.error("❌ 無法識別目標帳號")
            return
        
        with st.expander("📈 歷史數據導出選項", expanded=True):
            export_type = st.radio(
                "選擇導出類型",
                options=["最近數據", "全部歷史", "統計分析"],
                help="選擇要導出的歷史數據範圍"
            )
            
            col1, col2 = st.columns(2)
            
            if export_type == "最近數據":
                with col1:
                    days_back = st.number_input("回溯天數", min_value=1, max_value=365, value=7)
                with col2:
                    limit = st.number_input("最大記錄數", min_value=10, max_value=10000, value=1000)
                
                if st.button("📊 導出最近數據", key="export_recent"):
                    self._export_history_data(target_username, "recent", days_back=days_back, limit=limit)
            
            elif export_type == "全部歷史":
                with col1:
                    limit = st.number_input("最大記錄數", min_value=100, max_value=50000, value=5000)
                
                if st.button("📊 導出全部歷史", key="export_all"):
                    self._export_history_data(target_username, "all", limit=limit)
            
            elif export_type == "統計分析":
                st.info("按日期統計的分析報告，包含平均觀看數、成功率等指標")
                
                if st.button("📈 導出統計分析", key="export_analysis"):
                    self._export_history_data(target_username, "analysis")
    
    def _export_history_data(self, username: str, export_type: str, **kwargs):
        """導出歷史數據"""
        try:
            from common.csv_export_manager import CSVExportManager
            import asyncio
            
            csv_manager = CSVExportManager()
            
            # 創建新的事件循環來避免衝突
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                if export_type == "recent":
                    csv_file = loop.run_until_complete(
                        csv_manager.export_database_history(
                            username, 
                            days_back=kwargs.get('days_back'),
                            limit=kwargs.get('limit')
                        )
                    )
                elif export_type == "all":
                    csv_file = loop.run_until_complete(
                        csv_manager.export_database_history(
                            username,
                            limit=kwargs.get('limit')
                        )
                    )
                elif export_type == "analysis":
                    csv_file = loop.run_until_complete(
                        csv_manager.export_combined_analysis(username)
                    )
                else:
                    raise ValueError(f"不支持的導出類型: {export_type}")
                
                st.success(f"✅ 歷史數據導出成功！")
                st.info(f"📁 文件位置: {csv_file}")
                
                # 提供下載
                import os
                if os.path.exists(csv_file):
                    with open(csv_file, 'r', encoding='utf-8-sig') as f:
                        csv_content = f.read()
                    
                    st.download_button(
                        label="📥 下載歷史CSV文件",
                        data=csv_content,
                        file_name=os.path.basename(csv_file),
                        mime="text/csv"
                    )
                
            finally:
                loop.close()
                
        except Exception as e:
            st.error(f"❌ 歷史數據導出失敗: {str(e)}")
    
    def _show_advanced_export_options(self):
        """顯示進階導出選項"""
        with st.expander("🔍 進階導出功能", expanded=True):
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
                    
                    # 顯示文件列表 - 使用 multiselect 更直觀
                    file_options = {}
                    for file in sorted(json_files, reverse=True)[:10]:  # 最新的10個
                        file_time = self._extract_time_from_filename(str(file))
                        display_name = f"{file.name} ({file_time})"
                        file_options[display_name] = str(file)
                    
                    # 初始化會話狀態
                    if "comparison_selected_files" not in st.session_state:
                        st.session_state.comparison_selected_files = []
                    
                    selected_displays = st.multiselect(
                        "選擇要比對的文件（至少2個）：",
                        options=list(file_options.keys()),
                        default=[],
                        help="選擇多個文件進行比對分析",
                        key="comparison_file_selector"
                    )
                    
                    selected_files = [file_options[display] for display in selected_displays]
                    
                    # 添加調試信息
                    if selected_displays:
                        st.text(f"🔍 調試: 當前選中 {len(selected_displays)} 個顯示項目")
                        for i, display in enumerate(selected_displays):
                            st.text(f"   {i+1}. {display}")
                    
                    if len(selected_files) >= 2:
                        st.success(f"✅ 已選擇 {len(selected_files)} 個文件進行比對")
                        
                        # 顯示選中的文件摘要
                        with st.expander("📄 選中文件摘要", expanded=True):
                            for i, file_path in enumerate(selected_files):
                                try:
                                    with open(file_path, 'r', encoding='utf-8') as f:
                                        data = json.load(f)
                                    
                                    timestamp = data.get('timestamp', 'N/A')
                                    success_count = data.get('total_processed', 0)
                                    success_rate = data.get('overall_success_rate', 0)
                                    
                                    st.markdown(f"**📁 文件 {i+1}: {Path(file_path).name}**")
                                    col1, col2, col3 = st.columns(3)
                                    with col1:
                                        st.text(f"⏰ 時間: {timestamp[:16] if timestamp != 'N/A' else 'N/A'}")
                                    with col2:
                                        st.text(f"✅ 成功: {success_count} 個")
                                    with col3:
                                        st.text(f"📊 成功率: {success_rate:.1f}%")
                                    st.divider()
                                except Exception as e:
                                    st.error(f"❌ 讀取 {Path(file_path).name} 失敗: {e}")
                        
                        if st.button("📊 生成對比報告", key="generate_comparison", type="primary"):
                            with st.spinner("正在生成對比報告..."):
                                self._generate_comparison_report(selected_files)
                    elif len(selected_files) == 1:
                        st.warning("⚠️ 已選擇1個文件，請再選擇至少1個文件進行比對")
                        st.info("💡 提示：可以按住 Ctrl 鍵點擊其他文件來多選")
                    else:
                        st.info("💡 請選擇至少2個文件進行比對分析")
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
                    df.to_csv(csv_file, index=False, encoding='utf-8-sig')
                    
                    st.success("✅ 所有帳號統計導出成功！")
                    st.info(f"📁 文件位置: {csv_file}")
                    
                    # 顯示預覽
                    st.write("**統計預覽：**")
                    st.dataframe(df, use_container_width=True)
                    
                    # 提供下載
                    csv_content = df.to_csv(index=False, encoding='utf-8-sig')
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
        valid_results = [r for r in results if r.get('has_views') and r.get('has_likes')]
        
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