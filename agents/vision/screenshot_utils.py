"""
Screenshot 工具模組

使用 Jina Reader 的 x-respond-with: screenshot 功能捕獲網頁截圖
"""

import requests
import re
import json
from typing import Dict, Optional

from google import genai
from google.genai import types


class JinaScreenshotCapture:
    """Jina Reader Screenshot 封裝類別"""
    
    def __init__(self):
        """初始化 Jina Reader 客戶端"""
        self.base_url = "https://r.jina.ai/{url}"
        self.headers_markdown = {"x-respond-with": "markdown"}
        self.headers_screenshot = {"x-respond-with": "screenshot"}
        
        # Markdown 解析正則表達式
        self.metrics_pattern = re.compile(
            r'\*\*?Thread.*? (?P<views>[\d\.KM,]+) views.*?'
            r'愛心.*? (?P<likes>[\d\.KM,]*) .*?'
            r'留言.*? (?P<comments>[\d\.KM,]*) .*?'
            r'轉發.*? (?P<reposts>[\d\.KM,]*) .*?'
            r'分享.*? (?P<shares>[\d\.KM,]*)', 
            re.S
        )
        
        # Gemini Vision 設定
        self.vision_prompt = """
請讀取螢幕截圖中 Threads 主貼文下方的五個數字：
views、likes、comments、reposts、shares。
若不存在請輸出 0。僅回傳 JSON：
{"views":x,"likes":x,"comments":x,"reposts":x,"shares":x}
"""
    
    def _parse_number(self, text: str) -> Optional[int]:
        """解析數字字串（支援 K, M 後綴）"""
        if not text:
            return None
        
        text = text.strip()
        if not text:
            return None
            
        try:
            if text.lower().endswith(('k', 'K')):
                return int(float(text[:-1]) * 1_000)
            elif text.lower().endswith(('m', 'M')):
                return int(float(text[:-1]) * 1_000_000)
            else:
                return int(text.replace(',', ''))
        except (ValueError, TypeError):
            return None
    
    def get_markdown_metrics(self, post_url: str) -> Dict[str, Optional[int]]:
        """從 Markdown 解析貼文指標"""
        try:
            jina_url = self.base_url.format(url=post_url)
            response = requests.get(
                jina_url, 
                headers=self.headers_markdown, 
                timeout=30
            )
            response.raise_for_status()
            
            markdown_text = response.text
            match = self.metrics_pattern.search(markdown_text)
            
            if not match:
                return {
                    "views": None,
                    "likes": None, 
                    "comments": None,
                    "reposts": None,
                    "shares": None
                }
            
            groups = match.groupdict()
            return {
                "views": self._parse_number(groups.get("views")),
                "likes": self._parse_number(groups.get("likes")),
                "comments": self._parse_number(groups.get("comments")),
                "reposts": self._parse_number(groups.get("reposts")),
                "shares": self._parse_number(groups.get("shares"))
            }
            
        except Exception as e:
            raise Exception(f"Markdown 解析失敗 {post_url}: {str(e)}")
    
    def get_screenshot_bytes(self, post_url: str) -> bytes:
        """取得貼文截圖的 binary bytes"""
        try:
            jina_url = self.base_url.format(url=post_url)
            response = requests.get(
                jina_url,
                headers=self.headers_screenshot,
                timeout=45
            )
            response.raise_for_status()
            return response.content  # 直接回傳 binary bytes
            
        except Exception as e:
            raise Exception(f"截圖取得失敗 {post_url}: {str(e)}")
    
    def analyze_with_vision(self, image_bytes: bytes, gemini_api_key: str) -> Dict[str, int]:
        """使用 Gemini Vision 分析截圖"""
        try:
            client = genai.Client(api_key=gemini_api_key)
            
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part(inline_data=types.Blob(mime_type="image/png", data=image_bytes)),
                            types.Part(text=self.vision_prompt)
                        ]
                    )
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            
            result = json.loads(response.text)
            
            # 如果回傳的是 list，取第一個元素
            if isinstance(result, list) and len(result) > 0:
                return result[0]
            elif isinstance(result, dict):
                return result
            else:
                print(f"警告: 未預期的 Gemini 回應格式: {type(result)} - {result}")
                return {}
            
        except Exception as e:
            raise Exception(f"Vision 分析失敗: {str(e)}")
    
    def fill_missing_with_vision(
        self, 
        post_url: str, 
        partial_metrics: Dict[str, Optional[int]],
        gemini_api_key: str
    ) -> Dict[str, int]:
        """用 Vision 補完缺失的指標"""
        # 檢查是否需要 Vision 補值
        required_keys = ["likes", "comments", "reposts", "shares"]
        if all(partial_metrics.get(k) is not None for k in required_keys):
            return {k: v for k, v in partial_metrics.items() if v is not None}
        
        # 取得截圖並分析
        image_bytes = self.get_screenshot_bytes(post_url)
        vision_metrics = self.analyze_with_vision(image_bytes, gemini_api_key)
        
        # 合併結果，優先使用 Markdown 解析的值
        result = {}
        for key in ["views", "likes", "comments", "reposts", "shares"]:
            if partial_metrics.get(key) is not None:
                result[key] = partial_metrics[key]
            else:
                # 確保 vision_metrics 是 dict
                if isinstance(vision_metrics, dict):
                    result[key] = vision_metrics.get(key, 0)
                else:
                    print(f"警告: vision_metrics 不是 dict，而是 {type(vision_metrics)}: {vision_metrics}")
                    result[key] = 0
        
        return result
    
    def get_complete_metrics(self, post_url: str, gemini_api_key: str) -> Dict[str, int]:
        """取得完整的貼文指標（Markdown + Vision 補值）"""
        markdown_metrics = self.get_markdown_metrics(post_url)
        return self.fill_missing_with_vision(post_url, markdown_metrics, gemini_api_key)
    
    def health_check(self) -> Dict[str, any]:
        """健康檢查"""
        try:
            # 測試 Jina Reader 連線
            test_url = "https://r.jina.ai/https://www.threads.com"
            response = requests.get(
                test_url, 
                headers=self.headers_markdown, 
                timeout=10
            )
            
            if response.status_code == 200:
                return {
                    "status": "healthy",
                    "service": "Jina Reader",
                    "markdown_endpoint": "available",
                    "screenshot_endpoint": "available"
                }
            else:
                return {
                    "status": "unhealthy",
                    "error": f"Jina Reader 回應異常: {response.status_code}"
                }
                
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": f"Jina Reader 健康檢查失敗: {str(e)}"
            }