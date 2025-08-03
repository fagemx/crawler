#!/usr/bin/env python3
import json

with open('parallel_reader_debug_results.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# 找到 DMfOVeqSkM5 的內容
target = None
for item in data:
    if item['post_id'] == 'DMfOVeqSkM5':
        target = item
        break

if target:
    content = target['raw_content']
    lines = content.split('\n')
    
    print('=== DMfOVeqSkM5 完整內容分析 ===')
    print(f'總長度: {len(content)} 字符, 總行數: {len(lines)}')
    
    # 尋找包含 view 的所有行
    view_lines = []
    for i, line in enumerate(lines):
        if 'view' in line.lower():
            view_lines.append((i+1, line))
    
    print(f'\n包含 "view" 的行數: {len(view_lines)}')
    for line_num, line_content in view_lines[:8]:  # 顯示前8行
        print(f'L{line_num}: {line_content.strip()[:150]}...')
    
    # 尋找包含 Thread 的所有行
    thread_lines = []
    for i, line in enumerate(lines):
        if 'thread' in line.lower() and len(line.strip()) < 200:  # 排除太長的行
            thread_lines.append((i+1, line))
    
    print(f'\n包含 "thread" 的行數: {len(thread_lines)}')
    for line_num, line_content in thread_lines[:8]:  # 顯示前8行
        print(f'L{line_num}: {line_content.strip()}')
        
    # 檢查是否有特殊的觀看數格式
    import re
    # 檢查各種可能的觀看數格式
    patterns = [
        r'(\d+(?:[\.,]\d+)?[KMB]?)\s*views?',
        r'views?\s*[:\-]\s*(\d+(?:[\.,]\d+)?[KMB]?)',
        r'(\d+(?:[\.,]\d+)?[KMB]?)\s*人\s*觀看',
        r'(\d+(?:[\.,]\d+)?[KMB]?)\s*次\s*觀看',
        r'seen\s*by\s*(\d+(?:[\.,]\d+)?[KMB]?)'
    ]
    
    print(f'\n=== 正則表達式搜尋結果 ===')
    for i, pattern in enumerate(patterns):
        matches = re.findall(pattern, content, re.IGNORECASE)
        if matches:
            print(f'Pattern {i}: {matches[:5]}')  # 只顯示前5個匹配