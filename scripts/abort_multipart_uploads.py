#!/usr/bin/env python3
"""
清理 RustFS/S3 未完成的分段上傳（Multipart Uploads），以降低 heal queue 壓力。

使用方式：
  python scripts/abort_multipart_uploads.py --older-than-minutes 60

環境變數（可選，若未設置則採用預設值）：
  RUSTFS_ENDPOINT   預設: http://localhost:9000
  RUSTFS_ACCESS_KEY 預設: rustfsadmin
  RUSTFS_SECRET_KEY 預設: rustfsadmin
  RUSTFS_BUCKET     預設: social-media-content
"""

import os
import argparse
from datetime import datetime, timedelta, timezone
import boto3
from botocore.client import Config as BotoConfig


def get_s3_client():
    endpoint = os.getenv("RUSTFS_ENDPOINT", "http://localhost:9000")
    access_key = os.getenv("RUSTFS_ACCESS_KEY", "rustfsadmin")
    secret_key = os.getenv("RUSTFS_SECRET_KEY", "rustfsadmin")
    region = os.getenv("RUSTFS_REGION", "us-east-1")

    return boto3.client(
        's3',
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=BotoConfig(signature_version='s3v4', s3={'addressing_style': 'path'}),
        region_name=region,
    )


def abort_old_multipart_uploads(bucket: str, older_than_minutes: int) -> int:
    s3 = get_s3_client()
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)

    paginator = s3.get_paginator('list_multipart_uploads')
    aborted = 0

    for page in paginator.paginate(Bucket=bucket):
        uploads = page.get('Uploads', []) or []
        for u in uploads:
            key = u['Key']
            upload_id = u['UploadId']
            initiated = u.get('Initiated')
            if initiated and initiated < cutoff:
                try:
                    s3.abort_multipart_upload(Bucket=bucket, Key=key, UploadId=upload_id)
                    aborted += 1
                    print(f"[OK] Aborted MPU key={key} upload_id={upload_id} initiated={initiated}")
                except Exception as e:
                    print(f"[WARN] Abort failed key={key} upload_id={upload_id}: {e}")

    return aborted


def main():
    parser = argparse.ArgumentParser(description="Abort old multipart uploads to relieve heal queue")
    parser.add_argument("--bucket", default=os.getenv("RUSTFS_BUCKET", "social-media-content"))
    parser.add_argument("--older-than-minutes", type=int, default=60)
    args = parser.parse_args()

    count = abort_old_multipart_uploads(args.bucket, args.older_than_minutes)
    print(f"[SUMMARY] Aborted {count} multipart uploads older than {args.older_than_minutes} minutes in bucket '{args.bucket}'")


if __name__ == "__main__":
    main()



