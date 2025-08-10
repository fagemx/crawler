#!/usr/bin/env python3
"""
依前綴批次刪除 S3/RustFS 物件（支援大量鍵，分頁刪除）。

使用方式：
  python scripts/delete_objects_by_prefix.py --prefix image/1c/ --confirm

參數：
  --prefix 要刪除的 key 前綴（必填）
  --bucket 目標 bucket（預設從環境 RUSTFS_BUCKET 或 social-media-content）
  --confirm 加上後才會實際刪除，否則僅預覽
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


def delete_by_prefix(bucket: str, prefix: str, confirm: bool) -> int:
    s3 = get_s3_client()
    paginator = s3.get_paginator('list_objects_v2')
    total = 0
    batch = []

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        contents = page.get('Contents', []) or []
        for obj in contents:
            batch.append({'Key': obj['Key']})
            if len(batch) == 1000:
                if confirm:
                    s3.delete_objects(Bucket=bucket, Delete={'Objects': batch, 'Quiet': True})
                else:
                    print(f"[DRY] Would delete {len(batch)} objects")
                total += len(batch)
                batch = []

    if batch:
        if confirm:
            s3.delete_objects(Bucket=bucket, Delete={'Objects': batch, 'Quiet': True})
        else:
            print(f"[DRY] Would delete {len(batch)} objects")
        total += len(batch)

    return total


def main():
    parser = argparse.ArgumentParser(description="Delete objects by prefix")
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--bucket", default=os.getenv("RUSTFS_BUCKET", "social-media-content"))
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()

    count = delete_by_prefix(args.bucket, args.prefix, args.confirm)
    print(f"[SUMMARY] {'Deleted' if args.confirm else 'Would delete'} {count} objects with prefix '{args.prefix}' in bucket '{args.bucket}'")


if __name__ == "__main__":
    main()



