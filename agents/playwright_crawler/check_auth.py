#!/usr/bin/env python3
"""
檢查 auth.json 的狀態和有效性
"""

import json
from pathlib import Path
from datetime import datetime, timezone

from config import AUTH_FILE

def check_auth_status():
    """檢查認證檔案狀態"""
    print("🔍 檢查認證狀態")
    print("=" * 40)
    
    if not AUTH_FILE.exists():
        print("❌ auth.json 不存在")
        print("💡 請執行 python save_auth.py 進行認證")
        return False
    
    try:
        with open(AUTH_FILE, 'r', encoding='utf-8') as f:
            auth_data = json.load(f)
        
        # 基本資訊
        cookies = auth_data.get('cookies', [])
        origins = auth_data.get('origins', [])
        
        print(f"📄 檔案大小: {AUTH_FILE.stat().st_size} bytes")
        print(f"🍪 Cookies 數量: {len(cookies)}")
        print(f"🌐 Origins 數量: {len(origins)}")
        
        # 檢查關鍵 cookies
        threads_cookies = [c for c in cookies if 'threads.net' in c.get('domain', '')]
        ig_cookies = [c for c in cookies if 'instagram.com' in c.get('domain', '')]
        
        print(f"📱 Threads cookies: {len(threads_cookies)}")
        print(f"📷 Instagram cookies: {len(ig_cookies)}")
        
        # 查找重要的認證 cookies
        important_cookies = ['sessionid', 'csrftoken', 'mid', 'ig_did', 'rur']
        found_cookies = {}
        
        for cookie in cookies:
            name = cookie.get('name', '')
            if name in important_cookies:
                # 檢查過期時間
                expires = cookie.get('expires', -1)
                if expires > 0:
                    expire_date = datetime.fromtimestamp(expires, tz=timezone.utc)
                    is_expired = expire_date < datetime.now(timezone.utc)
                    status = "❌ 已過期" if is_expired else "✅ 有效"
                    found_cookies[name] = f"{status} (到期: {expire_date.strftime('%Y-%m-%d %H:%M UTC')})"
                else:
                    found_cookies[name] = "✅ 有效 (會話 cookie)"
        
        print("\n🔑 重要 Cookies:")
        for cookie_name in important_cookies:
            if cookie_name in found_cookies:
                print(f"  {cookie_name}: {found_cookies[cookie_name]}")
            else:
                print(f"  {cookie_name}: ❌ 未找到")
        
        # 整體評估
        has_sessionid = 'sessionid' in found_cookies
        has_csrftoken = 'csrftoken' in found_cookies
        
        print(f"\n📊 認證狀態評估:")
        if has_sessionid and has_csrftoken:
            print("✅ 認證看起來正常，應該可以正常爬取")
            return True
        elif has_sessionid:
            print("⚠️  有 sessionid 但缺少其他 cookies，可能部分功能受限")
            return True
        else:
            print("❌ 缺少關鍵認證資訊，建議重新執行 save_auth.py")
            return False
            
    except json.JSONDecodeError:
        print("❌ auth.json 格式錯誤")
        return False
    except Exception as e:
        print(f"❌ 檢查時發生錯誤: {e}")
        return False

if __name__ == "__main__":
    check_auth_status() 