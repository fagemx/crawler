"""
LLM 使用記錄器（正式版·穩定）

- 自動確保 Postgres 中存在 `llm_usage` 表與索引
- 提供輕量級 `log_usage` 非侵入介面，失敗時吞錯不影響主流程
- 欄位聚焦：服務、供應商、模型、時間、token 數、花費、延遲、狀態

注意：為避免循環依賴，本模組不導入 `common.llm_manager`。
"""

from __future__ import annotations

import os
import json
import asyncio
from typing import Any, Dict, Optional
from datetime import datetime, timezone, timedelta

# 注意：避免在模組載入階段就導入資料庫客戶端，以免缺少依賴時造成服務啟動失敗
# 轉為在函式內延遲導入


_TABLE_READY = False
_TABLE_LOCK = asyncio.Lock()


def _now_taipei_iso() -> str:
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).isoformat()


def get_service_name() -> str:
    # 優先使用容器環境變數
    service = os.getenv("AGENT_NAME")
    if service:
        return service
    # UI 容器
    if os.getenv("STREAMLIT_SERVER_PORT"):
        return "streamlit-ui"
    # 後端服務不明時
    return os.getenv("SERVICE_NAME", "app")


async def _ensure_table_exists():
    global _TABLE_READY
    if _TABLE_READY:
        return
    async with _TABLE_LOCK:
        if _TABLE_READY:
            return
        try:
            from .db_client import get_db_client  # 延遲導入
            db = await get_db_client()
            # 建表（若不存在），採最小穩定欄位集合
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_usage (
                    id BIGSERIAL PRIMARY KEY,
                    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    service TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    request_id TEXT,
                    prompt_tokens INTEGER DEFAULT 0,
                    completion_tokens INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0,
                    cost NUMERIC(12,6) DEFAULT 0,
                    latency_ms INTEGER DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'success',
                    error TEXT,
                    metadata JSONB
                );
                CREATE INDEX IF NOT EXISTS idx_llm_usage_ts ON llm_usage (ts DESC);
                CREATE INDEX IF NOT EXISTS idx_llm_usage_svc ON llm_usage (service);
                CREATE INDEX IF NOT EXISTS idx_llm_usage_provider ON llm_usage (provider);
                CREATE INDEX IF NOT EXISTS idx_llm_usage_model ON llm_usage (model);
                CREATE INDEX IF NOT EXISTS idx_llm_usage_status ON llm_usage (status);
                """
            )
            _TABLE_READY = True
        except Exception:
            # 不影響主流程
            _TABLE_READY = False


async def log_usage(
    *,
    provider: str,
    model: str,
    request_id: Optional[str] = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    cost: float = 0.0,
    latency_ms: int = 0,
    status: str = "success",
    error: Optional[str] = None,
    service: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """寫入一筆 LLM 使用紀錄。任何異常將被吞掉以保主流程穩定。"""
    try:
        await _ensure_table_exists()

        from .db_client import get_db_client  # 延遲導入
        db = await get_db_client()
        await db.execute(
            """
            INSERT INTO llm_usage (
                ts, service, provider, model, request_id,
                prompt_tokens, completion_tokens, total_tokens,
                cost, latency_ms, status, error, metadata
            ) VALUES (
                NOW(), $1, $2, $3, $4,
                $5, $6, $7,
                $8, $9, $10, $11, $12
            )
            """,
            service or get_service_name(),
            provider,
            model,
            request_id,
            int(prompt_tokens or 0),
            int(completion_tokens or 0),
            int(total_tokens or 0),
            float(cost or 0.0),
            int(latency_ms or 0),
            status or "success",
            error,
            json.dumps(metadata or {}),
        )
    except Exception:
        # 嚴格吞錯，不阻塞主流程
        return


