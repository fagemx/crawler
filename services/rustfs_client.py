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
from pathlib import Path
import httpx
import asyncio
from urllib.parse import urlparse

from common.settings import get_settings
from common.db_client import get_db_client


class RustFSClient:
    """RustFS 客戶端"""
    
    def __init__(self):
        self.settings = get_settings()
        # 從環境讀取設定（支援本機與容器內網）
        self.base_url = os.getenv("RUSTFS_ENDPOINT", "http://rustfs:9000").rstrip("/")
        self.access_key = os.getenv("RUSTFS_ACCESS_KEY", "rustfsadmin")
        self.secret_key = os.getenv("RUSTFS_SECRET_KEY", "rustfsadmin")
        self.bucket_name = os.getenv("RUSTFS_BUCKET", "social-media-content")
        # 自動偵測：若本機無法解析 rustfs，改用 localhost
        self._auto_select_endpoint()

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
        
    async def initialize(self):
        """初始化 RustFS 客戶端，建立 bucket"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # 檢查 bucket 是否存在，不存在則建立
                response = await client.head(
                    f"{self.base_url}/{self.bucket_name}",
                    auth=(self.access_key, self.secret_key)
                )
                
                if response.status_code == 404:
                    # 建立 bucket
                    await client.put(
                        f"{self.base_url}/{self.bucket_name}",
                        auth=(self.access_key, self.secret_key)
                    )
                    print(f"✅ Created RustFS bucket: {self.bucket_name}")
                else:
                    print(f"✅ RustFS bucket exists: {self.bucket_name}")
                    
        except Exception as e:
            print(f"❌ Failed to initialize RustFS: {e}")
            raise

    def health_check(self) -> Dict[str, Any]:
        """RustFS 健康檢查（同步）"""
        try:
            import requests
            # 簡單檢查 endpoint 可達
            # 健檢使用 HEAD 並移除 Authorization（避免某些實作對未簽名 GET 嚴格檢查）
            resp = requests.head(self.base_url + "/", timeout=5)
            ok = resp.status_code < 500
            return {
                "status": "healthy" if ok else "unhealthy",
                "endpoint": self.base_url,
                "bucket": self.bucket_name,
                "http_status": resp.status_code,
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "endpoint": self.base_url,
                "bucket": self.bucket_name,
                "error": str(e),
            }
    
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
        tasks = [download_single_media(url) for url in media_urls]
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
            db_client = await get_db_client()
            # 確保 posts(url) 存在，避免 media_files 的 FK 失敗
            try:
                # author 暫以來源標記，media_urls 只放當前媒體以通過 schema
                await db_client.upsert_post(url=post_url, author="playwright", markdown=None, media_urls=[media_url])
            except Exception:
                # 忽略 upsert 失敗，後續 insert 若 FK 失敗會拋出詳細資訊
                pass
            media_id = await self._record_media_file(
                db_client, post_url, media_url, media_type, rustfs_key, "pending"
            )
            
            # 下載檔案
            async with httpx.AsyncClient(timeout=60.0) as client:
                print(f"📥 Downloading: {media_url}")
                
                # 下載原始檔案
                response = await client.get(media_url, follow_redirects=True)
                response.raise_for_status()
                
                file_content = response.content
                file_size = len(file_content)
                content_type = response.headers.get('content-type', '')
                
                # 獲取檔案擴展名
                file_extension = self._get_file_extension(media_url, content_type)
                
                # 上傳到 RustFS
                rustfs_url = await self._upload_to_rustfs(rustfs_key, file_content, content_type)
                
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
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.put(
                f"{self.base_url}/{self.bucket_name}/{key}",
                content=content,
                headers={'Content-Type': content_type},
                auth=(self.access_key, self.secret_key)
            )
            response.raise_for_status()
            
            # 返回訪問 URL
            return f"{self.base_url}/{self.bucket_name}/{key}"
    
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
            media_id = await conn.fetchval("""
                INSERT INTO media_files (
                    post_url, original_url, media_type, rustfs_key, download_status
                )
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
            """, post_url, original_url, media_type, rustfs_key, status)
            
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
                    download_status = $8,
                    download_error = $9,
                    downloaded_at = CASE WHEN $8 = 'completed' THEN now() ELSE downloaded_at END,
                    metadata = $10
                WHERE id = $1
            """, 
            media_id, rustfs_url, file_size, file_extension,
            metadata.get('width'), metadata.get('height'), metadata.get('duration'),
            status, error, metadata)
    
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