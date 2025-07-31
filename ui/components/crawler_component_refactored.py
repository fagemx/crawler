"""
Threads 爬蟲組件 - 重構版本
結合精簡版架構與完整功能
"""

import streamlit as st
import httpx
import json
import os
import uuid
import tempfile
import threading
import time
import requests
from pathlib import Path
from typing import Dict, Any, Optional

class ThreadsCrawlerComponent:
    def __init__(self):
        self.agent_url = "http://localhost:8006/v1/playwright/crawl"
        self.sse_url = "http://localhost:8000/stream"
        # 使用統一的配置管理
        from common.config import get_auth_file_path
        self.auth_file_path = get_auth_file_path(from_project_root=True)
    
    # ---------- 1. 公用工具 ----------
    def _write_progress(self, path: str, data: Dict[str, Any]):
        """線程安全的進度寫入"""
        with open(path, "w", encoding="utf-8") as f:
            json.dump({**data, "timestamp": time.time()}, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())

    def _read_progress(self, path: str) -> Dict[str, Any]:
        """讀取進度文件"""
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}

    # ---------- 2. 初始化 / Reset ----------
    def _init_state(self):
        """初始化session state"""
        if "crawler_status" not in st.session_state:
            st.session_state.update({
                'crawler_status': 'idle',
                'crawler_logs': [],
                'crawler_posts': [],
                'crawler_progress': 0.0,
                'crawler_progress_file': '',
                'crawler_task_id': '',
                'crawler_target': {},
                'final_data': {},
                'crawler_current_work': ''
            })

    def _reset_crawler(self):
        """重置爬蟲狀態"""
        # 清理臨時文件
        if st.session_state.get('crawler_progress_file'):
            try:
                os.unlink(st.session_state.crawler_progress_file)
            except:
                pass
        
        # 重置狀態
        for key in ['crawler_status', 'crawler_logs', 'crawler_posts', 
                   'crawler_progress', 'crawler_progress_file', 'crawler_task_id',
                   'crawler_target', 'final_data', 'crawler_current_work']:
            if key in st.session_state:
                del st.session_state[key]
        
        self._init_state()

    # ---------- 3. 後台爬蟲 ----------
    def _crawler_worker(self, username: str, max_posts: int, auth: Dict[str, Any], task_id: str, progfile: str):
        """後台爬蟲工作線程 - 使用async/await調用API"""
        import asyncio
        
        async def _async_crawler():
            try:
                # 初始化進度
                self._write_progress(progfile, {
                    "stage": "initialization",
                    "progress": 0.0,
                    "status": "running",
                    "current_work": "正在初始化爬蟲..."
                })

                # 啟動 SSE 監聽線程
                threading.Thread(
                    target=self._sse_listener, 
                    args=(task_id, progfile), 
                    daemon=True
                ).start()

                # 調用後端爬蟲 - 使用async/await
                payload = {
                    'username': username,
                    'max_posts': max_posts,
                    'auth_json_content': auth,
                    'task_id': task_id
                }
                
                self._write_progress(progfile, {
                    "stage": "api_calling",
                    "progress": 0.1,
                    "status": "running",
                    "current_work": "正在調用後端API..."
                })
                
                timeout = httpx.Timeout(600.0)
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(self.agent_url, json=payload)
                
                if response.status_code != 200:
                    raise Exception(f"API調用失敗，狀態碼: {response.status_code}")
                
                # 爬蟲完成
                self._write_progress(progfile, {
                    "stage": "api_completed",
                    "progress": 1.0,
                    "status": "completed",
                    "final_data": response.json()
                })
                
            except Exception as e:
                self._write_progress(progfile, {
                    "stage": "error",
                    "error": str(e),
                    "status": "error",
                    "current_work": f"錯誤: {str(e)}"
                })
        
        # 運行async函數
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_async_crawler())

    def _sse_listener(self, task_id: str, progfile: str):
        """SSE 事件監聽線程"""
        url = f"{self.sse_url}/{task_id}"
        print(f"🔥 SSE監聽啟動: {url}")
        
        try:
            with requests.get(url, stream=True, timeout=600) as response:
                print(f"🔥 SSE連接成功，狀態碼: {response.status_code}")
                
                for line in response.iter_lines():
                    if line and line.startswith(b"data:"):
                        try:
                            data = json.loads(line[5:].decode().strip())
                            stage = data.get('stage', 'unknown')
                            print(f"🔥 收到SSE事件: {stage}")
                            
                            # 👉 統一寫入欄位：stage / progress / current_work
                            if stage == "post_parsed":
                                cur, tot = data.get("current", 0), data.get("total", 1)
                                progress = cur / tot if tot else 0
                                self._write_progress(
                                    progfile,
                                    dict(stage=stage,
                                         progress=progress,
                                         current_work=f"已解析 {cur}/{tot} 篇貼文")
                                )
                            elif stage == "batch_parsed":
                                self._write_progress(
                                    progfile,
                                    dict(stage=stage,
                                         current_work="批次解析完成，正在填充觀看數...")
                                )
                            elif stage == "fill_views_start":
                                self._write_progress(
                                    progfile,
                                    dict(stage=stage,
                                         current_work="正在填充觀看數據...")
                                )
                            else:
                                # 其餘事件直接寫
                                self._write_progress(progfile, dict(stage=stage))
                            
                            # 檢查是否完成
                            if stage in ("completed", "error"):
                                print(f"🔥 SSE監聽結束: {stage}")
                                break
                        except json.JSONDecodeError as e:
                            print(f"⚠️ JSON解析失敗: {e}")
                            continue
                            
        except Exception as e:
            print(f"❌ SSE連接失敗: {e}")
            self._write_progress(progfile, {
                "stage": "error",
                "error": f"SSE連接失敗: {str(e)}",
                "status": "error"
            })

    # ---------- 4. UI 渲染 ----------
    def render(self):
        """主渲染方法"""
        self._init_state()
        
        st.header("🕷️ Threads 內容爬蟲")
        st.markdown("基於 Playwright Agent 的真實 Threads 爬蟲，支持 SSE 實時進度顯示。")
        
        # 檢查認證文件
        if not self._check_auth_file():
            st.error("❌ 找不到認證檔案")
            st.info("請先執行: `python tests/threads_fetch/save_auth.py` 來產生認證檔案")
            return
        
        st.success("✅ 認證檔案已就緒")
        
        # 根據狀態渲染不同界面
        status = st.session_state.crawler_status
        
        if status == 'idle':
            self._render_config()
        elif status == 'running':
            self._render_progress()
        elif status == 'completed':
            self._render_results()
        elif status == 'error':
            self._render_error()

    def _check_auth_file(self) -> bool:
        """檢查認證文件是否存在"""
        return self.auth_file_path.exists()

    def _render_config(self):
        """渲染配置界面"""
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
        col1, col2 = st.columns([1, 1])
        
        with col1:
            if st.button("🚀 開始爬取", type="primary", use_container_width=True):
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
        # 讀取認證文件
        try:
            with open(self.auth_file_path, "r", encoding="utf-8") as f:
                auth_content = json.load(f)
        except Exception as e:
            st.error(f"❌ 無法讀取認證檔案: {e}")
            return

        # 設置session state
        task_id = str(uuid.uuid4())
        progress_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json").name
        
        st.session_state.update({
            'crawler_status': 'running',
            'crawler_target': {'username': username, 'max_posts': max_posts},
            'crawler_task_id': task_id,
            'crawler_progress_file': progress_file,
            'crawler_logs': [f"🚀 開始爬取 @{username} ({max_posts} 篇)"],
            'crawler_posts': [],
            'crawler_progress': 0.0,
            'final_data': {}
        })

        # 啟動後台工作線程 - 傳遞參數避免session_state跨線程問題
        threading.Thread(
            target=self._crawler_worker,
            args=(username, max_posts, auth_content, task_id, progress_file),
            daemon=True
        ).start()
        
        st.success("🚀 爬蟲已啟動！")
        st.rerun()

    def _render_progress(self):
        """渲染進度界面"""
        # 核心：檢查文件更新並觸發UI刷新
        progress_file = st.session_state.get('crawler_progress_file', '')
        
        if progress_file and os.path.exists(progress_file):
            pd = self._read_progress(progress_file)
            st.session_state.crawler_progress = pd.get("progress", 0.0)
            st.session_state.crawler_current_work = pd.get("current_work", "")

            if pd.get("stage") in ("api_completed", "completed"):
                st.session_state.crawler_status = "completed"
                st.session_state.final_data = pd.get("final_data", {})
                st.rerun()
            elif pd.get("stage") == "error":
                st.session_state.crawler_status = "error"
                st.rerun()

        # 顯示進度
        target = st.session_state.crawler_target
        username = target.get('username', 'unknown')
        max_posts = target.get('max_posts', 0)
        progress = st.session_state.crawler_progress
        current_work = st.session_state.crawler_current_work

        # 進度概覽
        col1, col2 = st.columns([3, 1])
        with col1:
            st.info(f"🔄 正在爬取 @{username} 的貼文...")
            if progress > 0 and max_posts > 0:
                estimated = int(progress * max_posts)
                st.write(f"📊 進度: {estimated}/{max_posts} 篇 ({progress:.1%})")
            else:
                st.write("📊 準備中...")
        
        with col2:
            st.metric("進度", f"{progress:.1%}")

        # 進度條
        st.progress(max(0.0, min(1.0, progress)))
        
        # 當前工作
        if current_work:
            st.write(f"🔄 {current_work}")

        # 即時貼文預覽
        posts = st.session_state.crawler_posts
        if posts:
            st.markdown("---")
            st.subheader("📝 即時貼文預覽")
            
            # 顯示最新的3個貼文
            recent_posts = posts[-3:]
            
            for post in recent_posts:
                with st.container():
                    st.markdown(f"**📝 {post.get('summary', 'N/A')}**")
                    
                    col1, col2 = st.columns([2, 1])
                    with col1:
                        content_preview = post.get('content_preview', post.get('content', ''))
                        if content_preview:
                            st.write(f"💬 {content_preview[:100]}...")
                        else:
                            st.write("💬 無內容")
                    
                    with col2:
                        likes = post.get('likes_count', 0)
                        views = post.get('views_count', 0)
                        st.write(f"❤️ {likes:,} | 👁️ {views:,}")

        # 自動更新提示和刷新按鈕
        col1, col2 = st.columns([3, 1])
        with col1:
            st.info("⏱️ 進度將自動更新，無需手動刷新")
        with col2:
            if st.button("🔄 刷新", key="refresh_progress"):
                st.rerun()
                
        # 定時刷新（每3秒）
        time.sleep(3)
        st.rerun()

    def _render_results(self):
        """渲染結果界面"""
        st.subheader("✅ 爬取完成")
        
        final_data = st.session_state.final_data
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
        if posts:
            username = final_data.get('username', 'threads_posts')
            json_str = json.dumps(final_data, ensure_ascii=False, indent=2)
            st.download_button(
                "📥 下載 JSON 檔案",
                data=json_str,
                file_name=f"{username}_posts.json",
                mime="application/json",
                use_container_width=True
            )

        # 貼文預覽 (帶排序)
        if posts:
            st.subheader("📝 貼文預覽")
            
            # 排序選項
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
                    }[x]
                )

            # 排序邏輯
            if sort_method == "score":
                sorted_posts = sorted(posts, key=lambda p: p.get('calculated_score', 0), reverse=True)
            elif sort_method == "date":
                sorted_posts = sorted(posts, key=lambda p: p.get('created_at', ''), reverse=True)
            elif sort_method == "views":
                sorted_posts = sorted(posts, key=lambda p: p.get('views_count', 0), reverse=True)
            elif sort_method == "likes":
                sorted_posts = sorted(posts, key=lambda p: p.get('likes_count', 0), reverse=True)

            # 顯示前10篇
            for i, post in enumerate(sorted_posts[:10], 1):
                with st.expander(f"#{i} {post.get('summary', 'N/A')}"):
                    col1, col2 = st.columns([2, 1])
                    
                    with col1:
                        content = post.get('content', '無內容')
                        st.write(f"**內容:** {content[:200]}...")
                    
                    with col2:
                        likes = post.get('likes_count', 0)
                        comments = post.get('comments_count', 0)
                        reposts = post.get('reposts_count', 0)
                        shares = post.get('shares_count', 0)
                        views = post.get('views_count', 0)
                        score = post.get('calculated_score', 0)
                        
                        st.write(f"❤️ 讚: {likes:,}")
                        st.write(f"💬 評論: {comments:,}")
                        st.write(f"🔄 轉發: {reposts:,}")
                        st.write(f"📤 分享: {shares:,}")
                        st.write(f"👁️ 觀看: {views:,}")
                        st.write(f"⭐ 分數: {score:.1f}")

        # 操作按鈕
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("🔄 重新爬取", use_container_width=True):
                self._reset_crawler()
                st.rerun()
        with col2:
            if st.button("🆕 爬取其他用戶", use_container_width=True):
                st.session_state.crawler_status = 'idle'
                st.rerun()

    def _render_error(self):
        """渲染錯誤界面"""
        st.error("❌ 爬蟲執行失敗")
        
        # 顯示錯誤詳情
        if st.session_state.crawler_progress_file:
            progress_data = self._read_progress(st.session_state.crawler_progress_file)
            error_msg = progress_data.get('error', '未知錯誤')
            st.write(f"**錯誤詳情:** {error_msg}")

        # 操作按鈕
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("🔄 重試", type="primary", use_container_width=True):
                target = st.session_state.crawler_target
                if target:
                    self._start_crawler(target.get('username', ''), target.get('max_posts', 10))
                else:
                    self._reset_crawler()
                    st.rerun()
        
        with col2:
            if st.button("🏠 返回", use_container_width=True):
                self._reset_crawler()
                st.rerun()