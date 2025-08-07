"""
Playwright 爬蟲組件 - 基於 Playwright Agent API
包含完整UI功能，與realtime_crawler_component.py相同，但使用Playwright Agent作為後端
"""

import streamlit as st
import asyncio
import json
import time
import threading
import httpx
import requests
import tempfile
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
import sys
import os

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

class PlaywrightCrawlerComponent:
    def __init__(self):
        self.is_running = False
        self.current_task = None
        self.agent_url = "http://localhost:8006/v1/playwright/crawl"
        self.sse_url = "http://localhost:8000/stream"  # SSE服務器URL
        # 使用統一的配置管理
        from common.config import get_auth_file_path
        self.auth_file_path = get_auth_file_path(from_project_root=True)
        
    def render(self):
        """渲染Playwright爬蟲組件"""
        st.header("🎭 Playwright 智能爬蟲")
        st.markdown("**基於 Playwright Agent API + 完整互動數據 + 資料庫整合**")
        
        # 檢查認證文件
        if not self._check_auth_file():
            st.error("❌ 找不到認證檔案")
            st.info("請先執行: `python tests/threads_fetch/save_auth.py` 來產生認證檔案")
            return
        
        st.success("✅ 認證檔案已就緒")
        
        # 參數設定區域
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("⚙️ 爬取設定")
            username = st.text_input(
                "目標帳號", 
                value="gvmonthly",
                help="要爬取的Threads帳號用戶名",
                key="playwright_username"
            )
            
            max_posts = st.number_input(
                "爬取數量", 
                min_value=1, 
                max_value=500, 
                value=50,
                help="要爬取的貼文數量",
                key="playwright_max_posts"
            )
            
            # 顯示爬取過程日誌（移到這裡，避免重新渲染影響）
            if 'playwright_crawl_logs' in st.session_state and st.session_state.playwright_crawl_logs:
                with st.expander("📋 爬取過程日誌", expanded=False):
                    # 顯示最後50行日誌
                    log_lines = st.session_state.playwright_crawl_logs[-50:] if len(st.session_state.playwright_crawl_logs) > 50 else st.session_state.playwright_crawl_logs
                    st.code('\n'.join(log_lines), language='text')
            
        with col2:
            col_title, col_refresh = st.columns([3, 1])
            with col_title:
                st.subheader("📊 資料庫統計")
            with col_refresh:
                if st.button("🔄 刷新", key="refresh_playwright_db_stats", help="刷新資料庫統計信息", type="secondary"):
                    # 清理可能的緩存狀態
                    if 'playwright_db_stats_cache' in st.session_state:
                        del st.session_state.playwright_db_stats_cache
                    st.success("🔄 正在刷新統計...")
                    st.rerun()  # 重新運行頁面來刷新統計
            
            self._display_database_stats()
        
        # 控制按鈕
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            if st.button("🚀 開始爬取", key="start_playwright"):
                with st.spinner("正在執行爬取..."):
                    self._execute_playwright_crawling(username, max_posts)
                
        with col2:
            # 載入CSV文件功能
            uploaded_file = st.file_uploader(
                "📁 載入CSV文件", 
                type=['csv'], 
                key="playwright_csv_uploader",
                help="上傳之前導出的CSV文件來查看結果"
            )
            if uploaded_file is not None:
                self._load_csv_file(uploaded_file)
        
        with col3:
            # 清除結果按鈕 (只在有結果時顯示)
            if 'playwright_results' in st.session_state:
                if st.button("🗑️ 清除結果", key="clear_playwright_results", help="清除當前顯示的結果"):
                    self._clear_results()
        
        # 結果顯示
        self._render_results_area()
    
    def _check_auth_file(self):
        """檢查認證檔案是否存在"""
        return self.auth_file_path.exists()
    
    def _write_progress(self, path: str, data: Dict[str, Any]):
        """線程安全寫入進度文件"""
        old: Dict[str, Any] = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    old = json.load(f)
            except Exception:
                pass

        # 合併邏輯
        stage_priority = {
            "initialization": 0, "fetch_start": 1, "post_parsed": 2,
            "batch_parsed": 3, "fill_views_start": 4, "fill_views_completed": 5,
            "api_completed": 6, "completed": 7, "error": 8
        }
        old_stage = old.get("stage", "")
        new_stage = data.get("stage", old_stage)
        if stage_priority.get(new_stage, 0) < stage_priority.get(old_stage, 0):
            data.pop("stage", None)

        if "progress" not in data and "progress" in old:
            data["progress"] = old["progress"]
        if "current_work" not in data and "current_work" in old:
            data["current_work"] = old["current_work"]

        merged = {**old, **data, "timestamp": time.time()}

        # 先寫到 tmp，再 atomic rename
        dir_ = os.path.dirname(path)
        os.makedirs(dir_, exist_ok=True)
        
        try:
            with tempfile.NamedTemporaryFile("w", delete=False, dir=dir_, suffix=".tmp", encoding='utf-8') as tmp:
                json.dump(merged, tmp, ensure_ascii=False)
                tmp.flush()
                os.fsync(tmp.fileno())
                tmp_path = tmp.name
            
            shutil.move(tmp_path, path)
        except Exception as e:
            print(f"❌ 寫入進度文件失敗: {e}")

    def _read_progress(self, path: str) -> Dict[str, Any]:
        """讀取進度文件"""
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    
    def _sse_listener(self, task_id: str, progfile: str):
        """SSE 事件監聽線程"""
        url = f"{self.sse_url}/{task_id}"
        self._add_log(f"🔥 SSE監聽啟動: {url}")
        
        try:
            with requests.get(url, stream=True, timeout=600) as response:  # 與原版相同的10分鐘超時
                print(f"🔥 SSE連接成功，狀態碼: {response.status_code}")
                
                current_cnt = 0
                total_cnt = None      # 第一次拿到再放進來
                for line in response.iter_lines():
                    if line and line.startswith(b"data:"):
                        try:
                            data = json.loads(line[5:].decode().strip())
                            stage = data.get('stage', 'unknown')
                            print(f"🔥 收到SSE事件: {stage}")
                            
                            # --- 通用事件處理 ---
                            # 對於所有事件，都準備一個基礎的 payload
                            payload = {'stage': stage}

                            # 提取工作描述
                            work_description = None
                            if "current_work" in data:
                                work_description = data["current_work"]
                            elif "message" in data:
                                work_description = data["message"]
                            
                            if work_description:
                                payload['current_work'] = work_description

                            # --- 針對性計算進度 (V2 - 分段權重) ---
                            PARSE_WEIGHT = 0.60   # 解析階段佔 60%
                            POST_PROCESS_W = 0.40   # 後處理佔 40%

                            if stage == "post_parsed":
                                current_cnt += 1
                                total_cnt = total_cnt or data.get("total") # 只要拿一次就好
                                
                                if total_cnt:
                                    unit_progress = min(1.0, current_cnt / total_cnt)
                                    payload['progress'] = unit_progress * PARSE_WEIGHT # 映射到 0% -> 60%
                                else:
                                    # 沒 total 時，給一個遞增但接近60%的假進度
                                    progress = min(PARSE_WEIGHT * 0.99, current_cnt * (PARSE_WEIGHT * 0.02))
                                    payload['progress'] = progress
                                payload['current_work'] = f"已解析 {current_cnt}/{total_cnt or '?'} 篇"
                            
                            elif stage == "fill_views_start":
                                payload["progress"] = PARSE_WEIGHT # 到達 60%
                                payload["current_work"] = "正在補齊瀏覽數..."

                            elif stage == "fill_views_completed":
                                payload["progress"] = PARSE_WEIGHT + POST_PROCESS_W * 0.75 # 60% + 30% = 90%
                                payload["current_work"] = "瀏覽數已補齊，準備收尾..."

                            elif stage in ("completed", "api_completed"):
                                payload["progress"] = 1.0
                                if not payload.get('current_work'):
                                    payload['current_work'] = "全部完成！"

                            elif stage == "fetch_progress" and "progress" in data:
                                payload['progress'] = max(0.0, min(1.0, float(data["progress"])))
                            
                            # 無論哪種事件，都用一個 write 完成
                            self._write_progress(progfile, payload)
                            
                            # 檢查是否完成
                            if stage in ("completed", "error"):
                                print(f"🔥 SSE監聽結束: {stage}")
                                break
                        except json.JSONDecodeError as e:
                            print(f"⚠️ JSON解析失敗: {e}")
                            continue
                            
        except Exception as e:
            self._add_log(f"❌ SSE連接失敗: {e}")
            self._write_progress(progfile, {
                "stage": "error",
                "error": f"SSE連接失敗: {str(e)}",
                "status": "error"
            })
    
    def _execute_playwright_crawling(self, username: str, max_posts: int):
        """執行 Playwright 爬蟲（使用SSE）"""
        if not username.strip():
            st.error("請輸入目標帳號！")
            return
            
        try:
            st.info(f"🔄 正在透過 Playwright Agent 爬取 @{username}，預計需要較長時間...")
            
            # 初始化日誌
            st.session_state.playwright_crawl_logs = []
            
            # 生成唯一的任務ID和進度文件
            task_id = str(uuid.uuid4())
            progress_dir = Path("temp_progress")
            progress_dir.mkdir(exist_ok=True)
            progress_file = progress_dir / f"playwright_crawl_{task_id}.json"
            
            # 讀取認證文件
            try:
                with open(self.auth_file_path, "r", encoding="utf-8") as f:
                    auth_content = json.load(f)
            except Exception as e:
                st.error(f"❌ 讀取認證檔案失敗: {e}")
                return
            
            # 準備 API 請求的 payload
            payload = {
                "username": username,
                "max_posts": max_posts,
                "auth_json_content": auth_content,
                "task_id": task_id  # 添加任務ID以支持SSE
            }
            
            # 添加日誌
            self._add_log(f"🔧 準備爬取 @{username}...")
            self._add_log(f"📊 目標貼文數: {max_posts}")
            self._add_log(f"🆔 任務ID: {task_id}")
            self._add_log(f"🔗 API 端點: {self.agent_url}")
            self._add_log(f"📡 SSE 端點: {self.sse_url}")
            
            # 啟動SSE監聽線程
            sse_thread = threading.Thread(
                target=self._sse_listener,
                args=(task_id, str(progress_file)),
                daemon=True
            )
            sse_thread.start()
            
            # 顯示進度區域
            progress_container = st.empty()
            log_container = st.empty()
            
            with st.expander("📋 爬取過程日志", expanded=True):
                log_placeholder = st.empty()
                self._update_log_display(log_placeholder)
                
                # 啟動爬蟲任務
                self._add_log("🚀 發送API請求...")
                self._update_log_display(log_placeholder)
                
                # 使用異步方式發送請求但不等待完成
                asyncio.run(self._execute_async_api_request(payload))
                
                # 監控進度直到完成
                self._monitor_progress_with_display(
                    str(progress_file), 
                    progress_container, 
                    log_placeholder,
                    task_id
                )
                
        except Exception as e:
            st.error(f"❌ 執行錯誤：{str(e)}")
            st.session_state.playwright_error = str(e)
    
    async def _execute_async_api_request(self, payload):
        """異步發送API請求（不等待完成）"""
        try:
            timeout = httpx.Timeout(600.0)  # 10分鐘超時，與原版一致
            
            async with httpx.AsyncClient(timeout=timeout) as client:
                self._add_log("🚀 已發送異步API請求，等待SSE回應...")
                
                # 發送請求但在背景執行
                response = await client.post(self.agent_url, json=payload)
                
                if response.status_code != 200:
                    self._add_log(f"❌ API 請求失敗，狀態碼: {response.status_code}")
                    self._add_log(f"錯誤內容: {response.text}")
                    return None
                
                # 解析響應
                try:
                    final_data = response.json()
                    self._add_log("✅ API請求成功完成！")
                    return final_data
                except json.JSONDecodeError as e:
                    self._add_log(f"❌ 無法解析響應 JSON: {e}")
                    return None
                    
        except httpx.TimeoutException:
            self._add_log("❌ API請求超時（30分鐘）")
            return None
        except Exception as e:
            self._add_log(f"❌ API請求錯誤: {e}")
            return None
    
    def _monitor_progress_with_display(self, progress_file: str, progress_container, log_placeholder, task_id: str):
        """監控進度並更新UI顯示"""
        max_wait_time = 600  # 10分鐘最大等待時間，與SSE超時一致
        start_time = time.time()
        last_activity = start_time
        
        while True:
            current_time = time.time()
            
            # 檢查總超時
            if current_time - start_time > max_wait_time:
                self._add_log("❌ 爬蟲總超時（10分鐘），停止監控")
                break
            
            # 讀取進度
            progress_data = self._read_progress(progress_file)
            
            if progress_data:
                last_activity = current_time
                stage = progress_data.get("stage", "unknown")
                progress = progress_data.get("progress", 0.0)
                current_work = progress_data.get("current_work", "處理中...")
                
                # 更新進度顯示
                with progress_container.container():
                    st.subheader("📊 爬蟲進度")
                    
                    # 進度條
                    progress_percent = int(progress * 100)
                    st.progress(progress, text=f"{progress_percent}% - {current_work}")
                    
                    # 階段信息
                    stage_names = {
                        "initialization": "🔧 初始化",
                        "fetch_start": "🔍 開始爬取",
                        "post_parsed": "📝 解析貼文",
                        "batch_parsed": "📦 批次處理",
                        "fill_views_start": "👁️ 補充觀看數",
                        "fill_views_completed": "✅ 觀看數完成",
                        "api_completed": "🎯 API完成",
                        "completed": "🎉 全部完成",
                        "error": "❌ 發生錯誤"
                    }
                    
                    stage_display = stage_names.get(stage, f"🔄 {stage}")
                    st.info(f"**當前階段**: {stage_display}")
                    
                    if "error" in progress_data:
                        st.error(f"錯誤: {progress_data['error']}")
                
                # 更新日誌顯示
                self._update_log_display(log_placeholder)
                
                # 檢查是否完成
                if stage in ("completed", "api_completed"):
                    self._add_log("🎉 爬蟲任務完成！")
                    self._update_log_display(log_placeholder)
                    
                    # 處理完成後的結果
                    self._handle_crawl_completion(task_id, progress_data)
                    break
                elif stage == "error":
                    self._add_log("❌ 爬蟲任務失敗")
                    self._update_log_display(log_placeholder)
                    break
            else:
                # 檢查無活動超時（10分鐘沒有進度更新）
                if current_time - last_activity > 600:
                    self._add_log("⚠️ 長時間無進度更新，但繼續等待...")
                    last_activity = current_time  # 重設計時器
                    self._update_log_display(log_placeholder)
            
            # 短暫休眠後再檢查
            time.sleep(2)
    
    def _handle_crawl_completion(self, task_id: str, progress_data: Dict):
        """處理爬蟲完成後的結果"""
        try:
            self._add_log("🔄 正在獲取最終結果...")
            
            # 這裡需要從某個地方獲取實際的爬蟲結果
            # 可能需要調用一個獲取結果的API
            # 暫時先創建一個示例結果
            
            # 創建結果數據
            converted_results = {
                "crawl_id": f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}",
                "timestamp": datetime.now().isoformat(),
                "target_username": "unknown",  # 需要從某處獲取
                "crawler_type": "playwright",
                "total_processed": 0,
                "results": [],
                "source": "playwright_agent",
                "database_saved": False,
                "database_saved_count": 0
            }
            
            # 保存JSON文件
            json_file_path = self._save_json_results(converted_results)
            
            # 保存到session_state
            st.session_state.playwright_results = converted_results
            st.session_state.playwright_results_file = json_file_path
            
            # 自動保存到資料庫
            asyncio.run(self._save_to_database_async(converted_results))
            
            st.success(f"✅ 爬取完成！")
            
            # 清理資料庫統計緩存
            if 'playwright_db_stats_cache' in st.session_state:
                del st.session_state.playwright_db_stats_cache
            
            st.info("📊 爬取結果已自動保存，您可以點擊右側「🔄 刷新」查看更新的統計")
            st.balloons()
            
        except Exception as e:
            self._add_log(f"❌ 處理完成結果時發生錯誤: {e}")
    
    def _convert_playwright_results(self, playwright_data):
        """轉換 Playwright API 結果為專用格式"""
        posts = playwright_data.get("posts", [])
        username = playwright_data.get("username", "")
        
        # 轉換為 Playwright 專用格式
        converted_results = []
        for post in posts:
            # 檢查數據格式並轉換
            result = {
                "post_id": post.get("post_id", ""),
                "url": post.get("url", ""),
                "content": post.get("content", ""),
                "views": str(post.get("views_count", "") or ""),
                "likes": str(post.get("likes_count", "") or ""),
                "comments": str(post.get("comments_count", "") or ""),
                "reposts": str(post.get("reposts_count", "") or ""),
                "shares": str(post.get("shares_count", "") or ""),
                "source": "playwright_agent",
                "crawler_type": "playwright",  # 標記爬蟲類型
                "success": True,
                "has_views": bool(post.get("views_count")),
                "has_content": bool(post.get("content")),
                "has_likes": bool(post.get("likes_count")),
                "has_comments": bool(post.get("comments_count")),
                "has_reposts": bool(post.get("reposts_count")),
                "has_shares": bool(post.get("shares_count")),
                "content_length": len(post.get("content", "")),
                "extracted_at": datetime.now().isoformat(),
                "created_at": post.get("created_at", ""),
                "username": username
            }
            converted_results.append(result)
        
        # 生成唯一ID（時間戳 + 隨機字符）
        import uuid
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_id = str(uuid.uuid4())[:8]
        
        # 包裝為 Playwright 專用結構
        return {
            "crawl_id": f"{timestamp}_{unique_id}",
            "timestamp": datetime.now().isoformat(),
            "target_username": username,
            "crawler_type": "playwright",
            "max_posts": len(posts),
            "total_processed": len(posts),
            "api_success_count": len(posts),
            "api_failure_count": 0,
            "overall_success_rate": 100.0 if posts else 0.0,
            "timing": {
                "total_time": 0,  # Playwright API 不提供詳細計時
                "url_collection_time": 0,
                "content_extraction_time": 0
            },
            "results": converted_results,
            "source": "playwright_agent",
            "database_saved": False,  # 將在保存後更新
            "database_saved_count": 0
        }
    
    async def _save_to_database_async(self, results_data):
        """異步保存結果到 Playwright 專用資料表"""
        try:
            from common.db_client import DatabaseClient
            
            db = DatabaseClient()
            await db.init_pool()
            
            try:
                results = results_data.get("results", [])
                target_username = results_data.get("target_username", "")
                crawl_id = results_data.get("crawl_id", "")
                
                if results and target_username:
                    saved_count = 0
                    
                    async with db.get_connection() as conn:
                        # 創建 Playwright 專用資料表（如果不存在）
                        await conn.execute("""
                            CREATE TABLE IF NOT EXISTS playwright_post_metrics (
                                id SERIAL PRIMARY KEY,
                                username VARCHAR(255) NOT NULL,
                                post_id VARCHAR(255) NOT NULL,
                                url TEXT,
                                content TEXT,
                                views_count INTEGER,
                                likes_count INTEGER,
                                comments_count INTEGER,
                                reposts_count INTEGER,
                                shares_count INTEGER,
                                source VARCHAR(100) DEFAULT 'playwright_agent',
                                crawler_type VARCHAR(50) DEFAULT 'playwright',
                                crawl_id VARCHAR(255),
                                created_at TIMESTAMP,
                                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                UNIQUE(username, post_id, crawler_type)
                            )
                        """)
                        
                        # 創建索引（如果不存在）
                        await conn.execute("""
                            CREATE INDEX IF NOT EXISTS idx_playwright_username_created 
                            ON playwright_post_metrics(username, created_at DESC)
                        """)
                        
                        await conn.execute("""
                            CREATE INDEX IF NOT EXISTS idx_playwright_crawl_id 
                            ON playwright_post_metrics(crawl_id)
                        """)
                        
                        # 插入數據
                        for result in results:
                            try:
                                # 解析數字字段
                                views_count = self._parse_number_safe(result.get('views', ''))
                                likes_count = self._parse_number_safe(result.get('likes', ''))
                                comments_count = self._parse_number_safe(result.get('comments', ''))
                                reposts_count = self._parse_number_safe(result.get('reposts', ''))
                                shares_count = self._parse_number_safe(result.get('shares', ''))
                                
                                # 使用 UPSERT 避免重複
                                await conn.execute("""
                                    INSERT INTO playwright_post_metrics (
                                        username, post_id, url, content, 
                                        views_count, likes_count, comments_count, reposts_count, shares_count,
                                        source, crawler_type, crawl_id, created_at
                                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW())
                                    ON CONFLICT (username, post_id, crawler_type) 
                                    DO UPDATE SET
                                        url = EXCLUDED.url,
                                        content = EXCLUDED.content,
                                        views_count = EXCLUDED.views_count,
                                        likes_count = EXCLUDED.likes_count,
                                        comments_count = EXCLUDED.comments_count,
                                        reposts_count = EXCLUDED.reposts_count,
                                        shares_count = EXCLUDED.shares_count,
                                        crawl_id = EXCLUDED.crawl_id,
                                        fetched_at = CURRENT_TIMESTAMP
                                """, 
                                    target_username,
                                    result.get('post_id', ''),
                                    result.get('url', ''),
                                    result.get('content', ''),
                                    views_count,
                                    likes_count,
                                    comments_count,
                                    reposts_count,
                                    shares_count,
                                    'playwright_agent',
                                    'playwright',
                                    crawl_id
                                )
                                saved_count += 1
                                
                            except Exception as e:
                                self._add_log(f"⚠️ 保存單個貼文失敗 {result.get('post_id', 'N/A')}: {e}")
                                continue
                        
                        # 更新 Playwright 爬取檢查點表
                        await conn.execute("""
                            CREATE TABLE IF NOT EXISTS playwright_crawl_state (
                                id SERIAL PRIMARY KEY,
                                username VARCHAR(255) UNIQUE NOT NULL,
                                latest_post_id VARCHAR(255),
                                total_crawled INTEGER DEFAULT 0,
                                last_crawl_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                crawl_id VARCHAR(255)
                            )
                        """)
                        
                        if results and saved_count > 0:
                            latest_post_id = results[0].get('post_id')
                            await conn.execute("""
                                INSERT INTO playwright_crawl_state (username, latest_post_id, total_crawled, crawl_id)
                                VALUES ($1, $2, $3, $4)
                                ON CONFLICT (username)
                                DO UPDATE SET
                                    latest_post_id = EXCLUDED.latest_post_id,
                                    total_crawled = playwright_crawl_state.total_crawled + EXCLUDED.total_crawled,
                                    last_crawl_at = CURRENT_TIMESTAMP,
                                    crawl_id = EXCLUDED.crawl_id
                            """, target_username, latest_post_id, saved_count, crawl_id)
                    
                    # 更新結果狀態
                    results_data["database_saved"] = True
                    results_data["database_saved_count"] = saved_count
                    
                    self._add_log(f"💾 已保存 {saved_count} 個貼文到 Playwright 專用資料表")
                    
            finally:
                await db.close_pool()
                
        except Exception as e:
            self._add_log(f"⚠️ 資料庫保存警告: {e}")
            # 不阻止主要流程，但記錄警告
    
    def _parse_number_safe(self, value):
        """安全解析數字字符串"""
        try:
            if not value or value == 'N/A':
                return None
            # 移除非數字字符（除了小數點）
            clean_value = str(value).replace(',', '').replace(' ', '')
            if 'K' in clean_value:
                return int(float(clean_value.replace('K', '')) * 1000)
            elif 'M' in clean_value:
                return int(float(clean_value.replace('M', '')) * 1000000)
            elif 'B' in clean_value:
                return int(float(clean_value.replace('B', '')) * 1000000000)
            else:
                return int(float(clean_value))
        except:
            return None
    
    def _save_json_results(self, results_data):
        """保存結果為JSON文件，使用指定格式"""
        try:
            # 創建 playwright_results 目錄
            results_dir = Path("playwright_results")
            results_dir.mkdir(exist_ok=True)
            
            # 生成文件名：crawl_data_20250803_121452_934d52b1.json
            crawl_id = results_data.get("crawl_id", "unknown")
            filename = f"crawl_data_{crawl_id}.json"
            json_file_path = results_dir / filename
            
            # 保存JSON文件
            with open(json_file_path, 'w', encoding='utf-8') as f:
                json.dump(results_data, f, ensure_ascii=False, indent=2)
            
            self._add_log(f"💾 結果已保存: {json_file_path}")
            return json_file_path
            
        except Exception as e:
            self._add_log(f"⚠️ 保存JSON文件失敗: {e}")
            return None
    
    def _add_log(self, message):
        """添加日誌消息"""
        if 'playwright_crawl_logs' not in st.session_state:
            st.session_state.playwright_crawl_logs = []
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}"
        st.session_state.playwright_crawl_logs.append(log_message)
    
    def _update_log_display(self, log_placeholder):
        """更新日誌顯示"""
        if 'playwright_crawl_logs' in st.session_state:
            log_lines = st.session_state.playwright_crawl_logs[-30:]  # 顯示最後30行
            log_placeholder.code('\n'.join(log_lines), language='text')
    
    def _load_csv_file(self, uploaded_file):
        """載入CSV文件並轉換為結果格式"""
        try:
            import pandas as pd
            import io
            
            # 讀取CSV文件
            content = uploaded_file.getvalue()
            df = pd.read_csv(io.StringIO(content.decode('utf-8-sig')))
            
            # 檢查CSV格式是否正確（更靈活的驗證）
            # 核心必要欄位
            core_required = ['username', 'post_id', 'content']
            missing_core = [col for col in core_required if col not in df.columns]
            
            if missing_core:
                st.error(f"❌ CSV格式不正確，缺少核心欄位: {', '.join(missing_core)}")
                return
            
            # 檢查可選欄位，如果沒有則提供預設值
            optional_columns = ['views', 'likes_count', 'comments_count', 'reposts_count', 'shares_count']
            for col in optional_columns:
                if col not in df.columns:
                    if col == 'views':
                        df[col] = df.get('views_count', 0)  # 嘗試使用 views_count 作為 views
                    else:
                        df[col] = 0  # 預設值為 0
            
            st.info(f"✅ 成功載入CSV，包含 {len(df)} 筆記錄")
            
            # 轉換為結果格式
            results = []
            for _, row in df.iterrows():
                # 轉換數據並處理空值
                views = str(row.get('views', '')).strip()
                likes = str(row.get('likes', '')).strip()
                comments = str(row.get('comments', '')).strip()
                reposts = str(row.get('reposts', '')).strip()
                shares = str(row.get('shares', '')).strip()
                content = str(row.get('content', '')).strip()
                
                result = {
                    'username': str(row.get('username', '')),
                    'post_id': str(row.get('post_id', '')),
                    'content': content,
                    'views': views,
                    'likes': likes,
                    'comments': comments,
                    'reposts': reposts,
                    'shares': shares,
                    'url': str(row.get('url', '')),
                    'source': str(row.get('source', 'csv_import')),
                    'created_at': str(row.get('created_at', '')),
                    'fetched_at': str(row.get('fetched_at', '')),
                    'success': True,
                    # 添加has_*欄位以兼容顯示邏輯
                    'has_views': bool(views and views != 'nan' and views != ''),
                    'has_content': bool(content and content != 'nan' and content != ''),
                    'has_likes': bool(likes and likes != 'nan' and likes != ''),
                    'has_comments': bool(comments and comments != 'nan' and comments != ''),
                    'has_reposts': bool(reposts and reposts != 'nan' and reposts != ''),
                    'has_shares': bool(shares and shares != 'nan' and shares != ''),
                    'content_length': len(content) if content else 0,
                    'extracted_at': datetime.now().isoformat()
                }
                results.append(result)
            
            # 保存到會話狀態
            st.session_state.playwright_results = {
                'results': results,
                'total_count': len(results),
                'username': results[0]['username'] if results else '',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'source': f"CSV文件: {uploaded_file.name}"
            }
            
            st.success(f"✅ 成功載入 {len(results)} 筆記錄")
            st.info(f"📊 來源: {uploaded_file.name}")
            
        except Exception as e:
            st.error(f"❌ 載入CSV文件失敗: {str(e)}")
    
    def _clear_results(self):
        """清除當前結果"""
        if 'playwright_results' in st.session_state:
            del st.session_state.playwright_results
        if 'playwright_results_file' in st.session_state:
            del st.session_state.playwright_results_file
        if 'playwright_error' in st.session_state:
            del st.session_state.playwright_error
        if 'latest_playwright_csv_file' in st.session_state:
            del st.session_state.latest_playwright_csv_file
        st.success("🗑️ 結果已清除")
        st.rerun()  # 重新運行頁面來刷新UI
    
    def _render_results_area(self):
        """渲染結果區域"""
        if 'playwright_results' in st.session_state:
            self._show_results()
        elif 'playwright_error' in st.session_state:
            st.error(f"❌ 爬取錯誤：{st.session_state.playwright_error}")
        else:
            st.info("👆 點擊「開始爬取」來開始，或上傳CSV文件查看之前的結果")
    
    def _show_results(self):
        """顯示爬取結果"""
        # 從session state獲取結果（可能是字典格式）
        playwright_results = st.session_state.playwright_results
        
        # 檢查results的格式，如果是字典則提取results列表
        if isinstance(playwright_results, dict):
            results = playwright_results.get('results', [])
        else:
            results = playwright_results if playwright_results else []
        
        st.subheader("📊 爬取結果")
        
        # 確保results是列表
        if not isinstance(results, list):
            st.error("❌ 結果格式錯誤，請重新載入")
            return
        
        # 基本統計
        total_posts = len(results)
        successful_views = len([r for r in results if isinstance(r, dict) and r.get('has_views')])
        successful_content = len([r for r in results if isinstance(r, dict) and r.get('has_content')])
        successful_likes = len([r for r in results if isinstance(r, dict) and r.get('has_likes')])
        successful_comments = len([r for r in results if isinstance(r, dict) and r.get('has_comments')])
        
        # 統計指標
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("總貼文數", total_posts)
        with col2:
            st.metric("觀看數成功", f"{successful_views}/{total_posts}")
        with col3:
            st.metric("內容成功", f"{successful_content}/{total_posts}")
        with col4:
            st.metric("互動數據", f"{successful_likes}/{total_posts}")
        
        # 成功率指標
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            view_rate = (successful_views / total_posts * 100) if total_posts > 0 else 0
            st.metric("觀看數成功率", f"{view_rate:.1f}%")
        with col2:
            content_rate = (successful_content / total_posts * 100) if total_posts > 0 else 0
            st.metric("內容成功率", f"{content_rate:.1f}%")
        with col3:
            like_rate = (successful_likes / total_posts * 100) if total_posts > 0 else 0
            st.metric("按讚數成功率", f"{like_rate:.1f}%")
        with col4:
            comment_rate = (successful_comments / total_posts * 100) if total_posts > 0 else 0
            st.metric("留言數成功率", f"{comment_rate:.1f}%")
        
        # 詳細結果表格
        if st.checkbox("📋 顯示詳細結果", key="show_playwright_detailed_results"):
            self._show_detailed_table(results)
        
        # 資料庫狀態和備用保存
        if isinstance(playwright_results, dict):
            db_saved = playwright_results.get('database_saved', False)
            saved_count = playwright_results.get('database_saved_count', 0)
            if db_saved:
                st.success(f"✅ 已保存到資料庫 ({saved_count} 個貼文)")
            else:
                # 顯示備用保存選項
                col_info, col_save = st.columns([3, 1])
                with col_info:
                    st.info("ℹ️ 爬蟲通常會自動保存到資料庫。如果統計中沒有看到新數據，您可以使用備用保存功能")
                with col_save:
                    if st.button("💾 備用保存", key="save_playwright_to_database", help="手動保存到資料庫（備用功能）"):
                        self._save_results_to_database()
        else:
            st.info("💡 Playwright 爬取模式會自動保存到資料庫並更新統計")

        st.divider()
        
        # 下載和導出按鈕
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if st.button("💾 下載JSON", key="download_playwright_json"):
                self._show_json_download_button()
        
        with col2:
            if st.button("📊 導出CSV", key="export_playwright_csv"):
                self._show_csv_export_options()
        
        with col3:
            if st.button("📈 歷史分析", key="export_playwright_history"):
                self._show_export_history_options()
        
        with col4:
            if st.button("🔍 更多導出", key="more_playwright_exports"):
                self._show_advanced_export_options()
    
    def _show_json_download_button(self):
        """顯示JSON下載按鈕"""
        if 'playwright_results' in st.session_state:
            try:
                # 將結果轉換為JSON格式
                json_content = json.dumps(
                    st.session_state.playwright_results, 
                    ensure_ascii=False, 
                    indent=2
                )
                
                # 生成下載文件名（包含時間戳）
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                download_filename = f"playwright_crawl_results_{timestamp}.json"
                
                # 使用 st.download_button 提供下載
                st.download_button(
                    label="💾 下載JSON",
                    data=json_content,
                    file_name=download_filename,
                    mime="application/json",
                    help="下載爬取結果JSON文件到您的下載資料夾",
                    key="download_playwright_json_btn"
                )
                
            except Exception as e:
                st.error(f"❌ 準備下載文件失敗: {e}")
        else:
            st.button("💾 下載JSON", disabled=True, help="暫無可下載的結果文件")
    
    def _show_csv_export_options(self):
        """顯示CSV導出選項"""
        # 復用原有的CSV導出邏輯，但使用playwright結果
        # 這裡簡化實現
        if 'playwright_results' not in st.session_state:
            st.error("❌ 沒有可導出的結果")
            return
        
        with st.expander("📊 CSV導出選項", expanded=True):
            st.write("**選擇排序方式（建議按觀看數排序）**")
            
            sort_options = {
                "觀看數 (高→低)": "views",
                "按讚數 (高→低)": "likes", 
                "留言數 (高→低)": "comments",
                "轉發數 (高→低)": "reposts",
                "分享數 (高→低)": "shares",
                "貼文ID (A→Z)": "post_id",
                "原始順序 (不排序)": "none"
            }
            
            selected_sort = st.selectbox(
                "排序方式",
                options=list(sort_options.keys()),
                index=0,  # 預設選擇觀看數排序
                help="選擇CSV文件中數據的排序方式，建議選擇觀看數以便分析最受歡迎的貼文",
                key="playwright_sort_selector"
            )
            
            if st.button("📥 生成CSV", key="export_playwright_csv_generate"):
                sort_by = sort_options[selected_sort]
                self._export_current_to_csv(sort_by)
            
            # 檢查是否有生成好的CSV可以下載
            self._show_csv_download_if_available()
    
    def _export_current_to_csv(self, sort_by: str = 'views'):
        """導出當次結果到CSV"""
        try:
            import pandas as pd
            
            # 獲取結果數據
            playwright_results = st.session_state.playwright_results
            if isinstance(playwright_results, dict):
                results = playwright_results.get('results', [])
            else:
                results = playwright_results if playwright_results else []
            
            if not results:
                st.error("❌ 沒有可導出的結果")
                return
            
            # 轉換為DataFrame
            df_data = []
            for r in results:
                df_data.append({
                    'username': r.get('username', ''),
                    'post_id': r.get('post_id', ''),
                    'url': r.get('url', ''),
                    'content': r.get('content', ''),
                    'views': r.get('views', ''),
                    'likes': r.get('likes', ''),
                    'comments': r.get('comments', ''),
                    'reposts': r.get('reposts', ''),
                    'shares': r.get('shares', ''),
                    'source': r.get('source', ''),
                    'created_at': r.get('created_at', ''),
                    'fetched_at': r.get('extracted_at', '')
                })
            
            df = pd.DataFrame(df_data)
            
            # 排序（簡化版本）
            if sort_by != 'none' and sort_by in df.columns:
                # 對於數字欄位，需要先轉換
                if sort_by in ['views', 'likes', 'comments', 'reposts', 'shares']:
                    # 簡單的數字轉換（實際應用中可能需要更複雜的處理）
                    df[f'{sort_by}_numeric'] = pd.to_numeric(df[sort_by].str.replace(r'[^\d.]', '', regex=True), errors='coerce')
                    df = df.sort_values(f'{sort_by}_numeric', ascending=False)
                    df = df.drop(columns=[f'{sort_by}_numeric'])
                else:
                    df = df.sort_values(sort_by)
            
            # 生成CSV文件
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            csv_filename = f"playwright_crawl_results_{timestamp}.csv"
            
            # 保存文件
            csv_content = df.to_csv(index=False, encoding='utf-8-sig')
            
            # 保存CSV文件路徑到會話狀態
            st.session_state.latest_playwright_csv_file = csv_content
            st.session_state.latest_playwright_csv_filename = csv_filename
            
            st.success(f"✅ CSV生成成功！")
            st.info(f"📊 包含 {len(df)} 筆記錄")
            
        except Exception as e:
            st.error(f"❌ CSV生成失敗: {str(e)}")
    
    def _show_csv_download_if_available(self):
        """顯示CSV下載按鈕（如果有可用的CSV文件）"""
        if 'latest_playwright_csv_file' in st.session_state:
            csv_content = st.session_state.latest_playwright_csv_file
            filename = st.session_state.get('latest_playwright_csv_filename', 'playwright_results.csv')
            
            st.download_button(
                label="📥 下載CSV文件",
                data=csv_content,
                file_name=filename,
                mime="text/csv",
                help="下載CSV文件到您的下載資料夾",
                key="download_playwright_csv_file_btn"
            )
    
    def _show_export_history_options(self):
        """顯示歷史導出選項（簡化版本）"""
        st.info("📈 歷史分析功能與 realtime_crawler_component.py 共用，請在資料庫統計中查看歷史數據")
    
    def _show_advanced_export_options(self):
        """顯示進階導出選項（簡化版本）"""
        st.info("🔍 進階導出功能與 realtime_crawler_component.py 共用")
    
    def _show_detailed_table(self, results: List[Dict]):
        """顯示詳細結果表格"""
        st.subheader("📋 詳細結果")
        
        # 準備表格數據
        table_data = []
        for r in results:
            table_data.append({
                "貼文ID": r.get('post_id', 'N/A'),
                "觀看數": r.get('views', 'N/A'),
                "按讚數": r.get('likes', 'N/A'),
                "留言數": r.get('comments', 'N/A'),
                "轉發數": r.get('reposts', 'N/A'),
                "分享數": r.get('shares', 'N/A'),
                "內容預覽": (r.get('content', '')[:50] + "...") if r.get('content') else 'N/A',
                "來源": r.get('source', 'N/A')
            })
        
        # 顯示表格
        st.dataframe(
            table_data,
            use_container_width=True,
            height=400
        )
    
    def _display_database_stats(self):
        """顯示資料庫統計信息（復用 realtime_crawler_component.py 的邏輯）"""
        # 檢查是否有緩存的統計信息
        if 'playwright_db_stats_cache' in st.session_state:
            self._render_cached_stats(st.session_state.playwright_db_stats_cache)
            return
        
        try:
            # 使用 asyncio 和 subprocess 來獲取資料庫統計
            import subprocess
            import json
            import sys
            import os
            
            # 創建一個臨時腳本來獲取 Playwright 資料庫統計
            script_content = '''
import asyncio
import sys
import os
import json
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from common.db_client import DatabaseClient

async def get_playwright_database_stats():
    db = DatabaseClient()
    try:
        await db.init_pool()
        
        # 獲取所有用戶的統計信息
        async with db.get_connection() as conn:
            # 檢查 Playwright 資料表是否存在
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'playwright_post_metrics'
                )
            """)
            
            if not table_exists:
                print(json.dumps({"total_stats": {}, "user_stats": []}))
                return
            
            # 統計每個用戶的貼文數量
            user_stats = await conn.fetch("""
                SELECT 
                    username,
                    COUNT(*) as post_count,
                    MAX(created_at) as latest_crawl,
                    MIN(created_at) as first_crawl,
                    MAX(crawl_id) as latest_crawl_id
                FROM playwright_post_metrics 
                GROUP BY username 
                ORDER BY post_count DESC, latest_crawl DESC
                LIMIT 20
            """)
            
            # 總體統計
            total_stats = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total_posts,
                    COUNT(DISTINCT username) as total_users,
                    MAX(created_at) as latest_activity,
                    COUNT(DISTINCT crawl_id) as total_crawls
                FROM playwright_post_metrics
            """)
            
            stats = {
                "total_stats": dict(total_stats) if total_stats else {},
                "user_stats": [dict(row) for row in user_stats] if user_stats else []
            }
            
            print(json.dumps(stats, default=str))
            
    except Exception as e:
        print(json.dumps({"error": str(e)}))
    finally:
        await db.close_pool()

if __name__ == "__main__":
    asyncio.run(get_playwright_database_stats())
'''
            
            # 將腳本寫入臨時文件
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                f.write(script_content)
                temp_script = f.name
            
            try:
                # 執行腳本獲取統計信息
                result = subprocess.run(
                    [sys.executable, temp_script],
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                    timeout=10
                )
                
                if result.returncode == 0 and result.stdout.strip():
                    stats = json.loads(result.stdout.strip())
                    
                    if "error" in stats:
                        st.error(f"❌ 資料庫錯誤: {stats['error']}")
                        return
                    
                    # 保存到緩存
                    st.session_state.playwright_db_stats_cache = stats
                    
                    # 渲染統計信息
                    self._render_cached_stats(stats)
                    
                else:
                    st.warning("⚠️ 無法獲取資料庫統計信息")
                    if result.stderr:
                        st.text(f"錯誤: {result.stderr}")
                        
            finally:
                # 清理臨時文件
                try:
                    os.unlink(temp_script)
                except:
                    pass
                    
        except Exception as e:
            st.error(f"❌ 獲取統計信息失敗: {str(e)}")
    
    def _render_cached_stats(self, stats):
        """渲染 Playwright 專用緩存統計信息"""
        # 顯示總體統計
        total_stats = stats.get("total_stats", {})
        if total_stats:
            st.info(f"""
            **🎭 Playwright 爬蟲統計**
            - 📊 總貼文數: {total_stats.get('total_posts', 0):,}
            - 👥 已爬取用戶: {total_stats.get('total_users', 0)} 個
            - 🔄 總爬取次數: {total_stats.get('total_crawls', 0):,}
            - ⏰ 最後活動: {str(total_stats.get('latest_activity', 'N/A'))[:16] if total_stats.get('latest_activity') else 'N/A'}
            """)
        
        # 顯示用戶統計
        user_stats = stats.get("user_stats", [])
        if user_stats:
            st.write("**👥 各用戶統計 (Playwright):**")
            
            # 使用表格顯示
            import pandas as pd
            df_data = []
            for user in user_stats:
                latest = str(user.get('latest_crawl', 'N/A'))[:16] if user.get('latest_crawl') else 'N/A'
                crawl_id = user.get('latest_crawl_id', 'N/A')[:12] + '...' if user.get('latest_crawl_id') else 'N/A'
                df_data.append({
                    "用戶名": f"@{user.get('username', 'N/A')}",
                    "貼文數": f"{user.get('post_count', 0):,}",
                    "最後爬取": latest,
                    "最新爬取ID": crawl_id
                })
            
            if df_data:
                df = pd.DataFrame(df_data)
                st.dataframe(
                    df, 
                    use_container_width=True,
                    hide_index=True,
                    height=min(300, len(df_data) * 35 + 38)  # 動態高度
                )
                
                # 添加說明
                st.caption("💡 這是 Playwright 爬蟲的專用統計，與 Realtime 爬蟲分離儲存")
        else:
            st.warning("📝 Playwright 資料庫中暫無爬取記錄")
    
    def _save_results_to_database(self):
        """將當前爬取結果保存到資料庫（備用功能）"""
        if 'playwright_results' not in st.session_state:
            st.error("❌ 沒有可保存的結果")
            return
        
        # 使用與 realtime_crawler_component.py 相同的邏輯
        # 但調整變數名稱
        playwright_results = st.session_state.playwright_results
        
        # 檢查results的格式，如果是字典則提取results列表
        if isinstance(playwright_results, dict):
            results = playwright_results.get('results', [])
            target_username = playwright_results.get('target_username', '')
        else:
            results = playwright_results if playwright_results else []
            target_username = results[0].get('username', '') if results else ''
        
        if not results:
            st.error("❌ 沒有找到可保存的結果")
            return
        
        if not target_username:
            st.error("❌ 無法識別目標用戶名")
            return
        
        try:
            import subprocess
            import json
            import sys
            import os
            import tempfile
            
            # 創建保存腳本（與 realtime_crawler_component.py 相同）
            save_script_content = f'''
import asyncio
import sys
import os
import json
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from common.incremental_crawl_manager import IncrementalCrawlManager

async def save_to_database():
    crawl_manager = IncrementalCrawlManager()
    try:
        await crawl_manager.db.init_pool()
        
        # 準備結果數據
        results = {json.dumps(results, ensure_ascii=False)}
        target_username = "{target_username}"
        
        # 保存結果到資料庫
        saved_count = await crawl_manager.save_quick_crawl_results(results, target_username)
        
        # 更新檢查點（使用最新的貼文ID）
        if results and saved_count > 0:
            latest_post_id = results[0].get('post_id')  # 第一個是最新的
            if latest_post_id:
                await crawl_manager.update_crawl_checkpoint(
                    target_username, 
                    latest_post_id, 
                    saved_count
                )
        
        result = {{
            "success": True,
            "saved_count": saved_count,
            "target_username": target_username
        }}
        
        print(json.dumps(result))
        
    except Exception as e:
        print(json.dumps({{"success": False, "error": str(e)}}))
    finally:
        await crawl_manager.db.close_pool()

if __name__ == "__main__":
    asyncio.run(save_to_database())
'''
            
            # 寫入臨時文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                f.write(save_script_content)
                temp_script = f.name
            
            try:
                # 執行保存腳本
                with st.spinner(f"💾 正在保存 {len(results)} 個貼文到資料庫..."):
                    result = subprocess.run(
                        [sys.executable, temp_script],
                        capture_output=True,
                        text=True,
                        encoding='utf-8',
                        cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                        timeout=60
                    )
                
                if result.returncode == 0 and result.stdout.strip():
                    save_result = json.loads(result.stdout.strip())
                    
                    if save_result.get("success"):
                        saved_count = save_result.get("saved_count", 0)
                        
                        st.success(f"""
                        ✅ **保存成功！**
                        
                        已成功將 @{target_username} 的貼文保存到資料庫：
                        - 💾 保存貼文數: {saved_count} 個
                        - 🔄 檢查點已更新
                        """)
                        
                        # 更新session state，標記為已保存
                        if isinstance(st.session_state.playwright_results, dict):
                            st.session_state.playwright_results['database_saved'] = True
                            st.session_state.playwright_results['database_saved_count'] = saved_count
                        
                        # 清理資料庫統計緩存，下次查看會更新
                        if 'playwright_db_stats_cache' in st.session_state:
                            del st.session_state.playwright_db_stats_cache
                        
                        st.info("📊 資料庫統計已更新，您可以點擊刷新按鈕查看最新數據")
                        
                    else:
                        st.error(f"❌ 保存失敗: {save_result.get('error', '未知錯誤')}")
                else:
                    st.error(f"❌ 保存腳本執行失敗")
                    if result.stderr:
                        st.text(f"錯誤詳情: {result.stderr}")
                        
            finally:
                # 清理臨時文件
                try:
                    os.unlink(temp_script)
                except:
                    pass
                    
        except Exception as e:
            st.error(f"❌ 保存操作失敗: {str(e)}")