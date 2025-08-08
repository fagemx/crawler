"""
批量分析協調器
統籌語料庫分析、模式生成和結構模板生成的完整流程
"""

import json
from typing import List, Dict, Any
from datetime import datetime

from .corpus_analyzer import CorpusAnalyzer
from .pattern_generator import PatternGenerator
from .structure_templater import StructureTemplater
from common.llm_manager import chat_completion
from common.llm_client import parse_llm_json_response


class BatchAnalyzer:
    """批量結構分析協調器"""
    
    def __init__(self):
        self.corpus_analyzer = CorpusAnalyzer()
        self.pattern_generator = PatternGenerator()
        self.structure_templater = StructureTemplater()
    
    async def analyze_batch_structure(self, posts_content: List[str], 
                                    username: str = "unknown") -> Dict[str, Any]:
        """執行完整的批量結構分析流程"""
        try:
            # 第一階段：語料庫特徵分析
            corpus_features = self.corpus_analyzer.analyze_corpus_features(posts_content)
            
            # 第二階段：動態模式生成
            min_groups = self._decide_min_groups(len(posts_content))
            applicable_patterns = self.pattern_generator.generate_applicable_patterns(
                corpus_features, min_groups
            )
            
            # 第三階段：LLM智能分組
            pattern_analysis = await self._intelligent_pattern_recognition(
                posts_content, applicable_patterns, corpus_features
            )
            
            # 第四階段：結構模板生成
            structure_templates = await self.structure_templater.generate_structure_templates(
                posts_content, pattern_analysis, corpus_features
            )
            
            return {
                "status": "success",
                "username": username,
                "analysis_type": "intelligent_batch_structure_analysis",
                "pattern_count": len(pattern_analysis.get("identified_patterns", [])),
                "total_posts": len(posts_content),
                "corpus_features": corpus_features,
                "applicable_patterns": applicable_patterns,
                "pattern_analysis": pattern_analysis,
                "structure_templates": structure_templates,
                "analyzed_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                "status": "error", 
                "message": f"智能批量結構分析失敗: {str(e)}",
                "error_details": str(e)
            }
    
    def _decide_min_groups(self, total_posts: int) -> int:
        """根據總貼文數決定最低分組數"""
        if total_posts >= 100:
            return 10
        elif total_posts >= 50:
            return 8
        elif total_posts >= 25:
            return 5
        else:
            return 3
    
    async def _intelligent_pattern_recognition(self, posts_content: List[str], 
                                             applicable_patterns: List[Dict[str, Any]], 
                                             corpus_features: Dict[str, Any]) -> Dict[str, Any]:
        """基於語料庫特徵的智能模式識別"""
        
        formatted_posts = self._format_multiple_posts(posts_content)
        
        # 構建特徵描述
        features_desc = self._build_features_description(corpus_features)
        patterns_desc = self._build_patterns_description(applicable_patterns)
        
        prompt = f"""根據語料庫特徵分析結果，將{len(posts_content)}篇貼文智能分組到合適的結構模式中。

{formatted_posts}

🔍 語料庫特徵分析結果：
{features_desc}

📋 建議的適用模式：
{patterns_desc}

🎯 分組要求：
1. 僅將貼文分配到確實適用的模式中（某些模式可能沒有對應貼文）
2. 允許同一篇貼文屬於多個模式（重疊覆蓋）
3. 模式命名須基於實際觀察到的結構特徵
4. 每個有效模式至少包含3篇貼文，否則說明原因
5. 必須覆蓋所有貼文，不可遺漏

回應格式：
{{
  "analysis_summary": {{
    "total_posts": {len(posts_content)},
    "applicable_patterns_count": {len(applicable_patterns)},
    "feature_based_grouping": true,
    "overlap_allowed": true
  }},
  "identified_patterns": [
    {{
      "pattern_id": "A",
      "pattern_name": "基於實際特徵的命名",
      "post_indices": [1, 3, 7, 12],
      "post_count": 4,
      "structure_characteristics": {{
        "dominant_feature": "主導特徵描述",
        "句數範圍": "X-Y句",
        "字數範圍": "A-B字",
        "段落特徵": "實際觀察結果",
        "特殊標記": "對話/列點/引用等（如有）",
        "節奏特徵": "基於實際分析"
      }},
      "confidence": 0.85,
      "sample_indices": [3, 7],
      "notes": "基於語料庫特徵的分組理由"
    }}
  ],
  "unused_patterns": [
    {{
      "pattern_name": "未使用的模式名",
      "reason": "語料庫中無對應特徵"
    }}
  ]
}}"""

        messages = [
            {"role": "system", "content": "你是專業的結構模式識別專家，擅長根據語料庫特徵進行智能分組，避免生成不存在的模式。"},
            {"role": "user", "content": prompt}
        ]
        
        try:
            content = await chat_completion(
                messages=messages,
                model="gemini-2.0-flash",
                temperature=0.3,
                max_tokens=3000,
                provider="gemini"
            )
            result = parse_llm_json_response(content)
            
            # 驗證結果的合理性
            self._validate_pattern_analysis(result, applicable_patterns, posts_content)
            
            return result
            
        except Exception as e:
            print(f"智能模式識別錯誤: {e}")
            return {
                "error": f"智能模式識別失敗: {str(e)}",
                "fallback": "使用基本分組策略"
            }
    
    def _format_multiple_posts(self, posts_content: List[str]) -> str:
        """格式化多篇貼文內容"""
        formatted_posts = []
        for i, content in enumerate(posts_content, 1):
            formatted_posts.append(f"【貼文 {i:02d}】\n{content}")
        return "\n\n" + "="*50 + "\n\n".join(formatted_posts)
    
    def _build_features_description(self, corpus_features: Dict[str, Any]) -> str:
        """構建特徵描述"""
        features_list = []
        
        if corpus_features.get("has_dialogue"):
            rate = corpus_features["feature_coverage"]["dialogue_rate"]
            features_list.append(f"✅ 對話特徵：{len(corpus_features['dialogue_posts'])}篇貼文含對話 ({rate:.1%})")
        else:
            features_list.append("❌ 對話特徵：語料庫中無明顯對話結構")
        
        if corpus_features.get("has_bullet_points"):
            rate = corpus_features["feature_coverage"]["bullet_rate"]
            features_list.append(f"✅ 列點特徵：{len(corpus_features['bullet_posts'])}篇貼文含列點 ({rate:.1%})")
        else:
            features_list.append("❌ 列點特徵：語料庫中無列點結構")
        
        if corpus_features.get("has_quotes"):
            rate = corpus_features["feature_coverage"]["quote_rate"]
            features_list.append(f"✅ 引用特徵：{len(corpus_features['quote_posts'])}篇貼文含引用 ({rate:.1%})")
        else:
            features_list.append("❌ 引用特徵：語料庫中無引用結構")
        
        if corpus_features.get("has_multi_paragraph"):
            rate = corpus_features["feature_coverage"]["multi_paragraph_rate"]
            features_list.append(f"✅ 多段特徵：{len(corpus_features['multi_paragraph_posts'])}篇貼文為多段 ({rate:.1%})")
        else:
            features_list.append("❌ 多段特徵：語料庫主要為單段結構")
        
        # 長度分布
        length_dist = corpus_features.get("length_distribution", {})
        features_list.append(f"📏 長度分布：{dict(length_dist)}")
        
        return "\n".join(features_list)
    
    def _build_patterns_description(self, applicable_patterns: List[Dict[str, Any]]) -> str:
        """構建模式描述"""
        patterns_list = []
        
        for pattern in applicable_patterns:
            confidence = pattern.get("confidence", 0.5)
            estimated_posts = pattern.get("estimated_posts", 0)
            patterns_list.append(
                f"• {pattern['pattern_name']} (信心度: {confidence:.1%}, 預估: {estimated_posts}篇)"
            )
        
        return "\n".join(patterns_list)
    
    def _validate_pattern_analysis(self, result: Dict[str, Any], 
                                 applicable_patterns: List[Dict[str, Any]], 
                                 posts_content: List[str]):
        """驗證模式分析結果的合理性"""
        if "identified_patterns" not in result:
            raise ValueError("LLM未返回identified_patterns")
        
        patterns = result["identified_patterns"]
        if len(patterns) == 0:
            raise ValueError("LLM未識別出任何模式")
        
        # 檢查是否所有貼文都被覆蓋
        covered_posts = set()
        for pattern in patterns:
            post_indices = pattern.get("post_indices", [])
            covered_posts.update(post_indices)
        
        all_posts = set(range(1, len(posts_content) + 1))
        if not all_posts.issubset(covered_posts):
            missing = all_posts - covered_posts
            print(f"警告：貼文 {missing} 未被任何模式覆蓋")
        
        print(f"✅ 模式驗證完成：{len(patterns)}個模式，覆蓋{len(covered_posts)}篇貼文")
