"""
批量分析組件 - 從 analyzer_component.py 拆分出來
負責批量結構分析的所有UI功能
"""

import streamlit as st
import json
import requests
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any


class BatchAnalysisComponent:
    """批量分析UI組件"""
    
    def __init__(self):
        # 批量摘要保存位置（沿用單篇的目錄與索引規則）
        self.analysis_results_dir = Path("storage") / "analysis_results"
        self.analysis_results_dir.mkdir(parents=True, exist_ok=True)
        self.analysis_index_file = self.analysis_results_dir / "analysis_index.json"
        # 會話級暫存，避免摘要被覆蓋
        if 'batch_summaries' not in st.session_state:
            st.session_state.batch_summaries = {}  # key: pattern_name -> {summary_markdown, structure_guide, samples}
    
    def render_batch_analysis_system(self):
        """渲染批量分析系統"""
        # 初始化批量分析狀態
        if 'batch_analysis_state' not in st.session_state:
            st.session_state.batch_analysis_state = {
                'status': 'idle',  # idle, loading_users, analyzing, showing_results
                'selected_user': None,
                'sort_method': 'likes',
                'post_count': 25,
                'current_step': 0,
                'analysis_results': None,
                'error_message': None
            }
        # 首次進入頁面時自動載入一次用戶列表
        if not st.session_state.get('batch_auto_loaded') and st.session_state.batch_analysis_state.get('status') == 'idle':
            st.session_state.batch_auto_loaded = True
            st.session_state.batch_analysis_state['status'] = 'loading_users'
            # 直接執行載入流程（內部會在完成後進行 rerun）
            self._render_batch_loading_users()
            return
        
        state = st.session_state.batch_analysis_state
        
        if state['status'] == 'idle':
            self._render_batch_input_section()
        elif state['status'] == 'loading_users':
            self._render_batch_loading_users()
        elif state['status'] == 'analyzing':
            self._render_batch_analyzing_progress()
        elif state['status'] == 'showing_results':
            self._render_batch_results()
        elif state['status'] == 'error':
            self._render_batch_error()
    
    def _render_batch_input_section(self):
        """渲染批量分析輸入區域"""
        st.subheader("🎭 從 Playwright 爬蟲導入")
        
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.markdown("**📊 數據來源**")
            st.info("從 Playwright 爬蟲已入庫的數據中選擇用戶進行批量分析（🚀 實時爬蟲作為備用）")
            
            if st.button("🔄 刷新用戶", key="refresh_crawled_users"):
                st.session_state.batch_analysis_state['status'] = 'loading_users'
                st.rerun()
            
            # 如果已有用戶列表，顯示選擇器
            if 'available_users' in st.session_state and st.session_state.available_users:
                selected_user = st.selectbox(
                    "選擇要分析的用戶",
                    options=st.session_state.available_users,
                    key="batch_user_selector"
                )
                st.session_state.batch_analysis_state['selected_user'] = selected_user
            
            # 排序方式
            sort_method = st.selectbox(
                "排序方式",
                options=["views", "likes", "comments", "reposts", "shares", "score"],
                format_func=lambda x: {
                    "views": "瀏覽數",
                    "likes": "按讚數",
                    "comments": "留言數",
                    "reposts": "轉發數",
                    "shares": "分享數",
                    "score": "計算分數",
                }[x],
                key="batch_sort_method"
            )
            st.session_state.batch_analysis_state['sort_method'] = sort_method
            
            # 引用數量
            post_count = st.selectbox(
                "引用貼文數量",
                options=[25, 50, 100],
                key="batch_post_count"
            )
            st.session_state.batch_analysis_state['post_count'] = post_count
        
        with col2:
            st.markdown("**🎯 分析設定**")
            st.markdown("""
            **批量結構分析說明：**
            - 智能識別多種貼文結構模式
            - 生成通用創作模板
            - 適用於AI貼文創作指導
            """)
            
            # 分析預覽
            if st.session_state.batch_analysis_state['selected_user']:
                user = st.session_state.batch_analysis_state['selected_user']
                sort_method_text = {"likes": "按讚數", "views": "瀏覽數", "score": "總和分數"}[sort_method]
                preview_text = f"""
                **預覽設定**
                - 用戶：{user}
                - 排序：{sort_method_text}
                - 數量：{post_count} 篇
                - 預期模式：5-10 組結構分析
                """
                st.success(preview_text)
        
        # 快速通道（左，主色） + 開始分析（右，次色）
        if st.session_state.batch_analysis_state['selected_user']:
            st.markdown("---")
            col_quick, col_run = st.columns(2)
            with col_quick:
                if st.button("⚡ 快速通道", type="primary", use_container_width=True):
                    self._run_quick_channel_batch()
            with col_run:
                if st.button("🚀 開始批量結構分析", use_container_width=True):
                    self._start_batch_analysis()
        else:
            st.markdown("---")
            st.info("👆 請先載入並選擇要分析的用戶")
    
    def _render_batch_loading_users(self):
        """渲染載入用戶狀態"""
        with st.spinner("🔍 正在載入已爬取的用戶列表..."):
            try:
                # 從後端獲取真實用戶列表
                api_url = "http://localhost:8007/available-users"
                resp = requests.get(api_url, timeout=15)
                if resp.status_code == 200:
                    data = resp.json() if resp.text else {"users": []}
                    users = data.get("users", [])
                    st.session_state.available_users = users
                    st.session_state.batch_analysis_state['status'] = 'idle'
                    st.success(f"✅ 已載入 {len(users)} 個可用用戶")
                    st.rerun()
                else:
                    st.session_state.batch_analysis_state['status'] = 'error'
                    st.session_state.batch_analysis_state['error_message'] = f"用戶列表API錯誤: HTTP {resp.status_code}"
                    st.rerun()
                
            except Exception as e:
                st.session_state.batch_analysis_state['status'] = 'error'
                st.session_state.batch_analysis_state['error_message'] = f"載入用戶失敗: {str(e)}"
                st.rerun()
    
    def _start_batch_analysis(self):
        """開始批量分析"""
        st.session_state.batch_analysis_state['status'] = 'analyzing'
        st.session_state.batch_analysis_state['current_step'] = 0
        st.rerun()
    
    def _render_batch_analyzing_progress(self):
        """渲染批量分析進度"""
        st.subheader("🔬 批量結構分析進行中")
        
        state = st.session_state.batch_analysis_state
        user = state['selected_user']
        sort_method = state['sort_method']
        post_count = state['post_count']
        
        # 顯示分析信息
        st.info(f"🔍 正在分析用戶 **{user}** 的 **{post_count}** 篇貼文（按 **{sort_method}** 排序）")
        
        # 進度條和步驟說明
        steps = ["🔍 結構模式識別", "📋 創作模板生成"]
        current_step = state.get('current_step', 0)
        
        # 進度條
        progress_percentage = (current_step + 1) / len(steps)
        st.progress(progress_percentage)
        st.write(f"進度: {current_step + 1}/{len(steps)} - {steps[current_step] if current_step < len(steps) else '完成'}")
        
        # 步驟詳情
        for i, step_name in enumerate(steps):
            col1, col2, col3 = st.columns([1, 4, 1])
            with col2:
                if i <= current_step:
                    if i == 0:  # 假設正在執行第一步
                        st.markdown(f"""
                        <div style="padding: 10px; border-left: 4px solid #1f77b4; background-color: #e8f4fd; margin: 5px 0;">
                        <strong>🔄 {step_name}</strong> - 進行中
                        </div>
                        """, unsafe_allow_html=True)
                        st.write("- 🧠 分析語料庫特徵")
                        st.write("- 🎯 動態生成適用模式")
                        st.write("- 📊 智能分組貼文結構")
                    elif i == 1:
                        st.markdown(f"""
                        <div style="padding: 10px; border-left: 4px solid #2ca02c; background-color: #e8f5e8; margin: 5px 0;">
                        <strong>✅ {step_name}</strong> - 已完成
                        </div>
                        """, unsafe_allow_html=True)
                        st.write("- 🎨 生成通用結構模板")
                        st.write("- 📝 產出創作指導規則")
                        st.write("- 🤖 適配AI寫作需求")
                else:
                    st.write(f"⏸️ {step_name} - 等待中")
        
        # 真實分析過程進度更新
        import time
        time.sleep(1)  # 短暫等待UI更新
        
        # 自動推進步驟
        if current_step < len(steps):
            st.session_state.batch_analysis_state['current_step'] += 1
            
            if current_step + 1 >= len(steps):
                # 分析完成，觸發結果模擬
                self._trigger_batch_analysis()
                st.session_state.batch_analysis_state['status'] = 'showing_results'
            
            st.rerun()
    
    def _trigger_batch_analysis(self):
        """觸發批量分析 - 調用真實後端API"""
        try:
            import requests
            
            # 獲取分析參數
            state = st.session_state.batch_analysis_state
            username = state.get('selected_user', 'unknown')
            post_count = state.get('post_count', 25)
            sort_method = state.get('sort_method', 'likes')
            
            # 調用後端批量分析API
            api_url = "http://localhost:8007/batch-structure-analyze"
            payload = {
                "username": username,
                "post_count": post_count,
                "sort_method": sort_method
            }
            
            # 顯示調用信息
            with st.spinner("🔄 正在調用智能分析API..."):
                response = requests.post(api_url, json=payload, timeout=120)
            
            if response.status_code == 200:
                result = response.json()
                st.session_state.batch_analysis_state['analysis_results'] = result
                st.success("✅ 智能分析完成！")
            elif response.status_code == 404:
                st.error(f"❌ 未找到用戶 {username} 的貼文數據")
                self._set_error_state(f"用戶 {username} 無貼文數據")
            else:
                st.error(f"❌ API調用失敗: {response.status_code}")
                self._set_error_state(f"API錯誤: {response.status_code}")
                
        except requests.exceptions.ConnectionError:
            st.error("❌ 無法連接到分析服務")
            self._set_error_state("無法連接到後端服務")
        except requests.exceptions.Timeout:
            st.error("❌ 分析超時")
            self._set_error_state("分析超時")
        except Exception as e:
            st.error(f"❌ 分析過程出錯: {e}")
            self._set_error_state(f"未知錯誤: {e}")

    def _run_quick_channel_batch(self):
        """快速通道：一鍵完成 批量分析→每個模板自動生成摘要→自動保存至引用清單。"""
        try:
            state = st.session_state.batch_analysis_state
            username = state.get('selected_user')
            post_count = state.get('post_count', 25)
            sort_method = state.get('sort_method', 'likes')
            if not username:
                st.error("❌ 請先選擇用戶")
                return
            with st.spinner("⚡ 正在執行快速通道：批量分析中..."):
                api_url = "http://localhost:8007/batch-structure-analyze"
                payload = {"username": username, "post_count": post_count, "sort_method": sort_method}
                resp = requests.post(api_url, json=payload, timeout=180)
                if resp.status_code != 200:
                    st.error(f"❌ 批量分析失敗：HTTP {resp.status_code}")
                    st.code(resp.text)
                    return
                result = resp.json()
            # 對每個模板自動生成摘要並保存
            templates = result.get('structure_templates', []) or []
            saved = 0
            errors = 0
            with st.spinner("🧠 正在為每個模板生成摘要並保存..."):
                for tpl in templates:
                    pattern_name = tpl.get('pattern_name', 'Unknown')
                    st.write(f"處理模板：{pattern_name} ...")
                    st.experimental_rerun if False else None  # 保持語義，無動作
                    st.flush_container() if hasattr(st, 'flush_container') else None
                    structure_template = tpl.get('structure_template', {})
                    guide = structure_template.get('structure_guide', {})
                    samples = structure_template.get('all_samples') or structure_template.get('samples') or []
                    if not samples:
                        errors += 1
                        continue
                    try:
                        summary_api = "http://localhost:8007/batch-summary"
                        req = {"pattern_name": pattern_name, "structure_guide": guide, "samples": [s.get('content','') for s in samples]}
                        sresp = requests.post(summary_api, json=req, timeout=180)
                        if sresp.status_code != 200:
                            errors += 1
                            continue
                        summary_md = sresp.json().get('summary_markdown', '')
                        # 保存到引用清單（沿用批量保存）
                        payload_save = {"summary_markdown": summary_md, "structure_guide": guide, "samples": samples}
                        aid = self._save_batch_summary(pattern_name, payload_save)
                        if aid:
                            saved += 1
                    except Exception:
                        errors += 1
                        continue
            if saved:
                st.success(f"✅ 快速通道完成！已保存 {saved} 個模板摘要至引用清單。")
                st.balloons()
            if errors:
                st.warning(f"⚠️ 有 {errors} 個模板摘要未成功生成或保存。")
        except Exception as e:
            st.error(f"❌ 快速通道失敗：{e}")
    
    def _set_error_state(self, error_message: str):
        """設置錯誤狀態"""
        st.session_state.batch_analysis_state['analysis_results'] = {
            "status": "error",
            "message": error_message,
            "username": st.session_state.batch_analysis_state.get('selected_user', 'unknown'),
            "pattern_count": 0,
            "total_posts": st.session_state.batch_analysis_state.get('post_count', 0),
            "analysis_type": "error",
            "pattern_analysis": {"identified_patterns": []},
            "structure_templates": []
        }
    
    def _render_batch_results(self):
        """渲染批量分析結果 - 分步驟展示"""
        st.subheader("📊 批量結構分析結果")
        
        results = st.session_state.batch_analysis_state['analysis_results']
        user = results['username']
        pattern_count = results['pattern_count']
        total_posts = results['total_posts']
        
        # 結果概覽
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("分析用戶", user)
        with col2:
            st.metric("貼文數量", total_posts)
        with col3:
            st.metric("識別模式", pattern_count)
        
        # 檢查是否為前端占位符
        if results.get("status") == "需要後端服務":
            st.warning("⚠️ " + results.get("message", "需要後端服務"))
            st.info("💡 這是前端UI展示，真實分析需要啟動後端服務")
        else:
            # 顯示真實結果
            if pattern_count > 0:
                # 分頁顯示結果
                tab1, tab2 = st.tabs(["🔍 結構模式", "📋 創作模板"])
                
                with tab1:
                    self._render_pattern_analysis(results['pattern_analysis'])
                
                with tab2:
                    self._render_structure_templates(results['structure_templates'])

                # 第三個分頁：🧠 分析摘要
                tab3, = st.tabs(["🧠 分析摘要"])
                with tab3:
                    self._render_batch_summary_tab()
        
        # 控制按鈕
        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 重新分析", key="restart_batch_analysis"):
                st.session_state.batch_analysis_state['status'] = 'idle'
                st.session_state.batch_analysis_state['current_step'] = 0
                st.rerun()
        with col2:
            if st.button("📥 導出結果", key="export_batch_results"):
                self._export_batch_results()
    
    def _render_pattern_analysis(self, pattern_analysis):
        """渲染模式分析結果"""
        st.subheader("🔍 識別的結構模式")
        
        patterns = pattern_analysis.get('identified_patterns', [])
        for pattern in patterns:
            with st.expander(f"📋 {pattern['pattern_name']}", expanded=True):
                st.write("**模式特徵：**")
                for char in pattern.get('characteristics', []):
                    st.write(f"• {char}")
                
                st.write(f"**包含貼文：** {pattern.get('post_count', 0)} 篇")
    
    def _render_structure_templates(self, structure_templates):
        """渲染結構模板結果"""
        st.subheader("📋 創作模板")
        
        for template in structure_templates:
            pattern_name = template.get('pattern_name', 'Unknown Pattern')
            
            with st.expander(f"📝 {pattern_name} - 創作模板", expanded=True):
                self._render_universal_template(template)
                # 分析摘要按鈕（多篇）
                if st.button("🧠 分析摘要", key=f"analyze_summary_{pattern_name}"):
                    st.session_state.batch_summary_request = {
                        "pattern_name": pattern_name,
                        "structure_template": template.get('structure_template', {}),
                        # 若有 all_samples 則使用完整覆蓋；否則沿用 samples
                        "use_all_samples": True
                    }
                    st.success("✅ 已準備摘要資料，請切換到『🧠 分析摘要』分頁。")
    
    def _render_universal_template(self, template):
        """渲染通用模板"""
        structure_template = template.get('structure_template', {})
        confidence = template.get('confidence')
        structure_guide = structure_template.get('structure_guide', {})
        creation_guidance = structure_template.get('creation_guidance', {})
        applicability = structure_template.get('applicability', {})
        paragraph_steps = structure_template.get('paragraph_steps', [])
        macro_blueprint = structure_guide.get('macro_blueprint', {}) if isinstance(structure_guide, dict) else {}
        
        # 顯示信心度
        if confidence is not None:
            st.caption(f"信心度：{confidence:.2f}")

        # 結構指南
        if structure_guide:
            st.markdown("**🏗️ 結構指南**")
            
            # 檢查是否有檢測特徵（模擬模式）
            if 'detected_features' in structure_guide:
                st.write("**檢測到的特徵：**")
                for feature in structure_guide['detected_features']:
                    st.write(f"• {feature}")
                
                if 'applicability' in structure_guide:
                    st.info(structure_guide['applicability'])
            else:
                # 正常模板結構
                for key, value in structure_guide.items():
                    if key == 'macro_blueprint' and isinstance(value, dict):
                        st.write("**macro_blueprint：**")
                        # 展開 macro_blueprint 的重要子項
                        chain = value.get('structure_chain_example')
                        if chain:
                            st.write("  - structure_chain_example:")
                            for item in chain:
                                st.write(f"    • {item}")
                        for subkey in ['micro_arc', 'tension', 'completeness']:
                            if subkey in value and value[subkey]:
                                st.write(f"  - {subkey}: {value[subkey]}")
                        continue
                    if isinstance(value, dict):
                        st.write(f"**{key}:**")
                        for subkey, subvalue in value.items():
                            st.write(f"  - {subkey}: {subvalue}")
                    elif isinstance(value, list):
                        st.write(f"**{key}:**")
                        for item in value:
                            st.write(f"  • {item}")
                    else:
                        st.write(f"**{key}:** {value}")
        
        # 段落步驟（新版）
        if isinstance(paragraph_steps, list) and paragraph_steps:
            st.markdown("**🧱 段落/句群步驟 (paragraph_steps)**")
            for i, step in enumerate(paragraph_steps, 1):
                with st.expander(f"步驟 {i}", expanded=False):
                    if isinstance(step, dict):
                        func = step.get('功能') or step.get('function')
                        if func:
                            st.write(f"- 功能: {func}")
                        std = step.get('標準寫法') or step.get('standard')
                        if std:
                            st.write(f"- 標準寫法: {std}")
                        connectors = step.get('連貫語') or step.get('connectors')
                        if isinstance(connectors, list) and connectors:
                            st.write("- 連貫語:")
                            st.write("  " + "、".join(connectors))
                        demo = step.get('示例片段') or step.get('example')
                        if demo:
                            st.code(demo)

        # 創作指導
        if creation_guidance:
            st.markdown("**📝 創作指導**")
            
            if 'writing_steps' in creation_guidance:
                st.write("**寫作步驟：**")
                for i, step in enumerate(creation_guidance['writing_steps'], 1):
                    st.write(f"{i}. {step}")
            
            if 'style_constraints' in creation_guidance:
                st.write("**風格限制：**")
                for constraint in creation_guidance['style_constraints']:
                    st.write(f"• {constraint}")
            
            if 'common_pitfalls' in creation_guidance:
                st.write("**常見陷阱：**")
                for pitfall in creation_guidance['common_pitfalls']:
                    st.write(f"⚠️ {pitfall}")
            
            if 'notes' in creation_guidance:
                st.info(f"💡 {creation_guidance['notes']}")

        # 適用性（新版）
        if isinstance(applicability, dict) and (applicability.get('適用場景') or applicability.get('不適用')):
            st.markdown("**🎯 適用性**")
            suitable = applicability.get('適用場景') or []
            unsuitable = applicability.get('不適用') or []
            if suitable:
                st.write("- 適用場景：")
                for item in suitable:
                    st.write(f"  • {item}")
            if unsuitable:
                st.write("- 不適用：")
                for item in unsuitable:
                    st.write(f"  • {item}")

    def _render_batch_summary_tab(self):
        """渲染多篇摘要結果分頁"""
        req = st.session_state.get('batch_summary_request')
        if not req:
            st.info("點擊某個模板中的『🧠 分析摘要』以生成摘要。")
            return
        pattern = req.get('pattern_name', 'Unknown')
        tpl = req.get('structure_template', {})
        guide = tpl.get('structure_guide', {})
        samples = []
        if st.session_state.get('batch_summary_request', {}).get('use_all_samples'):
            samples = tpl.get('all_samples') or tpl.get('samples', [])
        else:
            samples = tpl.get('samples', [])
        if not samples:
            st.warning("此模板缺少樣本內容，無法生成摘要。")
            return
        st.write(f"**目標模板：** {pattern}")
        st.write("**樣本數：**", len(samples))
        with st.expander("查看樣本清單", expanded=False):
            for s in samples:
                content = s.get('content') or ''
                st.code(content[:300] + ("..." if len(content) > 300 else ""))
        # 調用後端批量摘要 API
        if st.button("🚀 生成多篇摘要", key="run_batch_summary"):
            try:
                api_url = "http://localhost:8007/batch-summary"
                payload = {
                    "pattern_name": pattern,
                    "structure_guide": guide,
                    "samples": [s.get('content','') for s in samples]
                }
                resp = requests.post(api_url, json=payload, timeout=120)
                if resp.status_code == 200:
                    data = resp.json()
                    st.success("✅ 摘要已生成")
                    summary_md = data.get('summary_markdown', '')
                    st.session_state.batch_summaries[pattern] = {
                        "summary_markdown": summary_md,
                        "structure_guide": guide,
                        "samples": samples
                    }
                    st.markdown(summary_md)
                    if st.button("💾 保存分析", key=f"save_batch_summary_{pattern}"):
                        self._save_batch_summary(pattern, st.session_state.batch_summaries[pattern])
                        st.success("✅ 已保存到分析索引，可在『智能撰寫』的引用選項中看到。")
                else:
                    st.error(f"❌ 摘要服務錯誤: {resp.status_code} {resp.text}")
            except Exception as e:
                st.error(f"❌ 生成摘要失敗: {e}")

        # 已生成的摘要清單（本次會話）
        if st.session_state.batch_summaries:
            st.markdown("---")
            st.subheader("🗂️ 已生成的摘要（本次會話）")
            for ptn, payload in st.session_state.batch_summaries.items():
                with st.expander(f"{ptn}", expanded=False):
                    st.markdown(payload.get('summary_markdown', ''))
                    if st.button("💾 保存分析", key=f"save_batch_summary_list_{ptn}"):
                        self._save_batch_summary(ptn, payload)
                        st.success("✅ 已保存到分析索引。")

    # ======= 保存 / 索引 =======
    def _load_analysis_index(self) -> Dict[str, Any]:
        try:
            if self.analysis_index_file.exists():
                with open(self.analysis_index_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return {"analyses": []}

    def _save_analysis_index(self, index_data: Dict[str, Any]):
        try:
            with open(self.analysis_index_file, 'w', encoding='utf-8') as f:
                json.dump(index_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            st.error(f"❌ 保存索引失敗: {e}")

    def _save_batch_summary(self, pattern_name: str, payload: Dict[str, Any]) -> str:
        """保存批量模板摘要到分析結果目錄，並更新索引。"""
        try:
            import uuid
            analysis_id = str(uuid.uuid4())[:8]
            # 來源用戶名（優先從分析結果，其次從目前選擇）
            # 來源用戶名（優先從分析結果，其次從目前選擇）
            state = getattr(st.session_state, 'batch_analysis_state', None)
            username = 'unknown'
            sort_method = 'likes'
            post_count = 25
            if isinstance(state, dict):
                ar = state.get('analysis_results') or {}
                if isinstance(ar, dict):
                    username = ar.get('username', username)
                sort_method = state.get('sort_method', sort_method)
                post_count = state.get('post_count', post_count)
                if username == 'unknown':
                    username = state.get('selected_user', username)
            # 產生 display 名稱與檔名：{pattern}_@{username}_{likes|views|score}_{count}
            sort_slug = str(sort_method).lower()
            # 檔名安全處理（保留中文，替換空白與斜線）
            safe_pattern = str(pattern_name).replace(' ', '_').replace('/', '_').replace('\\', '_')
            display_name = f"{pattern_name}_@{username}_{sort_slug}_{post_count}"
            filename = f"{safe_pattern}_@{username}_{sort_slug}_{post_count}_{analysis_id}.json"
            file_path = self.analysis_results_dir / filename
            # 保險：payload 為空時置為空 dict
            payload = payload or {}
            created_at = datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None).isoformat()
            record = {
                "type": "batch_summary",
                "analysis_id": analysis_id,
                "pattern_name": pattern_name,
                "username": username,
                "structure_guide": (payload.get('structure_guide') or {}),
                "sample_count": len(payload.get('samples') or []),
                "summary_markdown": (payload.get('summary_markdown') or ''),
                "created_at": created_at
            }
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            index_data = self._load_analysis_index()
            index_entry = {
                "analysis_id": analysis_id,
                "display_name": display_name,
                "username": username,
                "pattern_name": pattern_name,
                "file_path": filename,
                "type": "batch_summary",
                "created_at": record["created_at"]
            }
            index_data.setdefault("analyses", []).append(index_entry)
            self._save_analysis_index(index_data)
            return analysis_id
        except Exception as e:
            st.error(f"❌ 保存分析失敗: {e}")
            return None
    
    def _render_batch_error(self):
        """渲染批量分析錯誤"""
        st.error("❌ 批量分析過程中發生錯誤")
        
        error_msg = st.session_state.batch_analysis_state.get('error_message', '未知錯誤')
        st.error(f"錯誤詳情：{error_msg}")
        
        if st.button("🔄 重試", key="retry_batch_analysis"):
            st.session_state.batch_analysis_state['status'] = 'idle'
            st.session_state.batch_analysis_state['error_message'] = None
            st.rerun()
    
    def _export_batch_results(self):
        """導出批量分析結果"""
        try:
            results = st.session_state.batch_analysis_state['analysis_results']
            
            import json
            
            # 準備導出數據
            export_data = {
                "export_timestamp": datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None).isoformat(),
                "analysis_results": results
            }
            
            json_str = json.dumps(export_data, indent=2, ensure_ascii=False)
            
            st.download_button(
                label="📥 下載分析結果 (JSON)",
                data=json_str,
                file_name=f"batch_analysis_{results['username']}_{datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json"
            )
            
        except Exception as e:
            st.error(f"導出失敗: {str(e)}")
