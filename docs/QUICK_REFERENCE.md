# 快速參考卡

## 🚀 一鍵啟動
```bash
bash setup_permissions.sh && ./manage_system.sh start-tunnel
```

## 📊 狀態檢查
```bash
./manage_system.sh status
```

## 🌐 訪問地址
- **本地**: http://localhost:8501
- **外網**: https://hlsbwbzaat.a.pinggy.link

## 🔧 常用指令

| 操作 | 指令 |
|------|------|
| 啟動系統+外網 | `./manage_system.sh start-tunnel` |
| 啟動系統 | `./manage_system.sh start` |
| 停止服務 | `./manage_system.sh stop` |
| 重啟系統 | `./manage_system.sh restart` |
| 檢查狀態 | `./manage_system.sh status` |
| 查看日誌 | `./manage_system.sh logs` |
| UI 日誌 | `./manage_system.sh ui-logs` |
| Tunnel 日誌 | `./manage_system.sh tunnel-logs` |
| 重啟 UI | `./manage_system.sh restart-ui` |
| 重啟 Tunnel | `./manage_system.sh restart-tunnel` |
| 清理系統 | `./manage_system.sh clean` |

## 🆘 故障排除

| 問題 | 解決方案 |
|------|----------|
| 服務啟動失敗 | `./manage_system.sh restart` |
| UI 無法訪問 | `./manage_system.sh restart-ui` |
| 外網無法訪問 | `./manage_system.sh restart-tunnel` |
| 記憶體不足 | `docker system prune -f` |

## 📋 服務端口

| 服務 | 端口 |
|------|------|
| UI | 8501 |
| Orchestrator | 8000 |
| Form API | 8010 |
| MCP Server | 10100 |
| PostgreSQL | 5432 |
| Redis | 6379 |

## 🔍 健康檢查

```bash
# UI 健康檢查
curl http://localhost:8501/_stcore/health

# API 健康檢查
curl http://localhost:8000/health
curl http://localhost:8010/health
curl http://localhost:10100/health
```

## 📁 重要檔案

- `docker-compose.yml` - 服務配置
- `.env` - 環境變數
- `manage_system.sh` - 管理腳本
- `docs/DEPLOYMENT_GUIDE.md` - 詳細文檔

---

*列印此頁面作為快速參考*