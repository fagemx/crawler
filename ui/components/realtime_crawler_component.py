"""
實時爬蟲組件 - 智能URL收集 + 輪迴策略提取
包含完整互動數據提取功能
"""

import streamlit as st
import asyncio
import json
import time
import threading
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
            
        with col2:
            st.subheader("📊 提取策略")
            strategy_info = st.info("""
            **🔄 輪迴策略：**
            - 10個API請求 → 20個本地Reader
            - 避免API 429阻擋
            - 自動回退機制
            
            **📈 提取數據：**
            - 觀看數、文字內容
            - 按讚、留言、轉發、分享
            """)
        
        # 控制按鈕
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            if st.button("🚀 開始爬取", key="start_realtime"):
                with st.spinner("正在執行爬取..."):
                    self._execute_crawling_simple(username, max_posts)
                
        with col2:
            if st.button("🔄 重置", key="reset_realtime"):
                self._reset_results()
        
        # 結果顯示
        self._render_results_area()
    
    def _execute_crawling_simple(self, username: str, max_posts: int):
        """簡化的爬取執行方法 - 使用同步版本避免asyncio衝突"""
        if not username.strip():
            st.error("請輸入目標帳號！")
            return
            
        try:
            st.info("🔄 正在執行爬取，請稍候...")
            
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
            
            # 執行腳本 - 設置UTF-8編碼
            import locale
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            env['PYTHONUTF8'] = '1'
            
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                encoding='utf-8',
                errors='replace',
                env=env,
                cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            )
            
            if result.returncode == 0:
                # 成功執行，尋找最新的結果文件
                import glob
                results_pattern = "realtime_extraction_results_*.json"
                results_files = glob.glob(results_pattern)
                
                if results_files:
                    # 取最新的文件
                    latest_file = max(results_files, key=os.path.getctime)
                    
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
                st.error(f"❌ 爬取失敗：{result.stderr}")
                
        except Exception as e:
            st.error(f"❌ 執行錯誤：{str(e)}")
            st.session_state.realtime_error = str(e)
    
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
        
        # 詳細結果表格
        if st.checkbox("📋 顯示詳細結果", key="show_detailed_results"):
            self._show_detailed_table(results)
        
        # 下載按鈕
        if st.button("💾 下載完整結果", key="download_results"):
            st.success(f"結果已保存到: {results_file}")
            st.json({"message": f"請查看項目根目錄下的 {results_file} 文件"})
    
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
                "來源": r.get('source', 'N/A')
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