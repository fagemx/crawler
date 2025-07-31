"""
MCP Client SDK - Agent 端共用客戶端
結合示範方案的簡潔性和我們的需求
"""

import asyncio
import os
import socket
import time
from typing import Dict, Any, Optional

import httpx
import structlog

log = structlog.get_logger()


class MCPClient:
    """MCP 客戶端 - 供各 Agent 使用"""
    
    def __init__(
        self,
        mcp_url: str = None,
        agent_name: str = None,
        agent_role: str = None,
        agent_port: int = None,
        version: str = "1.0.0"
    ):
        self.mcp_url = mcp_url or os.getenv("MCP_SERVER_URL", "http://mcp-server:10100")
        self.agent_name = agent_name or os.getenv("AGENT_NAME")
        self.agent_role = agent_role or os.getenv("AGENT_ROLE")
        self.agent_port = agent_port or int(os.getenv("AGENT_PORT", 8000))
        self.version = version or os.getenv("GIT_SHA", "dev")
        
        # 自動生成 Agent URL
        hostname = os.getenv("HOSTNAME", socket.gethostname())
        self.agent_url = f"http://{hostname}:{self.agent_port}"
        
        self._heartbeat_task = None
        self._registered = False
    
    async def register(self, capabilities: Dict[str, Any] = None, metadata: Dict[str, Any] = None) -> bool:
        """註冊 Agent 到 MCP Server"""
        if not self.agent_name or not self.agent_role:
            log.error("mcp_register_failed", reason="missing agent_name or agent_role")
            return False
        
        payload = {
            "name": self.agent_name,
            "role": self.agent_role,
            "url": self.agent_url,
            "version": self.version,
            "capabilities": capabilities or {},
            "agent_metadata": metadata or {
                "hostname": socket.gethostname(),
                "pid": os.getpid(),
                "started_at": time.time()
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(f"{self.mcp_url}/register", json=payload)
                response.raise_for_status()
                
                self._registered = True
                log.info("mcp_registered", agent=self.agent_name, role=self.agent_role, url=self.agent_url)
                return True
                
        except Exception as e:
            log.error("mcp_register_failed", agent=self.agent_name, error=str(e))
            return False
    
    async def start_heartbeat(self, interval: int = 30) -> None:
        """啟動心跳任務"""
        if not self._registered:
            log.warning("heartbeat_not_started", reason="agent not registered")
            return
        
        if self._heartbeat_task and not self._heartbeat_task.done():
            log.warning("heartbeat_already_running")
            return
        
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(interval))
        log.info("heartbeat_started", agent=self.agent_name, interval=interval)
    
    async def _heartbeat_loop(self, interval: int):
        """心跳循環"""
        while True:
            try:
                await asyncio.sleep(interval)
                
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.post(f"{self.mcp_url}/heartbeat/{self.agent_name}")
                    response.raise_for_status()
                    
                # 只在第一次成功或從失敗恢復時記錄
                if not hasattr(self, '_last_heartbeat_success') or not self._last_heartbeat_success:
                    log.info("heartbeat_success", agent=self.agent_name)
                    self._last_heartbeat_success = True
                    
            except Exception as e:
                if not hasattr(self, '_last_heartbeat_success') or self._last_heartbeat_success:
                    log.warning("heartbeat_failed", agent=self.agent_name, error=str(e))
                    self._last_heartbeat_success = False
    
    async def stop_heartbeat(self):
        """停止心跳任務"""
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            log.info("heartbeat_stopped", agent=self.agent_name)
    
    async def discover_agents(self, role: str = None, status: str = "ONLINE") -> list:
        """發現其他 Agent"""
        try:
            params = {}
            if role:
                params["role"] = role
            if status:
                params["status"] = status
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.mcp_url}/agents", params=params)
                response.raise_for_status()
                
                agents = response.json()
                log.info("agents_discovered", count=len(agents), role=role, status=status)
                return agents
                
        except Exception as e:
            log.error("agent_discovery_failed", role=role, error=str(e))
            return []
    
    async def get_agent(self, name: str) -> Optional[Dict[str, Any]]:
        """獲取特定 Agent 資訊"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.mcp_url}/agents/{name}")
                response.raise_for_status()
                return response.json()
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
        except Exception as e:
            log.error("get_agent_failed", agent=name, error=str(e))
            return None
    
    async def download_media(self, post_url: str, media_urls: list, max_concurrent: int = 3) -> Dict[str, Any]:
        """請求 MCP Server 下載媒體檔案"""
        try:
            payload = {
                "post_url": post_url,
                "media_urls": media_urls,
                "max_concurrent": max_concurrent
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(f"{self.mcp_url}/media/download", json=payload)
                response.raise_for_status()
                
                result = response.json()
                log.info("media_download_requested", post_url=post_url, media_count=len(media_urls))
                return result
                
        except Exception as e:
            log.error("media_download_failed", post_url=post_url, error=str(e))
            return {"status": "failed", "error": str(e)}
    
    async def get_media_files(self, post_url: str) -> Dict[str, Any]:
        """獲取貼文的媒體檔案"""
        try:
            # URL encode the post_url
            import urllib.parse
            encoded_url = urllib.parse.quote(post_url, safe='')
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.mcp_url}/media/{encoded_url}")
                response.raise_for_status()
                return response.json()
                
        except Exception as e:
            log.error("get_media_files_failed", post_url=post_url, error=str(e))
            return {"media_files": [], "count": 0}


# 全域 MCP 客戶端實例
_mcp_client: Optional[MCPClient] = None


def get_mcp_client() -> MCPClient:
    """獲取全域 MCP 客戶端實例"""
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = MCPClient()
    return _mcp_client


def init_mcp_client(
    mcp_url: str = None,
    agent_name: str = None,
    agent_role: str = None,
    agent_port: int = None,
    version: str = None
) -> MCPClient:
    """初始化 MCP 客戶端"""
    global _mcp_client
    _mcp_client = MCPClient(mcp_url, agent_name, agent_role, agent_port, version)
    return _mcp_client


# 便利函數
async def register_agent(capabilities: Dict[str, Any] = None, metadata: Dict[str, Any] = None) -> bool:
    """註冊當前 Agent"""
    client = get_mcp_client()
    return await client.register(capabilities, metadata)


async def start_heartbeat(interval: int = 30):
    """啟動心跳"""
    client = get_mcp_client()
    await client.start_heartbeat(interval)


async def discover_agents(role: str = None, status: str = "ONLINE") -> list:
    """發現 Agent"""
    client = get_mcp_client()
    return await client.discover_agents(role, status)


# Agent 啟動輔助函數
async def agent_startup(
    capabilities: Dict[str, Any] = None,
    metadata: Dict[str, Any] = None,
    heartbeat_interval: int = 30
):
    """Agent 啟動時的標準流程"""
    client = get_mcp_client()
    
    # 註冊
    success = await client.register(capabilities, metadata)
    if not success:
        log.error("agent_startup_failed", reason="registration failed")
        return False
    
    # 啟動心跳
    await client.start_heartbeat(heartbeat_interval)
    
    log.info("agent_startup_completed", agent=client.agent_name)
    return True


async def agent_shutdown():
    """Agent 關閉時的清理"""
    client = get_mcp_client()
    await client.stop_heartbeat()
    log.info("agent_shutdown_completed", agent=client.agent_name)


# 使用範例
if __name__ == "__main__":
    async def example():
        # 初始化客戶端
        client = init_mcp_client(
            agent_name="test-agent",
            agent_role="test",
            agent_port=8999
        )
        
        # 註冊並啟動心跳
        await agent_startup(
            capabilities={"testing": True},
            metadata={"version": "1.0.0"}
        )
        
        # 發現其他 Agent
        agents = await discover_agents(role="crawler")
        print(f"Found {len(agents)} crawler agents")
        
        # 等待一段時間
        await asyncio.sleep(60)
        
        # 清理
        await agent_shutdown()
    
    asyncio.run(example())