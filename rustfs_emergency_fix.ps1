# RustFS 緊急修復腳本 - PowerShell 版本
# 專門用於 Windows 環境快速解決 "Heal queue is full" 錯誤

param(
    [switch]$Force
)

Write-Host "[EMERGENCY] RustFS Heal Queue 緊急修復 - PowerShell 版本" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Cyan

# 檢查是否在正確的目錄
if (-not (Test-Path "docker-compose.yml")) {
    Write-Host "[ERROR] 請在專案根目錄執行此腳本" -ForegroundColor Red
    exit 1
}

# 檢查 Docker Compose
$composeCmd = ""
if (Get-Command "docker-compose" -ErrorAction SilentlyContinue) {
    $composeCmd = "docker-compose"
} elseif (Get-Command "docker" -ErrorAction SilentlyContinue) {
    try {
        docker compose version | Out-Null
        $composeCmd = "docker compose"
    } catch {
        Write-Host "[ERROR] 找不到 docker-compose 或 docker compose" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "[ERROR] 找不到 Docker" -ForegroundColor Red
    exit 1
}

Write-Host "[OK] 使用: $composeCmd" -ForegroundColor Green

# 1. 停止 RustFS 服務
Write-Host "`n[STEP 1] 停止 RustFS 服務..." -ForegroundColor Yellow
try {
    if ($composeCmd -eq "docker-compose") {
        docker-compose stop rustfs
    } else {
        docker compose stop rustfs
    }
    Write-Host "[OK] 服務已停止" -ForegroundColor Green
} catch {
    Write-Host "[WARN] 停止可能失敗，繼續執行..." -ForegroundColor Yellow
}

# 2. 強制移除容器
Write-Host "`n[STEP 2] 強制清理容器..." -ForegroundColor Yellow
try {
    if ($composeCmd -eq "docker-compose") {
        docker-compose rm -f rustfs
    } else {
        docker compose rm -f rustfs
    }
    Write-Host "[OK] 容器已清理" -ForegroundColor Green
} catch {
    Write-Host "[WARN] 容器清理可能失敗" -ForegroundColor Yellow
}

# 3. 清理本地數據
Write-Host "`n[STEP 3] 清理臨時數據..." -ForegroundColor Yellow
$tempCleanedCount = 0
$logCleanedCount = 0

# 清理 RustFS 數據目錄
$dataDir = ".\storage\rustfs"
if (Test-Path $dataDir) {
    $tempPatterns = @("*.tmp", "*.log", "*.lock", ".heal*")
    foreach ($pattern in $tempPatterns) {
        $files = Get-ChildItem -Path $dataDir -Recurse -Filter $pattern -ErrorAction SilentlyContinue
        foreach ($file in $files) {
            try {
                Remove-Item $file.FullName -Force
                $tempCleanedCount++
            } catch {
                # 忽略單個文件刪除錯誤
            }
        }
    }
    Write-Host "[OK] 清理了 $tempCleanedCount 個臨時文件" -ForegroundColor Green
} else {
    Write-Host "[INFO] RustFS 數據目錄不存在" -ForegroundColor Cyan
}

# 清理日誌目錄
$logDir = ".\storage\rustfs-logs"
if (Test-Path $logDir) {
    $logFiles = Get-ChildItem -Path $logDir -Filter "*.log" -ErrorAction SilentlyContinue
    foreach ($logFile in $logFiles) {
        try {
            Remove-Item $logFile.FullName -Force
            $logCleanedCount++
        } catch {
            # 忽略單個文件刪除錯誤
        }
    }
    Write-Host "[OK] 清理了 $logCleanedCount 個日誌文件" -ForegroundColor Green
} else {
    Write-Host "[INFO] 日誌目錄不存在" -ForegroundColor Cyan
}

# 4. 重新創建存儲目錄
Write-Host "`n[STEP 4] 重新創建存儲目錄..." -ForegroundColor Yellow
try {
    $storageDirs = @(".\storage\rustfs", ".\storage\rustfs-logs")
    foreach ($dir in $storageDirs) {
        if (-not (Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
    }
    Write-Host "[OK] 存儲目錄已準備" -ForegroundColor Green
} catch {
    Write-Host "[WARN] 目錄創建可能有問題: $_" -ForegroundColor Yellow
}

# 5. 重啟 RustFS 服務
Write-Host "`n[STEP 5] 重啟 RustFS 服務..." -ForegroundColor Yellow
try {
    if ($composeCmd -eq "docker-compose") {
        docker-compose up -d rustfs
    } else {
        docker compose up -d rustfs
    }
    Write-Host "[OK] 服務已重啟" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] 重啟失敗: $_" -ForegroundColor Red
    exit 1
}

# 6. 等待啟動
Write-Host "`n[STEP 6] 等待服務啟動..." -ForegroundColor Yellow
for ($i = 1; $i -le 3; $i++) {
    Write-Host "[WAIT] 等待中... ($i/3)" -ForegroundColor Cyan
    Start-Sleep -Seconds 5
}

# 7. 檢查狀態
Write-Host "`n[STEP 7] 檢查服務狀態..." -ForegroundColor Yellow
try {
    if ($composeCmd -eq "docker-compose") {
        $status = docker-compose ps rustfs
    } else {
        $status = docker compose ps rustfs
    }
    
    Write-Host "[STATUS] 容器狀態:" -ForegroundColor Cyan
    Write-Host $status -ForegroundColor White
    
    if ($status -match "Up") {
        Write-Host "[OK] RustFS 服務正在運行" -ForegroundColor Green
    } else {
        Write-Host "[WARN] RustFS 可能還未完全啟動" -ForegroundColor Yellow
    }
} catch {
    Write-Host "[WARN] 無法獲取狀態: $_" -ForegroundColor Yellow
}

# 8. 測試 S3 API
Write-Host "`n[STEP 8] 測試 S3 API..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:9000/" -TimeoutSec 5 -ErrorAction Stop
    Write-Host "[OK] S3 API 可以訪問 (狀態碼: $($response.StatusCode))" -ForegroundColor Green
} catch {
    if ($_.Exception.Response.StatusCode -eq 403) {
        Write-Host "[OK] S3 API 可以訪問 (403 預期響應)" -ForegroundColor Green
    } else {
        Write-Host "[WARN] S3 API 測試失敗: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

Write-Host "`n[COMPLETE] 緊急修復完成!" -ForegroundColor Green
Write-Host "`n[NEXT STEPS]" -ForegroundColor Cyan
Write-Host "1. 檢查 RustFS 容器狀態:" -ForegroundColor White
Write-Host "   $composeCmd ps rustfs" -ForegroundColor Gray
Write-Host "2. 查看 RustFS 日誌:" -ForegroundColor White
Write-Host "   $composeCmd logs rustfs" -ForegroundColor Gray
Write-Host "3. 如果問題持續，請查看完整管理工具:" -ForegroundColor White
Write-Host "   python rustfs_auto_manager.py --action health" -ForegroundColor Gray

Write-Host "`n[SUCCESS] 修復完成!" -ForegroundColor Green

