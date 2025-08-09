from typing import List, Dict, Any, Optional
import asyncio
import json

from common.db_client import get_db_client
from services.rustfs_client import get_rustfs_client
from agents.vision.gemini_vision import GeminiVisionAnalyzer
from common.image_primary_filter import compute_rule_score, decide_is_primary


class MediaDescribeService:
    """提供媒體描述的清單生成與執行（寫回 media_descriptions）。"""

    def __init__(self):
        self.analyzer = GeminiVisionAnalyzer()

    async def get_account_describe_stats(self, limit: int = 50) -> List[Dict[str, Any]]:
        """統計各帳號『已下載完成但未描述』的媒體數。"""
        db = await get_db_client()
        query = f"""
        WITH completed AS (
            SELECT mf.id, mf.post_url, mf.media_type
            FROM media_files mf
            WHERE mf.download_status = 'completed'
        ),
        pw AS (
            SELECT username, url FROM playwright_post_metrics
        ),
        joined AS (
            SELECT pw.username, c.id AS media_id, c.media_type
            FROM completed c
            JOIN pw ON pw.url = c.post_url
        )
        SELECT username,
               COUNT(*) FILTER (WHERE media_type='image') AS pending_images,
               COUNT(*) FILTER (WHERE media_type='video') AS pending_videos
        FROM joined j
        WHERE NOT EXISTS (
            SELECT 1 FROM media_descriptions d WHERE d.media_id = j.media_id
        )
        GROUP BY username
        ORDER BY (COUNT(*)) DESC
        LIMIT {limit}
        """
        return await db.fetch_all(query)

    async def build_describe_plan(
        self,
        username: str,
        media_types: List[str],
        sort_by: str = "none",
        top_k: Optional[int] = None,
        only_undesc: bool = True,
        only_primary: bool = True,
        primary_threshold: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """建立描述清單，回傳含 media_id/post_url/original_url/media_type 的列表。"""
        db = await get_db_client()

        # 先取貼文集合（排序 Top-N）
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

        base_posts = "WHERE username = $1" if not post_filter_cte else "WHERE url IN (SELECT url FROM top_posts)"
        query = f"""
        WITH base AS (
            SELECT url, username FROM playwright_post_metrics {base_posts}
        )
        {post_filter_cte}
        , completed AS (
            SELECT mf.*
            FROM media_files mf
            WHERE mf.download_status = 'completed'
        )
        SELECT mf.id AS media_id, mf.post_url, mf.original_url, mf.media_type, mf.rustfs_url,
               mf.width, mf.height, mf.file_size,
               COALESCE((mf.metadata->>'primary_score')::float, NULL) AS primary_score,
               COALESCE((mf.metadata->>'is_primary')::bool, NULL) AS is_primary
        FROM completed mf
        JOIN base b ON b.url = mf.post_url
        WHERE mf.media_type = ANY($2)
        """

        mt_array = media_types
        rows = await db.fetch_all(query, username, mt_array)

        if only_undesc and rows:
            ids = [r["media_id"] for r in rows]
            # 使用陣列參數避免動態拼接與參數編號問題
            desc_rows = await db.fetch_all(
                "SELECT media_id FROM media_descriptions WHERE media_id = ANY($1::int[])",
                ids
            )
            described = {d["media_id"] for d in desc_rows}
            rows = [r for r in rows if r["media_id"] not in described]

        # 規則篩選（第一段）：若 only_primary
        if only_primary and rows:
            # 對缺少標記的項目進行規則打分，並即時寫回 metadata
            to_update = []
            for r in rows:
                if r.get("is_primary") is None and r.get("media_type") == 'image':
                    score, reason = compute_rule_score(r)
                    r["primary_score"] = score
                    r["primary_reason"] = reason
                    r["is_primary"] = decide_is_primary(score, primary_threshold)
                    to_update.append((r["media_id"], score, r["is_primary"], reason))

            if to_update:
                async with (await get_db_client()).get_connection() as conn:
                    for media_id, score, is_primary, reason in to_update:
                        # 合併寫入 metadata 欄位
                        await conn.execute(
                            """
                            UPDATE media_files
                            SET metadata = COALESCE(metadata, '{}'::jsonb) ||
                                           jsonb_build_object('primary_score', $2::text, 'is_primary', $3::text, 'primary_reason', $4::text)
                            WHERE id = $1
                            """,
                            media_id, str(score), 'true' if is_primary else 'false', reason
                        )

            # 最終按照標記/分數過濾
            filtered = []
            for r in rows:
                score = r.get("primary_score")
                is_primary = r.get("is_primary")
                if is_primary is True:
                    filtered.append(r)
                elif is_primary is False:
                    continue
                elif score is not None and score >= primary_threshold:
                    filtered.append(r)
            rows = filtered

        return rows

    async def run_describe(self, items: List[Dict[str, Any]], overwrite: bool = True, attach_post_text: bool = True) -> Dict[str, Any]:
        """執行媒體描述，寫入 media_descriptions。"""
        db = await get_db_client()
        client = await get_rustfs_client()  # 若需要從 RustFS 讀回檔案可擴充

        success, failed = 0, 0
        details: List[Dict[str, Any]] = []

        # 預讀 post 內容（圖片描述要附主貼文內文）
        post_text_cache: Dict[str, str] = {}

        async with db.get_connection() as conn:
            for item in items:
                media_id = item["media_id"]
                post_url = item["post_url"]
                original_url = item["original_url"]
                media_type = item["media_type"]
                try:
                    # 0. 若為圖片且標記為非主貼圖，則跳過
                    if item.get("media_type") == 'image':
                        is_primary = item.get("is_primary")
                        if is_primary is False:
                            details.append({"media_id": media_id, "status": "skipped", "reason": "not_primary"})
                            continue

                    # 1. 下載媒體（優先 RustFS，失敗回原始 URL）
                    import httpx
                    media_bytes = None
                    mime = ""

                    rustfs_url = item.get("rustfs_url")
                    if rustfs_url:
                        try:
                            async with httpx.AsyncClient(timeout=60.0) as http:
                                resp = await http.get(rustfs_url, follow_redirects=True, auth=(client.access_key, client.secret_key))
                                resp.raise_for_status()
                                media_bytes = resp.content
                                mime = resp.headers.get("content-type", "") or mime
                        except Exception:
                            media_bytes = None

                    if media_bytes is None:
                        async with httpx.AsyncClient(timeout=60.0) as http:
                            resp = await http.get(original_url, follow_redirects=True)
                            resp.raise_for_status()
                            media_bytes = resp.content
                            mime = resp.headers.get("content-type", "") or mime

                    # 2. 準備提示（圖片附主貼文內文）
                    extra_text = ""
                    if attach_post_text and media_type == 'image':
                        if post_url not in post_text_cache:
                            row = await conn.fetchrow("SELECT content FROM playwright_post_metrics WHERE url = $1", post_url)
                            post_text_cache[post_url] = (row["content"] if row and row["content"] else "")
                        if post_text_cache[post_url]:
                            extra_text = f"貼文內文：\n{post_text_cache[post_url]}"

                    # 3. 呼叫 Gemini
                    if media_type == 'image':
                        # 將貼文原文作為 extra_text 提供給模型，改善情境判讀
                        result = await self.analyzer.analyze_media(media_bytes, mime or 'image/jpeg', extra_text=extra_text)
                        prompt_text = self.analyzer.image_prompt + ("\n\n" + (f"貼文原文：\n{extra_text}" if extra_text else ""))
                    else:
                        result = await self.analyzer.analyze_media(media_bytes, mime or 'video/mp4')
                        prompt_text = self.analyzer.video_prompt

                    # 4. 規整輸出為 JSON（允許模型回傳文字時包裝）
                    if not isinstance(result, (dict, list)):
                        try:
                            result = json.loads(str(result))
                        except Exception:
                            result = {"raw": str(result)}

                    # 5. 覆蓋或新增
                    if overwrite:
                        await conn.execute(
                            """
                            DELETE FROM media_descriptions WHERE media_id = $1
                            """,
                            media_id
                        )

                    await conn.execute(
                        """
                        INSERT INTO media_descriptions
                        (media_id, post_url, username, media_type, model, prompt, response_json, language, status, created_at)
                        SELECT $1, mf.post_url, pwm.username, $2, $3, $4, $5, 'zh-TW', 'completed', NOW()
                        FROM media_files mf
                        JOIN playwright_post_metrics pwm ON pwm.url = mf.post_url
                        WHERE mf.id = $1
                        """,
                        media_id, media_type, "gemini-2.5-pro", prompt_text, json.dumps(result, ensure_ascii=False)
                    )

                    success += 1
                    details.append({"media_id": media_id, "status": "completed"})
                except Exception as e:
                    failed += 1
                    details.append({"media_id": media_id, "status": "failed", "error": str(e)})

        return {"total": len(items), "success": success, "failed": failed, "details": details}


