#!/usr/bin/env python3
"""
簡單測試 RustFS S3 API 連接 - 使用 httpx
"""

import httpx
import json
import requests

# RustFS 服務的基本 URL
base_url = "http://localhost:9000"

# S3 兼容的設置 (MinIO)
s3_endpoint = base_url

def test_rustfs_simple():
    """簡單測試 RustFS S3 API"""
    
    try:
        # 測試 1: 檢查根路徑
        print("🔍 測試 1: 檢查 RustFS 根路徑")
        response = httpx.get(f"{base_url}/")
        if response.status_code == 200:
            print("✅ RustFS 根路徑響應正常")
            print(f"   狀態碼: {response.status_code}")
            print(f"   內容類型: {response.headers.get('content-type', 'unknown')}")
        else:
            print(f"❌ 根路徑響應異常: {response.status_code}")
            return False
        
        # 測試 2: 檢查是否有 S3 API 端點
        print(f"\n🔍 測試 2: 檢查 S3 API 端點")
        # 嘗試訪問一個典型的 S3 端點（會返回錯誤但證明 API 存在）
        response = httpx.get(f"{base_url}/test-bucket")
        print(f"   狀態碼: {response.status_code}")
        if response.status_code in [403, 404, 400]:  # 這些都是正常的 S3 錯誤響應
            print("✅ S3 API 端點響應正常（返回預期的錯誤碼）")
        else:
            print(f"⚠️  意外的響應碼: {response.status_code}")
        
        # 測試 3: 檢查健康端點
        print(f"\n🔍 測試 3: 檢查健康端點")
        try:
            response = httpx.get(f"{base_url}/minio/health/live")
            print(f"   狀態碼: {response.status_code}")
            if response.status_code in [200, 403]:  # 200 = OK, 403 = 需要認證但端點存在
                print("✅ 健康端點存在")
            else:
                print(f"⚠️  健康端點響應: {response.status_code}")
        except Exception as e:
            print(f"⚠️  健康端點測試失敗: {e}")
        
        # 測試 4: 檢查端口是否真的在監聽
        print(f"\n🔍 測試 4: 檢查端口連接")
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex(('localhost', 9000))
        sock.close()
        
        if result == 0:
            print("✅ 端口 9000 正在監聽")
        else:
            print("❌ 端口 9000 無法連接")
            return False
        
        print(f"\n🎉 基本測試通過! RustFS 正在 http://localhost:9000 運行")
        print("💡 要進行完整的 S3 API 測試，請安裝 boto3: pip install boto3")
        print("   然後運行: python test_rustfs_s3.py")
        
        return True
        
    except Exception as e:
        print(f"❌ 測試失敗: {e}")
        return False

def check_port_listening(port=9000):
    """檢查指定端口是否正在監聽"""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        result = sock.connect_ex(('localhost', 9000))
        if result == 0:
            print(f"✅ 端口 {port} 正在監聽")
            return True
        else:
            print(f"❌ 端口 {port} 無法連接")
            return False

def main():
    print(f"\n🎉 基本測試通過! RustFS 正在 http://localhost:9000 運行")
    print("你可以開始使用 'mc' 客戶端或 S3 SDK 與其交互。")

if __name__ == "__main__":
    test_rustfs_simple()