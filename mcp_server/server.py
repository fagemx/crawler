"""
MCP (Model Context Protocol) Server 實現

Agent 註冊中心和服務發現機制
"""

import json
import os
import asyncio
from typing import Dict, List, Optional, Any
from pathlib import Path
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as redis
from contextlib import asynccontextmanager
from pydantic import BaseModel

from common.settings import get_settings
from agents.ranker.ranker_logic import RankerAgent
from common.db_client import get_db_client


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
    
    async def initialize(self):
        """初始化 MCP Server"""
        # 初始化 Redis 連接
        self.redis_client = redis.from_url(
            self.settings.redis.url,
            encoding="utf-8",
            decode_responses=True
        )
        
        # 載入本地 Agent Cards
        await self.load_local_agent_cards()
        
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
    
    async def load_agent_cards_from_redis(self):
        """從 Redis 載入 Agent Cards"""
        if not self.redis_client:
            return
        
        try:
            cards_data = await self.redis_client.hgetall("mcp:agent_cards")
            
            for name, card_json in cards_data.items():
                if name not in self.agent_cards:  # 避免覆蓋本地檔案
                    card_data = json.loads(card_json)
                    self.agent_cards[name] = AgentCard(card_data)
                    
        except Exception as e:
            print(f"從 Redis 載入 Agent Cards 失敗: {e}")
    
    async def register_agent(self, agent_card_data: Dict[str, Any]) -> bool:
        """註冊新的 Agent"""
        try:
            agent_card = AgentCard(agent_card_data)
            
            # 驗證必要欄位
            if not agent_card.name or not agent_card.url:
                raise ValueError("Agent name and URL are required")
            
            # 更新狀態
            agent_card.status = "active"
            agent_card.last_seen = asyncio.get_event_loop().time()
            
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
            
            print(f"註冊 Agent: {agent_card.name}")
            return True
            
        except Exception as e:
            print(f"註冊 Agent 失敗: {e}")
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
        import httpx
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            for agent_name, agent_card in self.agent_cards.items():
                try:
                    response = await client.get(agent_card.health_check_url)
                    if response.status_code == 200:
                        agent_card.status = "active"
                    else:
                        agent_card.status = "error"
                except Exception:
                    agent_card.status = "inactive"
                
                agent_card.last_seen = asyncio.get_event_loop().time()
                
                # 更新 Redis
                if self.redis_client:
                    await self.redis_client.hset(
                        "mcp:agent_cards",
                        agent_name,
                        json.dumps(agent_card.to_dict())
                    )
    
    async def cleanup(self):
        """清理資源"""
        if self.redis_client:
            await self.redis_client.close()


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
async def register_agent(agent_card: Dict[str, Any]):
    """註冊 Agent"""
    success = await mcp_server.register_agent(agent_card)
    if success:
        return {"message": "Agent registered successfully"}
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
    
    stats = {
        "total_agents": len(agents),
        "active_agents": len([a for a in agents if a.status == "active"]),
        "inactive_agents": len([a for a in agents if a.status == "inactive"]),
        "error_agents": len([a for a in agents if a.status == "error"]),
        "skills_count": sum(len(a.skills) for a in agents)
    }
    
    return stats


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