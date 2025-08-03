#!/usr/bin/env python3
"""
分析調試文件，找出問題所在
"""

def analyze_debug_file(filename, label):
    """分析單個調試文件"""
    print(f"\n📄 分析 {label}")
    print("-" * 50)
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        
        lines = content.split('\n')
        
        print(f"檔案大小: {len(content):,} 字符")
        print(f"總行數: {len(lines)}")
        
        # 查找關鍵字
        keywords = {
            "Thread ======": content.count("Thread ======"),
            "views": content.count("views"),
            "觀看": content.count("觀看"),
            "Related threads": content.count("Related threads"),
            "post": content.count("/post/"),
            "Like": content.count("Like"),
            "Comment": content.count("Comment"),
            "Repost": content.count("Repost"),
            "Share": content.count("Share"),
        }
        
        print("關鍵字統計:")
        for keyword, count in keywords.items():
            if count > 0:
                print(f"   • {keyword}: {count} 次")
        
        # 查找觀看數模式
        import re
        view_patterns = [
            r'Thread\s*={6}\s*([0-9,\.]+[KMB]?)\s*views?',
            r'Thread\s*={6}\s*([0-9,\.]+[KMB]?)',
            r'(\d+(?:\.\d+)?[KMB]?)\s*views?',
        ]
        
        found_views = []
        for pattern in view_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                found_views.extend(matches)
        
        if found_views:
            print(f"找到觀看數: {found_views}")
        else:
            print("❌ 未找到觀看數")
        
        # 檢查是否包含其他 post_id
        original_post_id = "DMfOVeqSkM5"
        other_post_ids = re.findall(r'/post/([A-Za-z0-9_-]+)', content)
        other_unique_ids = list(set(other_post_ids) - {original_post_id})
        
        if other_unique_ids:
            print(f"發現其他 post_id: {other_unique_ids[:5]}")
        else:
            print("✅ 只包含目標 post_id")
        
        # 查看內容結構
        print("\n前 20 行重要內容:")
        important_lines = []
        for i, line in enumerate(lines):
            line = line.strip()
            if line and not line.startswith('=') and not line.startswith('[Image'):
                important_lines.append(f"L{i+1}: {line}")
                if len(important_lines) >= 20:
                    break
        
        for line in important_lines:
            print(f"   {line}")
        
        return found_views, len(other_unique_ids) > 1
        
    except Exception as e:
        print(f"❌ 無法讀取文件: {e}")
        return [], True

def main():
    print("🔍 分析 Reader 調試文件")
    print("=" * 80)
    
    files_to_analyze = [
        ("debug_content_原始請求_20250803_224922.txt", "原始請求"),
        ("debug_content_增強_Headers_20250803_224936.txt", "增強 Headers"),
        ("debug_content_無快取_20250803_224953.txt", "無快取")
    ]
    
    results = {}
    
    for filename, label in files_to_analyze:
        views, is_aggregated = analyze_debug_file(filename, label)
        results[label] = {
            'views': views,
            'is_aggregated': is_aggregated,
            'success': len(views) > 0 and not is_aggregated
        }
    
    print("\n" + "=" * 80)
    print("📊 總結分析")
    print("=" * 80)
    
    for label, result in results.items():
        status = "✅ 成功" if result['success'] else "❌ 失敗"
        print(f"{status} {label}:")
        print(f"   觀看數: {result['views'] if result['views'] else '未找到'}")
        print(f"   聚合頁面: {'是' if result['is_aggregated'] else '否'}")
    
    # 給出建議
    print("\n💡 分析建議:")
    
    successful = [label for label, result in results.items() if result['success']]
    if successful:
        print(f"✅ 以下策略有效: {', '.join(successful)}")
        print("   建議在主程式中採用相應的 headers")
    else:
        print("❌ 所有策略都失敗了")
        print("   可能的原因:")
        print("   1. Reader 服務本身有問題")
        print("   2. Threads.com 完全阻止了自動化訪問")
        print("   3. 需要更複雜的反檢測措施")
        
        # 檢查是否有內容但沒有觀看數
        has_content = any(not result['is_aggregated'] for result in results.values())
        if has_content:
            print("   📄 有內容但無觀看數 → 可能是觀看數提取邏輯問題")
        else:
            print("   📄 全部都是聚合頁面 → 確定是 Reader/Threads 的問題")

if __name__ == '__main__':
    main()