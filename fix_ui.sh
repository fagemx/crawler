#!/bin/bash

# 修復 UI 容器問題

echo "🔧 修復 UI 容器..."

# 停止並刪除 UI 容器
docker-compose stop streamlit-ui
docker-compose rm -f streamlit-ui

# 刪除 UI 鏡像
docker rmi social-media-content-generator_streamlit-ui 2>/dev/null || true

# 重新構建 UI（使用 pyproject.toml）
echo "🏗️ 重新構建 UI（使用 pyproject.toml）..."
docker-compose build --no-cache streamlit-ui

# 啟動 UI
echo "🚀 啟動 UI..."
docker-compose up -d streamlit-ui

# 等待啟動
sleep 15

# 檢查狀態
echo "📊 UI 狀態:"
docker-compose ps streamlit-ui

# 檢查日誌
echo "📋 UI 日誌:"
docker-compose logs --tail=30 streamlit-ui

# 測試連線
echo "🔍 測試 UI 連線:"
sleep 5
curl -s http://localhost:8501/_stcore/health && echo "✅ UI 健康檢查通過" || echo "❌ UI 健康檢查失敗"