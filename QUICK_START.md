# 🚀 快速開始指南

## 簡化版 Threads 爬蟲系統

基於 Apify `curious_coder/threads-scraper` 的簡化實現，只抓取貼文 URL。

### 📋 系統需求

- Python 3.8+
- Apify 帳號和 API Token
- 網路連接

### 🛠️ 快速設置

#### 1. 自動化設置（推薦）

```bash
# 執行自動化設置腳本
python setup_env.py
```

這個腳本會自動：
- 檢查 Python 版本
- 創建虛擬環境
- 安裝必要依賴
- 創建 .env 配置檔案

#### 2. 手動設置

```bash
# 創建虛擬環境
python -m venv venv

# 啟動虛擬環境
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 安裝依賴
pip install -r requirements.txt

# 創建環境配置
cp .env.example .env
```

#### 3. 配置 Apify Token

編輯 `.env` 檔案：

```env
# 設置你的 Apify API Token
APIFY_TOKEN=your_actual_apify_token_here

# 其他配置保持預設值即可
APIFY_THREADS_ACTOR_ID=curious_coder/threads-scraper
APIFY_MAX_POSTS_LIMIT=25
```

> 💡 **如何獲取 Apify Token？**
> 1. 註冊 [Apify 帳號](https://console.apify.com/)
> 2. 前往 [Integrations 頁面](https://console.apify.com/account#/integrations)
> 3. 複製你的 API Token

### 🧪 測試系統

#### 快速測試

```bash
# 啟動虛擬環境（如果還沒啟動）
# Windows: venv\Scripts\activate
# macOS/Linux: source venv/bin/activate

# 執行測試腳本
python test_crawler.py
```

測試會：
- 檢查 Apify 連接
- 抓取 `@09johan24` 的 5 則貼文 URL
- 驗證 URL 格式正確性

#### 預期輸出範例

```
🧪 測試簡化版 Crawler Agent
==================================================
✅ Apify Token: 已設置
📍 使用 Actor: curious_coder/threads-scraper

🎯 測試目標：@09johan24
📊 抓取數量：5 則貼文

開始抓取...
💬 訊息：調用 Apify Actor: curious_coder/threads-scraper
📋 狀態：running - Apify Actor 執行中，等待結果...
📈 進度：20.0% - 處理貼文 1/5
📈 進度：40.0% - 處理貼文 2/5
...

✅ 抓取完成！
📊 總共抓取：5 個 URL
⏱️  處理時間：15.32 秒
👤 用戶：09johan24

📋 抓取到的貼文 URL：
  1. https://www.threads.com/@09johan24/post/DMaHMSqTdFs
     ID: 3141737961795561608_314216
  2. https://www.threads.com/@09johan24/post/CuZsgfWLyiI
     ID: 3141737961795561609_314216
  ...

🔍 URL 格式驗證：
   預期格式：https://www.threads.com/@username/post/code
   ✅ https://www.threads.com/@09johan24/post/DMaHMSqTdFs
   ✅ https://www.threads.com/@09johan24/post/CuZsgfWLyiI
   ...

✅ 有效 URL：5/5
```

### 🚀 啟動完整系統

#### 啟動開發服務

```bash
# 啟動 MCP Server 和 Crawler Agent
python scripts/start_dev.py
```

這會啟動：
- MCP Server (http://localhost:10100)
- Crawler Agent (http://localhost:8001)

#### 手動測試 API

```bash
# 健康檢查
curl http://localhost:8001/health

# 直接抓取 API
curl -X POST "http://localhost:8001/crawl?username=09johan24&max_posts=3"
```

### 📊 系統架構

```
用戶請求 → Crawler Agent → Apify Actor → Threads 數據 → URL 提取 → 回傳結果
```

#### 核心組件

1. **Crawler Agent** (`agents/crawler/`)
   - FastAPI 服務
   - A2A 協議支援
   - 流式處理

2. **MCP Server** (`mcp_server/`)
   - Agent 註冊中心
   - 服務發現

3. **共用模組** (`common/`)
   - 配置管理
   - A2A 通訊協議

### 🔧 自定義使用

#### 抓取不同用戶

```python
from agents.crawler.crawler_logic import CrawlerLogic

crawler = CrawlerLogic()

# 抓取其他用戶的貼文
async for result in crawler.fetch_threads_post_urls(
    username="your_target_user",
    max_posts=10
):
    print(result)
```

#### 調整抓取數量

編輯 `.env` 檔案：

```env
# 調整最大抓取限制
APIFY_MAX_POSTS_LIMIT=50
```

### 📝 範例數據格式

#### 輸入格式

```json
{
  "username": "09johan24",
  "max_posts": 10
}
```

#### 輸出格式

```json
{
  "post_urls": [
    {
      "url": "https://www.threads.com/@09johan24/post/DMaHMSqTdFs",
      "post_id": "3141737961795561608_314216",
      "username": "09johan24"
    }
  ],
  "total_count": 10,
  "processing_time": 15.32,
  "username": "09johan24",
  "timestamp": "2025-01-23T10:30:00.000Z"
}
```

### 🐛 常見問題

#### 1. Apify Token 錯誤

```
❌ 錯誤：未設置 APIFY_TOKEN
```

**解決方案**：檢查 `.env` 檔案中的 `APIFY_TOKEN` 設置

#### 2. 網路連接問題

```
❌ Apify Actor 執行失敗: Connection timeout
```

**解決方案**：檢查網路連接，或增加超時時間

#### 3. 用戶不存在

```
❌ 抓取貼文 URL 失敗: User not found
```

**解決方案**：確認用戶名正確，且該用戶有公開貼文

### 📈 後續擴展

當前系統只實現了基礎的 URL 抓取功能。後續可以添加：

1. **內容分析** - 提取貼文文字內容
2. **互動數據** - 收集點讚、留言、分享數據
3. **媒體處理** - 處理圖片和影片 URL
4. **UI 介面** - Streamlit Web 介面
5. **數據存儲** - PostgreSQL 數據持久化

### 🔗 相關連結

- [Apify Console](https://console.apify.com/)
- [Threads Scraper Actor](https://apify.com/curious_coder/threads-scraper)
- [專案 GitHub](https://github.com/your-repo)

### 📞 支援

如果遇到問題：

1. 檢查 [常見問題](#-常見問題) 部分
2. 查看系統日誌輸出
3. 確認 Apify Token 和網路連接
4. 聯繫開發團隊

---

**版本**: v1.0.0 (簡化版)  
**最後更新**: 2025-01-23  
**狀態**: 基礎功能完成，可用於生產測試