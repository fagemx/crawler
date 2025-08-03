#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修正重複貼文和內容提取問題
1. 處理重複貼文，保留觀看數高的
2. 修正內容提取邏輯
"""

import json
import re
from typing import Dict, List, Optional
from collections import defaultdict

def convert_views_to_number(views_str: str) -> int:
    """將觀看數字符串轉換為數字以便比較"""
    if not views_str:
        return 0
    
    views_str = views_str.upper().replace(',', '')
    
    if views_str.endswith('K'):
        return int(float(views_str[:-1]) * 1000)
    elif views_str.endswith('M'):
        return int(float(views_str[:-1]) * 1000000)
    elif views_str.endswith('B'):
        return int(float(views_str[:-1]) * 1000000000)
    else:
        try:
            return int(views_str)
        except:
            return 0

def extract_post_content_fixed(content: str) -> Optional[str]:
    """修正後的內容提取邏輯"""
    lines = content.split('\n')
    
    # 策略1: 找到第一行如果是回覆，使用它
    if lines and lines[0].strip().startswith('>>>'):
        reply_content = lines[0].strip()
        if len(reply_content) > 10:
            return reply_content
    
    # 策略2: 查找主貼文內容（更智能的識別）
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # 跳過明顯的非內容行
        if (not stripped or
            stripped.startswith('[') or
            stripped.startswith('![') or
            stripped.startswith('http') or
            stripped.startswith('Log in') or
            stripped.startswith('Thread') or
            stripped.startswith('gvmonthly') or
            stripped.isdigit() or
            re.match(r'^\d+/\d+/\d+$', stripped) or  # 日期格式
            stripped in ['Translate', 'views', '===============']):
            continue
        
        # 檢查是否是有效的貼文內容
        if (len(stripped) > 15 and
            not stripped.startswith('>>>') and
            ('。' in stripped or '，' in stripped or '!' in stripped or '?' in stripped or
             stripped.endswith('😆') or stripped.endswith('😅') or '護照' in stripped)):
            
            # 檢查後續是否有 Translate 標識
            for j in range(i + 1, min(i + 3, len(lines))):
                if 'Translate' in lines[j]:
                    return stripped
            
            # 如果內容合理且長度足夠，也返回
            if len(stripped) > 20:
                return stripped
    
    return None

def process_duplicates_and_fix_content(filename: str):
    """處理重複貼文和修正內容提取"""
    
    print(f"📂 處理文件: {filename}")
    
    # 讀取結果
    with open(filename, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    results = data.get('results', [])
    print(f"📊 原始項目數: {len(results)}")
    
    # 1. 按 post_id 分組，找出重複項
    grouped = defaultdict(list)
    for result in results:
        if result.get('post_id'):
            grouped[result['post_id']].append(result)
    
    # 2. 處理重複項：保留觀看數最高的
    processed_results = []
    duplicates_found = 0
    content_fixed = 0
    
    for post_id, items in grouped.items():
        if len(items) > 1:
            duplicates_found += 1
            print(f"🔍 發現重複: {post_id} ({len(items)} 個版本)")
            
            # 打印觀看數比較
            for i, item in enumerate(items):
                views = item.get('views', 'N/A')
                source = item.get('source', 'unknown')
                print(f"   版本{i+1}: {views} 觀看 (來源: {source})")
            
            # 選擇觀看數最高的
            best_item = max(items, key=lambda x: convert_views_to_number(x.get('views', '0')))
            print(f"   ✅ 保留: {best_item.get('views')} 觀看")
            
            processed_results.append(best_item)
        else:
            processed_results.append(items[0])
        
        # 3. 修正內容提取
        current_item = processed_results[-1]
        if current_item.get('content'):
            # 檢查是否需要重新提取內容
            original_content = current_item.get('content', '')
            
            # 如果提取到的是回覆內容但這不是回覆貼文，嘗試重新提取
            if (original_content.startswith('>>>') and 
                not current_item.get('post_id', '').endswith('reply')):  # 假設回覆ID有特殊標識
                
                # 嘗試從原始內容重新提取
                raw_content = current_item.get('raw_content', '')  # 如果有保存原始內容
                if raw_content:
                    fixed_content = extract_post_content_fixed(raw_content)
                    if fixed_content and fixed_content != original_content:
                        print(f"🔧 修正內容提取: {post_id}")
                        print(f"   原始: {original_content[:50]}...")
                        print(f"   修正: {fixed_content[:50]}...")
                        current_item['content'] = fixed_content
                        content_fixed += 1
    
    print(f"\n📊 處理結果:")
    print(f"   🔄 處理重複: {duplicates_found} 組")
    print(f"   🔧 修正內容: {content_fixed} 個")
    print(f"   📝 最終項目: {len(processed_results)} 個")
    
    # 4. 保存修正後的結果
    data['results'] = processed_results
    data['total_processed'] = len(processed_results)
    
    # 重新計算統計
    successful = [r for r in processed_results if r.get('success', False)]
    data['overall_success_rate'] = len(successful) / len(processed_results) * 100 if processed_results else 0
    
    output_filename = filename.replace('.json', '_fixed.json')
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"💾 修正結果已保存到: {output_filename}")
    
    # 5. 顯示修正後的前幾個項目
    print(f"\n🎯 修正後的前5個項目:")
    for i, result in enumerate(processed_results[:5]):
        post_id = result.get('post_id', 'N/A')
        views = result.get('views', 'N/A')
        content = result.get('content', 'N/A')
        source = result.get('source', 'N/A')
        content_preview = content[:60] + '...' if len(content) > 60 else content
        print(f"   {i+1}. {post_id} | {views} | {source}")
        print(f"      📝 {content_preview}")

if __name__ == "__main__":
    # 處理最新的結果文件
    import glob
    result_files = glob.glob("realtime_extraction_results_*.json")
    if result_files:
        latest_file = max(result_files, key=lambda x: x.split('_')[-1])
        print(f"🎯 處理最新文件: {latest_file}")
        process_duplicates_and_fix_content(latest_file)
    else:
        print("❌ 未找到結果文件")