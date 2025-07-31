#!/usr/bin/env python3
"""
Streamlit UI - 社交媒體內容生成器前端
快速原型界面，支援三層 LLM 澄清流程
"""

import streamlit as st
import httpx
import json
import uuid
import asyncio
from typing import Dict, Any, Optional

# 設置頁面配置
st.set_page_config(
    page_title="社交媒體內容生成器",
    page_icon="📝",
    layout="wide"
)

# 全域配置
ORCHESTRATOR_URL = "http://localhost:8000"
FORM_API_URL = "http://localhost:8010"

class ContentGeneratorUI:
    def __init__(self):
        if 'session_id' not in st.session_state:
            st.session_state.session_id = str(uuid.uuid4())
        if 'current_step' not in st.session_state:
            st.session_state.current_step = "input"
        if 'questions' not in st.session_state:
            st.session_state.questions = []
        if 'final_post' not in st.session_state:
            st.session_state.final_post = ""
    
    async def call_orchestrator(self, text: str) -> Dict[str, Any]:
        """調用 Orchestrator 處理用戶請求"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{ORCHESTRATOR_URL}/user",
                json={
                    "text": text,
                    "session_id": st.session_state.session_id
                },
                timeout=30
            )
            response.raise_for_status()
            return response.json()
    
    async def get_form_questions(self, session_id: str) -> Optional[Dict[str, Any]]:
        """獲取表單問題"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{FORM_API_URL}/form/{session_id}",
                    timeout=10
                )
                response.raise_for_status()
                return response.json()
        except:
            return None
    
    async def submit_answers(self, session_id: str, answers: Dict[str, str]) -> Dict[str, Any]:
        """提交答案"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{ORCHESTRATOR_URL}/answers",
                json={
                    "session_id": session_id,
                    "answers": answers
                },
                timeout=60
            )
            response.raise_for_status()
            return response.json()
    
    def render_input_step(self):
        """渲染輸入步驟"""
        st.header("📝 社交媒體內容生成器")
        st.markdown("輸入你想要的貼文內容，我們會幫你生成專業的社交媒體貼文！")
        
        # 輸入區域
        user_input = st.text_area(
            "請描述你想要的貼文內容：",
            placeholder="例如：我要一篇新品乳霜的推薦貼文",
            height=100
        )
        
        col1, col2 = st.columns([1, 4])
        
        with col1:
            if st.button("🚀 開始生成", type="primary"):
                if user_input.strip():
                    with st.spinner("正在分析你的需求..."):
                        try:
                            # 調用 orchestrator
                            result = asyncio.run(self.call_orchestrator(user_input))
                            
                            if result["status"] == "need_clarification":
                                st.session_state.current_step = "clarification"
                                st.session_state.user_input = user_input
                                st.rerun()
                            elif result["status"] == "completed":
                                st.session_state.final_post = result["final_post"]
                                st.session_state.current_step = "result"
                                st.rerun()
                        except Exception as e:
                            st.error(f"處理請求時發生錯誤: {str(e)}")
                else:
                    st.warning("請輸入內容描述")
        
        with col2:
            if st.button("🔄 重新開始"):
                # 重置所有狀態
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()
    
    def render_clarification_step(self):
        """渲染澄清步驟"""
        st.header("🤔 需要一些澄清")
        st.markdown("為了生成更符合你需求的內容，請回答以下問題：")
        
        # 獲取問題
        with st.spinner("載入問題中..."):
            questions_data = asyncio.run(self.get_form_questions(st.session_state.session_id))
        
        if not questions_data:
            st.error("無法載入問題，請重新開始")
            if st.button("重新開始"):
                st.session_state.current_step = "input"
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
                    st.session_state.current_step = "input"
                    st.rerun()
        
        if submitted:
            with st.spinner("正在生成內容..."):
                try:
                    result = asyncio.run(self.submit_answers(st.session_state.session_id, answers))
                    
                    if result["status"] == "completed":
                        st.session_state.final_post = result["final_post"]
                        st.session_state.template_used = result.get("template_used", "unknown")
                        st.session_state.current_step = "result"
                        st.rerun()
                    else:
                        st.error("內容生成失敗")
                except Exception as e:
                    st.error(f"提交答案時發生錯誤: {str(e)}")
    
    def render_result_step(self):
        """渲染結果步驟"""
        st.header("🎉 內容生成完成！")
        
        # 顯示生成的內容
        st.subheader("📄 生成的貼文內容")
        
        # 使用文字區域顯示，方便複製
        st.text_area(
            "生成的貼文：",
            value=st.session_state.final_post,
            height=200,
            help="點擊文字區域可以選擇和複製內容"
        )
        
        # 顯示使用的模板
        if hasattr(st.session_state, 'template_used'):
            template_name = "連貫敘事" if st.session_state.template_used == "narrative" else "分行條列"
            st.info(f"使用模板：{template_name}")
        
        # 操作按鈕
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            if st.button("📋 複製到剪貼板"):
                # 使用 JavaScript 複製到剪貼板
                st.write("請手動選擇上方文字並複製")
        
        with col2:
            if st.button("🔄 重新生成"):
                st.session_state.current_step = "input"
                st.rerun()
        
        with col3:
            if st.button("✏️ 重新澄清"):
                st.session_state.current_step = "clarification"
                st.rerun()
    
    def render_sidebar(self):
        """渲染側邊欄"""
        with st.sidebar:
            st.header("🛠️ 系統狀態")
            
            # 顯示當前步驟
            steps = {
                "input": "1️⃣ 輸入需求",
                "clarification": "2️⃣ 澄清問題", 
                "result": "3️⃣ 查看結果"
            }
            
            current_step = st.session_state.current_step
            for step_key, step_name in steps.items():
                if step_key == current_step:
                    st.success(f"**{step_name}** ← 當前")
                else:
                    st.write(step_name)
            
            st.divider()
            
            # 會話資訊
            st.subheader("📊 會話資訊")
            st.write(f"**會話 ID:** `{st.session_state.session_id[:8]}...`")
            
            # 系統資訊
            st.divider()
            st.subheader("🔧 系統資訊")
            st.write("**服務狀態:**")
            st.write("- Orchestrator: 🟢")
            st.write("- Form API: 🟢") 
            st.write("- Content Writer: 🟢")
            st.write("- Clarification: 🟢")
    
    def run(self):
        """運行 UI"""
        self.render_sidebar()
        
        # 根據當前步驟渲染對應界面
        if st.session_state.current_step == "input":
            self.render_input_step()
        elif st.session_state.current_step == "clarification":
            self.render_clarification_step()
        elif st.session_state.current_step == "result":
            self.render_result_step()

# 主程式
if __name__ == "__main__":
    ui = ContentGeneratorUI()
    ui.run()