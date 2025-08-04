#!/bin/bash

# 修復 UI 容器問題 - 使用正確的映像名稱
echo "🔧 修復 UI 容器..."

# 停止並刪除 UI 容器
echo "⏹️ 停止 UI 容器..."
docker compose stop streamlit-ui
docker compose rm -f streamlit-ui

# 刪除 UI 映像（使用正確的名稱）
echo "🗑️ 刪除舊映像..."
docker rmi social-media-generator_streamlit-ui 2>/dev/null || true

# 重新構建 UI（使用 --no-cache 強制重建）
echo "🏗️ 重新構建 UI（無緩存）..."
docker compose build --no-cache streamlit-ui

# 啟動 UI
echo "🚀 啟動 UI..."
docker compose up -d streamlit-ui

# 等待啟動
echo "⏱️ 等待服務啟動..."
sleep 15

# 檢查狀態
echo "📊 UI 狀態:"
docker compose ps streamlit-ui

# 檢查日誌
echo "📋 UI 日誌:"
docker compose logs --tail=30 streamlit-ui

# 測試連線
echo "🔍 測試 UI 連線:"
sleep 5
curl -s http://localhost:8501/_stcore/health && echo "✅ UI 健康檢查通過" || echo "❌ UI 健康檢查失敗"

echo ""
echo "🌐 UI 應該在 http://localhost:8501 可用"
echo "📱 如果使用隧道，請檢查 Pinggy 連結"