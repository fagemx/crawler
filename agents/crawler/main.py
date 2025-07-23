"""
Crawler Agent 主程式

基於 FastAPI + A2A 協議的社交媒體內容抓取服務
"""

import asyncio
import json
import uuid
from typing import Dict, Any, AsyncIterable
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from common.a2a import (
    A2AMessage, BaseAgent, stream_text, stream_error, 
    MessageFormatError, TaskExecutionError
)
from common.settings import get_settings
from .crawler_logic import CrawlerLogic


class CrawlerAgent(BaseAgent):
    """Crawler Agent 實現"""
    
    def __init__(self):
        super().__init__(
            agent_name="Crawler Agent",
            agent_description="專業的社交媒體內容抓取代理"
        )
        self.crawler_logic = CrawlerLogic()
        self.settings = get_settings()
    
    async def handle_message(self, message: A2AMessage) -> AsyncIterable[Dict[str, Any]]:
        """處理 A2A 訊息"""
        try:
            # 驗證訊息格式
            if not message.parts or len(message.parts) == 0:
                yield stream_error("訊息內容為空")
                return
            
            # 獲取第一個文字部分
            text_part = None
            for part in message.parts:
                if part.kind == "text":
                    text_part = part
                    break
            
            if not text_part:
                yield stream_error("未找到文字內容")
                return
            
            # 解析請求內容
            try:
                if isinstance(text_part.content, str):
                    # 嘗試解析 JSON
                    try:
                        request_data = json.loads(text_part.content)
                    except json.JSONDecodeError:
                        # 如果不是 JSON，假設是用戶名
                        request_data = {"username": text_part.content.strip()}
                else:
                    request_data = text_part.content
            except Exception as e:
                yield stream_error(f"解析請求內容失敗: {str(e)}")
                return
            
            # 提取參數（簡化版本，只需要用戶名和貼文數量）
            username = request_data.get("username", "").strip()
            max_posts = request_data.get("max_posts", 10)  # 預設 10 則
            
            if not username:
                yield stream_error("用戶名不能為空")
                return
            
            # 執行抓取任務（簡化版本，只抓取 URL）
            async for result in self.crawler_logic.fetch_threads_post_urls(
                username=username,
                max_posts=max_posts,
                task_id=message.task_id
            ):
                yield result
                
        except Exception as e:
            yield stream_error(f"處理訊息時發生錯誤: {str(e)}")
    
    def get_agent_card(self) -> Dict[str, Any]:
        """獲取 Agent Card"""
        # 從檔案載入 Agent Card
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
                "url": f"http://localhost:{self.settings.agents.crawler_agent_port}",
                "capabilities": {"streaming": True},
                "skills": [
                    {
                        "id": "fetch_threads_posts",
                        "name": "抓取 Threads 貼文",
                        "description": "抓取指定用戶的 Threads 貼文"
                    }
                ]
            }


# 全域 Agent 實例
crawler_agent = CrawlerAgent()


async def register_to_mcp():
    """註冊到 MCP Server"""
    try:
        import httpx
        
        agent_card = crawler_agent.get_agent_card()
        mcp_url = crawler_agent.settings.mcp.server_url
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{mcp_url}/agents/register",
                json=agent_card,
                timeout=10.0
            )
            
            if response.status_code == 200:
                print(f"成功註冊到 MCP Server: {mcp_url}")
            else:
                print(f"註冊到 MCP Server 失敗: {response.status_code}")
                
    except Exception as e:
        print(f"註冊到 MCP Server 時發生錯誤: {e}")


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
            crawler_agent.crawler_logic.cleanup_completed_tasks()
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"清理任務失敗: {e}")


# FastAPI 應用
app = FastAPI(
    title="Crawler Agent",
    description="社交媒體內容抓取代理",
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
    health_status = await crawler_agent.crawler_logic.health_check()
    
    return {
        "agent": "Crawler Agent",
        "status": health_status.get("status", "unknown"),
        "details": health_status
    }


@app.get("/agent-card")
async def get_agent_card():
    """獲取 Agent Card"""
    return crawler_agent.get_agent_card()


@app.post("/a2a/message")
async def handle_a2a_message(message_data: Dict[str, Any]):
    """處理 A2A 訊息"""
    try:
        # 解析 A2A 訊息
        message = A2AMessage.from_dict(message_data)
        
        # 創建流式回應
        async def event_stream():
            try:
                async for result in crawler_agent.handle_message(message):
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
    status = crawler_agent.crawler_logic.get_task_status(task_id)
    
    if status:
        return status
    else:
        raise HTTPException(status_code=404, detail="任務未找到")


@app.post("/crawl")
async def crawl_posts(
    username: str,
    max_posts: int = 10,
    background_tasks: BackgroundTasks = None
):
    """直接抓取端點（非 A2A 協議）- 簡化版本，只抓取 URL"""
    try:
        task_id = str(uuid.uuid4())
        
        async def event_stream():
            async for result in crawler_agent.crawler_logic.fetch_threads_post_urls(
                username=username,
                max_posts=max_posts,
                task_id=task_id
            ):
                yield {
                    "event": "data",
                    "data": json.dumps(result)
                }
        
        return EventSourceResponse(event_stream())
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"抓取失敗: {str(e)}")


@app.get("/")
async def root():
    """根端點"""
    return {
        "agent": "Crawler Agent",
        "version": "1.0.0",
        "description": "社交媒體內容抓取代理",
        "endpoints": {
            "health": "/health",
            "agent_card": "/agent-card",
            "a2a_message": "/a2a/message",
            "direct_crawl": "/crawl"
        }
    }


if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    
    uvicorn.run(
        "agents.crawler.main:app",
        host="0.0.0.0",
        port=settings.agents.crawler_agent_port,
        reload=settings.is_development(),
        log_level="info"
    )