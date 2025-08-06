"""
攔截所有 GraphQL 請求，尋找內容相關的查詢
"""

import asyncio
import json
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List

import sys
sys.path.append(str(Path(__file__).parent))

from playwright.async_api import async_playwright
from common.config import get_auth_file_path

# 使用一個更穩定的測試目標（例如 Threads 官方帳號）
TEST_URL = "https://www.threads.net/@threads/post/DMxtXaggxsL"

async def intercept_all_graphql_requests():
    """攔截所有 GraphQL 請求"""
    print("🔍 攔截所有 GraphQL 請求...")
    
    auth_file_path = get_auth_file_path()
    
    all_requests = []
    all_responses = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # 設為 False 便於觀察
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
        )
        
        context = await browser.new_context(
            storage_state=str(auth_file_path),
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            viewport={"width": 375, "height": 812},
            locale="zh-TW",
            bypass_csp=True
        )
        
        await context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
        
        page = await context.new_page()
        
        # 攔截所有請求
        async def request_handler(request):
            url = request.url.lower()
            if "/graphql" in url:
                qname = request.headers.get("x-fb-friendly-name", "Unknown")
                all_requests.append({
                    "url": request.url,
                    "method": request.method,
                    "query_name": qname,
                    "headers": dict(request.headers),
                    "post_data": request.post_data if request.method == "POST" else None,
                    "timestamp": datetime.now().isoformat()
                })
                print(f"   📤 發送: {qname}")
        
        # 攔截所有響應
        async def response_handler(response):
            url = response.url.lower()
            if "/graphql" in url and response.status == 200:
                qname = response.request.headers.get("x-fb-friendly-name", "Unknown")
                try:
                    data = await response.json()
                    all_responses.append({
                        "url": response.url,
                        "query_name": qname,
                        "data": data,
                        "timestamp": datetime.now().isoformat(),
                        "request_headers": dict(response.request.headers)
                    })
                    
                    # 快速分析響應內容
                    content_indicators = []
                    
                    if "data" in data and data["data"]:
                        data_obj = data["data"]
                        
                        # 檢查是否包含媒體內容
                        if "media" in data_obj:
                            content_indicators.append("has_media")
                        if "containing_thread" in data_obj:
                            content_indicators.append("has_thread")
                        if any("text" in str(data_obj).lower() and len(str(data_obj)) > 1000 for _ in [1]):
                            content_indicators.append("has_long_text")
                        if "caption" in str(data_obj):
                            content_indicators.append("has_caption")
                        if "image_versions" in str(data_obj):
                            content_indicators.append("has_images")
                        if "video_versions" in str(data_obj):
                            content_indicators.append("has_videos")
                    
                    indicator_text = ", ".join(content_indicators) if content_indicators else "no_content"
                    print(f"   📥 響應: {qname} ({indicator_text})")
                    
                    # 如果看起來像內容響應，保存詳細信息
                    if any(indicator in content_indicators for indicator in ["has_media", "has_caption", "has_images", "has_videos"]):
                        print(f"      🎯 可能的內容響應！")
                        debug_file = Path(f"potential_content_{qname}_{datetime.now().strftime('%H%M%S')}.json")
                        with open(debug_file, 'w', encoding='utf-8') as f:
                            json.dump({
                                "query_name": qname,
                                "request_post_data": response.request.post_data,
                                "response_data": data
                            }, f, indent=2, ensure_ascii=False)
                        print(f"      📁 已保存到: {debug_file}")
                    
                except Exception as e:
                    print(f"   ❌ 解析響應失敗: {e}")
        
        page.on("request", request_handler)
        page.on("response", response_handler)
        
        # 導航到頁面
        print(f"   🌐 導航到: {TEST_URL}")
        await page.goto(TEST_URL, wait_until="networkidle", timeout=60000)
        
        # 等待初始加載
        await asyncio.sleep(5)
        
        # 嘗試一些用戶操作來觸發更多請求
        print(f"   🖱️ 嘗試用戶操作...")
        
        # 滾動
        for i in range(3):
            await page.evaluate("window.scrollTo(0, window.scrollY + 300)")
            await asyncio.sleep(1)
        
        # 嘗試點擊一些元素（如果存在）
        try:
            # 嘗試點擊貼文展開
            more_button = page.locator('text="更多"').first
            if await more_button.count() > 0:
                await more_button.click()
                await asyncio.sleep(2)
        except:
            pass
        
        try:
            # 嘗試點擊留言區域
            comments_area = page.locator('[aria-label*="留言"], [aria-label*="comment"]').first
            if await comments_area.count() > 0:
                await comments_area.hover()
                await asyncio.sleep(2)
        except:
            pass
        
        # 最後等待
        await asyncio.sleep(3)
        
        await browser.close()
    
    # 分析結果
    print(f"\n📊 分析結果:")
    print(f"   📤 總請求數: {len(all_requests)}")
    print(f"   📥 總響應數: {len(all_responses)}")
    
    # 按查詢名稱分組
    query_names = {}
    for req in all_requests:
        qname = req["query_name"]
        if qname not in query_names:
            query_names[qname] = {"requests": 0, "responses": 0}
        query_names[qname]["requests"] += 1
    
    for resp in all_responses:
        qname = resp["query_name"]
        if qname in query_names:
            query_names[qname]["responses"] += 1
    
    print(f"\n📋 查詢統計:")
    for qname, stats in sorted(query_names.items()):
        print(f"   {qname}: {stats['requests']} 請求, {stats['responses']} 響應")
    
    # 嘗試從請求中提取 doc_id
    print(f"\n🔍 提取的 doc_id:")
    doc_ids = set()
    for req in all_requests:
        if req["post_data"]:
            try:
                # 嘗試從 POST 數據中提取 doc_id
                post_data = req["post_data"]
                if "doc_id=" in post_data:
                    match = re.search(r'doc_id=(\d+)', post_data)
                    if match:
                        doc_id = match.group(1)
                        doc_ids.add((doc_id, req["query_name"]))
            except:
                pass
    
    for doc_id, qname in sorted(doc_ids):
        print(f"   {doc_id} ({qname})")
    
    # 保存完整結果
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = Path(f"all_graphql_intercept_{timestamp}.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "test_url": TEST_URL,
            "requests": all_requests,
            "responses": all_responses,
            "query_statistics": query_names,
            "extracted_doc_ids": list(doc_ids)
        }, f, indent=2, ensure_ascii=False, default=str)
    
    print(f"\n📁 完整結果已保存至: {output_file}")
    
    return list(doc_ids)

async def main():
    """主函數"""
    doc_ids = await intercept_all_graphql_requests()
    
    if doc_ids:
        print(f"\n🎯 發現的 doc_id:")
        for doc_id, qname in doc_ids:
            print(f"   {doc_id} - {qname}")
        print(f"\n💡 請嘗試使用這些 doc_id 來獲取內容")
    else:
        print(f"\n😞 未發現新的 doc_id")

if __name__ == "__main__":
    asyncio.run(main())