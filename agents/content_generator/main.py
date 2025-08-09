#!/usr/bin/env python3
"""
內容生成代理 - FastAPI 服務
基於分析結果和用戶需求生成貼文內容
"""

import os
import sys
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import json
import logging
from datetime import datetime
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from common.llm_manager import LLMManager

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Content Generator Agent", version="1.0.0")

# 初始化 LLM 管理器
llm_manager = LLMManager()

class ContentGenerationRequest(BaseModel):
    user_prompt: str
    llm_config: Optional[Dict[str, Any]] = None
    settings: Dict[str, Any]
    reference_analysis: Optional[Dict[str, Any]] = None

class ContentGenerationResponse(BaseModel):
    generated_posts: List[str]
    generation_settings: Dict[str, Any]
    generated_at: str

@app.get("/health")
async def health_check():
    """健康檢查"""
    return {"status": "healthy", "service": "content-generator"}

@app.post("/generate-content", response_model=ContentGenerationResponse)
async def generate_content(request: ContentGenerationRequest):
    """
    生成貼文內容
    根據用戶需求、設定參數和參考分析生成多個貼文版本
    """
    try:
        logger.info(f"開始生成內容，用戶提示: {request.user_prompt[:50]}...")
        
        # 構建五段式 prompt
        post_count = request.settings.get('post_count', 5)  # 預設5篇
        full_prompt = _build_five_stage_prompt(
            user_prompt=request.user_prompt,
            settings=request.settings,
            post_count=post_count,
            reference_analysis=request.reference_analysis
        )
        
        logger.info("調用 LLM 生成內容...")
        
        # 解析 LLM 配置
        llm_config = request.llm_config or {}
        provider_name = llm_config.get('provider', 'Gemini (Google)')
        model_name = llm_config.get('model', 'gemini-2.5-flash')
        
        # 映射提供商名稱
        provider = None
        if provider_name == 'Gemini (Google)':
            provider = 'gemini'
        elif provider_name == 'OpenRouter':
            provider = 'openrouter'
        
        logger.info(f"使用 LLM: {provider_name} - {model_name}")
        
        # 調用 LLM
        messages = [{"role": "user", "content": full_prompt}]
        generated_content = await llm_manager.chat_completion(
            messages=messages,
            model=model_name,
            provider=provider,
            max_tokens=4096,
            temperature=0.8
        )
        
        # 解析生成的多個貼文版本
        post_versions = _parse_generated_posts(generated_content.content)
        
        response = ContentGenerationResponse(
            generated_posts=post_versions,
            generation_settings=request.settings,
            generated_at=datetime.now().isoformat()
        )
        
        logger.info(f"內容生成完成，共 {len(post_versions)} 個版本")
        return response
        
    except Exception as e:
        logger.error(f"內容生成失敗: {e}")
        raise HTTPException(status_code=500, detail=f"內容生成失敗: {str(e)}")

def _build_five_stage_prompt(
    user_prompt: str,
    settings: Dict[str, Any],
    post_count: int = 5,
    reference_analysis: Optional[Dict[str, Any]] = None
) -> str:
    """
    構建五段式 prompt 結構
    """
    
    # 第一段：開頭指示
    stage_1 = f"""只輸出貼文範例，不用分析。
根據以下內容，提供{post_count}個貼文範例。
{post_count}種版本，請嚴格按照第一階段分析的格式。
只輸出貼文，不用分析，不要抄襲原文。
以下原文只是參考內容。
請以用戶需求優先。
"""
    
    # 第二段：撰寫風格和內容設定 + 用戶特別需求
    stage_2_parts = []
    stage_2_parts.append(f"**撰寫風格**: {settings.get('writing_style', '自動預設')}")
    stage_2_parts.append(f"**內容類型**: {settings.get('content_type', '社群貼文')}")
    stage_2_parts.append(f"**目標長度**: {settings.get('target_length', '中等')}")
    stage_2_parts.append(f"**語調風格**: {settings.get('tone', '友善親切')}")
    stage_2_parts.append(f"**用戶需求**: {user_prompt}")
    
    stage_2 = "\n".join(stage_2_parts)
    
    # 第三段、第四段、第五段：參考分析內容
    stage_3 = ""
    stage_4 = ""
    stage_5 = ""
    
    if reference_analysis:
        # 第三段：貼文原文
        original_post = reference_analysis.get('original_post', {})
        stage_3 = f"**貼文原文**:\n{original_post.get('content', '無參考原文')}"
        
        # 第四段：第一次分析結果 (結構分析)
        structure_guide = reference_analysis.get('structure_guide', {})
        stage_4 = f"**第一次分析結果 (結構特徵)**:\n{json.dumps(structure_guide, ensure_ascii=False, indent=2)}"
        
        # 第五段：第二次分析結果 (分析摘要)
        analysis_summary = reference_analysis.get('analysis_summary', {})
        stage_5 = f"**第二次分析結果 (分析摘要)**:\n{analysis_summary.get('analysis_summary', '無分析摘要')}"
    else:
        stage_3 = "**貼文原文**: 無參考原文"
        stage_4 = "**第一次分析結果**: 無參考分析"
        stage_5 = "**第二次分析結果**: 無參考分析"
    
    # 組合完整 prompt
    full_prompt = f"""{stage_1}

{stage_2}

{stage_3}

{stage_4}

{stage_5}

請根據以上信息，生成 5 個不同風格的貼文版本。每個版本用 "【版本X】" 標示，內容要符合指定的風格和長度要求。"""
    
    return full_prompt

def _parse_generated_posts(generated_content: str) -> List[str]:
    """
    解析 LLM 生成的多個貼文版本
    """
    try:
        # 尋找【版本X】格式的分隔符
        import re
        
        # 分割版本
        version_pattern = r'【版本\d+】'
        sections = re.split(version_pattern, generated_content)
        
        # 過濾掉空白和第一個部分（通常是介紹文字）
        posts = []
        for section in sections[1:]:  # 跳過第一個部分
            cleaned_post = section.strip()
            if cleaned_post:
                posts.append(cleaned_post)
        
        # 如果解析失敗，嘗試其他方法
        if not posts:
            # 嘗試按照空行分割
            lines = generated_content.split('\n')
            current_post = []
            posts = []
            
            for line in lines:
                line = line.strip()
                if not line:  # 空行，可能是分隔符
                    if current_post:
                        posts.append('\n'.join(current_post))
                        current_post = []
                elif not line.startswith(('版本', '【', '以下', '根據')):  # 過濾系統文字
                    current_post.append(line)
            
            # 添加最後一個貼文
            if current_post:
                posts.append('\n'.join(current_post))
        
        # 確保至少有一個版本
        if not posts:
            posts = [generated_content.strip()]
        
        # 限制最多 5 個版本
        return posts[:5]
        
    except Exception as e:
        logger.error(f"解析貼文版本失敗: {e}")
        # 返回原始內容作為單一版本
        return [generated_content.strip()]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8008)
