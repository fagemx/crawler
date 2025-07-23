#!/usr/bin/env python3
"""
測試 Jina Reader API 是否需要 API Key
"""

import requests

def test_jina_reader():
    """測試 Jina Reader 基本功能"""
    print("測試 Jina Reader API...")
    
    # 測試 URL
    test_url = "https://r.jina.ai/https://www.threads.com"
    
    try:
        # 測試 markdown 格式
        print("1. 測試 markdown 格式...")
        response = requests.get(
            test_url,
            headers={"x-respond-with": "markdown"},
            timeout=10
        )
        print(f"狀態碼: {response.status_code}")
        print(f"回應長度: {len(response.text)} 字元")
        
        if response.status_code == 200:
            print("✅ Markdown 格式測試成功")
            print(f"前 200 字元: {response.text[:200]}...")
        else:
            print(f"❌ Markdown 格式測試失敗: {response.status_code}")
            print(f"錯誤訊息: {response.text}")
        
        # 測試 screenshot 格式
        print("\n2. 測試 screenshot 格式...")
        response = requests.get(
            test_url,
            headers={"x-respond-with": "screenshot"},
            timeout=15
        )
        print(f"狀態碼: {response.status_code}")
        print(f"Content-Type: {response.headers.get('content-type', 'unknown')}")
        print(f"回應大小: {len(response.content)} bytes")
        
        if response.status_code == 200:
            print("✅ Screenshot 格式測試成功")
            # 檢查是否為圖片格式
            if response.content.startswith(b'\x89PNG'):
                print("📸 檢測到 PNG 格式")
            elif response.content.startswith(b'\xff\xd8'):
                print("📸 檢測到 JPEG 格式")
            else:
                print("❓ 未知圖片格式")
        else:
            print(f"❌ Screenshot 格式測試失敗: {response.status_code}")
            print(f"錯誤訊息: {response.text}")
        
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"❌ 網路請求失敗: {e}")
        return False
    except Exception as e:
        print(f"❌ 測試失敗: {e}")
        return False


def test_with_api_key():
    """測試是否需要 API Key"""
    print("\n測試是否需要 API Key...")
    
    # 常見的 API Key header 名稱
    api_key_headers = [
        "Authorization",
        "X-API-Key", 
        "Jina-API-Key",
        "x-api-key"
    ]
    
    test_url = "https://r.jina.ai/https://www.threads.com"
    
    for header_name in api_key_headers:
        try:
            print(f"測試 {header_name} header...")
            response = requests.get(
                test_url,
                headers={
                    "x-respond-with": "markdown",
                    header_name: "test-key"
                },
                timeout=5
            )
            
            if response.status_code == 401:
                print(f"🔑 {header_name} 可能需要有效的 API Key")
            elif response.status_code == 200:
                print(f"✅ {header_name} 不需要或測試 key 有效")
            else:
                print(f"❓ {header_name} 回應: {response.status_code}")
                
        except Exception as e:
            print(f"❌ {header_name} 測試失敗: {e}")


def main():
    """主函數"""
    print("Jina Reader API 測試")
    print("=" * 40)
    
    # 基本功能測試
    basic_test = test_jina_reader()
    
    # API Key 測試
    test_with_api_key()
    
    print("\n" + "=" * 40)
    if basic_test:
        print("🎉 Jina Reader 基本功能正常，無需 API Key！")
        print("💡 可以直接使用 https://r.jina.ai/ 服務")
    else:
        print("⚠️  Jina Reader 測試失敗，請檢查網路連線")
    
    return 0 if basic_test else 1


if __name__ == "__main__":
    exit(main())