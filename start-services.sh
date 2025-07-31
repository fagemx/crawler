#!/bin/bash
# Zeabur 多服務啟動腳本

# 設置環境變數
export PYTHONPATH=/app
export PYTHONUNBUFFERED=1

# 函數：啟動服務並記錄 PID
start_service() {
    local service_name=$1
    local command=$2
    echo "🚀 Starting $service_name..."
    nohup $command > /var/log/$service_name.log 2>&1 &
    echo $! > /var/run/$service_name.pid
    echo "✅ $service_name started with PID $(cat /var/run/$service_name.pid)"
}

# 等待基礎設施服務就緒的函數
wait_for_service() {
    local host=$1
    local port=$2
    local service_name=$3
    echo "⏳ Waiting for $service_name at $host:$port..."
    while ! nc -z $host $port; do
        sleep 1
    done
    echo "✅ $service_name is ready!"
}

# 創建日誌和 PID 目錄
mkdir -p /var/log /var/run

# 等待外部依賴 (如果在 Zeabur 環境中)
if [ ! -z "$DATABASE_URL" ]; then
    echo "🔗 External database detected: $DATABASE_URL"
fi

if [ ! -z "$REDIS_URL" ]; then
    echo "🔗 External Redis detected: $REDIS_URL"  
fi

# 啟動核心服務
echo "🎯 Starting core services..."

# 1. 啟動 Orchestrator (協調器)
start_service "orchestrator" "uvicorn agents.orchestrator.main:app --host 0.0.0.0 --port 8000"

# 等待 Orchestrator 就緒
sleep 5

# 2. 啟動關鍵 Agent (可選)
if [ "$ENABLE_CRAWLER" = "true" ]; then
    start_service "playwright-crawler" "uvicorn agents.playwright_crawler.main:app --host 0.0.0.0 --port 8006"
fi

if [ "$ENABLE_VISION" = "true" ]; then
    start_service "vision" "uvicorn agents.vision.main:app --host 0.0.0.0 --port 8005"
fi

# 3. 啟動主 UI (前台運行)
echo "🎨 Starting main UI..."
exec streamlit run ui/streamlit_app.py --server.port=8501 --server.address=0.0.0.0