"""
Threads 爬蟲組件
基於 test_playwright_agent.py 的真實功能
"""

import streamlit as st
import httpx
import json
import os
import asyncio
import time
from pathlib import Path
from typing import Dict, Any, Optional


class ThreadsCrawlerComponent:
    def __init__(self):
        self.agent_url = "http://localhost:8006/v1/playwright/crawl"
        self.orchestrator_url = "http://localhost:8000"  # 🔥 添加SSE服務器URL
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
            target = st.session_state.get('crawler_target', {})
            username = target.get('username', 'unknown')
            max_posts = target.get('max_posts', 0)
            current_progress = st.session_state.get('crawler_progress', 0)
            
            # 顯示當前進度概覽
            col1, col2 = st.columns([3, 1])
            with col1:
                st.info(f"🔄 正在爬取 @{username} 的貼文...")
                if current_progress > 0 and max_posts > 0:
                    estimated = int(current_progress * max_posts)
                    st.write(f"📊 進度: {estimated}/{max_posts} 篇 ({current_progress:.1%})")
                else:
                    st.write("📊 準備中...")
            
            with col2:
                st.metric("進度", f"{current_progress:.1%}")
            
            st.info("💡 **即時進度反饋**：請查看左側邊欄下方的「📊 爬蟲進度」區域，每2秒自動更新！")
            
            # 顯示最近的幾條日誌
            logs = st.session_state.get('crawler_logs', [])
            if logs:
                st.subheader("📝 最近活動")
                for log in logs[-3:]:  # 最近3條
                    st.write(f"• {log}")
            
            # 🔥 即時貼文預覽（主內容區域）
            posts = st.session_state.get('crawler_posts', [])
            if posts:
                st.markdown("---")
                st.subheader("📝 即時貼文預覽")
                
                # 顯示最新的3個貼文
                recent_posts = posts[-3:]
                
                for post in recent_posts:
                    # 使用卡片樣式顯示貼文
                    with st.container():
                        st.markdown(f"**🆔 {post.get('summary', 'N/A')}** `{post.get('timestamp', 'N/A')}`")
                        
                        # 顯示貼文詳情
                        col1, col2 = st.columns([2, 1])
                        with col1:
                            # 內容預覽
                            content_preview = post.get('content_preview', post.get('content', ''))
                            if content_preview:
                                st.write(f"💬 {content_preview}")
                            else:
                                st.write("💬 無內容")
                            
                            # 媒體信息
                            images_count = post.get('images_count', 0)
                            videos_count = post.get('videos_count', 0)
                            if images_count > 0 or videos_count > 0:
                                st.write(f"📸 圖片: {images_count} | 🎥 影片: {videos_count}")
                        
                        with col2:
                            # 🔥 完整的統計數據
                            likes_count = post.get('likes_count', 0)
                            comments_count = post.get('comments_count', 0)
                            reposts_count = post.get('reposts_count', 0)
                            shares_count = post.get('shares_count', 0)
                            views_count = post.get('views_count', 0)
                            calculated_score = post.get('calculated_score', 0)
                            
                            st.write(f"❤️ 讚: {likes_count:,}")
                            st.write(f"💬 留言: {comments_count:,}")
                            st.write(f"🔄 轉發: {reposts_count:,}")
                            st.write(f"📤 分享: {shares_count:,}")
                            st.write(f"👁️ 瀏覽: {views_count:,}")
                            st.write(f"⭐ 分數: {calculated_score:.1f}")
                        
                        st.markdown("---")
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
                max_value=200,
                value=10,
                help="建議：10篇穩定，50篇可能較慢，最多200篇",
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
        st.session_state.crawler_posts = []  # 貼文列表
        st.session_state.crawler_events = []
        st.session_state.final_data = None
        st.session_state.crawler_progress = 0
        st.session_state.crawler_current_work = "正在初始化爬蟲..."
        
        # 🔥 立即記錄啟動日誌，確保側邊欄有內容顯示
        st.session_state.crawler_logs.append("🚀 爬蟲已啟動，正在初始化...")
        st.session_state.crawler_logs.append(f"🎯 目標: @{username} ({max_posts} 篇)")
        
        # 🔥 生成任務ID，確保 has_task 條件滿足
        import uuid
        task_id = str(uuid.uuid4())
        st.session_state.crawler_task_id = task_id
        
        # 🔥 初始化調試信息
        if 'debug_messages' not in st.session_state:
            st.session_state.debug_messages = []
        st.session_state.debug_messages.append(f"🚀 爬蟲啟動: task_id={task_id[:8]}")
        
        # 🔥 立即創建進度文件，確保側邊欄條件檢查生效
        import tempfile
        import json
        import time
        import os
        
        progress_file = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix=f'_{task_id}.json')
        progress_file_path = progress_file.name
        progress_file.close()
        st.session_state.crawler_progress_file = progress_file_path
        
        # 寫入初始進度
        initial_progress = {
            "stage": "initialization",
            "progress": 0.0,
            "status": "running",
            "current_work": "正在初始化爬蟲...",
            "task_id": task_id,
            "timestamp": time.time()
        }
        with open(progress_file_path, 'w') as f:
            json.dump(initial_progress, f)
            f.flush()
            os.fsync(f.fileno())
        
        print(f"🔥 爬蟲啟動: status={st.session_state.crawler_status}, task_id={task_id[:8]}, target={username}")
        print(f"🔥 進度文件已創建: {progress_file_path}")
        
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
        st.success("🚀 爬蟲已啟動！即將開始爬取...")
        
        # 🔥 修復：傳遞必要參數到後台線程，避免session_state跨線程問題
        task_id = st.session_state.crawler_task_id
        progress_file = st.session_state.crawler_progress_file
        
        def crawler_worker():
            """後台爬蟲工作線程"""
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._execute_crawler_safe(username, max_posts, auth_content, task_id, progress_file))
            except Exception as e:
                # 直接寫入進度文件，避免session_state問題
                import json
                import time
                error_data = {
                    "stage": "error",
                    "error": str(e),
                    "timestamp": time.time()
                }
                try:
                    with open(progress_file, 'w', encoding='utf-8') as f:
                        json.dump(error_data, f, ensure_ascii=False)
                        f.flush()
                except:
                    pass
                print(f"❌ 爬蟲執行失敗: {e}")
        
        # 在後台線程啟動爬蟲，避免阻塞UI
        import threading
        threading.Thread(target=crawler_worker, daemon=True).start()
        st.info("⚡ 爬蟲已在後台啟動，請查看左側邊欄的進度更新！")
    
    async def _execute_crawler_safe(self, username: str, max_posts: int, auth_content: dict, task_id: str, progress_file: str):
        """執行真實的爬蟲任務，線程安全版本，不依賴session_state"""
        import requests
        import json
        import time
        
        print(f"🔥 使用已設置的 task_id: {task_id[:8]}")
        
        # 寫入初始狀態到進度文件
        def write_progress(stage, **kwargs):
            data = {"stage": stage, "timestamp": time.time(), **kwargs}
            try:
                with open(progress_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False)
                    f.flush()
            except Exception as e:
                print(f"❌ 寫入進度文件失敗: {e}")
        
        payload = {
            "username": username,
            "max_posts": max_posts,
            "auth_json_content": auth_content,
            "task_id": task_id  # 確保 Playwright Agent 使用這個 task_id
        }
        
        try:
            timeout = httpx.Timeout(600.0)  # 10分鐘超時（支持更多貼文爬取）
            async with httpx.AsyncClient(timeout=timeout) as client:
                write_progress("crawler_start", message="🚀 啟動爬蟲並開始 SSE 進度監聽...")
                
                # 啟動 SSE 監聽（在背景執行）
                self._start_sse_listener_safe(task_id, progress_file)
                
                # 觸發爬蟲（同步調用）
                response = await client.post(self.agent_url, json=payload)
                
                if response.status_code != 200:
                    error_msg = f"❌ API 請求失敗，狀態碼: {response.status_code}"
                    write_progress("error", error=error_msg, response_text=response.text)
                    print(error_msg)
                    return

                # 解析最終結果
                try:
                    final_data = response.json()
                    write_progress("api_success", message="✅ 成功收到最終爬取結果！")
                    
                    # 🔥 調試：檢查收到的數據格式
                    data_type = type(final_data).__name__
                    data_keys = list(final_data.keys()) if isinstance(final_data, dict) else "非字典"
                    posts_exists = "posts" in final_data if isinstance(final_data, dict) else False
                    posts_count = len(final_data.get("posts", [])) if isinstance(final_data, dict) else 0
                    
                    write_progress("api_debug", 
                        data_type=data_type, 
                        data_keys=str(data_keys), 
                        posts_exists=posts_exists, 
                        posts_count=posts_count
                    )
                    
                    print(f"🔥 調試final_data: type={data_type}, keys={data_keys}, posts={posts_exists}, count={posts_count}")
                    
                    # 將最終數據寫入進度文件，供UI讀取
                    write_progress("final_data_received", 
                        final_data=final_data,
                        username=username,
                        task_id=task_id
                    )
                    
                except json.JSONDecodeError as e:
                    write_progress("json_error", error=f"無法解析響應 JSON: {e}")
                    
        except Exception as e:
            write_progress("general_error", error=str(e))
            print(f"❌ 爬蟲執行失敗: {e}")
    
    def _start_sse_listener_safe(self, task_id: str, progress_file: str):
        """線程安全的SSE監聽器，不依賴session_state"""
        import threading
        
        def sse_worker():
            """SSE監聽工作線程"""
            self._run_sse_listener_safe(task_id, progress_file)
        
        # 啟動SSE監聽線程
        threading.Thread(target=sse_worker, daemon=True).start()
        print(f"🔥 SSE監聽器已啟動: {task_id[:8]}")
    
    def _run_sse_listener_safe(self, task_id: str, progress_file: str):
        """運行SSE監聽器，線程安全版本"""
        import requests
        import json
        
        sse_url = f"{self.orchestrator_url.rstrip('/')}/stream/{task_id}"
        
        try:
            with requests.get(sse_url, stream=True, timeout=600) as response:
                if response.status_code == 200:
                    print(f"📡 SSE 連接成功: {response.status_code}")
                    
                    for line in response.iter_lines():
                        if line:
                            line_str = line.decode('utf-8')
                            print(f"🔍 收到 SSE 行: {line_str}")
                            
                            if line_str.startswith('data: '):
                                try:
                                    data_str = line_str[6:]  # 移除 "data: " 前綴
                                    data = json.loads(data_str)
                                    print(f"📊 解析成功: {data}")
                                    
                                    # 寫入進度文件
                                    with open(progress_file, 'w', encoding='utf-8') as f:
                                        json.dump(data, f, ensure_ascii=False)
                                        f.flush()
                                    print("💾 進度已寫入文件")
                                    
                                except json.JSONDecodeError as e:
                                    print(f"❌ SSE JSON解析失敗: {e}")
                else:
                    print(f"❌ SSE 連接失敗: {response.status_code}")
                    
        except Exception as e:
            print(f"❌ SSE 監聽錯誤: {e}")

    def _start_sse_listener(self, task_id: str):
        """啟動 SSE 監聽器（在背景執行）"""
        import tempfile
        import json
        import os
        
        # 🔥 使用已創建的進度文件路徑
        progress_file_path = st.session_state.crawler_progress_file
        print(f"🔥 使用已創建的進度文件: {progress_file_path}")
        
        def sse_worker():
            try:
                import requests
                import json
                
                orchestrator_url = f"http://localhost:8000/stream/{task_id}"
                print(f"📡 連接 SSE: {orchestrator_url}")
                
                with requests.get(orchestrator_url, stream=True, timeout=600) as response:
                    if response.status_code == 200:
                        print(f"📡 SSE 連接成功: {response.status_code}")
                        
                        # 🔥 修復 #3: 一連上就先寫 "connected"，避免競速
                        try:
                            with open(progress_file_path, 'w') as f:
                                json.dump({"stage": "connected", "message": "SSE 連接已建立"}, f)
                                f.flush()  # 🔥 修復 #2: 強制刷新緩衝區
                                os.fsync(f.fileno())  # 🔥 修復 #2: 強制寫入磁碟
                            print(f"✅ 初始連接文件已寫入: {progress_file_path}")
                        except Exception as e:
                            print(f"⚠️ 寫入初始連接文件錯誤: {e}")
                        
                        for line in response.iter_lines():
                            if line:
                                line_str = line.decode('utf-8').strip()
                                print(f"🔍 收到 SSE 行: {line_str}")  # 調試輸出
                                
                                # 🔥 修復 #1: 改進 SSE 資料行格式解析
                                if line_str.startswith('data:'):
                                    payload_txt = line_str.split(':', 1)[1].strip()
                                    if payload_txt:
                                        try:
                                            data = json.loads(payload_txt)
                                            print(f"📊 解析成功: {data}")  # 調試輸出
                                            
                                            # 🔥 修復 #2: 改進檔案寫入同步
                                            try:
                                                with open(progress_file_path, 'w') as f:
                                                    json.dump(data, f)
                                                    f.flush()  # 強制刷新緩衝區
                                                    os.fsync(f.fileno())  # 強制寫入磁碟
                                                print(f"💾 進度已寫入文件")  # 調試輸出
                                            except Exception as e:
                                                print(f"⚠️ 寫入進度文件錯誤: {e}")
                                            
                                            # 如果收到完成或錯誤事件，結束監聽
                                            if data.get('stage') in ['completed', 'error']:
                                                break
                                                
                                        except json.JSONDecodeError as e:
                                            print(f"❌ JSON 解析失敗: {e}, 原始文本: {payload_txt}")
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
            # 🔥 更詳細的調試信息
            if not progress_file_path:
                print("🔍 沒有進度文件路徑")
            else:
                print(f"🔍 進度文件不存在: {progress_file_path}")
            return False
            
        try:
            # 🔥 修復：簡化檢查邏輯，每次都讀取文件
            # 檢查文件修改時間
            current_mtime = os.path.getmtime(progress_file_path)
            last_mtime = st.session_state.get('crawler_progress_mtime', 0)
            
            print(f"🔍 檔案時間檢查: current={current_mtime}, last={last_mtime}")
            
            # 🔥 修復：更寬鬆的更新檢查，避免錯過更新
            if current_mtime > last_mtime:
                st.session_state.crawler_progress_mtime = current_mtime
                print(f"🔥 檢測到進度文件更新: {current_mtime}")
                file_updated = True
            else:
                # 即使時間相同，也嘗試讀取一次（用於調試）
                print(f"🔍 檔案時間未變，但仍嘗試讀取")
                file_updated = False
            
            # 讀取進度數據
            with open(progress_file_path, 'r') as f:
                data = json.load(f)
            
            print(f"🔥 讀取到進度數據: stage={data.get('stage')}, progress={data.get('progress')}")
            
            # 更新 UI 狀態
            self._update_ui_from_progress(data)
            
            # 🔥 修復：只要成功讀取就返回True，確保UI更新
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
            if not hasattr(st.session_state, 'debug_messages'):
                st.session_state.debug_messages = []
            st.session_state.debug_messages.append(f"📡 SSE 連接已建立 (connected)")
            
        elif stage == 'fetch_start':
            username = data.get('username', '')
            st.session_state.crawler_logs.append(f"🔍 開始爬取 @{username} 的貼文...")
            st.session_state.crawler_current_work = f"正在連接 Threads API..."
            
        elif stage == 'post_parsed':
            current = data.get('current', 0)
            total = data.get('total', 1)
            progress = data.get('progress', 0)
            post_id = data.get('post_id', '')
            content_preview = data.get('content_preview', '')
            
            # 🔥 提取完整的統計數據
            likes_count = data.get('likes_count', 0)
            comments_count = data.get('comments_count', 0)
            reposts_count = data.get('reposts_count', 0)
            shares_count = data.get('shares_count', 0)
            views_count = data.get('views_count', 0)
            calculated_score = data.get('calculated_score', 0)
            content = data.get('content', '')
            url = data.get('url', '')
            created_at = data.get('created_at', '')
            images_count = data.get('images_count', 0)
            videos_count = data.get('videos_count', 0)
            media_urls = data.get('media_urls', {})
            
            # 🔥 強制設置進度並添加調試信息
            st.session_state.crawler_progress = progress
            if not hasattr(st.session_state, 'debug_messages'):
                st.session_state.debug_messages = []
            st.session_state.debug_messages.append(f"🔥 設置進度: {progress:.1%} (post_parsed)")
            
            # 🔥 更新當前工作狀態
            st.session_state.crawler_current_work = f"已解析 {current}/{total} 篇貼文 - 正在解析下一篇..."
            st.session_state.crawler_logs.append(f"✅ 解析貼文 {post_id[-8:]}: {likes_count}讚 - {content_preview}")
            
            # 🔥 創建完整的貼文對象並添加到列表
            post_data = {
                'post_id': post_id,
                'summary': f"貼文 {post_id[-8:]}",
                'timestamp': created_at[:19] if created_at else "未知時間",
                'content': content,
                'content_preview': content_preview,
                'url': url,
                'likes_count': likes_count,
                'comments_count': comments_count,
                'reposts_count': reposts_count,
                'shares_count': shares_count,
                'views_count': views_count,
                'calculated_score': calculated_score,
                'images_count': images_count,
                'videos_count': videos_count,
                'media_urls': media_urls
            }
            
            # 確保 crawler_posts 列表存在
            if 'crawler_posts' not in st.session_state:
                st.session_state.crawler_posts = []
            
            # 添加到貼文列表（避免重複）
            existing_ids = [p.get('post_id') for p in st.session_state.crawler_posts]
            if post_id not in existing_ids:
                st.session_state.crawler_posts.append(post_data)
            
        elif stage == 'batch_parsed':
            batch_size = data.get('batch_size', 0)
            current = data.get('current', 0)
            total = data.get('total', 1)
            query_name = data.get('query_name', '')
            st.session_state.crawler_current_work = f"已處理 {query_name} 批次，獲得 {batch_size} 篇新貼文..."
            st.session_state.crawler_logs.append(f"📦 從 {query_name} 解析了 {batch_size} 則貼文，總計: {current}/{total}")
            
        elif stage == 'fill_views_start':
            st.session_state.crawler_current_work = "正在補齊瀏覽數數據..."
            st.session_state.crawler_logs.append("👁️ 開始補齊瀏覽數...")
            
        elif stage == 'views_fetched':
            post_id = data.get('post_id', '')
            views_formatted = data.get('views_formatted', '0')
            st.session_state.crawler_current_work = f"正在獲取貼文 {post_id[-8:]} 的瀏覽數..."
            st.session_state.crawler_logs.append(f"👁️ 貼文 {post_id[-8:]}: {views_formatted} 次瀏覽")
            
        elif stage == 'fill_views_completed':
            st.session_state.crawler_current_work = "瀏覽數補齊完成，準備最終處理..."
            st.session_state.crawler_logs.append("✅ 瀏覽數補齊完成")
            
        elif stage == 'completed':
            st.session_state.crawler_current_work = "🎉 爬取任務已完成！"
            st.session_state.crawler_logs.append("🎉 爬取任務完成！")
            st.session_state.crawler_progress = 1.0
            
            # 🔥 修復：從crawler_posts創建final_data
            crawler_posts = st.session_state.get('crawler_posts', [])
            if crawler_posts and not st.session_state.get('final_data'):
                # 獲取目標信息
                target = st.session_state.get('crawler_target', {})
                username = target.get('username', 'unknown')
                task_id = st.session_state.get('crawler_task_id', 'unknown')
                
                # 轉換crawler_posts為final_data格式
                ui_posts = []
                for post in crawler_posts:
                    ui_post = {
                        "post_id": post.get("post_id", ""),
                        "username": post.get("username", username),
                        "content": post.get("content", ""),
                        "created_at": post.get("timestamp", ""),
                        "likes_count": post.get("likes_count", 0),
                        "comments_count": post.get("comments_count", 0),
                        "reposts_count": post.get("reposts_count", 0),
                        "shares_count": post.get("shares_count", 0),
                        "views_count": post.get("views_count", 0),
                        "calculated_score": post.get("calculated_score", 0),
                        "url": post.get("url", ""),
                        "source": "threads",
                        "processing_stage": "completed",
                        "media_urls": post.get("media_urls", [])
                    }
                    ui_posts.append(ui_post)
                
                # 創建final_data
                import time
                final_data = {
                    "batch_id": task_id,
                    "username": username,
                    "processing_stage": "completed",
                    "total_count": len(ui_posts),
                    "posts": ui_posts,
                    "crawl_timestamp": time.time(),
                    "agent_version": "1.0.0"
                }
                
                st.session_state.final_data = final_data
                st.session_state.crawler_logs.append(f"🔧 從SSE數據創建final_data ({len(ui_posts)} 篇貼文)")
                print(f"🔥 SSE完成：創建final_data，包含 {len(ui_posts)} 篇貼文")
            
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
        """渲染爬蟲進度（適合側邊欄，包含標題）"""
        self._render_crawler_progress_content_only()
    
    def _render_crawler_progress_content_only(self):
        """渲染爬蟲進度內容（不包含標題，避免重複）"""
        target = st.session_state.get('crawler_target', {})
        username = target.get("username", "N/A")
        max_posts = target.get("max_posts", 0)
        
        # 檢查並更新進度
        progress_updated = self._check_and_update_progress()
        progress = st.session_state.get('crawler_progress', 0)
        status = st.session_state.get('crawler_status', 'idle')
        current_work = st.session_state.get('crawler_current_work', '')
        
        # 緊湊顯示
        st.write(f"👤 @{username}")
        
        # 進度條
        if progress > 0:
            # 🔥 確保進度值在有效範圍內 [0.0, 1.0]
            safe_progress = max(0.0, min(1.0, progress))
            st.progress(safe_progress)
            if max_posts > 0:
                estimated = int(progress * max_posts)
                st.write(f"📊 {estimated}/{max_posts} ({progress:.1%})")
            else:
                st.write(f"📊 {progress:.1%}")
        else:
            st.write("📊 準備中...")
        
        # 狀態
        status_emoji = {"idle": "⚪", "running": "🟡", "completed": "🟢", "error": "🔴"}
        st.write(f"{status_emoji.get(status, '⚪')} {status}")
        
        # 當前工作
        if current_work:
            st.write(f"🔄 {current_work}")
        else:
            # 如果沒有當前工作但狀態是running，顯示默認信息
            if status == 'running':
                st.write("🔄 正在處理中...")
        
        # 最近日誌（緊湊顯示）
        logs = st.session_state.get('crawler_logs', [])
        if logs:
            with st.expander("📝 進度日誌", expanded=True):
                for log in logs[-5:]:  # 最近5條
                    st.write(f"• {log}")
        
        # 🔥 實時更新提示
        if status == 'running':
            st.info("⏱️ 每2秒自動更新進度")
        
        # 調試信息（可選）
        if st.session_state.get('show_debug_sidebar', True):  # 🔥 修正key名稱，默認為True
            with st.expander("🔧 調試信息", expanded=True):  # 🔥 默認展開
                st.write(f"🆔 任務: {st.session_state.get('crawler_task_id', 'N/A')[-8:]}")
                st.write(f"🔄 更新: {progress_updated}")
                
                # 進度文件狀態
                progress_file = st.session_state.get('crawler_progress_file')
                if progress_file and os.path.exists(progress_file):
                    st.write("✅ 進度文件存在")
                else:
                    st.write("❌ 進度文件不存在")
            st.write(f"📊 進度值: {progress:.1%}")
            st.write(f"🔄 已更新: {progress_updated}")
            st.write(f"🆔 Task ID: {st.session_state.get('crawler_task_id', 'N/A')}")
            st.write(f"📁 進度文件: {st.session_state.get('crawler_progress_file', 'N/A')}")
            st.write(f"⏰ 最後修改: {st.session_state.get('crawler_progress_mtime', 'N/A')}")
            st.write(f"📋 狀態: {st.session_state.get('crawler_status', 'N/A')}")
            st.write(f"📝 當前工作: {st.session_state.get('crawler_current_work', 'N/A')}")
            
            # 顯示調試消息
            debug_messages = st.session_state.get('debug_messages', [])
            if debug_messages:
                st.write("🔍 最新調試消息:")
                for msg in debug_messages[-10:]:  # 顯示最近10條
                    st.write(f"  {msg}")
            
            # 顯示進度文件內容
            progress_file = st.session_state.get('crawler_progress_file')
            if progress_file and os.path.exists(progress_file):
                try:
                    with open(progress_file, 'r') as f:
                        file_content = json.load(f)
                    st.write("📄 進度文件內容:")
                    st.json(file_content)
                except Exception as e:
                    st.write(f"❌ 無法讀取進度文件: {e}")
            else:
                st.write("❌ 進度文件不存在")
        
        # 側邊欄不顯示即時貼文預覽（已移到主內容區域）
        
        # 🔥 狀態相關顯示
        if status == 'running':
            st.markdown("---")
            st.subheader("📊 爬取狀態")
            
            # 顯示當前進度詳情
            
            if progress > 0:
                estimated_posts = int(progress * max_posts)
                st.success(f"📊 進度: {estimated_posts}/{max_posts} 篇貼文 ({progress:.1%})")
            else:
                st.info(f"🔄 初始化中... 當前進度: {progress:.1%}")
            
            # 📊 即時工作狀態報告
            task_id = st.session_state.get('crawler_task_id', 'N/A')
            current_work = st.session_state.get('crawler_current_work', '正在初始化...')
            
            col1, col2 = st.columns([2, 1])
            with col1:
                st.write(f"🔍 **正在爬取 @{username}**")
                st.info(f"⚡ **當前工作**: {current_work}")
            with col2:
                st.write(f"🆔 Task: `{task_id[:8]}...`")
            
            # 已移到上面總是顯示的區域
            
            # 自動刷新
            if progress_updated:
                st.success(f"🔄 有進度更新，立即刷新")
            st.rerun()
        else:
                st.info(f"⏳ 無進度更新，st.fragment會自動刷新")
                # 🔥 移除 time.sleep() - 不能在UI線程中阻塞！
                # 依賴 st.fragment(run_every=2) 自動刷新
        
        # 完整日誌（可選展開查看）
        if st.session_state.get('crawler_logs'):
            with st.expander("📋 查看完整日誌", expanded=False):
                for log in st.session_state.crawler_logs[-10:]:  # 最多顯示10條
                    st.text(log)
    
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
            
            # 🔥 排序方式選擇
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"**共 {len(posts)} 篇貼文，顯示前 10 篇**")
            with col2:
                sort_method = st.selectbox(
                    "排序方式",
                    options=["score", "date", "views", "likes"],
                    format_func=lambda x: {
                        "score": "🏆 權重排序",
                        "date": "📅 日期排序", 
                        "views": "👁️ 觀看排序",
                        "likes": "❤️ 按讚排序"
                    }[x],
                    key="post_sort_method"
                )
            
            # 🔥 根據選擇的排序方式對所有貼文進行排序
            if sort_method == "score":
                # 權重排序 (calculated_score 高到低)
                sorted_posts = sorted(posts, 
                                     key=lambda p: p.get('calculated_score', 0), 
                                     reverse=True)
            elif sort_method == "date":
                # 日期排序 (最新在前)
                sorted_posts = sorted(posts, 
                                     key=lambda p: p.get('created_at', '') or '', 
                                     reverse=True)
            elif sort_method == "views":
                # 觀看排序 (views_count 高到低)
                sorted_posts = sorted(posts, 
                                     key=lambda p: p.get('views_count', 0), 
                                     reverse=True)
            elif sort_method == "likes":
                # 按讚排序 (likes_count 高到低)
                sorted_posts = sorted(posts, 
                                     key=lambda p: p.get('likes_count', 0), 
                                     reverse=True)
            else:
                # 默認權重排序
                sorted_posts = sorted(posts, 
                                     key=lambda p: p.get('calculated_score', 0), 
                                     reverse=True)
            
            # 顯示排序說明
            sort_descriptions = {
                "score": f"📊 按權重分數排序 (最高: {sorted_posts[0].get('calculated_score', 0):.1f})",
                "date": f"📅 按發布時間排序 (最新: {sorted_posts[0].get('created_at', 'N/A')[:10]})",
                "views": f"👁️ 按觀看數排序 (最多: {sorted_posts[0].get('views_count', 0):,} 次)",
                "likes": f"❤️ 按按讚數排序 (最多: {sorted_posts[0].get('likes_count', 0):,} 讚)"
            }
            st.info(sort_descriptions.get(sort_method, ""))
            
            for i, post in enumerate(sorted_posts[:10]):  # 顯示前10篇
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
                        st.write(f"❤️ 讚: {post.get('likes_count', 0):,}")
                        st.write(f"💬 留言: {post.get('comments_count', 0):,}")
                        st.write(f"🔄 轉發: {post.get('reposts_count', 0):,}")
                        st.write(f"📤 分享: {post.get('shares_count', 0):,}")
                        st.write(f"👁️ 瀏覽: {post.get('views_count', 0):,}")
                        st.write(f"⭐ 分數: {post.get('calculated_score', 0):.1f}")
                        
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
            'crawler_status', 'crawler_target', 'crawler_logs', 'crawler_posts',
            'crawler_events', 'final_data', 'crawler_step', 'crawler_progress',
            'crawler_task_id', 'crawler_progress_file', 'crawler_progress_mtime',
            'crawler_current_work', 'debug_messages'
        ]
        for key in keys_to_reset:
            if key in st.session_state:
                del st.session_state[key]
        
        # 🔥 強制重置輸入框（解決卡住問題）
        st.session_state.crawler_username = ""
        st.session_state.crawler_max_posts = 10