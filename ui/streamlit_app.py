#!/usr/bin/env python3
"""
社交媒體內容生成器 - Streamlit UI
拆分為多個組件，基於真實功能實現
"""

import streamlit as st
import sys
import os
from pathlib import Path

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

# 導入組件
from ui.components.crawler_component import ThreadsCrawlerComponent
from ui.components.monitoring_component import SystemMonitoringComponent
from ui.components.content_generator_component import ContentGeneratorComponent

# 設置頁面配置
st.set_page_config(
    page_title="社交媒體內容生成器",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)


class SocialMediaGeneratorApp:
    def __init__(self):
        self.crawler_component = ThreadsCrawlerComponent()
        self.monitoring_component = SystemMonitoringComponent()
        self.content_generator_component = ContentGeneratorComponent()
        
        # 初始化會話狀態
        self._init_session_state()
    
    def _init_session_state(self):
        """初始化會話狀態"""
        if 'current_tab' not in st.session_state:
            st.session_state.current_tab = "crawler"
    
    def render_header(self):
        """渲染頁面標題"""
        st.title("🎯 社交媒體內容生成器")
        st.markdown("**Threads 爬蟲** + **智能內容生成** + **系統監控** = 完整的內容創作解決方案")
        st.divider()
    
    def render_sidebar(self):
        """渲染側邊欄"""
        with st.sidebar:
            st.header("🎯 功能導航")
            st.markdown("選擇你要使用的功能模組")
            
            st.divider()
            
            # 功能狀態
            st.subheader("📊 功能狀態")
            
            # 爬蟲狀態
            crawler_status = st.session_state.get('crawler_status', 'idle')
            status_colors = {
                "idle": "⚪",
                "running": "🟡", 
                "completed": "🟢",
                "error": "🔴"
            }
            status_names = {
                "idle": "待機中",
                "running": "運行中",
                "completed": "已完成", 
                "error": "錯誤"
            }
            
            st.write(f"🕷️ 爬蟲: {status_colors.get(crawler_status, '⚪')} {status_names.get(crawler_status, '未知')}")
            
            if crawler_status == "completed":
                final_data = st.session_state.get('final_data')
                if final_data:
                    posts_count = len(final_data.get("posts", []))
                    st.write(f"   📊 已爬取: {posts_count} 篇")
            
            # 內容生成狀態
            content_step = st.session_state.get('content_step', 'input')
            step_names = {
                'input': '輸入需求',
                'clarification': '澄清問題',
                'result': '查看結果'
            }
            st.write(f"📝 內容生成: {step_names.get(content_step, '未知')}")
            
            # 監控狀態
            if hasattr(st.session_state, 'monitoring_results'):
                results = st.session_state.monitoring_results
                mcp_healthy = results.get('mcp_server', False)
                st.write(f"📊 系統監控: {'🟢 正常' if mcp_healthy else '🔴 異常'}")
            else:
                st.write("📊 系統監控: ⚪ 待檢查")
            
            st.divider()
            
            # 快速操作
            st.subheader("⚡ 快速操作")
            
            if st.button("🔄 重置所有狀態", use_container_width=True):
                self._reset_all_states()
                st.rerun()
            
            # 系統信息
            st.divider()
            st.subheader("🔧 系統信息")
            st.write("**核心服務:**")
            st.write("- 🤖 Orchestrator: 8000")
            st.write("- 📝 Content Writer: 8003")
            st.write("- ❓ Clarification: 8004")
            st.write("- 📋 Form API: 8010")
            
            st.write("**擴展服務:**")
            st.write("- 🕷️ Playwright: 8006")
            st.write("- 👁️ Vision: 8005")
            st.write("- 📊 MCP Server: 10100")
            
            # 使用說明
            with st.expander("📖 使用說明"):
                st.markdown("""
                **🕷️ Threads 爬蟲:**
                1. 輸入 Threads 用戶名
                2. 設置爬取數量
                3. 查看實時進度
                4. 下載 JSON 結果
                
                **📝 內容生成:**
                1. 輸入想要的貼文描述
                2. 回答澄清問題（如需要）
                3. 獲得生成的貼文內容
                
                **📊 系統監控:**
                1. 執行完整系統測試
                2. 查看服務健康狀態
                3. 監控性能指標
                4. 下載測試報告
                """)
    
    def render_main_content(self):
        """渲染主要內容"""
        # 標籤頁
        tab1, tab2, tab3 = st.tabs([
            "🕷️ Threads 爬蟲", 
            "📝 內容生成", 
            "📊 系統監控"
        ])
        
        with tab1:
            self.crawler_component.render()
        
        with tab2:
            self.content_generator_component.render()
        
        with tab3:
            self.monitoring_component.render()
    
    def _reset_all_states(self):
        """重置所有狀態"""
        # 保留的鍵
        keys_to_keep = ['current_tab']
        
        # 刪除其他所有鍵
        keys_to_delete = [key for key in st.session_state.keys() if key not in keys_to_keep]
        for key in keys_to_delete:
            del st.session_state[key]
    
    def run(self):
        """運行應用"""
        self.render_header()
        self.render_sidebar()
        self.render_main_content()


# 主程式
if __name__ == "__main__":
    app = SocialMediaGeneratorApp()
    app.run()