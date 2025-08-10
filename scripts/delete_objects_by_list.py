#!/usr/bin/env python3
"""
讀取 key 清單（每行一個 key），批次刪除 S3/RustFS 物件。

使用方式：
  python scripts/delete_objects_by_list.py --file heal_keys.txt

參數：
  --file   指向包含 key 清單的檔案
  --bucket 目標 bucket（預設從環境 RUSTFS_BUCKET 或 social-media-content）
  --dry-run 僅顯示將刪除的 key，不實際刪除
"""

import os
import argparse
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


def delete_by_list(file_path: str, bucket: str, dry_run: bool) -> int:
    s3 = get_s3_client()
    with open(file_path, 'r', encoding='utf-8') as f:
        keys = [line.strip() for line in f if line.strip()]

    deleted = 0
    batch = []
    for key in keys:
        batch.append({'Key': key})
        # S3 刪除 API 每次最多 1000 筆
        if len(batch) == 1000:
            if dry_run:
                print(f"[DRY] Would delete {len(batch)} objects...")
            else:
                s3.delete_objects(Bucket=bucket, Delete={'Objects': batch, 'Quiet': True})
            deleted += len(batch)
            batch = []

    if batch:
        if dry_run:
            print(f"[DRY] Would delete {len(batch)} objects...")
        else:
            s3.delete_objects(Bucket=bucket, Delete={'Objects': batch, 'Quiet': True})
        deleted += len(batch)

    return deleted


def main():
    parser = argparse.ArgumentParser(description="Delete objects by key list")
    parser.add_argument("--file", required=True)
    parser.add_argument("--bucket", default=os.getenv("RUSTFS_BUCKET", "social-media-content"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    count = delete_by_list(args.file, args.bucket, args.dry_run)
    print(f"[SUMMARY] {'Would delete' if args.dry_run else 'Deleted'} {count} objects from '{args.bucket}'")


if __name__ == "__main__":
    main()



