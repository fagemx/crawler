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
import httpx

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

# Vision Agent URL - 指向我們即將建立的新端點
VISION_AGENT_URL = "http://vision-agent:8005/v1/vision/extract-views-from-image"

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
        created_at=datetime.fromtimestamp(created_at) if created_at and isinstance(created_at, (int, float)) else datetime.utcnow(),
        images=images,
        videos=videos,
        # 新增：直接從 API 解析 views_count（按指引優先嘗試 API）
        views_count=first_of(post, *FIELD_MAP["view_count"]) if first_of(post, *FIELD_MAP["view_count"]) is not None else None,
    )

# +++ 新增：從前端解析瀏覽數的輔助函式（修復空格問題） +++
def parse_views_text(text: Optional[str]) -> Optional[int]:
    """將 '161.9萬次瀏覽' 或 '4 萬次瀏覽' 或 '1.2M views' 這類文字轉換為整數"""
    if not text:
        return None
    try:
        original_text = text
        
        # 移除不必要的文字，保留數字和單位
        text = re.sub(r'串文\s*', '', text)  # 移除 "串文"
        
        # 處理中文格式：1.2萬、4 萬次瀏覽、5000次瀏覽
        if '萬' in text:
            match = re.search(r'([\d.]+)\s*萬', text)  # 允許數字和萬之間有空格
            if match:
                return int(float(match.group(1)) * 10000)
        elif '億' in text:
            match = re.search(r'([\d.]+)\s*億', text)  # 允許數字和億之間有空格
            if match:
                return int(float(match.group(1)) * 100000000)
        
        # 處理英文格式：1.2M views, 500K views
        text_upper = text.upper()
        if 'M' in text_upper:
            match = re.search(r'([\d.]+)M', text_upper)
            if match:
                return int(float(match.group(1)) * 1000000)
        elif 'K' in text_upper:
            match = re.search(r'([\d.]+)K', text_upper)
            if match:
                return int(float(match.group(1)) * 1000)
        
        # 處理純數字格式（可能包含逗號）
        match = re.search(r'[\d,]+', text)
        if match:
            return int(match.group(0).replace(',', ''))
        
        logging.debug(f"🔍 無法解析瀏覽數文字: '{original_text}'")
        return None
        
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
                        
                        # 🔥 新增：每解析一個貼文就發布即時進度
                        from common.nats_client import publish_progress
                        await publish_progress(
                            task_id, 
                            "post_parsed",
                            username=username,
                            post_id=parsed_post.post_id,
                            current=len(posts),
                            total=max_posts,
                            progress=len(posts) / max_posts,
                            content_preview=parsed_post.content[:50] + "..." if parsed_post.content else "無內容",
                            likes=parsed_post.likes_count
                        )
                        
            if new_count > 0:
                logging.info(f"✅ [{qname}] +{new_count} (總 {len(posts)}/{max_posts})")
                # 使用回調函數發送串流訊息 (如果有的話)
                if stream_callback:
                    stream_callback(f"✅ 從 {qname} 解析到 {new_count} 則新貼文，總數: {len(posts)}")
                    
                # 🔥 新增：每批解析完成後的進度更新
                from common.nats_client import publish_progress
                await publish_progress(
                    task_id, 
                    "batch_parsed",
                    username=username,
                    batch_size=new_count,
                    current=len(posts),
                    total=max_posts,
                    progress=len(posts) / max_posts,
                    query_name=qname
                )
            
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

    async def get_ordered_post_urls_from_page(self, page: Page, username: str, max_posts: int) -> List[str]:
        """
        從用戶頁面直接提取貼文 URLs，保持時間順序
        這是解決貼文順序混亂問題的關鍵方法
        """
        user_url = f"https://www.threads.com/@{username}"
        logging.info(f"🔍 正在從用戶頁面獲取有序的貼文 URLs: {user_url}")
        
        await page.goto(user_url, wait_until="networkidle")
        
        # 等待頁面載入
        await asyncio.sleep(3)
        
        # 滾動以載入更多貼文（但不要滾動太多次避免載入過舊的貼文）
        scroll_count = min(3, max(1, max_posts // 10))  # 根據需求動態調整滾動次數
        for i in range(scroll_count):
            await page.mouse.wheel(0, 1000)
            await asyncio.sleep(2)
        
        # 提取貼文 URLs，保持原始順序
        post_urls = await page.evaluate("""
            () => {
                // 獲取所有貼文連結，保持DOM中的原始順序
                const links = Array.from(document.querySelectorAll('a[href*="/post/"]'));
                const urls = [];
                const seen = new Set();
                
                // 遍歷時保持順序，只去重但不重排
                for (const link of links) {
                    const url = link.href;
                    if (url.includes('/post/') && !seen.has(url)) {
                        seen.add(url);
                        urls.push(url);
                    }
                }
                
                return urls;
            }
        """)
        
        # 限制數量但保持順序
        post_urls = post_urls[:max_posts]
        logging.info(f"   ✅ 按時間順序找到 {len(post_urls)} 個貼文 URLs")
        
        return post_urls

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
                    accept_downloads=False,
                    bypass_csp=True  # 新增：繞過 CSP 限制
                )
                # 新增：隱藏 webdriver 屬性
                await self.context.add_init_script(
                    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
                )
                
                page = await self.context.new_page()
                page.on("console", lambda m: logging.info(f"CONSOLE [{m.type}] {m.text}"))

                # --- 新方法：先獲取有序的貼文 URLs ---
                logging.info(f"🎯 [Task: {task_id}] 使用新的有序貼文獲取方法")
                ordered_post_urls = await self.get_ordered_post_urls_from_page(page, username, max_posts)
                
                if not ordered_post_urls:
                    logging.warning(f"⚠️ [Task: {task_id}] 無法從用戶頁面獲取貼文 URLs，回退至舊方法")
                    # 回退至原始的 GraphQL 攔截方法
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
                else:
                    # --- 新方法：使用有序URLs創建PostMetrics，稍後補齊詳細數據 ---
                    logging.info(f"✅ [Task: {task_id}] 使用有序URLs創建基礎PostMetrics，保持時間順序")
                    ordered_posts = []  # 保持順序的陣列
                    
                    for i, post_url in enumerate(ordered_post_urls):
                        # 從 URL 中提取 post_id 和 code
                        url_parts = post_url.split('/')
                        if len(url_parts) >= 2:
                            code = url_parts[-1] if url_parts[-1] != 'media' else url_parts[-2]  # 處理 /media 結尾
                            post_id = f"{username}_{code}"  # 生成唯一的 post_id
                            
                            # 創建基本的 PostMetrics 物件
                            post_metrics = PostMetrics(
                                url=post_url,
                                post_id=post_id,
                                username=username,
                                source="playwright_ordered",
                                processing_stage="url_extracted",
                                likes_count=0,  # 將通過頁面訪問補齊
                                comments_count=0,  # 將通過頁面訪問補齊
                                reposts_count=0,  # 將通過頁面訪問補齊
                                shares_count=0,  # 將通過頁面訪問補齊
                                content="",  # 將通過頁面訪問補齊
                                created_at=datetime.utcnow(),  # 使用當前時間作為預設值
                                images=[],  # 將通過頁面訪問補齊
                                videos=[],  # 將通過頁面訪問補齊
                                views_count=None  # 將通過 fill_views_from_page 補齊
                            )
                            
                            ordered_posts.append(post_metrics)
                            posts[post_id] = post_metrics  # 同時加入字典供後續處理
                            
                            # 發布進度
                            await publish_progress(
                                task_id, 
                                "post_url_extracted",
                                username=username,
                                post_id=post_id,
                                current=len(ordered_posts),
                                total=max_posts,
                                progress=len(ordered_posts) / max_posts,
                                url=post_url
                            )
                    
                    # 使用 ordered_posts 而不是 posts.values() 來保持順序
                    logging.info(f"✅ [Task: {task_id}] 創建了 {len(ordered_posts)} 個有序的基礎PostMetrics")
                
                # 關閉 page 但保留 context 供 fill_views_from_page 使用
                await page.close()

                # --- 整理並回傳結果 ---
                # 使用有序的 posts 列表或回退到原始方法
                if 'ordered_posts' in locals():
                    final_posts = ordered_posts[:max_posts]  # 保持原始順序，只限制數量
                    total_found = len(ordered_posts)
                    logging.info(f"🎯 [Task: {task_id}] 使用有序貼文列表，保持DOM提取的時間順序")
                else:
                    # 回退到原始方法（GraphQL攔截的情況）
                    final_posts = list(posts.values())
                total_found = len(final_posts)
                # 根據 max_posts 截斷結果
                if total_found > max_posts:
                    try:
                        final_posts.sort(key=lambda p: p.created_at or datetime.min, reverse=True)
                    except Exception:
                        pass 
                    final_posts = final_posts[:max_posts]
                    logging.info(f"🔄 [Task: {task_id}] 使用GraphQL攔截方法，按created_at排序")
                
                logging.info(f"🔄 [Task: {task_id}] 準備回傳最終資料：共發現 {total_found} 則貼文, 回傳 {len(final_posts)} 則")
                
                # --- 補齊詳細數據和觀看數 (在 browser context 還存在時執行) ---
                # 配置選項：是否啟用詳細數據補齊（修復默認值）
                enable_details_filling = getattr(self.settings, 'enable_details_filling', True)
                
                if enable_details_filling:
                    # 新方法：需要補齊詳細數據
                    logging.info(f"🔍 [Task: {task_id}] 開始補齊詳細數據（likes, content等）...")
                    await publish_progress(task_id, "fill_details_start", username=username, posts_count=len(final_posts))
                    
                    try:
                        final_posts = await self.fill_post_details_from_page(final_posts, task_id=task_id, username=username)
                        logging.info(f"✅ [Task: {task_id}] 詳細數據補齊完成")
                        await publish_progress(task_id, "fill_details_completed", username=username, posts_count=len(final_posts))
                    except Exception as e:
                        logging.warning(f"⚠️ [Task: {task_id}] 補齊詳細數據時發生錯誤: {e}")
                        await publish_progress(task_id, "fill_details_error", username=username, error=str(e))
                else:
                    logging.info(f"⚠️ [Task: {task_id}] 詳細數據補齊已禁用，將只補齊瀏覽數")
                
                # 補齊觀看數（兩種方法都需要）
                logging.info(f"🔍 [Task: {task_id}] 開始補齊觀看數...")
                await publish_progress(task_id, "fill_views_start", username=username, posts_count=len(final_posts))
                
                try:
                    final_posts = await self.fill_views_from_page(final_posts, task_id=task_id, username=username)
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

    # +++ 新增：從前端補齊瀏覽數的核心方法（整合 Gate 頁面處理） +++
    async def fill_views_from_page(self, posts_to_fill: List[PostMetrics], task_id: str = None, username: str = None) -> List[PostMetrics]:
        """
        遍歷貼文列表，導航到每個貼文的頁面以補齊 views_count。
        整合了成功的 Gate 頁面處理和雙策略提取方法。
        """
        if not self.context:
            logging.error("❌ Browser context 未初始化，無法執行 fill_views_from_page。")
            return posts_to_fill

        # 減少並發數以避免觸發反爬蟲機制
        semaphore = asyncio.Semaphore(2)
        
        async def fetch_single_view(post: PostMetrics):
            async with semaphore:
                page = None
                try:
                    page = await self.context.new_page()
                    # 禁用圖片和影片載入以加速
                    await page.route("**/*.{png,jpg,jpeg,gif,mp4,webp}", lambda r: r.abort())
                    
                    logging.debug(f"📄 正在處理: {post.url}")
                    
                    # 導航到貼文頁面
                    await page.goto(post.url, wait_until="networkidle", timeout=30000)
                    
                    # 檢查頁面類型（完整頁面 vs Gate 頁面）
                    page_content = await page.content()
                    is_gate_page = "__NEXT_DATA__" not in page_content
                    
                    if is_gate_page:
                        logging.debug(f"   ⚠️ 檢測到 Gate 頁面，直接使用 DOM 選擇器...")
                    
                    views_count = None
                    extraction_method = None
                    
                    # 策略 1: GraphQL 攔截（只在非 Gate 頁面時）
                    if not is_gate_page:
                        try:
                            response = await page.wait_for_response(
                                lambda r: "containing_thread" in r.url and r.status == 200, 
                                timeout=8000
                            )
                            data = await response.json()
                            
                            # 解析瀏覽數
                            thread_items = data["data"]["containing_thread"]["thread_items"]
                            post_data = thread_items[0]["post"]
                            views_count = (post_data.get("feedback_info", {}).get("view_count") or
                                          post_data.get("video_info", {}).get("play_count") or 0)
                            
                            if views_count > 0:
                                extraction_method = "graphql_api"
                                logging.debug(f"   ✅ GraphQL API 獲取瀏覽數: {views_count:,}")
                        except Exception as e:
                            logging.debug(f"   ⚠️ GraphQL 攔截失敗: {str(e)[:100]}")
                    
                    # 策略 2: DOM 選擇器（Gate 頁面的主要方法）
                    if views_count is None or views_count == 0:
                        selectors = [
                            "a:has-text(' 次瀏覽'), a:has-text(' views')",    # 主要選擇器
                            "*:has-text('次瀏覽'), *:has-text('views')",      # 通用選擇器
                            "span:has-text('次瀏覽'), span:has-text('views')", # span 元素
                            "text=/\\d+.*次瀏覽/, text=/\\d+.*views?/",       # 正則表達式
                        ]
                        
                        for i, selector in enumerate(selectors):
                            try:
                                element = await page.wait_for_selector(selector, timeout=3000)
                                if element:
                                    view_text = await element.inner_text()
                                    parsed_views = parse_views_text(view_text)
                                    if parsed_views and parsed_views > 0:
                                        views_count = parsed_views
                                        extraction_method = f"dom_selector_{i+1}"
                                        logging.debug(f"   ✅ DOM 選擇器 {i+1} 獲取瀏覽數: {views_count:,}")
                                        break
                            except Exception:
                                continue
                    
                    # 更新結果
                    if views_count and views_count > 0:
                        post.views_count = views_count
                        post.views_fetched_at = datetime.utcnow()
                        logging.info(f"  ✅ 成功獲取 {post.post_id} 的瀏覽數: {views_count:,} (方法: {extraction_method})")
                        
                        # 發布進度
                        if task_id:
                            from common.nats_client import publish_progress
                            await publish_progress(
                                task_id, 
                                "views_fetched",
                                username=username or "unknown",
                                post_id=post.post_id,
                                views_count=views_count,
                                extraction_method=extraction_method,
                                is_gate_page=is_gate_page
                            )
                    else:
                        logging.warning(f"  ❌ 無法獲取 {post.post_id} 的瀏覽數")
                        post.views_count = -1
                        post.views_fetched_at = datetime.utcnow()
                    
                    # 隨機延遲避免反爬蟲
                    delay = random.uniform(2, 4)
                    await asyncio.sleep(delay)
                    
                except Exception as e:
                    logging.error(f"  ❌ 處理 {post.post_id} 時發生錯誤: {e}")
                    post.views_count = -1
                    post.views_fetched_at = datetime.utcnow()
                finally:
                    if page:
                        await page.close()

        # 序列處理避免並發問題（根據成功經驗）
        for post in posts_to_fill:
            await fetch_single_view(post)
        
        return posts_to_fill

    # +++ 新增：混合提取器 - 結合計數查詢和DOM解析 +++
    async def fill_post_details_from_page(self, posts_to_fill: List[PostMetrics], task_id: str = None, username: str = None) -> List[PostMetrics]:
        """
        使用混合策略補齊貼文詳細數據：
        1. GraphQL 計數查詢獲取準確的數字數據 (likes, comments等)
        2. DOM 解析獲取完整的內容和媒體 (content, images, videos)
        這種方法結合了兩種技術的優勢，提供最穩定可靠的數據提取。
        """
        if not self.context:
            logging.error("❌ Browser context 未初始化，無法執行 fill_post_details_from_page。")
            return posts_to_fill

        # 減少並發數以避免觸發反爬蟲機制
        semaphore = asyncio.Semaphore(1)  # 更保守的並發數
        
        async def fetch_single_details_hybrid(post: PostMetrics):
            async with semaphore:
                page = None
                try:
                    page = await self.context.new_page()
                    
                    logging.debug(f"📄 使用混合策略補齊詳細數據: {post.url}")
                    
                    # === 步驟 1: 攔截計數查詢 ===
                    counts_data = {}
                    video_urls = set()
                    
                    async def handle_counts_response(response):
                        try:
                            url = response.url.lower()
                            headers = response.request.headers
                            query_name = headers.get("x-fb-friendly-name", "")
                            
                            # 攔截計數查詢
                            if ("/graphql" in url and response.status == 200 and 
                                "useBarcelonaBatchedDynamicPostCountsSubscriptionQuery" in query_name):
                                
                                data = await response.json()
                                if "data" in data and "data" in data["data"] and "posts" in data["data"]["data"]:
                                    posts_list = data["data"]["data"]["posts"]
                                    
                                    # 找到目標貼文 (通過 URL 中的代碼匹配)
                                    import re as regex
                                    url_match = regex.search(r'/post/([^/?]+)', post.url)
                                    target_code = url_match.group(1) if url_match else None
                                    
                                    logging.debug(f"   🔍 尋找目標貼文代碼: {target_code} (從 URL: {post.url})")
                                    logging.debug(f"   📊 響應包含 {len(posts_list)} 個貼文")
                                    
                                    for post_data in posts_list:
                                        if isinstance(post_data, dict):
                                            post_code = post_data.get("code")
                                            logging.debug(f"   📝 檢查貼文代碼: {post_code}")
                                            if target_code and post_code == target_code:  # 精確匹配
                                                counts_data.update({
                                                    "likes": post_data.get("like_count", 0),
                                                    "comments": post_data.get("text_post_app_info", {}).get("direct_reply_count", 0),
                                                    "reposts": post_data.get("text_post_app_info", {}).get("repost_count", 0),
                                                    "shares": post_data.get("text_post_app_info", {}).get("reshare_count", 0)
                                                })
                                                logging.debug(f"   ✅ 攔截到計數數據: 讚={counts_data['likes']}")
                                                break
                            
                            # 攔截影片資源
                            content_type = response.headers.get("content-type", "")
                            resource_type = response.request.resource_type
                            if (resource_type == "media" or 
                                content_type.startswith("video/") or
                                ".mp4" in response.url.lower() or
                                ".m3u8" in response.url.lower() or
                                ".mpd" in response.url.lower()):
                                video_urls.add(response.url)
                                logging.debug(f"   🎥 攔截到影片: {response.url[:60]}...")
                                
                        except Exception as e:
                            logging.debug(f"   ⚠️ 響應處理失敗: {e}")
                    
                    page.on("response", handle_counts_response)
                    
                    # === 步驟 2: 導航和觸發載入 ===
                    await page.goto(post.url, wait_until="networkidle", timeout=60000)
                    await asyncio.sleep(3)
                    
                    # 嘗試觸發影片載入
                    try:
                        trigger_selectors = [
                            'div[data-testid="media-viewer"]',
                            'video',
                            'div[role="button"][aria-label*="play"]',
                            'div[role="button"][aria-label*="播放"]',
                            '[data-pressable-container] div[style*="video"]'
                        ]
                        
                        for selector in trigger_selectors:
                            try:
                                elements = page.locator(selector)
                                count = await elements.count()
                                if count > 0:
                                    await elements.first.click(timeout=3000)
                                    await asyncio.sleep(2)
                                    break
                            except:
                                continue
                    except:
                        pass
                    
                    # === 步驟 3: DOM 內容提取 ===
                    content_data = {}
                    
                    try:
                        # 提取用戶名（從 URL）
                        import re as regex
                        url_match = regex.search(r'/@([^/]+)/', post.url)
                        content_data["username"] = url_match.group(1) if url_match else username or ""
                        
                        # 提取內容文字
                        content = ""
                        content_selectors = [
                            'div[data-pressable-container] span',
                            '[data-testid="thread-text"]',
                            'article div[dir="auto"]',
                            'div[role="article"] div[dir="auto"]'
                        ]
                        
                        for selector in content_selectors:
                            try:
                                elements = page.locator(selector)
                                count = await elements.count()
                                
                                for i in range(min(count, 20)):
                                    try:
                                        text = await elements.nth(i).inner_text()
                                        if (text and len(text.strip()) > 10 and 
                                            not text.strip().isdigit() and
                                            "小時" not in text and "分鐘" not in text and
                                            not text.startswith("@")):
                                            content = text.strip()
                                            break
                                    except:
                                        continue
                                
                                if content:
                                    break
                            except:
                                continue
                        
                        content_data["content"] = content
                        
                        # 提取圖片（過濾頭像）
                        images = []
                        img_elements = page.locator('img')
                        img_count = await img_elements.count()
                        
                        for i in range(min(img_count, 50)):
                            try:
                                img_elem = img_elements.nth(i)
                                img_src = await img_elem.get_attribute("src")
                                
                                if not img_src or not ("fbcdn" in img_src or "cdninstagram" in img_src):
                                    continue
                                
                                if ("rsrc.php" in img_src or "static.cdninstagram.com" in img_src):
                                    continue
                                
                                # 檢查尺寸過濾頭像
                                try:
                                    width = int(await img_elem.get_attribute("width") or 0)
                                    height = int(await img_elem.get_attribute("height") or 0)
                                    max_size = max(width, height)
                                    
                                    if max_size > 150 and img_src not in images:
                                        images.append(img_src)
                                except:
                                    if ("t51.2885-15" in img_src or "scontent" in img_src) and img_src not in images:
                                        images.append(img_src)
                            except:
                                continue
                        
                        content_data["images"] = images
                        
                        # 提取影片（結合網路攔截和DOM）
                        videos = list(video_urls)
                        
                        # DOM 中的 video 標籤
                        video_elements = page.locator('video')
                        video_count = await video_elements.count()
                        
                        for i in range(video_count):
                            try:
                                video_elem = video_elements.nth(i)
                                src = await video_elem.get_attribute("src")
                                data_src = await video_elem.get_attribute("data-src")
                                poster = await video_elem.get_attribute("poster")
                                
                                if src and src not in videos:
                                    videos.append(src)
                                if data_src and data_src not in videos:
                                    videos.append(data_src)
                                if poster and poster not in videos:
                                    videos.append(f"POSTER::{poster}")
                                
                                # source 子元素
                                sources = video_elem.locator('source')
                                source_count = await sources.count()
                                for j in range(source_count):
                                    source_src = await sources.nth(j).get_attribute("src")
                                    if source_src and source_src not in videos:
                                        videos.append(source_src)
                            except:
                                continue
                        
                        content_data["videos"] = videos
                        
                    except Exception as e:
                        logging.debug(f"   ⚠️ DOM 內容提取失敗: {e}")
                    
                    # === 步驟 4: 更新貼文數據 ===
                    updated = False
                    
                    # 更新計數數據
                    if counts_data:
                        post.likes_count = counts_data.get("likes", post.likes_count)
                        post.comments_count = counts_data.get("comments", post.comments_count)
                        post.reposts_count = counts_data.get("reposts", post.reposts_count)
                        post.shares_count = counts_data.get("shares", post.shares_count)
                        updated = True
                    
                    # 更新內容數據
                    if content_data.get("content"):
                        post.content = content_data["content"]
                        updated = True
                    
                    if content_data.get("images"):
                        post.images = content_data["images"]
                        updated = True
                    
                    if content_data.get("videos"):
                        # 過濾實際影片（排除 POSTER）
                        actual_videos = [v for v in content_data["videos"] if not v.startswith("POSTER::")]
                        if actual_videos:
                            post.videos = actual_videos
                            updated = True
                    
                    if updated:
                        post.processing_stage = "details_filled_hybrid"
                        logging.info(f"  ✅ 混合策略成功補齊 {post.post_id}: 讚={post.likes_count}, 內容={len(post.content)}字, 圖片={len(post.images)}個, 影片={len(post.videos)}個")
                        
                        # 發布進度
                        if task_id:
                            from common.nats_client import publish_progress
                            await publish_progress(
                                task_id, 
                                "details_fetched_hybrid",
                                username=content_data.get("username", username or "unknown"),
                                post_id=post.post_id,
                                likes_count=post.likes_count,
                                content_length=len(post.content),
                                media_count=len(post.images) + len(post.videos)
                            )
                    else:
                        post.processing_stage = "details_failed"
                        logging.warning(f"  ⚠️ 混合策略無法補齊 {post.post_id} 的數據")
                    
                    # 隨機延遲避免反爬蟲
                    delay = random.uniform(2, 4)
                    await asyncio.sleep(delay)
                    
                except Exception as e:
                    logging.error(f"  ❌ 混合策略處理 {post.post_id} 時發生錯誤: {e}")
                    post.processing_stage = "details_failed"
                finally:
                    if page:
                        await page.close()

        # 序列處理保持順序
        for post in posts_to_fill:
            await fetch_single_details_hybrid(post)
        
        return posts_to_fill


