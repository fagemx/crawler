import uuid
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
import json
import datetime
from pathlib import Path
import logging

from .playwright_logic import PlaywrightLogic
from common.models import PostMetricsBatch
from common.a2a import stream_error, TaskState
from common.mcp_client import agent_startup, agent_shutdown, get_mcp_client
from common.settings import get_settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用生命週期管理"""
    # 啟動時註冊到 MCP Server
    settings = get_settings()
    
    capabilities = {
        "browser_automation": True,
        "dynamic_content": True,
        "threads_scraping": True,
        "auth_handling": True
    }
    
    metadata = {
        "version": "1.0.0",
        "author": "AI Assistant",
        "max_concurrent_crawls": 3,
        "supported_platforms": ["threads"],
        "requires_auth": True
    }
    
    success = await agent_startup(capabilities, metadata)
    if success:
        print("✅ Playwright Crawler Agent registered to MCP Server")
    else:
        print("❌ Failed to register Playwright Crawler Agent to MCP Server")
    
    yield
    
    # 關閉時清理
    await agent_shutdown()
    print("🛑 Playwright Crawler Agent shutdown completed")


app = FastAPI(
    title="Playwright Crawler Agent",
    version="1.0.0",
    description="使用 Playwright 和使用者提供的認證狀態來爬取 Threads 貼文。",
    lifespan=lifespan
)

def json_serializer(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    raise TypeError ("Type %s not serializable" % type(obj))

class CrawlRequest(BaseModel):
    username: str = Field(..., description="要爬取的 Threads 使用者名稱 (不含 @)")
    max_posts: int = Field(default=100, gt=0, le=500, description="要爬取的最大貼文數量")
    auth_json_content: Dict[str, Any] = Field(..., description="包含認證 cookies 和狀態的 auth.json 內容")
    task_id: Optional[str] = Field(default=None, description="任務 ID，用於進度追蹤")

# --- Agent Instance ---
playwright_logic = PlaywrightLogic()

# --- API Endpoints ---
@app.post("/v1/playwright/crawl", response_model=PostMetricsBatch, tags=["Plan F"])
async def crawl_and_get_batch(request: CrawlRequest):
    """
    接收爬取請求，執行 Playwright 爬蟲，並一次性返回完整的 PostMetricsBatch。
    認證內容由請求方在 request body 中提供。
    """
    # 使用傳入的 task_id，如果沒有則生成新的
    task_id = request.task_id or str(uuid.uuid4())
    logic = PlaywrightLogic()

    try:
        batch = await logic.fetch_posts(
            username=request.username,
            max_posts=request.max_posts,
            auth_json_content=request.auth_json_content, # 使用傳入的認證內容
            task_id=task_id
        )
        return batch
    except Exception as e:
        logging.error(f"Crawling failed in main: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health", tags=["Monitoring"])
async def health_check():
    """
    執行健康檢查。
    未來可以擴充此檢查以驗證 Playwright 環境是否正常。
    """
    return {"status": "healthy", "service": "Playwright Crawler Agent"}

# MCP 整合端點
@app.get("/mcp/capabilities", tags=["MCP"])
async def get_capabilities():
    """獲取 Agent 能力"""
    return {
        "browser_automation": True,
        "dynamic_content": True,
        "threads_scraping": True,
        "auth_handling": True,
        "max_concurrent": 3,
        "supported_formats": ["PostMetricsBatch"]
    }

@app.get("/mcp/discover", tags=["MCP"])
async def discover_other_agents():
    """發現其他 Agent"""
    try:
        mcp_client = get_mcp_client()
        
        # 發現 vision agent 用於後續處理
        vision_agents = await mcp_client.discover_agents(role="vision", status="ONLINE")
        analysis_agents = await mcp_client.discover_agents(role="analysis", status="ONLINE")
        
        return {
            "vision_agents": vision_agents,
            "analysis_agents": analysis_agents,
            "total_discovered": len(vision_agents) + len(analysis_agents)
        }
    except Exception as e:
        logging.error(f"Failed to discover agents: {e}")
        return {"error": str(e), "vision_agents": [], "analysis_agents": []}

@app.post("/mcp/request-media-download", tags=["MCP"])
async def request_media_download(
    post_url: str,
    media_urls: list[str],
    background_tasks: BackgroundTasks
):
    """請求 MCP Server 下載媒體檔案"""
    try:
        mcp_client = get_mcp_client()
        result = await mcp_client.download_media(post_url, media_urls)
        
        logging.info(f"Media download requested for {post_url}: {len(media_urls)} files")
        return result
        
    except Exception as e:
        logging.error(f"Failed to request media download: {e}")
        raise HTTPException(status_code=500, detail=str(e)) 