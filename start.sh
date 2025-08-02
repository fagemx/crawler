#!/bin/bash

# 超簡單啟動腳本 - 一鍵啟動所有服務

echo "🚀 啟動系統..."

# 停止可能衝突的服務
sudo systemctl stop nats-server 2>/dev/null || true
sudo systemctl stop postgresql 2>/dev/null || true
sudo systemctl stop redis-server 2>/dev/null || true

# 停止現有 Docker 服務
docker compose down 2>/dev/null || true

# 啟動所有服務
docker compose up -d --build

echo "✅ 系統啟動完成！"
echo "🌐 訪問: http://localhost:8501"

# 等待服務啟動
sleep 10

# 檢查服務狀態
echo "📊 服務狀態:"
docker compose ps