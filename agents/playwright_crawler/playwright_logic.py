import json
import asyncio
import logging
import random
import re
import tempfile
import uuid
from pathlib import Path
from typing import Dict, List, Optional, AsyncIterable, Callable
from datetime import datetime

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError, Browser, BrowserContext, Page

from common.settings import get_settings
from common.a2a import stream_text, stream_data, stream_status, stream_error, TaskState
from common.models import PostMetrics, PostMetricsBatch

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
        ["text_post_app_info", "repost_count"],
        "repostCount", "share_count", "shareCount"
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
    ]
}

def first_of(obj, *keys):
    """
    多鍵 fallback 機制：依序嘗試多個可能的鍵名，回傳第一個非空值。
    支援巢狀鍵：["parent", "child"] 會取 obj["parent"]["child"]
    """
    for key in keys:
        try:
            if isinstance(key, (list, tuple)):
                # 巢狀鍵處理
                value = obj
                for sub_key in key:
                    if not isinstance(value, dict) or sub_key not in value:
                        value = None
                        break
                    value = value[sub_key]
            else:
                # 單一鍵處理
                value = obj.get(key) if isinstance(obj, dict) else None
            
            # 檢查值是否有效（非 None、空字串、空列表、空字典）
            if value not in (None, "", [], {}):
                return value
        except (KeyError, TypeError, AttributeError):
            continue
    return None


def find_post_dict(item: dict) -> Optional[dict]:
    """
    在 thread_item 裡自動找到真正的貼文 dict。
    支援不同版本的 GraphQL 結構變化。
    回傳含有 pk/id 的那層。
    """
    # 1) 傳統結構
    if 'post' in item and isinstance(item['post'], dict):
        return item['post']
        
    # 2) 新版結構：post_info / postInfo / postV2
    for key in ('post_info', 'postInfo', 'postV2', 'media_data', 'thread_data'):
        if key in item and isinstance(item[key], dict):
            return item[key]
    
    # 3) 深度搜尋：找第一個有 pk 或 id 的子 dict
    def search_for_post(obj, max_depth=3):
        if max_depth <= 0:
            return None
            
        if isinstance(obj, dict):
            # 檢查當前層是否為貼文物件
            if ('pk' in obj or 'id' in obj) and 'user' in obj:
                return obj
            # 遞歸搜尋子物件
            for value in obj.values():
                result = search_for_post(value, max_depth - 1)
                if result:
                    return result
        elif isinstance(obj, list) and obj:
            # 搜尋列表中的第一個元素
            return search_for_post(obj[0], max_depth - 1)
            
        return None
    
    return search_for_post(item)


def parse_post_data(post_data: dict, username: str) -> Optional[PostMetrics]:
    """
    強健的貼文解析器，使用多鍵 fallback 機制處理欄位變動。
    支援 Threads GraphQL API 的不同版本和欄位命名變化。
    """
    # 使用智能搜尋找到真正的貼文物件
    post = find_post_dict(post_data)
    
    if not post:
        logging.info(f"❌ 找不到有效的 post 物件，收到的資料鍵: {list(post_data.keys())}")
        logging.info(f"❌ post_data 內容範例: {str(post_data)[:300]}...")
        
        # 自動儲存第一筆 raw JSON 供分析
        try:
            if not DEBUG_FAILED_ITEM_FILE.exists():
                DEBUG_FAILED_ITEM_FILE.write_text(json.dumps(post_data, indent=2, ensure_ascii=False))
                logging.info(f"📝 已儲存失敗範例至 {DEBUG_FAILED_ITEM_FILE}")
        except Exception:
            pass
            
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

    url = f"https://www.threads.net/t/{code}"

    # 使用多鍵 fallback 解析所有欄位
    author = first_of(post, *FIELD_MAP["author"]) or username
    content = first_of(post, *FIELD_MAP["content"]) or ""
    like_count = first_of(post, *FIELD_MAP["like_count"]) or 0
    comment_count = first_of(post, *FIELD_MAP["comment_count"]) or 0
    share_count = first_of(post, *FIELD_MAP["share_count"]) or 0
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

    # 成功解析，記錄部分資訊供除錯
    logging.info(f"✅ 成功解析貼文 {post_id}: 作者={author}, 讚數={like_count}, 內容前50字={content[:50]}...")
    
    return PostMetrics(
        url=url,
        post_id=str(post_id),
        username=username,
        source="playwright",
        processing_stage="playwright_crawled",
        likes_count=int(like_count) if isinstance(like_count, (int, str)) and str(like_count).isdigit() else 0,
        comments_count=int(comment_count) if isinstance(comment_count, (int, str)) and str(comment_count).isdigit() else 0,
        reposts_count=int(share_count) if isinstance(share_count, (int, str)) and str(share_count).isdigit() else 0,
        content=content,
        created_at=created_at,
    )


class PlaywrightLogic:
    """
    使用 Playwright 進行爬蟲的核心邏輯。
    """
    def __init__(self):
        self.settings = get_settings().playwright
        self.known_queries = set()  # 追蹤已見過的查詢名稱

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
                            SAMPLE_THREAD_ITEM_FILE.write_text(json.dumps(thread_items[0], indent=2, ensure_ascii=False))
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
        target_url = f"https://www.threads.com/@{username}"
        posts: Dict[str, PostMetrics] = {}
        
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
                ctx = await browser.new_context(
                    storage_state=str(auth_file),
                    user_agent=self.settings.user_agent, # 從設定讀取
                    viewport={"width": 1920, "height": 1080},
                    locale="en-US",
                    has_touch=True,
                    accept_downloads=False
                )
                page = await ctx.new_page()
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
                
                await browser.close()

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
                            "content": post.content,
                            "created_at": post.created_at.isoformat() if post.created_at else None
                        } for post in final_posts
                    ]
                }
                
                # 使用時間戳記避免檔案衝突
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                raw_file = DEBUG_DIR / f"crawl_data_{timestamp}_{task_id[:8]}.json"
                raw_file.write_text(json.dumps(raw_data, indent=2, ensure_ascii=False))
                logging.info(f"💾 [Task: {task_id}] 已保存原始抓取資料至: {raw_file}")
                
            except Exception as e:
                logging.warning(f"⚠️ [Task: {task_id}] 保存調試資料失敗: {e}")
            
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
            raise
        
        finally:
            if auth_file.exists():
                auth_file.unlink()
                logging.info(f"🗑️ [Task: {task_id}] 已刪除臨時認證檔案: {auth_file}") 