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
# from ui.components.crawler_component import ThreadsCrawlerComponent  # 舊版本
from ui.components.crawler_component_refactored import ThreadsCrawlerComponent  # 重構版本
from ui.components.realtime_crawler_component import RealtimeCrawlerComponent  # 實時爬蟲
from ui.components.playwright_crawler_component_v2 import PlaywrightCrawlerComponentV2  # Playwright 爬蟲 V2
from ui.components.monitoring_component import SystemMonitoringComponent
from ui.components.content_generator_component import ContentGeneratorComponent
from ui.components.analyzer_component import AnalyzerComponent

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
        self.realtime_crawler_component = RealtimeCrawlerComponent()
        self.playwright_crawler_component = PlaywrightCrawlerComponentV2()
        self.monitoring_component = SystemMonitoringComponent()
        self.content_generator_component = ContentGeneratorComponent()
        self.analyzer_component = AnalyzerComponent()
        
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
            
            # 📊 爬蟲進度
            self._render_sidebar_progress()
            
            st.divider()
            
            # 📊 功能狀態
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
            
            st.divider()
            
            # ⚡ 快速操作
            st.subheader("⚡ 快速操作")
            
            if st.button("🔄 重置所有狀態", use_container_width=True):
                self._reset_all_states()
                st.rerun()
            
            st.divider()
            
            # 🔧 系統信息
            st.subheader("🔧 系統信息")
            st.write("**擴展服務:**")
            st.write("- 🕷️ Playwright: 8006")
            st.write("- 📊 Post Analyzer: 8007")
            st.write("- 👁️ Vision: 8005")
            st.write("- 📊 MCP Server: 10100")
    
    def _render_sidebar_progress(self):
        """在側邊欄渲染簡化的進度顯示"""
        st.subheader("📊 爬蟲進度")
        
        # 簡單的狀態顯示
        crawler_status = st.session_state.get('crawler_status', 'idle')
        
        if crawler_status == 'idle':
            st.write("⚪ 待機中")
            # 顯示上次爬取結果（如果有）
            final_data = st.session_state.get('final_data')
            if final_data:
                username = final_data.get('username', 'unknown')
                posts_count = len(final_data.get('posts', []))
                st.success(f"📋 上次: @{username} ({posts_count} 篇)")
        elif crawler_status == 'running':
            st.write("🟡 爬蟲運行中...")
            progress = st.session_state.get('crawler_progress', 0)
            st.progress(max(0.0, min(1.0, progress)))
        elif crawler_status == 'completed':
            st.write("🟢 爬蟲已完成")
            final_data = st.session_state.get('final_data')
            if final_data:
                username = final_data.get('username', 'unknown')
                posts_count = len(final_data.get('posts', []))
                st.success(f"✅ @{username} ({posts_count} 篇)")
        elif crawler_status == 'error':
            st.write("🔴 爬蟲發生錯誤")
            st.error("請檢查設定後重試")
    
    def render_main_content(self):
        """渲染主要內容"""
        
        # 爬蟲模式說明
        st.markdown("### 📖 爬蟲模式說明")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.info("""
            **🚀 實時智能爬蟲**
            
            ✅ **速度快** - 快速獲取基本貼文內容  
            ✅ **效率高** - 適合大量數據爬取  
            ✅ **即時性** - 實時顯示進度  
            
            **適用場景：** 快速分析、內容概覽
            """)
        
        with col2:
            st.warning("""
            **🎭 Playwright 爬蟲**
            
            ✅ **資料詳細** - 包含完整貼文信息  
            ✅ **發文時間** - 準確的時間戳記  
            ✅ **標籤提取** - 自動識別主題標籤  
            ✅ **多媒體** - 圖片、影片 URL  
            
            **適用場景：** 深度分析、完整數據收集
            """)
        
        st.divider()
        
        # 標籤頁 (暫時隱藏部分功能)
        tab1, tab2 = st.tabs([
            "🚀 實時智能爬蟲",
            "🎭 Playwright 爬蟲"
        ])
        
        # 隱藏的分頁 (保留程式碼，需要時可以重新啟用)
        # tab3, tab4, tab5, tab6 = st.tabs([
        #     "🕷️ Threads 爬蟲", 
        #     "📊 內容分析",
        #     "📝 內容生成", 
        #     "🔧 系統監控"
        # ])
        
        with tab1:
            self.realtime_crawler_component.render()
        
        with tab2:
            self.playwright_crawler_component.render()
        
        # 隱藏的組件渲染 (保留程式碼)
        # with tab3:
        #     self.crawler_component.render()
        # 
        # with tab4:
        #     self.analyzer_component.render()
        # 
        # with tab5:
        #     self.content_generator_component.render()
        # 
        # with tab6:
        #     self.monitoring_component.render()
    
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