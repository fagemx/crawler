"""
分析所有 GraphQL 查詢，找到真正的主貼文內容查詢
"""

import asyncio
import json
import urllib.parse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List

import sys
sys.path.append(str(Path(__file__).parent))

from playwright.async_api import async_playwright
from common.config import get_auth_file_path

# 測試貼文
TEST_POST_URL = "https://www.threads.com/@star_shining0828/post/DMyvZJRz5Cz"
TARGET_PK = "3689219480905289907"

async def analyze_all_graphql_queries():
    """分析所有 GraphQL 查詢並找到包含主貼文內容的查詢"""
    print("🔍 分析所有 GraphQL 查詢...")
    
    auth_file_path = get_auth_file_path()
    all_queries = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            storage_state=str(auth_file_path),
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15",
            viewport={"width": 375, "height": 812},
            locale="zh-TW"
        )
        
        page = await context.new_page()
        
        async def response_handler(response):
            url = response.url.lower()
            if "/graphql" in url and response.status == 200:
                friendly_name = response.request.headers.get("x-fb-friendly-name", "Unknown")
                root_field = response.request.headers.get("x-root-field-name", "")
                
                print(f"   📡 {friendly_name}")
                if root_field:
                    print(f"      🔍 Root field: {root_field}")
                
                try:
                    data = await response.json()
                    
                    # 分析響應結構
                    content_indicators = []
                    target_post_found = False
                    
                    if "data" in data and data["data"]:
                        # 檢查是否包含目標貼文
                        data_str = json.dumps(data, ensure_ascii=False)
                        if TARGET_PK in data_str:
                            target_post_found = True
                            content_indicators.append("HAS_TARGET_POST")
                        
                        # 檢查內容指標
                        if "media" in data["data"]:
                            content_indicators.append("has_media")
                        if "caption" in data_str:
                            content_indicators.append("has_caption")
                        if "image_versions" in data_str:
                            content_indicators.append("has_images")
                        if "video_versions" in data_str:
                            content_indicators.append("has_videos")
                        if "like_count" in data_str:
                            content_indicators.append("has_likes")
                        if "text_post_app_info" in data_str:
                            content_indicators.append("has_text_info")
                        if len(data_str) > 10000:
                            content_indicators.append("large_response")
                    
                    indicators_text = ", ".join(content_indicators) if content_indicators else "no_content"
                    print(f"      📊 指標: {indicators_text}")
                    
                    # 記錄查詢信息
                    query_info = {
                        "friendly_name": friendly_name,
                        "root_field": root_field,
                        "url": response.url,
                        "has_target_post": target_post_found,
                        "content_indicators": content_indicators,
                        "request_headers": dict(response.request.headers),
                        "request_data": response.request.post_data,
                        "response_size": len(json.dumps(data)) if data else 0,
                        "timestamp": datetime.now().isoformat()
                    }
                    
                    all_queries.append(query_info)
                    
                    # 如果找到目標貼文，詳細分析
                    if target_post_found:
                        print(f"      🎯 找到目標貼文！")
                        
                        # 保存完整響應
                        detail_file = Path(f"target_post_found_{friendly_name}_{datetime.now().strftime('%H%M%S')}.json")
                        with open(detail_file, 'w', encoding='utf-8') as f:
                            json.dump({
                                "query_info": query_info,
                                "full_response": data
                            }, f, indent=2, ensure_ascii=False)
                        print(f"      📁 詳細數據已保存: {detail_file}")
                
                except Exception as e:
                    print(f"      ❌ 解析失敗: {e}")
        
        page.on("response", response_handler)
        
        # 導航到頁面
        print(f"   🌐 導航到: {TEST_POST_URL}")
        await page.goto(TEST_POST_URL, wait_until="networkidle", timeout=60000)
        
        # 等待初始載入
        await asyncio.sleep(5)
        
        # 嘗試一些操作來觸發更多查詢
        print(f"   🖱️ 嘗試用戶操作...")
        
        # 滾動頁面
        await page.evaluate("window.scrollTo(0, 300)")
        await asyncio.sleep(2)
        
        # 嘗試點擊貼文區域
        try:
            # 點擊主貼文內容區域
            await page.click('article', timeout=5000)
            await asyncio.sleep(2)
        except:
            pass
        
        # 嘗試刷新頁面
        print(f"   🔄 刷新頁面...")
        await page.reload(wait_until="networkidle")
        await asyncio.sleep(5)
        
        # 再次滾動
        await page.evaluate("window.scrollTo(0, 600)")
        await asyncio.sleep(2)
        
        await browser.close()
    
    # 分析結果
    print(f"\n📊 分析結果:")
    print(f"   總查詢數: {len(all_queries)}")
    
    # 找到包含目標貼文的查詢
    target_queries = [q for q in all_queries if q["has_target_post"]]
    print(f"   包含目標貼文的查詢: {len(target_queries)}")
    
    if target_queries:
        print(f"\n🎯 包含目標貼文的查詢:")
        for i, query in enumerate(target_queries):
            print(f"   {i+1}. {query['friendly_name']}")
            print(f"      Root field: {query['root_field']}")
            print(f"      指標: {', '.join(query['content_indicators'])}")
            print(f"      響應大小: {query['response_size']:,} 字符")
    
    # 按查詢名稱分組統計
    query_stats = {}
    for query in all_queries:
        name = query["friendly_name"]
        if name not in query_stats:
            query_stats[name] = {"count": 0, "has_target": 0, "avg_size": 0}
        query_stats[name]["count"] += 1
        if query["has_target_post"]:
            query_stats[name]["has_target"] += 1
        query_stats[name]["avg_size"] += query["response_size"]
    
    for name, stats in query_stats.items():
        stats["avg_size"] = stats["avg_size"] // stats["count"] if stats["count"] > 0 else 0
    
    print(f"\n📋 查詢統計:")
    for name, stats in sorted(query_stats.items(), key=lambda x: x[1]["has_target"], reverse=True):
        print(f"   {name}:")
        print(f"      次數: {stats['count']}, 包含目標: {stats['has_target']}, 平均大小: {stats['avg_size']:,}")
    
    # 保存完整分析結果
    analysis_file = Path(f"graphql_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(analysis_file, 'w', encoding='utf-8') as f:
        json.dump({
            "test_url": TEST_POST_URL,
            "target_pk": TARGET_PK,
            "all_queries": all_queries,
            "summary": {
                "total_queries": len(all_queries),
                "target_queries_count": len(target_queries),
                "query_stats": query_stats
            }
        }, f, indent=2, ensure_ascii=False, default=str)
    
    print(f"\n📁 完整分析已保存: {analysis_file}")
    
    # 推薦最佳查詢
    if target_queries:
        # 選擇包含最多內容指標的查詢
        best_query = max(target_queries, key=lambda q: len(q["content_indicators"]))
        print(f"\n💡 推薦查詢: {best_query['friendly_name']}")
        print(f"   Root field: {best_query['root_field']}")
        print(f"   內容指標: {', '.join(best_query['content_indicators'])}")
        print(f"   響應大小: {best_query['response_size']:,} 字符")
        
        return best_query
    else:
        print(f"\n😞 未找到包含目標貼文的查詢")
        print(f"💡 可能需要:")
        print(f"   1. 檢查貼文 URL 是否正確")
        print(f"   2. 嘗試不同的用戶操作")
        print(f"   3. 檢查認證狀態")
        
        return None

async def main():
    """主函數"""
    auth_file = get_auth_file_path()
    if not auth_file.exists():
        print(f"❌ 認證檔案 {auth_file} 不存在。請先執行 save_auth.py。")
        return

    best_query = await analyze_all_graphql_queries()
    
    if best_query:
        print(f"\n🎉 分析完成！找到最佳查詢")
        print(f"💡 請使用這個查詢來獲取主貼文內容")
    else:
        print(f"\n😞 分析完成，但未找到合適的查詢")

if __name__ == "__main__":
    asyncio.run(main())