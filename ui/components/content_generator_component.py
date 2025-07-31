"""
內容生成組件
智能貼文生成器，支持通用主題
"""

import streamlit as st
import httpx
import json
import uuid
import asyncio
from typing import Dict, Any, Optional


class ContentGeneratorComponent:
    def __init__(self):
        self.orchestrator_url = "http://localhost:8000"
        self.form_api_url = "http://localhost:8010"
    
    def render(self):
        """渲染內容生成界面"""
        # 根據當前步驟渲染不同界面
        current_step = st.session_state.get('content_step', 'input')
        
        if current_step == 'input':
            self._render_input_step()
        elif current_step == 'clarification':
            self._render_clarification_step()
        elif current_step == 'result':
            self._render_result_step()
    
    def _render_input_step(self):
        """渲染輸入步驟"""
        st.header("📝 智能貼文生成器")
        st.markdown("輸入你想要的貼文內容，我們會幫你生成專業的社交媒體貼文！支持任何主題和風格。")
        
        # 主題示例
        with st.expander("💡 主題示例", expanded=False):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.write("**美妝保養**")
                st.write("- 新品推薦貼文")
                st.write("- 使用心得分享")
                st.write("- 護膚步驟教學")
            with col2:
                st.write("**生活日常**")
                st.write("- 週末生活分享")
                st.write("- 美食探店體驗")
                st.write("- 旅遊景點推薦")
            with col3:
                st.write("**商品推廣**")
                st.write("- 產品特色介紹")
                st.write("- 限時優惠活動")
                st.write("- 品牌故事分享")
        
        # 輸入區域
        user_input = st.text_area(
            "請描述你想要的貼文內容：",
            placeholder="例如：我要寫一篇咖啡店新品推薦貼文，強調口感和氛圍",
            height=120,
            help="可以包含主題、風格、重點等任何你想要的元素",
            key="content_user_input"
        )
        
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            if st.button("🚀 開始生成", type="primary", use_container_width=True):
                if user_input.strip():
                    self._start_generation(user_input)
                else:
                    st.warning("請輸入內容描述")
        
        with col2:
            if st.button("🔄 重新開始", use_container_width=True):
                self._reset_generator()
                st.rerun()
        
        with col3:
            if st.button("📊 查看示例", use_container_width=True):
                st.session_state.show_examples = not st.session_state.get('show_examples', False)
                st.rerun()
    
    def _render_clarification_step(self):
        """渲染澄清步驟"""
        st.header("🤔 需要一些澄清")
        st.markdown("為了生成更符合你需求的內容，請回答以下問題：")
        
        # 獲取問題
        questions_data = self._get_questions()
        if not questions_data:
            st.error("無法載入問題，請重新開始")
            if st.button("重新開始"):
                self._reset_generator()
                st.rerun()
            return
        
        questions = questions_data["questions"]
        answers = {}
        
        # 渲染問題表單
        with st.form("clarification_form"):
            for i, question in enumerate(questions):
                st.subheader(f"問題 {i+1}")
                st.write(question["question"])
                
                # 選項
                options = question["options"]
                selected = st.radio(
                    f"選擇選項 (問題 {i+1})",
                    options,
                    key=f"q_{question['id']}"
                )
                
                # 如果選擇了"自訂"，顯示文字輸入框
                if selected == "自訂":
                    custom_input = st.text_input(
                        f"請輸入自訂內容 (問題 {i+1})",
                        key=f"custom_{question['id']}"
                    )
                    answers[question["id"]] = f"自訂:{custom_input}" if custom_input else "自訂:"
                else:
                    answers[question["id"]] = selected
                
                st.divider()
            
            # 提交按鈕
            col1, col2 = st.columns([1, 1])
            with col1:
                submitted = st.form_submit_button("✅ 提交答案", type="primary")
            with col2:
                if st.form_submit_button("⬅️ 返回修改"):
                    st.session_state.content_step = "input"
                    st.rerun()
        
        if submitted:
            self._submit_answers(answers)
    
    def _render_result_step(self):
        """渲染結果步驟"""
        st.header("🎉 內容生成完成！")
        
        # 顯示生成的內容
        st.subheader("📄 生成的貼文內容")
        
        final_post = st.session_state.get('final_post', '')
        
        # 使用文字區域顯示，方便複製
        st.text_area(
            "生成的貼文：",
            value=final_post,
            height=200,
            help="點擊文字區域可以選擇和複製內容"
        )
        
        # 顯示使用的模板
        if st.session_state.get('template_used'):
            template_name = "連貫敘事" if st.session_state.template_used == "narrative" else "分行條列"
            st.info(f"使用模板：{template_name}")
        
        # 操作按鈕
        col1, col2, col3 = st.columns([1, 1, 1])
        
        with col1:
            if st.button("🔄 重新生成", use_container_width=True):
                st.session_state.content_step = "input"
                st.rerun()
        
        with col2:
            if st.button("✏️ 重新澄清", use_container_width=True):
                st.session_state.content_step = "clarification"
                st.rerun()
        
        with col3:
            if st.button("📝 生成新貼文", use_container_width=True):
                self._reset_generator()
                st.rerun()
    
    def _start_generation(self, user_input: str):
        """開始生成流程"""
        with st.spinner("正在分析你的需求..."):
            try:
                # 調用 orchestrator
                result = asyncio.run(self._call_orchestrator(user_input))
                
                if result["status"] == "need_clarification":
                    st.session_state.content_step = "clarification"
                    st.session_state.user_input = user_input
                    st.rerun()
                elif result["status"] == "completed":
                    st.session_state.final_post = result["final_post"]
                    st.session_state.content_step = "result"
                    st.rerun()
            except Exception as e:
                st.error(f"處理請求時發生錯誤: {str(e)}")
    
    def _submit_answers(self, answers: Dict[str, str]):
        """提交答案"""
        with st.spinner("正在生成內容..."):
            try:
                session_id = st.session_state.get('session_id', str(uuid.uuid4()))
                result = asyncio.run(self._submit_answers_api(session_id, answers))
                
                if result["status"] == "completed":
                    st.session_state.final_post = result["final_post"]
                    st.session_state.template_used = result.get("template_used", "unknown")
                    st.session_state.content_step = "result"
                    st.rerun()
                else:
                    st.error("內容生成失敗")
            except Exception as e:
                st.error(f"提交答案時發生錯誤: {str(e)}")
    
    def _get_questions(self) -> Optional[Dict[str, Any]]:
        """獲取問題"""
        try:
            session_id = st.session_state.get('session_id', str(uuid.uuid4()))
            return asyncio.run(self._get_form_questions(session_id))
        except:
            return None
    
    async def _call_orchestrator(self, text: str) -> Dict[str, Any]:
        """調用 Orchestrator"""
        session_id = str(uuid.uuid4())
        st.session_state.session_id = session_id
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.orchestrator_url}/user",
                json={
                    "text": text,
                    "session_id": session_id
                },
                timeout=30
            )
            response.raise_for_status()
            return response.json()
    
    async def _get_form_questions(self, session_id: str) -> Optional[Dict[str, Any]]:
        """獲取表單問題"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.form_api_url}/form/{session_id}",
                    timeout=10
                )
                response.raise_for_status()
                return response.json()
        except:
            return None
    
    async def _submit_answers_api(self, session_id: str, answers: Dict[str, str]) -> Dict[str, Any]:
        """提交答案 API"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.orchestrator_url}/answers",
                json={
                    "session_id": session_id,
                    "answers": answers
                },
                timeout=60
            )
            response.raise_for_status()
            return response.json()
    
    def _reset_generator(self):
        """重置生成器狀態"""
        keys_to_reset = [
            'content_step', 'session_id', 'user_input', 
            'final_post', 'template_used', 'show_examples'
        ]
        for key in keys_to_reset:
            if key in st.session_state:
                del st.session_state[key]
        
        st.session_state.content_step = 'input'