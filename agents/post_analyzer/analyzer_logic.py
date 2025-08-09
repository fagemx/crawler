import asyncio
import json
import re
import random
from typing import Dict, Any, List

from common.db_client import get_db_client
from common.settings import get_settings
from common.llm_manager import get_llm_manager, chat_completion
from common.llm_client import parse_llm_json_response
from datetime import datetime

class PostAnalyzerAgent:
    """
    Analyzes posts to extract success patterns based on different modes.
    """
    def __init__(self):
        self.settings = get_settings()
        self.llm_manager = get_llm_manager()
        
        # 🎲 隨機變化詞句庫
        self.analysis_variations = {
            "depth_words": ["深入", "細緻", "全面", "深度", "透徹", "詳盡"],
            "focus_words": ["精簡重點", "核心要點", "關鍵特徵", "重點摘要", "精華提煉", "要點歸納"],
            "theme_words": ["針對主題", "主題導向", "議題聚焦", "主旨分析", "話題中心", "主題切入"],
            "style_words": ["針對主題風格", "風格特色", "表達風格", "文字風格", "敘述風格", "呈現風格"],
            "analysis_angles": ["結構層面", "內容層面", "風格層面", "表達層面", "敘事層面", "組織層面"],
            "pattern_descriptors": ["典型模式", "常見形式", "主要類型", "核心樣式", "基本框架", "標準範式"]
        }

    def _get_random_variation(self, category: str) -> str:
        """獲取隨機變化詞句"""
        return random.choice(self.analysis_variations.get(category, [category]))
    
    def _get_random_pattern_count(self) -> int:
        """獲取隨機模式數量 (3-5)"""
        return random.randint(3, 5)
    
    def _decide_min_groups(self, total_posts: int) -> int:
        """根據總貼文數決定最低分組數（允許重疊覆蓋）"""
        if total_posts >= 100:
            return 10
        if total_posts >= 25:
            return 5
        return 3
    
    def _format_multiple_posts(self, posts_content: List[str]) -> str:
        """格式化多篇貼文內容"""
        formatted_posts = []
        for i, content in enumerate(posts_content, 1):
            formatted_posts.append(f"【貼文 {i:02d}】\n{content}")
        return "\n\n" + "="*50 + "\n\n".join(formatted_posts)

    # ========= 新增：短文/長文自適應的快速統計輔助 =========
    def _quick_text_stats(self, text: str) -> Dict[str, int]:
        """針對貼文做粗略統計，便於在提示詞中提供長度自適應線索。
        - char_count: 以字元數為準（含標點）
        - sentence_count: 以標點簡易切分（。.!?！？）
        - paragraph_count: 以空行切分
        """
        cleaned = (text or "").strip()
        char_count = len(cleaned)
        # 以常見終止符切分句子，過濾空白
        import re as _re
        sentences = [s for s in _re.split(r"[。\.\!\?！？]+", cleaned) if s and s.strip()]
        sentence_count = len(sentences)
        # 以空行切分段落
        paragraphs = [p for p in _re.split(r"\n\s*\n+", cleaned) if p and p.strip()]
        paragraph_count = len(paragraphs)
        return {
            "char_count": char_count,
            "sentence_count": sentence_count,
            "paragraph_count": paragraph_count,
        }

    def _extract_main_post(self, markdown: str) -> str:
        """
        Extracts the main post content by splitting at the first long separator.
        """
        if not markdown:
            return ""
        
        # Split by the most likely separator first
        if '===============' in markdown:
            return markdown.split('===============', 1)[0].strip()
        
        # Fallback to the other common separator
        if '---' in markdown:
            return markdown.split('---', 1)[0].strip()
        
        # If no separator is found, try to find the "views" indicator as a last resort
        match = re.search(r"\n\n\d+\s*(views|次查看)", markdown)
        if match:
            return markdown[:match.start()].strip()

        # If absolutely no separator is found, return the original text, but log a warning.
        print(f"Warning: No clear separator found in markdown. Using full content for URL (this may be incorrect).")
        return markdown.strip()


    async def _fetch_posts_content(self, post_urls: List[str]) -> List[str]:
        """Fetches the markdown content for a list of post URLs."""
        db_client = await get_db_client()
        posts = await db_client.get_posts_with_metrics(post_urls)
        # Extract only the main post content from the full markdown
        return [self._extract_main_post(post['markdown']) for post in posts if post and 'markdown' in post]

    async def _analyze_mode_1(self, posts_content: List[str]) -> Dict[str, Any]:
        """Mode 1: Quick rewrite analysis from a single post."""
        if not posts_content:
            return {}
        
        post_text = posts_content[0] # Use the first post for quick analysis
        
        prompt = f"""
        Analyze the following social media post and generate a simple, lightweight template for a quick rewrite.
        Focus on the basic structure: introduction, emotional expression, and conclusion.

        Post:
        ---
        {post_text}
        ---

        Based on this post, provide a template with three steps.
        Example output format:
        {{
            "analysis_type": "Quick Rewrite Template",
            "template": {{
                "summary": "Generates a lightweight template from a single post.",
                "steps": [
                    "Step 1: Brief introduction related to an event or topic.",
                    "Step 2: Expression of personal emotion or reaction.",
                    "Step 3: A concluding sentence, possibly humorous or self-deprecating."
                ]
            }}
        }}
        """
        
        print("\n--- [Mode 1] Prompt to be sent ---\n")
        print(prompt)
        print("\n-------------------------------------\n")

        messages = [{"role": "user", "content": prompt}]
        response = await self.llm_client.chat_completion(messages, temperature=0.2, usage_scene="content-analysis")
        
        try:
            content = response["choices"][0]["message"]["content"]
            return parse_llm_json_response(content)
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            print(f"Mode 1 - JSON Parsing Error: {e}")
            return {"error": "Failed to parse LLM response for mode 1."}


    async def _analyze_mode_2(self, posts_content: List[str]) -> Dict[str, Any]:
        """Mode 2: Style and structure analysis from multiple posts."""
        combined_posts = "\n\n---\n\n".join(posts_content)
        prompt = f"""
        Analyze the writing style and content structure from the following social media posts.
        Identify recurring patterns in tone, sentence structure, topics, and use of special elements like emojis or punctuation.
        Generate two distinct style templates based on your analysis.

        Posts:
        ---
        {combined_posts}
        ---

        Provide the output in a structured JSON format like this:
        {{
            "analysis_type": "Style & Structure Analysis",
            "templates": [
                {{
                    "name": "Style Template A",
                    "details": [
                        "Tone: Describe the primary tone.",
                        "Sentence Structure: Describe the sentence patterns.",
                        "Topics: List common topics.",
                        "Special Elements: Mention recurring emojis, symbols, or punctuation."
                    ]
                }},
                {{
                    "name": "Style Template B",
                    "details": [
                        "Tone: Describe a secondary or different tone.",
                        "Sentence Structure: Describe other sentence patterns observed.",
                        "Topics: List other common topics.",
                        "Special Elements: Mention other recurring elements."
                    ]
                }}
            ]
        }}
        """
        
        print("\n--- [Mode 2] Prompt to be sent ---\n")
        print(prompt)
        print("\n-------------------------------------\n")

        messages = [{"role": "user", "content": prompt}]
        response = await self.llm_client.chat_completion(messages, temperature=0.3, usage_scene="content-analysis")
        try:
            content = response["choices"][0]["message"]["content"]
            return parse_llm_json_response(content)
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            print(f"Mode 2 - JSON Parsing Error: {e}")
            return {"error": "Failed to parse LLM response for mode 2."}

    async def _analyze_mode_3(self, posts_content: List[str]) -> Dict[str, Any]:
        """Mode 3: In-depth multi-LLM analysis report."""
        combined_posts = "\n\n---\n\n".join(posts_content)
        
        # Get the list of models directly from the LLM client
        models_to_use = self.llm_client.models

        if not models_to_use:
            return {"error": "No models configured for multi-LLM analysis."}

        findings = []
        
        for model in models_to_use:
            prompt = f"""
            As a professional content strategist, perform an in-depth analysis of the following posts.
            Your analysis should be from your unique perspective as the '{model}' model.
            Identify the core emotional tone, language style, and content themes.
            Summarize your findings in a few key points.

            Posts:
            ---
            {combined_posts}
            ---

            Present your findings as a list of strings.
            """
            print(f"\n--- [Mode 3 - Model: {model}] Prompt to be sent ---\n")
            print(prompt)
            print("\n------------------------------------------------\n")

            messages = [{"role": "user", "content": prompt}]
            try:
                response = await self.llm_client.chat_completion(messages, model=model, temperature=0.5, usage_scene="content-analysis")
                content = response["choices"][0]["message"]["content"]
                findings.append({
                    "model": model,
                    "report": content.strip().split('\n') # Simple parsing
                })
            except Exception as e:
                findings.append({
                    "model": model,
                    "report": f"Error during analysis: {str(e)}"
                })
        
        # Generate a final summary and high-level template based on the findings
        final_summary_prompt = f"""
        Based on the analysis from multiple AI models, synthesize a final report and a high-level creative template.
        
        Analysis Reports:
        ---
        {json.dumps(findings, indent=2, ensure_ascii=False)}
        ---

        Synthesize these findings into:
        1. A brief summary of the author's overall style.
        2. A high-level, three-paragraph template for creating new content in this style.
        
        Provide the output in a structured JSON format:
        {{
            "analysis_type": "In-depth Multi-LLM Report",
            "synthesis": {{
                "summary": "Your synthesized summary here.",
                "high_level_template": {{
                    "paragraph_1": "Guideline for the first paragraph.",
                    "paragraph_2": "Guideline for the second paragraph.",
                    "paragraph_3": "Guideline for the third paragraph."
                }}
            }},
            "individual_reports": {json.dumps(findings)}
        }}
        """
        
        print("\n--- [Mode 3 - Final Summary] Prompt to be sent ---\n")
        print(final_summary_prompt)
        print("\n----------------------------------------------------\n")

        summary_messages = [{"role": "user", "content": final_summary_prompt}]
        summary_response = await self.llm_client.chat_completion(summary_messages, temperature=0.3, usage_scene="content-analysis")
        
        try:
            content = summary_response["choices"][0]["message"]["content"]
            return parse_llm_json_response(content)
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            print(f"Mode 3 - JSON Parsing Error: {e}")
            return {"error": "Failed to parse final summary response for mode 3."}


    async def analyze_posts(self, post_urls: List[str], analysis_mode: int) -> Dict[str, Any]:
        if not post_urls:
            return {"status": "error", "message": "No post URLs provided."}

        try:
            posts_content = await self._fetch_posts_content(post_urls)
            if not posts_content:
                return {"status": "error", "message": "Could not fetch content for the provided URLs."}

            result_data = {}
            if analysis_mode == 1:
                result_data = await self._analyze_mode_1(posts_content)
            elif analysis_mode == 2:
                result_data = await self._analyze_mode_2(posts_content)
            elif analysis_mode == 3:
                result_data = await self._analyze_mode_3(posts_content)
            else:
                return {"status": "error", "message": f"Invalid analysis mode: {analysis_mode}"}

            return {
                "status": "success",
                "analysis_mode": analysis_mode,
                "result": result_data,
                "message": f"Analysis for mode {analysis_mode} completed successfully."
            }

        except Exception as e:
            return {"status": "error", "message": f"An error occurred during analysis: {str(e)}"}
    
    async def analyze_post_structure(self, post_content: str, post_id: str, username: str) -> Dict[str, Any]:
        """執行單篇貼文的結構分析"""
        try:
            # 第一步：分析貼文結構特徵，填寫 post_structure_guide
            structure_guide = await self._analyze_post_structure_step1(post_content)
            
            # 第二步：根據表格生成簡短分析結果
            analysis_summary = await self._analyze_post_structure_step2(post_content, structure_guide)
            
            return {
                "status": "success",
                "post_id": post_id,
                "username": username,
                "post_structure_guide": structure_guide,
                "analysis_summary": analysis_summary,
                "analyzed_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {"status": "error", "message": f"結構分析失敗: {str(e)}"}
    
    async def _analyze_post_structure_step1(self, post_content: str) -> Dict[str, Any]:
        """第一步：分析貼文結構特徵"""
        # 動態長度統計，供提示詞自適應
        length_stats = self._quick_text_stats(post_content)
        char_count = length_stats["char_count"]
        sentence_count = length_stats["sentence_count"]
        paragraph_count = length_stats["paragraph_count"]

        prompt = f"""你是一個專業的文本結構分析師。請分析以下貼文的結構特徵，並填寫結構指南。

重要要求：
- 只許根據貼文「結構特徵」分析，不得帶入任何原文內容
- 各數值用合理範圍表示（例如「7-18句」、「30-45%」）
- 分析重點為「句子長短」、「段落組織」、「前後連貫」、「深度段落」
- 範例只用「結構鏈」，不可涉及具體內容或主題

【自適應規則（根據長度統計）】
- 參考統計：字元數={char_count}、句數≈{sentence_count}、段落數≈{paragraph_count}
- 若屬於短文（任一條件成立：字元數≤160 或 句數≤3 或 段落數≤1）：
  1) 允許「單段/極短多段」結構，句數範圍用小範圍表示（如 2-4 句）
  2) 「短句比例」可偏高；允許無明確「長句定義」，以簡短承接語替代
  3) 「連貫與銜接規則」以輕量化規則表述（如：每段首句承上、結尾用短句強化）
  4) 「敘事弧線」可使用「微弧線」：如「觸發→反應」或「提問→補充→收束」
- 若屬於長文（字元數≥600 或 句數≥10 或 段落數≥3）：
  1) 完整輸出段落類型分布與句型分類比例
  2) 補充更清晰的段落銜接與深度段落規則

【輸出一致性】
- 請盡量保留相同鍵名，數值用範圍表示；短文場景下仍需給出合乎短文的合理範圍。

貼文內容：
---
{post_content}
---

請按照以下格式分析並回應（JSON格式）：

{{
  "post_structure_guide": {{
    "總句數範圍": "X-Y句",
    "平均每句字數": "A-B字",
    "短句定義": "C-D字",
    "長句定義": "E-F字",
    "短句比例": "P1-P2%",
    "長句比例": "Q1-Q2%",
    "段落數量": "N1-N2段",
    "每段句數": "S1-S2句",
    "段落類型分布": [
      "事件敘述段（K1-K2段，每段M1-M2句）",
      "細節描寫/插曲段（L1-L2段，每段M3-M4句）",
      "評論推論段（1段，T1-T2句）",
      "情感收束/感謝段（1段，T3-T4句）"
    ],
    "句型分類比例": {{
      "敘事型（描述事件經過）": "X1-X2%",
      "細節描寫型（補充環境/人物細節）": "Y1-Y2%",
      "評論推論型（評論現象或推論結果）": "Z1-Z2%",
      "情感型（抒發感受、收尾強調）": "W1-W2%"
    }},
    "連貫與銜接規則": {{
      "長句應用": "長句應包含承接前文的連接詞（如『但』、『於是』、『最後』等）",
      "短句應用": "短句多用於收尾、強調、情緒表達",
      "段落銜接": "每段開頭盡量用轉折或承上啟下詞（如『接著』、『此外』、『最後』）",
      "深度段落": "每則貼文至少有一段包含評論或推論，用來展現思考深度"
    }},
    "敘事弧線": [
      "1. 事件起因/背景（開頭1段）",
      "2. 過程細節/插曲（中段1-3段）",
      "3. 評論/推論（倒數第2段）",
      "4. 情感收束或感謝（結尾1段）"
    ],
    "範例結構鏈": [
      "事件啟動→細節鋪陳→插曲/插話→評論/推論→情感收束"
    ]
  }},
  "analysis_elements": {{
    "長句功能分類": ["敘事型", "評論型", "推論型"],
    "長句組織模式": [
      "主句＋細節＋情緒補充",
      "描述＋個人感受",
      "因果/轉折/補述"
    ],
    "短句應用場景": [
      "斷點收尾",
      "情感強調",
      "節奏切換"
    ],
    "連貫策略": [
      "每3-5句有明顯承接詞",
      "每段開頭使用轉折/承接語",
      "短句銜接長句收尾"
    ]
  }}
}}"""

        messages = [
            {"role": "system", "content": "你是一個專業的文本結構分析師，擅長識別文本的結構特徵而不涉及內容細節。"},
            {"role": "user", "content": prompt}
        ]
        
        try:
            content = await chat_completion(
                messages=messages,
                model="gemini-2.0-flash",
                temperature=0.1,
                max_tokens=1000,
                provider="gemini"
            )
            result = parse_llm_json_response(content)
            # 如果有重複的 post_structure_guide 嵌套，提取內層的
            if "post_structure_guide" in result and "post_structure_guide" in result["post_structure_guide"]:
                return result["post_structure_guide"]
            return result
        except (json.JSONDecodeError, Exception) as e:
            print(f"結構分析步驟1 - LLM調用或JSON解析錯誤: {e}")
            return {"error": f"Failed to parse LLM response for structure analysis step 1: {str(e)}"}
    
    async def _analyze_post_structure_step2(self, post_content: str, structure_guide: Dict[str, Any]) -> str:
        """第二步：根據結構指南生成分析摘要"""
        # 動態長度統計，供提示詞自適應
        length_stats = self._quick_text_stats(post_content)
        char_count = length_stats["char_count"]
        sentence_count = length_stats["sentence_count"]
        paragraph_count = length_stats["paragraph_count"]

        prompt = f"""請根據「原貼文內容」與「第一階段結構分析」，以如下格式條列回應：

【自適應摘要規則】
- 參考統計：字元數={char_count}、句數≈{sentence_count}、段落數≈{paragraph_count}
- 若短文（字元數≤160 或 句數≤3 或 段落數≤1）：
  • 精煉輸出，整體不超過 6 條要點；避免冗長解釋
  • 強調「節奏/停頓、轉折語、收尾句型」等微結構建議
  • 允許以「微弧線」描述（如：觸發→反應 / 提問→補充→收束）
- 若長文：
  • 可保留完整條列，但仍以可操作為原則

原貼文內容：
---
{post_content}
---

第一階段結構分析結果：
{json.dumps(structure_guide, ensure_ascii=False, indent=2)}

請根據「原貼文內容」及「第一階段結構分析」，依以下格式回應：

【分析結果】

1.歸納本貼文的主題、情緒強度、段落安排、長短句節奏、用詞特色與連貫性，指出結構亮點及可優化空間。
2.觀察並描述發文者在本貼文所呈現的角色、身份或立場（如經驗分享者、專業服務者、參與者、觀察者、創作者、提問者等），簡述其語境、專業感、關注重點或話語角度。
3.判斷本貼文背後隱含的氛圍、價值觀或態度（如溫暖真誠、專業自信、幽默風趣、理性分析、呼籲行動等），補充內容特色與可再加強之處。
4.若有主題分散、情緒不足、段落失衡、句型單調、承接不足等現象，請具體指出。

【改寫建議】

1.依據分析，提出 3–5 點具體優化建議，可包含主題聚焦、段落分界、情緒補強、長短句調整、轉折語補充、評論或收尾段增強等。每點簡潔明確、可直接操作。
2.如角色偏專業或組織，建議強化專業術語、流程細節、成就展現；如角色偏經驗分享或自我表達，則可增強個人觀點、情感細節、互動引導等。

【發展方向】

1.判斷本貼文最接近哪一種風格方向（故事型／評論型／互動型／其他，如適用），僅選一種，簡述理由。
2.根據該方向，補充內容行銷、品牌經營、SEO/分發等策略建議（如角色形象建立、品牌信任感、話題／關鍵詞佈局、號召互動、專業證照露出、熱門標籤應用等）。
3.描述朝該方向延伸內容的寫作重點（1–2 句）。
4.舉一個符合該角色定位＋風格方向＋內容經營意圖的範例句子（可凸顯觀點、氛圍、關鍵詞、品牌調性、互動號召等）。

請以上述格式回應，每區塊標題明確，條列簡明，所有觀察皆須基於實際貼文內容自動判斷，不預設特定職業或語境，確保適用於各類 Threads 貼文優化、內容策略與品牌經營。
"""

        messages = [
            {"role": "system", "content": "你是 Threads 貼文結構優化助手，專門分析貼文結構並提供具體的改寫建議。"},
            {"role": "user", "content": prompt}
        ]
        
        try:
            content = await chat_completion(
                messages=messages,
                model="gemini-2.0-flash",
                temperature=0.2,
                max_tokens=8192,
                provider="gemini"
            )
            return content.strip()
        except Exception as e:
            print(f"結構分析步驟2 - LLM調用錯誤: {e}")
            return f"無法生成分析摘要: {str(e)}"
    
    # 🚀 智能批量結構分析方法
    async def analyze_batch_structure(self, posts_content: List[str], username: str = "unknown") -> Dict[str, Any]:
        """執行智能批量結構分析 - 語料庫驅動的模式發現"""
        try:
            # 使用新的智能分析器
            from .batch_analyzer import BatchAnalyzer
            batch_analyzer = BatchAnalyzer()
            
            return await batch_analyzer.analyze_batch_structure(posts_content, username)
            
        except ImportError:
            # 向後兼容：如果新模組不可用，使用舊方法
            return await self._legacy_batch_analysis(posts_content, username)
        except Exception as e:
            return {"status": "error", "message": f"智能批量結構分析失敗: {str(e)}"}
    
    async def _legacy_batch_analysis(self, posts_content: List[str], username: str = "unknown") -> Dict[str, Any]:
        """舊版批量分析方法（向後兼容）"""
        try:
            min_groups = self._decide_min_groups(len(posts_content))
            
            pattern_analysis = await self._batch_pattern_recognition(posts_content, min_groups)
            structure_templates = await self._generate_structure_templates(posts_content, pattern_analysis)
            
            identified_patterns = pattern_analysis.get("identified_patterns", []) if isinstance(pattern_analysis, dict) else []
            actual_pattern_count = len(identified_patterns)

            return {
                "status": "success",
                "username": username,
                "analysis_type": "legacy_batch_structure_analysis",
                "pattern_count": actual_pattern_count or min_groups,
                "total_posts": len(posts_content),
                "pattern_analysis": pattern_analysis,
                "structure_templates": structure_templates,
                "analyzed_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {"status": "error", "message": f"批量結構分析失敗: {str(e)}"}
    
    async def _batch_pattern_recognition(self, posts_content: List[str], min_groups: int) -> Dict[str, Any]:
        """第一層：純結構模式識別（不涉及內容主題）"""
        formatted_posts = self._format_multiple_posts(posts_content)
        
        # 動態建議每組至少樣本（允許重疊，放寬門檻）
        suggested_min_samples = max(3, len(posts_content) // max(min_groups, 5))
        target_groups_high = min_groups + 2
        
        prompt = f"""分析{len(posts_content)}篇貼文的結構特徵，請輸出至少{min_groups}組（可達到{target_groups_high}組）的結構模式分群，允許重疊覆蓋。

{formatted_posts}

要求：
1. 僅根據句數、字數分布、段落組織、標點密度、節奏/停頓等結構特徵分組
2. 允許同一篇貼文出現在多個模式中（重疊覆蓋），但必須覆蓋所有貼文（1..{len(posts_content)}），不可遺漏
3. 命名只可基於觀察到的結構特徵，不得含任何主題/文體字眼
4. 建議每組至少{suggested_min_samples}篇；若某組樣本偏少仍可保留，但需在 notes 中說明代表性限制

回應格式：
{{
  "analysis_summary": {{
    "total_posts": {len(posts_content)},
    "min_required_groups": {min_groups},
    "target_groups": "{min_groups}-{target_groups_high}",
    "overlap_allowed": true,
    "coverage": "必須覆蓋全部貼文（允許重疊）",
    "suggested_min_samples_per_group": {suggested_min_samples}
  }},
  "identified_patterns": [
    {{
      "pattern_id": "A",
      "pattern_name": "根據觀察到的結構特徵命名",
      "post_indices": [1, 3, 7, 12],  
      "post_count": 4,
      "structure_characteristics": {{
        "句數範圍": "X-Y句",
        "字數範圍": "A-B字", 
        "段落特徵": "單段/多段/列點",
        "句型分布": {{"陳述": "X%", "疑問": "Y%", "感嘆": "Z%", "祈使": "W%"}},
        "標點特徵": "感嘆號密度、逗號使用、省略號等",
        "節奏特徵": "急促/舒緩/停頓",
        "符號使用": "emoji/hashtag使用頻率"
      }},
      "sample_indices": [3, 12],
      "notes": "若樣本偏少，請說明代表性限制與不確定性"
    }}
  ]
}}"""

        messages = [
            {"role": "system", "content": "你是專業的結構模式識別專家，專注於從客觀結構特徵中發現貼文模式，不涉及內容主題分析。"},
            {"role": "user", "content": prompt}
        ]
        
        try:
            content = await chat_completion(
                messages=messages,
                model="gemini-2.0-flash",
                temperature=0.3,  # 適中的創意性，保持一致性
                max_tokens=2000,
                provider="gemini"
            )
            return parse_llm_json_response(content)
        except Exception as e:
            print(f"批量模式識別 - LLM調用錯誤: {e}")
            return {"error": f"模式識別失敗: {str(e)}"}
    
    async def _representative_deep_analysis(self, posts_content: List[str], pattern_analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """第二層：對代表性貼文進行深度結構分析"""
        analyses = []
        patterns = pattern_analysis.get("identified_patterns", [])
        
        for pattern in patterns:
            pattern_name = pattern.get("pattern_name", "未知模式")
            representative_indices = pattern.get("representative_indices", [])
            
            # 確保至少有代表性貼文
            if not representative_indices:
                continue
            
            # 🔧 修正：每個模式分析多篇貼文（2-3篇）
            # 確保每個模式至少分析2篇，最多3篇
            analysis_count = min(len(representative_indices), random.randint(2, 3))
            selected_indices = random.sample(representative_indices, analysis_count)
            
            pattern_analyses = []
            
            for selected_index in selected_indices:
                if selected_index <= len(posts_content):
                    post_content = posts_content[selected_index - 1]  # 轉換為0基索引
                    
                    # 使用變化的分析風格
                    style_word = self._get_random_variation("style_words")
                    focus_word = self._get_random_variation("focus_words")
                    
                    try:
                        structure_guide = await self._analyze_pattern_structure(
                            post_content, pattern_name, style_word, focus_word
                        )
                        
                        pattern_analyses.append({
                            "post_index": selected_index,
                            "post_content_preview": post_content[:100] + "..." if len(post_content) > 100 else post_content,
                            "structure_guide": structure_guide,
                            "analysis_variations": {
                                "style_focus": style_word,
                                "analysis_focus": focus_word
                            }
                        })
                        
                    except Exception as e:
                        print(f"代表性分析錯誤 - 模式 {pattern_name}, 貼文 {selected_index}: {e}")
                        continue
            
            # 將該模式的多篇分析結果整合
            if pattern_analyses:
                analyses.append({
                    "pattern_id": pattern.get("pattern_id"),
                    "pattern_name": pattern_name,
                    "analysis_count": len(pattern_analyses),
                    "analyzed_posts": pattern_analyses,
                    "representative_indices": selected_indices
                })
        
        return analyses
    
    async def _generate_structure_templates(self, posts_content: List[str], pattern_analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """第二層：為每個結構模式生成創作模板"""
        templates = []
        patterns = pattern_analysis.get("identified_patterns", [])
        
        for pattern in patterns:
            pattern_name = pattern.get("pattern_name", "未知模式")
            structure_chars = pattern.get("structure_characteristics", {})
            sample_indices = pattern.get("sample_indices", [])
            
            try:
                template = await self._generate_universal_structure_template(
                    pattern_name, structure_chars, posts_content, sample_indices
                )
                
                templates.append({
                    "pattern_id": pattern.get("pattern_id"),
                    "pattern_name": pattern_name,
                    "template_type": "universal",
                    "structure_template": template
                })
                
            except Exception as e:
                print(f"結構模板生成錯誤 - 模式 {pattern_name}: {e}")
                continue
        
        return templates
    
    def _estimate_avg_length(self, posts_content: List[str], post_indices: List[int]) -> int:
        """估算模式的平均字數"""
        if not post_indices:
            return 0
        
        total_length = 0
        valid_count = 0
        
        for idx in post_indices:
            if 0 <= idx - 1 < len(posts_content):  # 轉換為0基索引
                total_length += len(posts_content[idx - 1])
                valid_count += 1
        
        return total_length // valid_count if valid_count > 0 else 0
    
    async def _generate_universal_structure_template(self, pattern_name: str, structure_chars: Dict[str, Any], 
                                                   posts_content: List[str], sample_indices: List[int]) -> Dict[str, Any]:
        """生成通用結構模板"""
        # 獲取樣本貼文
        sample_posts = []
        for idx in sample_indices:
            if 0 <= idx - 1 < len(posts_content):
                sample_posts.append(posts_content[idx - 1])
        
        samples_text = "\n".join([f"樣本{i+1}: {post}" for i, post in enumerate(sample_posts)])
        
        prompt = f"""根據結構模式「{pattern_name}」的特徵，分析樣本並生成創作指引。

模式特徵：{json.dumps(structure_chars, ensure_ascii=False)}

樣本貼文：
{samples_text}

請分析這個模式的結構特點，自行決定最合適的分析維度，僅輸出「結構指引」，不得涉及內容主題或語義。

輸出JSON（鍵名固定但子項開放，僅在適用時輸出）：
{{
  "structure_guide": {{
    "length_profile": {{ "總句數範圍": "X-Y句", "平均每句字數": "A-B字" }},
    "organization": {{ "段落數量": "N1-N2段", "每段句數": "S1-S2句", "列點/對話/引用": "有/無/比例" }},
    "rhythm": {{ "節奏描述": "...", "標點/emoji使用": "..." }},
    "coherence": {{ "連貫策略": ["...","..."] }},
    "micro_arc": "若為短篇且適用時輸出：如 觸發→反應 / 情緒→具體化",
    "density": "若適用：每句需包含的資訊/情緒元素",
    "tension": "若適用：對比/反差/強調詞/停頓的運用",
    "completeness": "若適用：即使短文也需具備的要素",
    "sentence_types": {{ "從樣本發現的句型類別1": "統計比例", "從樣本發現的句型類別2": "統計比例" }},
    "structure_chain": ["從樣本抽象出的結構流程"]
  }},
  "creation_guidance": {{
    "writing_steps": ["具體創作步驟1", "具體創作步驟2", "具體創作步驟3"],
    "style_constraints": ["風格約束1", "風格約束2"],
    "common_pitfalls": ["常見錯誤1", "常見錯誤2"]
  }},
  "notes": "可補充限制或注意事項"
}}

規則：
- 僅在「適用時」才輸出 micro_arc / density / tension / completeness 等維度；不強行套用
- 所有數值用範圍表示（如 1-2 句、8-15 字）
- 僅根據結構特徵歸納，不得帶入任何內容細節
- 結構鏈只用邏輯關係，不涉及具體主題
"""

        messages = [
            {"role": "system", "content": "你是專業的結構分析師，專注於從結構特徵中提取可指導AI創作的模板。"},
            {"role": "user", "content": prompt}
        ]
        
        try:
            content = await chat_completion(
                messages=messages,
                model="gemini-2.0-flash",
                temperature=0.2,
                max_tokens=1500,
                provider="gemini"
            )
            return parse_llm_json_response(content)
        except Exception as e:
            print(f"結構模板生成錯誤: {e}")
            return {"error": f"無法生成結構模板: {str(e)}"}
    
    async def _generate_long_form_template_backup(self, pattern_name: str, structure_chars: Dict[str, Any],
                                         posts_content: List[str], sample_indices: List[int]) -> Dict[str, Any]:
        """備用函數（暫時保留）"""
        # 獲取樣本貼文
        sample_posts = []
        for idx in sample_indices:
            if 0 <= idx - 1 < len(posts_content):
                sample_posts.append(posts_content[idx - 1])
        
        samples_text = "\n".join([f"樣本{i+1}: {post}" for i, post in enumerate(sample_posts)])
        
        prompt = f"""請扮演結構分析專家，僅根據以下貼文的句型、長短、段落分佈和連貫性，
產生一份「貼文創作結構指引模板」，用以指導後續 AI 貼文創作，不得分析或回覆任何內容細節。

模式名稱：{pattern_name}
結構特徵：{json.dumps(structure_chars, ensure_ascii=False)}

樣本貼文：
{samples_text}

請嚴格按照下述格式輸出，所有數據需推估範圍，不需完全精確：

{{
  "post_structure_guide": {{
    "總句數範圍": "X-Y句",
    "平均每句字數": "A-B字",
    "短句定義": "C-D字",
    "長句定義": "E-F字",
    "短句比例": "P1-P2%",
    "長句比例": "Q1-Q2%",
    "段落數量": "N1-N2段",
    "每段句數": "S1-S2句",
    "段落類型分布": [
      "從樣本發現的段落類型1（K1-K2段，每段M1-M2句）",
      "從樣本發現的段落類型2（L1-L2段，每段M3-M4句）"
    ],
    "句型分類比例": {{
      "從樣本發現的句型類別1": "X1-X2%",
      "從樣本發現的句型類別2": "Y1-Y2%"
    }},
    "連貫與銜接規則": {{
      "長句應用": "從樣本總結的長句使用規則",
      "短句應用": "從樣本總結的短句使用規則",
      "段落銜接": "從樣本總結的段落連接方式"
    }},
    "敘事弧線": [
      "從樣本抽象出的結構流程1",
      "從樣本抽象出的結構流程2"
    ],
    "範例結構鏈": [
      "從樣本抽象出的結構鏈"
    ]
  }},
  "analysis_elements": {{
    "長句功能分類": ["從樣本發現的長句功能1", "從樣本發現的長句功能2"],
    "長句組織模式": ["從樣本總結的組織模式1", "從樣本總結的組織模式2"],
    "短句應用場景": ["從樣本總結的應用場景1", "從樣本總結的應用場景2"],
    "連貫策略": ["從樣本總結的連貫策略1", "從樣本總結的連貫策略2"]
  }}
}}

輸出重點：
- 只許根據貼文「結構特徵」分析，不得帶入任何原文內容
- 各數值用合理範圍表示（例如「7-18句」、「30-45%」）
- 分析重點為「句子長短」、「段落組織」、「前後連貫」、「深度段落」
- 範例只用「結構鏈」，不可涉及具體內容或主題
"""

        messages = [
            {"role": "system", "content": "你是專業的文本結構分析師，專注於從結構特徵中提取可指導AI創作的模板。"},
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
            return parse_llm_json_response(content)
        except Exception as e:
            print(f"長文模板生成錯誤: {e}")
            return {"error": f"無法生成長文模板: {str(e)}"}

    async def _analyze_pattern_structure(self, post_content: str, pattern_name: str, style_word: str, focus_word: str) -> Dict[str, Any]:
        """為特定模式分析結構（基於現有單篇分析，但調整為模式導向）"""
        theme_word = self._get_random_variation("theme_words")
        
        prompt = f"""你是專業的文本結構分析師。請{theme_word}分析以下代表「{pattern_name}」的貼文結構特徵，{focus_word}並從{style_word}角度填寫結構指南。

重要要求：
- 重點分析符合「{pattern_name}」的結構特徵
- 各數值用合理範圍表示（例如「7-18句」、「30-45%」）
- 分析重點為「句子長短」、「段落組織」、「前後連貫」、「深度段落」
- 範例只用「結構鏈」，不可涉及具體內容或主題

代表性貼文內容：
---
{post_content}
---

請按照以下格式分析並回應（JSON格式）：

{{
  "pattern_specific_guide": {{
    "模式名稱": "{pattern_name}",
    "總句數範圍": "X-Y句",
    "平均每句字數": "A-B字",
    "短句定義": "C-D字",
    "長句定義": "E-F字",
    "短句比例": "P1-P2%",
    "長句比例": "Q1-Q2%",
    "段落數量": "N1-N2段",
    "每段句數": "S1-S2句",
    "模式特色": ["特色1", "特色2", "特色3"],
    "適用情境": "此模式最適合的使用場景"
  }},
  "analysis_metadata": {{
    "style_focus": "{style_word}",
    "analysis_focus": "{focus_word}",
    "theme_approach": "{theme_word}"
  }}
}}"""

        messages = [
            {"role": "system", "content": f"你是專業的文本結構分析師，特別擅長{style_word}分析，能夠{focus_word}進行{theme_word}的結構分析。"},
            {"role": "user", "content": prompt}
        ]
        
        try:
            content = await chat_completion(
                messages=messages,
                model="gemini-2.0-flash",
                temperature=0.2,
                max_tokens=1000,
                provider="gemini"
            )
            return parse_llm_json_response(content)
        except Exception as e:
            print(f"模式結構分析錯誤: {e}")
            return {"error": f"無法分析模式結構: {str(e)}"}
    
    async def _generate_unified_guide(self, pattern_analysis: Dict[str, Any], structure_templates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """第三層：生成統合的結構創作指南"""
        prompt = f"""基於多種結構模式的分析結果，生成統合的創作策略指南：

🔍 模式識別結果：
{json.dumps(pattern_analysis, ensure_ascii=False, indent=2)}

📋 結構模板集：
{json.dumps(structure_templates, ensure_ascii=False, indent=2)}

請生成包含以下內容的統合指南：

1. **模式選擇策略**：根據創作需求（字數限制、內容類型、表達目標）選擇合適的結構模式
2. **跨模式應用技巧**：如何在不同模式間切換或組合使用
3. **結構優化建議**：如何針對每種模式進行效果提升
4. **實戰應用指南**：針對常見創作場景的模式推薦

格式要求：
- 基於結構模板的實用指導
- 可直接用於AI創作系統的策略建議
- 重點在結構特徵，不涉及內容主題

{{
  "unified_creation_guide": {{
    "pattern_selection_strategy": {{
      "selection_criteria": ["選擇標準1", "選擇標準2"],
      "scenario_mapping": {{"情境1": "推薦模式", "情境2": "推薦模式"}}
    }},
    "structure_templates": [
      {{
        "pattern_name": "模式名稱",
        "writing_steps": ["步驟1", "步驟2", "步驟3"],
        "key_techniques": ["技巧1", "技巧2"],
        "example_structure": "範例結構框架"
      }}
    ],
    "optimization_tips": {{
      "general_principles": ["通用原則1", "通用原則2"],
      "pattern_specific_tips": {{"模式A": ["tip1", "tip2"]}}
    }},
    "hybrid_strategies": [
      "混合策略1：何時何地如何結合",
      "混合策略2：進階應用技巧"
    ],
    "practical_application": {{
      "content_type_recommendations": {{"內容類型1": "建議模式及原因"}},
      "common_pitfalls": ["常見錯誤1", "常見錯誤2"],
      "success_indicators": ["成功指標1", "成功指標2"]
    }}
  }},
  "meta_analysis": {{
    "analysis_approach": "結構模板整合分析",
    "total_patterns_analyzed": {len(structure_templates)},
    "template_types": ["長文模板", "短文模板"]
  }}
}}"""

        messages = [
            {"role": "system", "content": "你是資深的結構創作策略顧問，專精於整合多種結構模板，制定實用的創作指南。"},
            {"role": "user", "content": prompt}
        ]
        
        try:
            content = await chat_completion(
                messages=messages,
                model="gemini-2.0-flash",
                temperature=0.4,  # 稍高的創意性用於生成指南
                max_tokens=4096,
                provider="gemini"
            )
            return parse_llm_json_response(content)
        except Exception as e:
            print(f"統合指南生成錯誤: {e}")
            return {"error": f"無法生成統合指南: {str(e)}"}

    # ========= 新增：多篇摘要（批量模板用） =========
    async def summarize_multi_posts(self, pattern_name: str, structure_guide: Dict[str, Any], sample_posts: List[str]) -> str:
        """批量版本的『第二步：根據結構指南生成分析摘要』。
        聚焦於：該模板類型的主題傾向、情緒/語氣、節奏與段落安排、用詞與表達、互動策略，
        並產出可直接用於後續寫作的「血與肉」級摘要與建議。
        """
        merged_samples = []
        for i, p in enumerate(sample_posts or [], 1):
            merged_samples.append(f"樣本{i:02d}:\n{p}")
        merged_posts_text = "\n\n".join(merged_samples)
        guide_json = json.dumps(structure_guide or {}, ensure_ascii=False, indent=2)

        prompt = f"""請根據「結構指南」與「多篇樣本內容」，為『{pattern_name}』這一模板類型生成可用於後續寫作的【分析摘要】（血與肉）。

重要要求：
- 從多篇樣本歸納「共通的主題傾向、情緒強度與語氣基調、節奏與段落安排、用詞與表達、互動策略」
- 不可直接抄寫樣本原句；如需指稱具體元素，請用占位符（如《作品名》、SxEy、YYYY/MM/DD、#標籤）
- 允許描述「此模板類型」的常見元素與語境（例如影視作品提及型可提及：作品/集數/播出時間），但不填入真實專有名詞
- 精煉、可操作，每點不超過一行；可被直接拿去指導 AI 寫作

【結構指南】
{guide_json}

【多篇樣本內容】（供你觀察共通規律，不得逐字引用）
{merged_posts_text}

請用 Markdown 條列回應，格式如下：
【分析結果】
1. 主題傾向／素材元素：此類貼文常圍繞哪些題材與資訊元素（用占位符，不填真名）
2. 情緒與語氣：強度範圍、主導語氣（如熱血／冷靜／幽默／正式）
3. 節奏與段落：短長句節奏、段落分工、常用承接/轉折語型、收尾句型
4. 用詞與表達：口語度、專業詞彙、emoji／hashtag 模式、典型句式
5. 互動策略：常見提問、CTA、互動誘因

【改寫建議】（3–5點，可直接操作）
- 針對此模板類型，提出具體可執行的優化／擴寫方式

【發展方向】
1. 最接近的風格方向（故事型／評論型／互動型／資訊型），並簡述理由
2. 內容行銷／品牌／SEO／分發建議（如 #標籤／欄位露出／CTA）
3. 寫作重點（1–2 句）
4. 範例句（符合此模板與定位；不得抄樣本原句，可用占位符）
"""

        messages = [
            {"role": "system", "content": "你是 Threads 貼文策略與寫作顧問。請以繁體中文輸出，從多篇樣本歸納可直接用於創作的摘要與建議；不得逐字引用樣本原句，可用占位符代表專有名詞。"},
            {"role": "user", "content": prompt}
        ]

        try:
            content = await chat_completion(
                messages=messages,
                model="gemini-2.0-flash",
                temperature=0.2,
                max_tokens=1500,
                provider="gemini"
            )
            return (content or "").strip()
        except Exception as e:
            return f"無法生成摘要：{str(e)}"

# Example Usage (requires .env configuration)
async def main():
    try:
        from agents.ranker.ranker_logic import RankerAgent
        ranker = RankerAgent()
        ranked_result = await ranker.rank_posts(author_id="@victor31429", top_n=5)
        
        if ranked_result['status'] == 'error':
            print("Could not get ranked posts for testing.")
            print(f"RankerAgent Error: {ranked_result.get('message', 'No error message returned.')}")
            return

        top_post_urls = [p['url'] for p in ranked_result['ranked_posts']]
        analyzer = PostAnalyzerAgent()
        
        print("--- Testing Mode 1 (Live LLM) ---")
        mode1_result = await analyzer.analyze_posts(post_urls=top_post_urls[:1], analysis_mode=1)
        print(json.dumps(mode1_result, indent=2, ensure_ascii=False))

        print("\n--- Testing Mode 2 (Live LLM) ---")
        mode2_result = await analyzer.analyze_posts(post_urls=top_post_urls, analysis_mode=2)
        print(json.dumps(mode2_result, indent=2, ensure_ascii=False))

        print("\n--- Testing Mode 3 (Live LLM) ---")
        mode3_result = await analyzer.analyze_posts(post_urls=top_post_urls, analysis_mode=3)
        print(json.dumps(mode3_result, indent=2, ensure_ascii=False))

    except (ValueError, FileNotFoundError) as e:
        print(f"Configuration Error: {e}")
        print("Please ensure your .env file is correctly configured with LLM provider settings.")
    finally:
        db_client = await get_db_client()
        if db_client:
            await db_client.close_pool()

if __name__ == '__main__':
    asyncio.run(main()) 