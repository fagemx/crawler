from typing import List, Dict, Any, Optional
import asyncio
import json
import time

from common.db_client import get_db_client
from services.rustfs_client import get_rustfs_client
from agents.vision.gemini_vision import GeminiVisionAnalyzer
from common.image_primary_filter import compute_rule_score, decide_is_primary


class MediaDescribeService:
    """提供媒體描述的清單生成與執行（寫回 media_descriptions）。"""

    def __init__(self):
        self.analyzer = GeminiVisionAnalyzer()
        
    async def _analyze_media_with_retry(self, media_bytes: bytes, mime_type: str, extra_text: str = None, max_retries: int = 3) -> Dict[str, Any]:
        """
        帶重試機制的 Gemini API 調用
        
        Args:
            media_bytes: 媒體二進制資料
            mime_type: MIME 類型
            extra_text: 額外文字上下文
            max_retries: 最大重試次數
            
        Returns:
            分析結果字典
        """
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                result = await self.analyzer.analyze_media(media_bytes, mime_type, extra_text)
                return result
                
            except Exception as e:
                error_str = str(e)
                error_lower = error_str.lower()
                last_error = e
                
                # 檢查是否是可重試的錯誤
                retryable_errors = [
                    "500 an internal error has occurred",
                    "internal error has occurred",
                    "503 service unavailable", 
                    "502 bad gateway",
                    "429 too many requests",
                    "timeout",
                    "timed out",
                    "connection",
                    "network",
                    "resource has been exhausted"
                ]
                
                is_retryable = any(phrase in error_lower for phrase in retryable_errors)
                
                if not is_retryable or attempt == max_retries:
                    # 不可重試的錯誤或已達最大重試次數
                    raise e
                
                # 可重試錯誤，等待後重試
                wait_time = (2 ** attempt) + (attempt * 0.5)  # 指數退避 + 抖動
                print(f"⚠️ Gemini API 錯誤 (第 {attempt + 1}/{max_retries + 1} 次)：{error_str}")
                print(f"🔄 等待 {wait_time:.1f} 秒後重試...")
                await asyncio.sleep(wait_time)
        
        # 應該不會到這裡，但以防萬一
        raise last_error

    async def get_account_describe_stats(self, limit: int = 50) -> List[Dict[str, Any]]:
        """統計各帳號媒體描述現況（待描述/已描述）。"""
        db = await get_db_client()
        query = f"""
        WITH mf AS (
            SELECT id, post_url, media_type
            FROM media_files
            WHERE download_status = 'completed'
        ),
        pwm AS (
            SELECT url, username FROM playwright_post_metrics
        ),
        joined AS (
            SELECT p.username, m.id AS media_id, m.media_type
            FROM mf m
            JOIN pwm p ON p.url = m.post_url
        ),
        joined_d AS (
            SELECT j.username, j.media_id, j.media_type,
                   CASE WHEN d.media_id IS NULL THEN 0 ELSE 1 END AS is_desc
            FROM joined j
            LEFT JOIN media_descriptions d ON d.media_id = j.media_id
        )
        SELECT username,
               COUNT(*) FILTER (WHERE media_type='image' AND is_desc=0) AS pending_images,
               COUNT(*) FILTER (WHERE media_type='video' AND is_desc=0) AS pending_videos,
               COUNT(*) FILTER (WHERE media_type='image' AND is_desc=1) AS completed_images,
               COUNT(*) FILTER (WHERE media_type='video' AND is_desc=1) AS completed_videos,
               COUNT(*) FILTER (WHERE is_desc=0) AS pending_total,
               COUNT(*) FILTER (WHERE is_desc=1) AS completed_total
        FROM joined_d
        GROUP BY username
        ORDER BY pending_total DESC, completed_total DESC
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
        if top_k and isinstance(top_k, int) and top_k > 0:
            sort_expr_map = {
                "views": "COALESCE(views_count, 0)",
                "likes": "COALESCE(likes_count, 0)",
                "comments": "COALESCE(comments_count, 0)",
                "reposts": "COALESCE(reposts_count, 0)",
            }
            sort_expr = sort_expr_map.get(sort_by) if sort_by and sort_by != "none" else None
            order_clause = f"ORDER BY {sort_expr} DESC NULLS LAST" if sort_expr else "ORDER BY COALESCE(created_at, fetched_at, NOW()) DESC"
            post_filter_cte = f"""
                , top_posts AS (
                    SELECT url
                    FROM playwright_post_metrics
                    WHERE replace(lower(username),'@','') = replace(lower($1),'@','')
                    {order_clause}
                    LIMIT {top_k}
                )
                """

        base_posts = "WHERE replace(lower(username),'@','') = replace(lower($1),'@','')" if not post_filter_cte else "WHERE url IN (SELECT url FROM top_posts)"
        query = f"""
        WITH
        {post_filter_cte}
        base AS (
            SELECT url, username FROM playwright_post_metrics {base_posts}
        )
        , completed AS (
            SELECT mf.*
            FROM media_files mf
            WHERE mf.download_status = 'completed' AND mf.rustfs_url IS NOT NULL AND mf.rustfs_url != ''
        )
        , described AS (
            SELECT d.media_id FROM media_descriptions d
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
            # 直接過濾掉已存在描述的 media_id（用 IN 子查詢避免佔位）
            ids = [r["media_id"] for r in rows]
            if ids:
                described_set = set([r['media_id'] for r in await db.fetch_all(f"SELECT media_id FROM media_descriptions WHERE media_id = ANY($1)", ids)])
                rows = [r for r in rows if r['media_id'] not in described_set]

        # 規則篩選（第一段）：若 only_primary（僅對圖片生效，影片不過濾）
        if only_primary and rows:
            # 對缺少標記的項目進行規則打分，並即時寫回 metadata（僅 image）
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

            # 最終按照標記/分數過濾：影片直接保留；圖片才依門檻
            filtered = []
            for r in rows:
                if r.get("media_type") != 'image':
                    filtered.append(r)
                    continue
                score = r.get("primary_score")
                is_primary = r.get("is_primary")
                if is_primary is True:
                    filtered.append(r)
                elif is_primary is False:
                    continue
                elif score is not None and score >= primary_threshold:
                    filtered.append(r)
            rows = filtered

        # 最終總量上限：確保 Top-N 不會超過使用者設定的數量（以媒體數量為單位）
        if top_k and isinstance(top_k, int) and top_k > 0 and rows:
            rows = rows[:top_k]

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
                    # 0. 實時重複檢查（防止並發競爭導致重複描述）
                    if not overwrite:
                        existing = await conn.fetchrow("SELECT id FROM media_descriptions WHERE media_id = $1", media_id)
                        if existing:
                            details.append({"media_id": media_id, "status": "skipped", "reason": "already_described"})
                            continue

                    # 1. 若為圖片且標記為非主貼圖，則跳過
                    if item.get("media_type") == 'image':
                        is_primary = item.get("is_primary")
                        if is_primary is False:
                            details.append({"media_id": media_id, "status": "skipped", "reason": "not_primary"})
                            continue

                    # 1. 下載媒體（僅 RustFS，不再回退原始 URL）
                    import httpx
                    media_bytes = None
                    mime = ""

                    rustfs_url = item.get("rustfs_url")
                    if rustfs_url:
                        try:
                            # 僅允許從 RustFS bucket 讀取，避免誤用原始 Instagram/FBCDN 連結
                            prefix = f"{client.base_url}/{client.bucket_name}/"
                            if not rustfs_url.startswith(prefix):
                                details.append({"media_id": media_id, "status": "skipped", "error": "invalid_rustfs_url_not_in_bucket"})
                                continue
                            key = rustfs_url[len(prefix):]
                            presigned = client.get_public_or_presigned_url(key, prefer_presigned=True)
                            async with httpx.AsyncClient(timeout=60.0) as http:
                                resp = await http.get(presigned, follow_redirects=True)
                                resp.raise_for_status()
                                media_bytes = resp.content
                                mime = resp.headers.get("content-type", "") or mime
                        except Exception as e:
                            # 無法從 RustFS 讀取 → 跳過
                            details.append({"media_id": media_id, "status": "skipped", "error": f"rustfs_unavailable: {str(e)}"})
                            continue
                    else:
                        # 沒有 rustfs_url（理論上不會出現，因為上面已過濾），保險起見也跳過
                        details.append({"media_id": media_id, "status": "skipped", "error": "no_rustfs_url"})
                        continue

                    # 2. 準備提示（圖片附主貼文內文）
                    extra_text = ""
                    if attach_post_text and media_type == 'image':
                        if post_url not in post_text_cache:
                            row = await conn.fetchrow("SELECT content FROM playwright_post_metrics WHERE url = $1", post_url)
                            post_text_cache[post_url] = (row["content"] if row and row["content"] else "")
                        if post_text_cache[post_url]:
                            extra_text = f"貼文內文：\n{post_text_cache[post_url]}"

                    # 3. 呼叫 Gemini (帶重試機制)
                    if media_type == 'image':
                        # 將貼文原文作為 extra_text 提供給模型，改善情境判讀
                        result = await self._analyze_media_with_retry(media_bytes, mime or 'image/jpeg', extra_text=extra_text)
                        prompt_text = self.analyzer.image_prompt + ("\n\n" + (f"貼文原文：\n{extra_text}" if extra_text else ""))
                    else:
                        result = await self._analyze_media_with_retry(media_bytes, mime or 'video/mp4')
                        prompt_text = self.analyzer.video_prompt

                    # 4. 規整輸出為 JSON（允許模型回傳文字時包裝）
                    if not isinstance(result, (dict, list)):
                        try:
                            result = json.loads(str(result))
                        except Exception:
                            result = {"raw": str(result)}

                    # 5. 原子性覆蓋或新增（使用 transaction + advisory lock 防止並發重複）
                    async with conn.transaction():
                        # 每個 media_id 拿一把交易級別鎖，序列化同一資源的並發寫入
                        # 明確轉換為 bigint 避免類型推斷衝突
                        await conn.execute("SELECT pg_advisory_xact_lock($1::bigint)", int(media_id))

                        if overwrite:
                            # 覆蓋模式：先刪除，再插入
                            await conn.execute(
                                """
                                DELETE FROM media_descriptions WHERE media_id = $1
                                """,
                                int(media_id)
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
                                int(media_id), media_type, "gemini-2.5-pro", prompt_text, json.dumps(result, ensure_ascii=False)
                            )
                        else:
                            # 非覆蓋：僅在不存在時插入
                            await conn.execute(
                                """
                                INSERT INTO media_descriptions
                                (media_id, post_url, username, media_type, model, prompt, response_json, language, status, created_at)
                                SELECT $1, mf.post_url, pwm.username, $2, $3, $4, $5, 'zh-TW', 'completed', NOW()
                                FROM media_files mf
                                JOIN playwright_post_metrics pwm ON pwm.url = mf.post_url
                                WHERE mf.id = $1
                                  AND NOT EXISTS (SELECT 1 FROM media_descriptions d WHERE d.media_id = $1)
                                """,
                                int(media_id), media_type, "gemini-2.5-pro", prompt_text, json.dumps(result, ensure_ascii=False)
                            )

                    success += 1
                    details.append({"media_id": media_id, "status": "completed"})
                except Exception as e:
                    failed += 1
                    details.append({"media_id": media_id, "status": "failed", "error": str(e)})

        return {"total": len(items), "success": success, "failed": failed, "details": details}


    async def get_undesc_summary_by_user(self, username: str, media_types: List[str], limit: int = 20) -> List[Dict[str, Any]]:
        """查詢某帳號尚未描述的貼文摘要（每貼文未描述媒體數）。"""
        db = await get_db_client()
        query = """
        SELECT mf.post_url,
               COUNT(*) FILTER (WHERE mf.media_type='image') AS pending_images,
               COUNT(*) FILTER (WHERE mf.media_type='video') AS pending_videos,
               COUNT(*) AS pending_total
        FROM media_files mf
        JOIN playwright_post_metrics pwm ON pwm.url = mf.post_url
        WHERE replace(lower(pwm.username),'@','') = replace(lower($1),'@','')
          AND mf.download_status = 'completed'
          AND mf.media_type = ANY($2)
          AND NOT EXISTS (
            SELECT 1 FROM media_descriptions d WHERE d.media_id = mf.id
          )
        GROUP BY mf.post_url
        ORDER BY pending_total DESC
        LIMIT $3
        """
        return await db.fetch_all(query, username, media_types, limit)

    async def get_descriptions_by_post(self, post_url: str) -> List[Dict[str, Any]]:
        """取得單篇貼文的描述結果列表。"""
        db = await get_db_client()
        query = """
        SELECT d.media_id, d.post_url, d.media_type, d.model, d.prompt, d.response_json, d.status, d.created_at,
               mf.original_url, mf.rustfs_url
        FROM media_descriptions d
        JOIN media_files mf ON mf.id = d.media_id
        WHERE d.post_url = $1
        ORDER BY d.created_at DESC
        """
        return await db.fetch_all(query, post_url)

    async def get_recent_descriptions_by_user(self, username: str, media_types: List[str], limit: int = 50) -> List[Dict[str, Any]]:
        """取得某帳號最近的描述結果（瀏覽成果用）。"""
        db = await get_db_client()
        query = """
        SELECT d.media_id, d.post_url, d.media_type, d.model, d.response_json, d.status, d.created_at,
               mf.original_url, mf.rustfs_url
        FROM media_descriptions d
        JOIN media_files mf ON mf.id = d.media_id
        JOIN playwright_post_metrics pwm ON pwm.url = d.post_url
        WHERE replace(lower(pwm.username),'@','') = replace(lower($1),'@','')
          AND d.media_type = ANY($2)
        ORDER BY d.created_at DESC
        LIMIT $3
        """
        return await db.fetch_all(query, username, media_types, limit)

    async def get_pending_media_by_user(self, username: str, media_types: List[str], limit: int = 50) -> List[Dict[str, Any]]:
        """取得某帳號尚未描述的媒體（瀏覽內容用）。"""
        db = await get_db_client()
        query = """
        SELECT mf.id AS media_id, mf.post_url, mf.media_type, mf.original_url, mf.rustfs_url,
               mf.width, mf.height, mf.file_size
        FROM media_files mf
        JOIN playwright_post_metrics pwm ON pwm.url = mf.post_url
        WHERE replace(lower(pwm.username),'@','') = replace(lower($1),'@','')
          AND mf.download_status = 'completed'
          AND mf.media_type = ANY($2)
          AND NOT EXISTS (SELECT 1 FROM media_descriptions d WHERE d.media_id = mf.id)
        ORDER BY mf.id DESC
        LIMIT $3
        """
        return await db.fetch_all(query, username, media_types, limit)

    async def describe_single_post(self,
        post_url: str,
        media_types: List[str],
        only_primary: bool = True,
        primary_threshold: float = 0.7,
        overwrite: bool = True,
    ) -> Dict[str, Any]:
        """針對單篇貼文建立清單並執行描述。"""
        db = await get_db_client()

        def _normalize_threads_url(u: str) -> str:
            try:
                u = u.strip()
                # 域名 threads.com → threads.net
                u = u.replace("threads.com", "threads.net")
                # 去掉尾端多餘斜線
                if u.endswith('/'):
                    u = u[:-1]
            except Exception:
                pass
            return u

        norm_url = _normalize_threads_url(post_url)

        async def _fetch_by_exact(url: str):
            # 單篇立即描述：放寬為不強制已完成下載，允許直接用 original_url 描述
            return await db.fetch_all(
                """
                SELECT id AS media_id, post_url, original_url, media_type, rustfs_url,
                       width, height, file_size,
                       COALESCE((metadata->>'primary_score')::float, NULL) AS primary_score,
                       COALESCE((metadata->>'is_primary')::bool, NULL) AS is_primary
                FROM media_files
                WHERE post_url = $1 AND media_type = ANY($2)
                """,
                url, media_types
            )

        rows = await _fetch_by_exact(norm_url)

        # 若找不到，嘗試以 shortcode 模糊查找
        if not rows:
            try:
                from urllib.parse import urlparse
                p = urlparse(norm_url)
                parts = [seg for seg in p.path.split('/') if seg]
                shortcode = parts[-1] if parts else None
            except Exception:
                shortcode = None

            if shortcode:
                rows = await db.fetch_all(
                    """
                    SELECT id AS media_id, post_url, original_url, media_type, rustfs_url,
                           width, height, file_size,
                           COALESCE((metadata->>'primary_score')::float, NULL) AS primary_score,
                           COALESCE((metadata->>'is_primary')::bool, NULL) AS is_primary
                    FROM media_files
                    WHERE media_type = ANY($1)
                      AND (post_url ILIKE '%'||$2||'%' OR original_url ILIKE '%'||$2||'%')
                    ORDER BY id DESC
                    LIMIT 50
                    """,
                    media_types, shortcode
                )

        # 過濾未描述的：僅在非覆蓋模式時才排除已描述
        if rows and not overwrite:
            ids = [r["media_id"] for r in rows]
            placeholders = ",".join([str(int(i)) for i in ids])
            desc_rows = await db.fetch_all(
                f"SELECT media_id FROM media_descriptions WHERE media_id IN ({placeholders})"
            )
            described = {d["media_id"] for d in desc_rows}
            rows = [r for r in rows if r["media_id"] not in described]

        # 主貼圖篩選（僅影響圖片，影片不受限）
        if only_primary and rows:
            filtered = []
            for r in rows:
                if r.get("media_type") != 'image':
                    filtered.append(r)
                    continue
                score = r.get("primary_score")
                is_primary = r.get("is_primary")
                if is_primary is True or (score is not None and score >= primary_threshold):
                    filtered.append(r)
            rows = filtered

        # 單篇模式：強制以並發數 1 的語義執行（上層 UI 已固定，這裡維持逐項順序處理）
        return await self.run_describe(rows, overwrite=overwrite)

