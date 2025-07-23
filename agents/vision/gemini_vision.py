"""
Gemini Vision 分析模組

使用 Gemini 2.5 Flash 分析截圖並提取社交媒體互動數據
"""

import os
import json
import base64
from typing import Dict, Any, Optional
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold


class GeminiVisionAnalyzer:
    """Gemini 2.5 Flash 視覺分析器"""
    
    def __init__(self):
        """初始化 Gemini 客戶端"""
        self.api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        
        if not self.api_key:
            raise ValueError("需要設定 GOOGLE_API_KEY 或 GEMINI_API_KEY 環境變數")
        
        # 配置 Gemini
        genai.configure(api_key=self.api_key)
        
        # 使用 Gemini 2.0 Flash (最新版本)
        self.model = genai.GenerativeModel("gemini-2.0-flash")
        
        # 安全設定 - 允許所有內容類型
        self.safety_settings = {
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }
        
        # 系統提示詞
        self.system_prompt = """
提取螢幕截圖中 Threads 貼文主要統計數字：

需要提取的數據：
- views: 觀看數量 (通常在貼文標題附近，格式如 "3.9K views")
- likes: 愛心數量 (愛心圖示旁的數字)
- comments: 留言數量 (氣泡圖示旁的數字)  
- reposts: 轉發數量 (旋轉箭頭圖示旁的數字)
- shares: 分享數量 (紙飛機圖示旁的數字)

重要規則：
1. 只提取主要貼文的數據，不要提取留言的數據
2. 如果某個數字不存在或看不清楚，輸出 0
3. 數字可能包含 K (千) 或 M (百萬) 後綴，請轉換為實際數字
4. 僅回傳 JSON 物件，不要其他文字

輸出格式：
{
  "views": 數字,
  "likes": 數字, 
  "comments": 數字,
  "reposts": 數字,
  "shares": 數字
}
"""
    
    async def analyze_screenshot(self, image_bytes: bytes) -> Dict[str, int]:
        """
        分析截圖並提取互動數據
        
        Args:
            image_bytes: 截圖的二進制數據
            
        Returns:
            包含 views, likes, comments, reposts, shares 的字典
        """
        try:
            # 創建圖片部分
            image_part = genai.ImagePart(image_bytes, "image/jpeg")
            text_part = genai.TextPart(self.system_prompt)
            
            # 生成內容
            response = self.model.generate_content(
                [image_part, text_part],
                safety_settings=self.safety_settings,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,  # 低溫度確保一致性
                    top_p=0.8,
                    top_k=40,
                    max_output_tokens=200,
                )
            )
            
            # 解析回應
            response_text = response.text.strip()
            
            # 嘗試解析 JSON
            try:
                data = json.loads(response_text)
                
                # 驗證和清理數據
                result = {
                    "views": self._parse_number(data.get("views", 0)),
                    "likes": self._parse_number(data.get("likes", 0)),
                    "comments": self._parse_number(data.get("comments", 0)),
                    "reposts": self._parse_number(data.get("reposts", 0)),
                    "shares": self._parse_number(data.get("shares", 0))
                }
                
                return result
                
            except json.JSONDecodeError:
                # 如果 JSON 解析失敗，嘗試從文字中提取數字
                return self._extract_numbers_from_text(response_text)
                
        except Exception as e:
            raise Exception(f"Gemini 視覺分析失敗: {str(e)}")
    
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
            test_image = base64.b64decode(
                "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/2wBDAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAv/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwA/8A"
            )
            
            response = self.model.generate_content([
                genai.ImagePart(test_image, "image/jpeg"),
                genai.TextPart("這是一個測試。請回覆 'OK'。")
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