"""
分析組件 - 重新設計
用於單篇貼文URL提取和結構分析
"""

import streamlit as st
import httpx
import requests
import json
import asyncio
import re
import pickle
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
import sys

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from scripts.realtime_crawler_extractor import RealtimeCrawlerExtractor

class AnalyzerComponent:
    def __init__(self):
        self.analyzer_url = "http://localhost:8007/analyze"
        self.structure_analyzer_url = "http://localhost:8007/structure-analyze"
        
        # 創建已測試的提取器實例（用於解析方法）
        self.extractor = RealtimeCrawlerExtractor("dummy_user", 1, False)  # 只用於解析方法
        
        # 初始化分頁系統
        self._init_tab_system()
        
        # 持久化儲存設定
        self.storage_dir = Path("temp_progress")
        self.storage_dir.mkdir(exist_ok=True)
        self.state_file = self.storage_dir / "analyzer_tabs_state.json"
        
        # 分析結果保存設定
        self.analysis_results_dir = Path("storage") / "analysis_results"
        self.analysis_results_dir.mkdir(parents=True, exist_ok=True)
        self.analysis_index_file = self.analysis_results_dir / "analysis_index.json"
        
        # 清理衝突的 widget keys
        self._cleanup_widget_conflicts()
        
        # 載入持久化狀態
        self._load_persistent_state()
        
        # JINA API 設定
        self.official_reader_url = "https://r.jina.ai"
        self.official_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'X-Return-Format': 'markdown'
        }
    
    def render(self):
        """渲染分析界面"""
        st.header("📊 貼文結構分析")
        st.markdown("**多任務分頁分析** - 同時處理多個 Threads 貼文的結構分析")
        
        # 使用新的分頁系統
        self._render_tab_system()
    
    def _render_input_section(self):
        """渲染輸入區域"""
        st.subheader("📝 輸入貼文資訊")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # 三種輸入方式
            st.markdown("**方式一：輸入用戶名 + 貼文ID**")
            col_user, col_post = st.columns(2)
            
            with col_user:
                username = st.text_input(
                    "Threads 用戶名",
                    placeholder="netflixtw",
                    help="不需要包含 @",
                    key="analyzer_username"
                )
            
            with col_post:
                post_id = st.text_input(
                    "貼文ID",
                    placeholder="DNCWbR5PeQk",
                    help="從 URL 中提取的貼文ID",
                    key="analyzer_post_id"
                )
            
            st.markdown("**方式二：直接輸入完整URL**")
            direct_url = st.text_input(
                "貼文URL",
                placeholder="https://www.threads.com/@netflixtw/post/DNCWbR5PeQk",
                key="analyzer_direct_url"
            )
        
        with col2:
            st.markdown("**示例格式：**")
            st.code("""
用戶名: netflixtw
貼文ID: DNCWbR5PeQk

或直接URL:
https://www.threads.com/@netflixtw/post/DNCWbR5PeQk
            """)
        
        # 提交按鈕
        if st.button("🔍 提取貼文內容", use_container_width=True, type="primary"):
            self._process_input(username, post_id, direct_url)
    
    def _process_input(self, username: str, post_id: str, direct_url: str):
        """處理用戶輸入並組合URL"""
        final_url = None
        
        # 驗證輸入
        if direct_url.strip():
            # 方式二：直接URL
            if self._is_valid_threads_url(direct_url.strip()):
                final_url = direct_url.strip()
            else:
                st.error("❌ 請輸入有效的 Threads URL")
                return
        elif username.strip() and post_id.strip():
            # 方式一：組合URL
            clean_username = username.strip().lstrip('@')
            clean_post_id = post_id.strip()
            final_url = f"https://www.threads.com/@{clean_username}/post/{clean_post_id}"
        else:
            st.error("❌ 請選擇一種方式：輸入用戶名+貼文ID 或 直接輸入完整URL")
            return
        
        # 開始提取
        self._extract_post_content(final_url)
    
    def _is_valid_threads_url(self, url: str) -> bool:
        """驗證是否為有效的 Threads URL"""
        pattern = r'^https://www\.threads\.com/@[\w\._]+/post/[\w-]+$'
        return bool(re.match(pattern, url))
    
    def _extract_post_content(self, url: str):
        """使用 JINA API 提取貼文內容"""
        with st.spinner("🔍 正在提取貼文內容..."):
            success, content = self._fetch_content_jina_api(url)
            
            if success:
                post_data = self._parse_post_data(url, content)
                
                if post_data:
                    # 儲存到 session state
                    st.session_state.extracted_posts = [post_data]
                    st.success("✅ 貼文內容提取成功！")
                    st.rerun()
                else:
                    st.error("❌ 無法解析貼文內容")
            else:
                st.error(f"❌ API 請求失敗：{content}")
    
    def _fetch_content_jina_api(self, url: str) -> tuple:
        """從Jina API獲取內容 - 直接使用測試過的方法"""
        return self.extractor.fetch_content_jina_api(url)
    


    def _parse_post_data(self, url: str, markdown_content: str) -> Optional[Dict[str, Any]]:
        """解析 JINA 返回的 markdown 內容 - 使用 realtime_crawler_component 的邏輯"""
        try:
            # 從 URL 提取基本資訊
            url_match = re.match(r'https://www\.threads\.com/@([\w\._]+)/post/([\w-]+)', url)
            if not url_match:
                return None
            
            username = url_match.group(1)
            post_id = url_match.group(2)
            
            # 直接使用 realtime_crawler_extractor 的所有方法
            views_count = self.extractor.extract_views_count(markdown_content, post_id)
            likes_count = self.extractor.extract_likes_count(markdown_content)
            main_content = self.extractor.extract_post_content(markdown_content)
            
            return {
                'post_id': post_id,
                'username': username,
                'url': url,
                'content': main_content,
                'views_count': views_count or '未知',
                'likes_count': likes_count or '未知',
                'comments_count': '未知',  # 暫不提取評論數
                'raw_markdown': markdown_content,
                'extracted_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"Error parsing post data: {e}")
            return None
    

    
    def _render_post_cards(self):
        """渲染貼文卡片"""
        st.subheader("📄 提取的貼文")
        
        posts = st.session_state.get('extracted_posts', [])
        if not posts:
            return
        
        # 只顯示第一篇貼文
        if posts:
            post = posts[0]
            self._render_single_post_card(post)
    
    def _render_single_post_card(self, post: Dict[str, Any]):
        """渲染單個貼文卡片"""
        # 用戶名
        st.markdown(f"**@{post['username']}**")
        
        # 完整內容顯示
        st.text(post['content'])
        
        # 互動數據
        st.caption(f"👁️ {post['views_count']} | ❤️ {post['likes_count']} | 💬 {post['comments_count']}")
        
        # 操作按鈕
        col1, col2 = st.columns(2)
        with col1:
            if st.button(f"🔗 查看原文", key=f"view_original_{post['post_id']}", use_container_width=True):
                st.markdown(f"[點此查看原文]({post['url']})")
        
        with col2:
            if st.button(f"🔍 選擇分析", key=f"select_analyze_{post['post_id']}", use_container_width=True, type="primary"):
                st.session_state.selected_post_id = post['post_id']
                st.session_state.selected_post_data = post
                st.success("✅ 已選擇此貼文進行分析")
                st.rerun()
        
        st.divider()
    
    def _render_analysis_section(self):
        """渲染分析區域"""
        st.subheader("🔬 結構分析")
        
        selected_post = st.session_state.get('selected_post_data')
        if not selected_post:
            st.error("❌ 找不到選中的貼文數據")
            return
        
        st.info(f"📝 分析貼文：@{selected_post['username']} - {selected_post['post_id']}")
        
        # 分析狀態
        analysis_status = st.session_state.get('structure_analysis_status', 'idle')
        
        if analysis_status == 'idle':
            # 開始分析按鈕
            if st.button("🚀 開始結構分析", use_container_width=True, type="primary"):
                self._start_structure_analysis(selected_post)
                
        elif analysis_status == 'running':
            self._render_analysis_progress()
            
        elif analysis_status == 'step1_completed':
            self._render_step1_results()
            
        elif analysis_status == 'completed':
            self._render_final_analysis_results()
            
        elif analysis_status == 'error':
            st.error("❌ 分析過程中發生錯誤")
            
            # 顯示錯誤日誌
            if st.session_state.get('structure_analysis_logs'):
                with st.expander("📋 錯誤日誌", expanded=True):
                    for log in st.session_state.structure_analysis_logs:
                        if "❌" in log:
                            st.error(log)
                        else:
                            st.text(log)
            
            if st.button("🔄 重新開始分析"):
                self._reset_analysis_state()
                st.rerun()
    
    def _start_structure_analysis(self, selected_post: Dict[str, Any]):
        """開始結構分析"""
        st.session_state.structure_analysis_status = 'running'
        st.session_state.structure_analysis_logs = []
        st.session_state.structure_analysis_result = None
        
        st.session_state.structure_analysis_logs.append("🚀 開始貼文結構分析...")
        
        # 執行分析
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._execute_structure_analysis(selected_post))
        except Exception as e:
            st.session_state.structure_analysis_logs.append(f"❌ 分析執行失敗: {e}")
            st.session_state.structure_analysis_status = 'error'
        finally:
            st.rerun()
    
    async def _execute_structure_analysis(self, selected_post: Dict[str, Any]):
        """執行結構分析請求"""
        try:
            # 準備請求數據
            request_data = {
                "post_content": selected_post['content'],
                "post_id": selected_post['post_id'],
                "username": selected_post['username']
            }
            
            st.session_state.structure_analysis_logs.append("📡 正在連接結構分析服務...")
            st.session_state.structure_analysis_logs.append("🤖 啟動 Gemini 2.0 Flash AI 模型...")
            st.session_state.structure_analysis_logs.append("🔍 第一階段：結構特徵分析中...")
            
            timeout = httpx.Timeout(120.0)  # 2分鐘超時
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(self.structure_analyzer_url, json=request_data)
                
                if response.status_code != 200:
                    error_msg = f"❌ 結構分析服務請求失敗，狀態碼: {response.status_code}"
                    st.session_state.structure_analysis_logs.append(error_msg)
                    st.session_state.structure_analysis_logs.append(f"錯誤內容: {response.text}")
                    st.session_state.structure_analysis_status = 'error'
                    return
                
                # 解析分析結果
                try:
                    st.session_state.structure_analysis_logs.append("📝 第二階段：深度內容分析完成")
                    st.session_state.structure_analysis_logs.append("📊 正在整理分析結果...")
                    analysis_result = response.json()
                    st.session_state.structure_analysis_result = analysis_result
                    st.session_state.structure_analysis_status = 'completed'
                    st.session_state.structure_analysis_logs.append("✅ 結構分析完成！生成了完整的改寫建議與發展方向")
                    
                except json.JSONDecodeError as e:
                    st.session_state.structure_analysis_logs.append(f"❌ 無法解析分析結果 JSON: {e}")
                    st.session_state.structure_analysis_status = 'error'
        
        except httpx.ConnectError:
            error_msg = f"連線錯誤: 無法連線至分析服務 {self.structure_analyzer_url}。請確認分析 Agent 是否正在運行。"
            st.session_state.structure_analysis_logs.append(error_msg)
            st.session_state.structure_analysis_status = 'error'
        except Exception as e:
            st.session_state.structure_analysis_logs.append(f"❌ 分析過程中發生錯誤: {e}")
            st.session_state.structure_analysis_status = 'error'
    
    def _render_analysis_progress(self):
        """渲染分析進度"""
        st.subheader("🔬 結構分析進行中")
        
        selected_post = st.session_state.get('selected_post_data', {})
        username = selected_post.get('username', '')
        post_id = selected_post.get('post_id', '')
        
        # 創建進度條容器
        progress_container = st.container()
        
        with progress_container:
            # 分析狀態指示器
            col1, col2, col3 = st.columns([1, 2, 1])
            
            with col2:
                st.markdown("""
                <div style="text-align: center; padding: 20px; border: 2px dashed #1f77b4; border-radius: 10px; background-color: #f0f8ff;">
                    <h3>🧠 AI 正在深度分析中...</h3>
                    <p style="font-size: 18px;">📝 @{username} 的貼文 (ID: {post_id})</p>
                    <div style="margin: 20px 0;">
                        <span style="font-size: 30px; animation: pulse 1.5s infinite;">🤖</span>
                        <span style="font-size: 20px; margin: 0 10px;">→</span>
                        <span style="font-size: 30px; animation: pulse 1.5s infinite 0.5s;">💭</span>
                        <span style="font-size: 20px; margin: 0 10px;">→</span>
                        <span style="font-size: 30px; animation: pulse 1.5s infinite 1s;">📊</span>
                    </div>
                    <p style="color: #666; font-style: italic;">預計需要 30-60 秒...</p>
                </div>
                <style>
                @keyframes pulse {{
                    0% {{ opacity: 0.3; transform: scale(0.8); }}
                    50% {{ opacity: 1; transform: scale(1); }}
                    100% {{ opacity: 0.3; transform: scale(0.8); }}
                }}
                </style>
                """.format(username=username, post_id=post_id[:8]), unsafe_allow_html=True)
        
        # 步驟指示器
        st.markdown("---")
        
        # 分析步驟進度
        steps = [
            ("1️⃣", "結構特徵分析", "分析句子長短、段落組織"),
            ("2️⃣", "深度內容分析", "生成改寫建議和發展方向"),
            ("3️⃣", "結果整理", "準備完整分析報告")
        ]
        
        for i, (emoji, title, desc) in enumerate(steps):
            col1, col2, col3 = st.columns([1, 4, 1])
            with col2:
                # 根據當前進度調整顏色
                if i == 0:  # 假設正在執行第一步
                    st.markdown(f"""
                    <div style="padding: 10px; border-left: 4px solid #1f77b4; background-color: #e8f4fd; margin: 5px 0;">
                        <strong>{emoji} {title}</strong> <span style="color: #1f77b4;">⏳ 進行中...</span><br>
                        <small style="color: #666;">{desc}</small>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div style="padding: 10px; border-left: 4px solid #ddd; background-color: #f9f9f9; margin: 5px 0;">
                        <strong style="color: #999;">{emoji} {title}</strong> <span style="color: #999;">⏱️ 等待中...</span><br>
                        <small style="color: #999;">{desc}</small>
                    </div>
                    """, unsafe_allow_html=True)
        
        # 顯示分析日誌（如果有的話）
        if st.session_state.get('structure_analysis_logs'):
            with st.expander("📋 詳細日誌", expanded=False):
                for log in st.session_state.structure_analysis_logs:
                    if "❌" in log:
                        st.error(log)
                    elif "✅" in log:
                        st.success(log)
                    elif "📡" in log or "🚀" in log:
                        st.info(log)
                    else:
                        st.text(log)
        
        # 取消按鈕
        st.markdown("---")
        if st.button("🛑 取消分析", type="secondary"):
            st.session_state.structure_analysis_status = 'idle'
            st.session_state.structure_analysis_logs = []
            st.success("✅ 已取消分析")
            st.rerun()
        
        # 自動刷新
        import time
        time.sleep(2)
        st.rerun()
    
    def _render_final_analysis_results(self):
        """渲染最終分析結果"""
        st.subheader("📊 結構分析結果")
        
        result = st.session_state.get('structure_analysis_result')
        if not result:
            st.error("❌ 沒有分析結果數據")
            return
        
        username = result.get('username', '')
        post_id = result.get('post_id', '')
        st.success(f"✅ @{username} 的貼文結構分析已完成 (ID: {post_id})")
        
        # 重置按鈕
        if st.button("🔄 重新分析", use_container_width=True):
            self._reset_analysis_state()
            st.rerun()
        
        # 優先顯示分析摘要
        self._render_analysis_summary_final(result)
        
        # 將結構指南放在折疊區域中
        with st.expander("📐 貼文結構指南", expanded=False):
            self._render_structure_guide_content(result)
    
    def _render_structure_guide_content(self, result: Dict[str, Any]):
        """渲染結構指南內容（用於嵌入到 expander 中）"""
        structure_guide = result.get('post_structure_guide', {})
        
        if not structure_guide:
            st.warning("⚠️ 沒有結構指南數據")
            return
        
        # 處理可能的嵌套結構
        if 'post_structure_guide' in structure_guide:
            structure_guide = structure_guide['post_structure_guide']
        
        # 顯示句子結構
        st.markdown("**📊 句子結構**")
        col1, col2 = st.columns(2)
        
        with col1:
            st.write(f"• 總句數範圍：{structure_guide.get('總句數範圍', 'N/A')}")
            st.write(f"• 平均每句字數：{structure_guide.get('平均每句字數', 'N/A')}")
            st.write(f"• 短句定義：{structure_guide.get('短句定義', 'N/A')}")
            st.write(f"• 長句定義：{structure_guide.get('長句定義', 'N/A')}")
        
        with col2:
            st.write(f"• 短句比例：{structure_guide.get('短句比例', 'N/A')}")
            st.write(f"• 長句比例：{structure_guide.get('長句比例', 'N/A')}")
            st.write(f"• 段落數量：{structure_guide.get('段落數量', 'N/A')}")
            st.write(f"• 每段句數：{structure_guide.get('每段句數', 'N/A')}")
        
        # 顯示段落類型分布
        paragraph_types = structure_guide.get('段落類型分布', [])
        if paragraph_types:
            st.markdown("**🏗️ 段落類型分布**")
            for paragraph_type in paragraph_types:
                st.write(f"• {paragraph_type}")

    
    def _render_analysis_summary_final(self, result: Dict[str, Any]):
        """渲染分析摘要 - 分區塊展示"""
        st.subheader("💡 分析摘要")
        
        analysis_summary = result.get('analysis_summary', '')
        if analysis_summary:
            # 解析並分區塊顯示
            self._parse_and_display_analysis_blocks(analysis_summary)
        else:
            st.warning("⚠️ 沒有分析摘要")
        
        # 分析時間
        analyzed_at = result.get('analyzed_at', '')
        if analyzed_at:
            st.caption(f"分析時間：{analyzed_at}")
    
    def _parse_and_display_analysis_blocks(self, analysis_summary: str):
        """直接顯示分析摘要內容"""
        
        # 直接顯示完整內容，不做任何處理
        st.markdown(analysis_summary)
    
    def _reset_analysis_state(self):
        """重置分析狀態"""
        keys_to_reset = [
            'structure_analysis_status', 'structure_analysis_logs', 
            'structure_analysis_result', 'selected_post_id', 'selected_post_data'
        ]
        for key in keys_to_reset:
            if key in st.session_state:
                del st.session_state[key]
    
    # =================== 多分頁系統 ===================
    
    def _get_widget_keys(self):
        """獲取所有可能的 widget key 後綴"""
        return [
            '_reset', '_reanalyze', '_save', '_save_analysis', '_duplicate', '_retry', 
            '_start_analysis', '_extract_url', '_extract_manual', 
            '_cancel_analysis', '_input_method', '_url_input', 
            '_username_input', '_post_id_input', 'new_tab_btn', 'close_tab_btn', 'close_all_tabs_btn'
        ]
    
    def _is_widget_key(self, key: str) -> bool:
        """檢查是否為 widget key"""
        widget_keys = self._get_widget_keys()
        
        # 檢查後綴匹配
        if any(key.endswith(widget_key) for widget_key in widget_keys):
            return True
        
        # 檢查特殊的前綴模式
        widget_prefixes = ['view_original_', 'select_analyze_']
        if any(key.startswith(prefix) for prefix in widget_prefixes):
            return True
        
        return False
    
    def _cleanup_widget_conflicts(self):
        """清理可能與 widget 衝突的 session state keys"""
        keys_to_remove = []
        for key in st.session_state.keys():
            if self._is_widget_key(key):
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            try:
                del st.session_state[key]
            except:
                pass  # 如果刪除失敗就忽略
    
    def _init_tab_system(self):
        """初始化分頁系統"""
        if 'analysis_tabs' not in st.session_state:
            st.session_state.analysis_tabs = []
        if 'active_tab_id' not in st.session_state:
            st.session_state.active_tab_id = None
        if 'tab_counter' not in st.session_state:
            st.session_state.tab_counter = 0
        if 'persistent_loaded' not in st.session_state:
            st.session_state.persistent_loaded = False
    
    def _load_persistent_state(self):
        """載入持久化狀態"""
        if st.session_state.get('persistent_loaded', False):
            return  # 已經載入過了
            
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    saved_state = json.load(f)
                
                # 載入分頁狀態
                if 'analysis_tabs' in saved_state:
                    st.session_state.analysis_tabs = saved_state['analysis_tabs']
                if 'active_tab_id' in saved_state:
                    st.session_state.active_tab_id = saved_state['active_tab_id']
                if 'tab_counter' in saved_state:
                    st.session_state.tab_counter = saved_state['tab_counter']
                
                # 載入每個分頁的詳細狀態
                for tab in st.session_state.analysis_tabs:
                    tab_id = tab['id']
                    tab_state_file = self.storage_dir / f"{tab_id}_state.json"
                    
                    if tab_state_file.exists():
                        with open(tab_state_file, 'r', encoding='utf-8') as f:
                            tab_state = json.load(f)
                        
                        # 恢復分頁的輸入狀態（跳過可能與 widget 衝突的 key）
                        for key, value in tab_state.items():
                            if key.startswith(f"{tab_id}_"):
                                # 檢查是否與 widget key 衝突
                                if not self._is_widget_key(key):
                                    st.session_state[key] = value
                
                if st.session_state.analysis_tabs:
                    st.success(f"✅ 已恢復 {len(st.session_state.analysis_tabs)} 個分析任務")
                else:
                    st.info("📝 沒有找到之前的分析任務")
                
        except Exception as e:
            st.warning(f"⚠️ 載入狀態時發生錯誤: {e}")
        
        st.session_state.persistent_loaded = True
    
    def _save_persistent_state(self):
        """保存持久化狀態"""
        try:
            # 保存主要分頁狀態
            main_state = {
                'analysis_tabs': st.session_state.get('analysis_tabs', []),
                'active_tab_id': st.session_state.get('active_tab_id'),
                'tab_counter': st.session_state.get('tab_counter', 0),
                'saved_at': datetime.now().isoformat()
            }
            
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(main_state, f, ensure_ascii=False, indent=2)
            
            # 保存每個分頁的詳細狀態
            for tab in st.session_state.analysis_tabs:
                tab_id = tab['id']
                tab_state = {}
                
                # 收集此分頁相關的所有 session state（跳過 widget keys）
                for key in st.session_state.keys():
                    if key.startswith(f"{tab_id}_"):
                        # 檢查是否與 widget key 衝突
                        if not self._is_widget_key(key):
                            value = st.session_state[key]
                            # 只保存可序列化的值
                            if isinstance(value, (str, int, float, bool, list, dict)):
                                tab_state[key] = value
                
                # 保存分頁狀態到獨立文件
                tab_state_file = self.storage_dir / f"{tab_id}_state.json"
                with open(tab_state_file, 'w', encoding='utf-8') as f:
                    json.dump(tab_state, f, ensure_ascii=False, indent=2)
            
        except Exception as e:
            st.error(f"❌ 保存狀態失敗: {e}")
    
    def _clear_persistent_state(self):
        """清理持久化狀態"""
        try:
            # 刪除主狀態文件
            if self.state_file.exists():
                self.state_file.unlink()
            
            # 刪除所有分頁狀態文件
            for state_file in self.storage_dir.glob("tab_*_state.json"):
                state_file.unlink()
                
            st.success("✅ 已清理所有持久化狀態")
            
        except Exception as e:
            st.error(f"❌ 清理狀態失敗: {e}")
    
    # =================== 分析結果保存系統 ===================
    
    def _load_analysis_index(self) -> Dict[str, Any]:
        """載入分析結果索引"""
        try:
            if self.analysis_index_file.exists():
                with open(self.analysis_index_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {"analyses": []}
        except Exception as e:
            st.error(f"❌ 載入分析索引失敗: {e}")
            return {"analyses": []}
    
    def _save_analysis_index(self, index_data: Dict[str, Any]):
        """保存分析結果索引"""
        try:
            with open(self.analysis_index_file, 'w', encoding='utf-8') as f:
                json.dump(index_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            st.error(f"❌ 保存分析索引失敗: {e}")
    
    def _save_analysis_result(self, tab: Dict[str, Any], custom_name: str = None) -> str:
        """保存分析結果並返回 analysis_id"""
        try:
            post_data = tab.get('post_data', {})
            analysis_result = tab.get('analysis_result', {})
            
            if not post_data or not analysis_result:
                return None
            
            # 生成唯一的分析ID
            import uuid
            analysis_id = str(uuid.uuid4())[:8]
            
            # 創建分析結果數據
            analysis_data = {
                "analysis_id": analysis_id,
                "created_at": datetime.now().isoformat(),
                "tab_info": {
                    "tab_id": tab['id'],
                    "tab_title": tab['title'],
                    "status": tab['status']
                },
                "post_content": {
                    "username": post_data.get('username', ''),
                    "post_id": post_data.get('post_id', ''),
                    "url": post_data.get('url', ''),
                    "content": post_data.get('content', ''),
                    "views_count": post_data.get('views_count', ''),
                    "likes_count": post_data.get('likes_count', ''),
                    "comments_count": post_data.get('comments_count', '')
                },
                "analysis_stage1": {
                    "post_structure_guide": analysis_result.get('post_structure_guide', {}),
                    "analysis_elements": analysis_result.get('analysis_elements', {})
                },
                "analysis_stage2": {
                    "analysis_summary": analysis_result.get('analysis_summary', ''),
                    "analyzed_at": analysis_result.get('analyzed_at', '')
                }
            }
            
            # 保存到單獨的分析結果文件
            analysis_file = self.analysis_results_dir / f"analysis_{analysis_id}.json"
            with open(analysis_file, 'w', encoding='utf-8') as f:
                json.dump(analysis_data, f, ensure_ascii=False, indent=2)
            
            # 更新索引
            index_data = self._load_analysis_index()
            
            # 生成顯示名稱
            if custom_name:
                display_name = custom_name
            else:
                username = post_data.get('username', 'unknown')
                post_id_short = post_data.get('post_id', 'unknown')[:8]
                display_name = f"@{username}_{post_id_short}"
            
            index_entry = {
                "analysis_id": analysis_id,
                "display_name": display_name,
                "username": post_data.get('username', ''),
                "post_id": post_data.get('post_id', ''),
                "created_at": datetime.now().isoformat(),
                "file_path": f"analysis_{analysis_id}.json"
            }
            
            index_data["analyses"].append(index_entry)
            self._save_analysis_index(index_data)
            
            return analysis_id
            
        except Exception as e:
            st.error(f"❌ 保存分析結果失敗: {e}")
            return None
    
    def _get_saved_analyses(self) -> List[Dict[str, Any]]:
        """獲取所有已保存的分析結果列表"""
        index_data = self._load_analysis_index()
        return index_data.get("analyses", [])
    
    def _load_analysis_result(self, analysis_id: str) -> Dict[str, Any]:
        """載入指定的分析結果"""
        try:
            analysis_file = self.analysis_results_dir / f"analysis_{analysis_id}.json"
            if analysis_file.exists():
                with open(analysis_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return None
        except Exception as e:
            st.error(f"❌ 載入分析結果失敗: {e}")
            return None
    
    def _delete_analysis_result(self, analysis_id: str):
        """刪除分析結果"""
        try:
            # 刪除分析文件
            analysis_file = self.analysis_results_dir / f"analysis_{analysis_id}.json"
            if analysis_file.exists():
                analysis_file.unlink()
            
            # 更新索引
            index_data = self._load_analysis_index()
            index_data["analyses"] = [
                a for a in index_data["analyses"] 
                if a["analysis_id"] != analysis_id
            ]
            self._save_analysis_index(index_data)
            
        except Exception as e:
            st.error(f"❌ 刪除分析結果失敗: {e}")
    
    def get_saved_analysis_options(self) -> List[Dict[str, str]]:
        """獲取已保存的分析結果選項（供其他組件使用）"""
        analyses = self._get_saved_analyses()
        options = []
        for analysis in analyses:
            options.append({
                "label": analysis["display_name"],
                "analysis_id": analysis["analysis_id"],
                "created_at": analysis["created_at"]
            })
        return options
    
    def get_analysis_content_for_llm(self, analysis_id: str) -> Dict[str, Any]:
        """獲取分析內容用於 LLM 引用（供其他組件使用）"""
        analysis_data = self._load_analysis_result(analysis_id)
        if not analysis_data:
            return None
        
        return {
            "original_post": analysis_data["post_content"],
            "structure_guide": analysis_data["analysis_stage1"],
            "analysis_summary": analysis_data["analysis_stage2"],
            "analysis_id": analysis_id
        }
    
    def _create_new_tab(self, title: str = None) -> str:
        """創建新分頁"""
        st.session_state.tab_counter += 1
        tab_id = f"tab_{st.session_state.tab_counter}"
        
        if not title:
            title = f"分析任務 {st.session_state.tab_counter}"
        
        new_tab = {
            'id': tab_id,
            'title': title,
            'created_at': datetime.now().strftime("%H:%M:%S"),
            'status': 'idle',  # idle, extracting, analyzing, completed, error
            'post_data': None,
            'analysis_result': None
        }
        
        st.session_state.analysis_tabs.append(new_tab)
        st.session_state.active_tab_id = tab_id
        
        # 自動保存狀態
        self._save_persistent_state()
        
        return tab_id
    
    def _close_tab(self, tab_id: str):
        """關閉分頁"""
        # 移除分頁
        st.session_state.analysis_tabs = [tab for tab in st.session_state.analysis_tabs if tab['id'] != tab_id]
        
        # 如果關閉的是活動分頁，切換到其他分頁
        if st.session_state.active_tab_id == tab_id:
            if st.session_state.analysis_tabs:
                st.session_state.active_tab_id = st.session_state.analysis_tabs[-1]['id']
            else:
                st.session_state.active_tab_id = None
                
        # 清理相關的 session state（跳過 widget keys）
        keys_to_clean = []
        for key in st.session_state.keys():
            if key.startswith(f'{tab_id}_'):
                # 檢查是否與 widget key 衝突
                if not self._is_widget_key(key):
                    keys_to_clean.append(key)
        for key in keys_to_clean:
            del st.session_state[key]
        
        # 刪除分頁的持久化文件
        tab_state_file = self.storage_dir / f"{tab_id}_state.json"
        if tab_state_file.exists():
            tab_state_file.unlink()
        
        # 自動保存狀態
        self._save_persistent_state()
    
    def _get_active_tab(self) -> Dict[str, Any]:
        """獲取當前活動分頁"""
        if not st.session_state.active_tab_id:
            return None
        
        for tab in st.session_state.analysis_tabs:
            if tab['id'] == st.session_state.active_tab_id:
                return tab
        return None
    
    def _update_tab_status(self, tab_id: str, status: str, **kwargs):
        """更新分頁狀態"""
        for tab in st.session_state.analysis_tabs:
            if tab['id'] == tab_id:
                tab['status'] = status
                for key, value in kwargs.items():
                    tab[key] = value
                break
        
        # 自動保存狀態
        self._save_persistent_state()
    
    def _render_tab_system(self):
        """渲染分頁系統"""
        # 分頁標籤欄
        tab_container = st.container()
        
        with tab_container:
            # 標籤欄樣式
            st.markdown("""
            <style>
            .tab-container {
                display: flex;
                background-color: #f0f2f6;
                border-radius: 10px 10px 0 0;
                padding: 5px;
                margin-bottom: 0;
                border-bottom: 2px solid #e0e0e0;
            }
            .tab-item {
                padding: 8px 12px;
                margin: 2px;
                border-radius: 8px;
                background-color: #ffffff;
                border: 1px solid #d0d0d0;
                cursor: pointer;
                transition: all 0.3s;
            }
            .tab-item.active {
                background-color: #1f77b4;
                color: white;
                border-color: #1f77b4;
            }
            .tab-item:hover {
                background-color: #e8f4fd;
            }
            .tab-item.active:hover {
                background-color: #1565c0;
            }
            .new-tab-btn {
                padding: 8px 12px;
                margin: 2px;
                border-radius: 8px;
                background-color: #4caf50;
                color: white;
                border: 1px solid #4caf50;
                cursor: pointer;
                font-weight: bold;
            }
            .new-tab-btn:hover {
                background-color: #45a049;
            }
            </style>
            """, unsafe_allow_html=True)
            
            # 分頁標籤欄
            cols = st.columns([0.1] + [0.15] * len(st.session_state.analysis_tabs) + [0.1, 0.1])
            
            # 新增分頁按鈕
            with cols[0]:
                if st.button("➕ 新分頁", key="new_tab_btn", help="創建新的分析任務"):
                    self._create_new_tab()
                    st.rerun()
            
            # 現有分頁標籤
            for i, tab in enumerate(st.session_state.analysis_tabs):
                with cols[i + 1]:
                    # 分頁狀態圖標
                    status_icons = {
                        'idle': '⚪',
                        'extracting': '🔍',
                        'analyzing': '🧠', 
                        'completed': '✅',
                        'error': '❌'
                    }
                    
                    status_icon = status_icons.get(tab['status'], '⚪')
                    is_active = tab['id'] == st.session_state.active_tab_id
                    
                    # 分頁按鈕
                    tab_label = f"{status_icon} {tab['title'][:10]}..."
                    if st.button(
                        tab_label, 
                        key=f"tab_btn_{tab['id']}", 
                        help=f"切換到 {tab['title']} ({tab['created_at']})",
                        type="primary" if is_active else "secondary"
                    ):
                        st.session_state.active_tab_id = tab['id']
                        st.rerun()
            
            # 關閉分頁按鈕（只在有分頁時顯示）
            if st.session_state.analysis_tabs:
                with cols[-2]:
                    if st.button("🗑️", key="close_tab_btn", help="關閉當前分頁"):
                        if st.session_state.active_tab_id:
                            self._close_tab(st.session_state.active_tab_id)
                            st.rerun()
                
                # 關閉所有分頁按鈕
                with cols[-1]:
                    if st.button("🗑️📑", key="close_all_tabs_btn", help="關閉所有分頁"):
                        st.session_state.analysis_tabs = []
                        st.session_state.active_tab_id = None
                        self._clear_persistent_state()
                        st.rerun()
        
        # 如果沒有分頁，創建第一個
        if not st.session_state.analysis_tabs:
            self._create_new_tab("分析任務 1")
            st.rerun()
        
        # 分頁內容區域
        active_tab = self._get_active_tab()
        if active_tab:
            self._render_tab_content(active_tab)
    
    def _render_tab_content(self, tab: Dict[str, Any]):
        """渲染分頁內容"""
        # 分頁信息
        st.markdown(f"""
        <div style="background-color: #f8f9fa; padding: 10px; border-radius: 5px; margin-bottom: 15px;">
            <strong>📋 {tab['title']}</strong> 
            <span style="color: #666; font-size: 0.9em;">
                | 創建時間: {tab['created_at']} 
                | 狀態: {tab['status']}
                {f"| 貼文: @{tab['post_data']['username']}" if tab.get('post_data') else ""}
            </span>
        </div>
        """, unsafe_allow_html=True)
        
        # 根據分頁狀態渲染不同內容
        if tab['status'] == 'idle':
            if tab.get('post_data'):
                # 有貼文數據時顯示貼文和分析按鈕
                self._render_tab_results(tab)
            else:
                # 沒有貼文數據時顯示輸入區域
                self._render_tab_input_section(tab)
        elif tab['status'] == 'extracting':
            self._render_tab_extracting_status(tab)
        elif tab['status'] == 'analyzing':
            self._render_tab_analyzing_status(tab)
        elif tab['status'] == 'completed':
            self._render_tab_completed_results(tab)
        elif tab['status'] == 'error':
            self._render_tab_error(tab)
        
        # 分頁控制面板
        self._render_tab_control_panel(tab)
    
    def _render_tab_input_section(self, tab: Dict[str, Any]):
        """渲染分頁輸入區域"""
        st.subheader("🔗 輸入 Threads 貼文資訊")
        
        # 使用分頁特定的 key
        tab_id = tab['id']
        
        # 輸入方式選擇
        input_method = st.radio(
            "選擇輸入方式：",
            ["🔗 完整 URL", "👤 用戶名 + 貼文ID"],
            key=f"{tab_id}_input_method"
        )
        
        if input_method == "🔗 完整 URL":
            url = st.text_input(
                "Threads 貼文 URL",
                placeholder="https://www.threads.net/@username/post/post_id",
                key=f"{tab_id}_url_input"
            )
            
            if st.button(f"🔍 提取貼文內容", key=f"{tab_id}_extract_url", type="primary"):
                if url:
                    # 自動保存輸入狀態
                    self._save_persistent_state()
                    self._extract_post_from_url(tab, url)
                else:
                    st.error("請輸入有效的 URL")
        
        else:  # 用戶名 + 貼文ID
            col1, col2 = st.columns(2)
            with col1:
                username = st.text_input(
                    "用戶名 (不含 @)",
                    placeholder="例：natgeo",
                    key=f"{tab_id}_username_input"
                )
            with col2:
                post_id = st.text_input(
                    "貼文 ID",
                    placeholder="例：C-123abc...",
                    key=f"{tab_id}_post_id_input"
                )
            
            if st.button(f"🔍 提取貼文內容", key=f"{tab_id}_extract_manual", type="primary"):
                if username and post_id:
                    # 自動保存輸入狀態
                    self._save_persistent_state()
                    url = f"https://www.threads.net/@{username}/post/{post_id}"
                    self._extract_post_from_url(tab, url)
                else:
                    st.error("請輸入用戶名和貼文ID")
    
    def _extract_post_from_url(self, tab: Dict[str, Any], url: str):
        """從URL提取貼文內容"""
        self._update_tab_status(tab['id'], 'extracting')
        
        try:
            # 執行提取
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            post_data = loop.run_until_complete(self._fetch_post_content(url))
            
            if post_data:
                # 更新分頁標題
                username = post_data.get('username', 'unknown')
                new_title = f"@{username}"
                tab['title'] = new_title
                
                self._update_tab_status(tab['id'], 'idle', post_data=post_data)
            else:
                self._update_tab_status(tab['id'], 'error')
        except Exception as e:
            st.error(f"提取失敗: {e}")
            self._update_tab_status(tab['id'], 'error')
        
        st.rerun()
    
    async def _fetch_post_content(self, url: str) -> Dict[str, Any]:
        """提取貼文內容（重用現有邏輯）"""
        try:
            # 使用 JINA API 提取
            full_url = f"{self.official_reader_url}/{url}"
            
            async with httpx.AsyncClient() as client:
                response = await client.get(full_url, headers=self.official_headers, timeout=30.0)
                
                if response.status_code != 200:
                    return None
                
                markdown_content = response.text
                
                # 解析貼文數據
                post_data = self._parse_post_data(url, markdown_content)
                return post_data
                
        except Exception as e:
            st.error(f"提取失敗: {e}")
            return None
    
    def _render_tab_extracting_status(self, tab: Dict[str, Any]):
        """渲染提取狀態"""
        st.info("🔍 正在提取貼文內容...")
        st.spinner("請稍候...")
    
    def _render_tab_analyzing_status(self, tab: Dict[str, Any]):
        """渲染分析狀態"""
        st.subheader("🔬 結構分析進行中")
        
        post_data = tab.get('post_data', {})
        username = post_data.get('username', '')
        post_id = post_data.get('post_id', '')
        
        # 創建進度條容器
        progress_container = st.container()
        
        with progress_container:
            # 分析狀態指示器
            col1, col2, col3 = st.columns([1, 2, 1])
            
            with col2:
                st.markdown(f"""
                <div style="text-align: center; padding: 20px; border: 2px dashed #1f77b4; border-radius: 10px; background-color: #f0f8ff;">
                    <h3>🧠 AI 正在深度分析中...</h3>
                    <p style="font-size: 18px;">📝 @{username} 的貼文 (ID: {post_id[:8]}...)</p>
                    <div style="margin: 20px 0;">
                        <span style="font-size: 30px; animation: pulse 1.5s infinite;">🤖</span>
                        <span style="font-size: 20px; margin: 0 10px;">→</span>
                        <span style="font-size: 30px; animation: pulse 1.5s infinite 0.5s;">💭</span>
                        <span style="font-size: 20px; margin: 0 10px;">→</span>
                        <span style="font-size: 30px; animation: pulse 1.5s infinite 1s;">📊</span>
                    </div>
                    <p style="color: #666; font-style: italic;">預計需要 30-60 秒...</p>
                </div>
                <style>
                @keyframes pulse {{
                    0% {{ opacity: 0.3; transform: scale(0.8); }}
                    50% {{ opacity: 1; transform: scale(1); }}
                    100% {{ opacity: 0.3; transform: scale(0.8); }}
                }}
                </style>
                """, unsafe_allow_html=True)
        
        # 步驟指示器
        st.markdown("---")
        
        # 分析步驟進度
        steps = [
            ("1️⃣", "結構特徵分析", "分析句子長短、段落組織"),
            ("2️⃣", "深度內容分析", "生成改寫建議和發展方向"),
            ("3️⃣", "結果整理", "準備完整分析報告")
        ]
        
        for i, (emoji, title, desc) in enumerate(steps):
            col1, col2, col3 = st.columns([1, 4, 1])
            with col2:
                # 假設正在執行第一步
                if i == 0:
                    st.markdown(f"""
                    <div style="padding: 10px; border-left: 4px solid #1f77b4; background-color: #e8f4fd; margin: 5px 0;">
                        <strong>{emoji} {title}</strong> <span style="color: #1f77b4;">⏳ 進行中...</span><br>
                        <small style="color: #666;">{desc}</small>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div style="padding: 10px; border-left: 4px solid #ddd; background-color: #f9f9f9; margin: 5px 0;">
                        <strong style="color: #999;">{emoji} {title}</strong> <span style="color: #999;">⏱️ 等待中...</span><br>
                        <small style="color: #999;">{desc}</small>
                    </div>
                    """, unsafe_allow_html=True)
        
        # 取消按鈕
        st.markdown("---")
        if st.button("🛑 取消分析", key=f"{tab['id']}_cancel_analysis", type="secondary"):
            self._update_tab_status(tab['id'], 'idle', analysis_result=None)
            st.success("✅ 已取消分析")
            st.rerun()
        
        # 自動刷新
        import time
        time.sleep(2)
        st.rerun()
    
    def _render_tab_results(self, tab: Dict[str, Any]):
        """渲染分頁結果（僅提取階段）"""
        if tab.get('post_data'):
            # 顯示貼文卡片
            st.subheader("📄 提取的貼文")
            self._render_single_post_card(tab['post_data'])
            
            # 開始分析按鈕
            if st.button(f"🚀 開始結構分析", key=f"{tab['id']}_start_analysis", type="primary", use_container_width=True):
                self._start_tab_analysis(tab)
    
    def _render_tab_completed_results(self, tab: Dict[str, Any]):
        """渲染已完成的分析結果"""
        # 顯示貼文卡片
        if tab.get('post_data'):
            st.subheader("📄 分析的貼文")
            self._render_single_post_card(tab['post_data'])
            st.markdown("---")
        
        # 顯示完整分析結果
        if tab.get('analysis_result'):
            self._render_tab_analysis_results(tab)
        else:
            st.error("❌ 沒有找到分析結果")
    
    def _render_tab_error(self, tab: Dict[str, Any]):
        """渲染錯誤狀態"""
        st.error("❌ 處理過程中發生錯誤")
        if st.button(f"🔄 重試", key=f"{tab['id']}_retry"):
            self._update_tab_status(tab['id'], 'idle')
            st.rerun()
    
    def _start_tab_analysis(self, tab: Dict[str, Any]):
        """開始分頁分析"""
        self._update_tab_status(tab['id'], 'analyzing')
        
        # 執行完整的兩階段分析
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self._execute_tab_structure_analysis(tab))
            
            if result:
                self._update_tab_status(tab['id'], 'completed', analysis_result=result)
                st.success("✅ 結構分析完成！")
            else:
                self._update_tab_status(tab['id'], 'error')
                st.error("❌ 分析失敗")
        except Exception as e:
            self._update_tab_status(tab['id'], 'error')
            st.error(f"❌ 分析過程中發生錯誤: {e}")
        
        st.rerun()
    
    async def _execute_tab_structure_analysis(self, tab: Dict[str, Any]) -> Dict[str, Any]:
        """執行分頁的結構分析請求"""
        try:
            post_data = tab.get('post_data')
            if not post_data:
                return None
            
            # 準備請求數據
            request_data = {
                "post_content": post_data['content'],
                "post_id": post_data['post_id'],
                "username": post_data['username']
            }
            
            # 調用後端分析 API
            timeout = httpx.Timeout(120.0)  # 2分鐘超時
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(self.structure_analyzer_url, json=request_data)
                
                if response.status_code != 200:
                    st.error(f"❌ 結構分析服務請求失敗，狀態碼: {response.status_code}")
                    return None
                
                # 解析分析結果
                try:
                    analysis_result = response.json()
                    return analysis_result
                    
                except json.JSONDecodeError as e:
                    st.error(f"❌ 無法解析分析結果 JSON: {e}")
                    return None
                    
        except Exception as e:
            st.error(f"❌ 分析請求執行失敗: {e}")
            return None
    
    def _render_tab_analysis_results(self, tab: Dict[str, Any]):
        """渲染分頁分析結果"""
        result = tab.get('analysis_result')
        if not result:
            st.error("❌ 沒有分析結果數據")
            return
        
        # 顯示分析完成信息
        post_data = tab.get('post_data', {})
        username = post_data.get('username', '')
        post_id = post_data.get('post_id', '')
        analyzed_at = result.get('analyzed_at', '')
        
        st.success(f"✅ @{username} 的貼文結構分析已完成 (ID: {post_id[:8]}...)")
        if analyzed_at:
            st.caption(f"分析時間：{analyzed_at}")
        
        # 優先顯示分析摘要
        analysis_summary = result.get('analysis_summary', '')
        if analysis_summary:
            st.subheader("💡 分析摘要")
            # 直接顯示完整內容，不做任何處理
            st.markdown(analysis_summary)
        
        # 將結構指南放在折疊區域中
        with st.expander("📐 貼文結構指南", expanded=False):
            self._render_tab_structure_guide_content(result)
    
    def _render_tab_structure_guide_content(self, result: Dict[str, Any]):
        """渲染分頁的結構指南內容"""
        structure_guide = result.get('post_structure_guide', {})
        
        if not structure_guide:
            st.warning("⚠️ 沒有結構指南數據")
            return
        
        # 處理可能的嵌套結構
        if 'post_structure_guide' in structure_guide:
            structure_guide = structure_guide['post_structure_guide']
        
        # 顯示句子結構
        st.markdown("**📊 句子結構**")
        col1, col2 = st.columns(2)
        
        with col1:
            st.write(f"• 總句數範圍：{structure_guide.get('總句數範圍', 'N/A')}")
            st.write(f"• 平均每句字數：{structure_guide.get('平均每句字數', 'N/A')}")
            st.write(f"• 短句定義：{structure_guide.get('短句定義', 'N/A')}")
            st.write(f"• 長句定義：{structure_guide.get('長句定義', 'N/A')}")
                    
        with col2:
            st.write(f"• 短句比例：{structure_guide.get('短句比例', 'N/A')}")
            st.write(f"• 長句比例：{structure_guide.get('長句比例', 'N/A')}")
            st.write(f"• 段落數量：{structure_guide.get('段落數量', 'N/A')}")
            st.write(f"• 每段句數：{structure_guide.get('每段句數', 'N/A')}")
        
        # 顯示段落類型分布
        paragraph_types = structure_guide.get('段落類型分布', [])
        if paragraph_types:
            st.markdown("**🏗️ 段落類型分布**")
            for paragraph_type in paragraph_types:
                st.write(f"• {paragraph_type}")
    
    def _render_tab_control_panel(self, tab: Dict[str, Any]):
        """渲染分頁控制面板"""
        st.markdown("---")
        
        with st.expander("⚙️ 分頁控制", expanded=False):
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                if st.button("🔄 重置此分頁", key=f"{tab['id']}_reset", help="清空此分頁的所有數據，回到初始狀態"):
                    self._reset_tab(tab['id'])
                    st.success("✅ 分頁已重置")
                    st.rerun()
            
            with col2:
                if st.button("🔄 重新分析", key=f"{tab['id']}_reanalyze", help="保留貼文內容，重新開始分析"):
                    if tab.get('post_data'):
                        self._update_tab_status(tab['id'], 'idle', analysis_result=None)
                        st.success("✅ 可以重新分析")
                        st.rerun()
                    else:
                        st.warning("⚠️ 沒有貼文數據可重新分析")
            
            with col3:
                if st.button("💾 保存分析", key=f"{tab['id']}_save_analysis", help="保存分析結果供貼文撰寫使用"):
                    if tab.get('analysis_result') and tab.get('post_data'):
                        analysis_id = self._save_analysis_result(tab)
                        if analysis_id:
                            post_data = tab.get('post_data', {})
                            username = post_data.get('username', 'unknown')
                            st.success(f"✅ 已保存分析結果: @{username}_{analysis_id}")
                        else:
                            st.error("❌ 保存失敗")
                    else:
                        st.warning("⚠️ 沒有完整的分析結果可保存")
            
            with col4:
                if st.button("📋 複製分頁", key=f"{tab['id']}_duplicate", help="複製當前分頁到新分頁"):
                    self._duplicate_tab(tab)
                    st.success("✅ 分頁已複製")
                    st.rerun()
            
            # 分頁信息
            st.markdown("**🔍 分頁詳細信息：**")
            
            info_col1, info_col2 = st.columns(2)
            with info_col1:
                st.write(f"📋 分頁ID: `{tab['id']}`")
                st.write(f"⏰ 創建時間: `{tab['created_at']}`")
                st.write(f"🏷️ 狀態: `{tab['status']}`")
            
            with info_col2:
                if tab.get('post_data'):
                    post_data = tab['post_data']
                    st.write(f"👤 用戶: `@{post_data.get('username', 'N/A')}`")
                    st.write(f"🔗 貼文ID: `{post_data.get('post_id', 'N/A')[:10]}...`")
                    st.write(f"👁️ 瀏覽數: `{post_data.get('views_count', 'N/A')}`")
                else:
                    st.write("📄 尚無貼文數據")
            
            # 持久化狀態信息
            st.markdown("**💾 持久化狀態：**")
            tab_state_file = self.storage_dir / f"{tab['id']}_state.json"
            if tab_state_file.exists():
                file_size = tab_state_file.stat().st_size
                modified_time = datetime.fromtimestamp(tab_state_file.stat().st_mtime).strftime("%H:%M:%S")
                st.write(f"✅ 已保存 ({file_size} bytes, 更新於 {modified_time})")
            else:
                st.write("❌ 尚未保存")
    
    def _reset_tab(self, tab_id: str):
        """重置分頁"""
        # 清理分頁相關的 session state（跳過 widget keys）
        keys_to_clean = []
        for key in st.session_state.keys():
            if key.startswith(f'{tab_id}_'):
                # 檢查是否與 widget key 衝突
                if not self._is_widget_key(key):
                    keys_to_clean.append(key)
        for key in keys_to_clean:
                del st.session_state[key]
        
        # 重置分頁狀態
        for tab in st.session_state.analysis_tabs:
            if tab['id'] == tab_id:
                tab['status'] = 'idle'
                tab['post_data'] = None
                tab['analysis_result'] = None
                break
        
        # 刪除持久化文件
        tab_state_file = self.storage_dir / f"{tab_id}_state.json"
        if tab_state_file.exists():
            tab_state_file.unlink()
        
        # 保存狀態
        self._save_persistent_state()
    
    def _duplicate_tab(self, source_tab: Dict[str, Any]):
        """複製分頁"""
        # 創建新分頁
        new_tab_id = self._create_new_tab(f"{source_tab['title']} (副本)")
        
        # 複製源分頁的數據
        if source_tab.get('post_data'):
            self._update_tab_status(new_tab_id, source_tab['status'], 
                                  post_data=source_tab['post_data'],
                                  analysis_result=source_tab.get('analysis_result'))
        
        # 複製輸入狀態
        for key in st.session_state.keys():
            if key.startswith(f"{source_tab['id']}_"):
                new_key = key.replace(f"{source_tab['id']}_", f"{new_tab_id}_")
                st.session_state[new_key] = st.session_state[key]