"""
Jina Agent 主程式

基於 FastAPI + A2A 協議的 Jina 數據增強服務
完全符合現有的 A2A 架構模式
"""

import asyncio
import json
import logging
import uuid
from typing import Dict, Any, AsyncIterable
from contextlib import asynccontextmanager

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from starlette.responses import StreamingResponse

from common.a2a import (
    A2AMessage, BaseAgent, stream_text, stream_error, 
    MessageFormatError, TaskExecutionError
)
from common.settings import get_settings
from common.models import PostMetrics, PostMetricsBatch, TaskState, A2APostMetricsRequest
from .jina_logic import JinaMarkdownAgent


class JinaAgent(BaseAgent):
    """Jina Agent 實現 - 完全符合現有 A2A 架構"""
    
    def __init__(self):
        super().__init__(
            agent_name="Jina增強代理",
            agent_description="使用 Jina AI 增強貼文數據，特別是 views 數據"
        )
        self.settings = get_settings()
    
    async def handle_message(self, message: A2AMessage) -> AsyncIterable[Dict[str, Any]]:
        """處理 A2A 訊息 - 與 Crawler Agent 相同的模式"""
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
                    # 嘗試解析 JSON
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
            
            # 執行 Jina 增強任務  
            async for result in jina_agent.enhance_posts_with_jina(
                posts=posts,
                task_id=message.task_id
            ):
                yield result
                
        except Exception as e:
            yield stream_error(f"處理訊息時發生錯誤: {str(e)}")
    
    def get_agent_card(self) -> Dict[str, Any]:
        """獲取 Agent Card - 與現有架構一致"""
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
                        "id": "enhance_with_jina",
                        "name": "Jina 數據增強",
                        "description": "使用 Jina AI 增強貼文的 views 和互動數據"
                    }
                ]
            }


# 全域 Agent 實例
jina_agent = JinaMarkdownAgent()


async def register_to_mcp():
    """註冊到 MCP Server - 與現有架構一致"""
    try:
        import httpx
        
        agent_card = jina_agent.get_agent_card()
        mcp_url = jina_agent.settings.mcp.server_url
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{mcp_url}/agents/register",
                json=agent_card,
                timeout=10.0
            )
            
            if response.status_code == 200:
                print(f"Jina Agent 成功註冊到 MCP Server: {mcp_url}")
            else:
                print(f"Jina Agent 註冊到 MCP Server 失敗: {response.status_code}")
                
    except Exception as e:
        print(f"Jina Agent 註冊到 MCP Server 時發生錯誤: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用生命週期管理 - 與現有架構一致"""
    # 啟動時註冊到 MCP Server
    await register_to_mcp()
    
    # 啟動清理任務
    cleanup_task = asyncio.create_task(periodic_cleanup())
    
    yield
    
    # 關閉時清理
    cleanup_task.cancel()


async def periodic_cleanup():
    """定期清理已完成的任務 - 與現有架構一致"""
    while True:
        try:
            await asyncio.sleep(3600)  # 每小時清理一次
            jina_agent.cleanup_completed_tasks()
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Jina Agent 清理任務失敗: {e}")


# FastAPI 應用 - 與現有架構完全一致
app = FastAPI(
    title="Jina Agent",
    description="Jina 數據增強代理",
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
    """健康檢查端點 - 與現有架構一致"""
    health_status = jina_agent.health_check()
    
    return {
        "agent": "Jina Agent",
        "status": health_status.get("status", "unknown"),
        "details": health_status
    }


@app.get("/agent-card")
async def get_agent_card():
    """獲取 Agent Card - 與現有架構一致"""
    return jina_agent.get_agent_card()


@app.post("/a2a/message")
async def handle_a2a_message(message_data: Dict[str, Any]):
    """處理 A2A 訊息 - 與現有架構完全一致"""
    try:
        # 解析 A2A 訊息
        message = A2AMessage.from_dict(message_data)
        
        # 創建流式回應
        async def event_stream():
            try:
                async for result in jina_agent.handle_message(message):
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


@app.post("/v1/jina/enrich", response_model=PostMetricsBatch, tags=["Plan F"])
async def enrich_metrics_batch(batch: PostMetricsBatch):
    """
    Plan F - 資料豐富化端點
    接收一個 PostMetricsBatch，使用 Jina Reader 填補缺失的指標，並返回更新後的 Batch。
    """
    try:
        logging.info(f"📥 [端點] 收到豐富化請求：{len(batch.posts)} 個貼文")
        logging.info(f"📥 [端點] Batch ID: {batch.batch_id}, Username: {batch.username}")
        
        # 使用 agent 的新方法來處理
        enriched_batch = await jina_agent.enrich_batch(batch)
        
        logging.info(f"📤 [端點] 豐富化完成，返回 {len(enriched_batch.posts)} 個貼文")
        return enriched_batch
    except Exception as e:
        logging.error(f"❌ [端點] Jina enrich 處理失敗: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Jina enrich 處理失敗: {str(e)}")


@app.post("/v1/jina/process_and_store", response_model=Dict[str, Any], tags=["Plan E - Legacy"])
async def process_and_store_posts(request: A2APostMetricsRequest):
    """
    Plan E (舊版) - 處理貼文 URL 並寫入儲存層
    """
    task_id = str(uuid.uuid4())
    
    # 從 request 中提取 posts
    posts_to_process = request.posts
    if not posts_to_process:
        raise HTTPException(status_code=400, detail="請求中缺少貼文數據")
        
    async def event_generator():
        # 啟動背景任務
        try:
            async for event in jina_agent.batch_process_posts_with_storage(posts_to_process, task_id):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            error_event = stream_error(f"背景任務啟動失敗: {str(e)}")
            yield f"data: {json.dumps(error_event)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/v1/jina/tasks/{task_id}", response_model=Dict[str, Any], tags=["Plan E - Legacy"])
def get_task_status(task_id: str):
    """獲取 Plan E 任務的狀態"""
    status = jina_agent.get_task_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="找不到任務")
    return status


@app.get("/")
async def root():
    """根端點 - 與現有架構一致"""
    return {
        "agent": "Jina Agent",
        "version": "1.0.0",
        "description": "Jina 數據增強代理",
        "endpoints": {
            "health": "/health",
            "agent_card": "/agent-card",
            "a2a_message": "/a2a/message",
            "direct_enhance": "/enhance"
        }
    }
if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    
    uvicorn.run(
        "agents.jina.main:app",
        host="0.0.0.0",
        port=settings.agents.jina_agent_port,
        reload=settings.is_development(),
        log_level="info"
    )

