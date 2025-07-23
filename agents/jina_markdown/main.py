"""
Jina Markdown Agent 主程式 - Plan E 版本

專注於單一職責：
- 使用 Jina Reader Markdown 解析貼文
- 寫入 Redis (Tier-0) 和 PostgreSQL (Tier-1)
- 標記需要 Vision 補值的貼文

基於 FastAPI + A2A 協議的 Markdown 解析服務
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
from common.models import PostMetrics
from .jina_markdown_logic import JinaMarkdownAgent


class JinaMarkdownAgentService(BaseAgent):
    """Jina Markdown Agent 服務實現 - Plan E 單一職責版本"""
    
    def __init__(self):
        super().__init__(
            agent_name="Jina Markdown Agent",
            agent_description="專業的 Markdown 解析代理，提取社交媒體指標並寫入雙重存儲"
        )
        self.jina_logic = JinaMarkdownAgent()
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
            
            # 提取 PostMetrics 列表
            if "batch" in request_data:
                # 來自 Orchestrator 的批次格式
                batch_data = request_data["batch"]
                posts_data = batch_data.get("posts", [])
            elif "posts" in request_data:
                # 直接的貼文列表
                posts_data = request_data["posts"]
            else:
                yield stream_error("未找到貼文數據")
                return
            
            # 轉換為 PostMetrics 對象
            try:
                posts = [PostMetrics(**post_data) for post_data in posts_data]
            except Exception as e:
                yield stream_error(f"轉換 PostMetrics 失敗: {str(e)}")
                return
            
            if not posts:
                yield stream_error("貼文列表為空")
                return
            
            # 執行 Jina Markdown 處理任務
            async for result in self.jina_logic.batch_process_posts_with_storage(
                posts=posts,
                task_id=message.task_id
            ):
                yield result
                
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
                "url": f"http://localhost:{self.settings.agents.jina_agent_port}",
                "capabilities": {"streaming": True},
                "skills": [
                    {
                        "id": "extract_markdown_metrics",
                        "name": "Markdown 指標提取",
                        "description": "使用 Jina Reader 提取社交媒體貼文的指標和內容"
                    },
                    {
                        "id": "dual_storage_write",
                        "name": "雙重存儲寫入",
                        "description": "同時寫入 Redis 快取和 PostgreSQL 長期存儲"
                    },
                    {
                        "id": "vision_queue_management",
                        "name": "Vision 佇列管理",
                        "description": "標記和管理需要 Vision 補值的貼文"
                    }
                ]
            }


# 全域 Agent 實例
jina_markdown_agent = JinaMarkdownAgentService()


async def register_to_mcp():
    """註冊到 MCP Server"""
    try:
        import httpx
        
        agent_card = jina_markdown_agent.get_agent_card()
        mcp_url = jina_markdown_agent.settings.mcp.server_url
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{mcp_url}/agents/register",
                json=agent_card,
                timeout=10.0
            )
            
            if response.status_code == 200:
                print(f"Jina Markdown Agent 成功註冊到 MCP Server: {mcp_url}")
            else:
                print(f"Jina Markdown Agent 註冊到 MCP Server 失敗: {response.status_code}")
                
    except Exception as e:
        print(f"Jina Markdown Agent 註冊到 MCP Server 時發生錯誤: {e}")


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
            jina_markdown_agent.jina_logic.cleanup_completed_tasks()
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Jina Markdown Agent 清理任務失敗: {e}")


# FastAPI 應用
app = FastAPI(
    title="Jina Markdown Agent",
    description="Markdown 解析代理 - 提取社交媒體指標並寫入雙重存儲",
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
    health_status = await jina_markdown_agent.jina_logic.health_check()
    
    return {
        "agent": "Jina Markdown Agent",
        "status": health_status.get("status", "unknown"),
        "details": health_status
    }


@app.get("/agent-card")
async def get_agent_card():
    """獲取 Agent Card"""
    return jina_markdown_agent.get_agent_card()


@app.post("/a2a/message")
async def handle_a2a_message(message_data: Dict[str, Any]):
    """處理 A2A 訊息"""
    try:
        # 解析 A2A 訊息
        message = A2AMessage.from_dict(message_data)
        
        # 創建流式回應
        async def event_stream():
            try:
                async for result in jina_markdown_agent.handle_message(message):
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
    status = jina_markdown_agent.jina_logic.get_task_status(task_id)
    
    if status:
        return status
    else:
        raise HTTPException(status_code=404, detail="任務未找到")


@app.post("/process-posts")
async def process_posts(
    posts_data: Dict[str, Any],
    background_tasks: BackgroundTasks = None
):
    """直接處理端點（非 A2A 協議）"""
    try:
        posts = [PostMetrics(**post) for post in posts_data.get("posts", [])]
        task_id = str(uuid.uuid4())
        
        async def event_stream():
            async for result in jina_markdown_agent.jina_logic.batch_process_posts_with_storage(
                posts=posts,
                task_id=task_id
            ):
                yield {
                    "event": "data",
                    "data": json.dumps(result)
                }
        
        return EventSourceResponse(event_stream())
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"處理失敗: {str(e)}")


@app.get("/queue/vision-fill/status")
async def get_vision_queue_status():
    """獲取 Vision 佇列狀態"""
    try:
        from common.redis_client import get_redis_client
        redis_client = get_redis_client()
        
        length = redis_client.get_queue_length("vision_fill")
        
        return {
            "queue_name": "vision_fill",
            "length": length,
            "status": "active" if length > 0 else "empty"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"獲取佇列狀態失敗: {str(e)}")


@app.get("/")
async def root():
    """根端點"""
    return {
        "agent": "Jina Markdown Agent",
        "version": "1.0.0",
        "description": "Markdown 解析代理 - 提取社交媒體指標並寫入雙重存儲",
        "plan_e_role": "第一階段處理：Markdown 解析 → 雙重存儲 → Vision 佇列",
        "endpoints": {
            "health": "/health",
            "agent_card": "/agent-card",
            "a2a_message": "/a2a/message",
            "process_posts": "/process-posts",
            "vision_queue_status": "/queue/vision-fill/status"
        }
    }


if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    
    uvicorn.run(
        "agents.jina_markdown.main:app",
        host="0.0.0.0",
        port=settings.agents.jina_agent_port,  # 使用現有的端口配置
        reload=settings.is_development(),
        log_level="info"
    )