# Playwright Crawler Agent

基於 Playwright 的高性能 Threads 爬蟲代理，支援大量貼文抓取和 GraphQL 攔截。

## 🔄 資料流程說明

### 當前階段：Playwright Agent（第一階段）
```
1. 爬取 Threads GraphQL API
2. 解析貼文指標：likes_count, comments_count, reposts_count
3. 提取內容：content, created_at
4. 產出：PostMetricsBatch
```

### 下一階段：資料持久化（第二階段）
```
5. JinaAgent 接收 PostMetricsBatch
6. 將內容存入 PostgreSQL posts 表
7. 將指標存入 Redis (Tier-0 快取)
8. 準備排序和分析
```

### 第三階段：智能分析
```
9. RankerAgent 從 Redis 讀取指標
10. 計算權重分數並排序
11. ContentAnalyzer 分析文字內容
12. VisionAgent 處理圖片/影片
```

## 🚀 快速開始

### 1. 認證設定

首次使用需要產生 `auth.json` 認證檔案：

```bash
# 進入 playwright_crawler 目錄
cd agents/playwright_crawler

# 執行認證工具（需要桌面環境）
python save_auth.py
```

認證流程：
1. 工具會開啟瀏覽器並導覽到 Threads 登入頁
2. 手動輸入您的 Instagram/Threads 帳號密碼
3. 完成二階段驗證（如有設定）
4. 確認成功登入後按下瀏覽器的 "Resume" 按鈕
5. 工具會自動儲存認證資訊到 `auth.json`

### 2. 驗證設定

```bash
# 檢查所有路徑和設定
python verify_setup.py

# 檢查認證狀態
python check_auth.py
```

### 3. 執行爬蟲

#### 透過 Docker Compose（推薦）

```bash
# 回到專案根目錄
cd ../..

# 啟動服務
docker-compose up social-media-playwright-crawler

# 發送爬取請求
curl -X POST http://localhost:8006/crawl \
  -H "Content-Type: application/json" \
  -d '{"username": "natgeo", "max_posts": 50}'
```

#### 直接執行

```bash
# 安裝依賴
pip install playwright fastapi uvicorn
playwright install chromium

# 啟動 Agent
python main.py

# 在另一個終端發送請求
curl -X POST http://localhost:8006/crawl \
  -H "Content-Type: application/json" \
  -d '{"username": "natgeo", "max_posts": 50}'
```

## 🔧 設定檔

Agent 支援多種設定方式：

### 環境變數

```bash
# 服務設定
PLAYWRIGHT_CRAWLER_HOST=0.0.0.0
PLAYWRIGHT_CRAWLER_PORT=8006

# 爬蟲設定
PLAYWRIGHT_SCROLL_DELAY_MIN=2.0
PLAYWRIGHT_SCROLL_DELAY_MAX=3.5
PLAYWRIGHT_MAX_SCROLL_ATTEMPTS=20
PLAYWRIGHT_NAVIGATION_TIMEOUT=30000
PLAYWRIGHT_HEADLESS=true

# 資料庫連接
DATABASE_URL=postgresql://user:password@localhost:5432/dbname
REDIS_URL=redis://localhost:6379/0
```

### 設定檔

詳見 `agents/playwright_crawler/settings.py` 中的 `PlaywrightCrawlerSettings` 類別。

## 📊 API 介面

### POST /crawl

爬取指定使用者的貼文。

**請求格式：**
```json
{
    "username": "natgeo",
    "max_posts": 50
}
```

**回應格式：**
- **串流模式**: `text/plain` (Server-Sent Events)
- **標準模式**: `application/json`

**範例回應：**
```json
{
    "task_id": "12345",
    "status": "completed",
    "posts_count": 47,
    "posts": [
        {
            "post_id": "3419...",
            "username": "natgeo",
            "content": "Amazing wildlife...",
            "likes_count": 1234,
            "comments_count": 56,
            "reposts_count": 12,
            "created_at": "2024-07-24T10:30:00Z",
            "url": "https://www.threads.net/t/...",
            "source": "playwright",
            "processing_stage": "playwright_crawled"
        }
    ]
}
```

## 🧪 除錯功能

### 自動樣本儲存

當 Agent 遇到解析問題時，會自動儲存除錯檔案：

- `sample_thread_item.json`: 第一筆成功的 thread_item
- `debug_failed_item.json`: 第一筆解析失敗的項目

### 日誌等級

```bash
# 啟動時設定詳細日誌
LOGGING_LEVEL=DEBUG python main.py
```

## 🛡️ 安全性

- **認證隔離**: `auth.json` 僅包含必要的 cookies
- **User-Agent 一致性**: 桌面認證與容器執行使用相同的 UA
- **反偵測**: 內建基本的反機器人偵測機制
- **速率限制**: 智能滾動延遲避免觸發限制

## 🔄 故障排除

### 問題：爬取到 0 貼文

1. **檢查認證狀態**:
   ```bash
   python check_auth.py
   ```

2. **檢查登入狀態**: 查看日誌中是否出現 "偵測到登入頁面"

3. **重新認證**:
   ```bash
   rm auth.json
   python save_auth.py
   ```

### 問題：GraphQL 結構改變

Agent 內建智能貼文搜尋功能，會自動適應 Threads 的結構變化：

- 自動 fallback `thread_items` → `items`
- 智能搜尋 `post` → `post_info` → `postV2` → 深度搜尋
- 自動儲存失敗樣本供分析

### 問題：容器中的 Playwright 錯誤

1. **檢查容器日誌**:
   ```bash
   docker logs social-media-playwright-crawler
   ```

2. **進入容器除錯**:
   ```bash
   docker exec -it social-media-playwright-crawler bash
   playwright --version
   ```

## 📈 效能優化

- **並發控制**: 單一瀏覽器實例，避免資源衝突
- **智能滾動**: 動態調整滾動間隔
- **記憶體管理**: 自動清理已處理的 GraphQL 回應
- **選擇性攔截**: 僅攔截相關的 GraphQL 請求

## 🔗 與下游 Agent 的整合

### 資料輸出格式

Playwright Agent 產出的 `PostMetricsBatch` 包含：

```python
{
    "posts": [
        {
            "url": "https://www.threads.net/t/...",
            "post_id": "3419...",
            "username": "natgeo",
            "likes_count": 1234,
            "comments_count": 56,
            "reposts_count": 12,
            "content": "Amazing wildlife...",  # 新增：完整內容
            "created_at": "2024-07-24T10:30:00Z",  # 新增：發布時間
            "source": "playwright",
            "processing_stage": "playwright_crawled"
        }
    ],
    "batch_id": "uuid-here",
    "username": "natgeo",
    "total_count": 50,
    "processing_stage": "playwright_completed"
}
```

### 下一步驟：JinaAgent

1. **接收 PostMetricsBatch**
2. **分離資料**：
   - 內容 → PostgreSQL `posts` 表
   - 指標 → Redis Tier-0 快取
3. **更新處理狀態**：`processing_stage = "jina_completed"`

### 範例程式碼：下游整合

```python
# 在 JinaAgent 中
async def process_playwright_batch(batch: PostMetricsBatch):
    for post in batch.posts:
        # 存入資料庫
        await db.execute("""
            INSERT INTO posts (url, author, content, created_at) 
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (url) DO UPDATE SET
                content = EXCLUDED.content,
                last_seen = now()
        """, post.url, post.username, post.content, post.created_at)
        
        # 存入 Redis 快取
        await redis.hset(f"metrics:{post.url}", {
            "likes": post.likes_count,
            "comments": post.comments_count,
            "reposts": post.reposts_count
        })
```

## 🔗 相關檔案

- `playwright_logic.py`: 核心爬蟲邏輯
- `settings.py`: 設定管理
- `main.py`: FastAPI 服務入口
- `save_auth.py`: 認證工具
- `check_auth.py`: 認證檢查工具
- `config.py`: 統一設定管理 