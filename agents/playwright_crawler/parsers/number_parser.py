"""
統一數字解析工具

從各種格式的文字中提取數字：
- K/M/萬/億 等縮寫
- 帶逗號的數字
- 嵌套字典結構
"""

import re
import logging
from typing import Optional


def parse_number(val):
    """
    統一解析各種數字格式 → int
    - int / float 直接回傳
    - dict 會嘗試抓 'count'、'total'、第一個 value
    - 其餘字串走 K / M / 萬 / 逗號 流程
    """
    # 1) 已經是數值
    if isinstance(val, (int, float)):
        return int(val)
    
    # 2) 如果是 dict 先挖數字再遞迴
    if isinstance(val, dict):
        for key in ("count", "total", "value"):
            if key in val:
                return parse_number(val[key])
        # 找不到常見鍵 → 抓第一個 value
        if val:
            return parse_number(next(iter(val.values())))
        return 0  # 空 dict
    
    # 3) None 或空字串
    if not val:
        return 0
    
    try:
        # --- 以下跟原本一樣 ---
        text = str(val).strip().replace('&nbsp;', ' ')
        text = re.sub(r'串文\s*', '', text)
        text = re.sub(r'次瀏覽.*$', '', text)
        text = re.sub(r'views?.*$', '', text, flags=re.IGNORECASE).strip()
        
        # 中文萬 / 億
        if '萬' in text:
            m = re.search(r'([\d.,]+)\s*萬', text)
            if m: 
                return int(float(m.group(1).replace(',', '')) * 1e4)
        if '億' in text:
            m = re.search(r'([\d.,]+)\s*億', text)
            if m: 
                return int(float(m.group(1).replace(',', '')) * 1e8)
        
        # 英文 K / M
        up = text.upper()
        if 'M' in up:
            m = re.search(r'([\d.,]+)\s*M', up)
            if m: 
                return int(float(m.group(1).replace(',', '')) * 1e6)
        if 'K' in up:
            m = re.search(r'([\d.,]+)\s*K', up)
            if m: 
                return int(float(m.group(1).replace(',', '')) * 1e3)
        
        # 單純數字含逗號
        m = re.search(r'[\d,]+', text)
        return int(m.group(0).replace(',', '')) if m else 0
        
    except (ValueError, IndexError) as e:
        logging.debug(f"⚠️ 無法解析數字: '{val}' - {e}")
        return 0


def parse_views_text(text: Optional[str]) -> Optional[int]:
    """將 '161.9萬次瀏覽' 或 '4 萬次瀏覽' 或 '1.2M views' 這類文字轉換為整數"""
    if not text:
        return None
    try:
        original_text = text
        
        # 移除不必要的文字，保留數字和單位
        text = re.sub(r'串文\s*', '', text)  # 移除 "串文"
        
        # 處理中文格式：1.2萬、4 萬次瀏覽、5000次瀏覽
        if '萬' in text:
            match = re.search(r'([\d.]+)\s*萬', text)  # 允許數字和萬之間有空格
            if match:
                return int(float(match.group(1)) * 10000)
        elif '億' in text:
            match = re.search(r'([\d.]+)\s*億', text)  # 允許數字和億之間有空格
            if match:
                return int(float(match.group(1)) * 100000000)
        
        # 處理英文格式：1.2M views, 500K views
        text_upper = text.upper()
        if 'M' in text_upper:
            match = re.search(r'([\d.]+)M', text_upper)
            if match:
                return int(float(match.group(1)) * 1000000)
        elif 'K' in text_upper:
            match = re.search(r'([\d.]+)K', text_upper)
            if match:
                return int(float(match.group(1)) * 1000)
        
        # 處理純數字格式（可能包含逗號）
        match = re.search(r'[\d,]+', text)
        if match:
            return int(match.group(0).replace(',', ''))
        
        logging.debug(f"🔍 無法解析瀏覽數文字: '{original_text}'")
        return None
        
    except (ValueError, IndexError) as e:
        logging.warning(f"⚠️ 無法解析瀏覽數文字: '{text}' - {e}")
        return None