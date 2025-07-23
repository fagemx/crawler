#!/usr/bin/env python3
"""
測試 Jina Agent 的功能
驗證 markdown 格式解析和正則表達式提取
"""

import asyncio
import json
from agents.jina.jina_logic import JinaLogic
from common.models import PostMetrics

async def test_jina_agent():
    """測試 Jina Agent 的核心功能"""
    
    # 創建 JinaLogic 實例
    jina_logic = JinaLogic()
    
    # 測試 URL - 你提供的範例
    test_url = "https://www.threads.com/@evenchen14/post/DMZ4lbJTchf"
    
    # 創建測試 PostMetrics
    test_post = PostMetrics(
        url=test_url,
        username="evenchen14",
        post_id="DMZ4lbJTchf",
        source="crawler"
    )
    
    print(f"🧪 測試 Jina Agent")
    print(f"📍 測試 URL: {test_url}")
    print("-" * 60)
    
    try:
        # 測試 Jina 增強功能
        print("🚀 開始 Jina 數據增強...")
        
        async for result in jina_logic.enhance_posts_with_jina([test_post]):
            if result.get("type") == "status":
                print(f"📊 {result['message']}")
            elif result.get("type") == "data" and result.get("final"):
                data = result["data"]
                batch = data["batch"]
                posts = batch["posts"]
                
                if posts:
                    enhanced_post = posts[0]
                    print("\n✅ Jina 處理結果:")
                    print(f"   Views: {enhanced_post.get('views_count', 'N/A')}")
                    print(f"   Likes: {enhanced_post.get('likes_count', 'N/A')}")
                    print(f"   Comments: {enhanced_post.get('comments_count', 'N/A')}")
                    print(f"   Reposts: {enhanced_post.get('reposts_count', 'N/A')}")
                    print(f"   Shares: {enhanced_post.get('shares_count', 'N/A')}")
                    print(f"   Source: {enhanced_post.get('source', 'N/A')}")
                    print(f"   Complete: {enhanced_post.get('is_complete', False)}")
                
                print(f"\n📈 統計資訊:")
                print(f"   處理時間: {data['processing_time']:.2f}s")
                print(f"   成功數量: {data['successful_count']}")
                print(f"   完整數量: {data['complete_count']}")
                print(f"   不完整數量: {data['incomplete_count']}")
                print(f"   需要 Vision: {data['needs_vision']}")
                print(f"   下一階段: {data['next_stage']}")
                
    except Exception as e:
        print(f"❌ 測試失敗: {str(e)}")
        import traceback
        traceback.print_exc()

async def test_regex_parsing():
    """測試正則表達式解析功能"""
    
    print("\n" + "="*60)
    print("🔍 測試正則表達式解析")
    print("="*60)
    
    jina_logic = JinaLogic()
    
    # 使用你提供的真實 Jina markdown 回應
    test_markdown = """看到深藍長輩說趙少康晚節不保，也算是見證一種歷史奇蹟。

===============

[](https://www.threads.com/)

[](https://www.threads.com/)

[](https://www.threads.com/search)

[Log in](https://www.threads.com/login?show_choice_screen=false)

[Thread ====== 4K views](https://www.threads.com/@evenchen14/post/DMZ4lbJTchf)

[![Image 1: evenchen14's profile picture](https://scontent-sof1-1.cdninstagram.com/v/t51.2885-19/358176746_984355706034552_9096061686803033767_n.jpg?stp=dst-jpg_s150x150_tt6&efg=eyJ2ZW5jb2RlX3RhZyI6InByb2ZpbGVfcGljLmRqYW5nby4xMDgwLmMyIn0&_nc_ht=scontent-sof1-1.cdninstagram.com&_nc_cat=1&_nc_oc=Q6cZ2QEiaFawXmHlXi3VIMckIHeFsiZIJVtloomPMCUgmZgj4wVtUNpCHx83h0U4ascrKR1_oKbA2J2UXqWCsexW01We&_nc_ohc=Ng8NSpIidloQ7kNvwEe1ItZ&_nc_gid=DHJTTMcP7pQ7xWJHFCYBLw&edm=APs17CUBAAAA&ccb=7-5&oh=00_AfRM1UfzKE9Fk-W28SNCLOWdQ3Xyj0U835tHiPoBbh-KvA&oe=6886501F&_nc_sid=10d13b)](https://www.threads.com/@evenchen14)

[evenchen14](https://www.threads.com/@evenchen14)

[19h](https://www.threads.com/@evenchen14/post/DMZ4lbJTchf)

看到深藍長輩說趙少康晚節不保，也算是見證一種歷史奇蹟。

Translate

267

3

1

[![Image 2: huskygo1980's profile picture](https://scontent-sof1-2.cdninstagram.com/v/t51.2885-19/503996718_17887012845283018_1303051638358234247_n.jpg?stp=dst-jpg_s150x150_tt6&efg=eyJ2ZW5jb2RlX3RhZyI6InByb2ZpbGVfcGljLmRqYW5nby4xMDI0LmMyIn0&_nc_ht=scontent-sof1-2.cdninstagram.com&_nc_cat=110&_nc_oc=Q6cZ2QEiaFawXmHlXi3VIMckIHeFsiZIJVtloomPMCUgmZgj4wVtUNpCHx83h0U4ascrKR1_oKbA2J2UXqWCsexW01We&_nc_ohc=OoXir4ZHRDAQ7kNvwGFKNKC&_nc_gid=DHJTTMcP7pQ7xWJHFCYBLw&edm=APs17CUBAAAA&ccb=7-5&oh=00_AfThWlw4MTKYt9gFwFdoKk9yWqoNTXcMP6_owx0BLUkWhA&oe=6886418B&_nc_sid=10d13b)](https://www.threads.com/@huskygo1980)

[huskygo1980](https://www.threads.com/@huskygo1980)

[14h](https://www.threads.com/@huskygo1980/post/DMaaZOYT4rF)

他一直如一 哪有晚節不保

Translate

1
"""
    
    # 創建測試 PostMetrics
    test_post = PostMetrics(
        url="https://www.threads.com/@evenchen14/post/DMZ4lbJTchf",
        username="evenchen14",
        post_id="DMZ4lbJTchf"
    )
    
    # 測試解析
    enhanced_post = jina_logic._parse_metrics_from_markdown(test_post, test_markdown)
    
    print("📝 測試 Markdown 內容 (前200字符):")
    print(test_markdown[:200] + "...")
    
    print("\n🔍 正則表達式測試:")
    
    # 測試 views 正則表達式
    views_match = jina_logic.views_pattern.search(test_markdown)
    if views_match:
        print(f"   Views 匹配: '{views_match.group(0)}' -> {views_match.group(1)}")
    else:
        print("   Views 匹配: 無")
    
    # 測試 translate 正則表達式
    translate_match = jina_logic.translate_pattern.search(test_markdown)
    if translate_match:
        print(f"   Translate 匹配: '{translate_match.group(0)}'")
        print(f"   提取的數字: {translate_match.groups()}")
    else:
        print("   Translate 匹配: 無")
    
    print("\n✅ 最終解析結果:")
    print(f"   Views: {enhanced_post.views_count}")
    print(f"   Likes: {enhanced_post.likes_count}")
    print(f"   Comments: {enhanced_post.comments_count}")
    print(f"   Reposts: {enhanced_post.reposts_count}")
    print(f"   Shares: {enhanced_post.shares_count}")
    print(f"   Complete: {enhanced_post.is_complete}")
    
    # 測試不完整的情況
    print("\n🧪 測試不完整數據 (只有2個數字):")
    incomplete_markdown = """
[Thread ====== 2.5K views](https://www.threads.com/@test/post/123)

[test](https://www.threads.com/@test)

測試貼文內容

Translate

150

5
"""
    
    test_post2 = PostMetrics(
        url="https://www.threads.com/@test/post/123",
        username="test",
        post_id="123"
    )
    
    enhanced_post2 = jina_logic._parse_metrics_from_markdown(test_post2, incomplete_markdown)
    
    print(f"   Views: {enhanced_post2.views_count}")
    print(f"   Likes: {enhanced_post2.likes_count}")
    print(f"   Comments: {enhanced_post2.comments_count}")
    print(f"   Reposts: {enhanced_post2.reposts_count}")
    print(f"   Shares: {enhanced_post2.shares_count}")
    print(f"   Complete: {enhanced_post2.is_complete}")
    print(f"   需要 Vision: {not enhanced_post2.is_complete}")

async def test_number_conversion():
    """測試數字轉換功能"""
    
    print("\n" + "="*60)
    print("🔢 測試數字轉換")
    print("="*60)
    
    jina_logic = JinaLogic()
    
    test_cases = [
        "3.9K",
        "1.2M", 
        "265",
        "1,234",
        "15.7K",
        "2.5M"
    ]
    
    for test_case in test_cases:
        result = jina_logic._to_int(test_case)
        print(f"   {test_case:>8} -> {result:>10,}")

if __name__ == "__main__":
    print("🧪 Jina Agent 測試套件")
    print("="*60)
    
    # 運行所有測試
    asyncio.run(test_regex_parsing())
    asyncio.run(test_number_conversion())
    asyncio.run(test_jina_agent())