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
    
    def delete_user_data(self, username: str):
        """刪除指定用戶的所有數據"""
        try:
            # 二次確認
            st.warning(f"⚠️ 確認要刪除用戶 @{username} 的所有Playwright爬蟲資料嗎？")
            
            col1, col2, col3 = st.columns([1, 1, 2])
            
            with col1:
                if st.button("✅ 確認刪除", key=f"confirm_delete_{username}", type="primary"):
                    # 執行刪除
                    result = asyncio.run(self.db_handler.delete_user_data_async(username))
                    
                    if result.get("success"):
                        st.success(f"✅ {result.get('message', '刪除成功')}")
                        
                        # 清除緩存
                        if 'playwright_db_stats_cache' in st.session_state:
                            del st.session_state.playwright_db_stats_cache
                        
                        st.rerun()
                    else:
                        st.error(f"❌ 刪除失敗: {result.get('error', '未知錯誤')}")
            
            with col2:
                if st.button("❌ 取消", key=f"cancel_delete_{username}"):
                    st.info("🔄 已取消刪除操作")
                    st.rerun()
            
            with col3:
                st.info("💡 提示：刪除後將無法復原，請謹慎操作")
                
        except Exception as e:
            st.error(f"❌ 刪除操作失敗: {e}")
    
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