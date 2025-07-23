"""
Jina Agent 核心邏輯

使用 Jina Reader 的 markdown 和 screenshot 功能來提取 Threads 貼文數據
採用兩階段處理：
1. 先用 markdown 解析基本數據
2. 如果數據不完整，標記為需要 Vision Agent 處理
"""

import re
import requests
from typing import Dict, Any, Optional, List
from datetime import datetime

from common.models import ThreadsPost, TaskState, AgentResponse
from agents.vision.screenshot_utils import JinaScreenshotCapture


class JinaAgent:
    """Jina Agent - 使用 Jina Reader 提取貼文數據"""
    
    def __init__(self):
        """初始化 Jina Agent"""
        self.screenshot_capture = JinaScreenshotCapture()
        
        # Jina API 設定
        self.base_url = "https://r.jina.ai/{url}"
        self.headers_markdown = {"x-respond-with": "markdown"}
        
        # 正則表達式模式
        self.metrics_pattern = re.compile(
            r'\*\*?Thread.*? (?P<views>[\d\.KM,]+) views.*?'
            r'愛心.*? (?P<likes>[\d\.KM,]*) .*?'
            r'留言.*? (?P<comments>[\d\.KM,]*) .*?'
            r'轉發.*? (?P<reposts>[\d\.KM,]*) .*?'
            r'分享.*? (?P<shares>[\d\.KM,]*)', 
            re.S
        )
    
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
    
    def process_single_post(self, post_url: str) -> AgentResponse:
        """
        處理單一貼文（僅 Markdown 解析）
        
        Args:
            post_url: 貼文 URL
            
        Returns:
            AgentResponse，如果數據不完整會標記為 input_required
        """
        try:
            # 取得 Markdown 指標
            metrics = self.get_markdown_metrics(post_url)
            
            # 檢查是否需要 Vision 補值
            required_keys = ["likes", "comments", "reposts", "shares"]
            needs_vision = any(metrics.get(k) is None for k in required_keys)
            
            if needs_vision:
                # 數據不完整，需要 Vision Agent 處理
                return AgentResponse(
                    task_state=TaskState.INPUT_REQUIRED,
                    data=None,
                    message=f"貼文數據不完整，需要 Vision 分析: {post_url}",
                    artifacts={
                        "post_url": post_url,
                        "partial_metrics": metrics,
                        "missing_fields": [k for k in required_keys if metrics.get(k) is None]
                    }
                )
            else:
                # 數據完整，創建 ThreadsPost
                post = ThreadsPost(
                    url=post_url,
                    views=metrics.get("views", 0),
                    likes=metrics.get("likes", 0),
                    comments=metrics.get("comments", 0),
                    reposts=metrics.get("reposts", 0),
                    shares=metrics.get("shares", 0)
                )
                
                return AgentResponse(
                    task_state=TaskState.COMPLETED,
                    data=post.dict(),
                    message=f"成功解析貼文數據: {post_url}",
                    artifacts={
                        "metrics": metrics,
                        "processing_method": "jina_markdown_only"
                    }
                )
                
        except Exception as e:
            return AgentResponse(
                task_state=TaskState.FAILED,
                data=None,
                message=f"Jina 處理失敗: {str(e)}",
                artifacts={
                    "post_url": post_url,
                    "error": str(e)
                }
            )
    
    def batch_process_posts(self, post_urls: List[str]) -> List[AgentResponse]:
        """
        批次處理多個貼文
        
        Args:
            post_urls: 貼文 URL 列表
            
        Returns:
            AgentResponse 列表
        """
        results = []
        
        for post_url in post_urls:
            try:
                result = self.process_single_post(post_url)
                results.append(result)
                
            except Exception as e:
                results.append(AgentResponse(
                    task_state=TaskState.FAILED,
                    data=None,
                    message=f"批次處理失敗: {str(e)}",
                    artifacts={
                        "post_url": post_url,
                        "error": str(e)
                    }
                ))
        
        return results
    
    def health_check(self) -> Dict[str, Any]:
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
                    "service": "Jina Agent",
                    "jina_reader": "available"
                }
            else:
                return {
                    "status": "unhealthy",
                    "error": f"Jina Reader 回應異常: {response.status_code}"
                }
                
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": f"Jina Agent 健康檢查失敗: {str(e)}"
            }


# 便利函數
def create_jina_agent() -> JinaAgent:
    """創建 Jina Agent 實例"""
    return JinaAgent()


def process_post_with_jina(post_url: str) -> AgentResponse:
    """處理單一貼文的便利函數"""
    agent = create_jina_agent()
    return agent.process_single_post(post_url)


def batch_process_with_jina(post_urls: List[str]) -> List[AgentResponse]:
    """批次處理貼文的便利函數"""
    agent = create_jina_agent()
    return agent.batch_process_posts(post_urls)


# 整合的 Jina + Vision 處理函數
def get_complete_post_metrics_integrated(post_url: str, gemini_api_key: str) -> AgentResponse:
    """
    整合的貼文處理函數（Jina Markdown + Vision 補值）
    
    Args:
        post_url: 貼文 URL
        gemini_api_key: Gemini API 金鑰
        
    Returns:
        AgentResponse 包含完整的指標數據
    """
    try:
        # 使用 JinaScreenshotCapture 的整合方法
        capture = JinaScreenshotCapture()
        complete_metrics = capture.get_complete_metrics(post_url, gemini_api_key)
        
        # 創建 ThreadsPost 物件
        post = ThreadsPost(
            url=post_url,
            views=complete_metrics.get("views", 0),
            likes=complete_metrics.get("likes", 0),
            comments=complete_metrics.get("comments", 0),
            reposts=complete_metrics.get("reposts", 0),
            shares=complete_metrics.get("shares", 0)
        )
        
        return AgentResponse(
            task_state=TaskState.COMPLETED,
            data=post.dict(),
            message=f"成功處理貼文（整合模式）: {post_url}",
            artifacts={
                "metrics": complete_metrics,
                "processing_method": "jina_integrated_vision"
            }
        )
        
    except Exception as e:
        return AgentResponse(
            task_state=TaskState.FAILED,
            data=None,
            message=f"整合處理失敗: {str(e)}",
            artifacts={
                "post_url": post_url,
                "error": str(e)
            }
        )