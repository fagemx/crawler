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
import httpx
import base64
import hashlib

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

# 媒體分析快取（記憶體快取，避免重複分析同一媒體）
media_analysis_cache: Dict[str, str] = {}

async def analyze_media_with_vision(media: Dict[str, Any]) -> List[str]:
    """
    使用 GeminiVisionAnalyzer 分析媒體內容，返回文字描述列表
    """
    media_descriptions = []
    
    try:
        # 導入 GeminiVisionAnalyzer
        from agents.vision.gemini_vision import GeminiVisionAnalyzer
        
        # 檢查環境變數
        import os
        gemini_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        logger.info(f"GEMINI API KEY 狀態: {'已設置' if gemini_key else '未設置'}")
        
        analyzer = GeminiVisionAnalyzer()
        logger.info("GeminiVisionAnalyzer 初始化成功")
        
        # 處理圖片
        images = media.get('images', [])
        for i, img in enumerate(images):
            try:
                # 生成快取鍵（基於 URL 或 key）
                cache_key = None
                if img.get('key'):
                    cache_key = f"img:{img['key']}"
                elif img.get('url'):
                    cache_key = f"img:{hashlib.md5(img['url'].encode()).hexdigest()}"
                
                # 檢查快取
                if cache_key and cache_key in media_analysis_cache:
                    desc = media_analysis_cache[cache_key]
                    media_descriptions.append(f"圖片 {i+1} 內容描述：{desc}")
                    logger.info(f"圖片 {i+1} 使用快取分析結果")
                    continue
                
                # 準備圖片數據
                image_data = None
                content_type = img.get('content_type') or img.get('mime') or 'image/jpeg'
                
                # 如果有 base64 數據，直接使用
                if img.get('data_base64'):
                    image_data = base64.b64decode(img['data_base64'])
                # 否則嘗試透過 RustFS key 產生在容器內可訪問的 URL，再下載
                elif img.get('key') or img.get('url') or img.get('rustfs_url'):
                    url = None
                    try:
                        if img.get('key'):
                            from services.rustfs_client import RustFSClient
                            _rclient = RustFSClient()
                            # 產生對容器可用的 URL（優先 presigned）
                            url = _rclient.get_public_or_presigned_url(img['key'], prefer_presigned=True)
                        else:
                            url = img.get('url') or img.get('rustfs_url')
                            # 避免容器內使用 localhost/127.0.0.1/0.0.0.0，若偵測到則改用 RUSTFS_ENDPOINT
                            if url:
                                from urllib.parse import urlparse, urlunparse
                                parsed = urlparse(url)
                                host = (parsed.hostname or '').lower()
                                if host in {"localhost", "127.0.0.1", "0.0.0.0"}:
                                    from services.rustfs_client import RustFSClient
                                    _rclient = RustFSClient()
                                    # 嘗試從原 URL path 還原 key，重新生成合法簽名 URL
                                    path_no_slash = parsed.path.lstrip('/')
                                    key_from_url = path_no_slash
                                    try:
                                        bucket = _rclient.bucket_name
                                        if path_no_slash.startswith(bucket + "/"):
                                            key_from_url = path_no_slash[len(bucket)+1:]
                                    except Exception:
                                        pass
                                    regen = _rclient.get_public_or_presigned_url(key_from_url, prefer_presigned=True)
                                    if regen:
                                        url = regen
                                        logger.info(f"已用 key 重新產生簽名 URL（容器可用）: {url}")
                                    else:
                                        # 最後才嘗試直接替換主機（可能會導致簽名失效）
                                        base_parsed = urlparse(_rclient.base_url)
                                        url = urlunparse((
                                            base_parsed.scheme or 'http',
                                            base_parsed.netloc,
                                            parsed.path,
                                            '',
                                            parsed.query,
                                            ''
                                        ))
                                        logger.info(f"已替換 localhost 為 RUSTFS_ENDPOINT，用於容器內訪問: {url}")
                    except Exception:
                        url = img.get('url') or img.get('rustfs_url')

                    # 最後保險：無論來源，統一在請求前再做一次容器可用 URL 正規化
                    try:
                        if url:
                            from urllib.parse import urlparse
                            parsed = urlparse(url)
                            host = (parsed.hostname or '').lower()
                            if host in {"localhost", "127.0.0.1", "0.0.0.0"}:
                                from services.rustfs_client import RustFSClient
                                _rclient = RustFSClient()
                                path_no_slash = parsed.path.lstrip('/')
                                key_from_url = path_no_slash
                                try:
                                    bucket = _rclient.bucket_name
                                    if path_no_slash.startswith(bucket + "/"):
                                        key_from_url = path_no_slash[len(bucket)+1:]
                                except Exception:
                                    pass
                                regen2 = _rclient.get_public_or_presigned_url(key_from_url, prefer_presigned=True)
                                if regen2:
                                    url = regen2
                                    logger.info(f"已二次正規化為容器可用 URL: {url}")
                    except Exception:
                        pass

                    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                        if url:
                            logger.info(f"下載圖片使用 URL: {url}")
                        response = await client.get(url)
                        response.raise_for_status()
                        image_data = response.content
                        content_type = response.headers.get('content-type', content_type)
                
                if not image_data:
                    continue
                    
                # 直接調用 GeminiVisionAnalyzer 分析圖片
                logger.info(f"開始分析第 {i+1} 張圖片...")
                logger.info(f"圖片大小: {len(image_data)} bytes, 類型: {content_type}")
                analysis_result = await analyzer.analyze_media(image_data, content_type)

                # 萃取可讀描述
                desc = None
                try:
                    if isinstance(analysis_result, dict):
                        if analysis_result.get('main_content'):
                            # 圖片主要描述
                            parts = [analysis_result.get('main_content')]
                            aux = []
                            if analysis_result.get('text_content'):
                                aux.append(f"文字: {analysis_result['text_content']}")
                            if analysis_result.get('visual_elements'):
                                aux.append(f"元素: {analysis_result['visual_elements']}")
                            if aux:
                                parts.append("；".join(aux))
                            desc = " ".join(parts)
                        elif analysis_result.get('narrative_overview'):
                            desc = analysis_result.get('narrative_overview')
                        elif isinstance(analysis_result.get('segments'), list) and analysis_result['segments']:
                            seg = analysis_result['segments'][0]
                            desc = seg.get('visual_description') or str(seg)
                except Exception:
                    desc = None

                if desc:
                    media_descriptions.append(f"圖片 {i+1} 內容描述：{desc}")
                    logger.info(f"圖片 {i+1} 分析完成")

                    # 存入快取
                    if cache_key:
                        media_analysis_cache[cache_key] = desc
                        logger.info(f"圖片 {i+1} 分析結果已快取")
                else:
                    media_descriptions.append(f"圖片 {i+1} 內容：（分析未獲得有效結果）")
                    
            except Exception as e:
                logger.warning(f"圖片 {i+1} 分析失敗: {e}")
                # 提供基本的圖片描述作為 fallback
                safe_size = len(image_data) if ('image_data' in locals() and image_data is not None) else '未知'
                fallback_desc = f"已上傳圖片 {i+1}（類型：{content_type}，大小：{safe_size} bytes）。請根據此圖片內容進行創作，需要體現圖片中的主要元素和特色。"
                media_descriptions.append(f"圖片 {i+1} 內容描述：{fallback_desc}")
        
        # 處理影片
        videos = media.get('videos', [])
        for i, vid in enumerate(videos):
            try:
                # 生成快取鍵（基於 URL 或 key）
                cache_key = None
                if vid.get('key'):
                    cache_key = f"vid:{vid['key']}"
                elif vid.get('url'):
                    cache_key = f"vid:{hashlib.md5(vid['url'].encode()).hexdigest()}"
                
                # 檢查快取
                if cache_key and cache_key in media_analysis_cache:
                    desc = media_analysis_cache[cache_key]
                    media_descriptions.append(f"影片 {i+1} 內容描述：{desc}")
                    logger.info(f"影片 {i+1} 使用快取分析結果")
                    continue
                
                # 準備影片數據
                video_data = None
                content_type = vid.get('content_type') or vid.get('mime') or 'video/mp4'
                
                # 如果有 base64 數據，直接使用
                if vid.get('data_base64'):
                    video_data = base64.b64decode(vid['data_base64'])
                # 否則從 RustFS 取得容器可訪問的 URL 再下載（注意影片可能很大）
                elif vid.get('key') or vid.get('url') or vid.get('rustfs_url'):
                    url = None
                    try:
                        if vid.get('key'):
                            from services.rustfs_client import RustFSClient
                            _rclient = RustFSClient()
                            url = _rclient.get_public_or_presigned_url(vid['key'], prefer_presigned=True)
                        else:
                            url = vid.get('url') or vid.get('rustfs_url')
                            if url:
                                from urllib.parse import urlparse, urlunparse
                                parsed = urlparse(url)
                                host = (parsed.hostname or '').lower()
                                if host in {"localhost", "127.0.0.1", "0.0.0.0"}:
                                    from services.rustfs_client import RustFSClient
                                    _rclient = RustFSClient()
                                    path_no_slash = parsed.path.lstrip('/')
                                    key_from_url = path_no_slash
                                    try:
                                        bucket = _rclient.bucket_name
                                        if path_no_slash.startswith(bucket + "/"):
                                            key_from_url = path_no_slash[len(bucket)+1:]
                                    except Exception:
                                        pass
                                    regen = _rclient.get_public_or_presigned_url(key_from_url, prefer_presigned=True)
                                    if regen:
                                        url = regen
                                        logger.info(f"已用 key 重新產生簽名 URL（容器可用）: {url}")
                                    else:
                                        base_parsed = urlparse(_rclient.base_url)
                                        url = urlunparse((
                                            base_parsed.scheme or 'http',
                                            base_parsed.netloc,
                                            parsed.path,
                                            '',
                                            parsed.query,
                                            ''
                                        ))
                                        logger.info(f"已替換 localhost 為 RUSTFS_ENDPOINT，用於容器內訪問: {url}")
                    except Exception:
                        url = vid.get('url') or vid.get('rustfs_url')

                    # 最後保險：統一對影片 URL 也做一次容器可用正規化
                    try:
                        if url:
                            from urllib.parse import urlparse
                            parsed = urlparse(url)
                            host = (parsed.hostname or '').lower()
                            if host in {"localhost", "127.0.0.1", "0.0.0.0"}:
                                from services.rustfs_client import RustFSClient
                                _rclient = RustFSClient()
                                path_no_slash = parsed.path.lstrip('/')
                                key_from_url = path_no_slash
                                try:
                                    bucket = _rclient.bucket_name
                                    if path_no_slash.startswith(bucket + "/"):
                                        key_from_url = path_no_slash[len(bucket)+1:]
                                except Exception:
                                    pass
                                regen2 = _rclient.get_public_or_presigned_url(key_from_url, prefer_presigned=True)
                                if regen2:
                                    url = regen2
                                    logger.info(f"已二次正規化為容器可用 URL: {url}")
                    except Exception:
                        pass

                    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
                        if url:
                            logger.info(f"下載影片使用 URL: {url}")
                        response = await client.get(url)
                        response.raise_for_status()
                        video_data = response.content
                        content_type = response.headers.get('content-type', content_type)
                
                if not video_data:
                    continue
                    
                # 直接調用 GeminiVisionAnalyzer 分析影片
                logger.info(f"開始分析第 {i+1} 個影片...")
                analysis_result = await analyzer.analyze_media(video_data, content_type)

                # 萃取可讀描述
                desc = None
                try:
                    if isinstance(analysis_result, dict):
                        if analysis_result.get('narrative_overview'):
                            desc = analysis_result.get('narrative_overview')
                        elif isinstance(analysis_result.get('segments'), list) and analysis_result['segments']:
                            seg = analysis_result['segments'][0]
                            desc = seg.get('visual_description') or str(seg)
                        elif analysis_result.get('main_content'):
                            desc = analysis_result.get('main_content')
                except Exception:
                    desc = None

                if desc:
                    media_descriptions.append(f"影片 {i+1} 內容描述：{desc}")
                    logger.info(f"影片 {i+1} 分析完成")

                    # 存入快取
                    if cache_key:
                        media_analysis_cache[cache_key] = desc
                        logger.info(f"影片 {i+1} 分析結果已快取")
                else:
                    media_descriptions.append(f"影片 {i+1} 內容：（分析未獲得有效結果）")
                    
            except Exception as e:
                logger.warning(f"影片 {i+1} 分析失敗: {e}")
                # 提供基本的影片描述作為 fallback
                safe_vsize = len(video_data) if ('video_data' in locals() and video_data is not None) else '未知'
                fallback_desc = f"已上傳影片 {i+1}（類型：{content_type}，大小：{safe_vsize} bytes）。請根據此影片內容進行創作，需要體現影片中的主要場景和內容。"
                media_descriptions.append(f"影片 {i+1} 內容描述：{fallback_desc}")
        
    except Exception as e:
        logger.error(f"媒體分析器初始化失敗: {e}")
        media_descriptions.append("媒體內容：（分析服務不可用）")
    
    return media_descriptions

# 初始化 LLM 管理器
llm_manager = LLMManager()

class ContentGenerationRequest(BaseModel):
    user_prompt: str
    llm_config: Optional[Dict[str, Any]] = None
    settings: Dict[str, Any]
    reference_analysis: Optional[Dict[str, Any]] = None
    media: Optional[Dict[str, Any]] = None  # {enabled: bool, images: [{name,mime}], videos: [{name,mime}]}

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
            reference_analysis=request.reference_analysis,
            media=request.media
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
        
        # 調用 LLM：若啟用媒體且有上傳，使用兩步驟處理（先分析媒體，再生成內容）
        messages = [{"role": "user", "content": full_prompt}]
        metadata = {"usage_scene": "post-writing"}
        
        # 處理媒體（改為兩步驟：先分析媒體內容，再用純文字模式生成）
        if request.media and request.media.get('enabled') and ((request.media.get('images')) or (request.media.get('videos'))):
            logger.info("開始兩步驟媒體處理：先分析媒體內容")
            try:
                # 第一步：調用 vision 服務分析媒體內容
                media_descriptions = await analyze_media_with_vision(request.media)
                
                if media_descriptions:
                    logger.info(f"媒體分析完成，獲得 {len(media_descriptions)} 個描述")
                    for i, desc in enumerate(media_descriptions):
                        logger.info(f"媒體描述 {i+1}: {desc[:100]}...")  # 顯示前100字
                    
                    # 第二步：重新構建 prompt，加入媒體描述
                    full_prompt_with_media = _build_five_stage_prompt(
                        user_prompt=request.user_prompt,
                        settings=request.settings,
                        post_count=post_count,
                        reference_analysis=request.reference_analysis,
                        media=request.media,
                        media_descriptions=media_descriptions  # 傳入媒體描述
                    )
                    
                    # 更新 messages 為包含媒體描述的版本
                    messages = [{"role": "user", "content": full_prompt_with_media}]
                    logger.info("已將媒體描述整合到提示中，使用純文字模式生成")
                    logger.info(f"最終提示前500字: {full_prompt_with_media[:500]}...")
                else:
                    logger.warning("媒體分析未獲得有效描述，退回原始提示")
                    
            except Exception as media_err:
                logger.error(f"媒體處理失敗: {media_err}")
                logger.info("媒體處理失敗，退回純文字模式")
        generated_content = await llm_manager.chat_completion(
            messages=messages,
            model=model_name,
            provider=provider,
            max_tokens=4096,
            temperature=0.8,
            **metadata
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
    reference_analysis: Optional[Dict[str, Any]] = None,
    media: Optional[Dict[str, Any]] = None,
    media_descriptions: Optional[List[str]] = None,
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
    
    # 第六段：媒體素材（可選）
    stage_6 = ""
    if media and media.get('enabled'):
        media_parts = []
        
        # 如果有媒體描述，優先使用描述
        if media_descriptions:
            media_parts.append("**媒體內容描述**:")
            for i, desc in enumerate(media_descriptions, 1):
                media_parts.append(f"{i}. {desc}")
            media_parts.append("")
            media_parts.append("**創作要求**:")
            media_parts.append("- 必須根據上述媒體內容進行創作")
            media_parts.append("- 貼文內容要與媒體內容相關呼應")
            media_parts.append("- 可自然地提及媒體中的具體元素、場景或內容")
            media_parts.append("- 文字與媒體要形成良好的搭配")
        else:
            # 退回原始提示
            if media.get('images'):
                media_parts.append("請根據圖片內容傳達情緒，與模板設計貼文，圖片與文字需要搭配，兩者呼應且相關。必要時文字會自然講到圖片的內容。")
            if media.get('videos'):
                media_parts.append("可搭配影片內容設計貼文，如果沒有特別要求以文字文主。影片內容可自由參考，自然呼應即可。")
        
        if media_parts:
            stage_6 = "**媒體素材提示**:\n" + "\n".join(media_parts)

    # 組合完整 prompt
    full_prompt = f"""{stage_1}

{stage_2}

{stage_3}

{stage_4}

{stage_5}

{stage_6}

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
