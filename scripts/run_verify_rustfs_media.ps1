# 設定到專案根目錄
Set-Location $PSScriptRoot\..

# 在容器內執行驗證腳本（mcp-server 擁有依賴環境與網路）
docker compose exec -T mcp-server python scripts/verify_rustfs_media.py --batch-size 1000

if ($LASTEXITCODE -ne 0) {
  Write-Host "verify_rustfs_media 執行失敗，請檢查容器日誌" -ForegroundColor Red
  exit 1
}

Write-Host "verify_rustfs_media 執行完成" -ForegroundColor Green
