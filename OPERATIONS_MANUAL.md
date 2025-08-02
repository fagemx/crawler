# 操作手冊 - 快速參考

## 🚀 一鍵啟動

```bash
# 設置權限（只需執行一次）
bash setup_permissions.sh

# 啟動完整系統 + 外網訪問
./manage_system.sh start-tunnel
```

## 📊 服務狀態檢查

```bash
# 檢查所有服務狀態
./manage_system.sh status

# 訪問地址
# 本地: http://localhost:8501
# 外網: https://hlsbwbzaat.a.pinggy.link
```

## 🔧 常用管理指令

### 服務控制
```bash
./manage_system.sh start          # 啟動系統（不含外網）
./manage_system.sh start-tunnel   # 啟動系統 + 外網訪問
./manage_system.sh stop           # 停止所有服務
./manage_system.sh restart        # 重啟系統
```

### 日誌查看
```bash
./manage_system.sh logs           # 所有服務日誌
./manage_system.sh ui-logs        # UI 日誌
./manage_system.sh tunnel-logs    # Tunnel 日誌
```

### 單獨服務管理
```bash
./manage_system.sh restart-ui     # 重啟 UI
./manage_system.sh restart-tunnel # 重啟 Tunnel
```

## 🆘 緊急處理

### 服務異常
```bash
# 1. 檢查狀態
./manage_system.sh status

# 2. 查看日誌
./manage_system.sh logs

# 3. 重啟服務
./manage_system.sh restart
```

### UI 無法訪問
```bash
# 重啟 UI
./manage_system.sh restart-ui

# 檢查 UI 日誌
./manage_system.sh ui-logs
```

### 外網無法訪問
```bash
# 重啟 Tunnel
./manage_system.sh restart-tunnel

# 檢查 Tunnel 日誌
./manage_system.sh tunnel-logs
```

## 📋 服務端口對照

| 服務 | 端口 | 用途 |
|------|------|------|
| Streamlit UI | 8501 | Web 用戶介面 |
| Orchestrator | 8000 | 總協調器 |
| Form API | 8010 | 表單處理 |
| MCP Server | 10100 | Agent 註冊中心 |
| Clarification | 8004 | 澄清問卷 |
| Content Writer | 8003 | 內容生成 |
| Vision Agent | 8005 | 圖像處理 |
| Playwright Crawler | 8006 | 網頁爬蟲 |
| PostgreSQL | 5432 | 資料庫 |
| Redis | 6379 | 快取 |
| RustFS | 9000 | 對象存儲 |
| NATS | 4222 | 訊息佇列 |

## 🔍 故障排除速查

| 問題 | 檢查指令 | 解決方案 |
|------|----------|----------|
| 服務啟動失敗 | `./manage_system.sh status` | `./manage_system.sh restart` |
| UI 無法訪問 | `curl localhost:8501/_stcore/health` | `./manage_system.sh restart-ui` |
| 外網無法訪問 | `./manage_system.sh tunnel-logs` | `./manage_system.sh restart-tunnel` |
| 記憶體不足 | `docker stats` | `docker system prune -f` |
| 磁碟空間不足 | `df -h` | `./manage_system.sh clean` |

## 📞 交接清單

### 必要資訊
- [ ] 伺服器 IP 和 SSH 憑證
- [ ] `.env` 檔案中的 API Keys
- [ ] Pinggy 帳號和 Token
- [ ] 資料庫備份位置

### 必要檔案
- [ ] `docker-compose.yml` - 服務配置
- [ ] `.env` - 環境變數
- [ ] `manage_system.sh` - 管理腳本
- [ ] `docs/DEPLOYMENT_GUIDE.md` - 詳細文檔

### 驗證步驟
- [ ] 執行 `./manage_system.sh start-tunnel`
- [ ] 檢查 `./manage_system.sh status`
- [ ] 訪問 http://localhost:8501
- [ ] 訪問 https://hlsbwbzaat.a.pinggy.link

---

*快速參考 - 詳細說明請參考 `docs/DEPLOYMENT_GUIDE.md`*