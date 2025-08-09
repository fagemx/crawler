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
import json
import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Depends
from fastapi.responses import StreamingResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy.exc import OperationalError
from sqlmodel import SQLModel, Session, select, create_engine
from sqlalchemy import text
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
    max_retries = 10
    retry_delay = 5  # seconds
    
    for attempt in range(max_retries):
        try:
            # 嘗試初始化資料庫
            SQLModel.metadata.create_all(engine)
            # 確保 user_operation_log 表與索引存在（idempotent）
            with Session(engine) as session:
                session.exec(text(
                    """
                    CREATE TABLE IF NOT EXISTS user_operation_log (
                        id               BIGSERIAL PRIMARY KEY,
                        ts               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        user_id          TEXT,
                        anonymous_id     TEXT,
                        session_id       TEXT,
                        actor_type       TEXT NOT NULL DEFAULT 'user' CHECK (actor_type IN ('user')),
                        menu_name        TEXT NOT NULL,
                        page_name        TEXT,
                        action_type      TEXT NOT NULL,
                        action_name      TEXT NOT NULL,
                        resource_id      TEXT,
                        status           TEXT NOT NULL CHECK (status IN ('success','failed','pending')),
                        latency_ms       INTEGER,
                        error_message    TEXT,
                        ip_address       INET,
                        user_agent       TEXT,
                        request_id       TEXT,
                        trace_id         TEXT,
                        metadata         JSONB DEFAULT '{}'
                    );
                    """
                ))
                # 索引
                for idx_sql in [
                    "CREATE INDEX IF NOT EXISTS idx_user_ops_ts_desc ON user_operation_log (ts DESC)",
                    "CREATE INDEX IF NOT EXISTS idx_user_ops_user ON user_operation_log (user_id)",
                    "CREATE INDEX IF NOT EXISTS idx_user_ops_anon ON user_operation_log (anonymous_id)",
                    "CREATE INDEX IF NOT EXISTS idx_user_ops_menu ON user_operation_log (menu_name)",
                    "CREATE INDEX IF NOT EXISTS idx_user_ops_action ON user_operation_log (action_type)",
                    "CREATE INDEX IF NOT EXISTS idx_user_ops_trace ON user_operation_log (trace_id)",
                ]:
                    session.exec(text(idx_sql))
                session.commit()
            log.info("database_initialized_successfully")
            break  # 成功，跳出循環
        except OperationalError as e:
            log.warning(
                "database_connection_failed_on_startup",
                error=str(e),
                attempt=attempt + 1,
                max_attempts=max_retries,
            )
            if attempt + 1 == max_retries:
                log.critical("database_initialization_failed_after_max_retries", error=str(e))
                raise  # 重試次數用完，拋出異常
            
            log.info(f"retrying_database_initialization_in_{retry_delay}_seconds")
            await asyncio.sleep(retry_delay)
    
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


# ============================================================================
# 使用者操作日誌 API
# ============================================================================

from pydantic import BaseModel
from typing import Any, Dict


class UserOperationIn(BaseModel):
    user_id: Optional[str] = None
    anonymous_id: Optional[str] = None
    session_id: Optional[str] = None
    menu_name: str
    page_name: Optional[str] = None
    action_type: str
    action_name: str
    resource_id: Optional[str] = None
    status: str = "success"
    latency_ms: Optional[int] = None
    error_message: Optional[str] = None
    request_id: Optional[str] = None
    trace_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@app.post("/user/ops")
async def create_user_operation(
    payload: UserOperationIn,
    request: Request,
):
    """寫入一筆使用者操作日誌。
    自動補: ip_address、user_agent、request_id（若 header 帶入）、trace_id（若 header 帶入）。
    """
    try:
        # 來源資訊
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
        request_id = payload.request_id or request.headers.get("x-request-id")
        trace_id = payload.trace_id or request.headers.get("x-trace-id") or request.headers.get("traceparent")

        insert_sql = text(
            """
            INSERT INTO user_operation_log (
                user_id, anonymous_id, session_id, actor_type,
                menu_name, page_name, action_type, action_name, resource_id,
                status, latency_ms, error_message,
                ip_address, user_agent, request_id, trace_id, metadata
            ) VALUES (
                :user_id, :anonymous_id, :session_id, 'user',
                :menu_name, :page_name, :action_type, :action_name, :resource_id,
                :status, :latency_ms, :error_message,
                :ip_address, :user_agent, :request_id, :trace_id, :metadata
            ) RETURNING id, ts
            """
        )

        with Session(engine) as session:
            result = session.exec(
                insert_sql,
                {
                    "user_id": payload.user_id,
                    "anonymous_id": payload.anonymous_id,
                    "session_id": payload.session_id,
                    "menu_name": payload.menu_name,
                    "page_name": payload.page_name,
                    "action_type": payload.action_type,
                    "action_name": payload.action_name,
                    "resource_id": payload.resource_id,
                    "status": payload.status,
                    "latency_ms": payload.latency_ms,
                    "error_message": payload.error_message,
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                    "request_id": request_id,
                    "trace_id": trace_id,
                    "metadata": (payload.metadata or {}),
                },
            )
            row = result.first()
            session.commit()

        return {"ok": True, "id": row[0] if row else None, "ts": row[1] if row else None}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/user/ops")
async def list_user_operations(
    request: Request,
    user_id: Optional[str] = None,
    anonymous_id: Optional[str] = None,
    menu_name: Optional[str] = None,
    action_type: Optional[str] = None,
    status: Optional[str] = None,
    start: Optional[str] = None,  # ISO8601
    end: Optional[str] = None,    # ISO8601
    limit: int = 100,
    offset: int = 0,
    format: Optional[str] = None,
):
    """查詢使用者操作日誌。支援 CSV 匯出: ?format=csv"""
    try:
        clauses = ["1=1"]
        params: Dict[str, Any] = {"limit": limit, "offset": offset}

        if user_id:
            clauses.append("user_id = :user_id")
            params["user_id"] = user_id
        if anonymous_id:
            clauses.append("anonymous_id = :anonymous_id")
            params["anonymous_id"] = anonymous_id
        if menu_name:
            clauses.append("menu_name = :menu_name")
            params["menu_name"] = menu_name
        if action_type:
            clauses.append("action_type = :action_type")
            params["action_type"] = action_type
        if status:
            clauses.append("status = :status")
            params["status"] = status
        if start:
            clauses.append("ts >= :start")
            params["start"] = start
        if end:
            clauses.append("ts <= :end")
            params["end"] = end

        where_sql = " AND ".join(clauses)
        base_sql = f"""
            SELECT id, ts, user_id, anonymous_id, session_id, menu_name, page_name,
                   action_type, action_name, resource_id, status, latency_ms,
                   ip_address, user_agent, request_id, trace_id, error_message, metadata
            FROM user_operation_log
            WHERE {where_sql}
            ORDER BY ts DESC
            LIMIT :limit OFFSET :offset
        """

        with Session(engine) as session:
            rows = session.exec(text(base_sql), params).all()

        if format == "csv":
            # 產生 CSV
            import csv
            import io
            buf = io.StringIO()
            writer = csv.writer(buf)
            headers = [
                "id","ts","user_id","anonymous_id","session_id","menu_name","page_name",
                "action_type","action_name","resource_id","status","latency_ms",
                "ip_address","user_agent","request_id","trace_id","error_message","metadata"
            ]
            writer.writerow(headers)
            for r in rows:
                # r 是 sqlalchemy Row，支援 by index 或 key
                writer.writerow([
                    r[0], r[1], r[2], r[3], r[4], r[5], r[6],
                    r[7], r[8], r[9], r[10], r[11], r[12], r[13], r[14], r[15], r[16],
                    json.dumps(r[17] if isinstance(r[17], dict) else r[17]) if len(r) > 17 else None,
                ])
            csv_bytes = buf.getvalue().encode("utf-8-sig")
            filename = f"user_ops_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
            return StreamingResponse(iter([csv_bytes]), media_type="text/csv", headers={
                "Content-Disposition": f"attachment; filename={filename}"
            })

        # JSON 格式
        json_rows = []
        for r in rows:
            json_rows.append({
                "id": r[0],
                "ts": r[1],
                "user_id": r[2],
                "anonymous_id": r[3],
                "session_id": r[4],
                "menu_name": r[5],
                "page_name": r[6],
                "action_type": r[7],
                "action_name": r[8],
                "resource_id": r[9],
                "status": r[10],
                "latency_ms": r[11],
                "ip_address": r[12],
                "user_agent": r[13],
                "request_id": r[14],
                "trace_id": r[15],
                "error_message": r[16],
                "metadata": r[17] if len(r) > 17 else None,
            })
        return {"logs": json_rows, "count": len(json_rows)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/user/ops/options")
async def list_user_ops_options():
    """提供下拉選單可用的選項（去重）。"""
    try:
        with Session(engine) as session:
            menus = session.exec(text("SELECT DISTINCT menu_name FROM user_operation_log ORDER BY menu_name ASC LIMIT 200")).all()
            actions = session.exec(text("SELECT DISTINCT action_type FROM user_operation_log ORDER BY action_type ASC LIMIT 200")).all()
            users = session.exec(text("SELECT DISTINCT user_id FROM user_operation_log WHERE user_id IS NOT NULL ORDER BY user_id ASC LIMIT 200")).all()

        # 轉為簡單 list
        def flatten(rows):
            return [row[0] for row in rows if row and row[0] is not None]

        return {
            "menu_names": flatten(menus),
            "action_types": flatten(actions),
            "user_ids": flatten(users),
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