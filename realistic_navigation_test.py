"""
真實導航測試 - 模擬用戶行為：首頁 > 用戶頁面 > 貼文
"""

import asyncio
from pathlib import Path
from datetime import datetime
import sys
sys.path.append(str(Path(__file__).parent))

from playwright.async_api import async_playwright
from common.config import get_auth_file_path

# 測試目標
USERNAME = "netflixtw"
POST_ID = "DM_9ebSBlTh"

async def realistic_navigation():
    """模擬真實用戶導航路徑"""
    print("🧭 真實導航測試 - 模擬用戶行為")
    print(f"🎯 目標用戶: @{USERNAME}")
    print(f"🎯 目標貼文: {POST_ID}")
    
    auth_file_path = get_auth_file_path()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    async with async_playwright() as p:
        # 使用更真實的瀏覽器設定
        browser = await p.chromium.launch(
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-first-run',
                '--disable-extensions-except',
                '--disable-plugins-except',
                '--disable-default-apps',
                '--disable-dev-shm-usage',
                '--no-sandbox'
            ]
        )
        
        context = await browser.new_context(
            storage_state=str(auth_file_path),
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        page = await context.new_page()
        
        try:
            # 步驟1: 訪問首頁
            print("\n📍 步驟 1: 訪問 Threads 首頁")
            await page.goto("https://www.threads.net/", wait_until="networkidle", timeout=30000)
            await asyncio.sleep(3)
            print("   ✅ 首頁載入完成")
            
            # 步驟2: 搜索或導航到用戶頁面
            print(f"\n📍 步驟 2: 導航到用戶頁面 @{USERNAME}")
            user_url = f"https://www.threads.net/@{USERNAME}"
            await page.goto(user_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(3)
            
            title = await page.title()
            print(f"   📄 用戶頁面標題: '{title}'")
            
            # 嘗試找到貼文連結
            print(f"\n📍 步驟 3: 尋找目標貼文 {POST_ID}")
            
            # 多種方式尋找貼文
            post_selectors = [
                f'a[href*="{POST_ID}"]',
                f'a[href*="post/{POST_ID}"]',
                f'a[href*="@{USERNAME}/post/{POST_ID}"]',
                'article a',
                '[data-testid*="post"] a'
            ]
            
            post_found = False
            for selector in post_selectors:
                try:
                    links = await page.locator(selector).all()
                    for link in links:
                        href = await link.get_attribute('href')
                        if href and POST_ID in href:
                            print(f"   🔗 找到貼文連結: {href}")
                            await link.click()
                            post_found = True
                            break
                except:
                    continue
                if post_found:
                    break
            
            if not post_found:
                # 如果找不到，直接導航到貼文
                print("   ⚠️ 未找到貼文連結，直接導航")
                post_url = f"https://www.threads.net/@{USERNAME}/post/{POST_ID}"
                await page.goto(post_url, wait_until="networkidle", timeout=30000)
            
            await asyncio.sleep(5)  # 等待貼文完全載入
            
            # 步驟4: 分析貼文頁面
            print(f"\n📍 步驟 4: 分析貼文頁面")
            
            title = await page.title()
            print(f"   📄 貼文標題: '{title}'")
            
            # 等待互動元素載入
            print("   ⏰ 等待互動元素載入...")
            await asyncio.sleep(3)
            
            # 滾動一下確保元素可見
            await page.mouse.wheel(0, 300)
            await asyncio.sleep(2)
            
            # 尋找互動數據
            print("   🔢 搜索互動數據...")
            
            interaction_data = {}
            
            # 更精確的選擇器
            selectors = {
                'likes': [
                    'button[aria-label*="讚"] span',
                    'svg[aria-label="讚"] ~ span',
                    'button:has([aria-label="讚"]) span',
                    'span:has-text("讚")',
                ],
                'comments': [
                    'button[aria-label*="留言"] span',
                    'svg[aria-label="留言"] ~ span', 
                    'button:has([aria-label="留言"]) span',
                    'span:has-text("則留言")',
                    'a[href*="#comments"] span',
                ],
                'reposts': [
                    'button[aria-label*="轉發"] span',
                    'svg[aria-label="轉發"] ~ span',
                    'button:has([aria-label="轉發"]) span',
                    'span:has-text("次轉發")',
                ],
                'shares': [
                    'button[aria-label*="分享"] span',
                    'svg[aria-label="分享"] ~ span',
                    'button:has([aria-label="分享"]) span',
                    'span:has-text("次分享")',
                ]
            }
            
            for interaction_type, type_selectors in selectors.items():
                print(f"     🔍 搜索 {interaction_type}...")
                for selector in type_selectors:
                    try:
                        elements = await page.locator(selector).all()
                        for element in elements:
                            if await element.is_visible():
                                text = await element.inner_text()
                                if text and text.strip() and any(char.isdigit() for char in text):
                                    interaction_data[interaction_type] = text.strip()
                                    print(f"       ✅ 找到 {interaction_type}: {text.strip()}")
                                    break
                    except:
                        continue
                    if interaction_type in interaction_data:
                        break
            
            # 顯示結果
            print(f"\n🎯 互動數據結果:")
            if interaction_data:
                for key, value in interaction_data.items():
                    print(f"   {key}: {value}")
            else:
                print("   ❌ 未找到任何互動數據")
            
            # 額外嘗試：搜索任何包含數字的元素
            print(f"\n🔍 通用數字搜索...")
            try:
                # 搜索頁面上所有包含數字的元素
                all_elements = await page.locator('*').all()
                found_numbers = []
                
                for element in all_elements:
                    try:
                        if await element.is_visible():
                            text = await element.inner_text()
                            if text and len(text.strip()) < 50 and any(char.isdigit() for char in text):
                                found_numbers.append(text.strip())
                    except:
                        continue
                    
                    # 限制搜索數量避免太慢
                    if len(found_numbers) > 50:
                        break
                
                # 去重並顯示
                unique_numbers = list(set(found_numbers))
                if unique_numbers:
                    print(f"   📊 找到的數字元素 (前20個): {unique_numbers[:20]}")
                else:
                    print("   ❌ 完全沒有找到數字元素")
                    
            except Exception as e:
                print(f"   ❌ 通用搜索失敗: {e}")
            
            # 保存證據
            html_file = f"realistic_nav_{timestamp}.html"
            html_content = await page.content()
            Path(html_file).write_text(html_content, encoding='utf-8')
            print(f"\n💾 HTML已保存: {html_file}")
            
            screenshot_file = f"realistic_nav_{timestamp}.png"
            await page.screenshot(path=screenshot_file, full_page=True)
            print(f"📸 截圖已保存: {screenshot_file}")
            
        except Exception as e:
            print(f"❌ 測試失敗: {e}")
            
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(realistic_navigation())