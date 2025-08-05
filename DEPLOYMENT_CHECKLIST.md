# 🚀 部署檢查清單

## 📋 新部署流程（完全自動化）

### 1. 準備部署
```bash
# 克隆專案
git clone <repository-url>
cd social-media-content-generator

# 確保環境文件存在
cp .env.example .env
# 編輯 .env 填入必要的 API 金鑰
```

### 2. 啟動服務
```bash
# 啟動所有服務（PostgreSQL 會自動執行初始化腳本）
docker-compose up -d

# 等待所有服務啟動
docker-compose ps
```

### 3. 驗證部署
```bash
# 執行部署驗證腳本
docker exec -i social-media-postgres psql -U postgres -d social_media_db < scripts/verify_deployment.sql
```

**✅ 預期結果：**
- 所有表狀態顯示 `✅ table exists`
- `playwright_post_metrics` 包含 `source`, `crawler_type` 等欄位
- 包含 `UNIQUE(username, post_id, crawler_type)` 約束
- 所有索引都已創建

### 4. 測試功能
```bash
# 檢查 UI 服務
curl http://localhost:8501/_stcore/health

# 檢查服務日誌
docker-compose logs streamlit-ui --tail 20
```

## 🔧 如果遇到問題

### PostgreSQL 初始化被跳過
如果看到 `"Skipping initialization"`：

```bash
# 方法1：手動執行修復腳本
docker exec -i social-media-postgres psql -U postgres -d social_media_db < scripts/fix_playwright_table_final.sql

# 方法2：完全重建（會清除所有數據）
docker-compose down -v
docker-compose up -d
```

### 表結構不正確
```bash
# 執行最新的修復腳本
docker exec -i social-media-postgres psql -U postgres -d social_media_db < scripts/fix_playwright_table_final.sql

# 重啟相關服務
docker-compose restart streamlit-ui
```

### Playwright 依賴問題
```bash
# 重建 UI 容器
docker-compose build --no-cache streamlit-ui
docker-compose up -d streamlit-ui
```

## 📁 重要文件

### 自動初始化文件
- `scripts/init-db.sql` - 主要資料庫初始化腳本
- `alembic/versions/001_add_crawl_state_with_latest_post_id.py` - Alembic 遷移
- `docker-compose.yml` - 已配置自動執行初始化

### 手動修復文件（如需要）
- `scripts/fix_playwright_table_final.sql` - 完整表重建
- `scripts/verify_deployment.sql` - 部署驗證

### 配置文件
- `ui/Dockerfile` - 已包含 Playwright 依賴
- `.env` - 環境變數配置

## ✅ 確認事項

**重新部署時應該自動完成：**
1. ✅ PostgreSQL 自動執行 `scripts/init-db.sql`
2. ✅ 創建所有必要的表（包括正確的 `playwright_post_metrics`）
3. ✅ 創建所有 UNIQUE 約束和索引
4. ✅ UI 容器包含 Playwright 依賴

**如果以上任何一項失敗，請參考本文檔的修復方法！**

## 🚨 緊急修復

如果部署後爬蟲無法保存數據：

```bash
# 一鍵修復
docker exec -i social-media-postgres psql -U postgres -d social_media_db < scripts/fix_playwright_table_final.sql
docker-compose restart streamlit-ui

# 驗證修復
docker exec -i social-media-postgres psql -U postgres -d social_media_db < scripts/verify_deployment.sql
```

---

**最後更新：** 2025-08-05
**版本：** v2.0 - 完全自動化部署