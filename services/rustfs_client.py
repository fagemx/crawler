"""
RustFS 客戶端服務

用於處理媒體檔案的上傳、下載和管理
"""

import os
import socket
from urllib.parse import urlparse, urlunparse
import hashlib
import mimetypes
from typing import Optional, Dict, Any, List
import uuid
from datetime import datetime
from pathlib import Path
import httpx
import asyncio
import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError
import json

from common.settings import get_settings
from common.db_client import get_db_client
from common.config import get_auth_file_path


class RustFSClient:
    """RustFS 客戶端"""
    
    def __init__(self):
        self.settings = get_settings()
        # 從環境讀取設定（支援本機與容器內網）
        self.base_url = os.getenv("RUSTFS_ENDPOINT", "http://rustfs:9000").rstrip("/")
        self.access_key = os.getenv("RUSTFS_ACCESS_KEY", "rustfsadmin")
        self.secret_key = os.getenv("RUSTFS_SECRET_KEY", "rustfsadmin")
        self.bucket_name = os.getenv("RUSTFS_BUCKET", "social-media-content")
        self.region = os.getenv("RUSTFS_REGION", "us-east-1")
        # 自動偵測：若本機無法解析 rustfs，改用 localhost
        self._auto_select_endpoint()
        self._s3_client = None
        self._cookie_header: Optional[str] = None

    def _auto_select_endpoint(self):
        try:
            parsed = urlparse(self.base_url)
            host = parsed.hostname or ""
            if host.lower() == "rustfs":
                try:
                    socket.gethostbyname(host)
                except OSError:
                    # 無法解析容器域名，回退本機端口
                    new_netloc = f"localhost:{parsed.port or 9000}"
                    self.base_url = urlunparse((parsed.scheme, new_netloc, "", "", "", ""))
        except Exception:
            # 靜默失敗，維持原端點
            pass
        
    def _create_s3_client(self):
        """建立統一設定的 S3 客戶端（path-style 位址，方便本機/MinIO）。"""
        return boto3.client(
            's3', endpoint_url=self.base_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            config=BotoConfig(signature_version='s3v4', s3={'addressing_style': 'path'}),
            region_name=self.region
        )

    async def initialize(self):
        """初始化：使用 S3 檢查/建立 bucket"""
        try:
            s3 = self._create_s3_client()
            def _head():
                try:
                    s3.head_bucket(Bucket=self.bucket_name)
                    return True
                except ClientError as e:
                    code = e.response.get('Error', {}).get('Code')
                    if code in ('404', 'NoSuchBucket'):
                        return False
                    if code in ('403', 'AccessDenied'):
                        return True
                    raise
            exists = await asyncio.to_thread(_head)
            if not exists:
                def _create():
                    try:
                        s3.create_bucket(Bucket=self.bucket_name)
                        return True
                    except ClientError as e:
                        if e.response.get('Error', {}).get('Code') in ('BucketAlreadyOwnedByYou', 'BucketAlreadyExists'):
                            return True
                        raise
                await asyncio.to_thread(_create)
        except Exception as e:
            print(f"❌ Failed to initialize RustFS: {e}")
            raise

    def health_check(self) -> Dict[str, Any]:
        """RustFS 健檢（S3 HeadBucket）"""
        try:
            s3 = self._create_s3_client()
            try:
                s3.head_bucket(Bucket=self.bucket_name)
                return {"status": "healthy", "endpoint": self.base_url, "bucket": self.bucket_name}
            except ClientError as e:
                code = e.response.get('Error', {}).get('Code')
                if code in ('404', 'NoSuchBucket', '403', 'AccessDenied'):
                    return {"status": "healthy", "endpoint": self.base_url, "bucket": self.bucket_name, "note": code}
                return {"status": "unhealthy", "endpoint": self.base_url, "bucket": self.bucket_name, "error": code}
        except Exception as e:
            return {"status": "unhealthy", "endpoint": self.base_url, "bucket": self.bucket_name, "error": str(e)}
    
    def _generate_key(self, post_url: str, original_url: str, media_type: str) -> str:
        """生成 RustFS 存儲鍵值"""
        # 使用 post_url 和 original_url 的 hash 生成唯一鍵值
        url_hash = hashlib.md5(f"{post_url}:{original_url}".encode()).hexdigest()
        
        # 從原始 URL 獲取檔案擴展名
        parsed_url = urlparse(original_url)
        path = Path(parsed_url.path)
        extension = path.suffix.lower()
        
        if not extension:
            # 根據媒體類型推測擴展名
            if media_type == 'image':
                extension = '.jpg'
            elif media_type == 'video':
                extension = '.mp4'
            elif media_type == 'audio':
                extension = '.mp3'
            else:
                extension = '.bin'
        
        return f"{media_type}/{url_hash[:2]}/{url_hash[2:4]}/{url_hash}{extension}"
    
    async def download_and_store_media(
        self, 
        post_url: str, 
        media_urls: List[str],
        max_concurrent: int = 3
    ) -> List[Dict[str, Any]]:
        """
        批次下載並存儲媒體檔案到 RustFS
        
        Args:
            post_url: 貼文 URL
            media_urls: 媒體 URL 列表
            max_concurrent: 最大並發下載數
            
        Returns:
            List[Dict]: 下載結果列表
        """
        if not media_urls:
            return []
        
        # 限制並發數量
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def download_single_media(media_url: str) -> Dict[str, Any]:
            async with semaphore:
                return await self._download_single_media(post_url, media_url)
        
        # 並發下載所有媒體檔案
        # 保證所有子任務在同一事件迴圈中建立與等待，避免跨迴圈 Future
        loop = asyncio.get_running_loop()
        tasks = [loop.create_task(download_single_media(url)) for url in media_urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 處理結果，過濾異常
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"❌ Failed to download {media_urls[i]}: {result}")
                processed_results.append({
                    "original_url": media_urls[i],
                    "status": "failed",
                    "error": str(result)
                })
            else:
                processed_results.append(result)
        
        return processed_results
    
    async def _download_single_media(self, post_url: str, media_url: str) -> Dict[str, Any]:
        """下載單個媒體檔案"""
        try:
            # 檢測媒體類型
            media_type = self._detect_media_type(media_url)
            rustfs_key = self._generate_key(post_url, media_url, media_type)
            
            # 記錄到資料庫（pending 狀態）
            # 每次在當前事件迴圈中獲取/建立連線池，避免跨迴圈使用
            db_client = await get_db_client()
            # 直接以安全方式確保 posts(url) 存在，避免 upsert_post 函數造成 created_at NOT NULL 問題
            await self._ensure_post_url(db_client, post_url)
            media_id = await self._record_media_file(
                db_client, post_url, media_url, media_type, rustfs_key, "pending"
            )
            # 若歷史環境缺 created_at 預設，避免 NULL 導致後續違反 not-null
            try:
                async with db_client.get_connection() as conn:
                    await conn.execute("UPDATE media_files SET created_at = NOW() WHERE id = $1 AND created_at IS NULL", media_id)
            except Exception:
                pass
            
            # 下載檔案
            # 強化下載層：針對不同媒體類型使用不同的 headers
            if media_type == 'video' and 'instagram' in media_url.lower():
                # Instagram 影片需要特殊處理
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                    "Referer": "https://www.instagram.com/",
                    "Origin": "https://www.instagram.com",
                    "Accept": "video/webm,video/ogg,video/*;q=0.9,application/ogg;q=0.7,audio/*;q=0.6,*/*;q=0.5",
                    "Accept-Language": "en-US,en;q=0.5",
                    "Accept-Encoding": "gzip, deflate, br",
                    "DNT": "1",
                    "Connection": "keep-alive",
                    "Sec-Fetch-Dest": "video",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Site": "same-site",
                }
            else:
                # 圖片和其他媒體
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                    "Referer": "https://www.threads.net/",
                    "Accept": "*/*",
                }
            # 嘗試附帶 Threads cookies（從 auth.json 載入），提升成功率
            cookie_header = self._get_cookie_header()
            if cookie_header:
                headers["Cookie"] = cookie_header
            
            # Instagram 影片特殊處理：嘗試更多認證相關的 headers
            if media_type == 'video' and 'instagram' in media_url.lower():
                # 增加 Instagram 常用的安全 headers
                headers.update({
                    "X-Requested-With": "XMLHttpRequest",
                    "X-IG-App-ID": "936619743392459",
                    "X-Instagram-Ajax": "1",
                    "X-CSRFToken": "missing",  # 如果沒有真實 token 就用佔位符
                })
            async with httpx.AsyncClient(timeout=120.0, headers=headers) as client:
                print(f"📥 Downloading {media_type}: {media_url}")
                
                # 下載原始檔案（影片可能需要更長時間）
                max_retries = 3 if media_type == 'video' else 1
                last_exception = None
                
                for attempt in range(max_retries):
                    try:
                        # Instagram 影片：嘗試 HEAD 請求先確認可用性
                        if media_type == 'video' and 'instagram' in media_url.lower() and attempt == 0:
                            try:
                                head_response = await client.head(media_url, follow_redirects=True)
                                if head_response.status_code != 200:
                                    print(f"⚠️ HEAD check failed with {head_response.status_code}, trying direct download...")
                            except Exception:
                                print(f"⚠️ HEAD check failed, trying direct download...")
                        
                        response = await client.get(media_url, follow_redirects=True)
                        response.raise_for_status()
                        break
                    except httpx.HTTPStatusError as e:
                        if e.response.status_code == 403:
                            print(f"❌ 403 Forbidden (attempt {attempt + 1}): {e.response.headers.get('X-FB-Debug', 'No debug info')}")
                            if attempt < max_retries - 1:
                                print(f"🔄 Retrying with different approach in 3s...")
                                await asyncio.sleep(3)
                                # 嘗試移除一些可能導致問題的 headers
                                if "X-Instagram-Ajax" in headers:
                                    del headers["X-Instagram-Ajax"]
                                if "X-CSRFToken" in headers:
                                    del headers["X-CSRFToken"]
                                last_exception = e
                                continue
                        raise
                    except Exception as e:
                        if attempt < max_retries - 1:
                            print(f"⚠️ Download failed (attempt {attempt + 1}): {e}, retrying...")
                            await asyncio.sleep(2)
                            last_exception = e
                            continue
                        raise
                else:
                    # All retries failed
                    raise last_exception or Exception("Max retries exceeded")
                
                file_content = response.content
                file_size = len(file_content)
                content_type = response.headers.get('content-type', '')
                
                # 獲取檔案擴展名
                file_extension = self._get_file_extension(media_url, content_type)
                
                # 上傳到 RustFS
                try:
                    rustfs_url = await self._upload_to_rustfs(rustfs_key, file_content, content_type)
                except ClientError as s3e:
                    # 若物件已存在（重試/並發重複），改為取已存在的 URL
                    err_code = s3e.response.get('Error', {}).get('Code') if hasattr(s3e, 'response') else None
                    if err_code in ('EntityAlreadyExists', 'BucketAlreadyOwnedByYou'):
                        rustfs_url = f"{self.base_url}/{self.bucket_name}/{rustfs_key}"
                    else:
                        raise
                
                # 獲取媒體檔案的元數據（寬度、高度、時長等）
                metadata = await self._extract_media_metadata(file_content, media_type)
                
                # 更新資料庫記錄
                await self._update_media_file(
                    db_client, media_id, rustfs_url, file_size, 
                    file_extension, metadata, "completed"
                )
                
                print(f"✅ Successfully stored: {media_url} -> {rustfs_key}")
                
                return {
                    "original_url": media_url,
                    "rustfs_key": rustfs_key,
                    "rustfs_url": rustfs_url,
                    "media_type": media_type,
                    "file_size": file_size,
                    "status": "completed",
                    "metadata": metadata
                }
                
        except Exception as e:
            print(f"❌ Failed to download {media_url}: {e}")
            
            # 更新資料庫記錄為失敗狀態
            try:
                if 'media_id' in locals():
                    await self._update_media_file(
                        db_client, media_id, None, None, None, {}, "failed", str(e)
                    )
            except:
                pass
            
            return {
                "original_url": media_url,
                "status": "failed",
                "error": str(e)
            }

    async def _ensure_post_url(self, db_client, post_url: str) -> None:
        """最小化保證 posts(url) 存在，避免 FK 阻擋。"""
        try:
            async with db_client.get_connection() as conn:
                # 查詢 posts 欄位
                col_rows = await conn.fetch(
                    """
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_schema = 'public' AND table_name = 'posts'
                    """
                )
                cols = {r["column_name"] for r in col_rows}

                # 構建 INSERT 欄位/值
                fields = ["url", "author"]
                values = ["$1", "$2"]
                params = [post_url, "playwright"]

                if "markdown" in cols:
                    fields.append("markdown"); values.append("$3"); params.append(None)
                if "media_urls" in cols:
                    # 儲存為空陣列
                    fields.append("media_urls"); values.append("'[]'::jsonb")
                if "created_at" in cols:
                    fields.append("created_at"); values.append("NOW()")
                if "last_seen" in cols:
                    fields.append("last_seen"); values.append("NOW()")

                insert_sql = f"INSERT INTO posts ({', '.join(fields)}) VALUES ({', '.join(values)}) "
                # 衝突時更新 last_seen
                update_parts = []
                if "last_seen" in cols:
                    update_parts.append("last_seen = NOW()")
                if "media_urls" in cols:
                    update_parts.append("media_urls = COALESCE(posts.media_urls, EXCLUDED.media_urls)")
                if "markdown" in cols:
                    update_parts.append("markdown = COALESCE(posts.markdown, EXCLUDED.markdown)")
                if update_parts:
                    insert_sql += "ON CONFLICT (url) DO UPDATE SET " + ", ".join(update_parts)
                else:
                    insert_sql += "ON CONFLICT (url) DO NOTHING"

                await conn.execute(insert_sql, *params)
        except Exception:
            # 靜默失敗，不阻斷主流程
            pass

    def _get_cookie_header(self) -> Optional[str]:
        """
        從 Playwright 的 auth.json 載入 cookies，合併為 Cookie 標頭字串。
        注意：此為最佳努力，實際站點可能需要特定域名/路徑；這裡統一附上常用 cookies。
        """
        if self._cookie_header is not None:
            return self._cookie_header
        try:
            auth_path = get_auth_file_path()
            if not auth_path.exists():
                self._cookie_header = ""
                return self._cookie_header
            with open(auth_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            cookies = data.get("cookies") or data.get("orig_cookies") or []
            parts = []
            for c in cookies:
                name = c.get("name")
                value = c.get("value")
                if not name or value is None:
                    continue
                # 過濾明顯無效/敏感名可自行擴充
                parts.append(f"{name}={value}")
            self._cookie_header = "; ".join(parts) if parts else ""
            return self._cookie_header
        except Exception:
            self._cookie_header = ""
            return self._cookie_header
    
    def _detect_media_type(self, url: str) -> str:
        """檢測媒體類型"""
        url_lower = url.lower()
        
        # 圖片格式
        if any(ext in url_lower for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg']):
            return 'image'
        
        # 影片格式
        if any(ext in url_lower for ext in ['.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.mkv']):
            return 'video'
        
        # 音頻格式
        if any(ext in url_lower for ext in ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a']):
            return 'audio'
        
        # 預設為圖片（社交媒體大多是圖片）
        return 'image'
    
    def _get_file_extension(self, url: str, content_type: str) -> str:
        """獲取檔案擴展名"""
        # 先從 URL 獲取
        parsed_url = urlparse(url)
        path = Path(parsed_url.path)
        extension = path.suffix.lower()
        
        if extension:
            return extension
        
        # 從 content-type 推測
        if content_type:
            extension = mimetypes.guess_extension(content_type)
            if extension:
                return extension
        
        # 預設
        return '.bin'
    
    async def _upload_to_rustfs(self, key: str, content: bytes, content_type: str) -> str:
        """上傳檔案到 RustFS"""
        s3 = self._create_s3_client()
        def _put():
            s3.put_object(Bucket=self.bucket_name, Key=key, Body=content, ContentType=content_type)
            return f"{self.base_url}/{self.bucket_name}/{key}"
        return await asyncio.to_thread(_put)

    async def upload_user_media(self, filename: str, content: bytes, content_type: str) -> Dict[str, str]:
        """
        上傳使用者在撰寫器匯入的媒體到 RustFS，返回 key 與可瀏覽 URL。
        路徑格式：user-media/YYYYMMDD/uuid_filename
        """
        safe_name = ''.join(ch for ch in filename if ch.isalnum() or ch in ('-', '_', '.', ' ')).strip().replace(' ', '_')
        day = datetime.utcnow().strftime('%Y%m%d')
        unique = uuid.uuid4().hex[:12]
        key = f"user-media/{day}/{unique}_{safe_name}"
        rustfs_url = await self._upload_to_rustfs(key, content, content_type or 'application/octet-stream')
        browse_url = self.get_public_or_presigned_url(key, prefer_presigned=True)
        return {"key": key, "rustfs_url": rustfs_url, "url": browse_url, "content_type": content_type or ""}

    def make_object_url(self, key: str) -> str:
        """回傳未簽名的物件 URL（適用於已設公開讀取的 bucket）。"""
        return f"{self.base_url}/{self.bucket_name}/{key}"

    def generate_presigned_url(self, key: str, expires_in: int = 3600) -> Optional[str]:
        """產生 GET 物件的簽名 URL（預設一小時）。"""
        try:
            s3 = self._create_s3_client()
            return s3.generate_presigned_url(
                ClientMethod='get_object',
                Params={'Bucket': self.bucket_name, 'Key': key},
                ExpiresIn=expires_in
            )
        except Exception as e:
            print(f"⚠️ Failed to generate presigned url for {key}: {e}")
            return None

    def get_public_or_presigned_url(self, key: str, prefer_presigned: bool = True, expires_in: int = 3600) -> str:
        """取得可用於瀏覽的 URL。
        - 若 prefer_presigned 為 True，優先回傳簽名 URL；失敗則退回未簽名 URL。
        - 若 bucket 未設公開讀取，未簽名 URL 會 403。
        """
        if prefer_presigned:
            url = self.generate_presigned_url(key, expires_in=expires_in)
            if url:
                return url
        return self.make_object_url(key)
    
    async def _extract_media_metadata(self, content: bytes, media_type: str) -> Dict[str, Any]:
        """提取媒體檔案元數據"""
        metadata = {}
        
        try:
            if media_type == 'image':
                # 使用 PIL 獲取圖片尺寸
                try:
                    from PIL import Image
                    import io
                    
                    image = Image.open(io.BytesIO(content))
                    metadata['width'] = image.width
                    metadata['height'] = image.height
                    metadata['format'] = image.format
                except ImportError:
                    print("⚠️ PIL not available, skipping image metadata extraction")
                except Exception as e:
                    print(f"⚠️ Failed to extract image metadata: {e}")
            
            elif media_type == 'video':
                # 對於影片，可以使用 ffprobe 或其他工具
                # 這裡先跳過，因為需要額外的依賴
                pass
                
        except Exception as e:
            print(f"⚠️ Failed to extract metadata: {e}")
        
        return metadata
    
    async def _record_media_file(
        self, 
        db_client, 
        post_url: str, 
        original_url: str, 
        media_type: str, 
        rustfs_key: str, 
        status: str
    ) -> int:
        """記錄媒體檔案到資料庫"""
        async with db_client.get_connection() as conn:
            media_id = await conn.fetchval(
                """
                INSERT INTO media_files (
                    post_url, original_url, media_type, rustfs_key, download_status
                )
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (rustfs_key) DO UPDATE SET
                    original_url = EXCLUDED.original_url,
                    media_type = EXCLUDED.media_type
                RETURNING media_files.id
                """,
                post_url, original_url, media_type, rustfs_key, status,
            )
            return media_id
    
    async def _update_media_file(
        self, 
        db_client, 
        media_id: int, 
        rustfs_url: Optional[str], 
        file_size: Optional[int],
        file_extension: Optional[str],
        metadata: Dict[str, Any], 
        status: str,
        error: Optional[str] = None
    ):
        """更新媒體檔案記錄"""
        async with db_client.get_connection() as conn:
            await conn.execute("""
                UPDATE media_files 
                SET 
                    rustfs_url = $2,
                    file_size = $3,
                    file_extension = $4,
                    width = $5,
                    height = $6,
                    duration = $7,
                    download_status = $8::text,
                    download_error = $9,
                    downloaded_at = CASE WHEN $8::text = 'completed' THEN now() ELSE downloaded_at END,
                    metadata = $10::jsonb
                WHERE id = $1
            """, 
            media_id, rustfs_url, file_size, file_extension,
            metadata.get('width'), metadata.get('height'), metadata.get('duration'),
            status, error, json.dumps(metadata) if metadata else '{}')
    
    async def get_media_files(self, post_url: str) -> List[Dict[str, Any]]:
        """獲取貼文的媒體檔案"""
        db_client = await get_db_client()
        
        async with db_client.get_connection() as conn:
            rows = await conn.fetch("""
                SELECT 
                    id, original_url, media_type, file_extension, rustfs_key, rustfs_url,
                    file_size, width, height, duration, download_status, download_error,
                    created_at, downloaded_at, metadata
                FROM media_files 
                WHERE post_url = $1
                ORDER BY created_at
            """, post_url)
            
            return [dict(row) for row in rows]
    
    async def cleanup_failed_downloads(self, max_age_hours: int = 24):
        """清理失敗的下載記錄"""
        db_client = await get_db_client()
        
        async with db_client.get_connection() as conn:
            deleted_count = await conn.fetchval("""
                DELETE FROM media_files 
                WHERE download_status = 'failed' 
                AND created_at < now() - interval '%s hours'
                RETURNING COUNT(*)
            """, max_age_hours)
            
            print(f"🧹 Cleaned up {deleted_count} failed download records")
            return deleted_count


# 全域 RustFS 客戶端實例
rustfs_client = RustFSClient()


async def get_rustfs_client() -> RustFSClient:
    """獲取 RustFS 客戶端實例"""
    return rustfs_client


async def download_media_for_post(post_url: str, media_urls: List[str]) -> List[Dict[str, Any]]:
    """為貼文下載媒體檔案的便利函數"""
    client = await get_rustfs_client()
    return await client.download_and_store_media(post_url, media_urls)


if __name__ == "__main__":
    # 測試用例
    async def test_rustfs():
        client = RustFSClient()
        await client.initialize()
        
        # 測試下載
        test_urls = [
            "https://example.com/image1.jpg",
            "https://example.com/image2.png"
        ]
        
        results = await client.download_and_store_media(
            "https://example.com/post/123", 
            test_urls
        )
        
        print("Download results:", results)
    
    asyncio.run(test_rustfs())

