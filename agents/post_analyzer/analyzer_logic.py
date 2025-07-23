import asyncio
import json
import re
from typing import Dict, Any, List

from common.db_client import get_db_client
from common.settings import get_settings
from common.llm_client import LLMClient, parse_llm_json_response

class PostAnalyzerAgent:
    """
    Analyzes posts to extract success patterns based on different modes.
    """
    def __init__(self):
        self.settings = get_settings()
        self.llm_client = LLMClient(provider_name="openrouter")

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