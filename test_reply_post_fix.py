#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
測試回覆貼文的處理
DMzvyiSzkdc 是一個回覆貼文，內容就是回覆
"""

from scripts.realtime_crawler_extractor import RealtimeCrawlerExtractor

def test_reply_post():
    """測試回覆貼文的處理"""
    
    # 這是回覆貼文本身
    reply_url = "https://www.threads.com/@gvmonthly/post/DMzvyiSzkdc"
    main_url = "https://www.threads.com/@gvmonthly/post/DMzvu4MTpis"
    
    print("🧪 測試回覆貼文處理")
    print(f"📍 回覆貼文: {reply_url}")
    print(f"📍 主貼文: {main_url}")
    print("=" * 60)
    
    extractor = RealtimeCrawlerExtractor("gvmonthly", 1)
    
    # 測試回覆貼文
    print("\n🔄 測試回覆貼文...")
    success, content = extractor.fetch_content_jina_api(reply_url)
    
    if success:
        print(f"✅ 成功獲取回覆貼文內容 ({len(content)} 字符)")
        main_content = extractor.extract_post_content(content)
        print(f"📝 提取內容: {main_content}")
        
        # 分析content結構
        lines = content.split('\n')[:30]  # 前30行
        print(f"\n📋 前30行內容結構:")
        for i, line in enumerate(lines):
            if line.strip():
                print(f"   {i:2d}: {line.strip()[:80]}")
    
    # 測試主貼文
    print(f"\n🔄 測試主貼文...")
    success2, content2 = extractor.fetch_content_jina_api(main_url)
    
    if success2:
        print(f"✅ 成功獲取主貼文內容 ({len(content2)} 字符)")
        main_content2 = extractor.extract_post_content(content2)
        print(f"📝 提取內容: {main_content2}")

if __name__ == "__main__":
    test_reply_post()