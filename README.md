# 社交媒體內容生成系統

基於 A2A + MCP 多代理協同架構的智能內容創作平台

## 專案概述

本系統採用前沿的 A2A (Agent-to-Agent) + MCP (Model Context Protocol) 架構，將社交媒體內容生成流程拆分為多個專業化的 AI Agent，實現高度模組化、可擴展的智能內容創作。

### 核心功能

- 🕷️ **智能爬蟲**：基於 Apify Threads Actor 的社交媒體內容抓取
- 🎯 **多模態分析**：Gemini 2.5 Pro 驅動的圖片/影片內容理解
- 📊 **智能排序**：基於瀏覽數的高影響力內容識別
- 🧠 **風格分析**：三種模式的內容風格深度解析
- ✍️ **互動生成**：多輪對話式的個性化內容創作
- 🏷️ **自動標籤**：智能 Hashtag 建議和優化

### 技術架構

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Streamlit UI  │    │  Orchestrator   │    │   MCP Server    │
│                 │◄──►│     Agent       │◄──►│                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │
                    ┌───────────┼───────────┐
                    │           │           │
            ┌───────▼───┐ ┌─────▼─────┐ ┌───▼───────┐
            │ Crawler   │ │ Analysis  │ │ Content   │
            │  Agent    │ │  Agent    │ │ Writer    │
            └───────────┘ └───────────┘ └───────────┘
```

## 快速開始

### 環境要求

- Python 3.11+
- Docker & Docker Compose
- PostgreSQL 15+
- Redis 7+

### 安裝步驟

1. **克隆專案**
```bash
git clone <repository-url>
cd social-media-content-generator
```

2. **設置環境變數**
```bash
cp .env.example .env
# 編輯 .env 檔案，填入必要的 API 金鑰
```

3. **啟動服務**
```bash
docker-compose up -d
```

4. **安裝依賴**
```bash
pip install -r requirements.txt
```

5. **啟動系統**
```bash
# 啟動 MCP Server
python mcp_server/server.py

# 啟動各個 Agent（在不同終端）
python agents/crawler/main.py
python agents/analysis/main.py
python agents/content_writer/main.py
python agents/orchestrator/main.py

# 啟動 UI
streamlit run ui/app.py
```

## 環境配置

### 必要的 API 金鑰

```env
# Apify 配置
APIFY_TOKEN=your_apify_token_here

# Gemini AI 配置
GEMINI_API_KEY=your_gemini_api_key_here

# 資料庫配置
DATABASE_URL=postgresql://user:password@localhost:5432/social_media_db

# Redis 配置
REDIS_URL=redis://localhost:6379

# NATS 配置
NATS_URL=nats://localhost:4222
```

### 可選配置

```env
# OpenTelemetry 追蹤
JAEGER_ENDPOINT=http://localhost:14268/api/traces

# 日誌等級
LOG_LEVEL=INFO

# Token 使用量限制
MAX_TOKENS_PER_DAY=1000000
```

## 使用指南

### 基本工作流程

1. **登入系統**：使用帳號密碼登入
2. **設置 API 金鑰**：配置 Apify 和 Gemini API 金鑰
3. **抓取內容**：輸入目標 Threads 用戶名，抓取貼文
4. **分析內容**：選擇分析模式（快速/風格/深度）
5. **生成內容**：基於分析結果互動式生成新貼文
6. **優化調整**：多輪對話優化內容質量

### 三種分析模式

- **快速模仿**：基礎風格特徵分析，適合快速原型
- **風格解析**：深入語言風格分析，適合品牌一致性
- **深度文案**：完整創意手法分析，適合專業創作

## 開發指南

### 專案結構

```
social-media-content-generator/
├── agents/                 # 各個 AI Agent
│   ├── crawler/           # 爬蟲代理
│   ├── analysis/          # 分析代理
│   ├── content_writer/    # 內容生成代理
│   └── orchestrator/      # 協調代理
├── mcp_server/            # MCP 服務註冊中心
├── ui/                    # Streamlit 用戶介面
├── common/                # 共用模組
├── tests/                 # 測試檔案
└── docs/                  # 文檔
```

### 添加新 Agent

1. 在 `agents/` 目錄下創建新的 Agent 資料夾
2. 實現 `main.py`（FastAPI + A2A handler）
3. 創建 `agent_card.json`（MCP 註冊卡片）
4. 在 MCP Server 中註冊新 Agent

### 測試

```bash
# 運行所有測試
pytest

# 運行特定測試
pytest tests/test_crawler.py

# 運行整合測試
pytest tests/integration/
```

## 監控與維護

### 健康檢查

```bash
# 檢查所有服務狀態
curl http://localhost:8000/health

# 檢查特定 Agent
curl http://localhost:8001/health  # Crawler Agent
curl http://localhost:8002/health  # Analysis Agent
```

### 日誌查看

```bash
# 查看系統日誌
docker-compose logs -f

# 查看特定服務日誌
docker-compose logs -f mcp-server
```

### 性能監控

訪問 Jaeger UI：http://localhost:16686

## 故障排除

### 常見問題

1. **Agent 無法註冊到 MCP**
   - 檢查 MCP Server 是否正常運行
   - 確認 Agent Card 格式正確

2. **Apify 抓取失敗**
   - 檢查 API Token 是否有效
   - 確認目標用戶名是否存在

3. **Gemini API 調用失敗**
   - 檢查 API 金鑰是否正確
   - 確認 Token 配額是否充足

### 支援

如需技術支援，請：
1. 查看 [故障排除指南](docs/troubleshooting.md)
2. 檢查 [常見問題](docs/faq.md)
3. 提交 Issue 或聯繫開發團隊

## 授權

本專案採用 MIT 授權條款。詳見 [LICENSE](LICENSE) 檔案。

## 貢獻

歡迎貢獻！請閱讀 [貢獻指南](CONTRIBUTING.md) 了解如何參與開發。

---

**版本**: v1.0.0  
**最後更新**: 2025-01-23  
**維護者**: 開發團隊