#!/usr/bin/env python3
"""
Post Analyzer Agent - 基於 Clarification 問卷方向的貼文深度分析
分析爬蟲結果中的前10則貼文，提供主題、風格、表現等分析和改寫建議
"""

import json
import uuid
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import asyncio
import sys
import os
from datetime import datetime
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# 添加專案根目錄到 Python 路徑
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from common.llm_manager import get_llm_manager, chat_completion
from common.settings import get_settings
from common.models import PostMetrics, PostMetricsBatch
from agents.post_analyzer.analyzer_logic import PostAnalyzerAgent as StructureAnalyzerAgent

app = FastAPI(title="Post Analyzer Agent", version="1.0.0")

class AnalyzeRequest(BaseModel):
    username: str = Field(..., description="要分析的用戶名稱")
    posts_data: List[Dict[str, Any]] = Field(..., description="貼文數據列表")
    batch_id: Optional[str] = Field(None, description="批次ID")

class StructureAnalyzeRequest(BaseModel):
    post_content: str = Field(..., description="要分析的貼文內容")
    post_id: str = Field(..., description="貼文ID")
    username: str = Field(..., description="用戶名稱")

class AnalysisResult(BaseModel):
    batch_id: str
    username: str
    analysis_summary: Dict[str, Any]
    recommendations: Dict[str, Any]
    top_posts_analysis: List[Dict[str, Any]]
    rewrite_suggestions: List[Dict[str, Any]]
    analyzed_at: datetime

class StructureAnalysisResult(BaseModel):
    post_id: str
    username: str
    post_structure_guide: Dict[str, Any]
    analysis_summary: str
    analyzed_at: datetime

class PostAnalyzerAgent:
    def __init__(self):
        self.settings = get_settings()
        self.llm_manager = get_llm_manager()
    
    def _parse_llm_json_response(self, response_content: str) -> Dict[str, Any]:
        """解析 LLM 的 JSON 響應"""
        import re
        
        # 首先嘗試找到 ```json ... ``` 塊
        match = re.search(r"```json\s*(\{.*?\})\s*```", response_content, re.DOTALL)
        if match:
            json_str = match.group(1)
        else:
            # 如果沒找到，找第一個 '{' 和最後一個 '}'
            start_index = response_content.find('{')
            end_index = response_content.rfind('}')
            if start_index != -1 and end_index != -1 and end_index > start_index:
                json_str = response_content[start_index:end_index+1]
            else:
                raise json.JSONDecodeError("No valid JSON object found in the response.", response_content, 0)
        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"Failed to decode JSON string: {json_str}")
            raise e
    
    def _extract_analysis_dimensions(self, posts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """提取分析維度信息"""
        total_posts = len(posts)
        total_likes = sum(post.get('likes_count', 0) for post in posts)
        total_views = sum(post.get('views_count', 0) for post in posts)
        total_comments = sum(post.get('comments_count', 0) for post in posts)
        
        # 計算平均長度
        content_lengths = []
        for post in posts:
            content = post.get('content', '')
            if content:
                content_lengths.append(len(content))
        
        avg_length = sum(content_lengths) / len(content_lengths) if content_lengths else 0
        
        # 分析媒體使用
        posts_with_images = sum(1 for post in posts if post.get('images_count', 0) > 0)
        posts_with_videos = sum(1 for post in posts if post.get('videos_count', 0) > 0)
        
        return {
            "total_posts": total_posts,
            "engagement_metrics": {
                "total_likes": total_likes,
                "total_views": total_views,
                "total_comments": total_comments,
                "avg_likes_per_post": total_likes / total_posts if total_posts > 0 else 0,
                "avg_views_per_post": total_views / total_posts if total_posts > 0 else 0,
                "avg_comments_per_post": total_comments / total_posts if total_posts > 0 else 0
            },
            "content_analysis": {
                "avg_content_length": avg_length,
                "posts_with_images": posts_with_images,
                "posts_with_videos": posts_with_videos,
                "image_usage_rate": posts_with_images / total_posts if total_posts > 0 else 0,
                "video_usage_rate": posts_with_videos / total_posts if total_posts > 0 else 0
            }
        }
    
    async def _analyze_content_themes_and_style(self, posts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析內容主題和風格"""
        contents = []
        for post in posts:
            content = post.get('content', '')
            if content:
                contents.append(content)
        
        combined_content = "\n\n---\n\n".join(contents[:10])  # 只分析前10篇
        
        prompt = f"""你是一個專業的社交媒體內容分析師。請根據以下貼文內容，進行深度分析：

貼文內容：
---
{combined_content}
---

請按照以下維度進行分析，並以 JSON 格式回應：

1. **主題分析**：識別主要主題類別（美妝保養、時尚穿搭、美食分享、旅遊生活、科技數碼、健康運動、生活日常、商品推廣、教育學習、娛樂休閒等）
2. **風格分析**：分析呈現風格（連貫敘事、分行條列、圖文並茂等）
3. **語氣分析**：分析語氣特色（親身體驗、客觀介紹、幽默風趣、專業知識等）
4. **內容長度**：分析內容長度偏好
5. **特殊元素**：分析使用的特殊元素（emoji、hashtag、特殊符號等）

回應格式：
{{
  "theme_analysis": {{
    "primary_themes": ["主要主題1", "主要主題2"],
    "theme_distribution": {{"主題": "出現比例"}},
    "content_focus": "內容重點描述"
  }},
  "style_analysis": {{
    "presentation_style": "主要呈現風格",
    "structure_patterns": ["結構模式1", "結構模式2"],
    "visual_elements": "視覺元素使用情況"
  }},
  "tone_analysis": {{
    "primary_tone": "主要語氣",
    "emotional_style": "情感風格",
    "perspective": "敘述視角"
  }},
  "length_analysis": {{
    "avg_length_category": "長度類別",
    "length_pattern": "長度規律",
    "content_density": "內容密度"
  }},
  "special_elements": {{
    "emoji_usage": "emoji使用情況",
    "hashtag_usage": "hashtag使用情況",
    "special_symbols": "特殊符號使用",
    "formatting_style": "格式化風格"
  }}
}}"""

        messages = [
            {"role": "system", "content": "你是一個專業的社交媒體內容分析師，擅長識別內容模式和風格特色。"},
            {"role": "user", "content": prompt}
        ]
        
        content = await chat_completion(
            messages=messages,
            model="gemini-2.0-flash",
            temperature=0.2,
            max_tokens=2000,
            provider="gemini"
        )
        
        return self._parse_llm_json_response(content)
    
    async def _analyze_top_performing_posts(self, posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """分析表現最好的貼文原因"""
        # 按分數排序獲取前5名
        sorted_posts = sorted(posts, key=lambda x: x.get('calculated_score', 0), reverse=True)[:5]
        
        analyses = []
        
        for i, post in enumerate(sorted_posts, 1):
            content = post.get('content', '')
            likes = post.get('likes_count', 0)
            views = post.get('views_count', 0)
            comments = post.get('comments_count', 0)
            score = post.get('calculated_score', 0)
            
            prompt = f"""分析這篇高表現貼文成功的原因：

貼文內容：
---
{content}
---

表現數據：
- 讚數：{likes:,}
- 瀏覽數：{views:,}
- 評論數：{comments}
- 綜合分數：{score:.1f}

請分析這篇貼文成功的原因，以 JSON 格式回應：

{{
  "ranking": {i},
  "success_factors": {{
    "content_appeal": "內容吸引力分析",
    "emotional_trigger": "情感觸發點",
    "timing_relevance": "時機相關性",
    "visual_elements": "視覺元素效果",
    "engagement_drivers": "互動驅動因素"
  }},
  "improvement_suggestions": [
    "改進建議1",
    "改進建議2",
    "改進建議3"
  ]
}}"""
            
            messages = [
                {"role": "system", "content": "你是一個社交媒體數據分析專家，擅長解析高表現內容的成功因素。"},
                {"role": "user", "content": prompt}
            ]
            
            try:
                content_response = await chat_completion(
                    messages=messages,
                    model="gemini-2.0-flash",
                    temperature=0.3,
                    max_tokens=1000,
                    provider="gemini"
                )
                
                analysis = self._parse_llm_json_response(content_response)
                analysis["post_content"] = content[:100] + "..." if len(content) > 100 else content
                analysis["metrics"] = {
                    "likes": likes,
                    "views": views,
                    "comments": comments,
                    "score": score
                }
                analyses.append(analysis)
                
            except Exception as e:
                print(f"Error analyzing post {i}: {e}")
                continue
        
        return analyses
    
    async def _generate_rewrite_suggestions(self, posts: List[Dict[str, Any]], style_analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """生成改寫建議"""
        # 選擇3篇中等表現的貼文進行改寫建議
        sorted_posts = sorted(posts, key=lambda x: x.get('calculated_score', 0))
        middle_posts = sorted_posts[len(sorted_posts)//3:2*len(sorted_posts)//3][:3]
        
        suggestions = []
        
        for i, post in enumerate(middle_posts, 1):
            content = post.get('content', '')
            
            prompt = f"""基於分析出的風格特色，為這篇貼文提供改寫建議：

原始貼文：
---
{content}
---

分析出的風格特色：
主要主題：{style_analysis.get('theme_analysis', {}).get('primary_themes', [])}
呈現風格：{style_analysis.get('style_analysis', {}).get('presentation_style', '')}
語氣特色：{style_analysis.get('tone_analysis', {}).get('primary_tone', '')}
特殊元素：{style_analysis.get('special_elements', {})}

請提供改寫建議，以 JSON 格式回應：

{{
  "original_analysis": {{
    "strengths": ["優點1", "優點2"],
    "weaknesses": ["可改進處1", "可改進處2"],
    "current_style": "當前風格描述"
  }},
  "rewrite_suggestions": {{
    "theme_optimization": "主題優化建議",
    "style_improvement": "風格改進建議",
    "tone_adjustment": "語氣調整建議",
    "structure_enhancement": "結構增強建議",
    "engagement_boost": "互動提升建議"
  }},
  "sample_rewrite": "改寫範例（保持原意但優化表達）"
}}"""
            
            messages = [
                {"role": "system", "content": "你是一個專業的內容改寫專家，擅長根據成功模式優化內容。"},
                {"role": "user", "content": prompt}
            ]
            
            try:
                content_response = await chat_completion(
                    messages=messages,
                    model="gemini-2.0-flash",
                    temperature=0.4,
                    max_tokens=1500,
                    provider="gemini"
                )
                
                suggestion = self._parse_llm_json_response(content_response)
                suggestion["original_content"] = content
                suggestion["suggestion_id"] = i
                suggestions.append(suggestion)
                
            except Exception as e:
                print(f"Error generating rewrite suggestion {i}: {e}")
                continue
        
        return suggestions
    
    async def _generate_overall_recommendations(self, 
                                              style_analysis: Dict[str, Any], 
                                              top_posts_analysis: List[Dict[str, Any]], 
                                              dimensions: Dict[str, Any]) -> Dict[str, Any]:
        """生成整體建議"""
        prompt = f"""基於完整的分析結果，生成整體內容策略建議：

風格分析：
{json.dumps(style_analysis, ensure_ascii=False, indent=2)}

高表現貼文分析：
{json.dumps(top_posts_analysis, ensure_ascii=False, indent=2)}

數據統計：
{json.dumps(dimensions, ensure_ascii=False, indent=2)}

請生成整體建議，以 JSON 格式回應：

{{
  "content_strategy": {{
    "primary_recommendations": ["核心建議1", "核心建議2", "核心建議3"],
    "content_pillars": ["內容支柱1", "內容支柱2", "內容支柱3"],
    "posting_frequency": "發布頻率建議",
    "optimal_length": "最佳長度建議"
  }},
  "engagement_optimization": {{
    "best_practices": ["最佳實踐1", "最佳實踐2"],
    "avoid_patterns": ["避免模式1", "避免模式2"],
    "timing_suggestions": "時機建議",
    "interaction_tips": ["互動技巧1", "互動技巧2"]
  }},
  "style_guidelines": {{
    "tone_recommendations": "語氣建議",
    "formatting_tips": "格式建議",
    "visual_guidelines": "視覺指南",
    "hashtag_strategy": "hashtag策略"
  }},
  "growth_opportunities": {{
    "content_gaps": ["內容空白1", "內容空白2"],
    "expansion_topics": ["擴展主題1", "擴展主題2"],
    "collaboration_ideas": ["合作想法1", "合作想法2"]
  }}
}}"""

        messages = [
            {"role": "system", "content": "你是一個資深的社交媒體策略顧問，擅長制定全面的內容策略。"},
            {"role": "user", "content": prompt}
        ]
        
        content = await chat_completion(
            messages=messages,
            model="gemini-2.0-flash",
            temperature=0.3,
            max_tokens=2500,
            provider="gemini"
        )
        
        return self._parse_llm_json_response(content)
    
    async def analyze_posts(self, username: str, posts_data: List[Dict[str, Any]], batch_id: Optional[str] = None) -> AnalysisResult:
        """執行完整的貼文分析"""
        if not batch_id:
            batch_id = str(uuid.uuid4())
        
        try:
            # 1. 提取基礎分析維度
            dimensions = self._extract_analysis_dimensions(posts_data)
            
            # 2. 分析內容主題和風格
            style_analysis = await self._analyze_content_themes_and_style(posts_data)
            
            # 3. 分析表現最好的貼文
            top_posts_analysis = await self._analyze_top_performing_posts(posts_data)
            
            # 4. 生成改寫建議
            rewrite_suggestions = await self._generate_rewrite_suggestions(posts_data, style_analysis)
            
            # 5. 生成整體建議
            overall_recommendations = await self._generate_overall_recommendations(
                style_analysis, top_posts_analysis, dimensions
            )
            
            # 6. 組合最終結果
            analysis_summary = {
                "basic_metrics": dimensions,
                "content_analysis": style_analysis,
                "performance_insights": {
                    "top_posts_count": len(top_posts_analysis),
                    "avg_engagement_rate": dimensions["engagement_metrics"]["avg_likes_per_post"] / dimensions["engagement_metrics"]["avg_views_per_post"] if dimensions["engagement_metrics"]["avg_views_per_post"] > 0 else 0
                }
            }
            
            return AnalysisResult(
                batch_id=batch_id,
                username=username,
                analysis_summary=analysis_summary,
                recommendations=overall_recommendations,
                top_posts_analysis=top_posts_analysis,
                rewrite_suggestions=rewrite_suggestions,
                analyzed_at=datetime.utcnow()
            )
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"分析失敗: {str(e)}")

# 全域 agent 實例
post_analyzer_agent = PostAnalyzerAgent()
structure_analyzer_agent = StructureAnalyzerAgent()

@app.get("/health")
async def health_check():
    """健康檢查端點"""
    return {
        "status": "healthy",
        "service": "post-analyzer-agent",
        "version": "2.0.0"
    }

@app.post("/analyze", response_model=AnalysisResult)
async def analyze_posts(request: AnalyzeRequest):
    """分析貼文"""
    try:
        result = await post_analyzer_agent.analyze_posts(
            username=request.username,
            posts_data=request.posts_data,
            batch_id=request.batch_id
        )
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析處理失敗: {str(e)}")

@app.post("/structure-analyze", response_model=StructureAnalysisResult)
async def analyze_post_structure(request: StructureAnalyzeRequest):
    """結構分析貼文"""
    try:
        result = await structure_analyzer_agent.analyze_post_structure(
            post_content=request.post_content,
            post_id=request.post_id,
            username=request.username
        )
        
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("message"))
        
        return StructureAnalysisResult(
            post_id=result["post_id"],
            username=result["username"],
            post_structure_guide=result["post_structure_guide"],
            analysis_summary=result["analysis_summary"],
            analyzed_at=datetime.fromisoformat(result["analyzed_at"])
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"結構分析處理失敗: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8007)