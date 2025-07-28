import logging
from typing import List, Dict, Any, Optional

def first_of(obj: Dict[str, Any], *keys: List[Any]) -> Optional[Any]:
    """
    多鍵 fallback 機制：依序嘗試多個可能的鍵名，回傳第一個非空值。
    支援巢狀鍵：["parent", "child"] 會取 obj["parent"]["child"]
    """
    if not isinstance(obj, dict):
        return None

    for key in keys:
        try:
            if isinstance(key, (list, tuple)):
                # 巢狀鍵處理
                value = obj
                for sub_key in key:
                    if not isinstance(value, dict) or sub_key not in value:
                        value = None
                        break
                    value = value[sub_key]
            else:
                # 單一鍵處理
                value = obj.get(key)
            
            # 我們只關心值是否存在，即使是 0 或 False 也算有效值
            if value is not None:
                return value
        except (KeyError, TypeError, AttributeError):
            continue
    return None

def parse_thread_item(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    在 thread_item 裡自動找到真正的貼文 dict (通常是 `post` 或 `media` 物件)。
    支援不同版本的 GraphQL 結構變化。
    回傳含有 pk/id 的那層。
    """
    if not isinstance(item, dict):
        return None
        
    # 1) 傳統結構
    if 'post' in item and isinstance(item['post'], dict):
        return item['post']
        
    # 2) 新版結構：post_info / postInfo / postV2
    for key in ('post_info', 'postInfo', 'postV2', 'media_data', 'thread_data'):
        if key in item and isinstance(item[key], dict):
            return item[key]
    
    # 3) 深度搜尋：找第一個有 pk 或 id 的子 dict
    # (這種情況很少見，但作為最後的保險)
    def search_for_post(obj, max_depth=3):
        if max_depth <= 0:
            return None
            
        if isinstance(obj, dict):
            # 檢查當前層是否為貼文物件的特徵
            if ('pk' in obj or 'id' in obj) and 'user' in obj:
                return obj
            # 遞歸搜尋子物件
            for value in obj.values():
                result = search_for_post(value, max_depth - 1)
                if result:
                    return result
        elif isinstance(obj, list) and obj:
            # 搜尋列表中的第一個元素
            return search_for_post(obj[0], max_depth - 1)
            
        return None
    
    return search_for_post(item)

def generate_post_url(username: str, code: str) -> str:
    """產生標準的 Threads 貼文 URL。"""
    return f"https://www.threads.com/@{username}/post/{code}"

def get_best_image_url(candidates: List[Dict[str, Any]]) -> Optional[str]:
    """從候選列表中選擇最佳圖片 URL (通常是寬度最大的)。"""
    if not isinstance(candidates, list) or not candidates:
        return None
    try:
        # 過濾掉非字典或缺少 'width' 的項目
        valid_candidates = [c for c in candidates if isinstance(c, dict) and 'width' in c and 'url' in c]
        if not valid_candidates:
            return None
        best_candidate = max(valid_candidates, key=lambda c: c.get('width', 0))
        return best_candidate.get('url')
    except (TypeError, ValueError) as e:
        logging.warning(f"解析最佳圖片 URL 時出錯: {e}")
        return None

def get_best_video_url(candidates: List[Dict[str, Any]], prefer_mp4: bool = True) -> Optional[str]:
    """從候選列表中選擇最佳影片 URL。"""
    if not isinstance(candidates, list) or not candidates:
        return None
    
    try:
        valid_candidates = [c for c in candidates if isinstance(c, dict) and 'width' in c and 'url' in c]
        if not valid_candidates:
            return None

        if prefer_mp4:
            mp4_candidates = [c for c in valid_candidates if c.get('url', '').endswith('.mp4')]
            if mp4_candidates:
                return max(mp4_candidates, key=lambda c: c.get('width', 0)).get('url')
            
        # Fallback to highest quality if no mp4 found or not preferred
        best_candidate = max(valid_candidates, key=lambda c: c.get('width', 0))
        return best_candidate.get('url')
    except (TypeError, ValueError) as e:
        logging.warning(f"解析最佳影片 URL 時出錯: {e}")
        return None 