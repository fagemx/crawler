"""
結構模板生成器
為每個識別出的結構模式生成詳細的創作模板
"""

import json
from typing import List, Dict, Any

from common.llm_manager import chat_completion
from common.llm_client import parse_llm_json_response


class StructureTemplater:
    """結構模板生成器"""
    
    def __init__(self):
        pass
    
    async def generate_structure_templates(self, posts_content: List[str], 
                                         pattern_analysis: Dict[str, Any],
                                         corpus_features: Dict[str, Any]) -> List[Dict[str, Any]]:
        """為每個結構模式生成創作模板"""
        templates = []
        patterns = pattern_analysis.get("identified_patterns", [])
        
        for pattern in patterns:
            pattern_name = pattern.get("pattern_name", "未知模式")
            structure_chars = pattern.get("structure_characteristics", {})
            sample_indices = pattern.get("sample_indices", [])
            confidence = pattern.get("confidence", 0.5)
            post_indices_all = pattern.get("post_indices", [])
            
            try:
                template = await self._generate_adaptive_structure_template(
                    pattern_name, structure_chars, posts_content, 
                    sample_indices, corpus_features, confidence,
                    post_indices_all=post_indices_all
                )
                
                templates.append({
                    "pattern_id": pattern.get("pattern_id"),
                    "pattern_name": pattern_name,
                    "template_type": "adaptive",
                    "confidence": confidence,
                    "structure_template": template
                })
                
            except Exception as e:
                print(f"結構模板生成錯誤 - 模式 {pattern_name}: {e}")
                continue
        
        return templates
    
    async def _generate_adaptive_structure_template(self, pattern_name: str, 
                                                   structure_chars: Dict[str, Any],
                                                   posts_content: List[str], 
                                                   sample_indices: List[int],
                                                   corpus_features: Dict[str, Any],
                                                   confidence: float,
                                                   post_indices_all: List[int] = None) -> Dict[str, Any]:
        """生成自適應結構模板"""
        
        # 獲取樣本貼文
        sample_posts = []
        for idx in sample_indices:
            if 0 <= idx - 1 < len(posts_content):
                sample_posts.append(posts_content[idx - 1])
        
        samples_text = "\n".join([f"樣本{i+1}: {post}" for i, post in enumerate(sample_posts)])
        
        # 根據語料庫特徵決定重點分析維度
        analysis_focus = self._determine_analysis_focus(structure_chars, corpus_features)
        
        prompt = f"""
根據結構模式「{pattern_name}」的特徵，請分析樣本並生成『結構-創作指引』JSON。
信心度：{confidence:.1%}

🧩 結構統計特徵：
{json.dumps(structure_chars, ensure_ascii=False)}

📚 樣本貼文：
{samples_text}

📖 語料庫背景：
{self._build_corpus_context(corpus_features)}

🎯 建議首要分析維度：{analysis_focus or "模型自行判斷"}

僅談「結構」與「表現手法」，嚴禁引用具體主題或情節。

================　JSON　================
{{
  "structure_guide": {{
    "length_profile": {{ 
      "總句數範圍": "X-Y句", 
      "平均每句字數": "A-B字",
      "總字數": "M-N字"
    }},
    "organization": {{ 
      "段落數量": "N1-N2段", 
      "每段句數": "S1-S2句",
      "特殊組織": "列點/對話/引用…(若有)"
    }},
    "rhythm": {{ 
      "節奏": "快/中/慢等", 
      "標點模式": "逗號/冒號/破折號/省略號…"
    }},
    "coherence": {{ 
      "連貫策略": ["時間順序","因果","對比","承接詞…"]
    }},
    "macro_blueprint": {{
      "structure_chain_example": ["功能1→功能2→功能3"],
      "micro_arc": "觸發→反應 / 情緒→具體化 (若適用)",
      "tension": "對比/停頓/強調詞 (若適用)",
      "completeness": "引用/鋪陳/收束三要素 (若適用)"
    }},
    "density": "資訊或情緒密度建議 (若適用)",
    "special_features": "本模式獨有的結構特徵",
    "sentence_types": {{ 
      "陳述": "P-Q%", "疑問": "R-S%", "感嘆": "T-U%"
    }}
  }},

  "paragraph_steps": [
    {{
      "功能": "此段落/句群的角色定位",
      "標準寫法": "常見措辭或語氣",
      "連貫語": ["例如","此外","最後"],
      "示例片段": "【占位符：不含任何主題詞】"
    }}
  ],

  "analysis_elements": {{
    "長句功能分類": ["敘事","評論","推論"],
    "長句組織模式": ["主句+細節+情緒", "因果/轉折"],
    "短句應用場景": ["收尾強調","節奏切換"],
    "連貫策略補充": ["每3-5句使用承接詞", "段首轉折"]
  }},

  "creation_guidance": {{
    "writing_steps": ["步驟1","步驟2","步驟3"],
    "style_constraints": ["字數/語氣/用詞限制"],
    "common_pitfalls": ["常錯1","常錯2"],
    "optimization_tips": ["技巧1","技巧2"]
  }},

  "applicability": {{
    "適用場景": ["可用於…"],
    "不適用": ["不建議於…"],
    "confidence_level": {confidence:.2f}
  }},

  "notes": "信心度、資料偏差或其他補充"
}}

⚠️ 規則（僅 4 條，減少束縛）
1. 只有「確實觀察到」的欄位才輸出；無則省略。
2. 數值一律用『範圍』表示 (如 8-15字)。
3. 全文不得出現具體主題詞/專有名詞。
4. 若信心度 < 0.65，notes 中標示『結構可靠性不足』並簡述原因。
"""

        messages = [
            {"role": "system", "content": "你是專業的結構分析師，請以繁體中文輸出，只關注『結構與表現手法』，嚴禁涉及主題/情節內容。"},
            {"role": "user", "content": prompt}
        ]
        
        try:
            content = await chat_completion(
                messages=messages,
                model="gemini-2.0-flash",
                temperature=0.2,
                max_tokens=2000,
                provider="gemini"
            )
            parsed = parse_llm_json_response(content)
            # 將樣本一併回傳，便於後續摘要不需再查資料
            if isinstance(parsed, dict):
                parsed.setdefault("sample_indices", sample_indices)
                parsed_samples = []
                for idx in sample_indices:
                    if 0 <= idx - 1 < len(posts_content):
                        parsed_samples.append({
                            "index": idx,
                            "content": posts_content[idx - 1]
                        })
                parsed.setdefault("samples", parsed_samples)
                # 同步回傳此模式覆蓋的所有貼文樣本，供摘要使用
                all_samples = []
                if post_indices_all:
                    for idx in post_indices_all:
                        if 0 <= idx - 1 < len(posts_content):
                            all_samples.append({
                                "index": idx,
                                "content": posts_content[idx - 1]
                            })
                parsed.setdefault("all_indices", post_indices_all or [])
                parsed.setdefault("all_samples", all_samples)
            return parsed
        except Exception as e:
            print(f"自適應結構模板生成錯誤: {e}")
            return {"error": f"無法生成結構模板: {str(e)}"}
    
    def _determine_analysis_focus(self, structure_chars: Dict[str, Any], 
                                corpus_features: Dict[str, Any]) -> str:
        """根據結構特徵和語料庫特徵決定分析重點"""
        focus_areas = []
        
        # 根據主導特徵決定重點
        dominant_feature = structure_chars.get("dominant_feature", "")
        
        if "對話" in dominant_feature:
            focus_areas.append("對話節奏與停頓")
        if "列點" in dominant_feature:
            focus_areas.append("列點組織與邏輯")
        if "引用" in dominant_feature:
            focus_areas.append("引用整合與層次")
        if "多段" in dominant_feature:
            focus_areas.append("段落銜接與弧線")
        if "單段" in dominant_feature:
            focus_areas.append("連貫性與密度")
        
        # 根據語料庫整體特徵調整
        avg_length = corpus_features.get("avg_length", 0)
        if avg_length <= 50:
            focus_areas.append("微弧線與張力")
        elif avg_length >= 200:
            focus_areas.append("敘事弧線與深度")
        
        return "、".join(focus_areas) if focus_areas else "基本結構特徵"
    
    def _build_corpus_context(self, corpus_features: Dict[str, Any]) -> str:
        """構建語料庫背景描述"""
        context_parts = []
        
        total_posts = corpus_features.get("total_posts", 0)
        avg_length = corpus_features.get("avg_length", 0)
        
        context_parts.append(f"語料庫規模：{total_posts}篇，平均長度{avg_length:.0f}字")
        
        # 主要特徵
        main_features = []
        if corpus_features.get("has_dialogue"):
            main_features.append("含對話")
        if corpus_features.get("has_bullet_points"):
            main_features.append("含列點")
        if corpus_features.get("has_multi_paragraph"):
            main_features.append("多段為主")
        else:
            main_features.append("單段為主")
        
        if main_features:
            context_parts.append(f"主要特徵：{', '.join(main_features)}")
        
        return "；".join(context_parts)
