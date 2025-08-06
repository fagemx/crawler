#!/usr/bin/env python3
"""
測試 UI 顯示流程 - 模擬任務管理中的查看功能
"""
import sys
from pathlib import Path

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from common.redis_client import get_redis_client
from ui.components.playwright_utils import PlaywrightUtils

def test_ui_display_flow():
    """測試 UI 顯示流程"""
    task_id = "28ebc0e7-95b7-4c87-9e6a-31404b257a67"
    
    print("🔍 模擬任務管理查看流程")
    
    # 步驟1: 模擬 _show_task_results 的邏輯
    print("\n📡 步驟1: 從 Redis 獲取 final_data (模擬任務管理點擊)")
    redis_client = get_redis_client()
    progress_data = redis_client.get_task_status(task_id)
    final_data = progress_data.get("final_data", {})
    
    print(f"✅ 獲取到 final_data: {len(final_data.get('results', []))} 篇貼文")
    print(f"📋 final_data 鍵值: {list(final_data.keys())}")
    
    # 步驟2: 模擬 _render_results 的轉換邏輯  
    print("\n🔄 步驟2: 轉換為顯示格式 (模擬 _render_results)")
    converted_results = PlaywrightUtils.convert_playwright_results(final_data)
    converted_results["target_username"] = "netflixtw"
    
    print(f"✅ 轉換後格式: {len(converted_results.get('results', []))} 篇貼文")
    print(f"📋 轉換後鍵值: {list(converted_results.keys())}")
    
    # 步驟3: 模擬 _show_results 的顯示邏輯
    print("\n📊 步驟3: 模擬結果顯示 (模擬 _show_results)")
    posts = converted_results.get("results", [])
    
    if not posts:
        print("❌ 沒有貼文可顯示")
        return
    
    # 統計計算（模擬 UI 中的統計）
    total_posts = len(posts)
    success_posts = sum(1 for r in posts if r.get('success', False))
    content_posts = sum(1 for r in posts if r.get('content'))
    views_posts = sum(1 for r in posts if r.get('views_count') or r.get('views'))
    
    print(f"✅ 統計結果:")
    print(f"   📊 總貼文數: {total_posts}")
    print(f"   ✅ 成功獲取: {success_posts}")
    print(f"   📝 有內容: {content_posts}")
    print(f"   👁️ 有觀看數: {views_posts}")
    
    # 步驟4: 檢查詳細結果格式
    print("\n📋 步驟4: 詳細結果檢查 (前2篇)")
    for i, post in enumerate(posts[:2]):
        print(f"\n📄 貼文 {i+1}:")
        print(f"   🆔 post_id: {post.get('post_id', 'N/A')}")
        print(f"   🔗 url: {post.get('url', 'N/A')[:50]}...")
        print(f"   📝 content: {len(post.get('content', ''))} 字元")
        print(f"   👁️ views: {post.get('views_count', 0)}")
        print(f"   ❤️ likes: {post.get('likes_count', 0)}")
        print(f"   💬 comments: {post.get('comments_count', 0)}")
    
    print("\n✅ UI 顯示流程測試完成！")
    print("💡 這個結果應該與任務管理中點擊 '📊 結果' 看到的一樣")

if __name__ == "__main__":
    test_ui_display_flow()