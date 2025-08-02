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
from common.history import crawl_history

# 導入 Hybrid Extractor（如果存在）
try:
    import sys
    sys.path.append(str(Path(__file__).parent.parent.parent))
    from hybrid_content_extractor import HybridContentExtractor
    HYBRID_AVAILABLE = True
except ImportError:
    HYBRID_AVAILABLE = False
    logging.warning("⚠️ Hybrid Extractor 不可用，將使用原始方法")

# Vision Agent URL - 指向我們即將建立的新端點
VISION_AGENT_URL = "http://vision-agent:8005/v1/vision/extract-views-from-image"

# 調試檔案路徑
DEBUG_DIR = Path(__file__).parent / "debug"
DEBUG_DIR.mkdir(exist_ok=True)
DEBUG_FAILED_ITEM_FILE = DEBUG_DIR / "failed_post_sample.json"
SAMPLE_THREAD_ITEM_FILE = DEBUG_DIR / "sample_thread_item.json"
RAW_CRAWL_DATA_FILE = DEBUG_DIR / "raw_crawl_data.json"

# 設定日誌（避免重複配置）
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 移除 GraphQL 依賴，改用純 DOM 方案 ---

# --- 統一數字解析工具 ---
def parse_number(val):
    """
    統一解析各種數字格式 → int
    - int / float 直接回傳
    - dict 會嘗試抓 'count'、'total'、第一個 value
    - 其餘字串走 K / M / 萬 / 逗號 流程
    """
    # 1) 已經是數值
    if isinstance(val, (int, float)):
        return int(val)
    
    # 2) 如果是 dict 先挖數字再遞迴
    if isinstance(val, dict):
        for key in ("count", "total", "value"):
            if key in val:
                return parse_number(val[key])
        # 找不到常見鍵 → 抓第一個 value
        if val:
            return parse_number(next(iter(val.values())))
        return 0  # 空 dict
    
    # 3) None 或空字串
    if not val:
        return 0
    
    try:
        # --- 以下跟原本一樣 ---
        text = str(val).strip().replace('&nbsp;', ' ')
        text = re.sub(r'串文\s*', '', text)
        text = re.sub(r'次瀏覽.*$', '', text)
        text = re.sub(r'views?.*$', '', text, flags=re.IGNORECASE).strip()
        
        # 中文萬 / 億
        if '萬' in text:
            m = re.search(r'([\d.,]+)\s*萬', text)
            if m: 
                return int(float(m.group(1).replace(',', '')) * 1e4)
        if '億' in text:
            m = re.search(r'([\d.,]+)\s*億', text)
            if m: 
                return int(float(m.group(1).replace(',', '')) * 1e8)
        
        # 英文 K / M
        up = text.upper()
        if 'M' in up:
            m = re.search(r'([\d.,]+)\s*M', up)
            if m: 
                return int(float(m.group(1).replace(',', '')) * 1e6)
        if 'K' in up:
            m = re.search(r'([\d.,]+)\s*K', up)
            if m: 
                return int(float(m.group(1).replace(',', '')) * 1e3)
        
        # 單純數字含逗號
        m = re.search(r'[\d,]+', text)
        return int(m.group(0).replace(',', '')) if m else 0
        
    except (ValueError, IndexError) as e:
        logging.debug(f"⚠️ 無法解析數字: '{val}' - {e}")
        return 0

# --- 強健的欄位對照表 ---
FIELD_MAP = {
    "like_count": [
        "like_count", "likeCount", 
        ["feedback_info", "aggregated_like_count"],
        ["feedback_info", "aggregated_like_count", "count"],  # 更深層路徑
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
    like_count = parse_number(first_of(post, *FIELD_MAP["like_count"]))
    comment_count = parse_number(first_of(post, *FIELD_MAP["comment_count"]))
    share_count = parse_number(first_of(post, *FIELD_MAP["share_count"]))
    repost_count = parse_number(first_of(post, *FIELD_MAP["repost_count"]))
    created_at = first_of(post, *FIELD_MAP["created_at"])
    
    # 🔥 調試信息：檢查原始數據
    logging.debug(f"🔥 like={first_of(post, *FIELD_MAP['like_count'])!r} comment={first_of(post, *FIELD_MAP['comment_count'])!r} from raw post_id={post_id}")
    logging.debug(f"🔥 解析後: like={like_count} comment={comment_count} share={share_count} repost={repost_count}")
    
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
    
    # 統一 post_id 格式：使用 username_code 而不是原始的數字 ID
    unified_post_id = f"{username}_{code}"
    
    return PostMetrics(
        url=url,
        post_id=unified_post_id,  # 使用統一格式的 post_id
        username=username,
        source="playwright",
        processing_stage="playwright_crawled",
        likes_count=like_count,      # 已經通過 parse_number() 處理
        comments_count=comment_count, # 已經通過 parse_number() 處理
        reposts_count=repost_count,   # 已經通過 parse_number() 處理
        shares_count=share_count,     # 已經通過 parse_number() 處理
        content=content,
        created_at=datetime.fromtimestamp(created_at) if created_at and isinstance(created_at, (int, float)) else datetime.utcnow(),
        images=images,
        videos=videos,
        # 新增：直接從 API 解析 views_count（按指引優先嘗試 API）
        views_count=parse_number(first_of(post, *FIELD_MAP["view_count"])),
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
        self.context = None  # 初始化 context

    # GraphQL 響應處理器已移除 - 改用純 DOM 方案

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
        extra_posts: int,
        auth_json_content: Dict,
        task_id: str = None
    ) -> PostMetricsBatch:
        """
        使用指定的認證內容進行增量爬取。
        
        Args:
            username: 目標用戶名
            extra_posts: 想要額外抓取的貼文數量（增量語義）
            auth_json_content: 認證信息
            task_id: 任務ID
            
        Returns:
            PostMetricsBatch: 新抓取的貼文批次
            
        核心優化（基於用戶建議）：
        - extra_posts=0 自動跳過爬取
        - 預先計算need，實現精確早停
        - 使用latest_post_id優化查詢
        """
        if task_id is None:
            task_id = str(uuid.uuid4())
        
        # 🚀 核心優化：增量爬取邏輯（基於用戶建議）
        # ① 檢查是否需要爬取
        if extra_posts <= 0:
            logging.info(f"🟢 {username} 無需額外爬取 (extra_posts={extra_posts})")
            existing_state = await crawl_history.get_crawl_state(username)
            total_existing = existing_state.get("total_crawled", 0) if existing_state else 0
            return PostMetricsBatch(posts=[], username=username, total_count=total_existing)
        
        # ② 讀取現有post_id集合（避免重複抓取）
        existing_post_ids = await crawl_history.get_existing_post_ids(username)
        already_count = len(existing_post_ids)
        need_to_fetch = extra_posts  # 精確控制：就是要這麼多篇新的
        
        logging.info(f"📊 {username} 增量狀態: 已有={already_count}, 需要新增={need_to_fetch}")
        
        target_url = f"https://www.threads.com/@{username}"
        posts: Dict[str, PostMetrics] = {}
        
        # 發布開始爬取的進度
        await publish_progress(task_id, "fetch_start", username=username, extra_posts=extra_posts)
        
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

                # --- 🚀 優化方法：使用增量需求+buffer ---
                logging.info(f"🎯 [Task: {task_id}] 增量爬取: 需要{need_to_fetch}篇新貼文")
                buffer_size = min(need_to_fetch + 10, 50)  # 合理buffer，避免過度抓取
                ordered_post_urls = await self.get_ordered_post_urls_from_page(page, username, buffer_size)
                
                if not ordered_post_urls:
                    logging.warning(f"⚠️ [Task: {task_id}] 無法從用戶頁面獲取貼文 URLs")
                    # GraphQL 方法已移除，純 DOM 方案不需要回退

                logging.info(f"導覽至目標頁面: {target_url}")
                await page.goto(target_url, wait_until="networkidle", timeout=self.settings.navigation_timeout)

                # --- 滾動與延遲邏輯 ---
                scroll_attempts_without_new_posts = 0
                max_retries = 5

                # 注意：此滾動邏輯在增量模式下已不需要，因為我們已通過get_ordered_post_urls_from_page獲取URL
                while len(posts) < need_to_fetch and False:  # 暫時禁用滾動
                    posts_before_scroll = len(posts)
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

                    await asyncio.sleep(0.5)  # 真的要等 networkidle 的話自己睡一下就好

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
                            total=need_to_fetch,
                            progress=min(len(posts) / need_to_fetch, 1.0) if need_to_fetch > 0 else 1.0
                        )

                # --- 🚀 增量優化：去重+精確早停 ---
                logging.info(f"✅ [Task: {task_id}] 增量篩選: 從{len(ordered_post_urls)}個URL中尋找{need_to_fetch}篇新貼文")
                ordered_posts = []  # 保持順序的陣列
                processed_count = 0
                new_posts_found = 0
                
                for i, post_url in enumerate(ordered_post_urls):
                    # 從 URL 中提取 post_id 和 code
                    url_parts = post_url.split('/')
                    if len(url_parts) >= 2:
                        code = url_parts[-1] if url_parts[-1] != 'media' else url_parts[-2]  # 處理 /media 結尾
                        post_id = f"{username}_{code}"  # 生成唯一的 post_id
                        processed_count += 1
                        
                        # 🚀 核心去重邏輯
                        if post_id in existing_post_ids:
                            logging.debug(f"⏭️ 跳過已存在: {post_id}")
                            continue
                        
                        # 🎯 精確早停機制
                        if new_posts_found >= need_to_fetch:
                            logging.info(f"🎯 提早停止: 已收集到{need_to_fetch}篇新貼文")
                            break
                        
                        # ① 創建新的PostMetrics
                        post_metrics = PostMetrics(
                            url=post_url,
                            post_id=post_id,
                            username=username,
                            source="playwright_incremental",
                            processing_stage="url_extracted",
                            likes_count=0,
                            comments_count=0,
                            reposts_count=0,
                            shares_count=0,
                            content="",
                            created_at=datetime.utcnow(),
                            images=[],
                            videos=[],
                            views_count=None,
                        )
                        posts[post_id] = post_metrics
                        ordered_posts.append(post_metrics)
                        new_posts_found += 1
                        
                        logging.info(f"✅ 發現新貼文 {new_posts_found}/{need_to_fetch}: {post_id}")
                        
                        # 只在最後一個或每2個發布進度，減少日誌噪音
                        if new_posts_found == need_to_fetch or (new_posts_found % 2 == 0):
                            await publish_progress(
                                task_id, 
                                "post_url_extracted",
                                username=username,
                                post_id=post_id,
                                current=new_posts_found,
                                total=need_to_fetch,
                                progress=new_posts_found / need_to_fetch,
                                urls_processed=i + 1
                            )
                
                # 使用 ordered_posts 而不是 posts.values() 來保持順序
                logging.info(f"✅ [Task: {task_id}] 創建了 {len(ordered_posts)} 個有序的基礎PostMetrics")
                
                # 關閉 page 但保留 context 供 fill_views_from_page 使用
                await page.close()

                # --- 🚀 增量模式：使用精確收集的結果 ---
                # 在增量模式下，ordered_posts已經是精確控制的結果
                if 'ordered_posts' in locals():
                    final_posts = ordered_posts  # 已經是精確數量，無需截斷
                    total_found = len(ordered_posts)
                    logging.info(f"🎯 [Task: {task_id}] 增量模式: 精確收集到{total_found}篇新貼文")
                else:
                    # 回退到原始方法（保留兼容性）
                    final_posts = list(posts.values())[:need_to_fetch]
                    total_found = len(final_posts)
                    logging.info(f"🔄 [Task: {task_id}] 回退模式: 限制到{need_to_fetch}篇")
                
                logging.info(f"🔄 [Task: {task_id}] 準備回傳最終資料：共發現 {total_found} 則貼文, 回傳 {len(final_posts)} 則")
                
                # --- 補齊詳細數據和觀看數 (在 browser context 還存在時執行) ---
                # 純 DOM 方案：一定要執行詳細數據補齊來獲取計數
                logging.info(f"🔍 [Task: {task_id}] 開始 DOM 數據補齊（likes, comments, content等）...")
                await publish_progress(task_id, "fill_details_start", username=username, posts_count=len(final_posts))
                
                try:
                    final_posts = await self.fill_post_details_from_page(final_posts, task_id=task_id, username=username)
                    logging.info(f"✅ [Task: {task_id}] 詳細數據補齊完成")
                    await publish_progress(task_id, "fill_details_completed", username=username, posts_count=len(final_posts))
                except Exception as e:
                    logging.warning(f"⚠️ [Task: {task_id}] 補齊詳細數據時發生錯誤: {e}")
                    await publish_progress(task_id, "fill_details_error", username=username, error=str(e))
                
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

            # 🚀 更新爬取狀態（關鍵優化）
            if final_posts:
                # 保存新貼文到數據庫
                saved_count = await crawl_history.upsert_posts(final_posts)
                
                # 更新crawl_state（使用最新的post_id）
                latest_post_id = final_posts[0].post_id if final_posts else None
                if latest_post_id:
                    await crawl_history.update_crawl_state(username, latest_post_id, saved_count)
                
                # 生成任務監控指標
                task_metrics = await crawl_history.get_task_metrics(username, need_to_fetch, len(final_posts))
                logging.info(f"📊 任務完成: {task_metrics}")
            
            batch = PostMetricsBatch(
                posts=final_posts,
                username=username,
                total_count=already_count + len(final_posts),  # 更新總數
                processing_stage="playwright_incremental_completed"
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
                            "text=/\\d+[\\.\\d]*[^\\d]?次瀏覽/, text=/\\d+.*views?/",  # 處理「4 萬次瀏覽」空格問題
                        ]
                        
                        for i, selector in enumerate(selectors):
                            try:
                                element = await page.wait_for_selector(selector, timeout=3000)
                                if element:
                                    view_text = await element.inner_text()
                                    parsed_views = parse_number(view_text)
                                    if parsed_views and parsed_views > 0:
                                        views_count = parsed_views
                                        extraction_method = f"dom_selector_{i+1}"
                                        logging.debug(f"   ✅ DOM 選擇器 {i+1} 獲取瀏覽數: {views_count:,}")
                                        break
                            except Exception:
                                continue
                    
                    # 更新結果 - 只在現有瀏覽數為 None 或 <= 0 時才更新
                    if views_count and views_count > 0:
                        if post.views_count is None or post.views_count <= 0:
                            post.views_count = views_count
                            post.views_fetched_at = datetime.utcnow()
                            logging.info(f"  ✅ 成功獲取 {post.post_id} 的瀏覽數: {views_count:,} (方法: {extraction_method})")
                            
                            # 發布進度
                            if task_id:
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
                            logging.info(f"  ℹ️ {post.post_id} 已有瀏覽數 {post.views_count:,}，跳過更新")
                    else:
                        if post.views_count is None:
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
                    
                    # === 步驟 1: 混合策略 - 攔截+重發請求（模仿成功的hybrid方法） ===
                    counts_data = {}
                    video_urls = set()
                    captured_graphql_request = {}
                    
                    async def handle_counts_response(response):
                        try:
                            import json
                            url = response.url.lower()
                            headers = response.request.headers
                            query_name = headers.get("x-fb-friendly-name", "")
                            
                            # 攔截計數查詢請求（保存headers和payload）
                            if ("/graphql" in url and response.status == 200 and 
                                "useBarcelonaBatchedDynamicPostCountsSubscriptionQuery" in query_name):
                                logging.info(f"   🎯 攔截到GraphQL計數查詢，保存請求信息...")
                                
                                # 保存請求信息（模仿hybrid_content_extractor.py的成功策略）
                                captured_graphql_request.update({
                                    "headers": dict(response.request.headers),
                                    "payload": response.request.post_data,
                                    "url": "https://www.threads.com/graphql/query"
                                })
                                
                                # 清理headers
                                clean_headers = captured_graphql_request["headers"].copy()
                                for h in ["host", "content-length", "accept-encoding"]:
                                    clean_headers.pop(h, None)
                                captured_graphql_request["clean_headers"] = clean_headers
                                
                                logging.info(f"   ✅ 成功保存GraphQL請求信息，準備重發...")
                                
                                # 也嘗試直接解析當前響應（作為備用）
                                try:
                                    data = await response.json()
                                    if "data" in data and "data" in data["data"] and "posts" in data["data"]["data"]:
                                        posts_list = data["data"]["data"]["posts"]
                                        if posts_list and len(posts_list) > 0:
                                            post_data = posts_list[0]
                                            if isinstance(post_data, dict):
                                                text_info = post_data.get("text_post_app_info", {}) or {}
                                                counts_data.update({
                                                    "likes": post_data.get("like_count") or 0,
                                                    "comments": text_info.get("direct_reply_count") or 0, 
                                                    "reposts": text_info.get("repost_count") or 0,
                                                    "shares": text_info.get("reshare_count") or 0
                                                })
                                                logging.info(f"   ✅ 直接攔截成功: 讚={counts_data['likes']}, 留言={counts_data['comments']}, 轉發={counts_data['reposts']}, 分享={counts_data['shares']}")
                                except Exception as e:
                                    logging.debug(f"   ⚠️ 直接解析失敗: {e}")
                            
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
                    
                    # === 步驟 2.5: 混合策略重發請求（模仿hybrid_content_extractor.py） ===
                    if captured_graphql_request and not counts_data:
                        logging.info(f"   🔄 使用保存的GraphQL請求信息重發請求...")
                        try:
                            import httpx
                            
                            # 從URL提取PK（如果可能）
                            target_pk = None
                            url_match = re.search(r'/post/([^/?]+)', post.url)
                            if url_match:
                                # 這裡我們需要從某個地方獲取PK，或者用其他方式
                                logging.info(f"   🔍 URL代碼: {url_match.group(1)}")
                            
                            # 準備重發請求
                            headers = captured_graphql_request["clean_headers"]
                            payload = captured_graphql_request["payload"]
                            
                            # 從頁面context獲取cookies
                            cookies_list = await self.context.cookies()
                            cookies = {cookie['name']: cookie['value'] for cookie in cookies_list}
                            
                            # 確保有認證
                            if not headers.get("authorization") and 'ig_set_authorization' in cookies:
                                auth_value = cookies['ig_set_authorization']
                                headers["authorization"] = f"Bearer {auth_value}" if not auth_value.startswith('Bearer') else auth_value
                            
                            # 發送HTTP請求到Threads API
                            async with httpx.AsyncClient(headers=headers, cookies=cookies, timeout=30.0, http2=True) as client:
                                api_response = await client.post("https://www.threads.com/graphql/query", data=payload)
                                
                                if api_response.status_code == 200:
                                    result = api_response.json()
                                    logging.info(f"   ✅ 重發請求成功，狀態: {api_response.status_code}")
                                    
                                    if "data" in result and result["data"] and "data" in result["data"] and "posts" in result["data"]["data"]:
                                        posts_list = result["data"]["data"]["posts"]
                                        logging.info(f"   📊 重發請求響應包含 {len(posts_list)} 個貼文")
                                        
                                        # 使用第一個貼文（當前頁面的主要貼文）
                                        if posts_list and len(posts_list) > 0:
                                            post_data = posts_list[0]
                                            if isinstance(post_data, dict):
                                                text_info = post_data.get("text_post_app_info", {}) or {}
                                                counts_data.update({
                                                    "likes": post_data.get("like_count") or 0,
                                                    "comments": text_info.get("direct_reply_count") or 0, 
                                                    "reposts": text_info.get("repost_count") or 0,
                                                    "shares": text_info.get("reshare_count") or 0
                                                })
                                                logging.info(f"   🎯 重發請求成功獲取數據: 讚={counts_data['likes']}, 留言={counts_data['comments']}, 轉發={counts_data['reposts']}, 分享={counts_data['shares']}")
                                else:
                                    logging.warning(f"   ⚠️ 重發請求失敗，狀態: {api_response.status_code}")
                                
                        except Exception as e:
                            logging.warning(f"   ⚠️ 重發請求過程失敗: {e}")
                    
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
                    
                    # === 步驟 3.5: DOM 計數後援（當 GraphQL 攔截失敗時） ===
                    if not counts_data:
                        logging.warning(f"   🔄 GraphQL 計數攔截失敗，開始 DOM 計數後援...")
                        
                        # 先檢查頁面狀態
                        page_title = await page.title()
                        page_url = page.url
                        logging.info(f"   📄 頁面狀態 - 標題: {page_title}, URL: {page_url}")
                        
                        count_selectors = {
                            "likes": [
                                # English selectors
                                "button[aria-label*='likes'] span",
                                "button[aria-label*='Like'] span", 
                                "span:has-text(' likes')",
                                "span:has-text(' like')",
                                "button svg[aria-label='Like'] + span",
                                "button[aria-label*='like']",
                                # Chinese selectors
                                "button[aria-label*='個喜歡'] span",
                                "button[aria-label*='喜歡']",
                                # Generic patterns
                                "button[data-testid*='like'] span",
                                "div[role='button'][aria-label*='like'] span"
                            ],
                            "comments": [
                                # English selectors
                                "a[href$='#comments'] span",
                                "span:has-text(' comments')",
                                "span:has-text(' comment')",
                                "a:has-text('comments')",
                                "button[aria-label*='comment'] span",
                                # Chinese selectors
                                "span:has-text(' 則留言')",
                                "a:has-text('則留言')",
                                # Generic patterns
                                "button[data-testid*='comment'] span",
                                "div[role='button'][aria-label*='comment'] span"
                            ],
                            "reposts": [
                                # English selectors
                                "span:has-text(' reposts')",
                                "span:has-text(' repost')",
                                "button[aria-label*='repost'] span",
                                "a:has-text('reposts')",
                                # Chinese selectors
                                "span:has-text(' 次轉發')",
                                "a:has-text('轉發')",
                                # Generic patterns
                                "button[data-testid*='repost'] span"
                            ],
                            "shares": [
                                # English selectors
                                "span:has-text(' shares')",
                                "span:has-text(' share')",
                                "button[aria-label*='share'] span",
                                "a:has-text('shares')",
                                # Chinese selectors
                                "span:has-text(' 次分享')",
                                "a:has-text('分享')",
                                # Generic patterns
                                "button[data-testid*='share'] span"
                            ],
                        }
                        
                        # 先進行通用元素掃描，並智能提取數字
                        logging.info(f"   🔍 通用元素掃描和智能數字提取...")
                        dom_counts = {}
                        try:
                            all_buttons = await page.locator('button').all_inner_texts()
                            all_spans = await page.locator('span').all_inner_texts()
                            number_elements = [text for text in (all_buttons + all_spans) if any(char.isdigit() for char in text)]
                            logging.info(f"   🔢 找到包含數字的元素: {number_elements[:20]}")
                            
                            # === 🎯 智能數字識別：從找到的數字中提取社交數據 ===
                            pure_numbers = []
                            for text in number_elements:
                                # 跳過明顯不是互動數據的文字
                                if any(skip in text for skip in ['瀏覽', '次瀏覽', '觀看', '天', '小時', '分鐘', '秒', 'on.natgeo.com']):
                                    continue
                                    
                                number = parse_number(text)
                                if number and number > 0:
                                    pure_numbers.append((number, text))
                                    logging.info(f"   📊 提取數字: {number} (從 '{text}')")
                            
                            # 根據數字大小智能分配（通常：likes > comments > reposts > shares）
                            pure_numbers.sort(reverse=True)  # 從大到小排序
                            
                            if len(pure_numbers) >= 4:
                                dom_counts["likes"] = pure_numbers[0][0]
                                dom_counts["comments"] = pure_numbers[1][0] 
                                dom_counts["reposts"] = pure_numbers[2][0]
                                dom_counts["shares"] = pure_numbers[3][0]
                                logging.info(f"   🎯 智能分配4個數字: 讚={dom_counts['likes']}, 留言={dom_counts['comments']}, 轉發={dom_counts['reposts']}, 分享={dom_counts['shares']}")
                            elif len(pure_numbers) >= 2:
                                dom_counts["likes"] = pure_numbers[0][0]
                                dom_counts["comments"] = pure_numbers[1][0]
                                logging.info(f"   🎯 智能分配2個數字: 讚={dom_counts['likes']}, 留言={dom_counts['comments']}")
                            elif len(pure_numbers) >= 1:
                                dom_counts["likes"] = pure_numbers[0][0]
                                logging.info(f"   🎯 智能分配1個數字: 讚={dom_counts['likes']}")
                                
                        except Exception as e:
                            logging.warning(f"   ⚠️ 智能數字提取失敗: {e}")
                        
                        # 如果智能提取成功，跳過傳統選擇器；否則繼續嘗試
                        if not dom_counts:
                            logging.info(f"   ⚠️ 智能提取失敗，回到傳統選擇器...")
                            for key, sels in count_selectors.items():
                                logging.info(f"   🔍 嘗試提取 {key} 數據...")
                                for i, sel in enumerate(sels):
                                    try:
                                        el = page.locator(sel).first
                                        count = await el.count()
                                        if count > 0:
                                            text = (await el.inner_text()).strip()
                                            logging.info(f"   📝 選擇器 {i+1}/{len(sels)} '{sel}' 找到文字: '{text}'")
                                            n = parse_number(text)
                                            if n and n > 0:
                                                dom_counts[key] = n
                                                logging.info(f"   ✅ DOM 成功提取 {key}: {n} (選擇器: {sel})")
                                                break
                                            else:
                                                logging.info(f"   ⚠️ 無法解析數字: '{text}' -> {n}")
                                        else:
                                            logging.info(f"   ❌ 選擇器 {i+1}/{len(sels)} 未找到元素: '{sel}'")
                                    except Exception as e:
                                        logging.info(f"   ⚠️ 選擇器 {i+1}/{len(sels)} '{sel}' 錯誤: {e}")
                                        continue
                                
                                if key not in dom_counts:
                                    logging.warning(f"   ❌ 無法找到 {key} 數據")
                        
                        if dom_counts:
                            counts_data = {
                                "likes": dom_counts.get("likes", 0),
                                "comments": dom_counts.get("comments", 0),
                                "reposts": dom_counts.get("reposts", 0),
                                "shares": dom_counts.get("shares", 0),
                            }
                            logging.info(f"   🎯 DOM 計數後援成功: {counts_data}")
                        else:
                            # 所有方法都失敗時，記錄頁面狀態用於調試
                            logging.warning(f"   ❌ GraphQL攔截和DOM後援都失敗了！")
                            try:
                                page_title = await page.title()
                                page_url = page.url
                                logging.info(f"   📄 失敗頁面分析 - 標題: {page_title}")
                                logging.info(f"   🔗 失敗頁面分析 - URL: {page_url}")
                                
                                # 檢查頁面是否正常載入
                                all_text = await page.inner_text('body')
                                if "登入" in all_text or "login" in all_text.lower():
                                    logging.warning(f"   ⚠️ 可能遇到登入頁面")
                                elif len(all_text) < 100:
                                    logging.warning(f"   ⚠️ 頁面內容太少，可能載入失敗")
                                else:
                                    logging.info(f"   📝 頁面內容長度: {len(all_text)} 字元")
                                    
                                    # 檢查是否有互動按鈕
                                    like_buttons = await page.locator('[aria-label*="like"], [aria-label*="Like"], [aria-label*="喜歡"]').count()
                                    comment_buttons = await page.locator('[aria-label*="comment"], [aria-label*="Comment"], [aria-label*="留言"]').count()
                                    logging.info(f"   📊 找到按鈕: 讚 {like_buttons} 個, 留言 {comment_buttons} 個")
                                    
                                    # 嘗試找到任何數字
                                    all_numbers = await page.locator(':text-matches("\\d+")').all_inner_texts()
                                    if all_numbers:
                                        logging.info(f"   🔢 頁面所有數字: {all_numbers[:15]}")  # 顯示前15個
                                    
                                    # 檢查是否有阻擋元素
                                    modal_count = await page.locator('[role="dialog"], .modal, [data-testid*="modal"]').count()
                                    if modal_count > 0:
                                        logging.warning(f"   ⚠️ 發現 {modal_count} 個模態框可能阻擋內容")
                                        
                            except Exception as debug_e:
                                logging.warning(f"   ⚠️ 失敗頁面分析錯誤: {debug_e}")
                    
                    # === 步驟 4: 更新貼文數據 ===
                    updated = False
                    
                    # 更新計數數據 - 只在現有數據為 None 或 0 時才更新
                    if counts_data:
                        if post.likes_count in (None, 0) and (counts_data.get("likes") or 0) > 0:
                            post.likes_count = counts_data["likes"]
                            updated = True
                        if post.comments_count in (None, 0) and (counts_data.get("comments") or 0) > 0:
                            post.comments_count = counts_data["comments"]
                            updated = True
                        if post.reposts_count in (None, 0) and (counts_data.get("reposts") or 0) > 0:
                            post.reposts_count = counts_data["reposts"]
                            updated = True
                        if post.shares_count in (None, 0) and (counts_data.get("shares") or 0) > 0:
                            post.shares_count = counts_data["shares"]
                            updated = True
                    
                    # 更新內容數據 - 只在現有數據為空時才更新
                    if content_data.get("content") and not post.content:
                        post.content = content_data["content"]
                        updated = True
                    
                    if content_data.get("images") and not post.images:
                        post.images = content_data["images"]
                        updated = True
                    
                    if content_data.get("videos") and not post.videos:
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


