# 🚀 Zeabur 部署指南

## 📋 部署選項總覽

你的項目是**微服務架構**，有多個獨立的 Agent 服務。以下提供 3 種部署策略：

---

## 🎯 **方案 1: 最小化部署 (推薦新手)**

### 服務列表
- ✅ **主 UI (Streamlit)** - 用戶界面
- ✅ **基礎設施** - PostgreSQL + Redis (Zeabur 模板)
- ❌ 其他 Agent 服務 (暫時禁用)

### 部署步驟

#### 1. 基礎設施
在 Zeabur 控制台創建：
```bash
# 1. PostgreSQL 模板
名稱: social-media-postgres
版本: 15

# 2. Redis 模板  
名稱: social-media-redis
版本: 7
```

#### 2. 主應用部署
```bash
# 使用 Dockerfile.minimal
git add Dockerfile.minimal
git commit -m "Add Zeabur minimal deployment"
git push

# 在 Zeabur 中：
# - 選擇 Dockerfile.minimal
# - 端口: 8501 (自動檢測)
# - 環境變數設定如下
```

#### 3. 環境變數配置
```bash
# 資料庫連接
DATABASE_URL=postgresql://user:password@postgres_host:5432/social_media_db

# Redis 連接
REDIS_URL=redis://redis_host:6379

# 應用設定
PYTHONPATH=/app
PYTHONUNBUFFERED=1

# 禁用其他服務
ENABLE_CRAWLER=false
ENABLE_VISION=false
ENABLE_CONTENT_WRITER=false
```

---

## 🔥 **方案 2: 核心功能部署**

### 服務列表
- ✅ **UI + Orchestrator** - 主要應用
- ✅ **Playwright Crawler** - 爬蟲功能
- ✅ **基礎設施** - PostgreSQL + Redis + NATS
- ❌ 其他 Agent (按需部署)

### 部署步驟

#### 1. 基礎設施 (同方案 1 + NATS)
```bash
# 額外需要 NATS (可能需要自建容器)
NATS_URL=nats://nats_host:4222
```

#### 2. 主應用部署
```bash
# 使用 Dockerfile.zeabur
git add Dockerfile.zeabur start-services.sh
git commit -m "Add Zeabur core deployment" 
git push
```

#### 3. 環境變數配置
```bash
# 基礎設施
DATABASE_URL=postgresql://user:password@postgres_host:5432/social_media_db
REDIS_URL=redis://redis_host:6379
NATS_URL=nats://nats_host:4222

# 啟用核心服務
ENABLE_CRAWLER=true
ENABLE_VISION=false
ENABLE_CONTENT_WRITER=false

# 應用設定
PYTHONPATH=/app
PYTHONUNBUFFERED=1
```

---

## 🚀 **方案 3: 分服務部署 (專業)**

### 服務列表
將每個 Agent 作為獨立的 Zeabur 服務部署：

```bash
# 主要服務
1. UI Service (ui/Dockerfile)
2. Orchestrator (agents/orchestrator/Dockerfile)
3. Playwright Crawler (agents/playwright_crawler/Dockerfile)

# 可選服務
4. Vision Agent (agents/vision/Dockerfile)  
5. Content Writer (agents/content_writer/Dockerfile)
6. Clarification (agents/clarification/Dockerfile)
7. 其他 Agent...
```

### 部署步驟

#### 1. 基礎設施
```bash
- PostgreSQL (Zeabur 模板)
- Redis (Zeabur 模板)  
- NATS (可能需要自建)
```

#### 2. 主服務部署
每個服務分別部署：

**UI 服務:**
```bash
Dockerfile: ui/Dockerfile
端口: 8501
環境變數: ORCHESTRATOR_URL=https://orchestrator-xxx.zeabur.app
```

**Orchestrator 服務:**
```bash
Dockerfile: agents/orchestrator/Dockerfile  
端口: 8000
環境變數: 基礎設施連接 + Agent URLs
```

**Playwright Crawler:**
```bash
Dockerfile: agents/playwright_crawler/Dockerfile
端口: 8006
環境變數: 基礎設施連接
```

#### 3. 服務間連接
在各服務的環境變數中設定其他服務的 URL：
```bash
# 在 UI 服務中
ORCHESTRATOR_URL=https://orchestrator-xxx.zeabur.app

# 在 Orchestrator 中  
PLAYWRIGHT_CRAWLER_URL=https://crawler-xxx.zeabur.app
VISION_AGENT_URL=https://vision-xxx.zeabur.app
CONTENT_WRITER_URL=https://writer-xxx.zeabur.app
```

---

## ⚙️ **通用配置要點**

### 1. Dockerfile 端口要求
確保 Dockerfile 中有 `EXPOSE` 聲明：
```dockerfile
EXPOSE 8501  # 或其他端口
```

### 2. 健康檢查
確保服務有健康檢查端點：
```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8501/health || exit 1
```

### 3. 環境變數管理
在 Zeabur 控制台中設定所有必要的環境變數。

### 4. 文件存儲
如果需要文件上傳/存儲，考慮：
- Zeabur 的對象存儲服務
- 或移除 RustFS，改用雲端存儲

---

## 🎯 **推薦開始方式**

1. **第一次部署**: 使用**方案 1 (最小化)**
2. **功能測試**: 確認 UI 和基本功能正常
3. **逐步擴展**: 根據需要加入更多 Agent
4. **生產環境**: 考慮**方案 3 (分服務)**

---

## 🆘 **常見問題**

### Q: 哪個 Dockerfile 是主要的？
A: 根據你的需求選擇：
- 初學者: `Dockerfile.minimal`
- 核心功能: `Dockerfile.zeabur` 
- 個別服務: 各服務目錄下的 `Dockerfile`

### Q: 如何處理依賴服務？
A: 
- PostgreSQL、Redis: 使用 Zeabur 模板
- NATS: 可能需要自建容器或尋找替代方案

### Q: 是否需要全部 Agent？
A: 不需要。可以先部署核心的 UI + Orchestrator + Crawler，其他按需添加。

### Q: 服務間如何通信？
A: 通過環境變數配置其他服務的 URL，使用 HTTP API 通信。

---

## 📞 **下一步**

選擇一個方案開始部署，如果遇到問題可以：
1. 檢查 Zeabur 的部署日誌
2. 確認環境變數配置
3. 檢查服務間的網絡連接

祝部署順利！🚀