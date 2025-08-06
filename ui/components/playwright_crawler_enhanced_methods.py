"""
Playwright 爬蟲組件的增強方法
包含任務恢復、背景監控等新功能
"""

import streamlit as st
import time
from typing import Dict, Any

def _handle_recovered_task(self):
    """處理從背景恢復的任務"""
    if not hasattr(st.session_state, 'playwright_task_id'):
        st.error("❌ 恢復任務失敗：找不到任務 ID")
        st.session_state.playwright_crawl_status = "idle"
        return
    
    task_id = st.session_state.playwright_task_id
    
    if self.task_recovery:
        # 使用任務恢復組件監控
        if not self.task_recovery.render_task_monitor(task_id):
            # 監控失敗，返回空閒狀態
            st.session_state.playwright_crawl_status = "idle"
            return
    
    # 清除恢復標記
    if hasattr(st.session_state, 'recovered_from_background'):
        del st.session_state.recovered_from_background

def _render_task_manager(self):
    """渲染任務管理頁面"""
    st.header("📋 任務管理中心")
    
    # 返回按鈕
    col_back, col_refresh = st.columns([1, 1])
    with col_back:
        if st.button("← 返回爬蟲設定", key="back_to_setup"):
            st.session_state.playwright_crawl_status = "idle"
            st.rerun()
    
    with col_refresh:
        if st.button("🔄 重新整理", key="refresh_tasks"):
            st.rerun()
    
    st.divider()
    
    if not self.task_recovery:
        st.error("❌ 任務管理功能不可用")
        return
    
    # 渲染任務列表
    self.task_recovery.render_task_list()
    
    st.divider()
    
    # 渲染清理控制
    self.task_recovery.render_cleanup_controls()

def _render_progress_enhanced(self):
    """增強版進度渲染（支援背景任務恢復）"""
    # 檢查是否為恢復的任務
    if (hasattr(st.session_state, 'recovered_from_background') and 
        st.session_state.recovered_from_background):
        
        st.info("📡 這是從背景恢復的任務，正在從 Redis 同步進度...")
        
        # 嘗試從 Redis 獲取最新進度
        if self.progress_manager and hasattr(st.session_state, 'playwright_task_id'):
            task_id = st.session_state.playwright_task_id
            redis_progress = self.progress_manager.read_redis_progress(task_id)
            
            if redis_progress:
                # 更新本地進度顯示
                st.session_state.playwright_progress = redis_progress.get("progress", 0.0)
                st.session_state.playwright_current_work = redis_progress.get("current_work", "")
                
                # 檢查任務是否已完成
                stage = redis_progress.get("stage", "")
                if stage in ("completed", "api_completed"):
                    st.session_state.playwright_crawl_status = "completed"
                    st.session_state.playwright_final_data = redis_progress.get("final_data", {})
                    if hasattr(st.session_state, 'recovered_from_background'):
                        del st.session_state.recovered_from_background
                    st.rerun()
                elif stage == "error":
                    st.session_state.playwright_crawl_status = "error"
                    st.session_state.playwright_error_msg = redis_progress.get("error", "未知錯誤")
                    if hasattr(st.session_state, 'recovered_from_background'):
                        del st.session_state.recovered_from_background
                    st.rerun()
            else:
                st.warning("⚠️ 無法從 Redis 獲取任務進度，任務可能已結束")
                if st.button("返回設定頁面"):
                    st.session_state.playwright_crawl_status = "idle"
                    if hasattr(st.session_state, 'recovered_from_background'):
                        del st.session_state.recovered_from_background
                    st.rerun()
                return
        
        # 清除恢復標記
        if hasattr(st.session_state, 'recovered_from_background'):
            del st.session_state.recovered_from_background
    
    # 使用原有的進度渲染邏輯
    self._render_progress_original()

def _render_progress_original(self):
    """原有的進度渲染邏輯（保持不變）"""
    # 這裡應該是原有的 _render_progress 邏輯
    # 為了避免衝突，我們保持原有邏輯不變
    pass

# 將這些方法添加到 PlaywrightCrawlerComponentV2 類別中
def enhance_playwright_component(component_class):
    """為 PlaywrightCrawlerComponentV2 添加增強方法"""
    component_class._handle_recovered_task = _handle_recovered_task
    component_class._render_task_manager = _render_task_manager
    component_class._render_progress_enhanced = _render_progress_enhanced
    component_class._render_progress_original = _render_progress_original
    return component_class