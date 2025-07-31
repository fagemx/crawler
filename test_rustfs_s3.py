#!/usr/bin/env python3
"""
測試 RustFS S3 API 連接
"""

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

def test_rustfs_s3():
    """測試 RustFS S3 API"""
    
    # 創建 S3 客戶端
    s3_client = boto3.client(
        's3',
        endpoint_url='http://localhost:9000',
        aws_access_key_id='rustfsadmin',
        aws_secret_access_key='rustfsadmin',
        config=Config(signature_version='s3v4'),
        region_name='us-east-1'
    )
    
    try:
        # 測試 1: 列出所有 buckets
        print("🔍 測試 1: 列出所有 buckets")
        response = s3_client.list_buckets()
        print(f"✅ 成功! 找到 {len(response['Buckets'])} 個 buckets:")
        for bucket in response['Buckets']:
            print(f"  - {bucket['Name']} (創建於: {bucket['CreationDate']})")
        
        # 測試 2: 創建測試 bucket
        test_bucket = 'social-media-content'
        print(f"\n🔍 測試 2: 創建 bucket '{test_bucket}'")
        try:
            s3_client.create_bucket(Bucket=test_bucket)
            print(f"✅ 成功創建 bucket: {test_bucket}")
        except ClientError as e:
            if e.response['Error']['Code'] == 'BucketAlreadyOwnedByYou':
                print(f"ℹ️  Bucket {test_bucket} 已存在")
            else:
                print(f"❌ 創建 bucket 失敗: {e}")
        
        # 測試 3: 上傳測試文件
        print(f"\n🔍 測試 3: 上傳測試文件")
        test_content = "Hello from RustFS S3 API!"
        s3_client.put_object(
            Bucket=test_bucket,
            Key='test.txt',
            Body=test_content.encode('utf-8'),
            ContentType='text/plain'
        )
        print("✅ 成功上傳測試文件: test.txt")
        
        # 測試 4: 下載測試文件
        print(f"\n🔍 測試 4: 下載測試文件")
        response = s3_client.get_object(Bucket=test_bucket, Key='test.txt')
        downloaded_content = response['Body'].read().decode('utf-8')
        print(f"✅ 成功下載文件內容: {downloaded_content}")
        
        # 測試 5: 列出 bucket 中的對象
        print(f"\n🔍 測試 5: 列出 bucket 中的對象")
        response = s3_client.list_objects_v2(Bucket=test_bucket)
        if 'Contents' in response:
            print(f"✅ 找到 {len(response['Contents'])} 個對象:")
            for obj in response['Contents']:
                print(f"  - {obj['Key']} (大小: {obj['Size']} bytes)")
        else:
            print("ℹ️  Bucket 為空")
            
        print(f"\n🎉 所有測試通過! RustFS S3 API 正常運行在 http://localhost:9000")
        return True
        
    except Exception as e:
        print(f"❌ 測試失敗: {e}")
        return False

if __name__ == "__main__":
    test_rustfs_s3()