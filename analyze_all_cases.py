#!/usr/bin/env python3
import json
import re

with open('parallel_reader_debug_results.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print('=== 完整案例分析 ===')
print(f'總數: {len(data)}')

single_post_pages = []
aggregated_pages = []

for item in data:
    post_id = item['post_id']
    content = item['raw_content']
    success = item['success']
    
    # 檢查是否是聚合頁面的指標
    is_aggregated = False
    
    # 1. 包含 "Related threads"
    if 'Related threads' in content:
        is_aggregated = True
        reason = "Related threads"
    
    # 2. 包含多個不同的 post ID
    elif len(content) > 5000:  # 長內容更可能是聚合頁面
        # 查找所有 /post/ URL
        post_urls = re.findall(r'/post/([A-Za-z0-9_-]+)', content)
        unique_posts = set(post_urls)
        if len(unique_posts) > 2:  # 如果包含超過2個不同的post ID
            is_aggregated = True
            reason = f"Multi-post ({len(unique_posts)} posts)"
        else:
            single_post_pages.append((post_id, success, len(content)))
    else:
        single_post_pages.append((post_id, success, len(content)))
    
    if is_aggregated:
        aggregated_pages.append((post_id, success, reason, len(content)))

print(f'\n=== 頁面類型分析 ===')
print(f'📄 單一貼文頁面: {len(single_post_pages)}')
print(f'📚 聚合頁面: {len(aggregated_pages)}')

print(f'\n=== 聚合頁面詳情 ===')
for post_id, success, reason, length in aggregated_pages:
    print(f'📚 {post_id}: {reason} (長度: {length:,} 字符)')

print(f'\n=== 單一貼文頁面成功率 ===')
single_success = [item for item in single_post_pages if item[1]]
single_failed = [item for item in single_post_pages if not item[1]]

print(f'✅ 成功: {len(single_success)} / {len(single_post_pages)} ({len(single_success)/len(single_post_pages)*100:.1f}%)')
print(f'❌ 失敗: {len(single_failed)}')

print(f'\n=== 成功的單一貼文 ===')
for post_id, success, length in single_success:
    success_item = next(item for item in data if item['post_id'] == post_id)
    views = success_item.get('views', 'N/A')
    print(f'✅ {post_id}: {views} (長度: {length:,})')

print(f'\n=== 失敗的單一貼文 ===')
for post_id, success, length in single_failed:
    print(f'❌ {post_id}: 單一貼文但無觀看數 (長度: {length:,})')

print(f'\n=== 總結 ===')
print(f'📊 實際可分析的單一貼文: {len(single_post_pages)}')
print(f'✅ 觀看數提取成功: {len(single_success)}')
print(f'🎯 真實成功率: {len(single_success)/len(single_post_pages)*100:.1f}%')
print(f'📚 排除的聚合頁面: {len(aggregated_pages)} (這些頁面本來就沒有觀看數)')