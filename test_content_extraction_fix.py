#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
測試修正後的內容提取邏輯
針對主貼文vs回覆的區分問題
"""

import sys
import asyncio
from scripts.realtime_crawler_extractor import RealtimeCrawlerExtractor

async def test_specific_post():
    """測試特定貼文的內容提取"""
    
    # 測試貼文：主文是 "關稅+台幣升值，傳產業者們「海嘯第一排」"
    # 而不是回覆內容 ">>>232條款恐怕衝擊高科技產品"
    test_url = "https://www.threads.com/@gvmonthly/post/DMzvu4MTpis"
    
    print("🧪 測試修正後的內容提取邏輯")
    print(f"📍 目標貼文: {test_url}")
    print(f"🎯 期望主文: 關稅+台幣升值，傳產業者們「海嘯第一排」")
    print(f"❌ 應該避免: >>>232條款恐怕衝擊高科技產品")
    print("=" * 60)
    
    # 創建提取器實例
    extractor = RealtimeCrawlerExtractor("gvmonthly", 1)
    
    # 測試Jina API提取
    print("\n🌐 測試Jina API提取...")
    success, content = await extractor.fetch_content_jina_api(test_url)
    
    if success:
        print(f"✅ Jina API成功獲取內容 ({len(content)} 字符)")
        
        # 提取主貼文內容
        main_content = extractor.extract_post_content(content)
        print(f"\n📝 提取到的主文內容:")
        print(f"   {main_content}")
        
        # 檢查是否正確
        if main_content:
            if "關稅+台幣升值" in main_content:
                print("\n✅ 成功！正確提取到主貼文內容")
            elif ">>>232條款" in main_content:
                print("\n❌ 失敗！仍然提取到回覆內容")
            else:
                print(f"\n⚠️ 提取到其他內容: {main_content}")
        else:
            print("\n❌ 沒有提取到任何內容")
            
        # 也提取其他數據進行驗證
        views = extractor.extract_views_count(content, "DMzvu4MTpis")
        likes = extractor.extract_likes_count(content)
        comments = extractor.extract_comments_count(content)
        
        print(f"\n📊 其他提取數據:")
        print(f"   👁️ 觀看數: {views}")
        print(f"   👍 按讚數: {likes}")
        print(f"   💬 留言數: {comments}")
        
    else:
        print(f"❌ Jina API提取失敗: {content}")
        
        # 嘗試本地Reader
        print("\n⚡ 嘗試本地Reader...")
        local_success, local_content = extractor.fetch_content_local(test_url)
        
        if local_success:
            print(f"✅ 本地Reader成功 ({len(local_content)} 字符)")
            main_content = extractor.extract_post_content(local_content)
            print(f"📝 本地提取內容: {main_content}")
        else:
            print(f"❌ 本地Reader也失敗: {local_content}")

if __name__ == "__main__":
    asyncio.run(test_specific_post())