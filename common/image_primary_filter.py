"""
主貼圖規則篩選器

提供快速、零推論成本的規則打分，協助判斷圖片是否為貼文主圖。

輸入記錄需要包含：width、height、file_size、original_url（可選）。
輸出：score 介於 0~1、reason 簡短字串。
"""

from typing import Dict, Tuple


def _safe_num(value, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def compute_rule_score(record: Dict) -> Tuple[float, str]:
    """
    根據尺寸、檔案大小、長寬比與 URL 模式，計算主貼圖分數。
    """
    width = _safe_num(record.get("width"))
    height = _safe_num(record.get("height"))
    file_size = _safe_num(record.get("file_size"))
    url = (record.get("original_url") or "").lower()

    if width <= 0 or height <= 0:
        return 0.2, "missing_size"

    area = width * height
    short_side = min(width, height)
    aspect = (width / height) if height else 1.0

    score = 1.0
    reason_parts = []

    # 極小尺寸/面積 → 大幅降權
    if short_side < 200 or area < 80_000:
        score -= 0.6
        reason_parts.append("tiny")
    elif short_side < 300 or area < 120_000:
        score -= 0.4
        reason_parts.append("small")

    # 檔案大小過小 → 降權（常見縮圖/表情）
    if file_size and file_size < 40_000:
        score -= 0.4
        reason_parts.append("very_small_file")
    elif file_size and file_size < 80_000:
        score -= 0.2
        reason_parts.append("small_file")

    # 長寬比極端（常見截圖/拼圖/長圖）
    if aspect < 0.5 or aspect > 2.0:
        score -= 0.2
        reason_parts.append("extreme_ratio")

    # URL 模式簡單排除：頭像/表情/emoji 等關鍵詞
    bad_tokens = ["avatar", "profile", "emoji", "sticker", "icon"]
    if any(t in url for t in bad_tokens):
        score -= 0.3
        reason_parts.append("url_pattern")

    # 規範到 0~1
    score = max(0.0, min(1.0, score))
    reason = ",".join(reason_parts) if reason_parts else "ok"
    return score, reason


def decide_is_primary(score: float, threshold: float = 0.7) -> bool:
    return score >= threshold


