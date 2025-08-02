# 社交媒體內容生成器 - 部署說明

## 🎯 快速部署

### 一鍵啟動
```bash
# 1. 設置權限
bash setup_permissions.sh

# 2. 啟動完整系統
./manage_system.sh start-tunnel

# 3. 訪問服務
# 本地: http://localhost:8501
# 外網: https://hlsbwbzaat.a.pinggy.link
```

## 📁 文檔結構

```
├── docs/
│   └── DEPLOYMENT_GUIDE.md     # 詳細部署指南
├── OPERATIONS_MANUAL.md        # 操作手冊（快速參考）
├── README_DEPLOYMENT.md        # 本文件（部署概述）
├── manage_system.sh            # 主要管理腳本
├── docker-compose.yml          # Docker 服務配置
└── .env                        # 環境變數配置
```

## 🛠️ 管理腳本

### 主要腳本
- `manage_system.sh` - 統一管理腳本（推薦使用）
- `start_with_tunnel.sh` - 啟動完整系統 + Tunnel
- `start_docker_ui.sh` - 啟動完整系統
- `start_ui_only.sh` - 只啟動 UI
- `start_tunnel_only.sh` - 只啟動 Tunnel

### 使用方式
```bash
# 查看幫助
./manage_system.sh help

# 常用指令
./manage_system.sh start-tunnel  # 啟動系統+外網
./manage_system.sh status        # 檢查狀態
./manage_system.sh stop          # 停止服務
```

## 🌐 訪問地址

| 服務 | 本地地址 | 外網地址 |
|------|----------|----------|
| UI 介面 | http://localhost:8501 | https://hlsbwbzaat.a.pinggy.link |
| API 文檔 | http://localhost:8000/docs | - |
| 資料庫管理 | http://localhost:5050 | - |

## 📋 系統架構

```
┌─────────────────┐    ┌─────────────────┐
│   Pinggy Tunnel │────│  Streamlit UI   │
│     (外網訪問)    │    │     (8501)      │
└─────────────────┘    └─────────────────┘
                              │
                    ┌─────────────────┐
                    │  Orchestrator   │
                    │     (8000)      │
                    └─────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│Clarification│    │Content Writer│    │Vision Agent │
│   (8004)    │    │   (8003)    │    │   (8005)    │
└─────────────┘    └─────────────┘    └─────────────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │
                    ┌─────────────────┐
                    │   MCP Server    │
                    │    (10100)      │
                    └─────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ PostgreSQL  │    │    Redis    │    │   RustFS    │
│   (5432)    │    │   (6379)    │    │   (9000)    │
└─────────────┘    └─────────────┘    └─────────────┘
```

## 🔧 環境要求

- **Docker**: 20.10+
- **Docker Compose**: 1.29+
- **記憶體**: 8GB+
- **硬碟**: 20GB+
- **網路**: 穩定網際網路連線

## 📞 支援資源

- **詳細文檔**: `docs/DEPLOYMENT_GUIDE.md`
- **操作手冊**: `OPERATIONS_MANUAL.md`
- **配置檔案**: `docker-compose.yml`
- **環境變數**: `.env`

## 🆘 緊急聯絡

如遇到問題，請按以下順序處理：

1. 檢查服務狀態：`./manage_system.sh status`
2. 查看錯誤日誌：`./manage_system.sh logs`
3. 嘗試重啟服務：`./manage_system.sh restart`
4. 參考故障排除：`docs/DEPLOYMENT_GUIDE.md#故障排除`

---

*更多詳細資訊請參考 `docs/DEPLOYMENT_GUIDE.md`*