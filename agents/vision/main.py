"""
Vision Fill Agent 主程式 - Plan E 版本

專注於單一職責：補完 Jina Markdown Agent 無法提取的指標
基於 FastAPI + A2A 協議的 Vision 補值服務
"""

import asyncio
import json
import uuid
from typing import Dict, Any, AsyncIterable
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from common.a2a import (
    A2AMessage, BaseAgent, stream_text, stream_error, 
    MessageFormatError, TaskExecutionError
)
from common.settings import get_settings
from .vision_fill_logic import VisionFillAgent


class VisionFillAgentService(BaseAgent):
    """Vision Fill Agent 服務實現 - Plan E 單一職責版本"""
    
    def __init__(self):
        super().__init__(
            agent_name="Vision Fill Agent",
            agent_description="專業的視覺補值代理，補完缺失的社交媒體指標"
        )
        self.vision_logic = VisionFillAgent()
        self.settings = get_settings()
    
    async def handle_message(self, message: A2AMessage) -> AsyncIterable[Dict[str, Any]]:
        """處理 A2A 訊息"""
        try:
            # 驗證訊息格式
            if not message.parts or len(message.parts) == 0:
                yield stream_error("訊息內容為空")
                return
            
            # 獲取數據部分
            data_part = None
            for part in message.parts:
                if part.kind == "data":
                    data_part = part
                    break
                elif part.kind == "text":
                    try:
                        data_part = part
                        break
                    except:
                        continue
            
            if not data_part:
                yield stream_error("未找到有效的數據內容")
                return
            
            # 解析請求數據
            try:
                if isinstance(data_part.content, str):
                    request_data = json.loads(data_part.content)
                else:
                    request_data = data_part.content
            except Exception as e:
                yield stream_error(f"解析請求數據失敗: {str(e)}")
                return
            
            # 處理不同類型的請求
            action = request_data.get("action", "fill_missing")
            
            if action == "fill_missing":
                # 補值缺失指標
                urls = request_data.get("urls", [])
                if not urls:
                    yield stream_error("未提供需要補值的 URL")
                    return
                
                async for result in self.vision_logic.batch_fill_missing_metrics(
                    urls=urls,
                    task_id=message.task_id
                ):
                    yield result
                    
            elif action == "process_queue":
                # 處理 Redis 佇列中的項目
                queue_name = request_data.get("queue_name", "vision_fill")
                batch_size = request_data.get("batch_size", 10)
                
                async for result in self.vision_logic.process_vision_queue(
                    queue_name=queue_name,
                    batch_size=batch_size,
                    task_id=message.task_id
                ):
                    yield result
                    
            else:
                yield stream_error(f"不支援的操作: {action}")
                
        except Exception as e:
            yield stream_error(f"處理訊息時發生錯誤: {str(e)}")
    
    def get_agent_card(self) -> Dict[str, Any]:
        """獲取 Agent Card"""
        import os
        card_path = os.path.join(os.path.dirname(__file__), "agent_card.json")
        
        try:
            with open(card_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            # 如果檔案不存在，返回基本資訊
            return {
                "name": self.agent_name,
                "description": self.agent_description,
                "version": "1.0.0",
                "url": f"http://localhost:{self.settings.agents.vision_agent_port}",
                "capabilities": {"streaming": True},
                "skills": [
                    {
                        "id": "fill_missing_metrics",
                        "name": "補值缺失指標",
                        "description": "使用 Jina Screenshot + Gemini Vision 補完缺失的社交媒體指標"
                    },
                    {
                        "id": "process_vision_queue",
                        "name": "處理視覺佇列",
                        "description": "批次處理 Redis 佇列中需要視覺分析的項目"
                    }
                ]
            }


# 全域 Agent 實例
vision_fill_agent = VisionFillAgentService()


async def register_to_mcp():
    """註冊到 MCP Server"""
    try:
        import httpx
        
        agent_card = vision_fill_agent.get_agent_card()
        mcp_url = vision_fill_agent.settings.mcp.server_url
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{mcp_url}/agents/register",
                json=agent_card,
                timeout=10.0
            )
            
            if response.status_code == 200:
                print(f"Vision Fill Agent 成功註冊到 MCP Server: {mcp_url}")
            else:
                print(f"Vision Fill Agent 註冊到 MCP Server 失敗: {response.status_code}")
                
    except Exception as e:
        print(f"Vision Fill Agent 註冊到 MCP Server 時發生錯誤: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用生命週期管理"""
    # 啟動時註冊到 MCP Server
    await register_to_mcp()
    
    # 啟動清理任務
    cleanup_task = asyncio.create_task(periodic_cleanup())
    
    yield
    
    # 關閉時清理
    cleanup_task.cancel()


async def periodic_cleanup():
    """定期清理已完成的任務"""
    while True:
        try:
            await asyncio.sleep(3600)  # 每小時清理一次
            vision_fill_agent.vision_logic.cleanup_completed_tasks()
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Vision Fill Agent 清理任務失敗: {e}")


# FastAPI 應用
app = FastAPI(
    title="Vision Fill Agent",
    description="視覺補值代理 - 補完缺失的社交媒體指標",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 中介軟體
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """健康檢查端點"""
    health_status = await vision_fill_agent.vision_logic.health_check()
    
    return {
        "agent": "Vision Fill Agent",
        "status": health_status.get("status", "unknown"),
        "details": health_status
    }


@app.get("/agent-card")
async def get_agent_card():
    """獲取 Agent Card"""
    return vision_fill_agent.get_agent_card()


@app.post("/a2a/message")
async def handle_a2a_message(message_data: Dict[str, Any]):
    """處理 A2A 訊息"""
    try:
        # 解析 A2A 訊息
        message = A2AMessage.from_dict(message_data)
        
        # 創建流式回應
        async def event_stream():
            try:
                async for result in vision_fill_agent.handle_message(message):
                    yield {
                        "event": "data",
                        "data": json.dumps(result)
                    }
            except Exception as e:
                yield {
                    "event": "error", 
                    "data": json.dumps({"error": str(e)})
                }
        
        return EventSourceResponse(event_stream())
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"處理訊息失敗: {str(e)}")


@app.get("/tasks/{task_id}/status")
async def get_task_status(task_id: str):
    """獲取任務狀態"""
    status = vision_fill_agent.vision_logic.get_task_status(task_id)
    
    if status:
        return status
    else:
        raise HTTPException(status_code=404, detail="任務未找到")


@app.post("/fill-missing")
async def fill_missing_metrics(
    urls: list[str],
    background_tasks: BackgroundTasks = None
):
    """直接補值端點（非 A2A 協議）"""
    try:
        task_id = str(uuid.uuid4())
        
        async def event_stream():
            async for result in vision_fill_agent.vision_logic.batch_fill_missing_metrics(
                urls=urls,
                task_id=task_id
            ):
                yield {
                    "event": "data",
                    "data": json.dumps(result)
                }
        
        return EventSourceResponse(event_stream())
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"補值失敗: {str(e)}")


@app.post("/process-queue")
async def process_vision_queue(
    queue_name: str = "vision_fill",
    batch_size: int = 10
):
    """處理視覺佇列端點"""
    try:
        task_id = str(uuid.uuid4())
        
        async def event_stream():
            async for result in vision_fill_agent.vision_logic.process_vision_queue(
                queue_name=queue_name,
                batch_size=batch_size,
                task_id=task_id
            ):
                yield {
                    "event": "data",
                    "data": json.dumps(result)
                }
        
        return EventSourceResponse(event_stream())
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"處理佇列失敗: {str(e)}")


@app.get("/queue/{queue_name}/status")
async def get_queue_status(queue_name: str):
    """獲取佇列狀態"""
    try:
        from common.redis_client import get_redis_client
        redis_client = get_redis_client()
        
        length = redis_client.get_queue_length(queue_name)
        
        return {
            "queue_name": queue_name,
            "length": length,
            "status": "active" if length > 0 else "empty"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"獲取佇列狀態失敗: {str(e)}")


@app.get("/")
async def root():
    """根端點"""
    return {
        "agent": "Vision Fill Agent",
        "version": "1.0.0",
        "description": "視覺補值代理 - 補完缺失的社交媒體指標",
        "endpoints": {
            "health": "/health",
            "agent_card": "/agent-card",
            "a2a_message": "/a2a/message",
            "fill_missing": "/fill-missing",
            "process_queue": "/process-queue",
            "queue_status": "/queue/{queue_name}/status"
        }
    }


if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    
    uvicorn.run(
        "agents.vision.main:app",
        host="0.0.0.0",
        port=settings.agents.vision_agent_port,
        reload=settings.is_development(),
        log_level="info"
    )