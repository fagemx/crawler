"""
Gemini Vision 分析模組 (修正版)

支援 image/jpeg‧png 直接 ImagePart，video/mp4 走 upload_file → File 物件
"""

import os
import json
import tempfile
import time
from typing import Dict, Any
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import asyncio

from common.llm_usage_recorder import log_usage, get_service_name
from common.llm_manager import GeminiProvider, LLMRequest


class GeminiVisionAnalyzer:
    """Gemini Vision 分析器 - 正確使用 File API 處理影片"""
    
    def __init__(self):
        """初始化 Gemini 客戶端"""
        self.api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        
        if not self.api_key:
            raise ValueError("需要設定 GOOGLE_API_KEY 或 GEMINI_API_KEY 環境變數")
        
        # 配置 Gemini
        genai.configure(api_key=self.api_key)
        
        # 預設使用 Gemini 2.5 Pro（可由環境切換），保留舊版為備援
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
        self.model = genai.GenerativeModel(self.model_name)
        # 可調式最大輸出 token（避免描述被截斷）
        default_max = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "2048"))
        self.max_output_tokens_image = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS_IMAGE", str(default_max)))
        self.max_output_tokens_video = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS_VIDEO", str(max(default_max, 3072))))
        
        # 安全設定 - 允許所有內容類型
        self.safety_settings = {
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }
        
        # 圖片內容描述系統提示（建議 JSON，但允許純文字長段落）
        self.image_prompt = """
請詳細描述這張 Threads 社交媒體貼文圖片的內容：

描述重點：
1. **視覺元素**：圖片中的主要物件、人物、場景
2. **文字內容**：圖片中的所有可見文字（包括貼文內容、標籤、註解等）
3. **色彩和風格**：整體色調、設計風格、視覺效果
4. **情境和氛圍**：圖片傳達的情感、氛圍或主題
5. **技術細節**：圖片品質、構圖、特殊效果等

描述格式：
{
  "main_content": "主要內容描述",
  "text_content": "圖片中的文字內容",
  "visual_elements": "視覺元素描述",
  "style_and_mood": "風格和氛圍描述",
  "technical_notes": "技術細節說明"
}

請用繁體中文回應，描述要詳細且準確。優先使用上方 JSON 格式；若不便，也可輸出一段完整的長文字描述。
"""

        # 安全回退用的中性提示（僅客觀元素，避免敏感觸發）
        self.safe_image_prompt = """
請以客觀、中性的方式列出圖片中的可見元素與場景，不涉及裸露、性暗示、暴力或價值判斷。
輸出 JSON：
{
  "main_content": "重點客觀描述",
  "text_content": "圖片中的可見文字（若無留空）",
  "visual_elements": "主要物件/構圖/場景",
  "style_and_mood": "風格/色調（客觀詞彙）",
  "technical_notes": "解析度/光線/清晰度等技術觀察"
}
僅回傳 JSON。
        """

        # 影片內容描述系統提示（建議 JSON，但允許純文字長段落）
        self.video_prompt = """
請你擔任影片場景敘述與關鍵元素標記器。優先依照時間片段輸出結構化 JSON；若不便，也可輸出純文字的完整長段落描述。避免過度簡化，盡量涵蓋主要內容與字幕。

回傳 JSON 格式（物件）：
{
  "segments": [
    {
      "startTime": "00:00",
      "endTime": "00:02",
      "visual_description": "畫面所見客觀內容",
      "dialogue": { "chinese_subtitle": "若有字幕/對話，提供中文內容；沒有則省略此欄" }
    }
  ],
  "key_elements": { "people": [], "objects": [], "locations": [] },
  "message_and_tone": "整體訊息與情緒（中性詞彙）",
  "narrative_overview": "以 1-3 句話客觀總結影片敘事"
}

以繁體中文回覆。優先 JSON；否則輸出一段完整長文字即可。
        """

        # 從截圖中提取瀏覽次數的系統提示
        self.extract_views_prompt = """
        你是一個專注於從 Threads 貼文截圖中提取「瀏覽次數」的專家。
        你的任務是只找出代表瀏覽次數的數字，並忽略所有其他資訊（如按讚、留言、轉發等）。

        - **目標**：找出「次瀏覽」或「views」旁邊的數字。
        - **格式**：將數字轉換為整數 (integer)。例如 "1,234" 應為 1234，"1.2萬" 應為 12000，"1.2M" 應為 1200000。
        - **輸出**：必須以以下的 JSON 格式回傳，且不得包含任何其他文字或說明。
        - **如果找不到**：如果圖片中沒有瀏覽次數，回傳 `{"views_count": null}`。

        範例輸出:
        {"views_count": 12345}

        範例輸出（找不到時）:
        {"views_count": null}
        """
    
    async def extract_views_from_image(self, image_bytes: bytes) -> Dict[str, Any]:
        """
        從單張圖片中提取瀏覽次數。

        Args:
            image_bytes: 圖片的二進制數據。

        Returns:
            一個包含 `views_count` 的字典。
        """
        try:
            import base64
            media_part = {
                "mime_type": "image/jpeg", # 假設截圖為 jpeg
                "data": base64.b64encode(image_bytes).decode('utf-8')
            }
            
            start_ts = time.time()
            response = self.model.generate_content(
                [media_part, self.extract_views_prompt],
                safety_settings=self.safety_settings,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.0, # 溫度設為 0 以獲得最精確、可預測的結果
                    max_output_tokens=100, # 限制輸出 token 數量
                )
            )
            latency_ms = int((time.time() - start_ts) * 1000)
            
            response_text = response.text.strip()
            # 清理常見的 markdown code block
            if response_text.startswith("```json"):
                response_text = response_text[7:-3].strip()
            
            data = json.loads(response_text)
            
            # 驗證格式並確保 views_count 是整數或 None
            if "views_count" in data and data["views_count"] is not None:
                data["views_count"] = int(data["views_count"])
            else:
                data["views_count"] = -1 # 使用 -1 表示未找到，以便與 Playwright 的失敗情況區分

            # 嘗試記錄 usage（若 SDK 提供 usage_metadata）
            try:
                usage_md = getattr(response, 'usage_metadata', None)
                usage = {
                    'prompt_tokens': getattr(usage_md, 'prompt_token_count', 0) if usage_md else 0,
                    'completion_tokens': getattr(usage_md, 'candidates_token_count', 0) if usage_md else 0,
                    'total_tokens': getattr(usage_md, 'total_token_count', 0) if usage_md else 0,
                }
                # 無成本資訊，留 0；此處不做估算以保守穩定
                # 使用 LLMManager 的費率計算邏輯
                try:
                    from common.llm_manager import GeminiProvider
                    provider = GeminiProvider({})
                    cost = provider._calculate_cost(self.model_name, usage)
                except Exception:
                    cost = 0.0
                asyncio.create_task(log_usage(
                    provider="gemini",
                    model=self.model_name,
                    request_id=f"gemini_vision_{int(time.time()*1000)}",
                    prompt_tokens=usage['prompt_tokens'],
                    completion_tokens=usage['completion_tokens'],
                    total_tokens=usage['total_tokens'],
                    cost=cost,
                    latency_ms=latency_ms,
                    status="success",
                    service=get_service_name(),
                    metadata={"component": "gemini_vision.extract_views"},
                ))
            except Exception:
                pass

            return data

        except json.JSONDecodeError as e:
            print(f"❌ Gemini Vision - JSON 解析失敗: {e}, 回應: {response.text}")
            return {"views_count": -1} # 解析失敗也返回 -1
        except Exception as e:
            print(f"❌ Gemini Vision - 提取瀏覽次數時發生錯誤: {e}")
            raise Exception(f"Gemini Vision 提取瀏覽次數失敗: {str(e)}")

    
    async def analyze_media(self, media_bytes: bytes, mime_type: str, extra_text: str = None) -> Dict[str, Any]:
        """
        分析媒體（圖片或影片）並描述內容
        
        Args:
            media_bytes: 媒體的二進制數據
            mime_type: MIME 類型 (如 'image/jpeg', 'video/mp4')
            
        Returns:
            包含媒體內容描述的字典
        """
        try:
            # 根據 MIME 類型選擇處理方式
            is_image = False
            if mime_type.startswith('image/'):
                # 圖片：使用正確的 API 語法
                import base64
                media_part = {
                    "mime_type": mime_type,
                    "data": base64.b64encode(media_bytes).decode('utf-8')
                }
                prompt = self.image_prompt
                if extra_text:
                    # 將貼文原文作為額外上下文
                    context_text = f"貼文原文（作為圖片情境參考）：\n{extra_text}"
                    parts = [media_part, prompt, context_text]
                else:
                    parts = [media_part, prompt]
                is_image = True
                
            elif mime_type.startswith('video/'):
                # 影片：使用 File API
                file_obj = await self._upload_video_get_file(media_bytes, mime_type)
                prompt = self.video_prompt
                parts = [file_obj, prompt]
                
            else:
                raise ValueError(f"不支援的媒體類型: {mime_type}")
            
            # 生成內容
            start_ts = time.time()
            response = self.model.generate_content(
                parts,
                safety_settings=self.safety_settings,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.2,
                    top_p=0.9,
                    top_k=64,
                    max_output_tokens=(self.max_output_tokens_image if is_image else self.max_output_tokens_video),
                )
            )
            latency_ms = int((time.time() - start_ts) * 1000)
            
            # 解析回應（安全提取，避免 finish_reason=2 時拋例外）
            def _safe_text(resp):
                try:
                    txt = resp.text.strip()
                    if txt.startswith("```json") and txt.endswith("```"):
                        txt = txt[7:-3].strip()
                    return txt
                except Exception:
                    return None
            response_text = _safe_text(response)

            # 取得 finish_reason 判斷是否被安全阻擋
            finish_reason = None
            try:
                finish_reason = response.candidates[0].finish_reason if response.candidates else None
            except Exception:
                pass

            # 若遭安全阻擋或無文字，嘗試回退
            if response_text is None or finish_reason == 2:
                # 回退 1：圖片改用中性提示
                if is_image:
                    safe_parts = parts[:-1] + [self.safe_image_prompt] if isinstance(parts[-1], str) else parts + [self.safe_image_prompt]
                    try:
                        safe_resp = self.model.generate_content(
                            safe_parts,
                            safety_settings=self.safety_settings,
                            generation_config=genai.types.GenerationConfig(
                                temperature=0.0,
                                max_output_tokens=320,
                            )
                        )
                        response_text = _safe_text(safe_resp)
                        # 記錄回退使用量
                        try:
                            usage_md = getattr(safe_resp, 'usage_metadata', None)
                            usage = {
                                'prompt_tokens': getattr(usage_md, 'prompt_token_count', 0) if usage_md else 0,
                                'completion_tokens': getattr(usage_md, 'candidates_token_count', 0) if usage_md else 0,
                                'total_tokens': getattr(usage_md, 'total_token_count', 0) if usage_md else 0,
                            }
                            provider = GeminiProvider({})
                            cost = provider._calculate_cost(self.model_name, usage)
                            asyncio.create_task(log_usage(
                                provider="gemini",
                                model=self.model_name,
                                request_id=f"gemini_vision_{int(time.time()*1000)}",
                                prompt_tokens=usage['prompt_tokens'],
                                completion_tokens=usage['completion_tokens'],
                                total_tokens=usage['total_tokens'],
                                cost=cost,
                                latency_ms=latency_ms,
                                status="fallback_safe_prompt",
                                service=get_service_name(),
                                metadata={"component": "gemini_vision.analyze_media", "fallback": "safe_prompt"},
                            ))
                        except Exception:
                            pass
                    except Exception:
                        response_text = None

                # 回退 2：替代模型（image/video 都可）
                if response_text is None:
                    try:
                        alt_model_name = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.0-flash")
                        alt_model = genai.GenerativeModel(alt_model_name)
                        alt_parts = parts
                        if is_image:
                            # 確保使用中性提示
                            alt_parts = parts[:-1] + [self.safe_image_prompt] if isinstance(parts[-1], str) else parts + [self.safe_image_prompt]
                        alt_resp = alt_model.generate_content(
                            alt_parts,
                            safety_settings=self.safety_settings,
                            generation_config=genai.types.GenerationConfig(
                                temperature=0.0,
                                max_output_tokens=320,
                            )
                        )
                        response_text = _safe_text(alt_resp)
                        try:
                            usage_md = getattr(alt_resp, 'usage_metadata', None)
                            usage = {
                                'prompt_tokens': getattr(usage_md, 'prompt_token_count', 0) if usage_md else 0,
                                'completion_tokens': getattr(usage_md, 'candidates_token_count', 0) if usage_md else 0,
                                'total_tokens': getattr(usage_md, 'total_token_count', 0) if usage_md else 0,
                            }
                            provider = GeminiProvider({})
                            cost = provider._calculate_cost(alt_model_name, usage)
                            asyncio.create_task(log_usage(
                                provider="gemini",
                                model=alt_model_name,
                                request_id=f"gemini_vision_{int(time.time()*1000)}",
                                prompt_tokens=usage['prompt_tokens'],
                                completion_tokens=usage['completion_tokens'],
                                total_tokens=usage['total_tokens'],
                                cost=cost,
                                latency_ms=latency_ms,
                                status="fallback_alt_model",
                                service=get_service_name(),
                                metadata={"component": "gemini_vision.analyze_media", "fallback": "alt_model"},
                            ))
                        except Exception:
                            pass
                    except Exception:
                        response_text = None
            
            # 嘗試解析 JSON（寬鬆處理 ```json 包裹、陣列包裝）
            try:
                if response_text is None:
                    raise json.JSONDecodeError("no text", "", 0)
                txt = response_text.strip()
                if txt.startswith("```json"):
                    txt = txt[7:]
                if txt.endswith("```"):
                    txt = txt[:-3]
                txt = txt.strip()
                data = json.loads(txt)
                if isinstance(data, list):
                    data = {"segments": data}
                # 記錄 usage
                try:
                    usage_md = getattr(response, 'usage_metadata', None)
                    usage = {
                        'prompt_tokens': getattr(usage_md, 'prompt_token_count', 0) if usage_md else 0,
                        'completion_tokens': getattr(usage_md, 'candidates_token_count', 0) if usage_md else 0,
                        'total_tokens': getattr(usage_md, 'total_token_count', 0) if usage_md else 0,
                    }
                    try:
                        from common.llm_manager import GeminiProvider
                        provider = GeminiProvider({})
                        cost = provider._calculate_cost(self.model_name, usage)
                    except Exception:
                        cost = 0.0
                    asyncio.create_task(log_usage(
                        provider="gemini",
                        model=self.model_name,
                        request_id=f"gemini_vision_{int(time.time()*1000)}",
                        prompt_tokens=usage['prompt_tokens'],
                        completion_tokens=usage['completion_tokens'],
                        total_tokens=usage['total_tokens'],
                        cost=cost,
                        latency_ms=latency_ms,
                        status="success",
                        service=get_service_name(),
                        metadata={"component": "gemini_vision.analyze_media", "mime": mime_type},
                    ))
                except Exception:
                    pass
                return data  # 直接返回內容描述的 JSON
                
            except json.JSONDecodeError:
                # 如果 JSON 解析失敗或無文字，返回最小可用結構（避免整批失敗）
                if mime_type.startswith('image/'):
                    if response_text is None:
                        return {
                            "blocked": True,
                            "reason": "safety_block_or_empty",
                            "main_content": "受內容安全限制或無輸出，返回中性占位描述。",
                            "text_content": "",
                            "visual_elements": "",
                            "style_and_mood": "",
                            "technical_notes": "fallback"
                        }
                    return {
                        "main_content": response_text,
                        "text_content": "",
                        "visual_elements": "",
                        "style_and_mood": "",
                        "technical_notes": "JSON 解析失敗，返回原始回應"
                    }
                else:  # video
                    if response_text is None:
                        return {
                            "blocked": True,
                            "reason": "safety_block_or_empty",
                            "narrative_overview": "受內容安全限制或無輸出，返回中性占位描述。",
                            "key_elements": {"people": [], "objects": [], "locations": []},
                            "message_and_tone": "fallback",
                            "segments": []
                        }
                    return {
                        "narrative_overview": response_text,
                        "key_elements": {
                            "people": [],
                            "objects": [],
                            "locations": []
                        },
                        "message_and_tone": "JSON 解析失敗，返回原始回應",
                        "segments": []
                    }
                
        except Exception as e:
            raise Exception(f"Gemini 視覺分析失敗: {str(e)}")
    
    async def _upload_video_get_file(self, media_bytes: bytes, mime_type: str):
        """
        上傳影片到 Gemini File API 並等待處理完成
        
        Args:
            media_bytes: 影片的二進制數據
            mime_type: MIME 類型
            
        Returns:
            genai.File: 已處理完成的檔案物件
        """
        # 1. 先寫到臨時檔案，因為 upload_file 目前只能吃檔案路徑
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
            tmp.write(media_bytes)
            tmp_path = tmp.name
        
        try:
            # 2. 上傳檔案
            file_obj = genai.upload_file(path=tmp_path, display_name="threads_video")
            
            # 3. 等待狀態變為 ACTIVE
            while file_obj.state.name != "ACTIVE":
                print(f"等待檔案處理中... 狀態: {file_obj.state.name}")
                time.sleep(2)
                file_obj = genai.get_file(file_obj.name)
            
            return file_obj
            
        finally:
            # 4. 清理臨時檔案
            import os
            try:
                os.unlink(tmp_path)
            except:
                pass
    
    # 保持向後兼容性的方法
    async def analyze_screenshot(self, image_bytes: bytes) -> Dict[str, int]:
        """
        分析截圖並提取互動數據（向後兼容方法）
        
        Args:
            image_bytes: 截圖的二進制數據
            
        Returns:
            包含 views, likes, comments, reposts, shares 的字典
        """
        return await self.analyze_media(image_bytes, "image/jpeg")
    
    def _parse_number(self, value) -> int:
        """解析數字，處理 K/M 後綴"""
        if value is None:
            return 0
        
        if isinstance(value, int):
            return max(0, value)
        
        if isinstance(value, str):
            value = value.strip().upper()
            
            # 處理 K 後綴
            if value.endswith('K'):
                try:
                    return int(float(value[:-1]) * 1000)
                except:
                    return 0
            
            # 處理 M 後綴
            if value.endswith('M'):
                try:
                    return int(float(value[:-1]) * 1000000)
                except:
                    return 0
            
            # 處理普通數字
            try:
                return int(value.replace(',', ''))
            except:
                return 0
        
        return 0
    
    def _extract_numbers_from_text(self, text: str) -> Dict[str, int]:
        """從文字中提取數字（備用方法）"""
        import re
        
        result = {
            "views": 0,
            "likes": 0, 
            "comments": 0,
            "reposts": 0,
            "shares": 0
        }
        
        # 嘗試用正則表達式提取
        patterns = {
            "views": r'"views":\s*(\d+)',
            "likes": r'"likes":\s*(\d+)',
            "comments": r'"comments":\s*(\d+)',
            "reposts": r'"reposts":\s*(\d+)',
            "shares": r'"shares":\s*(\d+)'
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, text)
            if match:
                result[key] = int(match.group(1))
        
        return result
    
    async def test_connection(self) -> Dict[str, Any]:
        """測試 Gemini API 連接"""
        try:
            # 創建一個簡單的測試圖片 (1x1 像素的白色圖片)
            import base64
            test_image_b64 = "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/2wBDAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAv/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwA/8A"
            
            test_image_part = {
                "mime_type": "image/jpeg",
                "data": test_image_b64
            }
            
            response = self.model.generate_content([
                test_image_part,
                "這是一個測試。請回覆 'OK'。"
            ])
            
            return {
                "status": "healthy",
                "service": "Gemini 2.0 Flash",
                "test_response": response.text[:100] if response.text else "無回應"
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": f"Gemini API 測試失敗: {str(e)}"
            }
    
    def health_check(self) -> Dict[str, Any]:
        """健康檢查"""
        try:
            if not self.api_key:
                return {
                    "status": "unhealthy",
                    "error": "缺少 Gemini API 金鑰"
                }
            
            return {
                "status": "healthy",
                "service": "Gemini 2.0 Flash",
                "api_key_configured": bool(self.api_key),
                "model": "gemini-2.0-flash"
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": f"Gemini 健康檢查失敗: {str(e)}"
            }