"""
動態模式生成器
根據語料庫特徵動態生成適用的結構模式，避免硬編碼
"""

from typing import List, Dict, Any
import random


class PatternGenerator:
    """動態結構模式生成器"""
    
    def __init__(self):
        # 模式模板庫（只有在對應特徵存在時才會被使用）
        self.pattern_templates = {
            "dialogue": {
                "name_variants": ["對話插入型", "對話引用型", "引述交流型"],
                "characteristics": ["含對話標記", "停頓節奏明顯", "語氣轉換"],
                "detection_rule": "contains_dialogue"
            },
            "bullet_points": {
                "name_variants": ["列點摘要型", "條列展示型", "要點整理型"],
                "characteristics": ["列點為主", "每點簡潔", "結構化表達"],
                "detection_rule": "contains_bullets"
            },
            "quotes": {
                "name_variants": ["引用補充型", "括號說明型", "註釋豐富型"],
                "characteristics": ["含引用/括號", "補述信息密度高", "層次分明"],
                "detection_rule": "contains_quotes"
            },
            "multi_paragraph": {
                "name_variants": ["多段敘事型", "分段展開型", "層次推進型"],
                "characteristics": ["多段組織", "段落間有轉折", "邏輯遞進"],
                "detection_rule": "multi_paragraph"
            },
            "single_paragraph": {
                "name_variants": ["單段直述型", "一氣呵成型", "連貫表達型"],
                "characteristics": ["單段為主", "連續敘述", "一次性表達"],
                "detection_rule": "single_paragraph"
            },
            "short_burst": {
                "name_variants": ["簡潔快節奏型", "短促表達型", "即時分享型"],
                "characteristics": ["句子簡短", "節奏明快", "信息密度高"],
                "detection_rule": "short_posts"
            },
            "long_form": {
                "name_variants": ["深度展開型", "詳細敘述型", "全面表達型"],
                "characteristics": ["內容豐富", "展開充分", "細節詳盡"],
                "detection_rule": "long_posts"
            },
            "emoji_rich": {
                "name_variants": ["表情符號型", "視覺增強型", "情感標記型"],
                "characteristics": ["emoji密度高", "視覺表達", "情感豐富"],
                "detection_rule": "contains_emoji"
            },
            "hashtag_focused": {
                "name_variants": ["標籤導向型", "話題標記型", "關鍵詞型"],
                "characteristics": ["含hashtag", "話題聚焦", "標籤使用"],
                "detection_rule": "contains_hashtags"
            }
        }
    
    def generate_applicable_patterns(self, corpus_features: Dict[str, Any], 
                                   min_groups: int = 5) -> List[Dict[str, Any]]:
        """根據語料庫特徵生成適用的模式"""
        applicable_patterns = []
        
        # 根據實際存在的特徵生成模式
        if corpus_features.get("has_dialogue"):
            applicable_patterns.append(self._create_pattern("dialogue", corpus_features))
        
        if corpus_features.get("has_bullet_points"):
            applicable_patterns.append(self._create_pattern("bullet_points", corpus_features))
        
        if corpus_features.get("has_quotes"):
            applicable_patterns.append(self._create_pattern("quotes", corpus_features))
        
        if corpus_features.get("has_emoji"):
            applicable_patterns.append(self._create_pattern("emoji_rich", corpus_features))
        
        if corpus_features.get("has_hashtags"):
            applicable_patterns.append(self._create_pattern("hashtag_focused", corpus_features))
        
        # 根據段落分布添加段落相關模式
        if corpus_features.get("has_multi_paragraph"):
            applicable_patterns.append(self._create_pattern("multi_paragraph", corpus_features))
        else:
            applicable_patterns.append(self._create_pattern("single_paragraph", corpus_features))
        
        # 根據長度分布添加長度相關模式
        length_dist = corpus_features.get("length_distribution", {})
        short_ratio = (length_dist.get("極短", 0) + length_dist.get("短", 0)) / corpus_features["total_posts"]
        long_ratio = (length_dist.get("長", 0) + length_dist.get("極長", 0)) / corpus_features["total_posts"]
        
        if short_ratio >= 0.3:
            applicable_patterns.append(self._create_pattern("short_burst", corpus_features))
        
        if long_ratio >= 0.2:
            applicable_patterns.append(self._create_pattern("long_form", corpus_features))
        
        # 確保至少有最小數量的模式
        while len(applicable_patterns) < min_groups:
            applicable_patterns.extend(self._generate_generic_patterns(corpus_features, min_groups - len(applicable_patterns)))
        
        # 隨機化模式順序和名稱
        self._randomize_patterns(applicable_patterns)
        
        return applicable_patterns[:min_groups + 2]  # 稍微超過最小數量
    
    def _create_pattern(self, pattern_type: str, corpus_features: Dict[str, Any]) -> Dict[str, Any]:
        """創建特定類型的模式"""
        template = self.pattern_templates[pattern_type]
        
        return {
            "pattern_type": pattern_type,
            "pattern_name": random.choice(template["name_variants"]),
            "characteristics": template["characteristics"].copy(),
            "detection_rule": template["detection_rule"],
            "estimated_posts": self._estimate_pattern_posts(pattern_type, corpus_features),
            "confidence": self._calculate_confidence(pattern_type, corpus_features)
        }
    
    def _estimate_pattern_posts(self, pattern_type: str, corpus_features: Dict[str, Any]) -> int:
        """估算模式包含的貼文數量"""
        total_posts = corpus_features["total_posts"]
        
        if pattern_type == "dialogue":
            return len(corpus_features.get("dialogue_posts", []))
        elif pattern_type == "bullet_points":
            return len(corpus_features.get("bullet_posts", []))
        elif pattern_type == "quotes":
            return len(corpus_features.get("quote_posts", []))
        elif pattern_type == "multi_paragraph":
            return len(corpus_features.get("multi_paragraph_posts", []))
        elif pattern_type == "single_paragraph":
            return total_posts - len(corpus_features.get("multi_paragraph_posts", []))
        elif pattern_type == "emoji_rich":
            return len(corpus_features.get("emoji_posts", []))
        elif pattern_type == "hashtag_focused":
            return len(corpus_features.get("hashtag_posts", []))
        elif pattern_type == "short_burst":
            length_dist = corpus_features.get("length_distribution", {})
            return length_dist.get("極短", 0) + length_dist.get("短", 0)
        elif pattern_type == "long_form":
            length_dist = corpus_features.get("length_distribution", {})
            return length_dist.get("長", 0) + length_dist.get("極長", 0)
        else:
            return max(3, total_posts // 5)  # 預設估算
    
    def _calculate_confidence(self, pattern_type: str, corpus_features: Dict[str, Any]) -> float:
        """計算模式的信心度"""
        feature_coverage = corpus_features.get("feature_coverage", {})
        
        confidence_map = {
            "dialogue": feature_coverage.get("dialogue_rate", 0),
            "bullet_points": feature_coverage.get("bullet_rate", 0),
            "quotes": feature_coverage.get("quote_rate", 0),
            "emoji_rich": feature_coverage.get("emoji_rate", 0),
            "hashtag_focused": feature_coverage.get("hashtag_rate", 0),
            "multi_paragraph": feature_coverage.get("multi_paragraph_rate", 0),
        }
        
        return confidence_map.get(pattern_type, 0.5)
    
    def _generate_generic_patterns(self, corpus_features: Dict[str, Any], count: int) -> List[Dict[str, Any]]:
        """生成通用模式以達到最小數量要求"""
        generic_patterns = []
        
        # 根據句數分布生成模式
        sentence_dist = corpus_features.get("sentence_distribution", {})
        
        for i in range(count):
            if i == 0:
                name = "簡潔表達型"
                chars = ["句數較少", "表達直接", "重點突出"]
            elif i == 1:
                name = "平衡敘述型"
                chars = ["句數適中", "結構平衡", "邏輯清晰"]
            else:
                name = f"特色模式{chr(ord('A') + i)}"
                chars = ["結構特殊", "風格獨特", "表達方式特別"]
            
            generic_patterns.append({
                "pattern_type": f"generic_{i}",
                "pattern_name": name,
                "characteristics": chars,
                "detection_rule": "generic_grouping",
                "estimated_posts": max(3, corpus_features["total_posts"] // (count + 3)),
                "confidence": 0.3
            })
        
        return generic_patterns
    
    def _randomize_patterns(self, patterns: List[Dict[str, Any]]):
        """隨機化模式順序和某些屬性"""
        random.shuffle(patterns)
        
        # 為每個模式添加隨機ID
        for i, pattern in enumerate(patterns):
            pattern["pattern_id"] = chr(ord('A') + i)
    
    def get_pattern_assignment_strategy(self, patterns: List[Dict[str, Any]], 
                                      posts_content: List[str]) -> Dict[str, Any]:
        """獲取貼文分配策略"""
        return {
            "strategy": "feature_based_assignment",
            "allow_overlap": True,
            "min_posts_per_pattern": 3,
            "confidence_threshold": 0.2,
            "patterns": patterns,
            "assignment_rules": {
                pattern["pattern_id"]: pattern["detection_rule"] 
                for pattern in patterns
            }
        }
