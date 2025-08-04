#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
內容提取器
處理貼文主內容的智能提取
"""

import re
from typing import Optional, List
from ..utils.helpers import normalize_content

class ContentExtractor:
    """貼文內容提取器"""
    
    def __init__(self, target_username: str = None):
        self.target_username = target_username
    
    def extract_post_content(self, content: str) -> Optional[str]:
        """智能提取主貼文內容 - 區分主貼文和分享貼文"""
        lines = content.split('\n')
        
        # 策略1: 專門處理 Threads 頁面結構
        main_post_content = self._extract_main_post_from_threads_structure(lines)
        if main_post_content:
            return main_post_content
        
        # 策略2: 通用結構化提取
        main_post_content = self._extract_main_post_from_structure(lines)
        if main_post_content:
            return main_post_content
        
        # 策略3: 回到原始方法作為備選
        return self._extract_content_fallback(lines)
    
    def _extract_main_post_from_threads_structure(self, lines: List[str]) -> Optional[str]:
        """專門從 Threads 頁面結構中提取主貼文內容"""
        # 策略A: 檢查開頭是否就是主內容（常見模式）
        for i, line in enumerate(lines[:10]):  # 只檢查前10行
            stripped = line.strip()
            if (stripped and 
                len(stripped) > 8 and
                not stripped.startswith('[') and
                not stripped.startswith('![') and
                not stripped.startswith('http') and
                not stripped.startswith('=') and  # 跳過分隔符
                not stripped.isdigit() and
                not stripped in ['Translate', 'views', 'Log in', 'Thread', 'Sorry, we\'re having trouble playing this video.', 'Learn more'] and
                not re.match(r'^\d+[dhm]$', stripped) and
                not re.match(r'^\d+$', stripped)):
                
                # 這很可能是主內容
                return stripped
        
        # 策略B: 查找目標用戶名後的內容
        if self.target_username:
            return self._extract_content_after_username(lines)
        
        return None
    
    def _extract_content_after_username(self, lines: List[str]) -> Optional[str]:
        """在目標用戶名後查找內容"""
        target_user_found = False
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # 檢查是否找到目標用戶名（支持連結格式）
            if (self.target_username in stripped and 
                (not stripped.startswith('[') or f'[{self.target_username}]' in stripped)):
                target_user_found = True
                continue
            
            # 如果已經找到目標用戶，開始收集內容
            if target_user_found:
                # 跳過時間戳
                if re.match(r'^\d{2}/\d{2}/\d{2}$', stripped):
                    continue
                
                # 找到實質內容
                if (stripped and 
                    len(stripped) > 8 and
                    not stripped.startswith('[') and
                    not stripped.startswith('![') and
                    not stripped.startswith('http') and
                    not stripped.isdigit() and
                    not stripped in ['Translate', 'views', 'Log in', 'Thread', 'Sorry, we\'re having trouble playing this video.', 'Learn more'] and
                    not re.match(r'^\d+[dhm]$', stripped) and
                    not re.match(r'^\d+$', stripped)):
                    
                    # 檢查這是否是分享的貼文
                    is_shared_post = False
                    for j in range(i + 1, min(i + 5, len(lines))):
                        next_line = lines[j].strip()
                        if ('profile picture' in next_line and self.target_username not in next_line):
                            is_shared_post = True
                            break
                    
                    if not is_shared_post:
                        return stripped
                
                # 如果遇到其他用戶的 profile picture，停止
                if 'profile picture' in stripped and self.target_username not in stripped:
                    break
        
        return None
    
    def _extract_main_post_from_structure(self, lines: List[str]) -> Optional[str]:
        """從結構化內容中提取主貼文 - 優先提取當前頁面的主要內容"""
        main_content_candidates = []
        
        # 策略1: 如果第一行就是回覆內容，優先使用它
        if lines and lines[0].strip().startswith('>>>'):
            reply_content = lines[0].strip()
            if len(reply_content) > 10:  # 確保有實質內容
                return reply_content
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # 跳過明顯的回覆標識（但如果是第一行已經處理過了）
            if i > 0 and (stripped.startswith('>>>') or stripped.startswith('回覆') or stripped.startswith('·Author')):
                continue
            
            # 尋找主貼文內容的模式
            if (stripped and 
                not stripped.startswith('[') and  # 跳過連結
                not stripped.startswith('![') and  # 跳過圖片
                not stripped.startswith('http') and  # 跳過URL
                not stripped.startswith('Log in') and  # 跳過登入提示
                not stripped.startswith('Thread') and  # 跳過Thread標題
                not stripped.startswith('gvmonthly') and  # 跳過用戶名
                not stripped.startswith('=') and  # 跳過分隔符
                not stripped.isdigit() and  # 跳過純數字
                not re.match(r'^\d+[dhm]$', stripped) and  # 跳過時間格式
                not stripped in ['Translate', 'views', 'Sorry, we\'re having trouble playing this video.', 'Learn more'] and  # 跳過特殊詞
                len(stripped) > 8):  # 內容要有一定長度
                
                # 檢查這是否可能是主貼文內容
                if self._is_likely_main_post_content(stripped, lines, i):
                    main_content_candidates.append(stripped)
        
        # 返回第一個合理的主貼文候選
        if main_content_candidates:
            return main_content_candidates[0]
        
        return None
    
    def _is_likely_main_post_content(self, content: str, lines: List[str], index: int) -> bool:
        """判斷內容是否可能是主貼文"""
        # 檢查後續是否有 "Translate" 標識（主貼文的典型結構）
        for j in range(index + 1, min(index + 3, len(lines))):
            if 'Translate' in lines[j]:
                return True
        
        # 檢查是否包含常見的主貼文特徵
        if (len(content) > 15 and  # 有一定長度
            not content.startswith('>>>') and  # 不是回覆
            not content.startswith('·') and  # 不是元數據
            ('!' in content or '?' in content or '。' in content or '，' in content)):  # 包含標點符號
            return True
        
        return False
    
    def _extract_content_fallback(self, lines: List[str]) -> Optional[str]:
        """備選內容提取方法"""
        content_start = -1
        for i, line in enumerate(lines):
            if 'Markdown Content:' in line:
                content_start = i + 1
                break
        
        if content_start == -1:
            return None
        
        content_lines = []
        for i in range(content_start, min(content_start + 15, len(lines))):
            line = lines[i].strip()
            if (line and 
                not line.startswith('[![Image') and 
                not line.startswith('[Image') and
                not line.startswith('>>>')):  # 排除回覆
                content_lines.append(line)
                
                # 如果找到了合理的內容就停止
                if len(content_lines) >= 2 and len(line) > 10:
                    break
        
        return '\n'.join(content_lines) if content_lines else None