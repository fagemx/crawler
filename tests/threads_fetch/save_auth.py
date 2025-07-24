# save_auth.py ── 只跑一次就好
import asyncio, pathlib
from playwright.async_api import async_playwright

AUTH_FILE = pathlib.Path("auth.json")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)   # 打開真視窗
        ctx      = await browser.new_context()              # 全新乾淨 Context
        page     = await ctx.new_page()
        await page.goto("https://www.threads.com/login") # 直接導向 .com 的登入頁面

        print("👉 請手動登入 Threads / IG，完成二階段驗證後再關掉視窗")
        await page.pause()    # 登入完自行按 Resume

        await ctx.storage_state(path=AUTH_FILE)
        print("✅ 已寫入 auth.json，可供後續爬蟲使用")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main()) 