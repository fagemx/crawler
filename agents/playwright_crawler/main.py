import uuid
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Dict, Any
import json
import datetime

from .playwright_logic import PlaywrightLogic
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
@app.post("/v1/playwright/crawl", tags=["Crawling"])
async def crawl_with_playwright(request: CrawlRequest, background_tasks: BackgroundTasks):
    """
    使用 Playwright 啟動一個新的串流爬取任務。

    此端點接收使用者名稱、最大貼文數和一個包含 `auth.json` 內容的 JSON 物件。
    它會即時串流回傳進度和最終結果。
    """
    task_id = str(uuid.uuid4())

    async def event_generator():
        try:
            # 這是核心的爬取邏輯
            async for event in playwright_logic.fetch_posts(
                username=request.username,
                max_posts=request.max_posts,
                auth_json_content=request.auth_json_content,
                task_id=task_id
            ):
                yield f"data: {json.dumps(event, default=json_serializer)}\n\n"
        except Exception as e:
            # 處理意外的生成器錯誤
            error_event = stream_error(f"爬取任務生成器發生嚴重錯誤: {e}", TaskState.FAILED)
            yield f"data: {json.dumps(error_event, default=json_serializer)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

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