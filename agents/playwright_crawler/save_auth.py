#!/usr/bin/env python3
"""
Playwright Crawler Agent - 認證工具 (v3 - 穩定登入版)

核心策略：
1.  模擬真實使用者環境 (偽裝 webdriver, 使用 Windows UA)。
2.  反轉登入流程，先登入主要網站 Instagram，再訪問 Threads 同步。
3.  移除所有不必要的網路攔截，確保登入流程純淨。
"""
import asyncio
import json
import logging
from pathlib import Path
from playwright.async_api import async_playwright
import sys
import os

# 動態找到專案根目錄
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from common.config import get_auth_file_path

# 與使用者環境匹配的 Windows User-Agent
WINDOWS_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

async def main():
    print("🔐 Playwright Crawler - 認證工具 (v3 - 穩定登入版)")
    print("=" * 50)
    
    auth_file_path = get_auth_file_path()

    if auth_file_path.exists():
        response = input(f"⚠️  {auth_file_path} 已存在，是否覆蓋？ (y/N): ").strip().lower()
        if response != 'y':
            print("已取消")
            return
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent=WINDOWS_UA,
            locale="zh-TW",
        )
        
        # ★★★ 關鍵：在所有頁面載入前，抹除自動化特徵 ★★★
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        page = await context.new_page()

        # --- 步驟 1: 登入主要網站 Instagram ---
        login_url = "https://www.instagram.com/accounts/login/"
        print(f"📱 步驟 1/4: 導覽至 Instagram 登入頁面")
        print(f"   -> {login_url}")
        # 對於動態網站，等待 'domcontentloaded' 更可靠
        await page.goto(login_url, wait_until="domcontentloaded")
        
        print("\n" + "=" * 50)
        print("👉 請在瀏覽器中手動完成 Instagram 登入。")
        print("   完成登入並看到首頁後，回到此終端視窗並按 Enter...")
        input("✅ Instagram 登入完成後，請按 Enter...")

        # --- 步驟 2: "互動式暖機", 模擬真人瀏覽行為以建立信任 ---
        print('🔄 步驟 2/3: 正在進行 "互動式暖機"，請稍候...')
        try:
            await page.mouse.wheel(0, 1000)
            await asyncio.sleep(2)
            await page.mouse.wheel(0, 1500)
            await asyncio.sleep(2)
            print("   -> 模擬滾動完成。")
        except Exception as e:
            print(f"   -> 暖機操作時發生輕微錯誤，但不影響繼續: {e}")
        
        # --- 步驟 3: 在當前頁面背景中請求 Threads 以同步 Cookies ---
        print("🔄 步驟 3/4: 在背景中請求 Threads 以同步認證...")
        threads_url = "https://www.threads.net/"
        try:
            await page.evaluate(f"fetch('{threads_url}').catch(e => console.error('Fetch error:', e))")
            print("   -> 背景請求已發送。等待 5 秒以確保 Cookie 同步...")
            await asyncio.sleep(5)
            print("✅ Threads 同步完成。")
        except Exception as e:
            print(f"❌ 在背景請求 Threads 時發生錯誤，但不影響儲存 Instagram Cookie：{e}")

        # --- 步驟 4: 導航到 Threads.com 讓用戶手動登入 ---
        print("🔄 步驟 4/5: 導航到 Threads.com，請手動完成登入...")
        threads_com_url = "https://www.threads.com/"
        try:
            await page.goto(threads_com_url, wait_until="domcontentloaded")
            print(f"✅ 已導航到 {threads_com_url}")
            print("👉 請在瀏覽器中完成 Threads 登入（如果需要點擊 'Continue as' 按鈕，請手動點擊）")
            
        except Exception as e:
            print(f"❌ 導航到 Threads.com 時發生錯誤：{e}")
            print("   -> 但不影響繼續，將使用現有的認證狀態")

        print("\n" + "=" * 50)
        print("👉 所有認證步驟已完成。")
        input("✅ 確認無誤後，請按 Enter 以儲存認證檔案並關閉瀏覽器...")

        # --- 步驟 5: 儲存認證資訊 ---
        try:
            print(f"💾 步驟 5/5: 正在儲存認證資訊...")
            storage_state = await context.storage_state()
            
            # 驗證關鍵 Cookie 是否存在
            required_cookies = {"sessionid", "ds_user_id", "csrftoken"}
            found_cookies = {cookie['name'] for cookie in storage_state['cookies']}
            
            if not required_cookies.issubset(found_cookies):
                print("❌ 警告：儲存的資訊中缺少必要的 Cookie。")
                print(f"   -> 應有: {required_cookies}")
                print(f"   -> 實有: {found_cookies}")
                print(f"   -> 請確保您已成功登入 Instagram。")
            
            auth_file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(auth_file_path, 'w', encoding='utf-8') as f:
                json.dump(storage_state, f, ensure_ascii=False, indent=4)
            
            print(f"✅ 成功儲存認證資訊至 {auth_file_path}")
            print(f"   -> 共儲存 {len(storage_state['cookies'])} 個 Cookies。")

        except Exception as e:
            print(f"❌ 儲存認證時發生錯誤：{e}")
        finally:
            await browser.close()
            print("🚪 瀏覽器已關閉。")
    
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    os.chdir(project_root)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️  使用者中斷")
    except Exception as e:
        print(f"❌ 執行時發生未預期錯誤：{e}")
