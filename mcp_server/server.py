"""
MCP (Model Context Protocol) Server 實現

Agent 註冊中心和服務發現機制
"""

import json
import os
import asyncio
import time
import traceback
from typing import Dict, List, Optional, Any
from pathlib import Path
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as redis
from contextlib import asynccontextmanager
from pydantic import BaseModel
import httpx

from common.settings import get_settings
from agents.ranker.ranker_logic import RankerAgent
from common.db_client import get_db_client
from services.rustfs_client import get_rustfs_client


class AgentCard:
    """Agent 卡片數據模型"""
    
    def __init__(self, data: Dict[str, Any]):
        self.name = data.get("name", "")
        self.description = data.get("description", "")
        self.version = data.get("version", "1.0.0")
        self.url = data.get("url", "")
        self.capabilities = data.get("capabilities", {})
        self.skills = data.get("skills", [])
        self.requirements = data.get("requirements", {})
        self.metadata = data.get("metadata", {})
        self.health_check_url = data.get("health_check_url", f"{self.url}/health")
        self.last_seen = data.get("last_seen")
        self.status = data.get("status", "unknown")  # active, inactive, error
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "url": self.url,
            "capabilities": self.capabilities,
            "skills": self.skills,
            "requirements": self.requirements,
            "metadata": self.metadata,
            "health_check_url": self.health_check_url,
            "last_seen": self.last_seen,
            "status": self.status
        }
    
    def matches_query(self, query: str) -> bool:
        """檢查是否匹配查詢"""
        query_lower = query.lower()
        
        # 檢查名稱和描述
        if query_lower in self.name.lower() or query_lower in self.description.lower():
            return True
        
        # 檢查技能
        for skill in self.skills:
            if query_lower in skill.get("name", "").lower():
                return True
            if query_lower in skill.get("description", "").lower():
                return True
            
            # 檢查標籤
            for tag in skill.get("tags", []):
                if query_lower in tag.lower():
                    return True
        
        return False


class MCPServer:
    """MCP Server 主類別"""
    
    def __init__(self):
        self.settings = get_settings()
        self.redis_client: Optional[redis.Redis] = None
        self.agent_cards: Dict[str, AgentCard] = {}
        self.agent_cards_dir = Path("mcp_server/agent_cards")
        self.agent_cards_dir.mkdir(exist_ok=True)
        self.db_client = None
    
    async def initialize(self):
        """初始化 MCP Server"""
        # 初始化資料庫連接
        self.db_client = await get_db_client()
        
        # 初始化 Redis 連接
        self.redis_client = redis.from_url(
            self.settings.redis.url,
            encoding="utf-8",
            decode_responses=True
        )
        
        # 初始化 RustFS 客戶端
        try:
            rustfs_client = await get_rustfs_client()
            await rustfs_client.initialize()
            print("✅ RustFS client initialized")
        except Exception as e:
            print(f"⚠️ RustFS initialization failed: {e}")
        
        # 載入本地 Agent Cards
        await self.load_local_agent_cards()
        
        # 從資料庫載入 Agent Cards
        await self.load_agent_cards_from_database()
        
        # 從 Redis 載入 Agent Cards
        await self.load_agent_cards_from_redis()
        
        print(f"MCP Server 初始化完成，載入了 {len(self.agent_cards)} 個 Agent Cards")
    
    async def load_local_agent_cards(self):
        """載入本地 Agent Card 檔案"""
        for card_file in self.agent_cards_dir.glob("*.json"):
            try:
                with open(card_file, 'r', encoding='utf-8') as f:
                    card_data = json.load(f)
                
                agent_card = AgentCard(card_data)
                self.agent_cards[agent_card.name] = agent_card
                
                # 同步到 Redis
                if self.redis_client:
                    await self.redis_client.hset(
                        "mcp:agent_cards",
                        agent_card.name,
                        json.dumps(agent_card.to_dict())
                    )
                
                print(f"載入 Agent Card: {agent_card.name}")
                
            except Exception as e:
                print(f"載入 Agent Card 失敗 {card_file}: {e}")
    
    async def load_agent_cards_from_database(self):
        """從資料庫載入 Agent Cards"""
        if not self.db_client:
            return
        
        try:
            async with self.db_client.get_connection() as conn:
                rows = await conn.fetch("""
                    SELECT name, description, version, url, health_check_url,
                           capabilities, skills, requirements, metadata, status,
                           last_seen
                    FROM mcp_agents
                    WHERE status != 'inactive'
                """)
                
                for row in rows:
                    card_data = {
                        "name": row["name"],
                        "description": row["description"],
                        "version": row["version"],
                        "url": row["url"],
                        "health_check_url": row["health_check_url"],
                        "capabilities": row["capabilities"],
                        "skills": row["skills"],
                        "requirements": row["requirements"],
                        "metadata": row["metadata"],
                        "status": row["status"],
                        "last_seen": row["last_seen"].timestamp() if row["last_seen"] else None
                    }
                    
                    self.agent_cards[row["name"]] = AgentCard(card_data)
                    
                print(f"從資料庫載入了 {len(rows)} 個 Agent Cards")
                    
        except Exception as e:
            print(f"從資料庫載入 Agent Cards 失敗: {e}")

    async def load_agent_cards_from_redis(self):
        """從 Redis 載入 Agent Cards"""
        if not self.redis_client:
            return
        
        try:
            cards_data = await self.redis_client.hgetall("mcp:agent_cards")
            
            for name, card_json in cards_data.items():
                if name not in self.agent_cards:  # 避免覆蓋資料庫和本地檔案
                    card_data = json.loads(card_json)
                    self.agent_cards[name] = AgentCard(card_data)
                    
        except Exception as e:
            print(f"從 Redis 載入 Agent Cards 失敗: {e}")
    
    async def register_agent(self, agent_card_data: Dict[str, Any], request: Optional[Request] = None) -> bool:
        """註冊新的 Agent"""
        start_time = time.time()
        
        try:
            agent_card = AgentCard(agent_card_data)
            
            # 驗證必要欄位
            if not agent_card.name or not agent_card.url:
                raise ValueError("Agent name and URL are required")
            
            # 更新狀態
            agent_card.status = "active"
            agent_card.last_seen = time.time()
            
            # 儲存到資料庫
            if self.db_client:
                await self._save_agent_to_database(agent_card)
            
            # 儲存到記憶體
            self.agent_cards[agent_card.name] = agent_card
            
            # 儲存到 Redis
            if self.redis_client:
                await self.redis_client.hset(
                    "mcp:agent_cards",
                    agent_card.name,
                    json.dumps(agent_card.to_dict())
                )
            
            # 儲存到本地檔案（可選）
            card_file = self.agent_cards_dir / f"{agent_card.name.lower().replace(' ', '_')}.json"
            with open(card_file, 'w', encoding='utf-8') as f:
                json.dump(agent_card.to_dict(), f, indent=2, ensure_ascii=False)
            
            # 記錄操作日誌
            execution_time = int((time.time() - start_time) * 1000)
            await self._log_operation(
                "agent_register", f"register_{agent_card.name}", agent_card.name,
                request_data=agent_card_data, status="success", 
                execution_time_ms=execution_time, request=request
            )
            
            print(f"✅ 註冊 Agent: {agent_card.name}")
            return True
            
        except Exception as e:
            # 記錄錯誤
            execution_time = int((time.time() - start_time) * 1000)
            await self._log_operation(
                "agent_register", f"register_{agent_card_data.get('name', 'unknown')}", 
                agent_card_data.get('name'), request_data=agent_card_data, 
                status="failed", error_message=str(e), execution_time_ms=execution_time, request=request
            )
            
            await self._log_error(
                "agent_error", "AGENT_REGISTER_FAILED", str(e), traceback.format_exc(),
                agent_card_data.get('name'), "agent_registration", agent_card_data
            )
            
            print(f"❌ 註冊 Agent 失敗: {e}")
            return False
    
    async def unregister_agent(self, agent_name: str) -> bool:
        """取消註冊 Agent"""
        try:
            if agent_name in self.agent_cards:
                del self.agent_cards[agent_name]
            
            # 從 Redis 移除
            if self.redis_client:
                await self.redis_client.hdel("mcp:agent_cards", agent_name)
            
            print(f"取消註冊 Agent: {agent_name}")
            return True
            
        except Exception as e:
            print(f"取消註冊 Agent 失敗: {e}")
            return False
    
    async def find_agent(self, query: str) -> Optional[AgentCard]:
        """根據查詢找到最匹配的 Agent"""
        matching_agents = []
        
        for agent_card in self.agent_cards.values():
            if agent_card.matches_query(query):
                matching_agents.append(agent_card)
        
        # 簡單排序：優先返回狀態為 active 的 Agent
        matching_agents.sort(key=lambda x: (x.status == "active", x.name))
        
        return matching_agents[0] if matching_agents else None
    
    async def list_agents(self, skill_filter: Optional[str] = None) -> List[AgentCard]:
        """列出所有 Agent"""
        agents = list(self.agent_cards.values())
        
        if skill_filter:
            filtered_agents = []
            for agent in agents:
                for skill in agent.skills:
                    if skill_filter.lower() in skill.get("name", "").lower():
                        filtered_agents.append(agent)
                        break
            agents = filtered_agents
        
        return agents
    
    async def get_agent(self, agent_name: str) -> Optional[AgentCard]:
        """獲取特定 Agent"""
        return self.agent_cards.get(agent_name)
    
    async def health_check_agents(self):
        """檢查所有 Agent 的健康狀態"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            for agent_name, agent_card in self.agent_cards.items():
                start_time = time.time()
                
                try:
                    response = await client.get(agent_card.health_check_url)
                    response_time_ms = int((time.time() - start_time) * 1000)
                    
                    if response.status_code == 200:
                        agent_card.status = "active"
                        health_status = "healthy"
                        error_message = None
                    else:
                        agent_card.status = "error"
                        health_status = "unhealthy"
                        error_message = f"HTTP {response.status_code}"
                        
                except httpx.TimeoutException:
                    agent_card.status = "inactive"
                    health_status = "timeout"
                    error_message = "Request timeout"
                    response_time_ms = int((time.time() - start_time) * 1000)
                    
                except Exception as e:
                    agent_card.status = "inactive"
                    health_status = "error"
                    error_message = str(e)
                    response_time_ms = int((time.time() - start_time) * 1000)
                
                agent_card.last_seen = time.time()
                
                # 記錄健康檢查結果到資料庫
                if self.db_client:
                    await self._record_health_check(
                        agent_name, health_status, response_time_ms, error_message
                    )
                
                # 更新 Redis
                if self.redis_client:
                    await self.redis_client.hset(
                        "mcp:agent_cards",
                        agent_name,
                        json.dumps(agent_card.to_dict())
                    )
    
    async def _save_agent_to_database(self, agent_card: AgentCard):
        """儲存 Agent 到資料庫"""
        async with self.db_client.get_connection() as conn:
            await conn.execute("""
                SELECT upsert_agent($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """, 
            agent_card.name, agent_card.description, agent_card.version,
            agent_card.url, agent_card.health_check_url, agent_card.capabilities,
            agent_card.skills, agent_card.requirements, agent_card.metadata)
    
    async def _record_health_check(self, agent_name: str, status: str, response_time_ms: int, error_message: str):
        """記錄健康檢查結果"""
        async with self.db_client.get_connection() as conn:
            await conn.execute("""
                SELECT record_health_check($1, $2, $3, $4, $5)
            """, agent_name, status, response_time_ms, error_message, {})
    
    async def _log_operation(
        self, operation_type: str, operation_name: str, agent_name: str = None,
        user_id: str = None, status: str = "success", request_data: Dict = None,
        response_data: Dict = None, error_message: str = None, 
        execution_time_ms: int = None, request: Request = None
    ):
        """記錄系統操作"""
        if not self.db_client:
            return
        
        ip_address = None
        user_agent = None
        
        if request:
            ip_address = request.client.host if request.client else None
            user_agent = request.headers.get("user-agent")
        
        async with self.db_client.get_connection() as conn:
            await conn.execute("""
                SELECT log_system_operation($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """, 
            operation_type, operation_name, agent_name, user_id, status,
            request_data, response_data, error_message, execution_time_ms,
            ip_address, user_agent)
    
    async def _log_error(
        self, error_type: str, error_code: str = None, error_message: str = None,
        stack_trace: str = None, agent_name: str = None, operation_context: str = None,
        request_data: Dict = None, severity: str = "error", metadata: Dict = None
    ):
        """記錄系統錯誤"""
        if not self.db_client:
            return
        
        async with self.db_client.get_connection() as conn:
            await conn.execute("""
                SELECT log_system_error($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """, 
            error_type, error_code, error_message, stack_trace, agent_name,
            operation_context, request_data or {}, severity, metadata or {})

    async def cleanup(self):
        """清理資源"""
        if self.redis_client:
            await self.redis_client.close()
        
        if self.db_client and hasattr(self.db_client, 'close_pool'):
            await self.db_client.close_pool()


# 全域 MCP Server 實例
mcp_server = MCPServer()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用生命週期管理"""
    # 啟動
    await mcp_server.initialize()
    
    # 啟動健康檢查任務
    health_check_task = asyncio.create_task(periodic_health_check())
    
    yield
    
    # 關閉
    health_check_task.cancel()
    await mcp_server.cleanup()


async def periodic_health_check():
    """定期健康檢查"""
    while True:
        try:
            await asyncio.sleep(60)  # 每分鐘檢查一次
            await mcp_server.health_check_agents()
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"健康檢查失敗: {e}")


# FastAPI 應用
app = FastAPI(
    title="MCP Server",
    description="Model Context Protocol Server - Agent 註冊中心和服務發現",
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

# Pydantic model for the ranker request
class RankRequest(BaseModel):
    author_id: str
    top_n: Optional[int] = 5

@app.post("/agents/ranker/rank_posts")
async def rank_posts_endpoint(request: RankRequest):
    """Endpoint to trigger the RankerAgent."""
    try:
        ranker = RankerAgent()
        result = await ranker.rank_posts(author_id=request.author_id, top_n=request.top_n)
        
        # Ensure the shared db client pool is closed after use
        db_client = await get_db_client()
        if db_client and db_client.pool:
            await db_client.close_pool()

        if result.get("status") == "success":
            return result
        else:
            raise HTTPException(status_code=500, detail=result.get("message", "Ranking failed"))
    except Exception as e:
        # Also ensure pool is closed on exception
        db_client = await get_db_client()
        if db_client and db_client.pool:
            await db_client.close_pool()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """健康檢查端點"""
    return {
        "status": "healthy",
        "service": "MCP Server",
        "agents_count": len(mcp_server.agent_cards)
    }


@app.post("/agents/register")
async def register_agent(agent_card: Dict[str, Any], request: Request):
    """註冊 Agent"""
    success = await mcp_server.register_agent(agent_card, request)
    if success:
        return {"message": "Agent registered successfully", "agent_name": agent_card.get("name")}
    else:
        raise HTTPException(status_code=400, detail="Failed to register agent")


@app.delete("/agents/{agent_name}")
async def unregister_agent(agent_name: str):
    """取消註冊 Agent"""
    success = await mcp_server.unregister_agent(agent_name)
    if success:
        return {"message": "Agent unregistered successfully"}
    else:
        raise HTTPException(status_code=404, detail="Agent not found")


@app.get("/agents")
async def list_agents(skill: Optional[str] = None):
    """列出所有 Agent"""
    agents = await mcp_server.list_agents(skill_filter=skill)
    return {
        "agents": [agent.to_dict() for agent in agents],
        "count": len(agents)
    }


@app.get("/agents/{agent_name}")
async def get_agent(agent_name: str):
    """獲取特定 Agent"""
    agent = await mcp_server.get_agent(agent_name)
    if agent:
        return agent.to_dict()
    else:
        raise HTTPException(status_code=404, detail="Agent not found")


@app.get("/agents/find")
async def find_agent(query: str):
    """根據查詢找到 Agent"""
    agent = await mcp_server.find_agent(query)
    if agent:
        return agent.to_dict()
    else:
        raise HTTPException(status_code=404, detail="No matching agent found")


@app.post("/agents/health-check")
async def trigger_health_check(background_tasks: BackgroundTasks):
    """觸發健康檢查"""
    background_tasks.add_task(mcp_server.health_check_agents)
    return {"message": "Health check triggered"}


@app.get("/stats")
async def get_stats():
    """獲取統計資訊"""
    agents = list(mcp_server.agent_cards.values())
    
    # 基本 Agent 統計
    agent_stats = {
        "total_agents": len(agents),
        "active_agents": len([a for a in agents if a.status == "active"]),
        "inactive_agents": len([a for a in agents if a.status == "inactive"]),
        "error_agents": len([a for a in agents if a.status == "error"]),
        "skills_count": sum(len(a.skills) for a in agents)
    }
    
    # 資料庫統計
    db_stats = {}
    if mcp_server.db_client:
        try:
            async with mcp_server.db_client.get_connection() as conn:
                # 貼文統計
                total_posts = await conn.fetchval("SELECT COUNT(*) FROM posts")
                posts_with_metrics = await conn.fetchval("SELECT COUNT(*) FROM post_metrics")
                
                # 媒體檔案統計
                total_media = await conn.fetchval("SELECT COUNT(*) FROM media_files")
                completed_media = await conn.fetchval(
                    "SELECT COUNT(*) FROM media_files WHERE download_status = 'completed'"
                )
                failed_media = await conn.fetchval(
                    "SELECT COUNT(*) FROM media_files WHERE download_status = 'failed'"
                )
                
                # 系統操作統計
                total_operations = await conn.fetchval("SELECT COUNT(*) FROM system_operation_log")
                failed_operations = await conn.fetchval(
                    "SELECT COUNT(*) FROM system_operation_log WHERE status = 'failed'"
                )
                
                db_stats = {
                    "posts": {
                        "total": total_posts,
                        "with_metrics": posts_with_metrics,
                        "completion_rate": posts_with_metrics / total_posts if total_posts > 0 else 0
                    },
                    "media_files": {
                        "total": total_media,
                        "completed": completed_media,
                        "failed": failed_media,
                        "success_rate": completed_media / total_media if total_media > 0 else 0
                    },
                    "operations": {
                        "total": total_operations,
                        "failed": failed_operations,
                        "success_rate": (total_operations - failed_operations) / total_operations if total_operations > 0 else 0
                    }
                }
        except Exception as e:
            db_stats = {"error": str(e)}
    
    return {
        "agents": agent_stats,
        "database": db_stats,
        "timestamp": time.time()
    }


# 媒體管理 API
@app.post("/media/download")
async def download_media(request: Request, data: Dict[str, Any]):
    """下載媒體檔案到 RustFS"""
    try:
        post_url = data.get("post_url")
        media_urls = data.get("media_urls", [])
        
        if not post_url or not media_urls:
            raise HTTPException(status_code=400, detail="post_url and media_urls are required")
        
        # 記錄操作開始
        start_time = time.time()
        await mcp_server._log_operation(
            "media_download", f"download_media_{len(media_urls)}", None,
            request_data=data, status="pending", request=request
        )
        
        # 執行下載
        rustfs_client = await get_rustfs_client()
        results = await rustfs_client.download_and_store_media(post_url, media_urls)
        
        # 統計結果
        completed = len([r for r in results if r.get("status") == "completed"])
        failed = len([r for r in results if r.get("status") == "failed"])
        
        # 記錄操作完成
        execution_time = int((time.time() - start_time) * 1000)
        await mcp_server._log_operation(
            "media_download", f"download_media_{len(media_urls)}", None,
            request_data=data, response_data={"completed": completed, "failed": failed},
            status="success", execution_time_ms=execution_time, request=request
        )
        
        return {
            "message": "Media download completed",
            "total": len(media_urls),
            "completed": completed,
            "failed": failed,
            "results": results
        }
        
    except Exception as e:
        # 記錄錯誤
        execution_time = int((time.time() - start_time) * 1000)
        await mcp_server._log_operation(
            "media_download", f"download_media_error", None,
            request_data=data, status="failed", error_message=str(e),
            execution_time_ms=execution_time, request=request
        )
        
        await mcp_server._log_error(
            "media_error", "MEDIA_DOWNLOAD_FAILED", str(e), traceback.format_exc(),
            None, "media_download", data
        )
        
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/media/{post_url:path}")
async def get_media_files(post_url: str):
    """獲取貼文的媒體檔案"""
    try:
        rustfs_client = await get_rustfs_client()
        media_files = await rustfs_client.get_media_files(post_url)
        
        return {
            "post_url": post_url,
            "media_files": media_files,
            "count": len(media_files)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/system/logs")
async def get_system_logs(
    operation_type: Optional[str] = None,
    agent_name: Optional[str] = None,
    limit: int = 100
):
    """獲取系統操作日誌"""
    if not mcp_server.db_client:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        async with mcp_server.db_client.get_connection() as conn:
            query = """
                SELECT id, operation_type, operation_name, agent_name, status,
                       error_message, execution_time_ms, started_at, completed_at
                FROM system_operation_log
                WHERE 1=1
            """
            params = []
            
            if operation_type:
                query += " AND operation_type = $" + str(len(params) + 1)
                params.append(operation_type)
            
            if agent_name:
                query += " AND agent_name = $" + str(len(params) + 1)
                params.append(agent_name)
            
            query += " ORDER BY started_at DESC LIMIT $" + str(len(params) + 1)
            params.append(limit)
            
            rows = await conn.fetch(query, *params)
            
            return {
                "logs": [dict(row) for row in rows],
                "count": len(rows)
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/system/errors")
async def get_system_errors(
    error_type: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 100
):
    """獲取系統錯誤記錄"""
    if not mcp_server.db_client:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        async with mcp_server.db_client.get_connection() as conn:
            query = """
                SELECT id, error_type, error_code, error_message, agent_name,
                       operation_context, severity, occurred_at, resolved_at
                FROM system_error_log
                WHERE 1=1
            """
            params = []
            
            if error_type:
                query += " AND error_type = $" + str(len(params) + 1)
                params.append(error_type)
            
            if severity:
                query += " AND severity = $" + str(len(params) + 1)
                params.append(severity)
            
            query += " ORDER BY occurred_at DESC LIMIT $" + str(len(params) + 1)
            params.append(limit)
            
            rows = await conn.fetch(query, *params)
            
            return {
                "errors": [dict(row) for row in rows],
                "count": len(rows)
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    
    uvicorn.run(
        "mcp_server.server:app",
        host=settings.mcp.server_host,
        port=settings.mcp.server_port,
        reload=settings.is_development(),
        log_level="info"
    )