#!/usr/bin/env python3
"""
測試媒體URL、標籤等提取結果
"""

import asyncio
import json
from datetime import datetime, timezone
from agents.playwright_crawler.extractors.details_extractor import DetailsExtractor
from common.models import PostMetrics

async def test_media_extraction():
    print("🧪 測試媒體和其他欄位提取...")
    
    # 測試有媒體內容的貼文，比較兩個域名
    urls_to_test = [
        "https://www.threads.com/@netflixtw/post/DM9mZctIU4B",  # .com 域名
        "https://www.threads.net/@netflixtw/post/DM9mZctIU4B",   # .net 域名  
    ]
    
    extractor = DetailsExtractor()
    results = {}
    
    # 測試兩個域名的差異
    for i, url in enumerate(urls_to_test):
        domain = ".com" if "threads.com" in url else ".net"
        print(f"\n{'='*60}")
        print(f"🧪 測試 {i+1}/{len(urls_to_test)}: {domain} 域名")
        print(f"🎯 URL: {url}")
        
        # 創建測試post
        test_post = PostMetrics(
            post_id=f"test_media_{domain.replace('.', '')}",
            username="netflixtw", 
            url=url,
            created_at=datetime.now(timezone.utc)
        )
        
        try:
            print(f"📊 初始數據: 圖片={len(test_post.images)}, 影片={len(test_post.videos)}, 標籤={test_post.tags}")
            
            # 執行提取
            from playwright.async_api import async_playwright
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=False)
                # 添加反指紋設置（基於技術報告）
                context = await browser.new_context(
                    bypass_csp=True,
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
                )
                
                # 隱藏webdriver屬性（基於技術報告）
                await context.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
                
                try:
                    filled_posts = await extractor.fill_post_details_from_page(
                        posts_to_fill=[test_post],
                        context=context,
                        task_id=f"test_media_{domain.replace('.', '')}", 
                        username="netflixtw"
                    )
                finally:
                    await browser.close()
        
            if filled_posts:
                result_post = filled_posts[0]
                
                # 存儲結果供後續比較
                results[domain] = {
                    "images": len(result_post.images),
                    "videos": len(result_post.videos), 
                    "tags": result_post.tags or [],
                    "views": result_post.views_count,
                    "likes": result_post.likes_count,
                    "comments": result_post.comments_count,
                    "reposts": result_post.reposts_count,
                    "shares": result_post.shares_count,
                    "post_published_at": result_post.post_published_at,
                    "content_length": len(result_post.content) if result_post.content else 0,
                    "calculated_score": result_post.calculated_score,
                    "image_urls": result_post.images[:2] if result_post.images else [],  # 前2個作為樣本
                    "video_urls": result_post.videos[:2] if result_post.videos else []   # 前2個作為樣本
                }
                
                print(f"🎉 {domain} 域名提取結果:")
                print(f"   🖼️ 圖片數量: {len(result_post.images)}")
                print(f"   🎬 影片數量: {len(result_post.videos)}")
                print(f"   🏷️ 標籤數量: {len(result_post.tags) if result_post.tags else 0}")
                print(f"   👁️ 瀏覽數: {result_post.views_count}")
                print(f"   ❤️ 按讚數: {result_post.likes_count}")
                print(f"   📊 計算分數: {result_post.calculated_score}")
                print(f"   📝 內容長度: {len(result_post.content) if result_post.content else 0} 字")
                
                if result_post.images:
                    print(f"   🖼️ 圖片URL樣本:")
                    for i, img_url in enumerate(result_post.images[:2]):
                        print(f"      {i+1}. {img_url[:70]}...")
                
                if result_post.videos:
                    print(f"   🎬 影片URL樣本:")
                    for i, video_url in enumerate(result_post.videos[:2]):
                        print(f"      {i+1}. {video_url[:70]}...")
            
            else:
                print(f"❌ {domain} 域名提取失敗")
                results[domain] = None
                
        except Exception as e:
            print(f"❌ {domain} 域名錯誤: {e}")
            results[domain] = None
    
    # 比較兩個域名的結果
    print(f"\n{'='*80}")
    print("🔍 域名比較分析:")
    print(f"{'='*80}")
    
    if results.get(".com") and results.get(".net"):
        com_result = results[".com"]
        net_result = results[".net"]
        
        comparisons = [
            ("圖片數量", com_result["images"], net_result["images"]),
            ("影片數量", com_result["videos"], net_result["videos"]),
            ("標籤數量", len(com_result["tags"]), len(net_result["tags"])),
            ("瀏覽數", com_result["views"], net_result["views"]),
            ("按讚數", com_result["likes"], net_result["likes"]),
            ("留言數", com_result["comments"], net_result["comments"]),
            ("計算分數", com_result["calculated_score"], net_result["calculated_score"]),
        ]
        
        print(f"{'欄位':<10} {'threads.com':<15} {'threads.net':<15} {'差異':<10}")
        print("-" * 60)
        
        for field, com_val, net_val in comparisons:
            diff = "✅ 相同" if com_val == net_val else f"❌ 不同"
            print(f"{field:<10} {str(com_val):<15} {str(net_val):<15} {diff}")
        
        # 重點分析
        print(f"\n📊 關鍵發現:")
        if com_result["images"] != net_result["images"]:
            print(f"   🖼️ 圖片數量差異: .com={com_result['images']}, .net={net_result['images']}")
        if com_result["videos"] != net_result["videos"]:
            print(f"   🎬 影片數量差異: .com={com_result['videos']}, .net={net_result['videos']}")
        if com_result["views"] != net_result["views"]:
            print(f"   👁️ 瀏覽數差異: .com={com_result['views']}, .net={net_result['views']}")
            
        # 推薦域名
        if com_result["images"] > 0 or com_result["videos"] > 0:
            print(f"   ✅ 建議使用 threads.com 域名 (媒體內容更豐富)")
        elif net_result["images"] > 0 or net_result["videos"] > 0:
            print(f"   ✅ 建議使用 threads.net 域名 (媒體內容更豐富)")
        else:
            print(f"   ⚠️ 兩個域名都沒有媒體內容")
    
    else:
        print("❌ 無法比較：部分域名提取失敗")

if __name__ == "__main__":
    asyncio.run(test_media_extraction())