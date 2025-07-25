#!/usr/bin/env python3
"""
測試修正後的 Playwright Crawler
"""
import sys
sys.path.append('.')

import json
from pathlib import Path
from agents.playwright_crawler.playwright_logic import parse_post_data

def test_fixed_parsing():
    """測試修正後的解析邏輯"""
    print("🧪 測試修正後的 Playwright Crawler 解析邏輯")
    print("=" * 60)
    
    # 讀取範例數據
    sample_file = Path("agents/playwright_crawler/debug/sample_thread_item.json")
    if not sample_file.exists():
        print("❌ 找不到範例數據檔案")
        return
    
    with open(sample_file, 'r', encoding='utf-8') as f:
        sample_data = json.load(f)
    
    # 提取 post 數據
    post = sample_data.get('post', {})
    if not post:
        print("❌ 無法提取 post 數據")
        print(f"📋 可用的頂層鍵: {list(sample_data.keys())}")
        return
    
    # 構造測試 URL
    test_url = "https://www.threads.net/t/DMSy3RVNma0"
    
    # 使用修正後的解析邏輯
    try:
        result = parse_post_data(post, test_url)
        print(f"✅ 解析成功！")
        print(f"📊 完整結果:")
        print(f"   🔗 URL: {result.url}")
        print(f"   👤 用戶: {result.username}")
        print(f"   ❤️  讚數: {result.likes_count}")
        print(f"   💬 評論數: {result.comments_count}")
        print(f"   🔄 轉發數: {result.reposts_count}")
        print(f"   📤 分享數: {result.shares_count}")
        print(f"   📝 內容: {result.content[:100]}...")
        
        # 驗證所有指標都不是 None
        missing_metrics = []
        if result.likes_count is None:
            missing_metrics.append("likes_count")
        if result.comments_count is None:
            missing_metrics.append("comments_count") 
        if result.reposts_count is None:
            missing_metrics.append("reposts_count")
        if result.shares_count is None:
            missing_metrics.append("shares_count")
            
        if missing_metrics:
            print(f"⚠️  缺少指標: {missing_metrics}")
        else:
            print("🎉 所有核心指標都已正確解析！")
            
    except Exception as e:
        print(f"❌ 解析失敗: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_fixed_parsing() 