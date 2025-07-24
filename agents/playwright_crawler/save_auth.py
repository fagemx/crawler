#!/usr/bin/env python3
"""
Playwright Crawler Agent - 認證工具
用於產生 auth.json 檔案，供 Playwright Crawler Agent 使用。

使用方式：
1. 在桌面環境執行: python save_auth.py
2. 手動登入 Threads 帳號
3. 完成後會產生 auth.json 檔案

注意：為了與 Docker 容器相容，會使用與容器相同的 User-Agent 和設定。
"""

import asyncio
import json
import logging
from pathlib import Path
from playwright.async_api import async_playwright

from config import AUTH_FILE, DOCKER_COMPATIBLE_UA

async def main():
    """主要認證流程"""
    print("🔐 Playwright Crawler - 認證工具")
    print("=" * 50)
    
    if AUTH_FILE.exists():
        response = input(f"⚠️  {AUTH_FILE} 已存在，是否覆蓋？ (y/N): ").strip().lower()
        if response != 'y':
            print("已取消")
            return
    
    async with async_playwright() as p:
        print("🚀 啟動瀏覽器...")
        browser = await p.chromium.launch(
            headless=False,  # 需要顯示視窗供手動登入
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security",
                "--disable-features=VizDisplayCompositor",
            ]
        )
        
        # 使用與容器相同的設定
        context = await browser.new_context(
            user_agent=DOCKER_COMPATIBLE_UA,
            viewport={"width": 1280, "height": 720},
            locale="en-US",
            timezone_id="UTC",
            has_touch=True,
            accept_downloads=False
        )
        
        page = await context.new_page()
        
        print("📱 導覽至 Threads 登入頁面...")
        await page.goto("https://www.threads.net/login", wait_until="networkidle")
        
        print("\n" + "=" * 50)
        print("👉 請在瀏覽器中手動完成以下步驟：")
        print("   1. 輸入您的 Instagram/Threads 帳號密碼")
        print("   2. 完成二階段驗證（如有設定）")
        print("   3. 確認成功登入到 Threads 主頁")
        print("   4. 完成後請按下瀏覽器中的 'Resume' 按鈕")
        print("=" * 50)
        
        # 暫停讓使用者手動登入
        await page.pause()
        
        # 檢查登入狀態
        try:
            current_url = page.url
            if "/login" in current_url:
                print("❌ 仍在登入頁面，請確認已成功登入")
                return
            
            print(f"✅ 當前頁面：{current_url}")
            
            # 儲存認證狀態
            print("💾 儲存認證資訊...")
            await context.storage_state(path=AUTH_FILE)
            
            # 驗證儲存的檔案
            if AUTH_FILE.exists():
                with open(AUTH_FILE, 'r', encoding='utf-8') as f:
                    auth_data = json.load(f)
                    cookie_count = len(auth_data.get('cookies', []))
                    print(f"✅ 成功儲存 {AUTH_FILE}（包含 {cookie_count} 個 cookies）")
                    
                    # 檢查關鍵 cookies
                    has_sessionid = any(c.get('name') == 'sessionid' for c in auth_data.get('cookies', []))
                    if has_sessionid:
                        print("✅ 發現 sessionid cookie，認證應該有效")
                    else:
                        print("⚠️  未發現 sessionid cookie，可能需要重新認證")
            else:
                print("❌ 儲存失敗")
                
        except Exception as e:
            print(f"❌ 儲存認證時發生錯誤：{e}")
        finally:
            await browser.close()
    
    print("\n🎉 認證完成！現在可以執行 Playwright Crawler Agent 了。")

if __name__ == "__main__":
    # 設定日誌
    logging.basicConfig(level=logging.INFO)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️  使用者中斷")
    except Exception as e:
        print(f"❌ 執行錯誤：{e}")
        import traceback
        traceback.print_exc() 