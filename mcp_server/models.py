"""
MCP Server 資料模型 - 採用 SQLModel 簡化設計
"""

from __future__ import annotations
from datetime import datetime
from typing import Dict, Any, List, Optional

from sqlmodel import Field, SQLModel, Column, Session, select
from sqlalchemy.types import JSON
from sqlalchemy import Text

# ============================================================================
# Agent 模型 - 簡化但提供關聯輔助方法
# ============================================================================
class Agent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    role: str = Field(index=True)
    url: str
    version: str
    status: str = "OFFLINE" # ONLINE, OFFLINE, ERROR
    capabilities: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    agent_metadata: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_heartbeat: datetime = Field(default_factory=datetime.utcnow)
    
    # 輔助方法提供關聯功能
    def get_operations(self, session: Session) -> List["OperationLog"]:
        """獲取此 Agent 的所有操作記錄"""
        return session.exec(
            select(OperationLog).where(OperationLog.agent_id == self.id)
        ).all()


# ============================================================================
# OperationLog 模型 - 簡化但提供關聯輔助方法
# ============================================================================
class OperationLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    operation_type: str
    operation_name: str
    actor_name: str
    status: str
    details: Optional[str] = None
    execution_time_ms: Optional[int] = None
    request_data: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    response_data: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    agent_id: Optional[int] = Field(default=None, foreign_key="agent.id")
    
    # 輔助方法提供關聯功能
    def get_agent(self, session: Session) -> Optional["Agent"]:
        """獲取此操作記錄關聯的 Agent"""
        if not self.agent_id:
            return None
        return session.get(Agent, self.agent_id)


class OpsLog(SQLModel, table=True):
    """操作日誌 - 簡化但保留關鍵資訊"""
    __tablename__ = "system_operation_log"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    ts: datetime = Field(default_factory=datetime.utcnow, index=True)
    agent: Optional[str] = Field(default=None, index=True)
    operation_type: str = Field(index=True)  # register/heartbeat/media_download
    operation_name: str
    level: str = Field(default="INFO")  # INFO/WARN/ERROR
    message: str
    status: str = Field(default="success")  # success/failed/pending
    execution_time_ms: Optional[int] = None
    extra: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class ErrorLog(SQLModel, table=True):
    """錯誤日誌 - 保留詳細追蹤"""
    __tablename__ = "system_error_log"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    ts: datetime = Field(default_factory=datetime.utcnow, index=True)
    agent: Optional[str] = Field(default=None, index=True)
    error_type: str = Field(index=True)  # agent_error/media_error/database_error
    error_code: Optional[str] = None
    error_message: str
    traceback: Optional[str] = Field(default=None, sa_column=Column(Text))
    severity: str = Field(default="error")  # debug/info/warning/error/critical
    req_id: Optional[str] = None
    resolved_at: Optional[datetime] = None


# 保留媒體管理 - 這是我們的獨特需求
class MediaFile(SQLModel, table=True):
    """媒體檔案管理 - 保留 RustFS 整合"""
    __tablename__ = "media_files"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    post_url: str = Field(index=True)
    original_url: str
    media_type: str  # image/video/audio
    rustfs_key: Optional[str] = Field(default=None, unique=True)
    rustfs_url: Optional[str] = None
    file_size: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    download_status: str = Field(default="pending")  # pending/downloading/completed/failed
    download_error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    downloaded_at: Optional[datetime] = None
    media_metadata: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


# 保留現有的 posts 和 post_metrics 相容性
class Post(SQLModel, table=True):
    """貼文表 - 保持與現有系統相容"""
    __tablename__ = "posts"
    
    url: str = Field(primary_key=True)
    author: Optional[str] = None
    markdown: Optional[str] = Field(default=None, sa_column=Column(Text))
    media_urls: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    last_seen: datetime = Field(default_factory=datetime.utcnow)


class PostMetrics(SQLModel, table=True):
    """貼文指標表 - 保持與現有系統相容"""
    __tablename__ = "post_metrics"
    
    url: str = Field(primary_key=True, foreign_key="posts.url")
    views: int = Field(default=0)
    likes: int = Field(default=0)
    comments: int = Field(default=0)
    reposts: int = Field(default=0)
    shares: int = Field(default=0)
    # score 會由資料庫自動計算
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# Pydantic 模型用於 API
class AgentRegister(SQLModel):
    """Agent 註冊請求"""
    name: str
    role: str
    url: str
    version: str = "1.0.0"
    capabilities: Dict[str, Any] = Field(default_factory=dict)
    agent_metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentResponse(SQLModel):
    """Agent 回應"""
    name: str
    role: str
    url: str
    status: str
    last_heartbeat: datetime
    version: str
    capabilities: Dict[str, Any]


class MediaDownloadRequest(SQLModel):
    """媒體下載請求"""
    post_url: str
    media_urls: list[str]
    max_concurrent: int = Field(default=3, ge=1, le=10)


class SystemStats(SQLModel):
    """系統統計"""
    agents: Dict[str, Any]
    database: Dict[str, Any]
    timestamp: float