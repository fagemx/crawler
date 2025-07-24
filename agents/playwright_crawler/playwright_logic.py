import asyncio
import json
import logging
import random
import re
import tempfile
import uuid
from pathlib import Path
from typing import Dict, List, Optional, AsyncIterable

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

from common.settings import get_settings
from common.a2a import stream_text, stream_data, stream_status, stream_error, TaskState
from common.models import PostMetrics, PostMetricsBatch

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
            from .config import DEBUG_FAILED_ITEM_FILE
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
                        from .config import SAMPLE_THREAD_ITEM_FILE
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
                # 使用回調函數發送串流訊息
                stream_callback(f"✅ 從 {qname} 解析到 {new_count} 則新貼文，總數: {len(posts)}")
                
            # 記錄新發現的查詢名稱（用於除錯）
            if qname not in self.known_queries:
                self.known_queries.add(qname)
                # 可選：寫入檔案以供日後分析
                try:
                    from pathlib import Path
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
    ) -> AsyncIterable[Dict]:
        """
        使用指定的認證內容爬取貼文。

        Args:
            username: 目標使用者名稱 (不含 @)
            max_posts: 最大貼文數
            auth_json_content: auth.json 的內容
            task_id: 任務 ID

        Yields:
            串流回傳的狀態和資料
        """
        target_url = f"https://www.threads.com/@{username}"
        posts = {}
        
        # 1. 安全地處理 auth.json
        # 使用有唯一性的臨時檔案，並確保任務結束後刪除
        auth_file = Path(tempfile.gettempdir()) / f"{task_id or uuid.uuid4()}_auth.json"
        
        try:
            with open(auth_file, "w") as f:
                json.dump(auth_json_content, f)

            yield stream_status(TaskState.RUNNING, "Playwright 爬蟲準備中...", 0.1)

            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=self.settings.headless,
                    timeout=self.settings.navigation_timeout,
                    args=["--no-sandbox", "--disable-dev-shm-usage"]
                )
                ctx = await browser.new_context(
                    storage_state=str(auth_file),
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                    locale="en-US",
                    has_touch=True,
                    accept_downloads=False
                )
                page = await ctx.new_page()

                # 修正 console handler（.text 是屬性不是方法）
                page.on("console", lambda m: logging.info(f"CONSOLE [{m.type}] {m.text}"))

                # 建立串流回調函數（用 list 儲存訊息供後續 yield）
                stream_messages = []
                def add_stream_message(message):
                    stream_messages.append(stream_text(message))

                # 先掛載 response listener（在 goto 之前）
                response_handler = self._build_response_handler(
                    username, posts, task_id, max_posts, add_stream_message
                )
                page.on("response", response_handler)

                yield stream_text(f"導覽至目標頁面: {target_url}")
                await page.goto(target_url, wait_until="networkidle", timeout=self.settings.navigation_timeout)

                # 檢查登入狀態
                try:
                    current_url = page.url
                    is_login_page = "/login" in current_url or await page.locator("text=Log in").count() > 0
                    if is_login_page:
                        yield stream_text("⚠️ 偵測到登入頁面，認證可能已過期")
                        logging.warning(f"目前 URL: {current_url}，可能需要重新產生 auth.json")
                    else:
                        yield stream_text("✅ 成功載入使用者頁面")
                except Exception as e:
                    logging.warning(f"檢查登入狀態時發生錯誤: {e}")

                yield stream_text("頁面載入完成，開始滾動...")

                # --- 滾動與延遲邏輯 ---
                scroll_attempts_without_new_posts = 0
                max_retries = 5

                while len(posts) < max_posts:
                    posts_before_scroll = len(posts)
                    
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

                    try:
                        # 等待 GraphQL 請求，增加穩定性
                        async with page.expect_response(lambda res: GRAPHQL_RE.search(res.url), timeout=10000):
                            pass
                    except PlaywrightTimeoutError:
                        logging.warning(f"⏳ [Task: {task_id}] 滾動後等待網路回應逾時。")

                    # 加入您指定的隨機延遲
                    delay = random.uniform(2.0, 3.5)
                    await asyncio.sleep(delay)

                    # 發送累積的串流訊息
                    for message in stream_messages:
                        yield message
                    stream_messages.clear()

                    if len(posts) == posts_before_scroll:
                        scroll_attempts_without_new_posts += 1
                        yield stream_text(f"滾動後未發現新貼文 (嘗試 {scroll_attempts_without_new_posts}/{max_retries})")
                        if scroll_attempts_without_new_posts >= max_retries:
                            yield stream_text("已達頁面末端或無新內容，停止滾動。")
                            break
                    else:
                        scroll_attempts_without_new_posts = 0



                await ctx.close()

            # --- 整理並回傳結果 ---
            final_posts = list(posts.values())
            logging.info(f"🔄 [Task: {task_id}] 準備發送最終資料：共 {len(final_posts)} 則貼文")
            
            batch = PostMetricsBatch(
                posts=final_posts[:max_posts], # 確保不會超過請求的數量
                username=username,
                total_count=len(final_posts),
                processing_stage="playwright_completed"
            )
            
            logging.info(f"📤 [Task: {task_id}] 發送 PostMetricsBatch：{len(batch.posts)} 則貼文")
            yield stream_data(batch.dict(), final=True)
            logging.info(f"✅ [Task: {task_id}] 最終資料已發送完成")

        except Exception as e:
            logging.error(f"❌ [Task: {task_id}] Playwright 爬取過程中發生錯誤: {e}", exc_info=True)
            yield stream_error(f"Playwright 爬取失敗: {e}")
        finally:
            # 暫時註解掉，以便除錯
            # if auth_file.exists():
            #     auth_file.unlink()
            #     logging.info(f"🗑️ [Task: {task_id}] 已刪除臨時認證檔案: {auth_file}")
            pass 