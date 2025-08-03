#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reader內容解析器 - 從Jina Reader返回的markdown中提取關鍵數據
"""

import re
import requests
from typing import Dict, Optional, List
import json

class ThreadsReaderParser:
    """Threads貼文Reader解析器"""
    
    def __init__(self, reader_base_url: str = "http://localhost:8880"):
        self.reader_base_url = reader_base_url
    
    def fetch_content(self, post_url: str) -> str:
        """從Reader服務獲取內容"""
        reader_url = f"{self.reader_base_url}/{post_url}"
        try:
            response = requests.get(reader_url, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            print(f"❌ 獲取內容失敗: {e}")
            return ""
    
    def extract_post_content(self, markdown_content: str) -> Optional[str]:
        """提取貼文內容"""
        lines = markdown_content.split('\n')
        
        # 方法1: 查找第一段正文內容（在===分隔符之前）
        content_lines = []
        in_content = False
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # 跳過標題和URL行
            if line.startswith("Title:") or line.startswith("URL Source:") or line.startswith("Markdown Content:"):
                continue
                
            # 如果遇到分隔符，停止
            if "===============" in line or "---" in line:
                break
                
            # 如果是貼文內容（不是連結、不是按鈕文字）
            if not line.startswith("[") and not line.startswith("!") and len(line) > 10:
                content_lines.append(line)
                if len(content_lines) >= 3:  # 取前幾行作為內容
                    break
        
        return ' '.join(content_lines) if content_lines else None
    
    def extract_views_count(self, markdown_content: str) -> Optional[str]:
        """提取觀看數 - 新格式：在Thread連結中"""
        # 新格式：[Thread ====== 313K views](...)
        patterns = [
            r'\[Thread\s*={2,}\s*(\d+(?:\.\d+)?[KMB]?)\s*views\]',
            r'Thread.*?(\d+(?:\.\d+)?[KMB]?)\s*views',
            r'(\d+(?:\.\d+)?[KMB]?)\s*views'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, markdown_content, re.IGNORECASE)
            if match:
                return f"{match.group(1)} views"
        
        return None
    
    def extract_engagement_numbers(self, markdown_content: str) -> Dict[str, str]:
        """提取互動數據序列 - 基於位置推斷含義"""
        lines = markdown_content.split('\n')
        
        # 找到貼文的主圖片（不是頭像）
        for i, line in enumerate(lines):
            stripped = line.strip()
            # 找到貼文圖片（通常在Translate之後，且不是profile picture）
            if (stripped.startswith('![Image') and 
                'profile picture' not in stripped and 
                i > 0 and any('Translate' in lines[k] for k in range(max(0, i-3), i+1))):
                
                numbers = []
                # 在這個圖片後查找連續的數字
                for j in range(i + 1, min(i + 15, len(lines))):
                    candidate = lines[j].strip()
                    if re.match(r'^\d+(?:\.\d+)?[KMB]?$', candidate):
                        numbers.append(candidate)
                    elif candidate and candidate not in ["Pinned", "", "Translate"]:
                        # 遇到非數字行，停止收集
                        break
                
                # 根據位置推斷含義
                engagement_data = {}
                if len(numbers) >= 1:
                    engagement_data['likes'] = numbers[0]
                if len(numbers) >= 2:
                    engagement_data['comments'] = numbers[1]  
                if len(numbers) >= 3:
                    engagement_data['reposts'] = numbers[2]
                if len(numbers) >= 4:
                    engagement_data['shares'] = numbers[3]
                
                # 如果找到了數字序列，返回
                if len(numbers) >= 3:
                    return engagement_data
        
        return {}
    
    def extract_likes_count(self, markdown_content: str) -> Optional[str]:
        """提取按讚數 - 新格式：基於位置推斷"""
        engagement = self.extract_engagement_numbers(markdown_content)
        return engagement.get('likes')
    
    def parse_post(self, post_url: str) -> Dict:
        """解析單篇貼文，返回結構化數據"""
        print(f"🎯 開始解析貼文: {post_url}")
        
        # 獲取內容
        content = self.fetch_content(post_url)
        if not content:
            return {"error": "無法獲取內容"}
        
        print(f"📄 獲取到 {len(content)} 字符的內容")
        
        # 提取各項數據
        engagement = self.extract_engagement_numbers(content)
        
        result = {
            "url": post_url,
            "content": self.extract_post_content(content),
            "views": self.extract_views_count(content),
            "likes": engagement.get('likes'),
            "comments": engagement.get('comments'),
            "reposts": engagement.get('reposts'),
            "shares": engagement.get('shares'),
            "raw_numbers": list(engagement.values()) if engagement else [],
            "raw_length": len(content)
        }
        
        return result
    
    def debug_content(self, post_url: str, save_raw: bool = True):
        """調試模式：顯示原始內容以便分析"""
        content = self.fetch_content(post_url)
        if not content:
            return
        
        print("🔍 原始內容分析:")
        print("=" * 50)
        
        lines = content.split('\n')
        for i, line in enumerate(lines[:30]):  # 只顯示前30行
            print(f"{i+1:2d}: {line}")
        
        print(f"\n... (總共 {len(lines)} 行)")
        
        if save_raw:
            filename = f"reader_raw_content_{post_url.split('/')[-1]}.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"💾 原始內容已保存到: {filename}")

def main():
    """測試解析器"""
    parser = ThreadsReaderParser()
    
    # 測試貼文
    test_url = "https://www.threads.com/@ttshow.tw/post/DMfOVeqSkM5"
    
    print("🧪 測試Reader解析器")
    print("=" * 50)
    
    # 調試模式：查看原始內容
    print("📋 調試模式 - 查看原始內容:")
    parser.debug_content(test_url)
    
    print("\n" + "=" * 50)
    
    # 解析模式：提取結構化數據
    print("📊 解析模式 - 提取結構化數據:")
    result = parser.parse_post(test_url)
    
    print(f"📝 貼文內容: {result.get('content', 'N/A')}")
    print(f"👁️ 觀看數: {result.get('views', 'N/A')}")
    print(f"👍 按讚數: {result.get('likes', 'N/A')}")
    print(f"💬 留言數: {result.get('comments', 'N/A')}")
    print(f"🔄 轉發數: {result.get('reposts', 'N/A')}")  
    print(f"📤 分享數: {result.get('shares', 'N/A')}")
    print(f"🔢 原始數字序列: {result.get('raw_numbers', [])}")
    print(f"📄 原始長度: {result.get('raw_length', 0)} 字符")
    
    # 保存結果
    with open('reader_parse_result.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print("💾 解析結果已保存到: reader_parse_result.json")

if __name__ == "__main__":
    main()