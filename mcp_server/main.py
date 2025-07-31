"""
MCP Server 主程式 - 混合優化版本
結合示範方案的簡潔性和我們的獨特功能
"""

import asyncio
import time
import traceback
from datetime import datetime, timedelta
from typing import List, Optional

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from sqlmodel import SQLModel, Session, select, create_engine
from contextlib import asynccontextmanager

from .models import (
    Agent, AgentRegister, AgentResponse, OpsLog, ErrorLog, 
    MediaFile, MediaDownloadRequest, SystemStats
)
from services.rustfs_client import get_rustfs_client
from common.settings import get_settings

# 設置日誌
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO level
    logger_factory=structlog.PrintLoggerFactory(),
)

log = structlog.get_logger()

# 全域變數
settings = get_settings()
engine = create_engine(settings.database.url, echo=settings.development_mode)


def get_session():
    """獲取資料庫 session"""
    with Session(engine) as session:
        yield session


async def log_operation(
    session: Session,
    operation_type: str,
    operation_name: str,
    agent: str = None,
    status: str = "success",
    message: str = "",
    execution_time_ms: int = None,
    extra: dict = None
):
    """記錄操作日誌 - 簡化版"""
    ops_log = OpsLog(
        agent=agent,
        operation_type=operation_type,
        operation_name=operation_name,
        message=message,
        status=status,
        execution_time_ms=execution_time_ms,
        extra=extra or {}
    )
    session.add(ops_log)
    session.commit()


async def log_error(
    session: Session,
    error_type: str,
    error_message: str,
    agent: str = None,
    error_code: str = None,
    traceback_str: str = None,
    severity: str = "error"
):
    """記錄錯誤日誌"""
    error_log = ErrorLog(
        agent=agent,
        error_type=error_type,
        error_code=error_code,
        error_message=error_message,
        traceback=traceback_str,
        severity=severity
    )
    session.add(error_log)
    session.commit()


# 後台任務：監控 Agent 心跳
async def heartbeat_watcher():
    """監控 Agent 心跳，自動標記離線"""
    while True:
        try:
            await asyncio.sleep(30)  # 每30秒檢查一次
            
            with Session(engine) as session:
                # 找出超過90秒沒心跳的 Agent
                cutoff_time = datetime.utcnow() - timedelta(seconds=90)
                agents = session.exec(
                    select(Agent).where(
                        Agent.last_heartbeat < cutoff_time,
                        Agent.status == "ONLINE"
                    )
                ).all()
                
                for agent in agents:
                    agent.status = "DOWN"
                    session.add(agent)
                    log.warning("agent_down", agent=agent.name, last_heartbeat=agent.last_heartbeat)
                
                if agents:
                    session.commit()
                    
        except Exception as e:
            log.error("heartbeat_watcher_error", error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用生命週期管理"""
    # 啟動時
    SQLModel.metadata.create_all(engine)
    log.info("database_initialized")
    
    # 啟動心跳監控
    watcher_task = asyncio.create_task(heartbeat_watcher())
    
    # 初始化 RustFS（如果可用）
    try:
        rustfs_client = await get_rustfs_client()
        await rustfs_client.initialize()
        log.info("rustfs_initialized")
    except Exception as e:
        log.warning("rustfs_init_failed", error=str(e))
    
    yield
    
    # 關閉時
    watcher_task.cancel()
    log.info("mcp_server_shutdown")


# FastAPI 應用
app = FastAPI(
    title="MCP Server",
    description="Model Context Protocol Server - 混合優化版",
    version="2.0.0",
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

# Prometheus 指標
Instrumentator().instrument(app).expose(app)


# ============================================================================
# 核心 API 端點（採用示範方案的簡潔設計）
# ============================================================================

@app.post("/register", response_model=dict)
async def register_agent(
    agent_data: AgentRegister, 
    request: Request,
    session: Session = Depends(get_session)
):
    """註冊 Agent - 簡化版"""
    start_time = time.time()
    
    try:
        # 檢查是否已存在
        existing = session.exec(select(Agent).where(Agent.name == agent_data.name)).first()
        if existing:
            # 更新現有 Agent
            existing.role = agent_data.role
            existing.url = agent_data.url
            existing.version = agent_data.version
            existing.capabilities = agent_data.capabilities
            existing.agent_metadata = agent_data.agent_metadata
            existing.status = "ONLINE"
            existing.last_heartbeat = datetime.utcnow()
            session.add(existing)
        else:
            # 建立新 Agent
            agent = Agent(
                name=agent_data.name,
                role=agent_data.role,
                url=agent_data.url,
                version=agent_data.version,
                capabilities=agent_data.capabilities,
                agent_metadata=agent_data.agent_metadata,
                status="ONLINE"
            )
            session.add(agent)
        
        session.commit()
        
        # 記錄操作
        execution_time = int((time.time() - start_time) * 1000)
        await log_operation(
            session, "register", f"register_{agent_data.name}", 
            agent_data.name, "success", f"Agent {agent_data.name} registered",
            execution_time, {"role": agent_data.role, "url": agent_data.url}
        )
        
        log.info("agent_registered", agent=agent_data.name, role=agent_data.role, url=agent_data.url)
        return {"ok": True, "message": f"Agent {agent_data.name} registered successfully"}

    except Exception as e:
        execution_time = int((time.time() - start_time) * 1000)
        log.exception("register_failed", agent_name=agent_data.name, exc_info=e)
        # 保持日誌記錄，但返回更通用的錯誤
        # 注意: 在生產環境中，不應將詳細的 str(e) 返回給客戶端
        raise HTTPException(status_code=500, detail="An internal error occurred during agent registration.")
        

@app.post("/heartbeat/{name}")
async def heartbeat(name: str, session: Session = Depends(get_session)):
    """Agent 心跳 - 簡化版"""
    try:
        agent = session.exec(select(Agent).where(Agent.name == name)).first()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        agent.last_heartbeat = datetime.utcnow()
        agent.status = "ONLINE"
        session.add(agent)
        session.commit()
        
        return {"ok": True, "timestamp": agent.last_heartbeat}
        
    except HTTPException:
        raise
    except Exception as e:
        await log_error(session, "agent_error", str(e), name, "HEARTBEAT_FAILED")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/agents", response_model=List[AgentResponse])
async def list_agents(
    role: Optional[str] = None,
    status: Optional[str] = None,
    session: Session = Depends(get_session)
):
    """列出 Agent - 支援過濾"""
    try:
        query = select(Agent)
        
        if role:
            query = query.where(Agent.role == role)
        if status:
            query = query.where(Agent.status == status)
        
        agents = session.exec(query).all()
        
        return [
            AgentResponse(
                name=agent.name,
                role=agent.role,
                url=agent.url,
                status=agent.status,
                last_heartbeat=agent.last_heartbeat,
                version=agent.version,
                capabilities=agent.capabilities
            )
            for agent in agents
        ]
        
    except Exception as e:
        log.error("list_agents_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/agents/{name}", response_model=AgentResponse)
async def get_agent(name: str, session: Session = Depends(get_session)):
    """獲取特定 Agent"""
    agent = session.exec(select(Agent).where(Agent.name == name)).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    return AgentResponse(
        name=agent.name,
        role=agent.role,
        url=agent.url,
        status=agent.status,
        last_heartbeat=agent.last_heartbeat,
        version=agent.version,
        capabilities=agent.capabilities
    )


@app.get("/health")
async def health_check():
    """健康檢查"""
    return {"status": "ok", "timestamp": datetime.utcnow()}


# ============================================================================
# 保留的獨特功能：媒體管理
# ============================================================================

@app.post("/media/download")
async def download_media(
    request_data: MediaDownloadRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
):
    """下載媒體檔案到 RustFS - 保留我們的獨特功能"""
    try:
        # 記錄開始
        await log_operation(
            session, "media_download", f"download_{len(request_data.media_urls)}_files",
            None, "pending", f"Starting download of {len(request_data.media_urls)} files",
            extra={"post_url": request_data.post_url, "media_count": len(request_data.media_urls)}
        )
        
        # 後台執行下載
        background_tasks.add_task(
            _download_media_background, 
            request_data.post_url, 
            request_data.media_urls,
            request_data.max_concurrent
        )
        
        return {
            "message": "Media download started",
            "post_url": request_data.post_url,
            "media_count": len(request_data.media_urls),
            "status": "processing"
        }
        
    except Exception as e:
        await log_error(session, "media_error", str(e), None, "MEDIA_DOWNLOAD_FAILED", traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


async def _download_media_background(post_url: str, media_urls: List[str], max_concurrent: int):
    """後台媒體下載任務"""
    try:
        rustfs_client = await get_rustfs_client()
        results = await rustfs_client.download_and_store_media(post_url, media_urls, max_concurrent)
        
        # 記錄結果
        completed = len([r for r in results if r.get("status") == "completed"])
        failed = len([r for r in results if r.get("status") == "failed"])
        
        with Session(engine) as session:
            await log_operation(
                session, "media_download", f"download_completed",
                None, "success", f"Downloaded {completed}/{len(media_urls)} files",
                extra={"completed": completed, "failed": failed, "results": results}
            )
        
        log.info("media_download_completed", post_url=post_url, completed=completed, failed=failed)
        
    except Exception as e:
        with Session(engine) as session:
            await log_error(session, "media_error", str(e), None, "BACKGROUND_DOWNLOAD_FAILED", traceback.format_exc())
        log.error("media_download_failed", post_url=post_url, error=str(e))


@app.get("/media/{post_url:path}")
async def get_media_files(post_url: str, session: Session = Depends(get_session)):
    """獲取貼文的媒體檔案"""
    try:
        media_files = session.exec(
            select(MediaFile).where(MediaFile.post_url == post_url)
        ).all()
        
        return {
            "post_url": post_url,
            "media_files": [
                {
                    "id": mf.id,
                    "original_url": mf.original_url,
                    "media_type": mf.media_type,
                    "rustfs_url": mf.rustfs_url,
                    "download_status": mf.download_status,
                    "file_size": mf.file_size,
                    "created_at": mf.created_at,
                    "downloaded_at": mf.downloaded_at
                }
                for mf in media_files
            ],
            "count": len(media_files)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# 保留的監控功能
# ============================================================================

@app.get("/stats", response_model=SystemStats)
async def get_system_stats(session: Session = Depends(get_session)):
    """系統統計 - 保留豐富的監控資訊"""
    try:
        # Agent 統計
        agents = session.exec(select(Agent)).all()
        agent_stats = {
            "total": len(agents),
            "online": len([a for a in agents if a.status == "ONLINE"]),
            "down": len([a for a in agents if a.status == "DOWN"]),
            "unknown": len([a for a in agents if a.status == "UNKNOWN"]),
            "by_role": {}
        }
        
        # 按角色統計
        for agent in agents:
            role = agent.role
            if role not in agent_stats["by_role"]:
                agent_stats["by_role"][role] = {"total": 0, "online": 0}
            agent_stats["by_role"][role]["total"] += 1
            if agent.status == "ONLINE":
                agent_stats["by_role"][role]["online"] += 1
        
        # 媒體統計
        total_media = session.exec(select(MediaFile)).all()
        media_stats = {
            "total": len(total_media),
            "completed": len([m for m in total_media if m.download_status == "completed"]),
            "failed": len([m for m in total_media if m.download_status == "failed"]),
            "pending": len([m for m in total_media if m.download_status == "pending"])
        }
        
        return SystemStats(
            agents=agent_stats,
            database={"media_files": media_stats},
            timestamp=time.time()
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/system/logs")
async def get_operation_logs(
    operation_type: Optional[str] = None,
    agent: Optional[str] = None,
    limit: int = 100,
    session: Session = Depends(get_session)
):
    """獲取操作日誌"""
    try:
        query = select(OpsLog).order_by(OpsLog.ts.desc()).limit(limit)
        
        if operation_type:
            query = query.where(OpsLog.operation_type == operation_type)
        if agent:
            query = query.where(OpsLog.agent == agent)
        
        logs = session.exec(query).all()
        
        return {
            "logs": [
                {
                    "id": log.id,
                    "timestamp": log.ts,
                    "agent": log.agent,
                    "operation_type": log.operation_type,
                    "operation_name": log.operation_name,
                    "status": log.status,
                    "message": log.message,
                    "execution_time_ms": log.execution_time_ms
                }
                for log in logs
            ],
            "count": len(logs)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(
        "mcp_server.main:app",
        host=settings.mcp.server_host,
        port=settings.mcp.server_port,
        reload=settings.development_mode,
        log_level="info"
    )