"""
調試 Playwright Crawler 的原始抓取數據
查看 GraphQL 回應結構，找出 shares_count 為 null 的原因
"""
import sys
import json
from pathlib import Path
sys.path.append('.')

from agents.playwright_crawler.playwright_logic import first_of, FIELD_MAP

def debug_crawl_data():
    """分析最新的爬蟲數據"""
    debug_dir = Path("agents/playwright_crawler/debug")
    
    # 找到最新的爬蟲數據檔案
    crawl_files = list(debug_dir.glob("crawl_data_*.json"))
    if not crawl_files:
        print("❌ 找不到爬蟲數據檔案")
        return
    
    latest_file = max(crawl_files, key=lambda f: f.stat().st_mtime)
    print(f"📁 讀取檔案: {latest_file}")
    
    with open(latest_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"📊 總共 {data['total_found']} 個貼文，分析前 3 個...")
    
    # 分析前幾個貼文的 shares_count 問題
    for i, post in enumerate(data['posts'][:3]):
        print(f"\n--- 貼文 {i+1}: {post['url']} ---")
        print(f"結果: likes={post['likes_count']}, comments={post['comments_count']}, reposts={post['reposts_count']}, shares={post['shares_count']}")
        
        # 如果 shares_count 是 null，我們需要看原始數據
        if post['shares_count'] is None:
            print("⚠️  shares_count 是 null，需要檢查原始 GraphQL 數據")

def debug_raw_graphql():
    """檢查原始的 GraphQL 攔截數據"""
    debug_dir = Path("agents/playwright_crawler/debug")
    
    # 檢查是否有 sample_thread_item.json
    sample_file = debug_dir / "sample_thread_item.json"
    if sample_file.exists():
        print(f"📁 分析範例 GraphQL 數據: {sample_file}")
        
        with open(sample_file, 'r', encoding='utf-8') as f:
            thread_item = json.load(f)
        
        print(f"📊 GraphQL 回應結構分析:")
        analyze_post_structure(thread_item, "thread_item")
    else:
        print("❌ 找不到 sample_thread_item.json")

def analyze_post_structure(data, path="", max_depth=3, current_depth=0):
    """遞歸分析 JSON 結構，尋找可能的 shares/repost 相關欄位"""
    if current_depth > max_depth:
        return
    
    if isinstance(data, dict):
        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key
            
            # 尋找與 shares/repost 相關的欄位
            if any(keyword in key.lower() for keyword in ['share', 'repost', 'forward']):
                print(f"🔍 找到相關欄位: {current_path} = {value}")
            
            # 尋找數字欄位（可能是計數）
            if isinstance(value, (int, float)) and value > 0:
                if any(keyword in key.lower() for keyword in ['count', 'num', 'total']):
                    print(f"🔢 數字欄位: {current_path} = {value}")
            
            # 繼續遞歸
            if isinstance(value, (dict, list)) and current_depth < max_depth:
                analyze_post_structure(value, current_path, max_depth, current_depth + 1)
    
    elif isinstance(data, list) and len(data) > 0:
        # 只分析列表的第一個元素
        analyze_post_structure(data[0], f"{path}[0]", max_depth, current_depth)

def test_field_map():
    """測試 FIELD_MAP 中的 share_count 路徑"""
    debug_dir = Path("agents/playwright_crawler/debug")
    sample_file = debug_dir / "sample_thread_item.json"
    
    if not sample_file.exists():
        print("❌ 找不到 sample_thread_item.json")
        return
    
    with open(sample_file, 'r', encoding='utf-8') as f:
        thread_item = json.load(f)
    
    print(f"🧪 測試 FIELD_MAP 中的 share_count 路徑:")
    
    # 模擬 parse_post_data 中的邏輯
    post = find_post_dict(thread_item)
    if not post:
        print("❌ 找不到 post 字典")
        return
    
    share_count_paths = FIELD_MAP["share_count"]
    print(f"📋 share_count 路徑: {share_count_paths}")
    
    for path in share_count_paths:
        try:
            result = first_of(post, path)
            print(f"  ✅ 路徑 {path}: {result}")
        except Exception as e:
            print(f"  ❌ 路徑 {path}: 錯誤 - {e}")
    
    # 最終結果
    final_share_count = first_of(post, *share_count_paths) or 0
    print(f"🎯 最終 share_count: {final_share_count}")
    
    # 同樣測試 repost_count
    if "repost_count" in FIELD_MAP:
        repost_count_paths = FIELD_MAP["repost_count"]
        print(f"📋 repost_count 路徑: {repost_count_paths}")
        final_repost_count = first_of(post, *repost_count_paths) or 0
        print(f"🎯 最終 repost_count: {final_repost_count}")

def find_post_dict(data):
    """從 GraphQL 回應中找到 post 字典"""
    # 這裡需要實現與 playwright_logic.py 中相同的邏輯
    if isinstance(data, dict):
        # 檢查是否是 post 物件
        if 'pk' in data or 'id' in data:
            return data
        
        # 遞歸搜尋
        for value in data.values():
            result = find_post_dict(value)
            if result:
                return result
    
    elif isinstance(data, list):
        for item in data:
            result = find_post_dict(item)
            if result:
                return result
    
    return None

if __name__ == "__main__":
    print("🔍 調試 Playwright Crawler 的 shares_count 問題")
    print("=" * 60)
    
    # 1. 檢查處理後的爬蟲數據
    debug_crawl_data()
    
    print("\n" + "=" * 60)
    
    # 2. 分析原始 GraphQL 結構
    debug_raw_graphql()
    
    print("\n" + "=" * 60)
    
    # 3. 測試 FIELD_MAP 路徑
    test_field_map() 