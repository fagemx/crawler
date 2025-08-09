"""
貼文數據解析器

負責從 GraphQL API 響應中解析出 PostMetrics 對象
使用強健的多鍵 fallback 機制處理欄位變動
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

from common.models import PostMetrics
from common.utils import first_of, parse_thread_item, generate_post_url
from .number_parser import parse_number
from ..config.field_mappings import FIELD_MAP


# 調試檔案路徑
DEBUG_DIR = Path(__file__).parent.parent / "debug"
DEBUG_DIR.mkdir(exist_ok=True)
DEBUG_FAILED_ITEM_FILE = DEBUG_DIR / "failed_post_sample.json"


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
    
    # 統一台北時間：timestamp→UTC→台北，或無值時用台北現在
    if created_at and isinstance(created_at, (int, float)):
        utc_dt = datetime.fromtimestamp(created_at, tz=timezone.utc)
        created_taipei = utc_dt.astimezone(timezone(timedelta(hours=8))).replace(tzinfo=None)
    else:
        created_taipei = datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)

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
        created_at=created_taipei,
        images=images,
        videos=videos,
        # 新增：直接從 API 解析 views_count（按指引優先嘗試 API）
        views_count=parse_number(first_of(post, *FIELD_MAP["view_count"])),
    )