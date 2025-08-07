import asyncio
import json
import re
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
        response = await self.llm_client.chat_completion(messages, temperature=0.2)
        
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
        response = await self.llm_client.chat_completion(messages, temperature=0.3)
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
                response = await self.llm_client.chat_completion(messages, model=model, temperature=0.5)
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
        summary_response = await self.llm_client.chat_completion(summary_messages, temperature=0.3)
        
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
        prompt = f"""你是一個專業的文本結構分析師。請分析以下貼文的結構特徵，並填寫結構指南。

重要要求：
- 只許根據貼文「結構特徵」分析，不得帶入任何原文內容
- 各數值用合理範圍表示（例如「7-18句」、「30-45%」）
- 分析重點為「句子長短」、「段落組織」、「前後連貫」、「深度段落」
- 範例只用「結構鏈」，不可涉及具體內容或主題

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
        prompt = f"""請根據「原貼文內容」與「第一階段結構分析」，以如下格式條列回應：

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