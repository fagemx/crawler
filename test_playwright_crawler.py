import asyncio
import json
import random
from pathlib import Path
from playwright.async_api import async_playwright, Error
import os
import re

# --- ★★★ 修正後的解析函數 ★★★ ---
def parse_views_text(text: str) -> int:
    """
    Parses view count text like '串文\n1.2萬次瀏覽' or '1,234 views' into an integer.
    Handles various formats including commas, newlines, and units (k, m, 萬, 億).
    """
    if not text:
        return 0

    # --- 關鍵修正：只處理換行符後的內容 ---
    # 這可以將 '串文\n4,559次瀏覽' 處理為 '4,559次瀏覽'
    if '\n' in text:
        text = text.split('\n')[-1]
    
    # 接下來的邏輯處理已經被清理過的文本
    text = text.replace(',', '').strip()
    
    # 移除「次瀏覽」或「views」等後綴，為單位檢測做準備
    cleaned_text = re.sub(r'(?i)\s*(次?瀏覽|views?).*', '', text)
    
    unit_multipliers = {
        '萬': 10000,
        'k': 1000,
        'm': 1000000,
        '億': 100000000
    }
    
    number_part = cleaned_text
    multiplier = 1

    for unit, mult in unit_multipliers.items():
        if unit in cleaned_text.lower():
            number_part = cleaned_text.lower().replace(unit, '').strip()
            multiplier = mult
            break

    try:
        base_number = float(number_part)
        return int(base_number * multiplier)
    except (ValueError, TypeError):
        # 使用原始文本進行日誌記錄，以便更好地除錯
        print(f"⚠️ 無法從原始文本 '{text}' 解析數字部分 '{number_part}'，返回 0")
        return 0
# --- 修正結束 ---


# --- 測試設定 ---
HOME_URL = "https://www.threads.com/"
PROFILE_URL = "https://www.threads.com/@wuyiju28"
POST_URL = "https://www.threads.com/@wuyiju28/post/DMyvZJRz5Cz"

from common.config import get_auth_file_path
AUTH_FILE_PATH = get_auth_file_path(from_project_root=True)
UA_CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"


async def main():
    if not AUTH_FILE_PATH.exists():
        print(f"❌ 錯誤：找不到認證檔案 '{AUTH_FILE_PATH}'。")
        print("   請先執行 'agents/playwright_crawler/save_auth.py' 來產生此檔案。")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            storage_state=str(AUTH_FILE_PATH),
            user_agent=UA_CHROME,
            locale="zh-TW",
            extra_http_headers={
                "sec-ch-ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": "Windows",
            }
        )
        await context.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        page = await context.new_page()

        print("🔧 測試開始...")
        print(f"   - 目標個人檔案: {PROFILE_URL}")
        print(f"   - 目標貼文: {POST_URL}")

        try:
            print(f"\n🚀 步驟 1/3: 導航至首頁 ({HOME_URL})...")
            await page.goto(HOME_URL, wait_until="networkidle")
            await asyncio.sleep(random.uniform(1, 3))

            print(f"🚀 步驟 2/3: 導航至用戶個人主頁 ({PROFILE_URL})...")
            await page.goto(PROFILE_URL, wait_until="networkidle")
            await asyncio.sleep(random.uniform(1, 3))

            print(f"🚀 步驟 3/3: 最終導航至目標貼文 ({POST_URL})...")
            await page.goto(POST_URL, wait_until="networkidle")
            print("✅ 目標貼文頁面載入完成！")
            
            view_selector = "a:has-text('瀏覽'), a:has-text('view')"
            print(f"\n🔎 開始使用 Selector 尋找瀏覽數: '{view_selector}'")

            try:
                view_element = await page.wait_for_selector(view_selector, timeout=15000)
                
                if view_element:
                    raw_text = await view_element.inner_text()
                    parsed_views = parse_views_text(raw_text)

                    print("\n--- 測試結果 ---")
                    print(f"🎉 成功找到元素！")
                    print(f"   - 原始文本: '{raw_text.replace('\n', ' ')}'") # 為了美觀，日誌中替換換行符
                    print(f"   - 解析結果: {parsed_views:,}")
                    print("------------------")

            except Error as e:
                print("\n--- 測試結果 ---")
                print(f"❌ 使用 Selector 尋找元素時失敗: {type(e).__name__}")
                print(f"   請檢查 Selector 或頁面結構。")
                print("------------------")

        except Error as e:
            print(f"\n❌ 頁面導航失敗: {e}")
        
        finally:
            print("\n🚪 正在關閉瀏覽器...")
            await browser.close()

if __name__ == "__main__":
    project_root = Path(__file__).parent
    os.chdir(project_root)
    asyncio.run(main())
