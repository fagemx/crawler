import uuid
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Dict, Any
import json
import datetime
from pathlib import Path
import logging

from .playwright_logic import PlaywrightLogic
from common.models import PostMetricsBatch
from common.a2a import stream_error, TaskState

app = FastAPI(
    title="Playwright Crawler Agent",
    version="1.0.0",
    description="使用 Playwright 和使用者提供的認證狀態來爬取 Threads 貼文。",
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

# --- Agent Instance ---
playwright_logic = PlaywrightLogic()

# --- API Endpoints ---
@app.post("/v1/playwright/crawl", response_model=PostMetricsBatch, tags=["Plan F"])
async def crawl_and_get_batch(request: CrawlRequest):
    """
    接收爬取請求，執行 Playwright 爬蟲，並一次性返回完整的 PostMetricsBatch。
    認證內容由請求方在 request body 中提供。
    """
    task_id = str(uuid.uuid4())
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

# 在應用啟動時可以加入一些初始化邏輯
@app.on_event("startup")
async def startup_event():
    # 這裡可以預熱或檢查 Playwright 環境
    pass

# 在應用關閉時可以加入一些清理邏輯
@app.on_event("shutdown")
async def shutdown_event():
    pass 