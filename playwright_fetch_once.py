# playwright_fetch_once.py
import sys, asyncio
if sys.platform.startswith("win"):          # ★ 一定要在最前面
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import random, os
from pathlib import Path

from playwright.async_api import async_playwright

# --- 設定路徑 ---
try:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from common.config import get_auth_file_path
except ImportError:
    # 為了能獨立執行，提供一個備用路徑方案
    def get_auth_file_path():
        return Path("agents/playwright_crawler/auth.json")

HOME  = "https://www.threads.com/"                      # ← 使用新的 .com 域名
POST_URL = "https://www.threads.com/@wuyiju28/post/DMyvZJRz5Cz"  # ← 完整 URL
UA    = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "\
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

async def main():
    auth = get_auth_file_path()
    if not auth.exists():
        print("沒有 auth.json，先跑 save_auth.py")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            storage_state=str(auth),
            user_agent=UA,
            bypass_csp=True,                 # ← 解掉 TrustedHTML
            locale="zh-TW",
        )
        await ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

        page = await ctx.new_page()

        # ① 直接導航到貼文頁面
        print(f"🏠 直接前往貼文頁面: {POST_URL}")
        await page.goto(POST_URL, wait_until="networkidle")
        print("✅ 頁面載入完成")
        
        # 檢查頁面是否正確載入（不是 Gate 頁面）
        page_content = await page.content()
        if "__NEXT_DATA__" in page_content:
            print("✅ 檢測到完整的 Threads 頁面（包含 __NEXT_DATA__）")
            
            # ② 嘗試攔截 GraphQL API 回應獲取瀏覽數（最穩定的方法）
            print("🔍 嘗試攔截 GraphQL API 回應...")
            try:
                response = await page.wait_for_response(
                    lambda r: "containing_thread" in r.url and r.status == 200, 
                    timeout=10000
                )
                print("✅ 攔截到 GraphQL 回應")
                data = await response.json()
                
                # 解析瀏覽數
                try:
                    thread_items = data["data"]["containing_thread"]["thread_items"]
                    post_data = thread_items[0]["post"]
                    views = (post_data.get("feedback_info", {}).get("view_count") or
                            post_data.get("video_info", {}).get("play_count") or 0)
                    
                    print(f"🎉 成功從 GraphQL API 獲取瀏覽數: {views:,}")
                    return  # 成功獲取，直接結束
                except (KeyError, IndexError, TypeError) as e:
                    print(f"⚠️ GraphQL 回應解析失敗: {e}")
                    print("   -> 繼續嘗試 DOM 選擇器方法...")
                    
            except Exception as e:
                print(f"⚠️ GraphQL 攔截失敗: {e}")
                print("   -> 繼續嘗試 DOM 選擇器方法...")
        else:
            print("⚠️ 這似乎是訪客 Gate 頁面，可能需要重新認證")
            # 儲存截圖以供除錯
            await page.screenshot(path="debug_gate_page.png", full_page=True)
            print("   -> 已儲存 Gate 頁面截圖: debug_gate_page.png")

        # ⑤ 嘗試多種選擇器策略找瀏覽數
        selectors = [
            "a:has-text(' 次瀏覽'), a:has-text(' views')",  # 原始策略
            "*:has-text('次瀏覽'), *:has-text('views')",    # 任何元素
            "span:has-text('次瀏覽'), span:has-text('views')", # span 元素
            "[aria-label*='瀏覽'], [aria-label*='view']",     # aria-label 屬性
            "text=/\\d+.*次瀏覽/, text=/\\d+.*views?/",       # 正則表達式
        ]
        
        element = None
        successful_selector = None
        
        for i, sel in enumerate(selectors):
            print(f"🔍 嘗試選擇器 {i+1}/{len(selectors)}: {sel}")
            try:
                element = await page.wait_for_selector(sel, timeout=3000)
                successful_selector = sel
                print(f"✅ 找到元素！使用選擇器: {sel}")
                break
            except Exception as e:
                print(f"   ❌ 失敗: {str(e)[:100]}...")
                continue
        
        if element:
            text = await element.inner_text()
            print("👀 原始文字:", text.replace("\n", " "))
        else:
            print("❌ 所有選擇器都失敗了")
            # 儲存完整 HTML 以供除錯
            html_dump = await page.content()
            Path("debug.html").write_text(html_dump, encoding="utf-8")
            print("   -> 已把完整 HTML 寫到 debug.html，請打開確認 view 字樣。")
            # 同時儲存截圖
            await page.screenshot(path="debug_render.png", full_page=True)
            print("   -> 已儲存截圖: debug_render.png")
            
            # 搜尋頁面中所有包含 "瀏覽" 或 "view" 的文字
            print("🔍 搜尋頁面中所有相關文字...")
            view_texts = await page.evaluate("""
                () => {
                    const walker = document.createTreeWalker(
                        document.body,
                        NodeFilter.SHOW_TEXT,
                        null,
                        false
                    );
                    const results = [];
                    let node;
                    while (node = walker.nextNode()) {
                        const text = node.textContent.trim();
                        if (text && (text.includes('瀏覽') || text.toLowerCase().includes('view'))) {
                            results.push(text);
                        }
                    }
                    return results;
                }
            """)
            if view_texts:
                print("   找到的相關文字:")
                for text in view_texts[:10]:  # 只顯示前10個
                    print(f"     -> '{text}'")
            else:
                print("   ❌ 頁面中沒有找到任何包含 '瀏覽' 或 'view' 的文字")


        await browser.close()
        print("🚪 瀏覽器已關閉。")

if __name__ == "__main__":
    asyncio.run(main())                     # 不要再 new_event_loop()
