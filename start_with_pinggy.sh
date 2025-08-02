#!/bin/bash

# 啟動系統 + Pinggy Tunnel

echo "🚀 啟動系統 + 外網訪問..."

# 停止可能衝突的服務
sudo systemctl stop nats-server 2>/dev/null || true
sudo systemctl stop postgresql 2>/dev/null || true
sudo systemctl stop redis-server 2>/dev/null || true

# 停止現有 Docker 服務
docker compose --profile tunnel down 2>/dev/null || true

# 啟動所有服務 + Tunnel
docker compose --profile tunnel up -d --build

echo "✅ 系統啟動完成！"
echo "🌐 本地訪問: http://localhost:8501"
echo "🌍 外網訪問: https://hlsbwbzaat.a.pinggy.link"

# 等待服務啟動
sleep 15

# 檢查服務狀態
echo "📊 服務狀態:"
docker compose --profile tunnel ps

echo ""
echo "📋 查看 Tunnel 日誌:"
docker compose logs --tail=10 pinggy-tunnel