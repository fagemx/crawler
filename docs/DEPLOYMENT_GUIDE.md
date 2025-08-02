# 社交媒體內容生成器 - 部署與管理指南

## 📋 目錄

- [系統概述](#系統概述)
- [環境要求](#環境要求)
- [快速開始](#快速開始)
- [啟動方式](#啟動方式)
- [服務管理](#服務管理)
- [外網訪問](#外網訪問)
- [故障排除](#故障排除)
- [維護操作](#維護操作)

---

## 🎯 系統概述

本系統是一個基於 Docker 的微服務架構，包含以下主要組件：

### 基礎設施服務
- **PostgreSQL** (5432) - 主資料庫
- **Redis** (6379) - 快取和會話管理
- **RustFS** (9000) - 對象存儲
- **NATS** (4222) - 訊息佇列

### AI Agent 服務
- **MCP Server** (10100) - Agent 註冊中心
- **Orchestrator** (8000) - 總協調器
- **Clarification Agent** (8004) - 澄清問卷生成
- **Content Writer** (8003) - 內容生成
- **Vision Agent** (8005) - 圖像處理
- **Playwright Crawler** (8006) - 網頁爬蟲
- **Form API** (8010) - 表單處理

### 用戶介面
- **Streamlit UI** (8501) - Web 用戶介面
- **Pinggy Tunnel** - 外網訪問隧道

---

## 🔧 環境要求

### 系統要求
- **作業系統**: Ubuntu 18.04+ / CentOS 7+ / macOS 10.15+
- **記憶體**: 最少 8GB，推薦 16GB+
- **硬碟**: 最少 20GB 可用空間
- **網路**: 穩定的網際網路連線

### 軟體依賴
```bash
# Docker
sudo apt update
sudo apt install docker.io docker compose

# 啟動 Docker 服務
sudo systemctl start docker
sudo systemctl enable docker

# 將用戶加入 docker 群組（避免 sudo）
sudo usermod -aG docker $USER
# 重新登入或執行：newgrp docker
```

### 環境變數設置
```bash
# 複製環境變數範本
cp .env.example .env

# 編輯環境變數（設置 API Keys 等）
nano .env
```

---

## 🚀 快速開始

### 1. 檢查環境
```bash
# 檢查 Docker 環境
docker --version
docker compose version

# 如果沒有 docker compose，安裝它
sudo apt update
sudo apt install docker compose-plugin
```

### 2. 啟動完整系統（超簡單）
```bash
# 方法1: 只要本地訪問
docker compose up -d --build

# 方法2: 要外網訪問（推薦）
docker compose --profile tunnel up -d --build
```

### 3. 驗證部署
```bash
# 檢查服務狀態
docker compose ps

# 訪問服務
# 本地: http://localhost:8501
# 外網: https://hlsbwbzaat.a.pinggy.link

# 健康檢查
curl http://localhost:8501/_stcore/health
```

### 4. 如果遇到問題
```bash
# UI 啟動失敗
./fix_ui.sh

# 端口被佔用
sudo systemctl stop nats-server

# 重新啟動（安全操作，可重複執行）
docker compose --profile tunnel up -d --build
```

---

## 🎛️ 啟動方式

### 方式一：管理腳本（推薦）

#### 完整啟動
```bash
# 啟動所有服務 + UI + Tunnel
./manage_system.sh start-tunnel

# 只啟動服務 + UI（不含外網訪問）
./manage_system.sh start
```

#### 服務管理
```bash
# 查看服務狀態
./manage_system.sh status

# 停止所有服務
./manage_system.sh stop

# 重啟系統
./manage_system.sh restart
```

#### 日誌查看
```bash
# 查看所有服務日誌
./manage_system.sh logs

# 查看 UI 日誌
./manage_system.sh ui-logs

# 查看 Tunnel 日誌
./manage_system.sh tunnel-logs
```

#### 單獨服務管理
```bash
# 重啟 UI
./manage_system.sh restart-ui

# 重啟 Tunnel
./manage_system.sh restart-tunnel
```

### 方式二：Docker Compose 原生指令（推薦簡化方式）

#### 基本操作
```bash
# 啟動所有服務（不含 Tunnel）
docker compose up -d --build

# 啟動所有服務 + Tunnel（推薦）
docker compose --profile tunnel up -d --build

# 停止所有服務
docker compose down

# 停止所有服務 + Tunnel
docker compose --profile tunnel down
```

#### 重複執行安全性
```bash
# ✅ 可以重複執行，不會造成端口衝突
docker compose --profile tunnel up -d --build

# Docker Compose 會智能處理：
# - 已運行的服務顯示 "up-to-date"
# - 有變更的服務會優雅地重新創建
# - 不會重複佔用端口
```

#### 分階段啟動
```bash
# 1. 啟動基礎設施
docker compose up -d postgres redis rustfs nats

# 2. 啟動 MCP Server
docker compose up -d mcp-server

# 3. 啟動 Agent 服務
docker compose up -d orchestrator-agent clarification-agent content-writer-agent form-api vision-agent playwright-crawler-agent

# 4. 啟動 UI
docker compose up -d streamlit-ui

# 5. 啟動 Tunnel（可選）
docker compose --profile tunnel up -d pinggy-tunnel
```

#### 單獨服務管理
```bash
# 重啟特定服務
docker compose restart streamlit-ui
docker compose restart pinggy-tunnel

# 查看特定服務日誌
docker compose logs -f streamlit-ui
docker compose logs -f pinggy-tunnel

# 停止特定服務
docker compose stop streamlit-ui
docker compose stop pinggy-tunnel
```

### 方式三：專用腳本

#### 完整系統啟動
```bash
# 啟動完整系統 + Tunnel
./start_with_tunnel.sh

# 啟動完整系統（不含 Tunnel）
./start_docker_ui.sh
```

#### 單獨服務啟動
```bash
# 只啟動 UI（假設其他服務已運行）
./start_ui_only.sh

# 只啟動 Tunnel（假設 UI 已運行）
./start_tunnel_only.sh
```

---

## 🌐 外網訪問

### Pinggy Tunnel 配置

系統使用 Pinggy 提供外網訪問，配置如下：

```yaml
# docker compose.yml 中的配置
pinggy-tunnel:
  image: pinggy/pinggy:latest
  container_name: social-media-pinggy
  network_mode: host
  command: [
    "-p", "443",
    "-R0:localhost:8501",
    "-L4300:localhost:4300",
    "-o", "StrictHostKeyChecking=no",
    "-o", "ServerAliveInterval=30",
    "RdUOEHSfE2u@pro.pinggy.io"
  ]
```

### 訪問地址
- **本地訪問**: http://localhost:8501
- **外網訪問**: https://hlsbwbzaat.a.pinggy.link

### Tunnel 管理
```bash
# 啟動 Tunnel
./manage_system.sh start-tunnel

# 查看 Tunnel 狀態
docker compose logs pinggy-tunnel

# 重啟 Tunnel
./manage_system.sh restart-tunnel

# 停止 Tunnel
docker compose stop pinggy-tunnel
```

---

## 🔍 服務管理

### 服務狀態檢查

#### 使用管理腳本
```bash
# 完整狀態檢查（推薦）
./manage_system.sh status
```

#### 使用 Docker 指令
```bash
# 查看所有容器狀態
docker compose ps

# 查看特定服務狀態
docker compose ps streamlit-ui
docker compose ps pinggy-tunnel
```

#### 手動連線測試
```bash
# 測試 UI
curl http://localhost:8501/_stcore/health

# 測試 Orchestrator
curl http://localhost:8000/health

# 測試 Form API
curl http://localhost:8010/health

# 測試 MCP Server
curl http://localhost:10100/health
```

### 日誌管理

#### 查看即時日誌
```bash
# 所有服務日誌
docker compose logs -f

# 特定服務日誌
docker compose logs -f streamlit-ui
docker compose logs -f pinggy-tunnel
docker compose logs -f orchestrator-agent
```

#### 查看歷史日誌
```bash
# 最後 100 行日誌
docker compose logs --tail=100

# 特定時間範圍日誌
docker compose logs --since="2024-01-01T00:00:00" --until="2024-01-02T00:00:00"
```

### 資源監控

#### 容器資源使用
```bash
# 查看容器資源使用情況
docker stats

# 查看特定容器資源
docker stats social-media-ui social-media-pinggy
```

#### 系統資源監控
```bash
# 磁碟使用情況
df -h

# 記憶體使用情況
free -h

# CPU 使用情況
top
```

---

## 🛠️ 故障排除

### 常見問題

#### 1. 服務啟動失敗
```bash
# 檢查服務狀態
docker compose ps

# 查看錯誤日誌
docker compose logs [service-name]

# 重啟服務
docker compose restart [service-name]

# 重新執行啟動（安全操作）
docker compose --profile tunnel up -d --build
```

#### 0. Docker Compose 版本問題
```bash
# 如果出現 'ContainerConfig' KeyError
./fix_docker_issues.sh

# 或手動修復
docker compose --profile tunnel down
docker system prune -f
docker compose --profile tunnel up -d --build

# 升級 docker compose（如果需要）
sudo apt install docker compose-plugin
```

#### 1. 端口被佔用問題
```bash
# 檢查端口佔用
sudo netstat -tlnp | grep :4222

# 停止佔用端口的服務
sudo systemctl stop nats-server
sudo systemctl disable nats-server

# 或直接殺死進程
sudo kill [PID]

# 然後重新啟動
docker compose --profile tunnel up -d --build
```

#### 2. UI 無法訪問
```bash
# 檢查 UI 服務狀態
docker compose ps streamlit-ui

# 查看 UI 日誌
docker compose logs streamlit-ui

# 修復 UI 問題
./fix_ui.sh

# 或手動修復
docker compose stop streamlit-ui
docker compose rm -f streamlit-ui
docker compose build --no-cache streamlit-ui
docker compose up -d streamlit-ui

# 測試連線
curl http://localhost:8501/_stcore/health
```

#### 3. Tunnel 連線失敗
```bash
# 檢查 Tunnel 狀態
docker compose ps pinggy-tunnel

# 查看 Tunnel 日誌
docker compose logs pinggy-tunnel

# 重啟 Tunnel
./manage_system.sh restart-tunnel
```

#### 4. 資料庫連線問題
```bash
# 檢查 PostgreSQL 狀態
docker compose ps postgres

# 測試資料庫連線
docker compose exec postgres psql -U postgres -d social_media_db -c "SELECT 1;"

# 重啟資料庫
docker compose restart postgres
```

#### 5. 記憶體不足
```bash
# 檢查記憶體使用
free -h
docker stats

# 清理未使用的容器和映像
docker system prune -f

# 重啟系統（釋放記憶體）
./manage_system.sh restart
```

### 錯誤代碼對照

| 錯誤代碼 | 說明 | 解決方案 |
|---------|------|----------|
| Exit 125 | Docker 容器啟動失敗 | 檢查 Dockerfile 和環境變數 |
| Exit 126 | 權限問題 | 檢查檔案權限和 Docker 群組 |
| Exit 127 | 指令未找到 | 檢查 PATH 和依賴安裝 |
| Exit 1 | 一般錯誤 | 查看詳細日誌 |

---

## 🔧 維護操作

### 定期維護

#### 每日檢查
```bash
# 檢查服務狀態
./manage_system.sh status

# 檢查磁碟空間
df -h

# 檢查日誌大小
du -sh /var/lib/docker/containers/*/
```

#### 每週維護
```bash
# 清理未使用的 Docker 資源
docker system prune -f

# 備份重要數據
docker compose exec postgres pg_dump -U postgres social_media_db > backup_$(date +%Y%m%d).sql

# 更新系統
sudo apt update && sudo apt upgrade
```

#### 每月維護
```bash
# 完整系統清理
./manage_system.sh clean

# 重建所有服務
docker compose --profile tunnel up -d --build --force-recreate
```

### 備份與恢復

#### 資料備份
```bash
# 資料庫備份
docker compose exec postgres pg_dump -U postgres social_media_db > db_backup.sql

# 檔案備份
tar -czf files_backup.tar.gz storage/

# 配置備份
cp .env .env.backup
cp docker compose.yml docker compose.yml.backup
```

#### 資料恢復
```bash
# 資料庫恢復
docker compose exec -T postgres psql -U postgres social_media_db < db_backup.sql

# 檔案恢復
tar -xzf files_backup.tar.gz

# 配置恢復
cp .env.backup .env
cp docker compose.yml.backup docker compose.yml
```

### 系統升級

#### 升級流程
```bash
# 1. 備份現有系統
./manage_system.sh stop
cp -r . ../backup_$(date +%Y%m%d)

# 2. 拉取最新代碼
git pull origin main

# 3. 重建服務
docker compose --profile tunnel build --no-cache

# 4. 啟動系統
./manage_system.sh start-tunnel

# 5. 驗證升級
./manage_system.sh status
```

---

## 📞 支援與聯絡

### 技術支援
- **文檔**: 查看 `docs/` 目錄下的詳細文檔
- **日誌**: 使用 `./manage_system.sh logs` 查看系統日誌
- **狀態**: 使用 `./manage_system.sh status` 檢查服務狀態

### 常用指令速查

#### 簡化版（推薦）
```bash
# 啟動系統 + 外網
docker-compose --profile tunnel up -d --build

# 檢查狀態
docker-compose ps

# 查看日誌
docker-compose logs streamlit-ui

# 重啟服務
docker-compose restart streamlit-ui

# 停止系統
docker-compose --profile tunnel down
```

#### 管理腳本版
```bash
# 快速啟動
./manage_system.sh start-tunnel

# 檢查狀態
./manage_system.sh status

# 查看日誌
./manage_system.sh ui-logs

# 重啟服務
./manage_system.sh restart-ui

# 停止系統
./manage_system.sh stop
```

---

## 📝 更新日誌

### v1.0.0 (2024-02-08)
- ✅ 完整 Docker 化部署
- ✅ Pinggy Tunnel 整合
- ✅ 統一管理腳本
- ✅ 自動健康檢查
- ✅ 背景運行支援

---

*最後更新: 2024-02-08*
*維護者: 系統管理員*