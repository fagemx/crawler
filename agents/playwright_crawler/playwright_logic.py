import json
import asyncio
import logging
import random
import re
import tempfile
import uuid
from pathlib import Path
from typing import Dict, List, Optional, AsyncIterable, Callable, Any
from datetime import datetime

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError, Browser, BrowserContext, Page, Route, APIResponse

from common.settings import get_settings
from common.a2a import stream_text, stream_data, stream_status, stream_error, TaskState
from common.models import PostMetrics, PostMetricsBatch
from common.nats_client import publish_progress
from common.utils import (
    get_best_video_url,
    get_best_image_url,
    generate_post_url,
    first_of,
    parse_thread_item
)

# 調試檔案路徑
DEBUG_DIR = Path(__file__).parent / "debug"
DEBUG_DIR.mkdir(exist_ok=True)
DEBUG_FAILED_ITEM_FILE = DEBUG_DIR / "failed_post_sample.json"
SAMPLE_THREAD_ITEM_FILE = DEBUG_DIR / "sample_thread_item.json"
RAW_CRAWL_DATA_FILE = DEBUG_DIR / "raw_crawl_data.json"

# 設定日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- GraphQL API 詳細資訊 ---
GRAPHQL_RE = re.compile(r"/graphql/query")
# 保留用來 debug；實際邏輯改成「看結構」即可
POST_QUERY_NAMES = set()

# --- 強健的欄位對照表 ---
FIELD_MAP = {
    "like_count": [
        "like_count", "likeCount", 
        ["feedback_info", "aggregated_like_count"],
        ["like_info", "count"]
    ],
    "comment_count": [
        ["text_post_app_info", "direct_reply_count"],
        "comment_count", "commentCount",
        ["reply_info", "count"]
    ],
    "share_count": [
        ["text_post_app_info", "reshare_count"],  # 真正的 shares 欄位
        "reshareCount", "share_count", "shareCount"
    ],
    "repost_count": [
        ["text_post_app_info", "repost_count"],  # reposts 欄位
        "repostCount", "repost_count"
    ],
    "content": [
        ["caption", "text"],
        "caption", "text", "content"
    ],
    "author": [
        ["user", "username"], 
        ["owner", "username"],
        ["user", "handle"]
    ],
    "created_at": [
        "taken_at", "taken_at_timestamp", 
        "publish_date", "created_time"
    ],
    "post_id": [
        "pk", "id", "post_id"
    ],
    "code": [
        "code", "shortcode", "media_code"
    ],
    # 增加直接從 API 嘗試獲取 views 的路徑
    "view_count": [
        ["feedback_info", "view_count"],
        ["video_info", "play_count"],
        "view_count",
        "views",
        "impression_count"
    ],
}

def parse_post_data(thread_item: Dict[str, Any], username: str) -> Optional[PostMetrics]:
    """
    強健的貼文解析器，使用多鍵 fallback 機制處理欄位變動。
    支援 Threads GraphQL API 的不同版本和欄位命名變化。
    """
    # 使用智能搜尋找到真正的貼文物件
    post = parse_thread_item(thread_item)
    
    if not post:
        logging.info(f"❌ 找不到有效的 post 物件，收到的資料鍵: {list(thread_item.keys())}")
        logging.info(f"❌ thread_item 內容範例: {str(thread_item)[:300]}...")
        
        # 自動儲存第一筆 raw JSON 供分析
        try:
            if not DEBUG_FAILED_ITEM_FILE.exists():
                DEBUG_FAILED_ITEM_FILE.write_text(
                    json.dumps(thread_item, indent=2, ensure_ascii=False),
                    encoding="utf-8" # 明確指定 UTF-8
                )
                logging.info(f"📝 已儲存失敗範例至 {DEBUG_FAILED_ITEM_FILE}")
        except Exception:
            pass  # 寫檔失敗不影響主要功能
            
        return None

    # 使用強健的欄位解析
    post_id = first_of(post, *FIELD_MAP["post_id"])
    code = first_of(post, *FIELD_MAP["code"])
    
    if not post_id:
        logging.info(f"❌ 找不到有效的 post_id，可用欄位: {list(post.keys())}")
        return None
        
    if not code:
        logging.info(f"❌ 找不到有效的 code，可用欄位: {list(post.keys())}")
        return None

    # --- URL 修復：使用正確的格式 ---
    # 舊格式 (錯誤): f"https://www.threads.net/t/{code}"
    # 新格式 (正確): f"https://www.threads.com/@{username}/post/{code}"
    url = generate_post_url(username, code)

    # 使用多鍵 fallback 解析所有欄位
    author = first_of(post, *FIELD_MAP["author"]) or username
    content = first_of(post, *FIELD_MAP["content"]) or ""
    like_count = first_of(post, *FIELD_MAP["like_count"]) or 0
    comment_count = first_of(post, *FIELD_MAP["comment_count"]) or 0
    share_count = first_of(post, *FIELD_MAP["share_count"]) or 0
    repost_count = first_of(post, *FIELD_MAP["repost_count"]) or 0
    created_at = first_of(post, *FIELD_MAP["created_at"])
    
    # 偵測未知欄位（用於調試和改進）
    unknown_keys = set(post.keys()) - {
        'pk', 'id', 'post_id', 'code', 'shortcode', 'media_code',
        'user', 'owner', 'caption', 'text', 'content',
        'like_count', 'likeCount', 'feedback_info', 'like_info',
        'text_post_app_info', 'comment_count', 'commentCount', 'reply_info',
        'taken_at', 'taken_at_timestamp', 'publish_date', 'created_time',
        # 常見但不重要的欄位
        'media_type', 'has_liked', 'image_versions2', 'video_versions',
        'carousel_media', 'location', 'user_tags', 'usertags'
    }
    
    if unknown_keys:
        logging.debug(f"🔍 發現未知欄位: {unknown_keys}")
        # 可以選擇寫入檔案以供分析
        try:
            with open("unknown_fields.log", "a", encoding="utf-8") as f:
                f.write(f"{json.dumps(list(unknown_keys))}\n")
        except Exception:
            pass  # 寫檔失敗不影響主要功能

    # --- MEDIA -------------------------------------------------------------
    images, videos = [], []

    def append_image(url):
        if url and url not in images:
            images.append(url)

    def append_video(url):
        if url and url not in videos:
            videos.append(url)

    def best_candidate(candidates: list[dict], prefer_mp4=False):
        """
        從 image_versions2 或 video_versions 裡挑「寬度最大的那個」URL
        """
        if not candidates:
            return None
        key = "url"
        return max(candidates, key=lambda c: c.get("width", 0)).get(key)

    # 1) 單圖 / 單片
    if "image_versions2" in post:
        append_image(best_candidate(post["image_versions2"].get("candidates", [])))
    if "video_versions" in post:
        append_video(best_candidate(post.get("video_versions", []), prefer_mp4=True))

    # 2) 輪播 carousel_media (加入 None 的安全處理)
    for media in post.get("carousel_media") or []:
        if "image_versions2" in media:
            append_image(best_candidate(media["image_versions2"].get("candidates", [])))
        if "video_versions" in media:
            append_video(best_candidate(media.get("video_versions", []), prefer_mp4=True))
    # -----------------------------------------------------------------------


    # 成功解析，記錄部分資訊供除錯
    logging.info(f"✅ 成功解析貼文 {post_id}: 作者={author}, 讚數={like_count}, 圖片={len(images)}, 影片={len(videos)}")
    
    return PostMetrics(
        url=url,
        post_id=str(post_id),
        username=username,
        source="playwright",
        processing_stage="playwright_crawled",
        likes_count=int(like_count) if isinstance(like_count, (int, str)) and str(like_count).isdigit() else 0,
        comments_count=int(comment_count) if isinstance(comment_count, (int, str)) and str(comment_count).isdigit() else 0,
        reposts_count=int(repost_count) if isinstance(repost_count, (int, str)) and str(repost_count).isdigit() else 0,
        shares_count=int(share_count) if isinstance(share_count, (int, str)) and str(share_count).isdigit() else 0,
        content=content,
        created_at=created_at,
        images=images,
        videos=videos,
        # 新增：直接從 API 解析 views_count（按指引優先嘗試 API）
        views_count=first_of(post, *FIELD_MAP["view_count"]) if first_of(post, *FIELD_MAP["view_count"]) is not None else None,
    )

# +++ 新增：從前端解析瀏覽數的輔助函式 +++
def parse_views_text(text: Optional[str]) -> Optional[int]:
    """將 '161.9萬次瀏覽' 或 '1.2M views' 這類文字轉換為整數"""
    if not text:
        return None
    try:
        original_text = text
        text_lower = text.lower().replace(",", "").strip()
        
        # 移除「次瀏覽」和「views」等後綴
        text_clean = text_lower.replace("次瀏覽", "").replace("views", "").replace("view", "").strip()
        
        # 提取數字部分
        num_part = re.findall(r"[\d\.]+", text_clean)
        if not num_part:
            logging.debug(f"🔍 無法從 '{original_text}' 中提取數字")
            return None
        
        num = float(num_part[0])
        
        # 處理中文單位
        if "萬" in text:
            result = int(num * 10000)
        elif "億" in text:
            result = int(num * 100000000)
        # 處理英文單位
        elif "m" in text_lower:
            result = int(num * 1000000)
        elif "k" in text_lower:
            result = int(num * 1000)
        else:
            result = int(num)
            
        logging.debug(f"🔍 成功解析 '{original_text}' -> {result}")
        return result
        
    except (ValueError, IndexError) as e:
        logging.warning(f"⚠️ 無法解析瀏覽數文字: '{text}' - {e}")
        return None

class PlaywrightLogic:
    """
    使用 Playwright 進行爬蟲的核心邏輯。
    """
    def __init__(self):
        self.settings = get_settings().playwright
        self.known_queries = set()  # 追蹤已見過的查詢名稱
        self.context = None  # 初始化 context

    def _build_response_handler(self, username: str, posts: dict, task_id: str, max_posts: int, stream_callback):
        """建立 GraphQL 回應處理器 - 使用結構判斷而非名稱白名單"""
        async def _handle_response(res):
            if not GRAPHQL_RE.search(res.url):
                return
                
            qname = res.request.headers.get("x-fb-friendly-name", "UNKNOWN")
            try:
                data = await res.json()
            except Exception:
                return  # 非 JSON 回應，直接跳過
                
            # 結構判斷：只要有 data.mediaData.edges 就是貼文資料
            edges = data.get("data", {}).get("mediaData", {}).get("edges", [])
            if not edges:
                return  # 跟貼文無關，忽略
                
            # 解析貼文 - 支援新舊結構的 fallback
            new_count = 0
            for edge in edges:
                # 支援 thread_items / items 的 fallback
                node = edge.get("node", {})
                thread_items = node.get("thread_items") or node.get("items") or []
                
                # 自動儲存第一筆成功的 thread_item 供分析
                if thread_items and new_count == 0:
                    try:
                        if not SAMPLE_THREAD_ITEM_FILE.exists():
                            SAMPLE_THREAD_ITEM_FILE.write_text(
                                json.dumps(thread_items[0], indent=2, ensure_ascii=False),
                                encoding="utf-8" # 明確指定 UTF-8
                            )
                            logging.info(f"📝 已儲存成功範例至 {SAMPLE_THREAD_ITEM_FILE}")
                    except Exception:
                        pass

                for item in thread_items:
                    parsed_post = parse_post_data(item, username)
                    if parsed_post and parsed_post.post_id not in posts:
                        posts[parsed_post.post_id] = parsed_post
                        new_count += 1
                        
            if new_count > 0:
                logging.info(f"✅ [{qname}] +{new_count} (總 {len(posts)}/{max_posts})")
                # 使用回調函數發送串流訊息 (如果有的話)
                if stream_callback:
                    stream_callback(f"✅ 從 {qname} 解析到 {new_count} 則新貼文，總數: {len(posts)}")
            
            # 檢查是否已達到目標數量
            if len(posts) >= max_posts:
                logging.info(f"達到目標貼文數 {max_posts}，將盡快停止滾動。")
                # 這裡可以觸發一個事件來停止滾動，但目前架構下會自然停止
                pass
                
            # 記錄新發現的查詢名稱（用於除錯）
            if qname not in self.known_queries:
                self.known_queries.add(qname)
                # 可選：寫入檔案以供日後分析
                try:
                    with open("seen_queries.txt", "a", encoding="utf-8") as f:
                        f.write(f"{qname}\n")
                except Exception:
                    pass  # 寫檔失敗不影響主要功能
                    
        return _handle_response

    async def fetch_posts(
        self,
        username: str,
        max_posts: int,
        auth_json_content: Dict,
        task_id: str = None
    ) -> PostMetricsBatch:
        """
        使用指定的認證內容爬取貼文。
        此版本會聚合所有結果，並一次性返回 PostMetricsBatch。
        """
        if task_id is None:
            task_id = str(uuid.uuid4())
            
        target_url = f"https://www.threads.com/@{username}"
        posts: Dict[str, PostMetrics] = {}
        
        # 發布開始爬取的進度
        await publish_progress(task_id, "fetch_start", username=username, max_posts=max_posts)
        
        # 1. 安全地將 auth.json 內容寫入臨時檔案
        auth_file = Path(tempfile.gettempdir()) / f"{task_id or uuid.uuid4()}_auth.json"
        try:
            with open(auth_file, 'w', encoding='utf-8') as f:
                json.dump(auth_json_content, f)

            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=self.settings.headless,
                    timeout=self.settings.navigation_timeout,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
                )
                self.context = await browser.new_context(
                    storage_state=str(auth_file),
                    user_agent=self.settings.user_agent, # 從設定讀取
                    viewport={"width": 1920, "height": 1080},
                    locale="zh-TW",  # 設定為繁體中文
                    has_touch=True,
                    accept_downloads=False
                )
                page = await self.context.new_page()
                page.on("console", lambda m: logging.info(f"CONSOLE [{m.type}] {m.text}"))

                # Response handler
                response_handler = self._build_response_handler(username, posts, task_id, max_posts, stream_callback=None)
                page.on("response", response_handler)

                logging.info(f"導覽至目標頁面: {target_url}")
                await page.goto(target_url, wait_until="networkidle", timeout=self.settings.navigation_timeout)

                # --- 滾動與延遲邏輯 ---
                scroll_attempts_without_new_posts = 0
                max_retries = 5

                while len(posts) < max_posts:
                    posts_before_scroll = len(posts)
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

                    try:
                        async with page.expect_response(lambda res: GRAPHQL_RE.search(res.url), timeout=15000):
                            pass
                    except PlaywrightTimeoutError:
                        logging.warning(f"⏳ [Task: {task_id}] 滾動後等待網路回應逾時。")

                    delay = random.uniform(self.settings.scroll_delay_min, self.settings.scroll_delay_max) # 從設定讀取
                    await asyncio.sleep(delay)

                    if len(posts) == posts_before_scroll:
                        scroll_attempts_without_new_posts += 1
                        logging.info(f"滾動後未發現新貼文 (嘗試 {scroll_attempts_without_new_posts}/{max_retries})")
                        if scroll_attempts_without_new_posts >= max_retries:
                            logging.info("已達頁面末端或無新內容，停止滾動。")
                            break
                    else:
                        scroll_attempts_without_new_posts = 0
                        # 發布進度更新
                        await publish_progress(
                            task_id, "fetch_progress", 
                            username=username,
                            current=len(posts), 
                            total=max_posts,
                            progress=min(len(posts) / max_posts, 1.0)
                        )
                
                # 關閉 page 但保留 context 供 fill_views_from_page 使用
                await page.close()

                # --- 整理並回傳結果 ---
                final_posts = list(posts.values())
                total_found = len(final_posts)
                
                # 根據 max_posts 截斷結果
                if total_found > max_posts:
                    try:
                        final_posts.sort(key=lambda p: p.created_at or datetime.min, reverse=True)
                    except Exception:
                        pass 
                    final_posts = final_posts[:max_posts]
                
                logging.info(f"🔄 [Task: {task_id}] 準備回傳最終資料：共發現 {total_found} 則貼文, 回傳 {len(final_posts)} 則")
                
                # --- 補齊觀看數 (在 browser context 還存在時執行) ---
                logging.info(f"🔍 [Task: {task_id}] 開始補齊觀看數...")
                await publish_progress(task_id, "fill_views_start", username=username, posts_count=len(final_posts))
                
                try:
                    final_posts = await self.fill_views_from_page(final_posts)
                    logging.info(f"✅ [Task: {task_id}] 觀看數補齊完成")
                    await publish_progress(task_id, "fill_views_completed", username=username, posts_count=len(final_posts))
                except Exception as e:
                    logging.warning(f"⚠️ [Task: {task_id}] 補齊觀看數時發生錯誤: {e}")
                    await publish_progress(task_id, "fill_views_error", username=username, error=str(e))
                    # 即使補齊失敗，也繼續返回基本數據

                # 手動關閉 browser 和 context
                await self.context.close()
                await browser.close()
                self.context = None
            
            # 保存原始抓取資料供調試
            try:
                raw_data = {
                    "task_id": task_id,
                    "username": username, 
                    "timestamp": datetime.now().isoformat(),
                    "total_found": total_found,
                    "returned_count": len(final_posts),
                    "posts": [
                        {
                            "url": post.url,
                            "post_id": post.post_id,
                            "likes_count": post.likes_count,
                            "comments_count": post.comments_count,
                            "reposts_count": post.reposts_count,
                            "shares_count": post.shares_count,
                            "views_count": post.views_count,
                            "calculated_score": post.calculate_score(),  # 🆕 移到 views_count 下面
                            "content": post.content,
                            "created_at": post.created_at.isoformat() if post.created_at else None,
                            "images": post.images,  # 添加圖片 URL
                            "videos": post.videos   # 添加影片 URL
                        } for post in final_posts
                    ]
                }
                
                # 使用時間戳記避免檔案衝突
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                raw_file = DEBUG_DIR / f"crawl_data_{timestamp}_{task_id[:8]}.json"
                raw_file.write_text(
                    json.dumps(raw_data, indent=2, ensure_ascii=False),
                    encoding="utf-8" # 明確指定 UTF-8
                )
                logging.info(f"💾 [Task: {task_id}] 已保存原始抓取資料至: {raw_file}")
                
            except Exception as e:
                logging.warning(f"⚠️ [Task: {task_id}] 保存調試資料失敗: {e}")
            
            # 發布完成進度
            await publish_progress(
                task_id, "completed", 
                username=username,
                total_posts=len(final_posts),
                success=True
            )

            batch = PostMetricsBatch(
                posts=final_posts,
                username=username,
                total_count=total_found,
                processing_stage="playwright_completed"
            )
            return batch
            
        except Exception as e:
            error_message = f"Playwright 核心邏輯出錯: {e}"
            logging.error(error_message, exc_info=True)
            # 發布錯誤進度
            await publish_progress(
                task_id, "error", 
                username=username,
                error=error_message,
                success=False
            )
            raise
        
        finally:
            # 清理臨時認證檔案
            if auth_file.exists():
                auth_file.unlink()
                logging.info(f"🗑️ [Task: {task_id}] 已刪除臨時認證檔案: {auth_file}")
            
            # 確保 context 被重置（browser 已在上面手動關閉）
            self.context = None 

    # +++ 新增：從前端補齊瀏覽數的核心方法 +++
    async def fill_views_from_page(self, posts_to_fill: List[PostMetrics]) -> List[PostMetrics]:
        """
        遍歷貼文列表，導航到每個貼文的頁面以補齊 views_count。
        使用並發處理來加速此過程。
        """
        if not self.context:
            logging.error("❌ Browser context 未初始化，無法執行 fill_views_from_page。")
            return posts_to_fill

        # 使用 Semaphore 限制並發數，避免被伺服器封鎖
        semaphore = asyncio.Semaphore(5)
        
        async def fetch_single_view(post: PostMetrics):
            async with semaphore:
                page = None
                try:
                    page = await self.context.new_page()
                    # 禁用圖片和影片載入以加速
                    await page.route("**/*.{png,jpg,jpeg,gif,mp4,webp}", lambda r: r.abort())
                    
                    for attempt in range(3): # 最多重試3次
                        try:
                            logging.debug(f"  ➡️ (Attempt {attempt+1}) 正在導航至: {post.url}")
                            await page.goto(post.url, timeout=20000, wait_until='domcontentloaded')
                            
                            # 使用您建議的、最穩健的 Selector
                            selector = "span:has-text('次瀏覽'), span:has-text('views')"
                            
                            # 等待元素出現，最多10秒
                            element = await page.wait_for_selector(selector, timeout=10000)
                            
                            if element:
                                view_text = await element.inner_text()
                                views_count = parse_views_text(view_text)
                                if views_count is not None:
                                    post.views_count = views_count
                                    post.views_fetched_at = datetime.utcnow()
                                    logging.info(f"  ✅ 成功獲取 {post.post_id} 的瀏覽數: {views_count}")
                                    return # 成功後退出重試循環
                            break # 找到元素但解析失敗也跳出
                        except Exception as e:
                            logging.warning(f"  ⚠️ (Attempt {attempt+1}) 獲取 {post.post_id} 瀏覽數失敗: {type(e).__name__}")
                            if attempt < 2:
                                await asyncio.sleep(2) # 重試前等待
                            else:
                                post.views_count = -1 # 最終失敗，標記為-1
                                post.views_fetched_at = datetime.utcnow()
                except Exception as e:
                    logging.error(f"  ❌ 處理 {post.post_id} 時發生嚴重錯誤: {e}")
                    post.views_count = -1
                    post.views_fetched_at = datetime.utcnow()
                finally:
                    if page:
                        await page.close()

        tasks = []
        for post in posts_to_fill:
            tasks.append(fetch_single_view(post))
            
        await asyncio.gather(*tasks)
        
        return posts_to_fill


    async def _scroll_and_collect(self, page: Page, username: str, max_posts: int):
        pass


    async def _handle_response(self, response: APIResponse, username: str):
        """處理 GraphQL API 回應"""
        # ... (這裡的 _handle_response 維持原樣) ...
# ... existing code ... 