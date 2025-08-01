import sys, asyncio
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import json
import random
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright

# --- 設定路徑 ---
try:
    PROJECT_ROOT = Path(__file__).resolve().parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from common.config import get_auth_file_path
except ImportError:
    def get_auth_file_path():
        return Path("agents/playwright_crawler/auth.json")

# --- 測試設定 ---
TARGET_USERNAME = "wuyiju28"  # 要爬取的使用者名稱
MAX_POSTS_TO_FETCH = 2       # 要爬取的貼文數量（先測試少量）

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " \
     "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

def parse_views_text(text: str) -> int:
    """將 '串文 6,803次瀏覽' 或 '1,234 views' 轉換為整數"""
    import re
    if not text:
        return 0
    
    # 移除不必要的文字，保留數字和單位
    text = re.sub(r'串文\s*', '', text)  # 移除 "串文"
    
    # 處理中文格式：1.2萬、4 萬次瀏覽、5000次瀏覽
    if '萬' in text:
        match = re.search(r'([\d.]+)\s*萬', text)  # 允許數字和萬之間有空格
        if match:
            return int(float(match.group(1)) * 10000)
    elif '億' in text:
        match = re.search(r'([\d.]+)\s*億', text)  # 允許數字和億之間有空格
        if match:
            return int(float(match.group(1)) * 100000000)
    
    # 處理英文格式：1.2M views, 500K views
    text_upper = text.upper()
    if 'M' in text_upper:
        match = re.search(r'([\d.]+)M', text_upper)
        if match:
            return int(float(match.group(1)) * 1000000)
    elif 'K' in text_upper:
        match = re.search(r'([\d.]+)K', text_upper)
        if match:
            return int(float(match.group(1)) * 1000)
    
    # 處理純數字格式（可能包含逗號）
    match = re.search(r'[\d,]+', text)
    if match:
        return int(match.group().replace(',', ''))
    
    return 0

async def extract_post_views(page, post_url: str) -> dict:
    """提取單個貼文的瀏覽數和基本資訊"""
    try:
        print(f"📄 正在處理: {post_url}")
        
        # 導航到貼文頁面
        await page.goto(post_url, wait_until="networkidle", timeout=30000)
        
        # 檢查頁面是否正確載入（但不要直接跳過 Gate 頁面）
        page_content = await page.content()
        is_gate_page = "__NEXT_DATA__" not in page_content
        if is_gate_page:
            print(f"   ⚠️ 檢測到訪客 Gate 頁面，但仍嘗試提取基本數據...")
        
        # 方法 1: 嘗試攔截 GraphQL API 回應（只在非 Gate 頁面時）
        views_count = 0
        if not is_gate_page:
            try:
                response = await page.wait_for_response(
                    lambda r: "containing_thread" in r.url and r.status == 200, 
                    timeout=8000
                )
                data = await response.json()
                thread_items = data["data"]["containing_thread"]["thread_items"]
                post_data = thread_items[0]["post"]
                views_count = (post_data.get("feedback_info", {}).get("view_count") or
                              post_data.get("video_info", {}).get("play_count") or 0)
                
                if views_count > 0:
                    print(f"   ✅ GraphQL API 獲取瀏覽數: {views_count:,}")
                    return {
                        "url": post_url,
                        "views_count": views_count,
                        "extraction_method": "graphql_api",
                        "status": "success"
                    }
            except Exception as e:
                print(f"   ⚠️ GraphQL 攔截失敗: {str(e)[:100]}...")
        else:
            print("   ⚠️ Gate 頁面無法攔截 GraphQL，直接嘗試 DOM 選擇器...")
        
        # 方法 2: DOM 選擇器策略
        selectors = [
            "a:has-text(' 次瀏覽'), a:has-text(' views')",
            "*:has-text('次瀏覽'), *:has-text('views')",
            "span:has-text('次瀏覽'), span:has-text('views')",
            "text=/\\d+.*次瀏覽/, text=/\\d+.*views?/",
        ]
        
        for i, sel in enumerate(selectors):
            try:
                element = await page.wait_for_selector(sel, timeout=3000)
                text = await element.inner_text()
                views_count = parse_views_text(text)
                
                if views_count > 0:
                    print(f"   ✅ DOM 選擇器獲取瀏覽數: {views_count:,} (選擇器 {i+1})")
                    return {
                        "url": post_url,
                        "views_count": views_count,
                        "extraction_method": f"dom_selector_{i+1}",
                        "raw_text": text.strip(),
                        "status": "success"
                    }
            except:
                continue
        
        print(f"   ❌ 所有方法都失敗，無法獲取瀏覽數")
        return {
            "url": post_url,
            "views_count": 0,
            "extraction_method": "gate_page" if is_gate_page else "failed",
            "is_gate_page": is_gate_page,
            "status": "failed"
        }
        
    except Exception as e:
        print(f"   ❌ 處理貼文時發生錯誤: {e}")
        return {
            "url": post_url,
            "views_count": 0,
            "extraction_method": "error",
            "error": str(e),
            "status": "error"
        }

async def get_user_posts_urls(page, username: str, max_posts: int) -> list:
    """獲取用戶的貼文 URLs"""
    user_url = f"https://www.threads.com/@{username}"
    print(f"🔍 正在獲取 @{username} 的貼文 URLs...")
    
    await page.goto(user_url, wait_until="networkidle")
    
    # 等待貼文載入並滾動以載入更多
    await asyncio.sleep(3)
    
    # 滾動幾次以載入更多貼文
    for i in range(3):
        await page.mouse.wheel(0, 1000)
        await asyncio.sleep(2)
    
    # 提取貼文 URLs
    post_urls = await page.evaluate("""
        () => {
            const links = Array.from(document.querySelectorAll('a[href*="/post/"]'));
            const urls = links.map(link => link.href).filter(url => url.includes('/post/'));
            // 去重
            return [...new Set(urls)];
        }
    """)
    
    # 限制數量
    post_urls = post_urls[:max_posts]
    print(f"   ✅ 找到 {len(post_urls)} 個貼文 URLs")
    
    return post_urls

async def main():
    """主函數：爬取指定用戶的貼文瀏覽數"""
    auth_file = get_auth_file_path()
    if not auth_file.exists():
        print(f"❌ 找不到認證檔案: {auth_file}")
        print("   請先執行: python agents/playwright_crawler/save_auth.py")
        return

    print(f"🚀 開始爬取 @{TARGET_USERNAME} 的貼文瀏覽數")
    print(f"   目標數量: {MAX_POSTS_TO_FETCH}")
    print(f"   認證檔案: {auth_file}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)  # 使用無頭模式
        ctx = await browser.new_context(
            storage_state=str(auth_file),
            user_agent=UA,
            bypass_csp=True,
            locale="zh-TW",
        )
        await ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

        page = await ctx.new_page()
        
        try:
            # 步驟 0: 先訪問 Threads 首頁建立會話
            print("🏠 正在訪問 Threads 首頁建立會話...")
            await page.goto("https://www.threads.com/", wait_until="networkidle")
            
            # 檢查是否成功登入（但不要因此停止，因為個別貼文仍可能提取到數據）
            page_content = await page.content()
            if "__NEXT_DATA__" not in page_content:
                print("⚠️ 首頁顯示為訪客模式，但仍嘗試處理個別貼文")
                print("   提示：如果所有貼文都失敗，請重新執行: python agents/playwright_crawler/save_auth.py")
            else:
                print("✅ 首頁認證成功")
            
            # 短暫暖身
            await page.mouse.wheel(0, 500)
            await asyncio.sleep(2)
            
            # 步驟 1: 獲取貼文 URLs
            post_urls = await get_user_posts_urls(page, TARGET_USERNAME, MAX_POSTS_TO_FETCH)
            
            if not post_urls:
                print("❌ 沒有找到任何貼文 URLs")
                return
            
            # 步驟 2: 提取每個貼文的瀏覽數
            results = []
            successful_count = 0
            gate_page_count = 0
            
            for i, post_url in enumerate(post_urls, 1):
                print(f"\n--- 處理貼文 {i}/{len(post_urls)} ---")
                
                result = await extract_post_views(page, post_url)
                if result:
                    results.append(result)
                    if result.get("views_count", 0) > 0:
                        successful_count += 1
                        # 重置 gate_page_count 如果成功獲取數據
                        gate_page_count = 0
                    elif result.get("status") == "failed" and result.get("extraction_method") == "gate_page":
                        # Gate 頁面但沒有獲取到數據
                        gate_page_count += 1
                        print(f"   ⚠️ Gate 頁面無法獲取數據 ({gate_page_count}/3)")
                        
                        # 如果連續遇到太多無數據的 Gate 頁面，才重新建立會話
                        if gate_page_count >= 3:
                            print("🔄 連續無法從 Gate 頁面獲取數據，重新建立會話...")
                            await page.goto("https://www.threads.com/", wait_until="networkidle")
                            await asyncio.sleep(3)
                            gate_page_count = 0
                
                # 更長的隨機延遲避免觸發反爬蟲
                delay = random.uniform(3, 6)
                print(f"   ⏱️ 等待 {delay:.1f} 秒...")
                await asyncio.sleep(delay)
            
            # 步驟 3: 整理結果並保存
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"post_views_results_{TARGET_USERNAME}_{timestamp}.json"
            
            final_results = {
                "username": TARGET_USERNAME,
                "timestamp": timestamp,
                "total_posts_found": len(post_urls),
                "total_posts_processed": len(results),
                "successful_extractions": successful_count,
                "posts": results
            }
            
            # 保存結果
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(final_results, f, ensure_ascii=False, indent=2)
            
            # 顯示摘要
            print(f"\n{'='*50}")
            print(f"🎉 爬取完成！")
            print(f"   處理貼文: {len(results)}/{len(post_urls)}")
            print(f"   成功提取: {successful_count}")
            print(f"   結果已保存至: {output_file}")
            
            # 顯示前幾個結果
            print(f"\n--- 前 3 個結果預覽 ---")
            for i, result in enumerate(results[:3], 1):
                status_icon = "✅" if result.get("views_count", 0) > 0 else "❌"
                print(f"{i}. {status_icon} 瀏覽數: {result.get('views_count', 0):,}")
                print(f"   URL: {result.get('url', 'N/A')}")
                print(f"   方法: {result.get('extraction_method', 'N/A')}")
                if result.get('raw_text'):
                    print(f"   原始文字: '{result['raw_text']}'")
                print()
            
        except Exception as e:
            print(f"❌ 執行過程中發生錯誤: {e}")
        finally:
            await browser.close()
            print("🚪 瀏覽器已關閉")

if __name__ == "__main__":
    asyncio.run(main())