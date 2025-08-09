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

# 一次性/冪等：套用資料庫修復/初始化腳本
if docker ps --format '{{.Names}}' | grep -q '^social-media-postgres$'; then
  echo "🛠  套用資料庫初始化/修復腳本..."
  if [ -f scripts/init-db.sql ]; then
    docker exec -i social-media-postgres psql -U postgres -d social_media_db < scripts/init-db.sql || true
  else
    echo "⚠️  找不到 scripts/init-db.sql，略過資料庫修復"
  fi
fi

# 檢查服務狀態
echo "📊 服務狀態:"
docker compose ps