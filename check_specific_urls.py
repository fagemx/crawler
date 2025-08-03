#!/usr/bin/env python3
import json
import requests

def analyze_specific_cases():
    """檢查具體的 URL 和 Reader 返回的內容"""
    
    # 從調試結果中讀取數據
    with open('parallel_reader_debug_results.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print('=== 詳細檢查所謂的 "聚合頁面" ===')
    
    # 檢查幾個典型案例
    test_cases = [
        'DMfOVeqSkM5',  # 之前分析的長內容
        'DMZVCFzSpIX',  # 被標記為 Multi-post
        'DL_vyT-RZQ6',  # 被標記為 Related threads
        'DIfkbgLSjO3',  # 成功的案例
    ]
    
    for post_id in test_cases:
        item = next((x for x in data if x['post_id'] == post_id), None)
        if not item:
            continue
            
        content = item['raw_content']
        success = item['success']
        
        print(f'\n{"="*60}')
        print(f'🔍 檢查: {post_id}')
        print(f'URL: https://www.threads.net/@ttshow.tw/post/{post_id}')
        print(f'成功: {success}')
        print(f'內容長度: {len(content):,} 字符')
        
        # 檢查是否真的包含 "Related threads"
        has_related_threads = 'Related threads' in content
        print(f'包含 "Related threads": {has_related_threads}')
        
        # 檢查實際的標題和開頭內容
        lines = content.split('\n')
        print(f'\n📄 前10行內容:')
        for i, line in enumerate(lines[:10]):
            if line.strip():
                print(f'L{i+1}: {line.strip()[:100]}...' if len(line) > 100 else f'L{i+1}: {line.strip()}')
        
        # 查找所有包含 post ID 的行
        post_urls = []
        for i, line in enumerate(lines):
            if '/post/' in line and post_id not in line:
                # 找到其他的 post ID
                import re
                other_posts = re.findall(r'/post/([A-Za-z0-9_-]+)', line)
                for other_post in other_posts:
                    if other_post != post_id:
                        post_urls.append((i+1, other_post, line.strip()[:150]))
        
        if post_urls:
            print(f'\n🔗 發現其他 Post ID (前5個):')
            for line_num, other_post, line_content in post_urls[:5]:
                print(f'L{line_num}: {other_post} - {line_content}')
        else:
            print(f'\n✅ 沒有發現其他 Post ID，看起來是單一貼文')
        
        # 檢查觀看數相關內容
        view_lines = []
        for i, line in enumerate(lines):
            if any(keyword in line.lower() for keyword in ['view', '觀看', 'thread ======']):
                view_lines.append((i+1, line.strip()))
        
        if view_lines:
            print(f'\n👀 觀看數相關行:')
            for line_num, line_content in view_lines[:3]:
                print(f'L{line_num}: {line_content}')
        else:
            print(f'\n❌ 沒有找到觀看數相關內容')

def check_original_url():
    """直接檢查原始 URL 是否正常"""
    print(f'\n{"="*60}')
    print('🌐 直接檢查 Reader 服務')
    
    test_url = 'https://www.threads.net/@ttshow.tw/post/DMfOVeqSkM5'
    reader_url = f'http://localhost:8880/{test_url}'
    
    try:
        response = requests.get(reader_url, timeout=30)
        print(f'HTTP 狀態: {response.status_code}')
        print(f'內容長度: {len(response.text):,} 字符')
        
        content = response.text
        lines = content.split('\n')
        
        print(f'\n📄 Reader 返回的前15行:')
        for i, line in enumerate(lines[:15]):
            if line.strip():
                print(f'L{i+1}: {line.strip()[:120]}...' if len(line) > 120 else f'L{i+1}: {line.strip()}')
                
        # 檢查是否包含重定向信息
        if 'Related threads' in content:
            print(f'\n⚠️ 確實包含 "Related threads"')
        else:
            print(f'\n✅ 沒有 "Related threads"，可能是正常單一貼文')
            
    except Exception as e:
        print(f'❌ 請求失敗: {e}')

if __name__ == '__main__':
    analyze_specific_cases()
    check_original_url()