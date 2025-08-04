#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
指標提取器
處理觀看數、按讚數、留言數等指標的提取
"""

import re
from typing import Optional, List
from ..utils.helpers import normalize_content, validate_views_format

class MetricsExtractor:
    """貼文指標提取器"""
    
    def __init__(self):
        # NBSP字符和提取模式
        self.NBSP = "\u00A0"
        self.view_patterns = [
            re.compile(rf'\[Thread[\s{self.NBSP}=]*?(\d+(?:[\.,]\d+)?[KMB]?)\s*views\]', re.IGNORECASE),
            re.compile(rf'Thread[\s{self.NBSP}=]*?(\d+(?:[\.,]\d+)?[KMB]?)[\s{self.NBSP}]*views', re.IGNORECASE | re.MULTILINE),
            re.compile(r'(\d+(?:[\.,]\d+)?[KMB]?)\s*views?', re.IGNORECASE),
            re.compile(r'(\d+(?:[\.,]\d+)?[KMB]?)\s*view(?:s|ing)', re.IGNORECASE),
            re.compile(r'views?\s*[:\-]\s*(\d+(?:[\.,]\d+)?[KMB]?)', re.IGNORECASE),
        ]
    
    def extract_views_count(self, markdown_content: str, post_id: str = "") -> Optional[str]:
        """觀看數提取"""
        normalized_content = normalize_content(markdown_content)
        
        for pattern in self.view_patterns:
            match = pattern.search(normalized_content)
            if match:
                views = match.group(1).replace(',', '').replace('.', '').strip()
                
                if validate_views_format(views):
                    return views
        
        return None
    
    def extract_engagement_numbers(self, markdown_content: str) -> List[str]:
        """提取所有統計數字序列（按讚、留言、轉發、分享）"""
        lines = markdown_content.split('\n')
        
        # 策略1: 查找貼文內容後的第一個圖片，然後提取後續數字
        for i, line in enumerate(lines):
            stripped = line.strip()
            # 找到貼文圖片（通常在Translate之後）
            if stripped.startswith('![Image') and not 'profile picture' in stripped:
                numbers = []
                # 在這個圖片後查找連續的數字
                for j in range(i + 1, min(i + 20, len(lines))):
                    candidate = lines[j].strip()
                    if re.match(r'^\d+(?:\.\d+)?[KMB]?$', candidate):
                        numbers.append(candidate)
                    elif candidate and not re.match(r'^\d+(?:\.\d+)?[KMB]?$', candidate) and candidate != "Pinned":
                        # 遇到非數字行（但跳過Pinned），停止收集
                        break
                
                # 如果找到了數字序列，返回
                if len(numbers) >= 3:
                    return numbers
        
        # 策略2: 如果策略1失敗，查找任何連續的數字序列
        all_numbers = []
        consecutive_numbers = []
        
        for line in lines:
            stripped = line.strip()
            # 檢查是否為純數字（可能包含K/M/B後綴）
            if re.match(r'^\d+(?:\.\d+)?[KMB]?$', stripped):
                consecutive_numbers.append(stripped)
            else:
                # 如果找到了連續數字序列，保存它
                if len(consecutive_numbers) >= 3:
                    all_numbers.extend(consecutive_numbers)
                    break  # 找到第一個就夠了
                consecutive_numbers = []
        
        # 檢查最後的連續數字
        if len(consecutive_numbers) >= 3:
            all_numbers.extend(consecutive_numbers)
        
        return all_numbers[:4] if all_numbers else []  # 最多返回4個數字
    
    def extract_likes_count(self, markdown_content: str) -> Optional[str]:
        """按讚數提取"""
        engagement_numbers = self.extract_engagement_numbers(markdown_content)
        
        if len(engagement_numbers) >= 1:
            return engagement_numbers[0]
        
        # 備選方案：查找特定的likes模式
        likes_patterns = [
            re.compile(r'(\d+(?:\.\d+)?[KMB]?)\s*likes?', re.IGNORECASE),
            re.compile(r'likes?\s*[:\-]\s*(\d+(?:\.\d+)?[KMB]?)', re.IGNORECASE),
        ]
        
        for pattern in likes_patterns:
            match = pattern.search(markdown_content)
            if match:
                return match.group(1).replace(',', '').strip()
        
        return None
    
    def extract_comments_count(self, markdown_content: str) -> Optional[str]:
        """留言數提取"""
        engagement_numbers = self.extract_engagement_numbers(markdown_content)
        
        if len(engagement_numbers) >= 2:
            return engagement_numbers[1]
        
        # 備選方案：查找特定的comments模式
        comments_patterns = [
            re.compile(r'(\d+(?:\.\d+)?[KMB]?)\s*comments?', re.IGNORECASE),
            re.compile(r'comments?\s*[:\-]\s*(\d+(?:\.\d+)?[KMB]?)', re.IGNORECASE),
        ]
        
        for pattern in comments_patterns:
            match = pattern.search(markdown_content)
            if match:
                return match.group(1).replace(',', '').strip()
        
        return None
    
    def extract_reposts_count(self, markdown_content: str) -> Optional[str]:
        """轉發數提取"""
        engagement_numbers = self.extract_engagement_numbers(markdown_content)
        
        if len(engagement_numbers) >= 3:
            return engagement_numbers[2]
        
        # 備選方案：查找特定的reposts模式
        reposts_patterns = [
            re.compile(r'(\d+(?:\.\d+)?[KMB]?)\s*reposts?', re.IGNORECASE),
            re.compile(r'reposts?\s*[:\-]\s*(\d+(?:\.\d+)?[KMB]?)', re.IGNORECASE),
        ]
        
        for pattern in reposts_patterns:
            match = pattern.search(markdown_content)
            if match:
                return match.group(1).replace(',', '').strip()
        
        return None
    
    def extract_shares_count(self, markdown_content: str) -> Optional[str]:
        """分享數提取"""
        engagement_numbers = self.extract_engagement_numbers(markdown_content)
        
        if len(engagement_numbers) >= 4:
            return engagement_numbers[3]
        
        # 備選方案：查找特定的shares模式
        shares_patterns = [
            re.compile(r'(\d+(?:\.\d+)?[KMB]?)\s*shares?', re.IGNORECASE),
            re.compile(r'shares?\s*[:\-]\s*(\d+(?:\.\d+)?[KMB]?)', re.IGNORECASE),
        ]
        
        for pattern in shares_patterns:
            match = pattern.search(markdown_content)
            if match:
                return match.group(1).replace(',', '').strip()
        
        return None