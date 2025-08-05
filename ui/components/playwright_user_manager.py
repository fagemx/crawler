"""
Playwright 用戶數據管理模組
負責用戶相關的數據操作：CSV 導出、數據刪除等
"""

import streamlit as st
import asyncio
import pandas as pd
import io
import json
from datetime import datetime
from typing import Any, Dict

from .playwright_database_handler import PlaywrightDatabaseHandler

# 添加調試用的日誌函數
def debug_log(message: str):
    """調試日誌函數"""
    print(f"[PlaywrightUserManager DEBUG] {message}")
    # 可選：也寫入到 streamlit 的側邊欄或其他地方
    # st.sidebar.text(f"DEBUG: {message}")


class PlaywrightUserManager:
    """Playwright 用戶數據管理器"""
    
    def __init__(self):
        self.db_handler = PlaywrightDatabaseHandler()
    
    def show_user_csv_download(self, username: str):
        """顯示用戶CSV直接下載按鈕"""
        try:
            # 獲取用戶貼文
            posts = asyncio.run(self.db_handler.get_user_posts_async(username))
            
            if not posts:
                st.warning(f"❌ 用戶 @{username} 沒有貼文記錄")
                return
            
            # 準備CSV數據（與 JSON 格式完全一致）
            csv_data = []
            for post in posts:
                # 處理資料庫中可能存在的陣列字段（如果以 JSON 字符串存儲）
                tags = self._process_array_field(post.get('tags', []))
                images = self._process_array_field(post.get('images', []))
                videos = self._process_array_field(post.get('videos', []))
                
                csv_data.append({
                    "url": post.get('url', ''),
                    "post_id": post.get('post_id', ''),
                    "username": post.get('username', ''),
                    "content": post.get('content', ''),
                    "likes_count": post.get('likes_count', 0),
                    "comments_count": post.get('comments_count', 0),
                    "reposts_count": post.get('reposts_count', 0),
                    "shares_count": post.get('shares_count', 0),
                    "views_count": post.get('views_count', 0),
                    "calculated_score": post.get('calculated_score', ''),
                    "created_at": post.get('created_at', ''),
                    "post_published_at": post.get('post_published_at', ''),
                    "tags": "|".join(tags) if tags else "",
                    "images": "|".join(images) if images else "",
                    "videos": "|".join(videos) if videos else "",
                    "source": post.get('source', 'playwright_agent'),
                    "crawler_type": post.get('crawler_type', 'playwright'),
                    "crawl_id": post.get('crawl_id', ''),
                    "fetched_at": post.get('fetched_at', '')
                })
            
            # 轉換為DataFrame並生成CSV
            df = pd.DataFrame(csv_data)
            csv_content = self._dataframe_to_csv(df)
            
            # 直接顯示下載按鈕
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"user_posts_{username}_{timestamp}.csv"
            
            st.download_button(
                label=f"📥 導出CSV ({len(posts)}筆)",
                data=csv_content,
                file_name=filename,
                mime="text/csv",
                help=f"直接下載 @{username} 的所有貼文記錄",
                use_container_width=True
            )
            
        except Exception as e:
            st.error(f"❌ 準備CSV下載失敗: {e}")
    
    def export_user_csv(self, username: str):
        """導出指定用戶的所有貼文為CSV（中文欄位名）"""
        try:
            # 使用 asyncio 獲取用戶貼文
            posts = asyncio.run(self.db_handler.get_user_posts_async(username))
            
            if not posts:
                st.warning(f"❌ 用戶 @{username} 沒有找到任何貼文記錄")
                return
            
            # 準備CSV數據 - 完整欄位（中文名稱）
            csv_data = []
            for i, post in enumerate(posts, 1):
                # 處理陣列字段
                tags = self._process_array_field(post.get('tags', []))
                images = self._process_array_field(post.get('images', []))
                videos = self._process_array_field(post.get('videos', []))
                
                csv_data.append({
                    "序號": i,
                    "用戶名": post.get('username', ''),
                    "貼文ID": post.get('post_id', ''),
                    "URL": post.get('url', ''),
                    "內容": post.get('content', ''),
                    "觀看數": post.get('views_count', post.get('views', 0)),
                    "按讚數": post.get('likes_count', post.get('likes', 0)),
                    "留言數": post.get('comments_count', post.get('comments', 0)),
                    "轉發數": post.get('reposts_count', post.get('reposts', 0)),
                    "分享數": post.get('shares_count', post.get('shares', 0)),
                    "計算分數": post.get('calculated_score', ''),
                    "發布時間": post.get('post_published_at', ''),
                    "標籤": "|".join(tags) if tags else "",
                    "圖片": "|".join(images) if images else "",
                    "影片": "|".join(videos) if videos else "",
                    "來源": post.get('source', ''),
                    "爬蟲類型": post.get('crawler_type', ''),
                    "爬取ID": post.get('crawl_id', ''),
                    "建立時間": post.get('created_at', ''),
                    "爬取時間": post.get('fetched_at', '')
                })
            
            # 轉換為DataFrame並生成CSV
            df = pd.DataFrame(csv_data)
            csv_content = self._dataframe_to_csv(df)
            
            # 提供下載
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"user_posts_{username}_{timestamp}.csv"
            
            st.download_button(
                label=f"📥 下載 @{username} 的貼文CSV",
                data=csv_content,
                file_name=filename,
                mime="text/csv",
                help=f"下載用戶 @{username} 的所有貼文記錄"
            )
            
            st.success(f"✅ 成功導出 @{username} 的 {len(posts)} 筆貼文記錄")
            
        except Exception as e:
            st.error(f"❌ 導出用戶CSV失敗: {e}")
    
    def manage_user_data(self, user_stats: list[dict[str, Any]]):
        """整合用戶資料管理 UI，包括選擇、導出和刪除"""
        with st.expander("🗂️ 用戶資料管理 (Playwright)", expanded=True):
            user_options = [user.get('username') for user in user_stats if user.get('username')]
            if not user_options:
                st.warning("沒有可管理的用戶。")
                return

            # 使用 session state 來持久化選擇的用戶
            if 'playwright_selected_user' not in st.session_state:
                st.session_state.playwright_selected_user = user_options[0]

            selected_user = st.selectbox(
                "選擇要管理的用戶:",
                options=user_options,
                key="playwright_user_selector_v3",
                index=user_options.index(st.session_state.playwright_selected_user) if st.session_state.playwright_selected_user in user_options else 0,
                help="選擇一個用戶來管理其爬蟲資料"
            )
            
            # 當選擇框改變時，更新 session_state
            if st.session_state.playwright_selected_user != selected_user:
                st.session_state.playwright_selected_user = selected_user
                # 清除可能存在的舊的刪除確認狀態
                if 'playwright_confirm_delete_user' in st.session_state:
                    del st.session_state.playwright_confirm_delete_user
                st.rerun()

            st.markdown("---")
            
            # 顯示詳細信息
            selected_user_info = next((u for u in user_stats if u.get('username') == selected_user), None)
            if selected_user_info:
                st.info(f"""
                **📋 用戶 @{selected_user} 的詳細信息:**
                - 📊 貼文總數: {selected_user_info.get('post_count', 0):,} 個
                - ⏰ 最後爬取: {str(selected_user_info.get('latest_crawl', 'N/A'))[:16] if selected_user_info.get('latest_crawl') else 'N/A'}
                """)
            
            # 操作按鈕
            col1, col2 = st.columns(2)
            with col1:
                self.show_user_csv_download(selected_user)
            with col2:
                # 刪除流程現在由此方法完全管理
                self.handle_delete_button(selected_user)
    
    def handle_delete_button(self, username: str):
        """管理刪除按鈕的顯示和兩步確認流程"""
        delete_confirm_key = f"playwright_confirm_delete_user"

        # 自訂紅色樣式
        st.markdown("""
        <style>
        div.stButton > button[key*="playwright_delete_"] {
            background-color: #ff4b4b !important;
            color: white !important;
            border-color: #ff4b4b !important;
        }
        div.stButton > button[key*="playwright_delete_"]:hover {
            background-color: #ff2b2b !important;
            border-color: #ff2b2b !important;
        }
        </style>
        """, unsafe_allow_html=True)

        # 檢查是否進入了確認刪除流程
        if st.session_state.get(delete_confirm_key) == username:
            # 第二步：最終確認
            st.error(f"⚠️ **最終確認: 確定刪除 @{username}?**")
            
            if st.button(f"🗑️ 是，永久刪除 @{username}", key=f"playwright_delete_confirm_final_{username}", use_container_width=True):
                self._execute_user_deletion(username)
                del st.session_state[delete_confirm_key]
                # 執行刪除後會自動 rerun
            
            if st.button("❌ 取消", key=f"playwright_delete_cancel_{username}", use_container_width=True):
                del st.session_state[delete_confirm_key]
                st.success("✅ 已取消刪除操作。")
                st.rerun()

        else:
            # 第一步：觸發確認
            if st.button("🗑️ 刪除用戶資料", key=f"playwright_delete_init_{username}", help=f"刪除 @{username} 的所有爬蟲資料", use_container_width=True):
                st.session_state[delete_confirm_key] = username
                st.rerun()
    
    def _execute_user_deletion(self, username: str):
        """執行實際的用戶刪除操作（改善錯誤處理和日誌記錄）"""
        try:
            # 顯示詳細的操作進度
            progress_placeholder = st.empty()
            
            with st.spinner(f"🗑️ 正在刪除用戶 @{username} 的資料..."):
                progress_placeholder.info("📡 正在連接資料庫...")
                debug_log(f"開始執行用戶 {username} 的刪除操作")
                
                # 執行資料庫刪除操作
                import asyncio
                import time
                
                start_time = time.time()
                result = asyncio.run(self.db_handler.delete_user_data_async(username))
                end_time = time.time()
                
                debug_log(f"資料庫操作完成，耗時: {end_time - start_time:.2f} 秒")
                progress_placeholder.info(f"⏱️ 資料庫操作耗時: {end_time - start_time:.2f} 秒")
                
                # 顯示詳細的操作結果
                st.info(f"🔍 **資料庫操作詳細結果:**")
                st.json(result)
                
                if result and result.get("success"):
                    deleted_count = result.get("deleted_count", 0)
                    debug_log(f"成功刪除 {deleted_count} 筆記錄")
                    
                    if deleted_count > 0:
                        st.success(f"✅ **刪除成功！** 已刪除用戶 @{username} 的 {deleted_count} 筆記錄")
                    else:
                        st.warning(f"⚠️ 用戶 @{username} 沒有找到任何記錄，可能已經被刪除或不存在")
                    
                    # 清除相關緩存
                    progress_placeholder.info("🧹 正在清除緩存...")
                    cache_keys_to_clear = [
                        'playwright_db_stats_cache',
                        'playwright_user_list_cache',
                        f'user_posts_{username}_cache',
                        'playwright_selected_user'  # 也清除選中的用戶
                    ]
                    
                    cleared_caches = 0
                    for cache_key in cache_keys_to_clear:
                        if cache_key in st.session_state:
                            del st.session_state[cache_key]
                            cleared_caches += 1
                    
                    debug_log(f"已清除 {cleared_caches} 個緩存")
                    st.info(f"🧹 已清除 {cleared_caches} 個相關緩存")
                    
                    # 等待一下讓用戶看到結果
                    time.sleep(1)
                    
                    # 最後顯示成功消息並重新載入
                    progress_placeholder.success(f"🎉 用戶 @{username} 的資料已完全刪除！頁面即將刷新...")
                    time.sleep(1)
                    st.rerun()
                    
                else:
                    error_msg = result.get('error', '未知錯誤') if result else '資料庫操作返回空結果'
                    debug_log(f"刪除失敗: {error_msg}")
                    st.error(f"❌ **刪除失敗**: {error_msg}")
                    
                    # 顯示更多調試信息
                    if result:
                        st.error("🔍 **調試信息**: 請檢查資料庫連接和權限設置")
                    else:
                        st.error("🔍 **調試信息**: 資料庫操作沒有返回任何結果，可能是連接問題")
                    
        except Exception as e:
            debug_log(f"刪除操作異常: {str(e)}")
            st.error(f"❌ **刪除操作失敗**: {str(e)}")
            
            # 詳細的錯誤信息
            import traceback
            error_details = traceback.format_exc()
            st.error(f"🔧 **詳細錯誤信息**:")
            st.code(error_details, language="python")
            
            # 提供一些調試建議
            st.info("""
            🔍 **可能的解決方案**:
            1. 檢查資料庫服務是否正常運行
            2. 檢查網路連接
            3. 檢查資料庫連接字符串和權限
            4. 檢查 PostgreSQL 服務狀態
            """)
    
    def _process_array_field(self, field_value) -> list:
        """處理陣列字段（可能是 list 或 JSON 字符串）"""
        if isinstance(field_value, list):
            return field_value
        elif isinstance(field_value, str):
            try:
                return json.loads(field_value)
            except:
                return []
        else:
            return []
    
    def _dataframe_to_csv(self, df: pd.DataFrame) -> bytes:
        """將 DataFrame 轉換為 CSV 字節內容"""
        output = io.BytesIO()
        df.to_csv(output, index=False, encoding='utf-8-sig')
        return output.getvalue()