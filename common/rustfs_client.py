"""
RustFS 客戶端 - 使用 S3 API 與 RustFS 對象存儲交互

支援功能：
- 媒體檔案上傳/下載
- 生命週期管理
- 預簽名 URL 生成
- 錯誤處理和重試
"""

import os
import socket
from urllib.parse import urlparse, urlunparse
import hashlib
import asyncio
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError, NoCredentialsError
import aiohttp
# import magic  # 暫時註解，避免 Windows 相容性問題

from .settings import get_settings


class RustFSClient:
    """RustFS 對象存儲客戶端"""
    
    def __init__(self):
        """初始化 RustFS 客戶端"""
        self.settings = get_settings()
        
        # RustFS 配置
        self.endpoint = os.getenv("RUSTFS_ENDPOINT", "http://localhost:9000")
        # 自動修正：若端點為 rustfs 且在當前環境不可解析，回退為 localhost
        try:
            parsed = urlparse(self.endpoint)
            host = (parsed.hostname or "").lower()
            if host == "rustfs":
                try:
                    socket.gethostbyname(host)
                except OSError:
                    new_netloc = f"localhost:{parsed.port or 9000}"
                    self.endpoint = urlunparse((parsed.scheme, new_netloc, "", "", "", ""))
        except Exception:
            pass
        self.access_key = os.getenv("RUSTFS_ACCESS_KEY", "rustfsadmin")
        self.secret_key = os.getenv("RUSTFS_SECRET_KEY", "rustfssecret")
        self.bucket = os.getenv("RUSTFS_BUCKET", "threads-media")
        self.region = os.getenv("RUSTFS_REGION", "us-east-1")
        
        # 媒體處理配置
        self.top_n_posts = int(os.getenv("MEDIA_TOP_N_POSTS", "5"))
        self.lifecycle_days = int(os.getenv("MEDIA_LIFECYCLE_DAYS", "3"))
        self.max_size_mb = int(os.getenv("MEDIA_MAX_SIZE_MB", "100"))
        
        # 初始化 S3 客戶端
        self._init_s3_client()
    
    def _init_s3_client(self):
        """初始化 S3 客戶端"""
        try:
            self.s3_client = boto3.client(
                's3',
                endpoint_url=self.endpoint,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                config=Config(
                    signature_version='s3v4',
                    retries={'max_attempts': 3, 'mode': 'adaptive'},
                    max_pool_connections=50
                ),
                region_name=self.region
            )
            
            # 確保 bucket 存在
            self._ensure_bucket_exists()
            
        except Exception as e:
            raise Exception(f"RustFS 客戶端初始化失敗: {str(e)}")
    
    def _ensure_bucket_exists(self):
        """確保 bucket 存在"""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                # Bucket 不存在，創建它
                try:
                    self.s3_client.create_bucket(Bucket=self.bucket)
                    print(f"已創建 RustFS bucket: {self.bucket}")
                except ClientError as create_error:
                    raise Exception(f"無法創建 bucket {self.bucket}: {str(create_error)}")
            else:
                raise Exception(f"檢查 bucket 失敗: {str(e)}")
    
    def _guess_mime_type_from_url(self, url: str) -> str:
        """
        根據 URL 推測 MIME 類型（簡單版本，避免 python-magic 依賴）
        
        Args:
            url: 媒體 URL
            
        Returns:
            str: 推測的 MIME 類型
        """
        url_lower = url.lower()
        
        # 圖片格式
        if '.jpg' in url_lower or '.jpeg' in url_lower:
            return 'image/jpeg'
        elif '.png' in url_lower:
            return 'image/png'
        elif '.gif' in url_lower:
            return 'image/gif'
        elif '.webp' in url_lower:
            return 'image/webp'
        
        # 影片格式
        elif '.mp4' in url_lower:
            return 'video/mp4'
        elif '.webm' in url_lower:
            return 'video/webm'
        elif '.mov' in url_lower:
            return 'video/mov'
        elif '.avi' in url_lower:
            return 'video/avi'
        
        # 根據 Instagram/Threads URL 模式推測
        elif 'instagram.f' in url_lower and ('jpg' in url_lower or 'jpeg' in url_lower):
            return 'image/jpeg'
        elif 'instagram.f' in url_lower and 'mp4' in url_lower:
            return 'video/mp4'
        
        # 預設值
        else:
            return 'application/octet-stream'
    
    async def download_media(self, url: str) -> Tuple[bytes, str]:
        """
        從 CDN URL 下載媒體檔案
        
        Args:
            url: 媒體 URL
            
        Returns:
            Tuple[bytes, str]: (媒體 bytes, MIME 類型)
        """
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    response.raise_for_status()
                    
                    # 獲取內容
                    media_bytes = await response.read()
                    
                    # 檢查檔案大小
                    size_mb = len(media_bytes) / (1024 * 1024)
                    if size_mb > self.max_size_mb:
                        raise Exception(f"媒體檔案過大: {size_mb:.1f}MB > {self.max_size_mb}MB")
                    
                    # 獲取 MIME 類型
                    mime_type = response.headers.get('Content-Type')
                    if not mime_type:
                        # 根據 URL 推測 MIME 類型（簡單版本）
                        mime_type = self._guess_mime_type_from_url(url)
                    
                    return media_bytes, mime_type
                    
        except aiohttp.ClientError as e:
            raise Exception(f"下載媒體失敗 {url}: {str(e)}")
        except Exception as e:
            raise Exception(f"處理媒體失敗 {url}: {str(e)}")
    
    def _generate_storage_key(self, post_id: str, media_bytes: bytes, mime_type: str) -> str:
        """
        生成存儲 key
        
        Args:
            post_id: 貼文 ID
            media_bytes: 媒體 bytes
            mime_type: MIME 類型
            
        Returns:
            str: 存儲 key
        """
        # 生成檔案雜湊
        file_hash = hashlib.sha256(media_bytes).hexdigest()[:16]
        
        # 根據 MIME 類型決定副檔名
        ext_map = {
            'image/jpeg': '.jpg',
            'image/png': '.png',
            'image/webp': '.webp',
            'image/gif': '.gif',
            'video/mp4': '.mp4',
            'video/webm': '.webm',
            'video/mov': '.mov',
            'video/avi': '.avi'
        }
        
        ext = ext_map.get(mime_type, '')
        
        return f"{post_id}/{file_hash}{ext}"
    
    async def store_media(
        self, 
        post_id: str, 
        media_bytes: bytes, 
        mime_type: str
    ) -> Dict[str, Any]:
        """
        存儲媒體到 RustFS
        
        Args:
            post_id: 貼文 ID
            media_bytes: 媒體 bytes
            mime_type: MIME 類型
            
        Returns:
            Dict[str, Any]: 存儲結果
        """
        try:
            # 生成存儲 key
            storage_key = self._generate_storage_key(post_id, media_bytes, mime_type)
            
            # 檢查是否已存在
            try:
                self.s3_client.head_object(Bucket=self.bucket, Key=storage_key)
                return {
                    "storage_key": storage_key,
                    "status": "already_exists",
                    "size_bytes": len(media_bytes),
                    "mime_type": mime_type
                }
            except ClientError as e:
                if e.response['Error']['Code'] != '404':
                    raise
            
            # 上傳到 RustFS
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=storage_key,
                Body=media_bytes,
                ContentType=mime_type,
                Metadata={
                    'post_id': post_id,
                    'upload_time': datetime.utcnow().isoformat(),
                    'size_bytes': str(len(media_bytes))
                }
            )
            
            return {
                "storage_key": storage_key,
                "status": "uploaded",
                "size_bytes": len(media_bytes),
                "mime_type": mime_type
            }
            
        except ClientError as e:
            raise Exception(f"RustFS 上傳失敗: {str(e)}")
        except Exception as e:
            raise Exception(f"存儲媒體失敗: {str(e)}")
    
    async def get_media(self, storage_key: str) -> Tuple[bytes, str]:
        """
        從 RustFS 獲取媒體
        
        Args:
            storage_key: 存儲 key
            
        Returns:
            Tuple[bytes, str]: (媒體 bytes, MIME 類型)
        """
        try:
            response = self.s3_client.get_object(Bucket=self.bucket, Key=storage_key)
            
            media_bytes = response['Body'].read()
            mime_type = response.get('ContentType', 'application/octet-stream')
            
            return media_bytes, mime_type
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                raise Exception(f"媒體檔案不存在: {storage_key}")
            else:
                raise Exception(f"RustFS 讀取失敗: {str(e)}")
        except Exception as e:
            raise Exception(f"獲取媒體失敗: {str(e)}")
    
    def generate_presigned_url(
        self, 
        storage_key: str, 
        expiration: int = 3600,
        method: str = 'get_object'
    ) -> str:
        """
        生成預簽名 URL
        
        Args:
            storage_key: 存儲 key
            expiration: 過期時間（秒）
            method: HTTP 方法
            
        Returns:
            str: 預簽名 URL
        """
        try:
            url = self.s3_client.generate_presigned_url(
                ClientMethod=method,
                Params={'Bucket': self.bucket, 'Key': storage_key},
                ExpiresIn=expiration
            )
            return url
            
        except ClientError as e:
            raise Exception(f"生成預簽名 URL 失敗: {str(e)}")
    
    def delete_media(self, storage_key: str) -> bool:
        """
        刪除媒體檔案
        
        Args:
            storage_key: 存儲 key
            
        Returns:
            bool: 是否成功刪除
        """
        try:
            self.s3_client.delete_object(Bucket=self.bucket, Key=storage_key)
            return True
            
        except ClientError as e:
            print(f"刪除媒體失敗 {storage_key}: {str(e)}")
            return False
    
    def cleanup_expired_media(self) -> Dict[str, Any]:
        """
        清理過期媒體檔案
        
        Returns:
            Dict[str, Any]: 清理結果
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=self.lifecycle_days)
            deleted_count = 0
            total_count = 0
            
            # 列出所有對象
            paginator = self.s3_client.get_paginator('list_objects_v2')
            
            for page in paginator.paginate(Bucket=self.bucket):
                if 'Contents' not in page:
                    continue
                
                for obj in page['Contents']:
                    total_count += 1
                    
                    # 檢查上傳時間
                    if obj['LastModified'].replace(tzinfo=None) < cutoff_date:
                        try:
                            self.s3_client.delete_object(
                                Bucket=self.bucket, 
                                Key=obj['Key']
                            )
                            deleted_count += 1
                        except ClientError:
                            continue
            
            return {
                "status": "completed",
                "total_objects": total_count,
                "deleted_objects": deleted_count,
                "cutoff_date": cutoff_date.isoformat(),
                "lifecycle_days": self.lifecycle_days
            }
            
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e)
            }
    
    def health_check(self) -> Dict[str, Any]:
        """健康檢查"""
        try:
            # 測試連接
            self.s3_client.head_bucket(Bucket=self.bucket)
            
            # 獲取 bucket 統計
            try:
                response = self.s3_client.list_objects_v2(
                    Bucket=self.bucket,
                    MaxKeys=1
                )
                object_count = response.get('KeyCount', 0)
            except:
                object_count = 0
            
            return {
                "status": "healthy",
                "service": "RustFS",
                "endpoint": self.endpoint,
                "bucket": self.bucket,
                "object_count": object_count,
                "config": {
                    "top_n_posts": self.top_n_posts,
                    "lifecycle_days": self.lifecycle_days,
                    "max_size_mb": self.max_size_mb
                }
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": f"RustFS 健康檢查失敗: {str(e)}"
            }


# 全域實例
_rustfs_client = None


def get_rustfs_client() -> RustFSClient:
    """獲取 RustFS 客戶端實例"""
    global _rustfs_client
    if _rustfs_client is None:
        _rustfs_client = RustFSClient()
    return _rustfs_client


# 便利函數
async def download_and_store_media(post_id: str, media_url: str) -> Dict[str, Any]:
    """下載並存儲媒體的便利函數"""
    client = get_rustfs_client()
    
    try:
        # 下載媒體
        media_bytes, mime_type = await client.download_media(media_url)
        
        # 存儲到 RustFS
        result = await client.store_media(post_id, media_bytes, mime_type)
        
        return {
            "success": True,
            "post_id": post_id,
            "media_url": media_url,
            "storage_result": result
        }
        
    except Exception as e:
        return {
            "success": False,
            "post_id": post_id,
            "media_url": media_url,
            "error": str(e)
        }


async def get_media_for_analysis(storage_key: str) -> Tuple[bytes, str]:
    """獲取用於分析的媒體的便利函數"""
    client = get_rustfs_client()
    return await client.get_media(storage_key)