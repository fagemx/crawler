"""
貼文撰寫組件
基於分析結果進行智能貼文創作
"""

import streamlit as st
import httpx
import json
import asyncio
from datetime import datetime, timezone, timedelta
import time
from typing import List, Dict, Any, Optional
from pathlib import Path
import sys

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

class PostWriterComponent:
    def __init__(self, analyzer_component):
        """
        初始化貼文撰寫組件
        analyzer_component: 分析組件實例，用於獲取已保存的分析結果
        """
        self.analyzer_component = analyzer_component
        self.content_generator_url = "http://localhost:8008/generate-content"
        
        # 持久化狀態設定
        self.storage_dir = Path("storage") / "writer_projects"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.projects_state_file = self.storage_dir / "writer_projects_state.json"
        
        # 初始化撰寫工作區
        self._init_writer_workspace()
        
        # 載入持久化狀態
        self._load_writer_persistent_state()

    def _cleanup_deleted_reference_ids(self, deleted_ids: List[str]):
        """清理所有專案中已被刪除的參考分析引用"""
        try:
            projects = st.session_state.get('writer_projects', [])
            for p in projects:
                if p.get('reference_analysis_id') in deleted_ids:
                    p['reference_analysis_id'] = None
                    p['reference_analysis'] = None
        except Exception:
            pass
    
    def _init_writer_workspace(self):
        """初始化撰寫工作區"""
        if 'writer_projects' not in st.session_state:
            st.session_state.writer_projects = []
        if 'active_project_id' not in st.session_state:
            st.session_state.active_project_id = None
        if 'project_counter' not in st.session_state:
            st.session_state.project_counter = 0
    
    def render(self):
        """渲染撰寫界面"""
        st.header("✍️ 智能貼文撰寫")
        st.markdown("**基於分析結果的智能內容創作** - 選擇已分析的貼文作為參考，創作新內容")
        
        # 主要撰寫工作區
        self._render_writer_workspace()
    
    def _render_writer_workspace(self):
        """渲染撰寫工作區"""
        # 檢查是否有可用的分析結果
        saved_analyses = self.analyzer_component.get_saved_analysis_options()
        
        if not saved_analyses:
            self._render_no_analysis_state()
            return
        
        # 創建新專案或選擇現有專案
        self._render_project_management()
        
        # 如果有活動專案，顯示撰寫界面
        if st.session_state.active_project_id:
            self._render_writing_interface()
    
    def _render_no_analysis_state(self):
        """渲染沒有分析結果的狀態"""
        st.info("🔍 尚未找到已保存的分析結果")
        
        with st.container():
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.markdown("""
                <div style="text-align: center; padding: 40px; border: 2px dashed #ccc; border-radius: 10px; background-color: #f9f9f9;">
                    <h3>📊 需要先進行貼文分析</h3>
                    <p style="color: #666; margin: 20px 0;">
                        要使用智能撰寫功能，請先到 <strong>📊 內容分析</strong> 頁面分析一些貼文，
                        然後使用 <strong>💾 保存分析</strong> 功能保存分析結果。
                    </p>
                    <p style="color: #888; font-size: 0.9em;">
                        💡 提示：分析結果會成為撰寫新內容的參考依據
                    </p>
                </div>
                """, unsafe_allow_html=True)
    
    def _render_project_management(self):
        """渲染專案管理區域"""
        st.subheader("📋 撰寫專案")
        
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            # 顯示現有專案列表
            if st.session_state.writer_projects:
                project_options = []
                for project in st.session_state.writer_projects:
                    status_icon = "✅" if project.get('status') == 'completed' else "🔄" if project.get('status') == 'writing' else "📝"
                    project_options.append(f"{status_icon} {project['title']}")
                
                selected_idx = st.selectbox(
                    "選擇專案：",
                    range(len(project_options)),
                    format_func=lambda x: project_options[x],
                    key="project_selector"
                )
                
                if selected_idx is not None:
                    selected_project = st.session_state.writer_projects[selected_idx]
                    old_active_id = st.session_state.get('active_project_id')
                    st.session_state.active_project_id = selected_project['id']
                    
                    # 如果切換了專案，保存狀態
                    if old_active_id != st.session_state.active_project_id:
                        self._save_writer_persistent_state()
            else:
                st.info("尚無撰寫專案，請創建第一個專案")
        
        with col2:
            if st.button("➕ 新專案", type="primary", use_container_width=True):
                # 保存當前分頁狀態
                current_tab = st.session_state.get('current_tab', 'crawler')
                
                self._create_new_project()
                self._save_writer_persistent_state()
                
                # 恢復分頁狀態
                st.session_state.current_tab = current_tab
                
                st.rerun()
        
        with col3:
            if st.session_state.writer_projects and st.button("🗑️ 刪除專案", use_container_width=True):
                # 保存當前分頁狀態
                current_tab = st.session_state.get('current_tab', 'crawler')
                
                self._delete_current_project()
                self._save_writer_persistent_state()
                
                # 恢復分頁狀態
                st.session_state.current_tab = current_tab
                
                st.rerun()
    
    def _render_writing_interface(self):
        """渲染撰寫界面"""
        active_project = self._get_active_project()
        if not active_project:
            return
        
        st.markdown("---")
        st.subheader(f"✍️ {active_project['title']}")
        
        # 專案信息欄
        st.markdown(f"""
        <div style="background-color: #f0f8ff; padding: 10px; border-radius: 5px; margin-bottom: 15px;">
            <strong>📋 專案信息</strong> | 
            創建時間: {active_project['created_at']} | 
            狀態: {active_project.get('status', 'draft')} |
            {f"參考分析: {active_project.get('reference_analysis', '未選擇')}" if active_project.get('reference_analysis') else "參考分析: 未選擇"}
        </div>
        """, unsafe_allow_html=True)
        
        # 分頁式撰寫界面
        tabs = st.tabs(["🎯 撰寫設定", "✍️ 內容創作", "📝 生成結果", "⚙️ 專案管理"])
        
        with tabs[0]:
            self._render_writing_settings(active_project)
        
        with tabs[1]:
            self._render_content_creation(active_project)
        
        with tabs[2]:
            self._render_generated_results(active_project)
        
        with tabs[3]:
            self._render_project_management_panel(active_project)
    
    def _render_writing_settings(self, project: Dict[str, Any]):
        """渲染撰寫設定"""
        st.subheader("🎯 撰寫設定")
        
        # 選擇參考分析
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**📊 選擇參考分析**")
            saved_analyses = self.analyzer_component.get_saved_analysis_options()
            
            analysis_options = ["不使用參考"] + [f"{analysis['label']} ({analysis['created_at'][:10]})" for analysis in saved_analyses]
            
            current_ref = project.get('reference_analysis_id')
            current_idx = 0
            if current_ref:
                for i, analysis in enumerate(saved_analyses):
                    if analysis['analysis_id'] == current_ref:
                        current_idx = i + 1
                        break
            
            selected_idx = st.selectbox(
                "參考分析：",
                range(len(analysis_options)),
                index=current_idx,
                format_func=lambda x: analysis_options[x],
                key=f"ref_analysis_{project['id']}"
            )
            
            if selected_idx > 0:
                selected_analysis = saved_analyses[selected_idx - 1]
                project['reference_analysis_id'] = selected_analysis['analysis_id']
                project['reference_analysis'] = selected_analysis['label']
            else:
                project['reference_analysis_id'] = None
                project['reference_analysis'] = None
        
        with col2:
            st.markdown("**✍️ 撰寫風格**")
            writing_styles = [
                "自動預設 - 系統自動判斷最適合的風格",
                "原創風格 - 基於參考結構創作全新內容",
                "改寫風格 - 基於原文進行創新改寫", 
                "靈感風格 - 從參考中獲取靈感自由創作",
                "模仿風格 - 學習參考的寫作模式"
            ]
            
            project['writing_style'] = st.selectbox(
                "撰寫風格：",
                writing_styles,
                index=writing_styles.index(project.get('writing_style', writing_styles[0])),
                key=f"writing_style_{project['id']}"
            )
        
        # LLM 模型設定
        st.markdown("**🤖 LLM 模型設定**")
        llm_col1, llm_col2 = st.columns(2)
        
        with llm_col1:
            provider_options = ["Gemini (Google)", "OpenRouter"]
            project['llm_provider'] = st.selectbox(
                "LLM 提供商：",
                provider_options,
                index=provider_options.index(
                    project.get('llm_provider', 'Gemini (Google)')
                ),
                key=f"llm_provider_{project['id']}"
            )
        
        with llm_col2:
            # 根據選擇的提供商顯示不同的模型選項
            if project.get('llm_provider', 'Gemini (Google)') == 'Gemini (Google)':
                model_options = [
                    "gemini-2.0-flash",
                    "gemini-2.5-pro"
                ]
                default_model = 'gemini-2.0-flash'
            else:  # OpenRouter
                model_options = [
                    "perplexity/sonar",
                    "qwen/qwen3-235b-a22b:free", 
                    "moonshotai/kimi-k2:free",
                    "openai/gpt-oss-120b"
                ]
                default_model = 'perplexity/sonar'
            
            project['llm_model'] = st.selectbox(
                "LLM 模型：",
                model_options,
                index=model_options.index(
                    project.get('llm_model', default_model) if project.get('llm_model') in model_options else default_model
                ),
                key=f"llm_model_{project['id']}"
            )
        
        # 內容設定
        st.markdown("**📝 內容設定**")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            content_type_options = ["自動預設 - 系統自動判斷內容類型", "社群貼文", "產品介紹", "教學內容", "故事分享", "觀點評論"]
            project['content_type'] = st.selectbox(
                "內容類型：",
                content_type_options,
                index=content_type_options.index(
                    project.get('content_type', '自動預設 - 系統自動判斷內容類型')
                ),
                key=f"content_type_{project['id']}"
            )
        
        with col2:
            target_length_options = ["自動預設 - 系統自動判斷長度", "簡短 (50-100字)", "中等 (100-200字)", "詳細 (200-300字)", "長篇 (300+字)"]
            project['target_length'] = st.selectbox(
                "目標長度：",
                target_length_options,
                index=target_length_options.index(
                    project.get('target_length', '自動預設 - 系統自動判斷長度')
                ),
                key=f"target_length_{project['id']}"
            )
        
        with col3:
            tone_options = ["自動預設 - 系統自動判斷語調", "友善親切", "專業正式", "活潑有趣", "深度思考", "情感豐富"]
            project['tone'] = st.selectbox(
                "語調風格：",
                tone_options,
                index=tone_options.index(
                    project.get('tone', '自動預設 - 系統自動判斷語調')
                ),
                key=f"tone_{project['id']}"
            )
        
        with col4:
            project['post_count'] = st.selectbox(
                "生成數量：",
                [1, 2, 3, 4, 5],
                index=4,  # 預設5篇
                key=f"post_count_{project['id']}"
            )
        

    
    def _render_content_creation(self, project: Dict[str, Any]):
        """渲染內容創作區域"""
        st.subheader("✍️ 內容創作")
        
        # 創作提示輸入
        prompt_col1, prompt_col2 = st.columns([4, 1])
        
        with prompt_col1:
            st.markdown("**💭 創作提示**")
        
        with prompt_col2:
            if st.button("🗑️ 清空提示", key=f"clear_prompt_{project['id']}", help="清空創作提示，重新開始", use_container_width=True):
                project['user_prompt'] = ''
                project['prompt_source'] = '手動輸入'
                self._save_writer_persistent_state()
                st.rerun()
        
        # 暫存當前提示內容
        current_prompt = project.get('user_prompt', '')
        
        project['user_prompt'] = st.text_area(
            "描述您想要創作的內容：",
            value=current_prompt,
            height=100,
            placeholder="例如：我想寫一篇關於咖啡文化的貼文，重點介紹手沖咖啡的技巧和心得...",
            key=f"user_prompt_{project['id']}"
        )

        # 是否在提示後追加嚴格模板指示
        strict_key = f"strict_template_{project['id']}"
        strict_default = project.get('strict_template', True)
        project['strict_template'] = st.checkbox("嚴格使用模板寫作）", value=strict_default, key=strict_key)
        
        # 檢查用戶是否手動修改了提示內容
        if project['user_prompt'] != current_prompt and project['user_prompt']:
            # 如果用戶修改了內容，更新來源為手動輸入
            if not project.get('prompt_source') or project.get('prompt_source') != '手動輸入':
                project['prompt_source'] = '手動輸入'
                self._save_writer_persistent_state()
        
        # 顯示提示來源信息
        if project.get('user_prompt'):
            prompt_source = project.get('prompt_source', '手動輸入')
            st.caption(f"📝 提示來源：{prompt_source}")
        else:
            st.caption("💡 請輸入您的創作需求，系統會根據您的描述生成個性化內容")
        
        # 生成按鈕
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("🚀 開始創作", type="primary", use_container_width=True):
                self._generate_content(project)
        
        # 顯示創作歷史
        if project.get('generation_history'):
            st.markdown("---")
            st.markdown("**📚 創作歷史**")
            
            for i, generation in enumerate(reversed(project['generation_history'])):
                with st.expander(f"版本 {len(project['generation_history']) - i} - {generation['created_at'][:16]}", expanded=i==0):
                    st.markdown("**創作提示：**")
                    st.text(generation['prompt'])
                    st.markdown("**生成內容：**")
                    st.markdown(generation['content'])
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button(f"📋 複製內容", key=f"copy_{project['id']}_{i}"):
                            st.code(generation['content'])
                    with col2:
                        if st.button(f"⭐ 保留到精選", key=f"save_{project['id']}_{i}"):
                            self._save_to_favorites(project, generation)
                            st.success("✅ 已保留到精選！")
                            st.rerun()
    
    def _save_to_favorites(self, project: Dict[str, Any], generation: Dict[str, Any]):
        """保存版本到精選"""
        if 'saved_posts' not in project:
            project['saved_posts'] = []
        
        # 創建精選版本對象
        saved_post = {
            'id': f"saved_{len(project['saved_posts'])}_{int(time.time())}",
            'content': generation['content'],
            'prompt': generation['prompt'],
            'created_at': generation['created_at'],
            'saved_at': datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None).isoformat(),
            'settings': generation.get('settings', {}),
            'version_info': f"版本 {generation.get('version', '未知')}"
        }
        
        # 檢查是否已存在相同內容（避免重複保存）
        existing_content = [p['content'] for p in project['saved_posts']]
        if generation['content'] not in existing_content:
            project['saved_posts'].append(saved_post)
            self._save_writer_persistent_state()
    
    def _render_generated_results(self, project: Dict[str, Any]):
        """渲染精選的生成結果"""
        st.subheader("📝 精選貼文")
        
        saved_posts = project.get('saved_posts', [])
        
        if not saved_posts:
            st.info("🌟 尚未保留任何精選貼文\n\n請到「✍️ 內容創作」頁面生成內容，然後點擊「⭐ 保留到精選」按鈕")
            return
        
        # 統計資訊
        st.markdown(f"**📊 精選統計：** 共有 **{len(saved_posts)}** 篇精選貼文")
        
        # 顯示精選貼文
        st.markdown("---")
        
        for i, saved_post in enumerate(saved_posts):
            with st.expander(f"⭐ 精選 {i+1} - {saved_post['saved_at'][:16]}", expanded=False):
                # 顯示貼文內容
                st.markdown("**📝 精選內容：**")
                content_with_breaks = saved_post['content'].replace('\n', '<br>')
                st.markdown(
                    f"""
                    <div style="background-color: #fff3cd; padding: 15px; border-radius: 8px; border-left: 4px solid #ffc107; margin: 10px 0;">
                        {content_with_breaks}
                    </div>
                    """, 
                    unsafe_allow_html=True
                )
                
                # 顯示詳細資訊
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**ℹ️ 詳細資訊：**")
                    st.text(f"原始創作時間：{saved_post['created_at'][:16]}")
                    st.text(f"保存時間：{saved_post['saved_at'][:16]}")
                    if saved_post.get('version_info'):
                        st.text(f"版本：{saved_post['version_info']}")
                
                with col2:
                    st.markdown("**💭 創作提示：**")
                    edited_prompt = st.text_area("創作提示內容", value=saved_post['prompt'], height=80, key=f"prompt_view_{saved_post['id']}", label_visibility="collapsed")
                    
                    # 如果提示詞被修改，顯示保存按鈕
                    if edited_prompt != saved_post['prompt']:
                        if st.button("💾 保存修改", key=f"save_prompt_{saved_post['id']}", use_container_width=True):
                            saved_post['prompt'] = edited_prompt
                            self._save_writer_persistent_state()
                            st.success("✅ 創作提示已更新")
                            st.rerun()
                
                # 操作按鈕
                btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4)
                
                with btn_col1:
                    if st.button("📋 複製內容", key=f"copy_saved_{saved_post['id']}", use_container_width=True):
                        st.code(saved_post['content'])
                
                with btn_col2:
                    if st.button("📤 匯出文字", key=f"export_saved_{saved_post['id']}", use_container_width=True):
                        st.download_button(
                            label="📁 下載 TXT",
                            data=saved_post['content'],
                            file_name=f"精選貼文_{i+1}_{saved_post['saved_at'][:10]}.txt",
                            mime="text/plain",
                            key=f"download_saved_{saved_post['id']}"
                        )
                
                with btn_col3:
                    if st.button("🔄 基於此重新創作", key=f"recreate_saved_{saved_post['id']}", use_container_width=True):
                        project['user_prompt'] = saved_post['prompt']
                        project['prompt_source'] = f"精選貼文 {i+1}"
                        self._save_writer_persistent_state()
                        st.success("✅ 已更新創作提示，請切換到「✍️ 內容創作」頁面")
                        st.info(f"💭 新的創作提示：{saved_post['prompt'][:50]}...")
                
                with btn_col4:
                    if st.button("🗑️ 從精選移除", key=f"remove_saved_{saved_post['id']}", use_container_width=True):
                        project['saved_posts'].remove(saved_post)
                        self._save_writer_persistent_state()
                        st.success("✅ 已從精選中移除")
                        st.rerun()
                
                # 內容統計
                word_count = len(saved_post['content'])
                line_count = saved_post['content'].count('\n') + 1
                
                stat_col1, stat_col2 = st.columns(2)
                with stat_col1:
                    st.metric("字數", word_count, label_visibility="collapsed")
                with stat_col2:
                    st.metric("行數", line_count, label_visibility="collapsed")
        
        # 批量操作
        if len(saved_posts) > 1:
            st.markdown("---")
            st.markdown("**🔧 批量操作**")
            
            batch_col1, batch_col2 = st.columns(2)
            
            with batch_col1:
                if st.button("📤 匯出所有精選", use_container_width=True):
                    # 組合所有精選內容
                    all_content = ""
                    for i, post in enumerate(saved_posts):
                        all_content += f"=== 精選貼文 {i+1} ===\n"
                        all_content += f"創作時間：{post['created_at']}\n"
                        all_content += f"保存時間：{post['saved_at']}\n"
                        all_content += f"創作提示：{post['prompt']}\n\n"
                        all_content += f"{post['content']}\n\n"
                        all_content += "="*50 + "\n\n"
                    
                    st.download_button(
                        label="📁 下載所有精選貼文",
                        data=all_content,
                        file_name=f"所有精選貼文_{datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M%S')}.txt",
                        mime="text/plain"
                    )
            
            with batch_col2:
                if st.button("🗑️ 清空所有精選", use_container_width=True):
                    if st.button("⚠️ 確認清空", use_container_width=True):
                        project['saved_posts'] = []
                        self._save_writer_persistent_state()
                        st.success("✅ 已清空所有精選貼文")
                        st.rerun()
    
    def _create_new_project(self):
        """創建新專案"""
        st.session_state.project_counter += 1
        project_id = f"project_{st.session_state.project_counter}"
        
        new_project = {
            'id': project_id,
            'title': f"撰寫專案 {st.session_state.project_counter}",
            'created_at': datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S"),
            'status': 'draft',
            'reference_analysis_id': None,
            'reference_analysis': None,
            'writing_style': "自動預設 - 系統自動判斷最適合的風格",
            'llm_provider': 'Gemini (Google)',
            'llm_model': 'gemini-2.5-flash',
            'content_type': '自動預設 - 系統自動判斷內容類型',
            'target_length': '自動預設 - 系統自動判斷長度',
            'tone': '自動預設 - 系統自動判斷語調',
            'user_prompt': '',
            'generation_history': []
        }
        
        st.session_state.writer_projects.append(new_project)
        st.session_state.active_project_id = project_id
    
    def _delete_current_project(self):
        """刪除當前專案"""
        if st.session_state.active_project_id:
            original_count = len(st.session_state.writer_projects)
            project_to_delete = st.session_state.active_project_id
            
            st.session_state.writer_projects = [
                p for p in st.session_state.writer_projects 
                if p['id'] != st.session_state.active_project_id
            ]
            
            new_count = len(st.session_state.writer_projects)
            if original_count > new_count:
                st.success(f"✅ 已刪除專案 {project_to_delete[:8]}...")
                
                if st.session_state.writer_projects:
                    st.session_state.active_project_id = st.session_state.writer_projects[-1]['id']
                    st.info(f"ℹ️ 已切換到專案 {st.session_state.active_project_id[:8]}...")
                else:
                    st.session_state.active_project_id = None
                    st.info("ℹ️ 已清空所有專案")
            else:
                st.warning("⚠️ 專案清單中未找到對應項目")
        else:
            st.warning("⚠️ 沒有選中的專案可刪除")
    
    def _get_active_project(self) -> Dict[str, Any]:
        """獲取當前活動專案"""
        if not st.session_state.active_project_id:
            return None
        
        for project in st.session_state.writer_projects:
            if project['id'] == st.session_state.active_project_id:
                return project
        return None
    
    def _generate_content(self, project: Dict[str, Any]):
        """生成內容"""
        try:
            with st.spinner("🤖 AI 正在創作中..."):
                # 準備生成請求
                user_prompt_to_send = project['user_prompt'] + ("\n\n##請嚴格使用模板來寫貼文" if project.get('strict_template') else "")
                generation_data = {
                    'user_prompt': user_prompt_to_send,
                    'llm_config': {
                        'provider': project.get('llm_provider', 'Gemini (Google)'),
                        'model': project.get('llm_model', 'gemini-2.0-flash')
                    },
                    'settings': {
                        'writing_style': project.get('writing_style'),
                        'content_type': project.get('content_type'),
                        'target_length': project.get('target_length'),
                        'tone': project.get('tone'),
                        'post_count': project.get('post_count', 5)
                    }
                }
                
                # 如果有參考分析，添加到請求中
                if project.get('reference_analysis_id'):
                    reference_content = self.analyzer_component.get_analysis_content_for_llm(
                        project['reference_analysis_id']
                    )
                    if reference_content:
                        generation_data['reference_analysis'] = reference_content
                
                # 調用真正的生成服務 (同步方式)
                generated_posts = asyncio.run(self._call_content_generator_service(generation_data))
                
                # 保存生成結果 (每個版本單獨保存)
                for i, post_content in enumerate(generated_posts):
                    generation_record = {
                        'prompt': user_prompt_to_send,
                        'content': post_content,
                        'version': f"版本 {i + 1}",
                        'settings': generation_data['settings'],
                        'created_at': datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
                    }
                    
                    if 'generation_history' not in project:
                        project['generation_history'] = []
                    
                    project['generation_history'].append(generation_record)
                
                project['status'] = 'writing'
                
                # 保存狀態
                self._save_writer_persistent_state()
                
                # 保存當前分頁狀態
                current_tab = st.session_state.get('current_tab', 'crawler')
                st.session_state.current_tab = current_tab
                
                st.success("✅ 內容創作完成！")
                st.rerun()
                
        except Exception as e:
            st.error(f"❌ 創作過程中發生錯誤: {e}")
            # 不保存錯誤狀態，讓用戶可以重試
    

    
    # =================== 持久化狀態管理 ===================
    
    def _load_writer_persistent_state(self):
        """載入撰寫專案的持久化狀態"""
        try:
            if self.projects_state_file.exists():
                with open(self.projects_state_file, 'r', encoding='utf-8') as f:
                    state_data = json.load(f)
                
                # 載入專案列表
                if 'writer_projects' in state_data:
                    st.session_state.writer_projects = state_data['writer_projects']
                
                # 載入當前活動專案
                if 'active_project_id' in state_data:
                    st.session_state.active_project_id = state_data['active_project_id']
                
                # 載入專案計數器
                if 'project_counter' in state_data:
                    st.session_state.project_counter = state_data['project_counter']
                
                # 確保活動專案存在
                if st.session_state.active_project_id:
                    project_exists = any(
                        p['id'] == st.session_state.active_project_id 
                        for p in st.session_state.writer_projects
                    )
                    if not project_exists:
                        st.session_state.active_project_id = None
                        
        except Exception as e:
            st.error(f"載入撰寫專案狀態失敗: {e}")
    
    def _save_writer_persistent_state(self):
        """保存撰寫專案的持久化狀態"""
        try:
            state_data = {
                'writer_projects': st.session_state.get('writer_projects', []),
                'active_project_id': st.session_state.get('active_project_id'),
                'project_counter': st.session_state.get('project_counter', 0),
                'last_updated': datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None).isoformat()
            }
            
            with open(self.projects_state_file, 'w', encoding='utf-8') as f:
                json.dump(state_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            st.error(f"保存撰寫專案狀態失敗: {e}")
    
    def _clear_writer_persistent_state(self):
        """清除撰寫專案的持久化狀態"""
        try:
            if self.projects_state_file.exists():
                self.projects_state_file.unlink()
        except Exception as e:
            st.error(f"清除撰寫專案狀態失敗: {e}")
    
    def _render_project_management_panel(self, project: Dict[str, Any]):
        """渲染專案管理面板"""
        st.subheader("⚙️ 專案管理")
        
        # 專案操作
        st.markdown("**🔧 專案操作**")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🔄 重置專案", help="清空當前專案的所有生成記錄", use_container_width=True):
                if project:
                    project['generation_history'] = []
                    project['status'] = 'draft'
                    project['user_prompt'] = ''
                    self._save_writer_persistent_state()
                    st.success("✅ 專案已重置")
        
        with col2:
            if st.button("📋 複製專案", help="創建當前專案的副本", use_container_width=True):
                if project:
                    self._duplicate_project(project)
                    self._save_writer_persistent_state()
                    st.success("✅ 專案已複製")
        
        with col3:
            if st.button("🗑️ 清空所有專案", help="刪除所有撰寫專案", use_container_width=True, type="secondary"):
                # 保存當前分頁狀態
                current_tab = st.session_state.get('current_tab', 'crawler')
                
                st.session_state.writer_projects = []
                st.session_state.active_project_id = None
                st.session_state.project_counter = 0
                self._save_writer_persistent_state()
                
                # 恢復分頁狀態
                st.session_state.current_tab = current_tab
                
                st.success("✅ 所有專案已清空")
                st.rerun()
        
        # LLM 連接檢查
        st.markdown("---")
        st.markdown("**🤖 LLM 連接檢查**")
        
        llm_col1, llm_col2 = st.columns(2)
        
        with llm_col1:
            if st.button("🔍 檢查服務狀態", help="檢查 content-generator 服務是否運行", use_container_width=True):
                self._check_service_status()
        
        with llm_col2:
            if st.button("🧠 測試 LLM 連接", help="測試 LLM API 連接", use_container_width=True):
                self._test_llm_connection()
        
        # 持久化狀態管理
        st.markdown("---")
        st.markdown("**💾 狀態管理**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("💾 手動保存狀態", help="手動保存當前所有專案狀態", use_container_width=True):
                self._save_writer_persistent_state()
                st.success("✅ 狀態已保存")
        
        with col2:
            if st.button("🗑️ 清除持久化", help="清除所有保存的專案狀態", use_container_width=True, type="secondary"):
                # 保存當前分頁狀態
                current_tab = st.session_state.get('current_tab', 'crawler')
                
                self._clear_writer_persistent_state()
                st.session_state.writer_projects = []
                st.session_state.active_project_id = None
                st.session_state.project_counter = 0
                
                # 恢復分頁狀態
                st.session_state.current_tab = current_tab
                
                st.success("✅ 持久化狀態已清除")
                st.rerun()
        
        # 參考分析管理
        st.markdown("---")
        st.markdown("**📊 參考分析管理**")
        saved_analyses = self.analyzer_component.get_saved_analysis_options()
        if not saved_analyses:
            st.info("目前沒有任何已保存的參考分析。請先到『📊 內容分析』頁面保存分析。")
        else:
            st.caption(f"共 {len(saved_analyses)} 筆參考分析")

            # 批次選取刪除
            multi_cols = st.columns([3, 1])
            with multi_cols[0]:
                multi_options = [f"{a['label']}（{a['created_at'][:16]}）" for a in saved_analyses]
                selected_idx_list = st.multiselect(
                    "選擇要刪除的參考分析：",
                    options=list(range(len(saved_analyses))),
                    format_func=lambda i: multi_options[i],
                    key="ref_analysis_multi_delete"
                )
            with multi_cols[1]:
                if st.button("🗑️ 批量刪除", use_container_width=True) and selected_idx_list:
                    deleted_ids = []
                    for i in selected_idx_list:
                        analysis_id = saved_analyses[i]['analysis_id']
                        try:
                            # 呼叫分析組件的刪除函式
                            self.analyzer_component._delete_analysis_result(analysis_id)
                            deleted_ids.append(analysis_id)
                        except Exception as e:
                            st.error(f"刪除失敗：{e}")
                    if deleted_ids:
                        self._cleanup_deleted_reference_ids(deleted_ids)
                        self._save_writer_persistent_state()
                        st.success(f"✅ 已刪除 {len(deleted_ids)} 筆參考分析")
                        st.rerun()

            # 清單檢視與單筆操作
            for analysis in saved_analyses:
                with st.expander(f"{analysis['label']}（{analysis['created_at'][:16]}）", expanded=False):
                    col_a, col_b, col_c = st.columns([1, 1, 6])
                    with col_a:
                        if st.button("🗑️ 刪除", key=f"del_ref_{analysis['analysis_id']}", use_container_width=True):
                            try:
                                self.analyzer_component._delete_analysis_result(analysis['analysis_id'])
                                self._cleanup_deleted_reference_ids([analysis['analysis_id']])
                                self._save_writer_persistent_state()
                                st.success("✅ 已刪除")
                                st.rerun()
                            except Exception as e:
                                st.error(f"刪除失敗：{e}")
                    with col_b:
                        if st.button("👁️ 預覽", key=f"view_ref_{analysis['analysis_id']}", use_container_width=True):
                            content = self.analyzer_component.get_analysis_content_for_llm(analysis['analysis_id'])
                            if content:
                                st.markdown("**原始貼文**")
                                st.json(content.get('original_post', {}))
                            else:
                                st.warning("未找到內容，可能已被刪除。")
                    with col_c:
                        st.caption(f"ID: {analysis['analysis_id']}")

            # 全部清空
            clear_col1, clear_col2 = st.columns([3, 1])
            with clear_col1:
                st.caption("若需要可清空所有已保存參考分析（不影響撰寫專案）")
            with clear_col2:
                if st.button("🗑️ 清空所有參考分析", use_container_width=True):
                    try:
                        ids = [a['analysis_id'] for a in saved_analyses]
                        for aid in ids:
                            self.analyzer_component._delete_analysis_result(aid)
                        self._cleanup_deleted_reference_ids(ids)
                        self._save_writer_persistent_state()
                        st.success("✅ 已清空所有參考分析")
                        st.rerun()
                    except Exception as e:
                        st.error(f"清空失敗：{e}")

        # 專案詳細信息
        if project:
            st.markdown("---")
            st.markdown("**🔍 當前專案詳細信息**")
            
            info_col1, info_col2 = st.columns(2)
            
            with info_col1:
                st.write(f"📋 專案ID: `{project['id']}`")
                st.write(f"📝 專案標題: `{project['title']}`")
                st.write(f"⏰ 創建時間: `{project['created_at']}`")
                st.write(f"🏷️ 狀態: `{project['status']}`")
            
            with info_col2:
                st.write(f"🤖 LLM 提供商: `{project.get('llm_provider', '未設定')}`")
                st.write(f"🧠 LLM 模型: `{project.get('llm_model', '未設定')}`")
                st.write(f"✍️ 撰寫風格: `{project.get('writing_style', '未設定')}`")
                st.write(f"📝 內容類型: `{project.get('content_type', '未設定')}`")
            
            # 生成歷史統計
            generation_count = len(project.get('generation_history', []))
            st.write(f"📊 生成版本數: `{generation_count}`")
            
            if project.get('reference_analysis_id'):
                st.write(f"📊 參考分析: `{project.get('reference_analysis', '未知')}`")
        
        # 全局統計
        st.markdown("---")
        st.markdown("**📈 全局統計**")
        
        total_projects = len(st.session_state.get('writer_projects', []))
        completed_projects = len([p for p in st.session_state.get('writer_projects', []) if p.get('status') == 'completed'])
        
        stat_col1, stat_col2, stat_col3 = st.columns(3)
        
        with stat_col1:
            st.metric("總專案數", total_projects)
        
        with stat_col2:
            st.metric("已完成", completed_projects)
        
        with stat_col3:
            st.metric("進行中", total_projects - completed_projects)
    
    def _duplicate_project(self, source_project: Dict[str, Any]):
        """複製專案"""
        st.session_state.project_counter += 1
        new_project_id = f"project_{st.session_state.project_counter}"
        
        # 複製專案數據，但清空生成歷史
        new_project = source_project.copy()
        new_project.update({
            'id': new_project_id,
            'title': f"{source_project['title']} (副本)",
            'created_at': datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S"),
            'status': 'draft',
            'generation_history': []
        })
        
        st.session_state.writer_projects.append(new_project)
        st.session_state.active_project_id = new_project_id
    
    async def _call_content_generator_service(self, generation_data: Dict[str, Any]) -> List[str]:
        """調用真正的內容生成服務"""
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(
                    self.content_generator_url,
                    json=generation_data,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()
                
                result = response.json()
                return result.get('generated_posts', [])
                
        except httpx.ConnectError:
            st.error("❌ 無法連接到內容生成服務 (http://localhost:8008)")
            st.info("🔧 請檢查 content-generator-agent 服務是否運行")
            st.code("docker-compose up content-generator-agent -d")
            raise Exception("內容生成服務未啟動")
            
        except httpx.TimeoutException:
            st.error("⏱️ 內容生成服務響應超時")
            st.info("🔧 LLM 調用可能耗時較長，請稍後重試")
            raise Exception("服務響應超時")
            
        except httpx.HTTPStatusError as e:
            st.error(f"❌ 內容生成服務錯誤: HTTP {e.response.status_code}")
            if e.response.status_code == 500:
                st.info("🔧 請檢查 LLM API 配置和密鑰是否正確")
                st.code("檢查 .env 文件中的 GEMINI_API_KEY 或 OPENROUTER_API_KEY")
            raise Exception(f"服務錯誤: {e.response.status_code}")
            
        except Exception as e:
            st.error(f"❌ 內容生成失敗: {str(e)}")
            st.info("🔧 請檢查 LLM 連接狀態和 API 配置")
            raise e
    
    def _check_service_status(self):
        """檢查 content-generator 服務狀態"""
        try:
            import httpx
            with httpx.Client(timeout=5) as client:
                response = client.get("http://localhost:8008/health")
                if response.status_code == 200:
                    st.success("✅ content-generator 服務運行正常")
                    result = response.json()
                    st.info(f"服務狀態: {result.get('status', 'unknown')}")
                else:
                    st.error(f"❌ 服務響應異常: HTTP {response.status_code}")
        except httpx.ConnectError:
            st.error("❌ 無法連接到 content-generator 服務")
            st.info("🔧 請運行以下命令啟動服務:")
            st.code("docker-compose up content-generator-agent -d")
        except Exception as e:
            st.error(f"❌ 檢查服務時發生錯誤: {e}")
    
    def _test_llm_connection(self):
        """測試 LLM 連接"""
        try:
            import httpx
            test_data = {
                "user_prompt": "測試連接",
                "llm_config": {
                    "provider": "Gemini (Google)",
                    "model": "gemini-2.0-flash"
                },
                "settings": {
                    "writing_style": "自動預設",
                    "content_type": "測試",
                    "target_length": "簡短",
                    "tone": "友善"
                }
            }
            
            with st.spinner("🔍 測試 LLM 連接..."):
                with httpx.Client(timeout=30) as client:
                    response = client.post(
                        "http://localhost:8008/generate-content",
                        json=test_data,
                        headers={"Content-Type": "application/json"}
                    )
                    
                if response.status_code == 200:
                    st.success("✅ LLM 連接測試成功")
                    result = response.json()
                    posts = result.get('generated_posts', [])
                    st.info(f"生成了 {len(posts)} 個測試內容")
                else:
                    st.error(f"❌ LLM 連接測試失敗: HTTP {response.status_code}")
                    if response.status_code == 500:
                        st.info("🔧 可能是 API 密鑰問題，請檢查 .env 配置")
                        
        except httpx.ConnectError:
            st.error("❌ 無法連接到 content-generator 服務")
            st.info("🔧 請先啟動 content-generator-agent 服務")
        except httpx.TimeoutException:
            st.error("⏱️ LLM 請求超時")
            st.info("🔧 LLM API 響應時間較長，請檢查網絡連接")
        except Exception as e:
            st.error(f"❌ 測試 LLM 連接時發生錯誤: {e}")
