"""
NATS 客戶端實現
用於發布進度訊息和 Agent 間通訊
"""

import asyncio
import json
import logging
from typing import Optional, Dict, Any
from .settings import get_settings

try:
    import nats
    from nats.aio.client import Client as NATS
    NATS_AVAILABLE = True
except ImportError:
    NATS_AVAILABLE = False
    logging.warning("⚠️  NATS library not available. Install with: pip install nats-py")

_nats_client: Optional[NATS] = None

async def get_nats_client() -> Optional[NATS]:
    """獲取全局 NATS 客戶端"""
    if not NATS_AVAILABLE:
        logging.debug("📡 NATS library not available")
        return None
        
    global _nats_client
    if _nats_client is None or _nats_client.is_closed:
        try:
            settings = get_settings()
            _nats_client = await nats.connect(
                servers=[settings.nats.url],
                max_reconnect_attempts=60,   # 重試 60 次
                reconnect_time_wait=2,       # 每 2 秒
                connect_timeout=2
            )
            logging.info(f"✅ Connected to NATS: {settings.nats.url}")
        except Exception as e:
            logging.warning(f"⚠️ NATS connection failed (non-critical): {e}")
            return None
    return _nats_client

async def publish_progress(task_id: str, stage: str, **kwargs):
    """發布進度訊息到 NATS 和 Redis"""
    message = {
        "task_id": task_id,
        "stage": stage,
        "timestamp": asyncio.get_event_loop().time(),
        **kwargs
    }
    
    # 1. 嘗試發布到 NATS（原有邏輯）
    try:
        nc = await get_nats_client()
        if nc is not None:
            await nc.publish("crawler.progress", json.dumps(message).encode())
            logging.info(f"📡 Published to NATS: {stage} for {task_id}")
    except Exception as e:
        logging.warning(f"⚠️ NATS publish failed: {e}")
    
    # 2. 同時寫入 Redis（新增功能）
    try:
        from .redis_client import get_redis_client
        redis_client = get_redis_client()
        
        # 計算進度百分比（如果有相關資訊）
        progress_data = {"stage": stage, "timestamp": message["timestamp"]}
        
        # 嘗試解析進度百分比
        if "done" in kwargs and "total" in kwargs and kwargs["total"] > 0:
            progress_data["progress"] = round(kwargs["done"] / kwargs["total"] * 100, 1)
        elif "completed" in stage:
            progress_data["progress"] = 100.0
        elif "start" in stage:
            progress_data["progress"] = 0.0
        elif "error" in stage:
            progress_data["status"] = "error"
            progress_data["error"] = kwargs.get("error", "Unknown error")
        
        # 添加其他有用的資訊
        for key in ["username", "posts_count", "message", "error", "final_data"]:
            if key in kwargs:
                progress_data[key] = kwargs[key]
        
        redis_client.set_task_status(task_id, progress_data)
        logging.info(f"💾 Saved to Redis: {stage} for {task_id}")
        
    except Exception as e:
        logging.warning(f"⚠️ Redis save failed: {e}")
    
    # 原有的日誌
    logging.info(f"📊 Progress update: {stage} for {task_id}")

async def close_nats_client():
    """關閉 NATS 客戶端"""
    global _nats_client
    if _nats_client and not _nats_client.is_closed:
        await _nats_client.close()
        _nats_client = None
        logging.info("🛑 NATS client closed")