
# 快速參考 - 超簡單版

## 🚀 啟動系統

### 方法1: 只要本地訪問
```bash
docker compose up -d --build
```

### 方法2: 要外網訪問（推薦）
```bash
docker compose --profile tunnel up -d --build
```

## 🌐 訪問地址
- **本地**: http://localhost:8501
- **外網**: https://hlsbwbzaat.a.pinggy.link

## 🛑 停止系統
```bash
# 停止所有服務
docker compose down

# 停止包含外網訪問
docker compose --profile tunnel down
```

## � h常用指令

| 需求 | 指令 |
|------|------|
| 啟動系統 | `docker compose up -d --build` |
| 啟動+外網 | `docker compose --profile tunnel up -d --build` |
| 停止服務 | `docker compose down` |
| 查看狀態 | `docker compose ps` |
| 查看日誌 | `docker compose logs` |
| 重啟 UI | `docker compose restart streamlit-ui` |
| 重啟 Tunnel | `docker compose restart pinggy-tunnel` |

## 🔄 重複執行安全性
```bash
# 可以重複執行，不會造成端口衝突
docker compose --profile tunnel up -d --build

# 強制重新創建所有容器
docker compose --profile tunnel up -d --build --force-recreate

# 清理後重新開始
docker compose --profile tunnel down
docker compose --profile tunnel up -d --build
```

## 🆘 問題解決

| 問題 | 解決方案 |
|------|----------|
| UI 啟動失敗 | `./fix_ui.sh` |
| Docker 版本問題 | `./fix_docker_issues.sh` |
| 端口被佔用 | `sudo systemctl stop nats-server` |
| 記憶體不足 | `docker system prune -f` |
| 重新構建 | `docker compose build --no-cache` |

## 📋 服務端口

| 服務 | 端口 | 用途 |
|------|------|------|
| UI | 8501 | Web 介面 |
| Orchestrator | 8000 | 主控制器 |
| Form API | 8010 | 表單處理 |
| MCP Server | 10100 | Agent 管理 |

## 🔍 快速檢查

```bash
# 檢查 UI 是否正常
curl http://localhost:8501/_stcore/health

# 檢查服務狀態
docker compose ps

# 查看 UI 日誌
docker compose logs streamlit-ui
```

## 📝 重要檔案

- `docker-compose.yml` - 所有服務配置
- `.env` - 環境變數設定
- `fix_ui.sh` - 修復 UI 問題

---

**就這麼簡單！有問題就重啟：`docker compose restart [service-name]`**
