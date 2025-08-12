先說重點：`docker compose up -d` 本身就是「啟動後即在背景執行」，命令結束後就算關掉視窗，容器也會繼續跑。通常不需要用 Job。

如果你已經用 Job 啟動了，看不出有沒有啟動，請用以下指令確認。

### 檢查 PowerShell Job 狀態
```powershell
# 看 Job 狀態（Running/Completed/Failed）
Get-Job -Name DockerTunnel | Format-List Id, Name, State, HasMoreData

# 讀取一次 Job 輸出（保留輸出以便之後再看）
Receive-Job -Name DockerTunnel -Keep

# 如果要移除 Job（容器不會被停止，因為已經 -d）
Remove-Job -Name DockerTunnel
```

### 直接確認容器是否在跑（重點）
在你的 compose 專案目錄執行：
```powershell
# 顯示本專案（含 profile=tunnel）的容器
docker compose --profile tunnel ps

# 顯示所有容器（快速看是否有 pinggy/streamlit/mcp-server 等）
docker ps

# 看某服務日誌（例如 pinggy）
docker logs --tail 50 social-media-pinggy
```

### 更穩定的背景啟動（可替代 Job）
```powershell
# 用 Start-Process 背景啟動（不依賴 Job，執行完即返回）
Start-Process -FilePath "docker" `
  -ArgumentList "compose","--profile","tunnel","up","-d" `
  -WorkingDirectory "C:\ai_station\crawler" `
  -NoNewWindow

# 啟動後檢查
docker compose --profile tunnel ps
```

### 一行帶檢查
```powershell
Start-Process -FilePath "docker" -ArgumentList "compose","--profile","tunnel","up","-d" -WorkingDirectory "C:\ai_station\crawler" -NoNewWindow; Start-Sleep 3; docker compose --profile tunnel ps
```

- 若 `docker compose --profile tunnel ps` 有列出服務且 STATUS 為 `Up`，表示已啟動成功。
- 如需停止：`docker compose --profile tunnel down`

- 如果 Job 顯示 Failed，多半是工作目錄不對或 `docker` 沒在 PATH；用上面 `Start-Process -WorkingDirectory ...` 可解決。

- 你用的是 `C:\ai_station\crawler`，記得所有 compose 指令都在該目錄執行，或用 `-f` 指定檔案。