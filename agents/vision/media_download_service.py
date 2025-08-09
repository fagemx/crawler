from typing import List, Dict, Any, Optional, Tuple
import asyncio

from common.db_client import get_db_client
from services.rustfs_client import get_rustfs_client


class MediaDownloadService:
    """提供媒體下載所需的統計、清單與執行能力（基於 Playwright 資料）。"""

    async def get_account_media_stats(self, limit: int = 50) -> List[Dict[str, Any]]:
        """彙總各帳號圖片/影片總數、已配對、已完成、待下載數。"""
        db = await get_db_client()
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

    async def build_download_plan(
        self,
        username: str,
        media_types: List[str],
        sort_by: str = "none",
        top_k: Optional[int] = None,
        skip_completed: bool = True,
        only_unpaired: bool = False,
    ) -> Dict[str, List[str]]:
        """建立下載計畫：回傳 {post_url: [media_url,...]} 的映射。"""
        db = await get_db_client()

        type_filters = []
        if "image" in media_types:
            type_filters.append("'image'")
        if "video" in media_types:
            type_filters.append("'video'")
        if not type_filters:
            return {}
        type_sql = ",".join(type_filters)

        # 先鎖定貼文集合（排序 Top-N）
        post_filter_cte = ""
        if sort_by and sort_by != "none" and top_k and isinstance(top_k, int):
            sort_col = {
                "views": "views_count",
                "likes": "likes_count",
                "comments": "comments_count",
                "reposts": "reposts_count",
            }.get(sort_by, None)
            if sort_col:
                post_filter_cte = f"""
                , top_posts AS (
                    SELECT url
                    FROM playwright_post_metrics
                    WHERE username = $1
                    ORDER BY {sort_col} DESC NULLS LAST
                    LIMIT {top_k}
                )
                """
        
        # 展開媒體 URL
        where_posts = "WHERE username = $1" if not post_filter_cte else "WHERE url IN (SELECT url FROM top_posts)"
        pv_cte = f"""
        WITH base AS (
            SELECT url, username, images, videos FROM playwright_post_metrics {where_posts}
        )
        {post_filter_cte}
        , pv AS (
            SELECT username, url AS post_url,
                   jsonb_array_elements_text(COALESCE(images::jsonb,'[]'::jsonb)) AS media_url,
                   'image' AS media_type
            FROM base
            UNION ALL
            SELECT username, url AS post_url,
                   jsonb_array_elements_text(COALESCE(videos::jsonb,'[]'::jsonb)) AS media_url,
                   'video' AS media_type
            FROM base
        )
        SELECT post_url, media_url, media_type
        FROM pv
        WHERE media_type IN ({type_sql})
        """

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

        return {
            "total": total_media,
            "success": success,
            "failed": failed,
            "details": details,
        }


