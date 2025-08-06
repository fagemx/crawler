# 背景執行和進度追蹤 - 實施指南

## 🎯 實現目標

✅ **已完成的修改**：
- 修改 `publish_progress` 函式，同時寫入 NATS 和 Redis
- 建立 CLI 進度監控腳本 (`monitor_progress.py`)
- 建立測試腳本驗證功能

## 🔧 技術實現

### 1. 進度回報機制 (`common/nats_client.py`)

```python
async def publish_progress(task_id: str, stage: str, **kwargs):
    """發布進度訊息到 NATS 和 Redis"""
    # 1. 原有 NATS 發布（相容性）
    # 2. 新增 Redis 儲存（即時進度查詢）
    # 3. 自動計算進度百分比
```

**功能特色**：
- 🔄 同時支援 NATS 和 Redis
- 📊 自動計算進度百分比
- ⚡ 容錯處理，任一服務失敗不影響另一個
- 📝 詳細的日誌記錄

### 2. 進度監控工具 (`monitor_progress.py`)

```bash
# 監控特定任務
python monitor_progress.py job_c45351e48907

# 列出所有活躍任務
python monitor_progress.py --list
```

**功能特色**：
- 🎯 即時進度條顯示
- 📋 任務狀態總覽
- ⌨️ Ctrl+C 優雅退出
- 🔍 自動偵測任務完成

## 🚀 使用方法

### 方法一：基礎設施 + 監控

```powershell
# 1. 啟動基礎設施
docker-compose up -d postgres redis

# 2. 啟動爬蟲代理
docker-compose up -d --build playwright-crawler-agent

# 3. 在另一個終端監控進度
python monitor_progress.py --list  # 查看可用任務
python monitor_progress.py <task_id>  # 監控特定任務
```

### 方法二：完整測試

```powershell
# Windows 環境
.\test_progress.ps1

# Linux/Mac 環境
python test_background_progress.py
```

## 📊 進度資料格式

Redis 中儲存的進度資料：

```json
{
  "stage": "process_round_2_details",
  "progress": 40.0,
  "timestamp": 1704067200.123,
  "username": "test_user",
  "posts_count": 50,
  "status": "running"
}
```

## 🔍 疑難排解

### Redis 連線問題

```bash
# 檢查 Redis 容器
docker ps | grep redis

# 啟動 Redis（如果未運行）
docker-compose up -d redis

# 測試 Redis 連線
docker-compose exec redis redis-cli ping
```

### NATS 連線問題

```bash
# 檢查 NATS 容器
docker ps | grep nats

# 查看 NATS 日誌
docker-compose logs nats

# NATS 失敗不影響 Redis 進度儲存
```

### 環境變數設定

確認 `.env` 檔案包含：

```env
REDIS_URL=redis://redis:6379/0
NATS_URL=nats://nats:4222
```

## 🎉 成功指標

執行成功後，你將看到：

1. **即時進度追蹤**：
   ```
   用戶: test_user | 貼文數: 50 | [████████████░░░░░░] 40.0% | 階段: process_round_2_details
   ```

2. **背景執行確認**：
   - 關閉終端或 UI，爬蟲繼續執行
   - 重新開啟監控，進度不丟失

3. **容錯能力**：
   - NATS 服務停止，Redis 進度照常儲存
   - Redis 暫時不可用，不影響爬蟲執行

## 📋 TODO 清單

- [x] 修改 `publish_progress` 支援 Redis
- [x] 建立 CLI 監控工具
- [x] 建立測試腳本
- [ ] 修改 UI 從 Redis 讀取進度
- [ ] 增加進度持久化選項

## 🔗 相關檔案

- `common/nats_client.py` - 核心進度回報
- `common/redis_client.py` - Redis 任務狀態管理  
- `monitor_progress.py` - CLI 監控工具
- `test_background_progress.py` - 功能測試
- `test_progress.ps1` - Windows 測試腳本

---

💡 **提示**：這個實現是「最短路徑」方案，未來可以根據需要擴展更多功能，如進度持久化、UI 整合等。