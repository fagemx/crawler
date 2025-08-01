"""
Playwright API Fetcher - Threads 觀看數擷取器
版本：1.0 (最終策略 - 瀏覽器內核 API 請求)
作者：AI Assistant (基於與使用者的深度合作探索)
日期：2025-08-01

核心策略:
1.  啟動一個 Playwright 無頭瀏覽器。
2.  載入 `save_auth.py` 產生的、可信的 `auth.json` 會話狀態。
3.  在一個已登入的 instagram.com 頁面上下文中，使用 JavaScript 的 `fetch` 函數
    直接呼叫 Threads GraphQL API。
4.  利用真實瀏覽器的請求指紋，從根源上繞過伺服器的客戶端驗證。
"""
import asyncio
import json
from pathlib import Path
import sys
from playwright.async_api import async_playwright, Playwright

# --- 設定路徑 ---
try:
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from common.config import get_auth_file_path
except ImportError:
    def get_auth_file_path():
        return Path("agents/playwright_crawler/auth.json")

class PlaywrightAPIClient:
    """使用 Playwright 瀏覽器內核發送 API 請求的客戶端"""
    def __init__(self, auth_file: Path):
        self.auth_file = auth_file
        self.playwright: Playwright | None = None
        self.browser = None
        
    async def launch(self):
        """啟動瀏覽器並準備上下文"""
        print("🚀 正在啟動 Playwright 瀏覽器...")
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True)
        print("✅ 瀏覽器已啟動。")

    async def get_views(self, post_code: str) -> int:
        """獲取指定貼文的觀看數"""
        if not self.browser:
            raise RuntimeError("瀏覽器尚未啟動，請先呼叫 launch()")

        context = await self.browser.new_context(storage_state=str(self.auth_file))
        page = await context.new_page()

        try:
            # 導航到一個安全的、已登入的頁面以建立執行環境
            await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")

            # 從上下文中提取 csrftoken 以用於標頭
            cookies = await context.cookies()
            csrftoken = next((c['value'] for c in cookies if c['name'] == 'csrftoken'), None)
            if not csrftoken:
                raise RuntimeError("在 auth.json 的 cookies 中找不到 csrftoken。")

            # 準備在瀏覽器內核中執行的 JavaScript fetch 腳本
            js_script = f"""
            async () => {{
                const doc_id = '7428920450586442';
                const variables = {{ 'code': '{post_code}', 'surface': 'WEB_POST' }};
                const url = `https://www.threads.net/api/graphql?doc_id=${{doc_id}}`;
                
                const response = await fetch(url, {{
                    method: 'POST',
                    headers: {{
                        'Accept': '*/*',
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'X-IG-App-ID': '238260118697367',
                        'X-ASBD-ID': '129477',
                        'X-IG-WWW-Claim': '0',
                        'X-CSRFToken': '{csrftoken}'
                    }},
                    body: `variables=${{encodeURIComponent(JSON.stringify(variables))}}`
                }});
                
                if (!response.ok) {{
                    throw new Error(`HTTP 錯誤! 狀態: ${{response.status}}`);
                }}
                return response.json();
            }}
            """
            
            data = await page.evaluate(js_script)
            post = data["data"]["containing_thread"]["thread_items"][0]["post"]
            return (
                post.get("video_info", {}).get("play_count") or
                post.get("feedback_info", {}).get("view_count") or 0
            )
        except Exception as e:
            print(f"❌ 獲取或解析貼文 {post_code} 失敗: {e}")
            return 0
        finally:
            await context.close()

    async def close(self):
        """關閉瀏覽器和 Playwright 實例"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        print("🚪 瀏覽器已關閉。")


# ------------ Demo ------------
async def demo():
    """執行範例測試"""
    print("🚀 Playwright 內核 API 請求策略測試開始...")
    
    auth_file = get_auth_file_path()
    if not auth_file.exists():
        print(f"❌ 錯誤: 找不到認證檔案 {auth_file}。請先執行 save_auth.py。")
        return

    client = PlaywrightAPIClient(auth_file)
    await client.launch()
    
    test_codes = {
        "萬": "DMxwLDUy4JD",
        "多": "DMyvZJRz5Cz",
        "少": "DMwKpQlThM8",
    }
    
    tasks = [client.get_views(code) for code in test_codes.values()]
    results = await asyncio.gather(*tasks)

    print("\n--- 測試結果 ---")
    for label, views in zip(test_codes.keys(), results):
        status = "✅" if views > 0 else "❌"
        print(f"{status} {label} ({test_codes[label]}): {views:,} 次瀏覽")

    await client.close()
    print("\n✅ 測試完成。")

if __name__ == "__main__":
    asyncio.run(demo())
