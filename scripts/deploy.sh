#!/bin/bash

# 自動化部署腳本 - 避免手動修復資料庫問題
# 使用方式: ./scripts/deploy.sh

set -e

echo "🚀 開始自動化部署..."

# 1. 確保在正確的目錄
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ 請在項目根目錄執行此腳本"
    exit 1
fi

# 2. 停止現有服務（但保留數據卷）
echo "⏹️  停止現有服務..."
docker-compose down || true

# 3. 啟動基礎設施服務
echo "🔧 啟動基礎設施服務..."
docker-compose up -d postgres redis nats rustfs

# 4. 等待服務就緒
echo "⏳ 等待基礎設施服務就緒..."
sleep 10

# 5. 確保資料庫正確設置
echo "🔍 檢查和修復資料庫..."
chmod +x scripts/ensure_database.sh
./scripts/ensure_database.sh

# 6. 啟動 MCP Server
echo "🖥️  啟動 MCP Server..."
docker-compose up -d mcp-server

# 等待 MCP Server 就緒
echo "⏳ 等待 MCP Server 就緒..."
timeout=60
while ! curl -s http://localhost:10100/health > /dev/null 2>&1; do
    echo "等待 MCP Server..."
    sleep 3
    timeout=$((timeout-1))
    if [ $timeout -le 0 ]; then
        echo "⚠️  MCP Server 啟動超時，但繼續部署..."
        break
    fi
done

# 7. 啟動所有其他服務
echo "🚀 啟動所有應用服務..."
docker-compose up -d

# 8. 檢查服務狀態
echo "📊 檢查服務狀態..."
sleep 5
docker-compose ps

# 9. 驗證關鍵服務
echo "🔍 驗證關鍵服務..."
SERVICES=("social-media-postgres" "social-media-redis" "social-media-mcp-server")

for service in "${SERVICES[@]}"; do
    if docker ps --format "table {{.Names}}" | grep -q $service; then
        echo "✅ $service 正在運行"
    else
        echo "❌ $service 未運行"
    fi
done

# 10. 最終資料庫連接測試
echo "🧪 最終資料庫連接測試..."
if docker exec social-media-postgres psql -U postgres -d social_media_db -c "SELECT 1;" > /dev/null 2>&1; then
    echo "✅ 資料庫連接正常"
else
    echo "❌ 資料庫連接失敗"
    exit 1
fi

echo ""
echo "🎉 部署完成！"
echo ""
echo "📝 服務訪問地址:"
echo "   - Streamlit UI: http://localhost:8501"
echo "   - MCP Server: http://localhost:10100"
echo "   - PostgreSQL: localhost:5432"
echo "   - Redis: localhost:6379"
echo ""
echo "📋 檢查服務狀態: docker-compose ps"
echo "📋 查看日誌: docker-compose logs -f [service-name]"