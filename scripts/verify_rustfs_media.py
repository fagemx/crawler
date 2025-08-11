#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
驗證 RustFS 與資料庫一致性：
- 掃描 media_files(download_status='completed' 且有 rustfs_key/url)
- 以 S3 HEAD/GET 方式檢查物件是否存在
- 若不存在：將 download_status 標記為 'failed'，download_error='missing_on_rustfs'
- 輸出修復統計

PowerShell 執行範例：
python scripts/verify_rustfs_media.py --batch-size 200 --dry-run
python scripts/verify_rustfs_media.py --batch-size 200
"""

import os
import sys
import asyncio
import argparse
from typing import List, Dict, Any

import asyncpg
import boto3
from botocore.exceptions import ClientError

DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/social_media_db")
RUSTFS_ENDPOINT = os.getenv("RUSTFS_ENDPOINT", "http://localhost:9000")
RUSTFS_ACCESS_KEY = os.getenv("RUSTFS_ACCESS_KEY", "rustfsadmin")
RUSTFS_SECRET_KEY = os.getenv("RUSTFS_SECRET_KEY", "rustfsadmin")
RUSTFS_BUCKET = os.getenv("RUSTFS_BUCKET", "social-media-content")


def build_s3_client():
    return boto3.client(
        's3',
        endpoint_url=RUSTFS_ENDPOINT,
        aws_access_key_id=RUSTFS_ACCESS_KEY,
        aws_secret_access_key=RUSTFS_SECRET_KEY,
        region_name='us-east-1'
    )


async def fetch_completed_media(conn: asyncpg.Connection, limit: int) -> List[Dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT id, rustfs_key, rustfs_url
        FROM media_files
        WHERE download_status = 'completed'
          AND (rustfs_key IS NOT NULL OR rustfs_url IS NOT NULL)
        ORDER BY id DESC
        LIMIT $1
        """,
        limit,
    )
    return [dict(r) for r in rows]


def normalize_key(row: Dict[str, Any]) -> str:
    key = row.get('rustfs_key')
    if key:
        return key
    url = row.get('rustfs_url') or ''
    # 允許形如 http://host:9000/bucket/key
    try:
        prefix = f"{RUSTFS_ENDPOINT.rstrip('/')}/{RUSTFS_BUCKET}/"
        if url.startswith(prefix):
            return url[len(prefix):]
        # 兼容 http://rustfs:9000 之類不同主機名
        # 取最後 '/bucket/' 後的部分
        parts = url.split(f"/{RUSTFS_BUCKET}/", 1)
        if len(parts) == 2:
            return parts[1]
    except Exception:
        pass
    return ''


def head_object_exists(s3, key: str) -> bool:
    try:
        s3.head_object(Bucket=RUSTFS_BUCKET, Key=key)
        return True
    except ClientError as e:
        code = e.response.get('Error', {}).get('Code', '')
        if code in ('404', 'NoSuchKey', 'NotFound'):
            return False
        # 其他錯誤當作存在未知狀況，交給上層決定
        return False


async def mark_missing(conn: asyncpg.Connection, ids: List[int], dry_run: bool) -> int:
    if not ids:
        return 0
    if dry_run:
        return len(ids)
    await conn.execute(
        """
        UPDATE media_files
        SET download_status = 'failed',
            download_error = 'missing_on_rustfs'
        WHERE id = ANY($1)
        """,
        ids,
    )
    return len(ids)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch-size', type=int, default=500)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    s3 = build_s3_client()
    conn = await asyncpg.connect(DB_URL)

    try:
        rows = await fetch_completed_media(conn, args.batch_size)
        missing_ids: List[int] = []
        checked = 0
        for r in rows:
            key = normalize_key(r)
            if not key:
                continue
            exists = head_object_exists(s3, key)
            checked += 1
            if not exists:
                missing_ids.append(r['id'])
        updated = await mark_missing(conn, missing_ids, args.dry_run)
        print({
            'checked': checked,
            'missing': len(missing_ids),
            'updated': updated,
            'dry_run': args.dry_run,
        })
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())
