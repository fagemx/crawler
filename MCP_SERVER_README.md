# MCP Server 實作指南

## 概述

MCP (Model Context Protocol) Server 是社交媒體內容生成系統的核心組件，負責：

- **Agent 註冊與發現**：管理所有 AI Agent 的註冊、狀態監控
- **健康檢查機制**：定期檢查 Agent 服務的健康狀態
- **媒體檔案管理**：整合 RustFS 進行媒體檔案下載和存儲
- **操作日誌記錄**：完整的系統操作和錯誤追蹤
- **資料庫 Schema 管理**：統一的資料庫結構和函數

## 架構設計

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Agent Cards   │    │   MCP Server    │    │   Database      │
│   (Local/Redis) │◄──►│   (FastAPI)     │◄──►│   (PostgreSQL)  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │   RustFS        │
                       │   (Media Store) │
                       └─────────────────┘
```

## 功能特性

### 1. Agent 管理
- **註冊機制**：支援動態 Agent 註冊
- **服務發現**：根據技能和能力查找 Agent
- **狀態監控**：實時監控 Agent 健康狀態
- **版本管理**：支援 Agent 版本控制

### 2. 媒體檔案處理
- **批次下載**：並發下載社交媒體中的圖片、影片
- **RustFS 整合**：自動上傳到 RustFS 對象存儲
- **元數據提取**：自動提取媒體檔案的寬度、高度等資訊
- **狀態追蹤**：完整的下載狀態記錄

### 3. 監控與日誌
- **操作日誌**：記錄所有系統操作
- **錯誤追蹤**：詳細的錯誤記錄和堆疊追蹤
- **健康檢查歷史**：Agent 健康檢查的歷史記錄
- **統計資訊**：系統運行統計和性能指標

## 快速開始

### 1. 環境準備

```bash
# 複製環境變數檔案
cp .env.example .env

# 編輯環境變數
nano .env
```

必要的環境變數：
```bash
# 資料庫
DATABASE_URL=postgresql://postgres:password@localhost:5432/social_media_db

# Redis
REDIS_URL=redis://localhost:6379/0

# MCP Server
MCP_SERVER_HOST=0.0.0.0
MCP_SERVER_PORT=10100

# RustFS
RUSTFS_ENDPOINT=http://localhost:9000
RUSTFS_ACCESS_KEY=rustfsadmin
RUSTFS_SECRET_KEY=rustfsadmin
```

### 2. 啟動依賴服務

```bash
# 使用 Docker Compose 啟動基礎設施
docker-compose up -d postgres redis rustfs

# 或啟動所有服務
docker-compose up -d
```

### 3. 初始化資料庫

```bash
# 自動初始化（推薦）
python scripts/start_mcp_server.py --init-db

# 或手動執行 SQL
psql -h localhost -U postgres -d social_media_db -f scripts/init-db.sql
```

### 4. 啟動 MCP Server

```bash
# 開發模式
python scripts/start_mcp_server.py

# 或直接啟動
python -m mcp_server.server

# Docker 模式
docker-compose up -d mcp-server
```

### 5. 驗證安裝

```bash
# 檢查健康狀態
curl http://localhost:10100/health

# 執行完整測試
python test_mcp_server.py

# 查看 API 文檔
open http://localhost:10100/docs
```

## API 端點

### Agent 管理

```bash
# 註冊 Agent
POST /agents/register
{
  "name": "test-agent",
  "description": "Test Agent",
  "url": "http://test-agent:8999",
  "capabilities": {"testing": true},
  "skills": [{"name": "testing", "description": "Test capabilities"}]
}

# 列出所有 Agent
GET /agents

# 查找特定 Agent
GET /agents/{agent_name}
GET /agents/find?query=crawler

# 觸發健康檢查
POST /agents/health-check

# 取消註冊 Agent
DELETE /agents/{agent_name}
```

### 媒體管理

```bash
# 下載媒體檔案
POST /media/download
{
  "post_url": "https://example.com/post/123",
  "media_urls": [
    "https://example.com/image1.jpg",
    "https://example.com/video1.mp4"
  ]
}

# 查看貼文媒體檔案
GET /media/{post_url}
```

### 監控與統計

```bash
# 系統統計
GET /stats

# 操作日誌
GET /system/logs?operation_type=agent_register&limit=100

# 錯誤記錄
GET /system/errors?severity=error&limit=50
```

## 資料庫 Schema

### 核心表格

1. **posts** - 貼文基本資料
2. **post_metrics** - 貼文指標（views, likes 等）
3. **media_files** - 媒體檔案記錄（新增）
4. **processing_log** - Agent 處理記錄

### MCP 管理表格

1. **mcp_agents** - Agent 註冊資訊
2. **agent_health_history** - 健康檢查歷史
3. **system_operation_log** - 系統操作日誌
4. **system_error_log** - 系統錯誤記錄

### 重要函數

```sql
-- Agent 管理
SELECT upsert_agent(name, description, version, url, ...);
SELECT record_health_check(agent_name, status, response_time, ...);

-- 媒體檔案
SELECT upsert_media_file(post_url, original_url, media_type, ...);

-- 日誌記錄
SELECT log_system_operation(operation_type, operation_name, ...);
SELECT log_system_error(error_type, error_message, ...);
```

## 開發指南

### 新增 Agent

1. **建立 Agent Card**
```json
{
  "name": "my-agent",
  "description": "My Custom Agent",
  "version": "1.0.0",
  "url": "http://my-agent:8080",
  "health_check_url": "http://my-agent:8080/health",
  "capabilities": {
    "custom_processing": true
  },
  "skills": [
    {
      "name": "custom_skill",
      "description": "Custom processing capability",
      "tags": ["custom", "processing"]
    }
  ]
}
```

2. **實作健康檢查端點**
```python
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "my-agent"}
```

3. **註冊到 MCP Server**
```python
import httpx

async def register_agent():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://mcp-server:10100/agents/register",
            json=agent_card_data
        )
        return response.json()
```

### 媒體檔案處理

```python
from services.rustfs_client import get_rustfs_client

async def process_media():
    rustfs_client = await get_rustfs_client()
    
    # 下載並存儲媒體檔案
    results = await rustfs_client.download_and_store_media(
        post_url="https://example.com/post/123",
        media_urls=["https://example.com/image.jpg"]
    )
    
    return results
```

### 自定義日誌記錄

```python
from mcp_server.server import mcp_server

async def log_custom_operation():
    await mcp_server._log_operation(
        operation_type="custom_operation",
        operation_name="my_custom_task",
        agent_name="my-agent",
        status="success",
        request_data={"param": "value"},
        execution_time_ms=1500
    )
```

## 監控與維護

### 健康檢查

```bash
# 檢查 MCP Server 狀態
curl http://localhost:10100/health

# 檢查所有 Agent 狀態
curl http://localhost:10100/agents

# 觸發健康檢查
curl -X POST http://localhost:10100/agents/health-check
```

### 日誌監控

```bash
# 查看最近的操作
curl "http://localhost:10100/system/logs?limit=20"

# 查看錯誤記錄
curl "http://localhost:10100/system/errors?severity=error"

# 查看特定 Agent 的操作
curl "http://localhost:10100/system/logs?agent_name=crawler"
```

### 資料庫維護

```sql
-- 清理舊的健康檢查記錄（保留最近30天）
DELETE FROM agent_health_history 
WHERE checked_at < now() - interval '30 days';

-- 清理失敗的媒體下載記錄
DELETE FROM media_files 
WHERE download_status = 'failed' 
AND created_at < now() - interval '7 days';

-- 查看系統統計
SELECT 
    COUNT(*) as total_agents,
    COUNT(*) FILTER (WHERE status = 'active') as active_agents,
    COUNT(*) FILTER (WHERE status = 'inactive') as inactive_agents
FROM mcp_agents;
```

## 故障排除

### 常見問題

1. **Agent 註冊失敗**
   - 檢查 Agent URL 是否可訪問
   - 確認健康檢查端點正常回應
   - 查看系統錯誤日誌

2. **媒體下載失敗**
   - 檢查 RustFS 服務狀態
   - 確認網路連接和 URL 有效性
   - 查看媒體檔案錯誤記錄

3. **資料庫連接問題**
   - 檢查資料庫服務狀態
   - 確認連接字串正確
   - 檢查資料庫權限

### 除錯工具

```bash
# 檢查依賴服務
python scripts/start_mcp_server.py --check-only

# 執行完整測試
python test_mcp_server.py

# 查看詳細日誌
docker-compose logs -f mcp-server

# 資料庫連接測試
python -c "
import asyncio
from common.db_client import get_db_client

async def test():
    db = await get_db_client()
    async with db.get_connection() as conn:
        result = await conn.fetchval('SELECT version()')
        print(f'Database: {result}')

asyncio.run(test())
"
```

## 部署建議

### 生產環境

1. **安全配置**
   - 更改預設密碼和金鑰
   - 啟用 HTTPS
   - 配置防火牆規則

2. **性能優化**
   - 調整資料庫連接池大小
   - 配置 Redis 持久化
   - 啟用監控和告警

3. **高可用性**
   - 使用負載均衡器
   - 配置資料庫主從複製
   - 實作服務自動重啟

### Docker 部署

```yaml
# docker-compose.prod.yml
version: '3.8'
services:
  mcp-server:
    build: ./mcp_server
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/db
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - postgres
      - redis
      - rustfs
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:10100/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

## 貢獻指南

1. Fork 專案
2. 建立功能分支
3. 實作功能並添加測試
4. 更新文檔
5. 提交 Pull Request

## 授權

MIT License - 詳見 LICENSE 檔案