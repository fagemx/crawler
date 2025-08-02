# Plan E 架構測試指南

## 📋 測試概述

Plan E 重構後，我們有三個層次的測試來確保系統正常運作：

1. **向後兼容性測試** - 確保舊功能仍然可用
2. **分階段測試** - 測試 Plan E 的每個階段
3. **簡單功能測試** - 測試特定功能（如排序）

## 🚀 快速開始

### 前置條件

1. **環境變數設置**：
```bash
# 必需的環境變數
GOOGLE_API_KEY=your_gemini_api_key
REDIS_URL=redis://localhost:6379/0
DATABASE_URL=postgresql://postgres:password@localhost:5432/social_media_db
```

2. **啟動基礎設施**：
```bash
# 啟動 Redis 和 PostgreSQL
docker compose up -d postgres redis nats
```

3. **初始化資料庫**：
```bash
# 執行資料庫 schema
psql -h localhost -U postgres -d social_media_db -f database/schema_planE.sql
```

## 📊 測試執行順序

### 1. 向後兼容性測試（推薦先執行）

```bash
python test_backward_compatibility.py
```

**目的**：確保舊的 `JinaScreenshotCapture` 功能在 Plan E 重構後仍然可用。

**測試內容**：
- ✅ Jina Reader Markdown 解析
- ✅ Jina Reader Screenshot 功能
- ✅ Gemini Vision 分析
- ✅ 完整的指標整合流程

**預期結果**：所有測試通過，確認向後兼容性。

### 2. 簡單排序功能測試

```bash
python test_ranking_simple.py
```

**目的**：測試 Plan E 的核心排序邏輯。

**測試內容**：
- ✅ Redis 連接和基本操作
- ✅ Plan E 分數計算公式：`score = views + 0.3*(likes+comments) + 0.1*(reposts+shares)`
- ✅ 排序正確性驗證
- ✅ 缺失數據處理

**預期結果**：排序邏輯正確，分數計算準確。

### 3. Plan E 分階段測試（完整測試）

```bash
python test_plan_e_stages.py
```

**目的**：測試完整的 Plan E 工作流程。

**測試階段**：
1. **基礎設施測試** - Redis + PostgreSQL 連接
2. **JinaMarkdown Agent 測試** - Markdown 解析 + 雙重存儲
3. **VisionFill Agent 測試** - Vision 補值功能
4. **排序功能測試** - 完整排序流程
5. **端到端整合測試** - 模擬完整工作流

**預期結果**：所有階段測試通過，確認 Plan E 架構正常。

## 🔧 故障排除

### 常見問題

1. **Redis 連接失敗**
```bash
# 檢查 Redis 是否運行
docker compose ps redis
docker compose logs redis

# 測試連接
redis-cli ping
```

2. **PostgreSQL 連接失敗**
```bash
# 檢查 PostgreSQL 是否運行
docker compose ps postgres
docker compose logs postgres

# 測試連接
psql -h localhost -U postgres -d social_media_db -c "SELECT version();"
```

3. **Gemini API 錯誤**
```bash
# 檢查 API Key 是否設置
echo $GOOGLE_API_KEY
echo $GEMINI_API_KEY

# 檢查 API Key 是否有效（可以用簡單的 curl 測試）
```

4. **Jina Reader API 錯誤**
```bash
# 測試 Jina Reader 連接
curl -H "x-respond-with: markdown" "https://r.jina.ai/https://www.threads.com"
```

### 測試失敗處理

1. **部分測試失敗但不影響核心功能**：
   - Vision 相關測試失敗通常是因為 API Key 未設置
   - 這不影響 Markdown 解析功能

2. **基礎設施測試失敗**：
   - 必須先解決 Redis/PostgreSQL 連接問題
   - 檢查 Docker 容器狀態和網路連接

3. **排序測試失敗**：
   - 檢查 Redis 中的數據格式
   - 驗證分數計算公式實現

## 📈 測試結果解讀

### 成功指標

- ✅ **向後兼容性測試 4/4 通過** - 舊功能正常
- ✅ **排序功能測試 2/2 通過** - 核心邏輯正確  
- ✅ **Plan E 分階段測試 5/5 通過** - 新架構完整可用

### 部分成功情況

- ⚠️ **Vision 測試跳過** - 未設置 API Key，但不影響基本功能
- ⚠️ **某些指標為 0** - 可能是測試 URL 問題，不算失敗

## 🎯 Plan E 工作流驗證

完整的 Plan E 工作流應該是：

```mermaid
graph LR
    A[Crawler URLs] --> B[JinaMarkdown]
    B --> C[Redis Tier-0]
    B --> D[PostgreSQL Tier-1]
    B --> E[Vision Queue]
    E --> F[VisionFill]
    F --> C
    C --> G[Ranking]
    G --> H[Top-K URLs]
    H --> I[PostAnalyzer]
    I --> J[TemplateGen]
    J --> K[ContentWriter]
```

### 驗證檢查點

1. **數據寫入**：
   - Redis 中有指標數據 (`metrics:{url}`)
   - PostgreSQL 中有貼文和指標記錄

2. **排序功能**：
   - 能從 Redis 批量獲取指標
   - 分數計算正確
   - 排序結果按分數降序

3. **Vision 補值**：
   - 能識別缺失指標
   - 能使用 Screenshot + Gemini 補值
   - 補值結果寫回存儲

## 🚀 下一步開發

測試通過後，可以繼續開發：

1. **PostAnalyzer Agent** - 分析 Top-K 貼文內容
2. **TemplateGen Agent** - 生成內容模板
3. **ContentWriter Agent** - 最終內容生成
4. **UI 整合** - Streamlit 前端整合

## 📝 測試報告模板

```
Plan E 測試報告
================

測試時間: [日期時間]
測試環境: [開發/測試/生產]

基礎設施:
- Redis: [✅/❌] [狀態說明]
- PostgreSQL: [✅/❌] [狀態說明]

功能測試:
- 向後兼容性: [4/4] [✅/❌]
- 排序功能: [2/2] [✅/❌]  
- Plan E 分階段: [5/5] [✅/❌]

問題記錄:
- [問題描述和解決方案]

結論:
- [系統是否可用]
- [需要注意的問題]
- [下一步建議]
```

這個測試指南確保了 Plan E 架構的每個部分都能正常工作，同時保持了向後兼容性。