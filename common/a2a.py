"""
A2A (Agent-to-Agent) 通訊協議實現

基於標準 A2A 協議的訊息格式和通訊機制
"""

import json
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union, AsyncIterable
from dataclasses import dataclass, asdict
from pydantic import BaseModel, Field


class MessagePartKind(str, Enum):
    """訊息部分類型"""
    TEXT = "text"
    DATA = "data"
    IMAGE = "image"
    FILE = "file"
    ARTIFACT = "artifact"
    ERROR = "error"


class MessageRole(str, Enum):
    """訊息角色"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    AGENT = "agent"


class TaskState(str, Enum):
    """任務狀態"""
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    INPUT_REQUIRED = "input_required"


@dataclass
class MessagePart:
    """訊息部分"""
    kind: MessagePartKind
    content: Any
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def text(cls, content: str, metadata: Optional[Dict] = None) -> 'MessagePart':
        """創建文字訊息部分"""
        return cls(kind=MessagePartKind.TEXT, content=content, metadata=metadata)
    
    @classmethod
    def data(cls, content: Any, metadata: Optional[Dict] = None) -> 'MessagePart':
        """創建數據訊息部分"""
        return cls(kind=MessagePartKind.DATA, content=content, metadata=metadata)
    
    @classmethod
    def error(cls, content: str, error_code: Optional[str] = None) -> 'MessagePart':
        """創建錯誤訊息部分"""
        metadata = {"error_code": error_code} if error_code else None
        return cls(kind=MessagePartKind.ERROR, content=content, metadata=metadata)


@dataclass
class A2AMessage:
    """標準 A2A 訊息格式"""
    role: MessageRole
    parts: List[MessagePart]
    context_id: str
    message_id: str
    task_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        return {
            "role": self.role.value,
            "parts": [part.to_dict() for part in self.parts],
            "contextId": self.context_id,
            "messageId": self.message_id,
            "taskId": self.task_id,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'A2AMessage':
        """從字典創建訊息"""
        parts = [
            MessagePart(
                kind=MessagePartKind(part["kind"]),
                content=part["content"],
                metadata=part.get("metadata")
            )
            for part in data["parts"]
        ]
        
        timestamp = None
        if data.get("timestamp"):
            timestamp = datetime.fromisoformat(data["timestamp"].replace('Z', '+00:00'))
        
        return cls(
            role=MessageRole(data["role"]),
            parts=parts,
            context_id=data["contextId"],
            message_id=data["messageId"],
            task_id=data.get("taskId"),
            metadata=data.get("metadata"),
            timestamp=timestamp
        )
    
    @classmethod
    def create_user_message(
        cls, 
        content: str, 
        context_id: Optional[str] = None,
        task_id: Optional[str] = None
    ) -> 'A2AMessage':
        """創建用戶訊息"""
        return cls(
            role=MessageRole.USER,
            parts=[MessagePart.text(content)],
            context_id=context_id or str(uuid.uuid4()),
            message_id=str(uuid.uuid4()),
            task_id=task_id
        )
    
    @classmethod
    def create_assistant_message(
        cls,
        content: Any,
        context_id: str,
        task_id: Optional[str] = None,
        is_data: bool = False
    ) -> 'A2AMessage':
        """創建助手回應訊息"""
        part = MessagePart.data(content) if is_data else MessagePart.text(str(content))
        
        return cls(
            role=MessageRole.ASSISTANT,
            parts=[part],
            context_id=context_id,
            message_id=str(uuid.uuid4()),
            task_id=task_id
        )


class TaskStatus(BaseModel):
    """任務狀態"""
    state: TaskState
    message: Optional[str] = None
    progress: Optional[float] = Field(None, ge=0.0, le=1.0)
    metadata: Optional[Dict[str, Any]] = None


class TaskStatusUpdateEvent(BaseModel):
    """任務狀態更新事件"""
    task_id: str
    agent_id: str
    status: TaskStatus
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class StreamingResponse(BaseModel):
    """流式回應格式"""
    response_type: str = "text"  # "text" | "data" | "status" | "error"
    is_task_complete: bool = False
    require_user_input: bool = False
    content: Any
    metadata: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# 便利函數
def stream_text(content: str, final: bool = False, metadata: Optional[Dict] = None) -> Dict[str, Any]:
    """創建文字流式回應"""
    return StreamingResponse(
        response_type="text",
        is_task_complete=final,
        content=content,
        metadata=metadata
    ).model_dump()


def stream_data(content: Any, final: bool = False, metadata: Optional[Dict] = None) -> Dict[str, Any]:
    """創建數據流式回應"""
    return StreamingResponse(
        response_type="data",
        is_task_complete=final,
        content=content,
        metadata=metadata
    ).model_dump()


def stream_status(status: TaskState, message: str = "", progress: Optional[float] = None) -> Dict[str, Any]:
    """創建狀態流式回應"""
    return StreamingResponse(
        response_type="status",
        content={
            "status": status.value,
            "message": message,
            "progress": progress
        }
    ).model_dump()


def stream_error(error_message: str, error_code: Optional[str] = None, final: bool = True) -> Dict[str, Any]:
    """創建錯誤流式回應"""
    return StreamingResponse(
        response_type="error",
        is_task_complete=final,
        content={
            "error": error_message,
            "error_code": error_code
        }
    ).model_dump()


def stream_input_required(question: str, options: Optional[List[str]] = None) -> Dict[str, Any]:
    """創建需要用戶輸入的回應"""
    return StreamingResponse(
        response_type="input_required",
        require_user_input=True,
        content={
            "question": question,
            "options": options or []
        }
    ).model_dump()


class A2AClient:
    """A2A 客戶端"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
    
    async def send_message(
        self, 
        message: A2AMessage,
        stream: bool = True
    ) -> Union[Dict[str, Any], AsyncIterable[Dict[str, Any]]]:
        """發送 A2A 訊息"""
        import httpx
        
        url = f"{self.base_url}/a2a/message"
        
        async with httpx.AsyncClient() as client:
            if stream:
                return self._stream_response(client, url, message)
            else:
                response = await client.post(url, json=message.to_dict())
                response.raise_for_status()
                return response.json()
    
    async def _stream_response(
        self, 
        client: httpx.AsyncClient, 
        url: str, 
        message: A2AMessage
    ) -> AsyncIterable[Dict[str, Any]]:
        """處理流式回應"""
        async with client.stream("POST", url, json=message.to_dict()) as response:
            response.raise_for_status()
            
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])  # 移除 "data: " 前綴
                        yield data
                    except json.JSONDecodeError:
                        continue


class BaseAgent:
    """基礎 Agent 類別"""
    
    def __init__(self, agent_name: str, agent_description: str):
        self.agent_name = agent_name
        self.agent_description = agent_description
        self.agent_id = str(uuid.uuid4())
    
    async def handle_message(self, message: A2AMessage) -> AsyncIterable[Dict[str, Any]]:
        """處理 A2A 訊息 - 子類別需要實現"""
        raise NotImplementedError("Subclasses must implement handle_message")
    
    def get_agent_card(self) -> Dict[str, Any]:
        """獲取 Agent Card - 子類別需要實現"""
        raise NotImplementedError("Subclasses must implement get_agent_card")


# 錯誤類別
class A2AError(Exception):
    """A2A 協議錯誤"""
    def __init__(self, message: str, error_code: Optional[str] = None):
        super().__init__(message)
        self.error_code = error_code


class AgentNotFoundError(A2AError):
    """Agent 未找到錯誤"""
    pass


class MessageFormatError(A2AError):
    """訊息格式錯誤"""
    pass


class TaskExecutionError(A2AError):
    """任務執行錯誤"""
    pass