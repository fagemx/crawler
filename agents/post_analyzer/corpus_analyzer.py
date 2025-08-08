"""
語料庫特徵檢測器
分析貼文集合中實際存在的結構特徵，避免生成不存在的模式
"""

import re
from typing import List, Dict, Any
from collections import Counter


class CorpusAnalyzer:
    """語料庫結構特徵分析器"""
    
    def __init__(self):
        # 對話檢測規則
        self.dialogue_patterns = [
            r'["「『].*?["」』]',  # 引號對話
            r'：\s*[^：\n]{1,50}[。！？]',  # 冒號對話
            r'說[：:\s]*[^：\n]{1,50}[。！？]',  # "說："對話
        ]
        
        # 列點檢測規則
        self.bullet_patterns = [
            r'[•·・]',  # 圓點
            r'^\s*\d+[.、]\s',  # 數字列點
            r'^\s*[一二三四五六七八九十][.、]\s',  # 中文數字
            r'^\s*[①②③④⑤⑥⑦⑧⑨⑩]\s',  # 圓圈數字
            r'^\s*[-*+]\s',  # 短橫線
        ]
        
        # 引用檢測規則
        self.quote_patterns = [
            r'[（(].*?[）)]',  # 括號補充
            r'【.*?】',  # 方括號
            r'〈.*?〉',  # 書名號
            r'『.*?』',  # 重引號
        ]
    
    def analyze_corpus_features(self, posts_content: List[str]) -> Dict[str, Any]:
        """分析語料庫的結構特徵"""
        total_posts = len(posts_content)
        
        features = {
            # 基本統計
            "total_posts": total_posts,
            "avg_length": sum(len(post) for post in posts_content) / total_posts,
            
            # 結構特徵存在性
            "has_dialogue": False,
            "has_bullet_points": False,
            "has_quotes": False,
            "has_multi_paragraph": False,
            "has_emoji": False,
            "has_hashtags": False,
            
            # 詳細統計
            "dialogue_posts": [],
            "bullet_posts": [],
            "quote_posts": [],
            "multi_paragraph_posts": [],
            "emoji_posts": [],
            "hashtag_posts": [],
            
            # 句數分布
            "sentence_distribution": {},
            "paragraph_distribution": {},
            "length_distribution": {},
            
            # 標點符號模式
            "punctuation_density": {},
            "emoji_usage": {},
        }
        
        for i, post in enumerate(posts_content):
            self._analyze_single_post(post, i, features)
        
        # 計算比例和閾值判斷
        self._calculate_feature_thresholds(features)
        
        return features
    
    def _analyze_single_post(self, post: str, post_index: int, features: Dict[str, Any]):
        """分析單篇貼文的特徵"""
        
        # 對話檢測
        if self._has_dialogue(post):
            features["dialogue_posts"].append(post_index)
            features["has_dialogue"] = True
        
        # 列點檢測
        if self._has_bullet_points(post):
            features["bullet_posts"].append(post_index)
            features["has_bullet_points"] = True
        
        # 引用檢測
        if self._has_quotes(post):
            features["quote_posts"].append(post_index)
            features["has_quotes"] = True
        
        # 多段落檢測
        paragraphs = [p.strip() for p in post.split('\n') if p.strip()]
        if len(paragraphs) > 1:
            features["multi_paragraph_posts"].append(post_index)
            features["has_multi_paragraph"] = True
        
        # Emoji檢測
        if self._has_emoji(post):
            features["emoji_posts"].append(post_index)
            features["has_emoji"] = True
        
        # Hashtag檢測
        if '#' in post:
            features["hashtag_posts"].append(post_index)
            features["has_hashtags"] = True
        
        # 句數統計
        sentences = self._count_sentences(post)
        self._update_distribution(features["sentence_distribution"], sentences)
        
        # 段落數統計
        self._update_distribution(features["paragraph_distribution"], len(paragraphs))
        
        # 長度統計
        length_category = self._categorize_length(len(post))
        self._update_distribution(features["length_distribution"], length_category)
    
    def _has_dialogue(self, post: str) -> bool:
        """檢測是否包含對話"""
        for pattern in self.dialogue_patterns:
            if re.search(pattern, post, re.MULTILINE):
                return True
        return False
    
    def _has_bullet_points(self, post: str) -> bool:
        """檢測是否包含列點"""
        for pattern in self.bullet_patterns:
            if re.search(pattern, post, re.MULTILINE):
                return True
        return False
    
    def _has_quotes(self, post: str) -> bool:
        """檢測是否包含引用或補充說明"""
        for pattern in self.quote_patterns:
            if re.search(pattern, post):
                return True
        return False
    
    def _has_emoji(self, post: str) -> bool:
        """檢測是否包含emoji"""
        # 簡單的emoji檢測（可以更精確）
        emoji_pattern = r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]'
        return bool(re.search(emoji_pattern, post))
    
    def _count_sentences(self, post: str) -> int:
        """計算句子數量"""
        sentence_endings = r'[。！？.!?]'
        sentences = re.split(sentence_endings, post)
        return len([s for s in sentences if s.strip()])
    
    def _categorize_length(self, length: int) -> str:
        """將長度分類"""
        if length <= 30:
            return "極短"
        elif length <= 80:
            return "短"
        elif length <= 200:
            return "中"
        elif length <= 500:
            return "長"
        else:
            return "極長"
    
    def _update_distribution(self, distribution: Dict, key):
        """更新分布統計"""
        distribution[str(key)] = distribution.get(str(key), 0) + 1
    
    def _calculate_feature_thresholds(self, features: Dict[str, Any]):
        """計算特徵的閾值判斷"""
        total_posts = features["total_posts"]
        
        # 只有當至少10%的貼文包含某特徵時，才認為該特徵存在
        threshold = max(2, total_posts * 0.1)
        
        features["has_dialogue"] = len(features["dialogue_posts"]) >= threshold
        features["has_bullet_points"] = len(features["bullet_posts"]) >= threshold
        features["has_quotes"] = len(features["quote_posts"]) >= threshold
        features["has_multi_paragraph"] = len(features["multi_paragraph_posts"]) >= threshold
        features["has_emoji"] = len(features["emoji_posts"]) >= threshold
        features["has_hashtags"] = len(features["hashtag_posts"]) >= threshold
        
        # 添加特徵覆蓋率
        features["feature_coverage"] = {
            "dialogue_rate": len(features["dialogue_posts"]) / total_posts,
            "bullet_rate": len(features["bullet_posts"]) / total_posts,
            "quote_rate": len(features["quote_posts"]) / total_posts,
            "multi_paragraph_rate": len(features["multi_paragraph_posts"]) / total_posts,
            "emoji_rate": len(features["emoji_posts"]) / total_posts,
            "hashtag_rate": len(features["hashtag_posts"]) / total_posts,
        }
    
    def get_dominant_patterns(self, features: Dict[str, Any]) -> List[str]:
        """獲取語料庫中的主導模式"""
        dominant = []
        
        if features["has_dialogue"]:
            dominant.append("對話插入型")
        
        if features["has_bullet_points"]:
            dominant.append("列點摘要型")
        
        if features["has_quotes"]:
            dominant.append("引用補充型")
        
        if features["has_multi_paragraph"]:
            dominant.append("多段敘事型")
        else:
            dominant.append("單段直述型")
        
        # 根據長度分布添加長度相關模式
        length_dist = features["length_distribution"]
        if length_dist.get("極短", 0) + length_dist.get("短", 0) > features["total_posts"] * 0.3:
            dominant.append("簡潔快節奏型")
        
        if length_dist.get("長", 0) + length_dist.get("極長", 0) > features["total_posts"] * 0.2:
            dominant.append("深度展開型")
        
        return dominant
