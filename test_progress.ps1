# 測試背景進度追蹤的 PowerShell 腳本
# 適用於 Windows 環境

Write-Host "🧪 背景執行和進度追蹤測試" -ForegroundColor Green
Write-Host "=" * 40

# 檢查 Python 環境
try {
    $pythonVersion = python --version 2>&1
    Write-Host "🐍 Python 版本: $pythonVersion" -ForegroundColor Blue
} catch {
    Write-Host "❌ Python 未安裝或不在 PATH 中" -ForegroundColor Red
    exit 1
}

# 檢查 Docker 環境
try {
    $dockerVersion = docker --version 2>&1
    Write-Host "🐳 Docker 版本: $dockerVersion" -ForegroundColor Blue
} catch {
    Write-Host "❌ Docker 未安裝或不在 PATH 中" -ForegroundColor Red
}

Write-Host ""

# 檢查 Redis 是否運行
Write-Host "🔍 檢查 Redis 服務..." -ForegroundColor Yellow
try {
    $redisStatus = docker ps --filter "name=social-media-redis" --format "table {{.Names}}\t{{.Status}}" 2>&1
    if ($redisStatus -match "social-media-redis") {
        Write-Host "✅ Redis 容器正在運行" -ForegroundColor Green
    } else {
        Write-Host "⚠️ Redis 容器未運行，嘗試啟動..." -ForegroundColor Yellow
        docker-compose up -d redis
        Start-Sleep -Seconds 3
    }
} catch {
    Write-Host "❌ 無法檢查 Docker 容器狀態" -ForegroundColor Red
}

Write-Host ""

# 執行測試
Write-Host "🚀 執行進度追蹤測試..." -ForegroundColor Green
python test_background_progress.py

Write-Host ""
Write-Host "📖 使用說明:" -ForegroundColor Cyan
Write-Host "1. 監控特定任務: python monitor_progress.py <task_id>" -ForegroundColor White
Write-Host "2. 列出所有任務: python monitor_progress.py --list" -ForegroundColor White
Write-Host "3. 啟動爬蟲服務: docker-compose up -d playwright-crawler-agent" -ForegroundColor White
Write-Host "4. 查看爬蟲日誌: docker-compose logs -f playwright-crawler-agent" -ForegroundColor White