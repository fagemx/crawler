#!/usr/bin/env python3
"""
社交媒體內容生成器 - Streamlit UI
拆分為多個組件，基於真實功能實現
"""

import streamlit as st
import sys
import os
import asyncio
from pathlib import Path

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

# Windows: 修正 asyncio 子行程政策，避免 Playwright 在 Windows 出現 NotImplementedError
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

# 導入組件
# from ui.components.crawler_component import ThreadsCrawlerComponent  # 舊版本
from ui.components.crawler_component_refactored import ThreadsCrawlerComponent  # 重構版本
from ui.components.realtime_crawler_component import RealtimeCrawlerComponent  # 實時爬蟲
from ui.components.playwright_crawler_component_v2 import PlaywrightCrawlerComponentV2  # Playwright 爬蟲 V2
from ui.components.monitoring_component import SystemMonitoringComponent
from ui.components.content_generator_component import ContentGeneratorComponent
from ui.components.analyzer_component import AnalyzerComponent
from ui.components.post_writer_component import PostWriterComponent

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
        self.post_writer_component = PostWriterComponent(self.analyzer_component)
        
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
            
            # 爬蟲模式說明
            st.markdown("### 📖 爬蟲模式說明")
            st.info("""
            **🚀 實時智能爬蟲**
            速度快，適合快速分析
            """)
            st.warning("""
            **🎭 Playwright 爬蟲**
            資料詳細，包含發文時間、標籤、圖片、影片 URL
            """)
            
            st.divider()
            
            # 📊 爬蟲進度
            self._render_sidebar_progress()
            
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
        """渲染主要內容（改為可控導覽，避免 rerun 時回到第一分頁）"""
        if 'main_nav' not in st.session_state:
            st.session_state.main_nav = "🚀 實時智能爬蟲"

        options = [
            "🚀 實時智能爬蟲",
            "🎭 Playwright 爬蟲",
            "📊 內容分析",
            "✍️ 智能撰寫",
            "🛠 監控面板",
            "👁️ 媒體處理器"
        ]
        current = st.session_state.get('main_nav')
        index = options.index(current) if current in options else 0
        nav = st.radio(
            "主功能選單",
            options=options,
            index=index,
            horizontal=True,
            key="main_nav"
        )

        if nav == "🚀 實時智能爬蟲":
            self.realtime_crawler_component.render()
        elif nav == "🎭 Playwright 爬蟲":
            self.playwright_crawler_component.render()
        elif nav == "📊 內容分析":
            self.analyzer_component.render()
        elif nav == "✍️ 智能撰寫":
            self.post_writer_component.render()
        elif nav == "🛠 監控面板":
            self.monitoring_component.render()
        elif nav == "👁️ 媒體處理器":
            from ui.components.media_processor_component import MediaProcessorComponent
            MediaProcessorComponent().render()

        # with tabs[4]:
        #     self.content_generator_component.render()
        # 
        # with tabs[4]:
        #     self.monitoring_component.render()
        # 
        # 舊的 Threads 爬蟲 (可選)
        # with st.expander("🕷️ 舊版 Threads 爬蟲"):
        #      self.crawler_component.render()
    
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