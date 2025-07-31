"""
分析組件
用於選擇爬蟲結果並進行貼文分析
"""

import streamlit as st
import httpx
import json
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional

from common.crawler_storage import get_crawler_storage


class AnalyzerComponent:
    def __init__(self):
        self.analyzer_url = "http://localhost:8007/analyze"
        self.storage = get_crawler_storage()
    
    def render(self):
        """渲染分析界面"""
        st.header("📊 貼文內容分析")
        st.markdown("基於 Clarification 問卷方向，深度分析爬蟲結果，提供風格、主題和改寫建議。")
        
        # 獲取可用的爬蟲結果
        crawler_results = self.storage.get_crawler_results_list()
        
        if not crawler_results:
            st.warning("⚠️ 沒有找到爬蟲結果數據")
            st.info("請先使用 🕷️ Threads 內容爬蟲 來獲取貼文數據")
            return
        
        # 顯示爬蟲結果選擇
        self._render_result_selection(crawler_results)
        
        # 根據狀態顯示不同界面
        analysis_status = st.session_state.get('analysis_status', 'idle')
        
        if analysis_status == 'running':
            self._render_analysis_progress()
        elif analysis_status == 'completed':
            self._render_analysis_results()
        elif analysis_status == 'error':
            st.error("❌ 分析執行失敗，請檢查日誌")
            self._render_analysis_logs()
    
    def _render_result_selection(self, crawler_results: List[Dict[str, Any]]):
        """渲染爬蟲結果選擇界面"""
        st.subheader("📂 選擇要分析的爬蟲結果")
        
        if not crawler_results:
            return
        
        # 創建選擇表格
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            st.write("**帳號**")
        with col2:
            st.write("**爬取時間**")
        with col3:
            st.write("**貼文數量**")
        
        st.markdown("---")
        
        selected_batch_id = None
        
        for i, result in enumerate(crawler_results[:10]):  # 只顯示最近10個結果
            col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
            
            with col1:
                st.write(f"@{result['username']}")
            
            with col2:
                crawled_time = datetime.fromisoformat(result['crawled_at'].replace('Z', '+00:00'))
                st.write(crawled_time.strftime('%m-%d %H:%M'))
            
            with col3:
                st.write(f"{result['posts_count']} 篇")
            
            with col4:
                button_key = f"analyze_btn_{result['batch_id']}"
                if st.button("🔍 分析", key=button_key, use_container_width=True):
                    selected_batch_id = result['batch_id']
        
        # 如果有選擇，啟動分析
        if selected_batch_id:
            self._start_analysis(selected_batch_id)
    
    def _start_analysis(self, batch_id: str):
        """啟動分析"""
        # 載入爬蟲結果數據
        crawler_data = self.storage.get_crawler_result(batch_id)
        if not crawler_data:
            st.error(f"❌ 找不到批次 ID {batch_id} 的爬蟲結果")
            return
        
        # 初始化分析狀態
        st.session_state.analysis_status = 'running'
        st.session_state.analysis_batch_id = batch_id
        st.session_state.analysis_username = crawler_data['username']
        st.session_state.analysis_logs = []
        st.session_state.analysis_result = None
        
        st.session_state.analysis_logs.append(f"🚀 開始分析 @{crawler_data['username']} 的 {len(crawler_data['posts_data'])} 篇貼文...")
        
        # 執行分析
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._execute_analysis(crawler_data))
        except Exception as e:
            st.session_state.analysis_logs.append(f"❌ 分析執行失敗: {e}")
            st.session_state.analysis_status = 'error'
        finally:
            st.rerun()
    
    async def _execute_analysis(self, crawler_data: Dict[str, Any]):
        """執行分析請求"""
        try:
            # 準備請求數據
            request_data = {
                "username": crawler_data['username'],
                "posts_data": crawler_data['posts_data'][:10],  # 只分析前10篇
                "batch_id": crawler_data['batch_id']
            }
            
            st.session_state.analysis_logs.append("📡 正在連接分析服務...")
            
            timeout = httpx.Timeout(180.0)  # 3分鐘超時
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(self.analyzer_url, json=request_data)
                
                if response.status_code != 200:
                    error_msg = f"❌ 分析服務請求失敗，狀態碼: {response.status_code}"
                    st.session_state.analysis_logs.append(error_msg)
                    st.session_state.analysis_logs.append(f"錯誤內容: {response.text}")
                    st.session_state.analysis_status = 'error'
                    return
                
                # 解析分析結果
                try:
                    analysis_result = response.json()
                    st.session_state.analysis_result = analysis_result
                    st.session_state.analysis_status = 'completed'
                    st.session_state.analysis_logs.append("✅ 分析完成！")
                    
                except json.JSONDecodeError as e:
                    st.session_state.analysis_logs.append(f"❌ 無法解析分析結果 JSON: {e}")
                    st.session_state.analysis_status = 'error'
        
        except httpx.ConnectError:
            error_msg = f"連線錯誤: 無法連線至分析服務 {self.analyzer_url}。請確認分析 Agent 是否正在運行。"
            st.session_state.analysis_logs.append(error_msg)
            st.session_state.analysis_status = 'error'
        except Exception as e:
            st.session_state.analysis_logs.append(f"❌ 分析過程中發生錯誤: {e}")
            st.session_state.analysis_status = 'error'
    
    def _render_analysis_progress(self):
        """渲染分析進度"""
        st.subheader("📊 分析進行中")
        
        username = st.session_state.get('analysis_username', '')
        batch_id = st.session_state.get('analysis_batch_id', '')
        
        st.info(f"🔍 正在分析 @{username} 的貼文內容... (批次: {batch_id[:8]}...)")
        
        # 顯示進度動畫
        with st.spinner("分析中，這可能需要1-2分鐘..."):
            # 顯示分析日誌
            if st.session_state.get('analysis_logs'):
                with st.expander("📋 分析日誌", expanded=True):
                    for log in st.session_state.analysis_logs:
                        st.text(log)
        
        # 自動刷新
        import time
        time.sleep(5)
        st.rerun()
    
    def _render_analysis_results(self):
        """渲染分析結果"""
        st.subheader("📊 分析結果")
        
        result = st.session_state.get('analysis_result')
        if not result:
            st.error("❌ 沒有分析結果數據")
            return
        
        username = result.get('username', '')
        st.success(f"✅ @{username} 的貼文分析已完成")
        
        # 重置按鈕
        if st.button("🔄 重新選擇", use_container_width=True):
            self._reset_analysis()
            st.rerun()
        
        # 顯示分析結果的各個部分
        self._render_analysis_summary(result)
        self._render_top_posts_analysis(result)
        self._render_recommendations(result)
        self._render_rewrite_suggestions(result)
        
        # 下載結果按鈕
        self._render_download_button(result)
    
    def _render_analysis_summary(self, result: Dict[str, Any]):
        """渲染分析摘要"""
        st.subheader("📈 內容分析摘要")
        
        analysis_summary = result.get('analysis_summary', {})
        
        # 基礎指標
        basic_metrics = analysis_summary.get('basic_metrics', {})
        engagement_metrics = basic_metrics.get('engagement_metrics', {})
        content_analysis = basic_metrics.get('content_analysis', {})
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("總貼文數", basic_metrics.get('total_posts', 0))
        
        with col2:
            avg_likes = engagement_metrics.get('avg_likes_per_post', 0)
            st.metric("平均讚數", f"{avg_likes:.0f}")
        
        with col3:
            avg_views = engagement_metrics.get('avg_views_per_post', 0)
            st.metric("平均瀏覽數", f"{avg_views:,.0f}")
        
        with col4:
            avg_length = content_analysis.get('avg_content_length', 0)
            st.metric("平均字數", f"{avg_length:.0f}")
        
        # 內容分析
        content_insights = analysis_summary.get('content_analysis', {})
        if content_insights:
            st.markdown("---")
            st.subheader("🎯 內容深度分析")
            
            # 主題分析
            theme_analysis = content_insights.get('theme_analysis', {})
            if theme_analysis:
                st.markdown("**🏷️ 主題分析**")
                primary_themes = theme_analysis.get('primary_themes', [])
                if primary_themes:
                    st.write(f"主要主題：{', '.join(primary_themes)}")
                
                content_focus = theme_analysis.get('content_focus', '')
                if content_focus:
                    st.write(f"內容重點：{content_focus}")
            
            # 風格分析
            style_analysis = content_insights.get('style_analysis', {})
            if style_analysis:
                st.markdown("**🎨 風格分析**")
                presentation_style = style_analysis.get('presentation_style', '')
                if presentation_style:
                    st.write(f"呈現風格：{presentation_style}")
            
            # 語氣分析
            tone_analysis = content_insights.get('tone_analysis', {})
            if tone_analysis:
                st.markdown("**🗣️ 語氣分析**")
                primary_tone = tone_analysis.get('primary_tone', '')
                emotional_style = tone_analysis.get('emotional_style', '')
                if primary_tone:
                    st.write(f"主要語氣：{primary_tone}")
                if emotional_style:
                    st.write(f"情感風格：{emotional_style}")
    
    def _render_top_posts_analysis(self, result: Dict[str, Any]):
        """渲染高表現貼文分析"""
        st.subheader("🏆 高表現貼文分析")
        
        top_posts_analysis = result.get('top_posts_analysis', [])
        if not top_posts_analysis:
            st.info("沒有高表現貼文分析數據")
            return
        
        for i, post_analysis in enumerate(top_posts_analysis):
            with st.expander(f"🥇 第 {post_analysis.get('ranking', i+1)} 名貼文分析", expanded=i < 2):
                # 貼文內容預覽
                content = post_analysis.get('post_content', '')
                if content:
                    st.markdown(f"**內容預覽：** {content}")
                
                # 表現數據
                metrics = post_analysis.get('metrics', {})
                if metrics:
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("讚數", f"{metrics.get('likes', 0):,}")
                    with col2:
                        st.metric("瀏覽數", f"{metrics.get('views', 0):,}")
                    with col3:
                        st.metric("評論數", metrics.get('comments', 0))
                    with col4:
                        st.metric("分數", f"{metrics.get('score', 0):.1f}")
                
                # 成功因素分析
                success_factors = post_analysis.get('success_factors', {})
                if success_factors:
                    st.markdown("**🎯 成功因素：**")
                    for factor, description in success_factors.items():
                        st.write(f"• **{factor.replace('_', ' ').title()}**: {description}")
                
                # 改進建議
                improvement_suggestions = post_analysis.get('improvement_suggestions', [])
                if improvement_suggestions:
                    st.markdown("**💡 改進建議：**")
                    for suggestion in improvement_suggestions:
                        st.write(f"• {suggestion}")
    
    def _render_recommendations(self, result: Dict[str, Any]):
        """渲染整體建議"""
        st.subheader("🎯 整體策略建議")
        
        recommendations = result.get('recommendations', {})
        if not recommendations:
            st.info("沒有整體建議數據")
            return
        
        # 內容策略
        content_strategy = recommendations.get('content_strategy', {})
        if content_strategy:
            st.markdown("**📝 內容策略**")
            primary_recommendations = content_strategy.get('primary_recommendations', [])
            for rec in primary_recommendations:
                st.write(f"• {rec}")
            
            content_pillars = content_strategy.get('content_pillars', [])
            if content_pillars:
                st.write(f"**內容支柱：** {', '.join(content_pillars)}")
        
        # 互動優化
        engagement_optimization = recommendations.get('engagement_optimization', {})
        if engagement_optimization:
            st.markdown("**🤝 互動優化**")
            best_practices = engagement_optimization.get('best_practices', [])
            for practice in best_practices:
                st.write(f"• {practice}")
        
        # 風格指南
        style_guidelines = recommendations.get('style_guidelines', {})
        if style_guidelines:
            st.markdown("**🎨 風格指南**")
            for guideline, description in style_guidelines.items():
                if description:
                    st.write(f"• **{guideline.replace('_', ' ').title()}**: {description}")
    
    def _render_rewrite_suggestions(self, result: Dict[str, Any]):
        """渲染改寫建議"""
        st.subheader("✍️ 改寫建議")
        
        rewrite_suggestions = result.get('rewrite_suggestions', [])
        if not rewrite_suggestions:
            st.info("沒有改寫建議數據")
            return
        
        for suggestion in rewrite_suggestions:
            suggestion_id = suggestion.get('suggestion_id', 1)
            with st.expander(f"📝 改寫建議 #{suggestion_id}", expanded=suggestion_id == 1):
                # 原始內容
                original_content = suggestion.get('original_content', '')
                if original_content:
                    st.markdown("**原始內容：**")
                    st.write(original_content)
                
                # 分析
                original_analysis = suggestion.get('original_analysis', {})
                if original_analysis:
                    strengths = original_analysis.get('strengths', [])
                    weaknesses = original_analysis.get('weaknesses', [])
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if strengths:
                            st.markdown("**✅ 優點：**")
                            for strength in strengths:
                                st.write(f"• {strength}")
                    
                    with col2:
                        if weaknesses:
                            st.markdown("**⚠️ 可改進處：**")
                            for weakness in weaknesses:
                                st.write(f"• {weakness}")
                
                # 改寫建議
                rewrite_suggestions_detail = suggestion.get('rewrite_suggestions', {})
                if rewrite_suggestions_detail:
                    st.markdown("**💡 改寫建議：**")
                    for suggestion_type, description in rewrite_suggestions_detail.items():
                        if description:
                            st.write(f"• **{suggestion_type.replace('_', ' ').title()}**: {description}")
                
                # 改寫範例
                sample_rewrite = suggestion.get('sample_rewrite', '')
                if sample_rewrite:
                    st.markdown("**✨ 改寫範例：**")
                    st.success(sample_rewrite)
    
    def _render_download_button(self, result: Dict[str, Any]):
        """渲染下載按鈕"""
        st.markdown("---")
        
        # 生成下載文件名
        username = result.get('username', 'unknown')
        analyzed_at = result.get('analyzed_at', datetime.now().isoformat())
        filename = f"analysis_{username}_{analyzed_at[:10]}.json"
        
        # 準備下載數據
        download_data = json.dumps(result, ensure_ascii=False, indent=2, default=str)
        
        col1, col2, col3 = st.columns([1, 1, 1])
        
        with col2:
            st.download_button(
                label="📥 下載完整分析結果",
                data=download_data,
                file_name=filename,
                mime="application/json",
                use_container_width=True
            )
    
    def _render_analysis_logs(self):
        """渲染分析日誌"""
        if st.session_state.get('analysis_logs'):
            with st.expander("📋 分析日誌", expanded=True):
                for log in st.session_state.analysis_logs:
                    st.text(log)
    
    def _reset_analysis(self):
        """重置分析狀態"""
        keys_to_reset = [
            'analysis_status', 'analysis_batch_id', 'analysis_username',
            'analysis_logs', 'analysis_result'
        ]
        for key in keys_to_reset:
            if key in st.session_state:
                del st.session_state[key]