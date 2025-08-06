#!/usr/bin/env python3
"""
臨時腳本 - 添加監控方法到 playwright_crawler_component_v2.py
"""

# 監控方法的代碼
monitoring_method = '''
    def _render_monitoring(self):
        """渲染任務監控頁面 - 用於超時後的任務恢復"""
        st.subheader("🔍 後台任務監控")
        st.info("⏰ 由於請求超時，已切換到後台任務監控模式。任務仍在後台繼續執行...")
        
        task_id = st.session_state.get('playwright_task_id')
        if not task_id:
            st.error("❌ 無法找到任務ID")
            if st.button("🔙 返回設定"):
                st.session_state.playwright_crawl_status = "idle"
                st.rerun()
            return
        
        # 顯示任務信息
        col1, col2 = st.columns(2)
        with col1:
            st.metric("任務ID", f"{task_id[:8]}...")
        with col2:
            monitoring_duration = time.time() - st.session_state.get('playwright_monitoring_start', time.time())
            st.metric("監控時間", f"{monitoring_duration:.0f}秒")
        
        # 從 Redis 或進度管理器獲取實際進度
        try:
            progress_data = self.progress_manager.get_progress(task_id, prefer_redis=True)
            
            if progress_data:
                stage = progress_data.get("stage", "unknown")
                progress = progress_data.get("progress", 0)
                username = progress_data.get("username", "unknown")
                
                # 顯示當前狀態
                st.write("### 📊 當前狀態")
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric("用戶", username)
                with col2:
                    st.metric("階段", stage)
                with col3:
                    st.metric("進度", f"{progress:.1f}%")
                
                # 進度條
                st.progress(progress / 100.0 if progress > 0 else 0.0)
                
                # 檢查任務是否完成
                if stage == "completed":
                    st.success("🎉 任務已完成！")
                    
                    # 設定結果並切換到結果頁面
                    final_data = progress_data.get("final_data", {})
                    if final_data:
                        st.session_state.playwright_final_data = final_data
                        st.session_state.playwright_crawl_status = "completed"
                        st.rerun()
                    else:
                        st.warning("任務完成但無法獲取結果數據")
                
                elif "error" in stage:
                    st.error(f"❌ 任務執行錯誤: {progress_data.get('error', 'Unknown error')}")
                    st.session_state.playwright_crawl_status = "error"
                    st.session_state.playwright_error_msg = progress_data.get('error', 'Unknown error')
                    st.rerun()
                    
                # 顯示詳細日誌（如果有）
                log_messages = progress_data.get("log_messages", [])
                if log_messages:
                    with st.expander("📋 任務日誌", expanded=False):
                        recent_logs = log_messages[-20:] if len(log_messages) > 20 else log_messages
                        st.code('\\n'.join(recent_logs), language='text')
            else:
                st.warning("⚠️ 無法獲取任務進度，任務可能已完成或發生錯誤")
                
                # 提供手動選項
                if st.button("🔄 重新嘗試獲取進度"):
                    st.rerun()
                    
        except Exception as e:
            st.error(f"❌ 獲取進度時發生錯誤: {str(e)}")
        
        # 控制按鈕
        st.write("### 🎛️ 控制選項")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("📋 任務管理"):
                st.session_state.playwright_crawl_status = "task_manager"
                st.rerun()
        
        with col2:
            if st.button("🔙 返回設定"):
                st.session_state.playwright_crawl_status = "idle"
                st.rerun()
        
        with col3:
            if st.button("🗑️ 停止監控"):
                # 不刪除任務，只是停止監控
                st.session_state.playwright_crawl_status = "idle"
                st.info("已停止監控，任務仍在後台運行。可在任務管理中查看。")
                time.sleep(2)
                st.rerun()
'''

print("監控方法代碼已準備好，需要手動添加到文件中")
print("請在 _render_progress 方法之後添加這個方法")