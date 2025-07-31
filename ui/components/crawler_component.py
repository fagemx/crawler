"""
Threads 爬蟲組件
基於 test_playwright_agent.py 的真實功能
"""

import streamlit as st
import httpx
import json
import asyncio
import time
from pathlib import Path
from typing import Dict, Any, Optional


class ThreadsCrawlerComponent:
    def __init__(self):
        self.agent_url = "http://localhost:8006/v1/playwright/crawl"
        # 使用統一的配置管理
        from common.config import get_auth_file_path
        self.auth_file_path = get_auth_file_path(from_project_root=True)
    
    def render(self):
        """渲染爬蟲界面"""
        st.header("🕷️ Threads 內容爬蟲")
        st.markdown("基於 Playwright Agent 的真實 Threads 爬蟲，支持 SSE 實時進度顯示。")
        
        # 檢查認證文件
        if not self._check_auth_file():
            st.error("❌ 找不到認證檔案")
            st.info("請先執行: `python tests/threads_fetch/save_auth.py` 來產生認證檔案")
            return
        
        st.success("✅ 認證檔案已就緒")
        
        # 爬蟲配置
        self._render_crawler_config()
        
        # 根據狀態渲染不同界面
        status = st.session_state.get('crawler_status', 'idle')
        
        if status == 'running':
            self._render_crawler_progress()
        elif status == 'completed':
            self._render_crawler_results()
        elif status == 'error':
            st.error("❌ 爬蟲執行失敗，請檢查日誌")
            self._render_crawler_logs()
    
    def _check_auth_file(self) -> bool:
        """檢查認證文件是否存在"""
        return self.auth_file_path.exists()
    
    def _render_crawler_config(self):
        """渲染爬蟲配置界面"""
        col1, col2 = st.columns([2, 1])
        
        with col1:
            username = st.text_input(
                "Threads 用戶名稱：",
                placeholder="例如：natgeo",
                help="輸入不含 @ 符號的用戶名稱",
                key="crawler_username"
            )
        
        with col2:
            max_posts = st.number_input(
                "爬取貼文數量：",
                min_value=1,
                max_value=50,
                value=10,
                help="建議不超過 20 篇以避免過長等待時間",
                key="crawler_max_posts"
            )
        
        # 控制按鈕
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            if st.button(
                "🚀 開始爬取", 
                type="primary",
                disabled=st.session_state.get('crawler_status') == 'running',
                use_container_width=True
            ):
                if username.strip():
                    self._start_crawler(username, max_posts)
                else:
                    st.warning("請輸入用戶名稱")
        
        with col2:
            if st.button("🔄 重置", use_container_width=True):
                self._reset_crawler()
                st.rerun()
    
    def _start_crawler(self, username: str, max_posts: int):
        """啟動爬蟲"""
        # 初始化狀態
        st.session_state.crawler_status = 'running'
        st.session_state.crawler_target = {"username": username, "max_posts": max_posts}
        st.session_state.crawler_logs = []
        st.session_state.crawler_events = []
        st.session_state.final_data = None
        st.session_state.crawler_progress = 0
        
        # 讀取認證文件
        try:
            with open(self.auth_file_path, "r", encoding="utf-8") as f:
                auth_content = json.load(f)
        except Exception as e:
            st.error(f"❌ 無法讀取認證檔案: {e}")
            st.session_state.crawler_status = 'error'
            st.rerun()
            return
        
        # 啟動真實的爬蟲任務
        st.info("🚀 爬蟲已啟動，正在連接 Playwright Agent...")
        
        # 使用 asyncio 來執行異步任務
        import asyncio
        try:
            # 在 Streamlit 中運行異步任務
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._execute_crawler(username, max_posts, auth_content))
        except Exception as e:
            st.error(f"❌ 爬蟲執行失敗: {e}")
            st.session_state.crawler_status = 'error'
            st.session_state.crawler_logs.append(f"錯誤: {e}")
        finally:
            st.rerun()
    
    async def _execute_crawler(self, username: str, max_posts: int, auth_content: dict):
        """執行真實的爬蟲任務，使用混合模式：觸發爬蟲 + SSE 進度"""
        import uuid
        import threading
        import requests
        
        # 生成 task_id 用於追蹤進度
        task_id = str(uuid.uuid4())
        
        payload = {
            "username": username,
            "max_posts": max_posts,
            "auth_json_content": auth_content,
            "task_id": task_id  # 確保 Playwright Agent 使用這個 task_id
        }
        
        # 儲存 task_id 供 SSE 使用
        st.session_state.crawler_task_id = task_id
        
        try:
            timeout = httpx.Timeout(300.0)  # 5分鐘超時
            async with httpx.AsyncClient(timeout=timeout) as client:
                st.session_state.crawler_logs.append("🚀 啟動爬蟲並開始 SSE 進度監聽...")
                
                # 啟動 SSE 監聽（在背景執行）
                self._start_sse_listener(task_id)
                
                # 觸發爬蟲（同步調用）
                response = await client.post(self.agent_url, json=payload)
                
                if response.status_code != 200:
                    error_msg = f"❌ API 請求失敗，狀態碼: {response.status_code}"
                    st.session_state.crawler_logs.append(error_msg)
                    st.session_state.crawler_logs.append(f"錯誤內容: {response.text}")
                    st.session_state.crawler_status = 'error'
                    return

                # 解析最終結果
                try:
                    final_data = response.json()
                    st.session_state.crawler_logs.append("✅ 成功收到最終爬取結果！")
                    
                    # 轉換為UI期望的格式
                    if isinstance(final_data, dict) and "posts" in final_data:
                        ui_data = {
                            "batch_id": final_data.get("batch_id", task_id),
                            "username": final_data.get("username", username),
                            "processing_stage": "completed",
                            "total_count": final_data.get("total_count", len(final_data.get("posts", []))),
                            "posts": [],
                            "crawl_timestamp": time.time(),
                            "agent_version": "1.0.0"
                        }
                        
                        # 轉換貼文格式
                        for post in final_data.get("posts", []):
                            ui_post = {
                                "post_id": post.get("post_id", ""),
                                "username": post.get("username", username),
                                "content": post.get("content", ""),
                                "created_at": post.get("created_at", ""),
                                "likes_count": post.get("likes_count", 0),
                                "comments_count": post.get("comments_count", 0),
                                "reposts_count": post.get("reposts_count", 0),
                                "url": post.get("url", ""),
                                "source": "threads",
                                "processing_stage": "completed",
                                "media_urls": post.get("images", []) + post.get("videos", [])
                            }
                            ui_data["posts"].append(ui_post)
                        
                        st.session_state.final_data = ui_data
                    else:
                        st.session_state.final_data = final_data
                    
                    st.session_state.crawler_status = 'completed'
                    posts_count = len(st.session_state.final_data.get("posts", []))
                    st.session_state.crawler_logs.append(f"✅ 爬取完成！成功獲取 {posts_count} 篇貼文")
                    
                except json.JSONDecodeError as e:
                    st.session_state.crawler_logs.append(f"❌ 無法解析響應 JSON: {e}")
                    st.session_state.crawler_status = 'error'
                
        except httpx.ConnectError as e:
            error_msg = f"連線錯誤: 無法連線至 {self.agent_url}。請確認 Docker 容器是否正在運行。"
            st.session_state.crawler_logs.append(error_msg)
            st.session_state.crawler_status = 'error'
        except Exception as e:
            st.session_state.crawler_logs.append(f"執行時發生未預期的錯誤: {e}")
            st.session_state.crawler_status = 'error'

    def _start_sse_listener(self, task_id: str):
        """啟動 SSE 監聽器（在背景執行）"""
        import tempfile
        import json
        import os
        
        # 創建共享的進度文件
        progress_file = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix=f'_{task_id}.json')
        progress_file_path = progress_file.name
        progress_file.close()
        
        # 存儲進度文件路徑
        st.session_state.crawler_progress_file = progress_file_path
        
        def sse_worker():
            try:
                import requests
                import json
                
                orchestrator_url = f"http://localhost:8000/stream/{task_id}"
                print(f"📡 連接 SSE: {orchestrator_url}")
                
                with requests.get(orchestrator_url, stream=True, timeout=300) as response:
                    if response.status_code == 200:
                        for line in response.iter_lines():
                            if line:
                                line_str = line.decode('utf-8')
                                if line_str.startswith('data: '):
                                    try:
                                        data = json.loads(line_str[6:])  # 移除 'data: ' 前綴
                                        
                                        # 將進度寫入共享文件
                                        try:
                                            with open(progress_file_path, 'w') as f:
                                                json.dump(data, f)
                                        except Exception as e:
                                            print(f"⚠️ 寫入進度文件錯誤: {e}")
                                        
                                        # 如果收到完成或錯誤事件，結束監聽
                                        if data.get('stage') in ['completed', 'error']:
                                            break
                                            
                                    except json.JSONDecodeError:
                                        continue
                    else:
                        print(f"❌ SSE 連接失敗: {response.status_code}")
                        
            except Exception as e:
                print(f"❌ SSE 監聽錯誤: {e}")
            finally:
                # 清理：創建完成標記文件
                try:
                    completion_file = progress_file_path.replace('.json', '_completed.json')
                    with open(completion_file, 'w') as f:
                        json.dump({'completed': True}, f)
                except Exception:
                    pass
        
        # 在背景執行緒中啟動 SSE 監聽
        import threading
        threading.Thread(target=sse_worker, daemon=True).start()
    
    def _check_and_update_progress(self):
        """檢查進度文件並更新 UI 狀態，返回是否有更新"""
        import json
        import os
        
        progress_file_path = st.session_state.get('crawler_progress_file')
        if not progress_file_path or not os.path.exists(progress_file_path):
            return False
            
        try:
            # 檢查文件修改時間
            current_mtime = os.path.getmtime(progress_file_path)
            last_mtime = st.session_state.get('crawler_progress_mtime', 0)
            
            if current_mtime <= last_mtime:
                return False  # 沒有更新
                
            # 更新修改時間
            st.session_state.crawler_progress_mtime = current_mtime
            
            # 讀取進度數據
            with open(progress_file_path, 'r') as f:
                data = json.load(f)
            
            # 更新 UI 狀態
            self._update_ui_from_progress(data)
            return True
            
        except Exception as e:
            print(f"⚠️ 檢查進度文件錯誤: {e}")
            return False
    
    def _update_ui_from_progress(self, data: dict):
        """根據進度數據更新 UI 狀態"""
        stage = data.get('stage', '')
        
        # 確保日誌列表存在
        if 'crawler_logs' not in st.session_state:
            st.session_state.crawler_logs = []
        
        if stage == 'connected':
            st.session_state.crawler_logs.append("📡 SSE 連接已建立")
            
        elif stage == 'fetch_start':
            st.session_state.crawler_logs.append(f"🔍 開始爬取 @{data.get('username')} 的貼文...")
            
        elif stage == 'post_parsed':
            current = data.get('current', 0)
            total = data.get('total', 1)
            progress = data.get('progress', 0)
            post_id = data.get('post_id', '')
            content_preview = data.get('content_preview', '')
            likes = data.get('likes', 0)
            
            st.session_state.crawler_progress = progress
            st.session_state.crawler_logs.append(f"✅ 解析貼文 {post_id[-8:]}: {likes}讚 - {content_preview}")
            
        elif stage == 'batch_parsed':
            batch_size = data.get('batch_size', 0)
            current = data.get('current', 0)
            total = data.get('total', 1)
            query_name = data.get('query_name', '')
            st.session_state.crawler_logs.append(f"📦 從 {query_name} 解析了 {batch_size} 則貼文，總計: {current}/{total}")
            
        elif stage == 'fill_views_start':
            st.session_state.crawler_logs.append("👁️ 開始補齊瀏覽數...")
            
        elif stage == 'views_fetched':
            post_id = data.get('post_id', '')
            views_formatted = data.get('views_formatted', '0')
            st.session_state.crawler_logs.append(f"👁️ 貼文 {post_id[-8:]}: {views_formatted} 次瀏覽")
            
        elif stage == 'fill_views_completed':
            st.session_state.crawler_logs.append("✅ 瀏覽數補齊完成")
            
        elif stage == 'completed':
            st.session_state.crawler_logs.append("🎉 爬取任務完成！")
            st.session_state.crawler_progress = 1.0
            st.session_state.crawler_status = 'completed'
            
        elif stage == 'error':
            error_msg = data.get('error', '未知錯誤')
            st.session_state.crawler_logs.append(f"❌ 爬取錯誤: {error_msg}")
            st.session_state.crawler_status = 'error'
    
    def _handle_sse_event(self, data: dict):
        """處理 SSE 事件（線程安全版本）"""
        stage = data.get('stage', '')
        
        def safe_log(message: str):
            """安全地記錄日誌到 session state"""
            try:
                if hasattr(st.session_state, 'crawler_logs') and st.session_state.crawler_logs is not None:
                    st.session_state.crawler_logs.append(message)
                else:
                    print(message)  # 備用日誌
            except Exception:
                print(message)  # 備用日誌
        
        def safe_set_progress(progress: float):
            """安全地設置進度"""
            try:
                if hasattr(st.session_state, 'crawler_progress'):
                    st.session_state.crawler_progress = progress
            except Exception:
                print(f"📊 進度: {progress:.1%}")
        
        def safe_set_status(status: str):
            """安全地設置狀態"""
            try:
                if hasattr(st.session_state, 'crawler_status'):
                    st.session_state.crawler_status = status
            except Exception:
                print(f"狀態: {status}")
        
        if stage == 'connected':
            safe_log("📡 SSE 連接已建立")
        elif stage == 'fetch_start':
            safe_log(f"🔍 開始爬取 @{data.get('username')} 的貼文...")
        elif stage == 'fetch_progress':
            current = data.get('current', 0)
            total = data.get('total', 1)
            progress = data.get('progress', 0)
            safe_set_progress(progress)
            safe_log(f"📊 進度: {current}/{total} 篇貼文 ({progress:.1%})")
        elif stage == 'post_parsed':
            # 🔥 新增：每解析一個貼文的詳細進度
            current = data.get('current', 0)
            total = data.get('total', 1)
            progress = data.get('progress', 0)
            post_id = data.get('post_id', '')
            content_preview = data.get('content_preview', '')
            likes = data.get('likes', 0)
            safe_set_progress(progress)
            safe_log(f"✅ 解析貼文 {post_id[-8:]}: {likes}讚 - {content_preview}")
        elif stage == 'batch_parsed':
            # 🔥 新增：每批解析完成的進度
            batch_size = data.get('batch_size', 0)
            current = data.get('current', 0)
            total = data.get('total', 1)
            query_name = data.get('query_name', '')
            safe_log(f"📦 從 {query_name} 解析了 {batch_size} 則貼文，總計: {current}/{total}")
        elif stage == 'fill_views_start':
            safe_log("👁️ 開始補齊瀏覽數...")
        elif stage == 'views_fetched':
            # 🔥 新增：每獲取一個瀏覽數的詳細進度
            post_id = data.get('post_id', '')
            views_formatted = data.get('views_formatted', '0')
            safe_log(f"👁️ 貼文 {post_id[-8:]}: {views_formatted} 次瀏覽")
        elif stage == 'fill_views_completed':
            safe_log("✅ 瀏覽數補齊完成")
        elif stage == 'completed':
            safe_log("🎉 爬取任務完成！")
            safe_set_progress(1.0)
        elif stage == 'error':
            error_msg = data.get('error', '未知錯誤')
            safe_log(f"❌ 爬取錯誤: {error_msg}")
            safe_set_status('error')
        elif stage == 'heartbeat':
            # 心跳事件，不顯示
            pass

    def _render_crawler_progress(self):
        """渲染爬蟲進度"""
        st.subheader("📊 爬取狀態")
        
        target = st.session_state.crawler_target
        username = target["username"]
        max_posts = target["max_posts"]
        
        # 真實進度（來自 SSE）
        progress = st.session_state.get('crawler_progress', 0)
        status = st.session_state.get('crawler_status', 'running')
        
        # 🔥 新增：檢查並更新進度
        progress_updated = self._check_and_update_progress()
        
        # 顯示進度條
        if status == 'running':
            if progress > 0:
                st.progress(progress)
                estimated_posts = int(progress * max_posts)
                st.text(f"進度: ~{estimated_posts}/{max_posts} 篇貼文 ({progress:.1%})")
            else:
                st.progress(0.0)
                st.text("初始化中...")
            
            # 顯示當前狀態
            task_id = st.session_state.get('crawler_task_id', 'N/A')
            st.info(f"🔍 正在爬取 @{username} 的貼文... (Task ID: {task_id[:8]})")
            st.info("📡 使用 SSE 即時更新進度，請查看下方日誌了解詳細狀態。")
            
            # 自動刷新每3秒或有進度更新時立即刷新
            if progress_updated:
                st.rerun()
            else:
                time.sleep(3)
                st.rerun()
            
        elif status == 'completed':
            st.progress(1.0)
            st.success("✅ 爬取完成！")
            final_data = st.session_state.get('final_data')
            if final_data:
                posts_count = len(final_data.get("posts", []))
                st.text(f"成功獲取 {posts_count} 篇貼文")
                
        elif status == 'error':
            st.progress(0.0)
            st.error("❌ 爬取過程中發生錯誤")
        
        # 顯示日誌
        self._render_crawler_logs()
    
    def _render_crawler_results(self):
        """渲染爬蟲結果"""
        st.subheader("📋 爬取結果")
        
        final_data = st.session_state.get('final_data')
        if not final_data:
            st.warning("沒有爬取到數據")
            return
        
        # 結果摘要
        posts = final_data.get("posts", [])
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("批次 ID", final_data.get('batch_id', 'N/A'))
        with col2:
            st.metric("用戶", final_data.get('username', 'N/A'))
        with col3:
            st.metric("總數量", final_data.get('total_count', 0))
        with col4:
            st.metric("成功爬取", len(posts))
        
        # 下載按鈕
        self._render_download_button(final_data)
        
        # 貼文預覽
        if posts:
            st.subheader("📝 貼文預覽")
            
            for i, post in enumerate(posts[:5]):  # 只顯示前5篇
                with st.expander(f"貼文 {i+1} - {post.get('post_id', 'N/A')}", expanded=i < 2):
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        # 內容
                        content = post.get('content', '')
                        if content:
                            st.write("**內容:**")
                            st.write(content[:200] + "..." if len(content) > 200 else content)
                        
                        # 媒體 URL
                        if post.get('media_urls'):
                            st.write("**媒體:**")
                            for media_url in post['media_urls'][:3]:  # 最多顯示3個
                                st.write(f"🔗 {media_url}")
                    
                    with col2:
                        st.write("**統計:**")
                        st.write(f"👍 {post.get('likes_count', 0)}")
                        st.write(f"💬 {post.get('comments_count', 0)}")
                        st.write(f"🔄 {post.get('reposts_count', 0)}")
                        
                        st.write("**詳情:**")
                        st.write(f"🔗 [原文]({post.get('url', '#')})")
                        st.write(f"📅 {post.get('created_at', 'N/A')}")
    
    def _render_download_button(self, final_data: Dict[str, Any]):
        """渲染下載按鈕"""
        st.subheader("💾 下載結果")
        
        # 準備下載數據
        json_str = json.dumps(final_data, indent=2, ensure_ascii=False)
        filename = f"threads_crawl_{final_data.get('username', 'unknown')}_{int(time.time())}.json"
        
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            st.download_button(
                label="📥 下載 JSON",
                data=json_str,
                file_name=filename,
                mime="application/json",
                use_container_width=True
            )
        
        with col2:
            # 顯示文件大小
            file_size = len(json_str.encode('utf-8'))
            st.metric("文件大小", f"{file_size / 1024:.1f} KB")
        
        with col3:
            st.info(f"📁 文件名: {filename}")
    
    def _render_crawler_logs(self):
        """渲染爬蟲日誌"""
        if st.session_state.get('crawler_logs'):
            with st.expander("📋 爬取日誌", expanded=False):
                for log in st.session_state.crawler_logs[-10:]:  # 最多顯示10條
                    st.text(log)
    

    
    def _reset_crawler(self):
        """重置爬蟲狀態"""
        keys_to_reset = [
            'crawler_status', 'crawler_target', 'crawler_logs', 
            'crawler_events', 'final_data', 'crawler_step', 'crawler_progress'
        ]
        for key in keys_to_reset:
            if key in st.session_state:
                del st.session_state[key]