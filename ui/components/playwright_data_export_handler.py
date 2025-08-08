"""
Playwright 數據導出和CSV處理處理器
拆分自 playwright_crawler_component_v2.py 的導出相關功能
"""

import streamlit as st
import json
import os
from pathlib import Path
from datetime import datetime, date
from decimal import Decimal

from .playwright_utils import PlaywrightUtils


class PlaywrightDataExportHandler:
    """Playwright 數據導出和CSV處理處理器"""
    
    def __init__(self, db_handler):
        self.db_handler = db_handler
    
    def export_history_data(self, username: str, export_type: str, **kwargs):
        """導出歷史數據"""
        try:
            import asyncio
            
            # 獲取排序參數
            sort_by = kwargs.get('sort_by', 'fetched_at')
            sort_order = kwargs.get('sort_order', 'DESC')
            
            with st.spinner(f"🔄 正在從資料庫獲取 @{username} 的{export_type}數據..."):
                # 異步獲取資料庫數據
                posts_data = asyncio.run(self._fetch_history_from_db(username, export_type, **kwargs))
            
            if not posts_data:
                st.warning(f"⚠️ 沒有找到用戶 @{username} 的歷史數據")
                return
            
            # 排序數據
            def get_sort_key(post):
                value = post.get(sort_by, 0)
                if value is None:
                    return 0
                if isinstance(value, str):
                    try:
                        return float(value)
                    except:
                        return 0
                return value
            
            posts_data.sort(key=get_sort_key, reverse=(sort_order == 'DESC'))
            
            # 準備數據結構
            data = {
                "username": username,
                "export_type": export_type,
                "exported_at": PlaywrightUtils.get_current_taipei_time().isoformat(),
                "sort_by": sort_by,
                "sort_order": sort_order,
                "total_records": len(posts_data),
                "data": posts_data
            }
            
            # 添加統計信息
            if export_type == "analysis":
                data["summary"] = self._calculate_stats(posts_data)
            
            # 同時提供 JSON 和 CSV 下載
            col1, col2 = st.columns(2)
            
            with col1:
                # JSON 下載
                import json
                from decimal import Decimal
                from datetime import datetime, date
                
                # 自定義JSON編碼器處理Decimal和datetime類型
                def json_serializer(obj):
                    if isinstance(obj, Decimal):
                        return float(obj)
                    elif isinstance(obj, (datetime, date)):
                        return obj.isoformat()
                    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
                
                json_content = json.dumps(data, ensure_ascii=False, indent=2, default=json_serializer)
                timestamp = PlaywrightUtils.get_current_taipei_time().strftime('%Y%m%d_%H%M%S')
                json_filename = f"playwright_history_{username}_{export_type}_{timestamp}.json"
                
                st.download_button(
                    label=f"📥 下載JSON ({len(posts_data)}筆)",
                    data=json_content,
                    file_name=json_filename,
                    mime="application/json",
                    help="下載歷史數據JSON文件"
                )
            
            with col2:
                # CSV 下載
                csv_content = self.convert_to_csv(posts_data)
                # _convert_to_csv 已經返回 bytes，無需再次編碼
                csv_filename = f"playwright_history_{username}_{export_type}_{timestamp}.csv"
                
                st.download_button(
                    label=f"📊 下載CSV ({len(posts_data)}筆)",
                    data=csv_content,
                    file_name=csv_filename,
                    mime="text/csv",
                    help="下載歷史數據CSV文件"
                )
            
            # 顯示數據預覽
            st.subheader("📊 數據預覽")
            if export_type == "analysis" and "summary" in data:
                col_s1, col_s2, col_s3, col_s4 = st.columns(4)
                summary = data["summary"]
                with col_s1:
                    st.metric("總貼文數", summary.get("total_posts", 0))
                with col_s2:
                    st.metric("平均觀看數", f"{summary.get('avg_views', 0):,.0f}")
                with col_s3:
                    st.metric("平均按讚數", f"{summary.get('avg_likes', 0):,.0f}")
                with col_s4:
                    st.metric("最高分數", f"{summary.get('max_score', 0):,.0f}")
            
            # 顯示前10筆數據
            if posts_data:
                col_preview1, col_preview2 = st.columns([1, 1])
                with col_preview1:
                    st.write("**前10筆數據：**")
                with col_preview2:
                    show_full_history_content = st.checkbox("📖 顯示完整內容", key="show_full_history_content_v2", help="勾選後將顯示完整貼文內容")
                
                preview_data = []
                for i, post in enumerate(posts_data[:10], 1):
                    content = post.get('content', '')
                    content_display = content if show_full_history_content else ((content[:40] + "...") if content and len(content) > 40 else content or 'N/A')
                    
                    # 處理發布時間顯示（強化錯誤處理）
                    published_at = post.get('post_published_at', '')
                    if published_at:
                        try:
                            # 轉換為台北時間並格式化顯示
                            taipei_published = PlaywrightUtils.convert_to_taipei_time(published_at)
                            if taipei_published:
                                published_display = taipei_published.strftime('%Y-%m-%d %H:%M')
                            else:
                                # 如果轉換失敗，嘗試直接格式化字符串
                                published_display = str(published_at)[:16] if len(str(published_at)) >= 16 else str(published_at)
                        except Exception as e:
                            print(f"🐛 發布時間格式化錯誤: {published_at} -> {e}")
                            published_display = str(published_at)[:16] if published_at else 'N/A'
                    else:
                        published_display = 'N/A'
                    
                    # 處理爬取時間顯示（強化錯誤處理）
                    fetched_at = post.get('fetched_at', '')
                    if fetched_at:
                        try:
                            taipei_fetched = PlaywrightUtils.convert_to_taipei_time(fetched_at)
                            if taipei_fetched:
                                fetched_display = taipei_fetched.strftime('%Y-%m-%d %H:%M')
                            else:
                                # 如果轉換失敗，嘗試直接格式化字符串
                                fetched_display = str(fetched_at)[:16] if len(str(fetched_at)) >= 16 else str(fetched_at)
                        except Exception as e:
                            print(f"🐛 爬取時間格式化錯誤: {fetched_at} -> {e}")
                            fetched_display = str(fetched_at)[:16] if fetched_at else 'N/A'
                    else:
                        fetched_display = 'N/A'
                    
                    preview_data.append({
                        "#": i,
                        "貼文ID": post.get('post_id', 'N/A')[:20] + "..." if len(post.get('post_id', '')) > 20 else post.get('post_id', 'N/A'),
                        "內容" if show_full_history_content else "內容預覽": content_display,
                        "觀看數": f"{post.get('views_count', 0):,}",
                        "按讚數": f"{post.get('likes_count', 0):,}",
                        "分數": f"{post.get('calculated_score', 0):,.1f}" if post.get('calculated_score') else 'N/A',
                        "發布時間": published_display,
                        "爬取時間": fetched_display
                    })
                st.dataframe(preview_data, use_container_width=True)
            
            st.success(f"✅ {export_type}數據導出完成！共 {len(posts_data)} 筆記錄")
            
        except Exception as e:
            st.error(f"❌ 歷史數據導出失敗: {str(e)}")
    
    async def _fetch_history_from_db(self, username: str, export_type: str, **kwargs):
        """從資料庫獲取歷史數據"""
        try:
            posts = await self.db_handler.get_user_posts_async(username)
            
            # 轉換所有時間字段為台北時間
            for post in posts:
                for time_field in ['created_at', 'fetched_at', 'post_published_at']:
                    if post.get(time_field):
                        taipei_time = PlaywrightUtils.convert_to_taipei_time(post[time_field])
                        if taipei_time:
                            post[time_field] = taipei_time.isoformat()
            
            if export_type == "recent":
                days_back = kwargs.get('days_back', 7)
                limit = kwargs.get('limit', 1000)
                
                # 過濾最近的數據
                from datetime import datetime, timedelta
                cutoff_date = PlaywrightUtils.get_current_taipei_time() - timedelta(days=days_back)
                
                filtered_posts = []
                for post in posts:
                    try:
                        if post.get('fetched_at'):
                            fetch_time = datetime.fromisoformat(str(post['fetched_at']).replace('Z', '+00:00'))
                            if fetch_time >= cutoff_date:
                                filtered_posts.append(post)
                    except:
                        continue
                
                return filtered_posts[:limit]
                
            elif export_type == "all":
                limit = kwargs.get('limit', 5000)
                return posts[:limit]
                
            elif export_type == "analysis":
                return posts
                
        except Exception as e:
            st.error(f"❌ 資料庫查詢失敗: {e}")
            return []
    
    def _calculate_stats(self, posts_data):
        """計算統計數據"""
        if not posts_data:
            return {
                "total_posts": 0,
                "avg_views": 0,
                "avg_likes": 0,
                "avg_comments": 0,
                "max_score": 0,
                "min_score": 0
            }
        
        total_posts = len(posts_data)
        views = [post.get('views_count', 0) for post in posts_data if post.get('views_count')]
        likes = [post.get('likes_count', 0) for post in posts_data if post.get('likes_count')]
        comments = [post.get('comments_count', 0) for post in posts_data if post.get('comments_count')]
        scores = [post.get('calculated_score', 0) for post in posts_data if post.get('calculated_score')]
        
        return {
            "total_posts": total_posts,
            "avg_views": sum(views) / len(views) if views else 0,
            "avg_likes": sum(likes) / len(likes) if likes else 0,
            "avg_comments": sum(comments) / len(comments) if comments else 0,
            "max_score": max(scores) if scores else 0,
            "min_score": min(scores) if scores else 0
        }
    
    def convert_to_csv(self, posts_data):
        """將數據轉換為CSV格式"""
        import pandas as pd
        import io
        
        # 準備CSV數據，與主要導出格式一致
        csv_data = []
        for post in posts_data:
            # 處理陣列字段
            tags = post.get('tags', [])
            if isinstance(tags, str):
                try:
                    import json
                    tags = json.loads(tags)
                except:
                    tags = []
            tags_str = "|".join(tags) if tags else ""
            
            images = post.get('images', [])
            if isinstance(images, str):
                try:
                    import json
                    images = json.loads(images)
                except:
                    images = []
            images_str = "|".join(images) if images else ""
            
            videos = post.get('videos', [])
            if isinstance(videos, str):
                try:
                    import json
                    videos = json.loads(videos)
                except:
                    videos = []
            videos_str = "|".join(videos) if videos else ""
            
            # 處理時間字段 - 轉換為台北時間
            created_at = post.get('created_at', '')
            if created_at:
                taipei_created = PlaywrightUtils.convert_to_taipei_time(created_at)
                created_at = taipei_created.isoformat() if taipei_created else created_at
            
            post_published_at = post.get('post_published_at', '')
            if post_published_at:
                taipei_published = PlaywrightUtils.convert_to_taipei_time(post_published_at)
                post_published_at = taipei_published.isoformat() if taipei_published else post_published_at
            
            fetched_at = post.get('fetched_at', '')
            if fetched_at:
                taipei_fetched = PlaywrightUtils.convert_to_taipei_time(fetched_at)
                fetched_at = taipei_fetched.isoformat() if taipei_fetched else fetched_at
            
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
                "created_at": created_at,
                "post_published_at": post_published_at,
                "tags": tags_str,
                "images": images_str,
                "videos": videos_str,
                "source": post.get('source', 'playwright_agent'),
                "crawler_type": post.get('crawler_type', 'playwright'),
                "crawl_id": post.get('crawl_id', ''),
                "fetched_at": fetched_at
            })
        
        # 轉換為CSV
        df = pd.DataFrame(csv_data)
        output = io.BytesIO()
        df.to_csv(output, index=False, encoding='utf-8-sig')
        return output.getvalue()
    
    def show_advanced_export_options(self):
        """顯示進階導出選項"""
        with st.expander("🔍 進階導出功能", expanded=True):
            # 添加關閉按鈕
            col_title, col_close = st.columns([4, 1])
            with col_title:
                st.markdown("**更多導出選項和批量操作**")
            with col_close:
                if st.button("❌ 關閉", key="close_playwright_advanced_exports"):
                    st.session_state.show_playwright_advanced_exports = False
                    st.rerun()
            
            tab1, tab2, tab3 = st.tabs(["📊 對比報告", "🔄 批量導出", "⚡ 快速工具"])
            
            with tab1:
                st.subheader("📊 多次爬取對比報告")
                st.info("比較多次爬取結果的效能和成功率")
                
                # 查找所有Playwright JSON文件
                import glob
                from pathlib import Path
                
                # 檢查新的資料夾位置
                extraction_dir = Path("crawl_data")
                if extraction_dir.exists():
                    json_files = list(extraction_dir.glob("crawl_data_*.json"))
                else:
                    json_files = [Path(f) for f in glob.glob("crawl_data_*.json")]
                
                if len(json_files) >= 2:
                    st.write(f"🔍 找到 {len(json_files)} 個Playwright爬取結果文件：")
                    
                    # 顯示文件列表
                    file_options = {}
                    for file in sorted(json_files, reverse=True)[:10]:  # 最新的10個
                        file_time = self._extract_time_from_filename(str(file))
                        display_name = f"{file.name} ({file_time})"
                        file_options[display_name] = str(file)
                    
                    selected_displays = st.multiselect(
                        "選擇要比對的文件（至少2個）：",
                        options=list(file_options.keys()),
                        default=[],
                        help="選擇多個文件進行比對分析",
                        key="playwright_comparison_file_selector"
                    )
                    
                    selected_files = [file_options[display] for display in selected_displays]
                    
                    if len(selected_files) >= 2:
                        if st.button("📊 生成對比報告", key="playwright_generate_comparison", type="primary"):
                            self._generate_comparison_report(selected_files)
                    else:
                        st.info("💡 請選擇至少2個文件進行比對分析")
                else:
                    st.warning("⚠️ 需要至少2個Playwright爬取結果文件才能進行對比")
            
            with tab2:
                st.subheader("🔄 批量導出功能")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    if st.button("📥 導出所有最新結果", key="playwright_export_all_latest"):
                        self._export_all_latest_results()
                
                with col2:
                    if st.button("📈 導出所有帳號統計", key="playwright_export_all_stats"):
                        self._export_all_account_stats()
            
            with tab3:
                st.subheader("⚡ 快速工具")
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    if st.button("🧹 清理暫存檔案", key="playwright_cleanup_temp"):
                        self._cleanup_temp_files()
                
                with col2:
                    if st.button("📋 複製結果摘要", key="playwright_copy_summary"):
                        if 'playwright_results' in st.session_state:
                            self._copy_results_summary()
                        else:
                            st.error("❌ 沒有可複製的結果")
                
                with col3:
                    if st.button("🔗 生成分享連結", key="playwright_share_link"):
                        self._generate_share_link()
    
    def _extract_time_from_filename(self, filename: str) -> str:
        """從檔案名提取時間"""
        import re
        match = re.search(r'(\d{8}_\d{6})', filename)
        if match:
            time_str = match.group(1)
            return f"{time_str[:4]}-{time_str[4:6]}-{time_str[6:8]} {time_str[9:11]}:{time_str[11:13]}"
        return "未知時間"
    
    def _generate_comparison_report(self, selected_files: list):
        """生成對比報告"""
        try:
            import pandas as pd
            
            comparison_data = []
            
            for file_path in selected_files:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                comparison_data.append({
                    "檔案名": Path(file_path).name,
                    "時間戳": data.get('timestamp', 'N/A'),
                    "用戶名": data.get('target_username', 'N/A'),
                    "爬蟲類型": data.get('crawler_type', 'playwright'),
                    "總貼文數": len(data.get('results', [])),
                    "成功數": data.get('api_success_count', 0),
                    "失敗數": data.get('api_failure_count', 0),
                    "成功率": data.get('overall_success_rate', 0),
                })
            
            df = pd.DataFrame(comparison_data)
            
            st.subheader("📊 對比報告")
            st.dataframe(df, use_container_width=True)
            
            # 提供下載
            csv_content = df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
            timestamp = PlaywrightUtils.get_current_taipei_time().strftime('%Y%m%d_%H%M%S')
            filename = f"playwright_comparison_report_{timestamp}.csv"
            
            st.download_button(
                label="📥 下載對比報告",
                data=csv_content,
                file_name=filename,
                mime="text/csv"
            )
            
        except Exception as e:
            st.error(f"❌ 生成對比報告失敗: {e}")
    
    def _export_all_latest_results(self):
        """導出所有最新結果"""
        st.info("📦 批量導出功能開發中...")
    
    def _export_all_account_stats(self):
        """導出所有帳號統計"""
        st.info("📈 帳號統計導出功能開發中...")
    
    def _cleanup_temp_files(self):
        """清理暫存檔案 - 使用 FolderManager"""
        try:
            from pathlib import Path
            from common.folder_manager import FolderManager
            
            # 清理舊格式的進度檔案（根目錄下的）
            import glob
            old_temp_files = glob.glob("temp_playwright_progress_*.json")
            old_cleaned = 0
            for file in old_temp_files:
                try:
                    os.remove(file)
                    old_cleaned += 1
                except:
                    pass
            
            # 清理新格式的進度檔案資料夾
            temp_progress_dir = Path("temp_progress")
            if temp_progress_dir.exists():
                deleted_count = FolderManager.cleanup_old_files(
                    temp_progress_dir, 
                    max_files=50,  # 保留最新的 50 個進度檔案
                    pattern="*.json"
                )
                total_cleaned = old_cleaned + deleted_count
                if total_cleaned > 0:
                    st.success(f"🧹 已清理 {total_cleaned} 個暫存進度檔案 (舊格式: {old_cleaned}, 新格式: {deleted_count})")
                else:
                    st.info("✅ 暫存檔案已經是最新狀態")
            
            # 同時清理其他專案資料夾
            FolderManager.setup_project_folders()
            
        except Exception as e:
            st.warning(f"⚠️ 清理暫存檔案時發生錯誤: {e}")
    
    def _copy_results_summary(self):
        """複製結果摘要"""
        results = st.session_state.get('playwright_results', {})
        posts = results.get('results', [])
        
        summary = f"""Playwright 爬蟲結果摘要
用戶: @{results.get('target_username', 'unknown')}
時間: {results.get('timestamp', 'N/A')}
總貼文: {len(posts)}
成功率: {results.get('overall_success_rate', 0):.1f}%
"""
        
        st.text_area("📋 結果摘要（請複製）", value=summary, key="playwright_summary_copy")
    
    def _generate_share_link(self):
        """生成分享連結"""
        st.info("🔗 分享連結功能開發中...")
    
    def clear_results(self):
        """清除結果"""
        if 'playwright_results' in st.session_state:
            del st.session_state.playwright_results
        if 'playwright_results_file' in st.session_state:
            del st.session_state.playwright_results_file
        # 重置保存標記
        st.session_state.playwright_results_saved = False
        st.success("🗑️ 結果已清除")
        st.rerun()
    
    def load_csv_file(self, uploaded_file):
        """載入CSV文件"""
        try:
            import pandas as pd
            import io
            
            # 清理可能的舊文件引用，避免 MediaFileStorageError
            if hasattr(st.session_state, 'get'):
                file_related_keys = [k for k in st.session_state.keys() if 'file' in k.lower() or 'upload' in k.lower()]
                for key in file_related_keys:
                    if key != "playwright_csv_uploader_v2":  # 保留當前上傳器
                        try:
                            del st.session_state[key]
                        except:
                            pass
            
            # 讀取CSV文件
            content = uploaded_file.getvalue()
            df = pd.read_csv(io.StringIO(content.decode('utf-8-sig')))
            
            # 檢查CSV格式是否正確（更靈活的驗證）
            # 🔧 修復：支援新格式和舊格式的兼容性
            # 核心必要欄位 - 至少需要用戶識別和貼文識別
            has_username = 'username' in df.columns
            has_user_id = 'user_id' in df.columns
            has_post_id = 'post_id' in df.columns
            has_real_post_id = 'real_post_id' in df.columns
            
            # 必須有用戶識別欄位
            if not (has_username or has_user_id):
                st.error("❌ CSV格式不正確，必須包含 'username' 或 'user_id' 欄位")
                return
            
            # 必須有貼文識別欄位
            if not (has_post_id or has_real_post_id):
                st.error("❌ CSV格式不正確，必須包含 'post_id' 或 'real_post_id' 欄位")
                return
            
            # 必須有內容欄位
            if 'content' not in df.columns:
                st.error("❌ CSV格式不正確，缺少 'content' 欄位")
                return
            
            # 檢查可選欄位，如果沒有則提供預設值
            optional_columns = ['url', 'views', 'likes_count', 'comments_count', 'reposts_count', 'shares_count']
            for col in optional_columns:
                if col not in df.columns:
                    if col == 'views':
                        df[col] = df.get('views_count', 0)  # 嘗試使用 views_count 作為 views
                    elif col == 'url':
                        df[col] = ''  # URL可以為空
                    else:
                        df[col] = 0  # 預設值為 0
            
            st.info(f"✅ 成功載入CSV，包含 {len(df)} 筆記錄")
            
            # 轉換為結果格式
            results = []
            for _, row in df.iterrows():
                # 處理陣列字段 (tags, images, videos)
                tags_str = str(row.get('tags', '')).strip()
                tags = tags_str.split('|') if tags_str else []
                
                images_str = str(row.get('images', '')).strip()
                images = images_str.split('|') if images_str else []
                
                videos_str = str(row.get('videos', '')).strip()
                videos = videos_str.split('|') if videos_str else []
                
                # 🔧 修復：智能處理新舊格式的用戶名和貼文ID
                # 優先使用新格式欄位，回退到舊格式
                user_id = str(row.get('user_id', '')).strip() or str(row.get('username', '')).strip()
                real_post_id = str(row.get('real_post_id', '')).strip()
                original_post_id = str(row.get('post_id', '')).strip()
                
                # 如果沒有 real_post_id，嘗試從 post_id 分離
                if not real_post_id and original_post_id and '_' in original_post_id:
                    parts = original_post_id.split('_', 1)
                    if len(parts) > 1:
                        if not user_id:  # 如果還沒有用戶ID，從post_id提取
                            user_id = parts[0]
                        real_post_id = parts[1]
                else:
                    # 如果沒有分離格式，使用原始post_id作為real_post_id
                    real_post_id = real_post_id or original_post_id
                
                # 重建兼容的post_id格式（舊系統兼容性）
                combined_post_id = f"{user_id}_{real_post_id}" if user_id and real_post_id else original_post_id
                
                result = {
                    "url": str(row.get('url', '')).strip(),
                    "post_id": combined_post_id,  # 保持舊格式兼容性
                    "username": user_id,  # 使用分離的用戶ID
                    "content": str(row.get('content', '')).strip(),
                    "likes_count": row.get('likes_count', 0) if pd.notna(row.get('likes_count')) else 0,
                    "comments_count": row.get('comments_count', 0) if pd.notna(row.get('comments_count')) else 0,
                    "reposts_count": row.get('reposts_count', 0) if pd.notna(row.get('reposts_count')) else 0,
                    "shares_count": row.get('shares_count', 0) if pd.notna(row.get('shares_count')) else 0,
                    "views_count": row.get('views_count', 0) if pd.notna(row.get('views_count')) else 0,
                    "calculated_score": row.get('calculated_score', 0) if pd.notna(row.get('calculated_score')) else 0,
                    "created_at": str(row.get('created_at', '')).strip(),
                    "post_published_at": str(row.get('post_published_at', '')).strip(),
                    "tags": tags,
                    "images": images,
                    "videos": videos,
                    "source": str(row.get('source', 'playwright_agent')).strip(),
                    "crawler_type": str(row.get('crawler_type', 'playwright')).strip(),
                    "crawl_id": str(row.get('crawl_id', '')).strip(),
                    "extracted_at": str(row.get('extracted_at', '')).strip(),
                    "success": row.get('success', True) if pd.notna(row.get('success')) else True
                }
                results.append(result)
            
            # 🔧 修復：從結果中智能提取目標用戶名
            target_username = ""
            if results:
                # 嘗試從第一筆記錄獲取用戶名
                first_result = results[0]
                target_username = first_result.get('username', '')
                
                # 如果所有記錄的用戶名都相同，使用該用戶名
                all_usernames = set(r.get('username', '') for r in results if r.get('username'))
                if len(all_usernames) == 1:
                    target_username = list(all_usernames)[0]
                elif len(all_usernames) > 1:
                    st.info(f"📊 檢測到多個用戶的資料：{', '.join(sorted(all_usernames))}")
            
            # 包裝為完整結果格式
            final_results = {
                "crawl_id": f"imported_{PlaywrightUtils.get_current_taipei_time().strftime('%Y%m%d_%H%M%S')}",
                "timestamp": PlaywrightUtils.get_current_taipei_time().isoformat(),
                "target_username": target_username,  # 🔧 修復：使用智能提取的用戶名
                "source": "csv_import",
                "crawler_type": "playwright",
                "total_processed": len(results),
                "results": results
            }
            
            st.session_state.playwright_results = final_results
            st.session_state.playwright_crawl_status = "completed"  # 設置狀態為完成
            st.success(f"✅ 成功載入 {len(results)} 筆記錄")
            st.rerun()
            
        except Exception as e:
            st.error(f"❌ 載入CSV失敗: {e}")