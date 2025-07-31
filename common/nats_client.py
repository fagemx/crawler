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
        return None
        
    global _nats_client
    if _nats_client is None or _nats_client.is_closed:
        try:
            settings = get_settings()
            _nats_client = await nats.connect(settings.nats.url)
            logging.info(f"✅ Connected to NATS: {settings.nats.url}")
        except Exception as e:
            logging.error(f"❌ Failed to connect to NATS: {e}")
            return None
    return _nats_client

async def publish_progress(task_id: str, stage: str, **kwargs):
    """發布進度訊息到 NATS"""
    try:
        nc = await get_nats_client()
        if nc is None:
            logging.debug("📡 NATS not available, skipping progress publish")
            return
            
        message = {
            "task_id": task_id,
            "stage": stage,
            "timestamp": asyncio.get_event_loop().time(),
            **kwargs
        }
        await nc.publish("crawler.progress", json.dumps(message).encode())
        logging.debug(f"📡 Published progress: {stage} for {task_id}")
    except Exception as e:
        logging.error(f"❌ Failed to publish progress: {e}")

async def close_nats_client():
    """關閉 NATS 客戶端"""
    global _nats_client
    if _nats_client and not _nats_client.is_closed:
        await _nats_client.close()
        _nats_client = None
        logging.info("🛑 NATS client closed")