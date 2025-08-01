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


class GeminiVisionAnalyzer:
    """Gemini Vision 分析器 - 正確使用 File API 處理影片"""
    
    def __init__(self):
        """初始化 Gemini 客戶端"""
        self.api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        
        if not self.api_key:
            raise ValueError("需要設定 GOOGLE_API_KEY 或 GEMINI_API_KEY 環境變數")
        
        # 配置 Gemini
        genai.configure(api_key=self.api_key)
        
        # 使用 Gemini 2.0 Flash
        self.model = genai.GenerativeModel("gemini-2.0-flash")
        
        # 安全設定 - 允許所有內容類型
        self.safety_settings = {
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }
        
        # 圖片內容描述系統提示
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

請用繁體中文回應，描述要詳細且準確。
"""

        # 影片內容描述系統提示
        self.video_prompt = """
        請詳細描述這個 Threads 社交媒體影片的內容：

        描述重點：
        1. **影片概要**：影片的主要內容和主題
        2. **場景描述**：影片中的場景、環境、背景
        3. **動作和事件**：影片中發生的動作、事件序列
        4. **人物和對象**：出現的人物、物件及其互動
        5. **音視覺效果**：視覺效果、轉場、文字覆蓋等
        6. **文字內容**：影片中出現的所有文字（字幕、標題、註解等）
        7. **情感和氛圍**：影片傳達的情感、氛圍或訊息

        描述格式：
        {
          "video_summary": "影片概要",
          "scene_description": "場景描述",
          "actions_and_events": "動作和事件",
          "characters_and_objects": "人物和對象",
          "visual_effects": "視覺效果",
          "text_content": "文字內容",
          "mood_and_message": "情感和訊息"
        }

        請用繁體中文回應，描述要詳細且準確，特別注意影片的時間序列和動態變化。
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
            
            response = self.model.generate_content(
                [media_part, self.extract_views_prompt],
                safety_settings=self.safety_settings,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.0, # 溫度設為 0 以獲得最精確、可預測的結果
                    max_output_tokens=100, # 限制輸出 token 數量
                )
            )
            
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

            return data

        except json.JSONDecodeError as e:
            print(f"❌ Gemini Vision - JSON 解析失敗: {e}, 回應: {response.text}")
            return {"views_count": -1} # 解析失敗也返回 -1
        except Exception as e:
            print(f"❌ Gemini Vision - 提取瀏覽次數時發生錯誤: {e}")
            raise Exception(f"Gemini Vision 提取瀏覽次數失敗: {str(e)}")

    
    async def analyze_media(self, media_bytes: bytes, mime_type: str) -> Dict[str, Any]:
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
            if mime_type.startswith('image/'):
                # 圖片：使用正確的 API 語法
                import base64
                media_part = {
                    "mime_type": mime_type,
                    "data": base64.b64encode(media_bytes).decode('utf-8')
                }
                prompt = self.image_prompt
                parts = [media_part, prompt]
                
            elif mime_type.startswith('video/'):
                # 影片：使用 File API
                file_obj = await self._upload_video_get_file(media_bytes, mime_type)
                prompt = self.video_prompt
                parts = [file_obj, prompt]
                
            else:
                raise ValueError(f"不支援的媒體類型: {mime_type}")
            
            # 生成內容
            response = self.model.generate_content(
                parts,
                safety_settings=self.safety_settings,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,  # 低溫度確保一致性
                    top_p=0.8,
                    top_k=40,
                    max_output_tokens=512,
                )
            )
            
            # 解析回應
            response_text = response.text.strip()
            
            # 嘗試解析 JSON
            try:
                data = json.loads(response_text)
                return data  # 直接返回內容描述的 JSON
                
            except json.JSONDecodeError:
                # 如果 JSON 解析失敗，返回原始文字
                if mime_type.startswith('image/'):
                    return {
                        "main_content": response_text,
                        "text_content": "",
                        "visual_elements": "",
                        "style_and_mood": "",
                        "technical_notes": "JSON 解析失敗，返回原始回應"
                    }
                else:  # video
                    return {
                        "video_summary": response_text,
                        "scene_description": "",
                        "actions_and_events": "",
                        "characters_and_objects": "",
                        "visual_effects": "",
                        "text_content": "",
                        "mood_and_message": "JSON 解析失敗，返回原始回應"
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