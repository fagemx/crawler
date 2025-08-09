from typing import List, Dict, Any, Optional, Tuple
import asyncio
import sys

# Windows: 修正 asyncio 子行程政策，避免 Playwright NotImplementedError
if sys.platform == "win32":
    try:
        # 設定 Windows 相容的事件循環政策
        import multiprocessing
        multiprocessing.set_start_method('spawn', force=True)
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

from common.db_client import DatabaseClient, get_db_client
from services.rustfs_client import get_rustfs_client
from datetime import datetime
import json
import re

# 可選：直接使用爬蟲的細節抽取器與邏輯，實作單篇刷新
try:
    from agents.playwright_crawler.extractors.details_extractor import DetailsExtractor
    from agents.playwright_crawler.playwright_logic import PlaywrightLogic
    from common.config import get_auth_file_path
    from common.models import PostMetrics
    _PLAYWRIGHT_AVAILABLE = True
except Exception:
    _PLAYWRIGHT_AVAILABLE = False


class MediaDownloadService:
    """提供媒體下載所需的統計、清單與執行能力（基於 Playwright 資料）。"""

    async def get_account_media_stats(self, limit: int = 50) -> List[Dict[str, Any]]:
        """彙總各帳號圖片/影片總數、已配對、已完成、待下載數。"""
        db = DatabaseClient()
        await db.init_pool()
        try:
            query = f"""
        WITH pv AS (
            SELECT username,
                   url AS post_url,
                   jsonb_array_elements_text(COALESCE(images::jsonb, '[]'::jsonb)) AS media_url,
                   'image' AS media_type
            FROM playwright_post_metrics
            UNION ALL
            SELECT username,
                   url AS post_url,
                   jsonb_array_elements_text(COALESCE(videos::jsonb, '[]'::jsonb)) AS media_url,
                   'video' AS media_type
            FROM playwright_post_metrics
        ),
        agg AS (
            SELECT username,
                   COUNT(*) FILTER (WHERE media_type='image') AS total_images,
                   COUNT(*) FILTER (WHERE media_type='video') AS total_videos
            FROM pv GROUP BY username
        ),
        paired AS (
            SELECT pv.username,
                   COUNT(*) FILTER (WHERE pv.media_type='image' AND mf.id IS NOT NULL) AS paired_images,
                   COUNT(*) FILTER (WHERE pv.media_type='video' AND mf.id IS NOT NULL) AS paired_videos,
                   COUNT(*) FILTER (WHERE pv.media_type='image' AND mf.download_status='completed') AS completed_images,
                   COUNT(*) FILTER (WHERE pv.media_type='video' AND mf.download_status='completed') AS completed_videos
            FROM pv
            LEFT JOIN media_files mf ON mf.original_url = pv.media_url
            GROUP BY pv.username
        )
        SELECT a.username,
               a.total_images, a.total_videos,
               p.paired_images, p.paired_videos,
               p.completed_images, p.completed_videos,
               GREATEST(a.total_images - COALESCE(p.completed_images,0), 0) AS pending_images,
               GREATEST(a.total_videos - COALESCE(p.completed_videos,0), 0) AS pending_videos
        FROM agg a
        JOIN paired p USING(username)
        ORDER BY (GREATEST(a.total_images - COALESCE(p.completed_images,0),0) + GREATEST(a.total_videos - COALESCE(p.completed_videos,0),0)) DESC
        LIMIT {limit}
        """
            return await db.fetch_all(query)
        finally:
            await db.close_pool()

    async def build_download_plan(
        self,
        username: str,
        media_types: List[str],
        sort_by: str = "none",
        top_k: Optional[int] = None,
        skip_completed: bool = True,
        only_unpaired: bool = False,
        retry_failed_only: bool = False,
    ) -> Dict[str, List[str]]:
        """建立下載計畫：回傳 {post_url: [media_url,...]} 的映射。"""
        db = DatabaseClient()
        await db.init_pool()

        type_filters = []
        if "image" in media_types:
            type_filters.append("'image'")
        if "video" in media_types:
            type_filters.append("'video'")
        if not type_filters:
            return {}
        type_sql = ",".join(type_filters)

        # 僅重試失敗：改由 media_files 取清單
        if retry_failed_only:
            try:
                type_filters = set(media_types)
                rows = await db.fetch_all(
                    """
                    SELECT mf.post_url AS post_url, mf.original_url AS media_url, mf.media_type
                    FROM media_files mf
                    JOIN playwright_post_metrics ppm ON ppm.url = mf.post_url
                    WHERE ppm.username = $1 AND mf.download_status = 'failed'
                    ORDER BY mf.id ASC
                    """,
                    username,
                )

                plan: Dict[str, List[str]] = {}
                seen: set = set()
                for r in rows:
                    media_url = r["media_url"]
                    mtype = r.get("media_type") or "image"
                    if type_filters and mtype not in type_filters:
                        continue
                    if media_url in seen:
                        continue
                    seen.add(media_url)
                    plan.setdefault(r["post_url"], []).append(media_url)
                return plan
            finally:
                await db.close_pool()

        # 先鎖定貼文集合（排序 Top-N）
        top_posts_cte = ""
        using_top_posts = False
        if sort_by and sort_by != "none" and top_k and isinstance(top_k, int):
            sort_col = {
                "views": "views_count",
                "likes": "likes_count",
                "comments": "comments_count",
                "reposts": "reposts_count",
            }.get(sort_by, None)
            if sort_col:
                top_posts_cte = (
                    "top_posts AS (\n"
                    "    SELECT url\n"
                    "    FROM playwright_post_metrics\n"
                    "    WHERE username = $1\n"
                    f"    ORDER BY {sort_col} DESC NULLS LAST\n"
                    f"    LIMIT {top_k}\n"
                    ")\n"
                )
                using_top_posts = True
        
        # 展開媒體 URL（修正 WITH 順序，先定義 top_posts 再引用）
        where_clause = 'WHERE url IN (SELECT url FROM top_posts)' if using_top_posts else 'WHERE username = $1'
        # 若使用 top_posts，需在下一個 CTE 之前加逗號
        with_prefix = f"WITH {top_posts_cte},\n" if using_top_posts else "WITH "
        pv_cte = (
            f"{with_prefix}"
            "base AS (\n"
            f"    SELECT url, username, images, videos FROM playwright_post_metrics {where_clause}\n"
            "),\n"
            "pv AS (\n"
            "    SELECT username, url AS post_url,\n"
            "           jsonb_array_elements_text(COALESCE(images::jsonb,'[]'::jsonb)) AS media_url,\n"
            "           'image' AS media_type\n"
            "    FROM base\n"
            "    UNION ALL\n"
            "    SELECT username, url AS post_url,\n"
            "           jsonb_array_elements_text(COALESCE(videos::jsonb,'[]'::jsonb)) AS media_url,\n"
            "           'video' AS media_type\n"
            "    FROM base\n"
            ")\n"
            "SELECT post_url, media_url, media_type\n"
            "FROM pv\n"
            f"WHERE media_type IN ({type_sql})\n"
        )
        pv_cte = "".join(pv_cte)

        try:
            rows = await db.fetch_all(pv_cte, username)

            # 過濾條件：已完成 / 未配對
            if skip_completed or only_unpaired:
                # 取 media_files 對應狀態
                url_set = [r["media_url"] for r in rows]
                if url_set:
                    placeholders = ",".join([f"${i+1}" for i in range(len(url_set))])
                    mf_rows = await db.fetch_all(
                        f"""
                        SELECT original_url, download_status
                        FROM media_files
                        WHERE original_url IN ({placeholders})
                        """,
                        *url_set
                    )
                    status_map = {m["original_url"]: m.get("download_status") for m in mf_rows}
                else:
                    status_map = {}
            else:
                status_map = {}

            plan: Dict[str, List[str]] = {}
            seen: set = set()
            for r in rows:
                media_url = r["media_url"]
                if media_url in seen:
                    continue
                seen.add(media_url)

                if skip_completed and status_map.get(media_url) == "completed":
                    continue
                if only_unpaired and media_url in status_map:
                    continue

                post_url = r["post_url"]
                plan.setdefault(post_url, []).append(media_url)
            return plan
        finally:
            await db.close_pool()

    async def run_download(self, plan: Dict[str, List[str]], concurrency_per_post: int = 3) -> Dict[str, Any]:
        """執行下載計畫，逐貼文批次下載到 RustFS。"""
        client = await get_rustfs_client()

        total_media = sum(len(v) for v in plan.values())
        success = 0
        failed = 0
        details: List[Dict[str, Any]] = []

        for post_url, media_urls in plan.items():
            try:
                results = await client.download_and_store_media(post_url, media_urls, max_concurrent=concurrency_per_post)
                for res in results:
                    if res.get("status") == "completed":
                        success += 1
                    else:
                        failed += 1
                    details.append({"post_url": post_url, **res})
            except Exception as e:
                # 嘗試重新初始化 db 連線池（處理 pool is closed）
                try:
                    db = await get_db_client()
                    await db.close_pool()
                    await db.init_pool()
                except Exception:
                    pass
                # 整批失敗：計入失敗數
                batch_failed = len(media_urls)
                failed += batch_failed
                for u in media_urls:
                    details.append({"post_url": post_url, "original_url": u, "status": "failed", "error": str(e)})

            # 若該貼文有 403/Forbidden 的失敗，嘗試「刷新URL後重試」
            post_failed_errors = [d for d in details if d.get("post_url") == post_url and d.get("status") == "failed"]
            if any("403" in (d.get("error") or "") or "Forbidden" in (d.get("error") or "") for d in post_failed_errors):
                try:
                    refreshed = await self.refresh_post_media_urls(post_url)
                    new_urls = []
                    # 以需求的媒體類型為主，若不可得則全量
                    if refreshed.get("images"):
                        new_urls.extend(refreshed["images"])
                    if refreshed.get("videos"):
                        new_urls.extend(refreshed["videos"])
                    # 重試下載
                    if new_urls:
                        retry_results = await client.download_and_store_media(post_url, new_urls, max_concurrent=concurrency_per_post)
                        for rr in retry_results:
                            if rr.get("status") == "completed":
                                success += 1
                            else:
                                failed += 1
                            details.append({"post_url": post_url, **rr, "retry_after_refresh": True})
                except Exception as re_err:
                    details.append({"post_url": post_url, "status": "failed", "error": f"refresh-retry-failed: {re_err}"})

        return {
            "total": total_media,
            "success": success,
            "failed": failed,
            "details": details,
        }

    # ---------------- 刷新 URL 能力 ----------------
    async def refresh_post_media_urls(self, post_url: str) -> Dict[str, Any]:
        """
        單篇刷新：用 Playwright 重開貼文頁，抓取最新 images/videos，更新到 playwright_post_metrics。
        回傳 {username, post_id, images, videos, updated}
        """
        if not _PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright 模組不可用，無法刷新 URL")

        # 從 URL 解析 username/code
        username, code = self._parse_username_code(post_url)
        post_id = f"{username}_{code}" if username and code else code or post_url

        # 準備 Playwright 環境
        logic = PlaywrightLogic()
        auth_path = get_auth_file_path()
        with open(auth_path, "r", encoding="utf-8") as f:
            auth_json = json.load(f)

        task_id = f"refresh_{int(datetime.utcnow().timestamp())}"
        
        # Windows: 確保使用正確的事件循環和子程序處理
        if sys.platform == "win32":
            try:
                import os
                # 設定環境變數確保 Playwright 使用正確的子程序模式
                os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', '0')
                current_loop = asyncio.get_running_loop()
                if hasattr(current_loop, '_default_executor'):
                    current_loop._default_executor = None
                # 強制使用 ProactorEventLoop（Windows 推薦）
                if not isinstance(current_loop, asyncio.ProactorEventLoop):
                    new_loop = asyncio.ProactorEventLoop()
                    asyncio.set_event_loop(new_loop)
            except Exception as e:
                print(f"⚠️ Windows Playwright setup warning: {e}")
        
        await logic._setup_browser_and_auth(auth_json, task_id)  # 使用現有私有方法完成初始化

        try:
            extractor = DetailsExtractor()
            # 建立最小 PostMetrics 物件
            pm = PostMetrics(
                post_id=post_id,
                username=username or "unknown",
                url=post_url,
                content=None,
                likes_count=None,
                comments_count=None,
                reposts_count=None,
                shares_count=None,
                images=[],
                videos=[],
                created_at=datetime.utcnow(),
            )

            await extractor.fill_post_details_from_page([pm], logic.context, task_id=task_id, username=pm.username)

            # 更新 DB: playwright_post_metrics（只更新 images/videos/content/post_published_at/tags）
            await self._upsert_playwright_post(
                pm.username, pm.post_id, pm.url, pm.content,
                pm.views_count, pm.likes_count, pm.comments_count, pm.reposts_count, pm.shares_count,
                pm.calculated_score, pm.post_published_at, pm.tags, pm.images, pm.videos
            )

            return {
                "username": pm.username,
                "post_id": pm.post_id,
                "images": pm.images,
                "videos": pm.videos,
                "updated": True,
            }
        finally:
            try:
                if logic.context:
                    await logic.context.close()
            except Exception:
                pass
            try:
                if logic.browser:
                    await logic.browser.close()
            except Exception:
                pass

    async def _upsert_playwright_post(
        self,
        username: str,
        post_id: str,
        url: str,
        content: Optional[str],
        views_count: Optional[int],
        likes_count: Optional[int],
        comments_count: Optional[int],
        reposts_count: Optional[int],
        shares_count: Optional[int],
        calculated_score: Optional[float],
        post_published_at: Optional[datetime],
        tags: List[str],
        images: List[str],
        videos: List[str],
    ) -> None:
        """將刷新結果寫回 playwright_post_metrics。"""
        db = DatabaseClient()
        await db.init_pool()
        try:
            tags_json = json.dumps(tags or [], ensure_ascii=False)
            images_json = json.dumps(images or [], ensure_ascii=False)
            videos_json = json.dumps(videos or [], ensure_ascii=False)

            await db.execute(
                """
                INSERT INTO playwright_post_metrics (
                    username, post_id, url, content,
                    views_count, likes_count, comments_count, reposts_count, shares_count,
                    calculated_score, post_published_at, tags, images, videos,
                    source, crawler_type, crawl_id, created_at
                ) VALUES (
                    $1, $2, $3, $4,
                    $5, $6, $7, $8, $9,
                    $10, $11, $12, $13, $14,
                    'playwright_agent', 'playwright', NULL, NOW()
                )
                ON CONFLICT (username, post_id, crawler_type)
                DO UPDATE SET
                    url = EXCLUDED.url,
                    content = EXCLUDED.content,
                    views_count = EXCLUDED.views_count,
                    likes_count = EXCLUDED.likes_count,
                    comments_count = EXCLUDED.comments_count,
                    reposts_count = EXCLUDED.reposts_count,
                    shares_count = EXCLUDED.shares_count,
                    calculated_score = EXCLUDED.calculated_score,
                    post_published_at = EXCLUDED.post_published_at,
                    tags = EXCLUDED.tags,
                    images = EXCLUDED.images,
                    videos = EXCLUDED.videos,
                    crawl_id = EXCLUDED.crawl_id,
                    created_at = EXCLUDED.created_at,
                    fetched_at = CURRENT_TIMESTAMP
                """,
                username, post_id, url, content,
                views_count, likes_count, comments_count, reposts_count, shares_count,
                calculated_score, post_published_at, tags_json, images_json, videos_json,
            )
        finally:
            await db.close_pool()

    def _parse_username_code(self, post_url: str) -> Tuple[Optional[str], Optional[str]]:
        try:
            m = re.search(r"/@([^/]+)/post/([^/?#]+)", post_url)
            if not m:
                return None, None
            return m.group(1), m.group(2)
        except Exception:
            return None, None


