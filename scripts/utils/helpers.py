#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
輔助工具函數
"""

import re
from typing import Optional

def safe_print(msg, fallback_msg=None):
    """安全的打印函數，避免Unicode編碼錯誤"""
    try:
        print(msg)
    except UnicodeEncodeError:
        if fallback_msg:
            print(fallback_msg)
        else:
            # 移除所有非ASCII字符的安全版本
            ascii_msg = msg.encode('ascii', 'ignore').decode('ascii')
            print(ascii_msg if ascii_msg.strip() else "[編碼錯誤 - 訊息無法顯示]")

def normalize_content(text: str) -> str:
    """內容標準化"""
    NBSP = "\u00A0"
    text = text.replace(NBSP, " ").replace("\u2002", " ").replace("\u2003", " ")
    text = text.replace("\u2009", " ").replace("\u200A", " ").replace("\u3000", " ").replace("\t", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text

def validate_views_format(views: str) -> bool:
    """驗證觀看數格式"""
    if not views:
        return False
    
    # 檢查是否為數字或帶K/M/B後綴的數字
    pattern = r'^\d+(?:\.\d+)?[KMB]?$'
    
    # 移除逗號後檢查
    clean_views = views.replace(',', '')
    return bool(re.match(pattern, clean_views, re.IGNORECASE))

def convert_to_number(number_str: str) -> int:
    """將帶K/M/B後綴的數字轉換為整數"""
    if not number_str:
        return 0
    
    number_str = number_str.replace(',', '').upper()
    if number_str.endswith('K'): 
        return int(float(number_str[:-1]) * 1000)
    elif number_str.endswith('M'): 
        return int(float(number_str[:-1]) * 1000000)
    elif number_str.endswith('B'): 
        return int(float(number_str[:-1]) * 1000000000)
    else: 
        return int(number_str)