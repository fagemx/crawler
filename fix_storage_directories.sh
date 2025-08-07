#!/bin/bash

# 修復容器內存儲目錄結構的腳本

echo "🔧 修復容器內存儲目錄結構..."

# 在容器內創建缺失的目錄並設置權限
docker exec social-media-ui mkdir -p /app/storage/temp_progress
docker exec social-media-ui mkdir -p /app/storage/analysis_results  
docker exec social-media-ui mkdir -p /app/storage/writer_projects
docker exec social-media-ui mkdir -p /app/storage/crawler_results
docker exec social-media-ui mkdir -p /app/storage/rustfs-logs

# 設置正確的權限
docker exec social-media-ui chmod -R 755 /app/storage

echo "✅ 目錄修復完成！"

# 檢查修復結果
echo "📁 檢查目錄結構："
docker exec social-media-ui ls -la /app/storage/

echo "🔄 重啟容器以應用修復..."
docker restart social-media-ui

echo "⏳ 等待容器重啟..."
sleep 10

echo "✨ 修復完成！現在可以測試分頁功能了"
