"""
共用數據模型

定義 A2A Agent 間通訊的標準數據格式
"""

import uuid
from enum import Enum
from pydantic import BaseModel, Field, validator
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
    """單一貼文的指標數據模型"""
    post_id: str = Field(..., description="貼文的唯一ID")
    username: str = Field(..., description="作者的使用者名稱")
    url: str = Field(..., description="貼文的URL")
    content: Optional[str] = None
    likes_count: Optional[int] = None
    comments_count: Optional[int] = None
    reposts_count: Optional[int] = None
    shares_count: Optional[int] = None
    views_count: Optional[int] = Field(None, description="瀏覽數 (從前端畫面讀取)")
    media_urls: Optional[List[str]] = Field(default_factory=list, description="舊版媒體URL欄位(已棄用)")
    images: List[str] = Field(default_factory=list, description="圖片URL列表")
    videos: List[str] = Field(default_factory=list, description="影片URL列表")
    created_at: datetime = Field(..., description="貼文發布時間")  # 注意：實際為爬蟲處理時間
    post_published_at: Optional[datetime] = Field(None, description="貼文真實發布時間 (從DOM提取)")
    tags: List[str] = Field(default_factory=list, description="主題標籤列表 (從標籤連結提取)")
    fetched_at: datetime = Field(default_factory=datetime.utcnow, description="資料抓取時間")
    views_fetched_at: Optional[datetime] = Field(None, description="瀏覽數抓取時間")

    @validator('created_at', pre=True, allow_reuse=True)
    def parse_created_at(cls, v):
        if isinstance(v, str):
            return datetime.fromisoformat(v)
        return v
    
    @validator('post_published_at', pre=True, allow_reuse=True)
    def parse_post_published_at(cls, v):
        if isinstance(v, str):
            return datetime.fromisoformat(v)
        return v
    
    @validator('reader_processed_at', pre=True, allow_reuse=True)
    def parse_reader_processed_at(cls, v):
        if isinstance(v, str):
            return datetime.fromisoformat(v)
        return v
    
    @validator('dom_processed_at', pre=True, allow_reuse=True)  
    def parse_dom_processed_at(cls, v):
        if isinstance(v, str):
            return datetime.fromisoformat(v)
        return v
    
    # 處理元數據
    source: str = Field(default="unknown", description="數據來源: apify, jina, vision")
    processing_stage: str = Field(default="initial", description="處理階段")
    is_complete: bool = Field(default=False, description="數據是否完整")
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    
    # 雙軌處理狀態追蹤
    reader_status: str = Field(default="pending", description="Reader處理狀態: pending/success/failed")
    dom_status: str = Field(default="pending", description="DOM爬取狀態: pending/success/failed")
    reader_processed_at: Optional[datetime] = Field(None, description="Reader處理完成時間")
    dom_processed_at: Optional[datetime] = Field(None, description="DOM處理完成時間")
    
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
    
    def merge_from(self, other: "PostMetrics"):
        """
        從另一個 PostMetrics 物件合併數據，避免覆蓋已有的有效數據
        """
        for field in (
            "likes_count", "comments_count",
            "reposts_count", "shares_count",
            "views_count", "content",
            "images", "videos", "tags",
        ):
            src = getattr(other, field, None)
            dst = getattr(self, field, None)
            
            # 文字 / List → 只要對方有內容且目標為空
            if isinstance(src, (str, list)) and src and not dst:
                setattr(self, field, src)
            # 數字 → 優先使用非零值，如果都非零則使用較大值
            elif isinstance(src, (int, float)) and src is not None:
                if dst is None or dst == 0:
                    # 目標為 None 或 0，直接使用來源值
                    setattr(self, field, src)
                elif src > 0 and src > dst:
                    # 來源值更大且 > 0，使用來源值
                    setattr(self, field, src)
        
        # 特殊處理：post_published_at (datetime 欄位)
        if other.post_published_at and not self.post_published_at:
            self.post_published_at = other.post_published_at
        
        # 特殊處理：雙軌狀態欄位 (只有在對方成功且自己未成功時才更新)
        if other.reader_status == "success" and self.reader_status != "success":
            self.reader_status = other.reader_status
            self.reader_processed_at = other.reader_processed_at or datetime.utcnow()
        
        if other.dom_status == "success" and self.dom_status != "success":
            self.dom_status = other.dom_status
            self.dom_processed_at = other.dom_processed_at or datetime.utcnow()
        
        # 更新處理階段和時間
        if other.processing_stage and other.processing_stage != "initial":
            self.processing_stage = other.processing_stage
        self.last_updated = datetime.utcnow()
    
    # 雙軌狀態輔助方法
    def is_reader_complete(self) -> bool:
        """檢查Reader處理是否完成"""
        return self.reader_status == "success" and bool(self.content)
    
    def is_dom_complete(self) -> bool:
        """檢查DOM爬取是否完成"""
        return self.dom_status == "success" and self.is_complete
        
    def needs_processing(self) -> dict:
        """分析需要的處理類型"""
        return {
            "needs_reader": not self.is_reader_complete(),
            "needs_dom": not self.is_dom_complete(),
            "has_content": bool(self.content),
            "has_metrics": any([self.likes_count, self.views_count, self.comments_count])
        }
    
    def get_status_summary(self) -> dict:
        """獲取狀態摘要，用於UI顯示"""
        return {
            "reader_status": self.reader_status,
            "dom_status": self.dom_status,
            "reader_processed_at": self.reader_processed_at,
            "dom_processed_at": self.dom_processed_at,
            **self.needs_processing()
        }


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


class CrawlState(BaseModel):
    """爬取狀態模型 - 用於增量爬取優化"""
    username: str = Field(..., description="用戶名（主鍵）")
    latest_post_id: Optional[str] = Field(None, description="最新抓取的貼文ID（優化查詢）")
    total_crawled: int = Field(default=0, description="總抓取數量")
    last_crawl_at: Optional[datetime] = Field(None, description="最後抓取時間")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="記錄創建時間")