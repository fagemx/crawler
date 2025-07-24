"""
共用數據模型

定義 A2A Agent 間通訊的標準數據格式
"""

import uuid
from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class TaskState(str, Enum):
    """任務狀態枚舉"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INPUT_REQUIRED = "input_required"


class ThreadsPost(BaseModel):
    """Threads 貼文模型"""
    url: str = Field(description="貼文 URL")
    views: int = Field(default=0, description="瀏覽數")
    likes: int = Field(default=0, description="愛心數")
    comments: int = Field(default=0, description="留言數")
    reposts: int = Field(default=0, description="轉發數")
    shares: int = Field(default=0, description="分享數")
    
    def calculate_score(self) -> float:
        """計算權重分數"""
        return (
            self.views * 1.0 +
            self.likes * 0.3 +
            self.comments * 0.3 +
            self.reposts * 0.1 +
            self.shares * 0.1
        )


class PostMetrics(BaseModel):
    """貼文指標數據模型 - planD.md 核心數據結構"""
    
    # 基本資訊
    url: str = Field(description="貼文完整 URL")
    post_id: str = Field(description="貼文 ID")
    username: str = Field(description="用戶名")
    
    # planD.md 要求的五大指標
    views_count: Optional[int] = Field(None, description="瀏覽數 - 主要權重")
    likes_count: Optional[int] = Field(None, description="愛心數 - 次要權重")
    comments_count: Optional[int] = Field(None, description="留言數 - 次要權重")
    reposts_count: Optional[int] = Field(None, description="轉發數")
    shares_count: Optional[int] = Field(None, description="分享數")
    
    # 內容資料（可選，供即時使用）
    content: Optional[str] = Field(None, description="貼文內容文字")
    media_urls: Optional[List[str]] = Field(None, description="媒體 URL 列表")
    created_at: Optional[datetime] = Field(None, description="貼文建立時間")
    
    # 處理元數據
    source: str = Field(default="unknown", description="數據來源: apify, jina, vision")
    processing_stage: str = Field(default="initial", description="處理階段")
    is_complete: bool = Field(default=False, description="數據是否完整")
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    
    def calculate_score(self) -> float:
        """
        計算權重分數 - 基於 planD.md 的權重策略
        views_count 最重，likes_count 與 comments_count 其次
        """
        views = self.views_count or 0
        likes = self.likes_count or 0
        comments = self.comments_count or 0
        reposts = self.reposts_count or 0
        shares = self.shares_count or 0
        
        # planD.md 權重策略
        return (
            views * 1.0 +           # 主要權重
            likes * 0.3 +           # 次要權重
            comments * 0.3 +        # 次要權重
            reposts * 0.1 +         # 較低權重
            shares * 0.1            # 較低權重
        )
    
    def missing_fields(self) -> List[str]:
        """檢查缺失的欄位"""
        missing = []
        if self.views_count is None:
            missing.append("views_count")
        if self.likes_count is None:
            missing.append("likes_count")
        if self.comments_count is None:
            missing.append("comments_count")
        if self.reposts_count is None:
            missing.append("reposts_count")
        if self.shares_count is None:
            missing.append("shares_count")
        return missing
    
    def update_completeness(self):
        """更新完整性狀態"""
        self.is_complete = len(self.missing_fields()) == 0
        self.last_updated = datetime.utcnow()


class PostMetricsBatch(BaseModel):
    """貼文指標批次處理模型"""
    posts: List[PostMetrics]
    batch_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    username: str
    total_count: int
    processing_stage: str = "initial"
    
    def get_incomplete_posts(self) -> List[PostMetrics]:
        """獲取不完整的貼文"""
        return [post for post in self.posts if not post.is_complete]
    
    def get_completion_rate(self) -> float:
        """獲取完成率"""
        if not self.posts:
            return 0.0
        complete_count = len([post for post in self.posts if post.is_complete])
        return complete_count / len(self.posts)


class AgentResponse(BaseModel):
    """標準 Agent 回應格式"""
    task_state: TaskState
    data: Optional[Dict[str, Any]] = None
    message: str = ""
    artifacts: Optional[Dict[str, Any]] = None


class LegacyAgentResponse(BaseModel):
    """舊版 Agent 回應格式（向後兼容）"""
    success: bool
    message: str
    data: Optional[PostMetricsBatch] = None
    error_code: Optional[str] = None
    processing_time: Optional[float] = None


# A2A 訊息的標準格式
class A2APostMetricsRequest(BaseModel):
    """A2A 貼文指標請求格式"""
    action: str  # "fetch_urls", "enhance_with_jina", "fill_with_vision", "rank_posts"
    username: Optional[str] = None
    max_posts: Optional[int] = 100
    posts: Optional[List[PostMetrics]] = None


class A2APostMetricsResponse(BaseModel):
    """A2A 貼文指標回應格式"""
    status: str  # "success", "error", "processing"
    posts: Optional[List[PostMetrics]] = None
    message: Optional[str] = None
    progress: Optional[float] = None