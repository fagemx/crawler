"""
增強版頁面測試 - 嘗試繞過登入覆蓋層
"""

import asyncio
from pathlib import Path
from datetime import datetime
import sys
sys.path.append(str(Path(__file__).parent))

from playwright.async_api import async_playwright
from common.config import get_auth_file_path

# 測試URL
TEST_URL = "https://www.threads.com/@netflixtw/post/DM_9ebSBlTh"

async def enhanced_page_test():
    """增強版頁面測試，嘗試多種方法繞過登入覆蓋層"""
    print("🧪 增強版頁面測試")
    print(f"🎯 目標: {TEST_URL}")
    
    auth_file_path = get_auth_file_path()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    async with async_playwright() as p:
        # 嘗試非headless模式（更難被檢測）
        browser = await p.chromium.launch(
            headless=False,  # 非headless模式
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-first-run',
                '--disable-extensions-except',
                '--disable-plugins-except',
                '--disable-default-apps'
            ]
        )
        
        context = await browser.new_context(
            storage_state=str(auth_file_path),
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        page = await context.new_page()
        
        try:
            print("   🌐 導航到測試頁面...")
            await page.goto(TEST_URL, wait_until="networkidle", timeout=30000)
            
            print("   ⏰ 等待5秒讓頁面完全載入...")
            await asyncio.sleep(5)
            
            # 檢查是否有登入覆蓋層
            print("   🔍 檢查登入覆蓋層...")
            login_overlays = [
                '[data-testid*="login"]',
                '[aria-label*="Log in"]', 
                '[aria-label*="登入"]',
                'div:has-text("Log in")',
                'div:has-text("登入")',
                '[class*="login"]',
                '[class*="Login"]'
            ]
            
            found_overlay = False
            for selector in login_overlays:
                try:
                    element = await page.locator(selector).first
                    if await element.is_visible():
                        print(f"   ⚠️ 發現登入覆蓋層: {selector}")
                        found_overlay = True
                        break
                except:
                    continue
            
            if not found_overlay:
                print("   ✅ 沒有發現登入覆蓋層")
            
            # 嘗試點擊關閉按鈕
            print("   🔘 嘗試關閉彈窗...")
            close_selectors = [
                '[aria-label*="Close"]',
                '[aria-label*="關閉"]', 
                '[data-testid*="close"]',
                'button:has-text("×")',
                'button[aria-label*="dismiss"]'
            ]
            
            for selector in close_selectors:
                try:
                    element = await page.locator(selector).first
                    if await element.is_visible():
                        await element.click()
                        print(f"   ✅ 成功點擊關閉按鈕: {selector}")
                        await asyncio.sleep(2)
                        break
                except:
                    continue
            
            # 嘗試按ESC鍵
            print("   ⌨️ 嘗試按ESC鍵...")
            await page.keyboard.press('Escape')
            await asyncio.sleep(2)
            
            # 檢查頁面標題
            title = await page.title()
            print(f"   📄 頁面標題: '{title}'")
            
            # 尋找數字元素
            print("   🔢 搜索數字元素...")
            try:
                # 專門搜索互動數據
                interaction_selectors = [
                    'span:has-text("讚")',
                    'span:has-text("則留言")',
                    'span:has-text("次轉發")',
                    'span:has-text("次分享")',
                    '[aria-label*="讚"]',
                    '[aria-label*="留言"]',
                    '[aria-label*="轉發"]',
                    '[aria-label*="分享"]',
                    'span:text-matches(r"\\d+")',  # 任何包含數字的span
                ]
                
                found_numbers = []
                for selector in interaction_selectors:
                    try:
                        elements = await page.locator(selector).all()
                        for element in elements:
                            text = await element.inner_text()
                            if text and any(char.isdigit() for char in text):
                                found_numbers.append(text.strip())
                    except:
                        continue
                
                if found_numbers:
                    print(f"   🎯 找到數字元素: {found_numbers[:10]}")  # 只顯示前10個
                else:
                    print("   ❌ 未找到任何數字元素")
                
                # 保存現在的狀態
                html_file = f"enhanced_test_{timestamp}.html"
                html_content = await page.locator('html').inner_html()
                Path(html_file).write_text(html_content, encoding='utf-8')
                print(f"   💾 HTML已保存: {html_file}")
                
                # 截圖
                screenshot_file = f"enhanced_test_{timestamp}.png"
                await page.screenshot(path=screenshot_file, full_page=True)
                print(f"   📸 截圖已保存: {screenshot_file}")
                
            except Exception as e:
                print(f"   ❌ 數字搜索失敗: {e}")
                
        except Exception as e:
            print(f"   ❌ 頁面訪問失敗: {e}")
            
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(enhanced_page_test())