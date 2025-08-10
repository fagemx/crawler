#!/usr/bin/env python3
"""
列出 RustFS/S3 bucket 當前所有未完成的分段上傳，協助觀察是否有大量掛起的 MPU。

使用方式：
  python scripts/list_multipart_uploads.py
  python scripts/list_multipart_uploads.py --bucket my-bucket
"""

import os
import argparse
from datetime import timezone
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


def list_multipart_uploads(bucket: str):
    s3 = get_s3_client()
    paginator = s3.get_paginator('list_multipart_uploads')

    total = 0
    for page in paginator.paginate(Bucket=bucket):
        uploads = page.get('Uploads', []) or []
        for u in uploads:
            total += 1
            initiated = u.get('Initiated')
            if initiated and initiated.tzinfo is None:
                initiated = initiated.replace(tzinfo=timezone.utc)
            print(f"- key={u['Key']} upload_id={u['UploadId']} initiated={initiated}")

    print(f"[SUMMARY] Total multipart uploads in '{bucket}': {total}")


def main():
    parser = argparse.ArgumentParser(description="List current multipart uploads in a bucket")
    parser.add_argument("--bucket", default=os.getenv("RUSTFS_BUCKET", "social-media-content"))
    args = parser.parse_args()

    list_multipart_uploads(args.bucket)


if __name__ == "__main__":
    main()



