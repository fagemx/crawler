#!/bin/bash

# 啟動完整系統 + Pinggy Tunnel（背景運行）
# 這樣就不需要保持 SSH 視窗開啟

set -e

echo "🚀 啟動完整系統 + Pinggy Tunnel"
echo "================================="

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 檢查 Docker 環境
check_docker() {
    echo -e "${BLUE}🔍 檢查 Docker 環境...${NC}"
    
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}❌ Docker 未安裝${NC}"
        exit 1
    fi
    
    if ! command -v docker compose/null || ! docker compose version &> /dev/null 2>&1; then
        echo -e "${RED}❌ docker compose 未安裝${NC}"
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        echo -e "${RED}❌ Docker daemon 未運行${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✅ Docker 環境檢查通過${NC}"
}

# 停止現有服務
stop_existing() {
    echo -e "${YELLOW}🛑 停止現有服務...${NC}"
    docker compose --profile tunnel down --remove-orphans
}

# 啟動核心服務
start_core_services() {
    echo -e "${BLUE}🏗️  啟動核心服務...${NC}"
    
    # 基礎設施
    echo -e "${BLUE}📊 啟動基礎設施...${NC}"
    docker compose up -d postgres redis rustfs nats
    
    echo -e "${BLUE}⏳ 等待基礎設施就緒...${NC}"
    sleep 10
    
    # MCP Server
    echo -e "${BLUE}🤖 啟動 MCP Server...${NC}"
    docker compose up -d mcp-server
    sleep 5
    
    # Agent 服務
    echo -e "${BLUE}🎯 啟動 Agent 服務...${NC}"
    docker compose up -d orchestrator-agent clarification-agent content-writer-agent form-api vision-agent playwright-crawler-agent
    sleep 10
    
    # UI 服務
    echo -e "${BLUE}🎨 啟動 Streamlit UI...${NC}"
    docker compose up -d streamlit-ui
    sleep 5
}

# 啟動 Pinggy Tunnel
start_tunnel() {
    echo -e "${BLUE}🌐 啟動 Pinggy Tunnel...${NC}"
    docker compose --profile tunnel up -d pinggy-tunnel
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Pinggy Tunnel 啟動成功${NC}"
    else
        echo -e "${RED}❌ Pinggy Tunnel 啟動失敗${NC}"
        echo -e "${YELLOW}📋 檢查日誌：docker compose logs pinggy-tunnel${NC}"
        exit 1
    fi
}

# 等待服務就緒並顯示狀態
wait_and_show_status() {
    echo -e "${BLUE}⏳ 等待所有服務就緒...${NC}"
    sleep 15
    
    echo -e "${GREEN}🎉 系統啟動完成！${NC}"
    echo -e "${GREEN}================================${NC}"
    echo -e "${GREEN}🌐 本地訪問: http://localhost:8501${NC}"
    echo -e "${GREEN}🌍 外網訪問: https://supacool.xyz${NC}"
    echo -e "${GREEN}🤖 Orchestrator: http://localhost:8000${NC}"
    echo -e "${GREEN}📝 Form API: http://localhost:8010${NC}"
    echo -e "${GREEN}🔍 MCP Server: http://localhost:10100${NC}"
    echo -e "${GREEN}================================${NC}"
    
    echo -e "${BLUE}📊 服務狀態：${NC}"
    docker compose --profile tunnel ps
    
    echo -e "${YELLOW}💡 提示：${NC}"
    echo -e "${YELLOW}   - 查看 Tunnel 日誌：docker compose logs -f pinggy-tunnel${NC}"
    echo -e "${YELLOW}   - 查看 UI 日誌：docker compose logs -f streamlit-ui${NC}"
    echo -e "${YELLOW}   - 停止所有服務：docker compose --profile tunnel down${NC}"
    echo -e "${YELLOW}   - 重啟 Tunnel：docker compose restart pinggy-tunnel${NC}"
}

# 檢查 Tunnel 連線狀態
check_tunnel_status() {
    echo -e "${BLUE}🔍 檢查 Tunnel 連線狀態...${NC}"
    sleep 5
    
    # 顯示 Pinggy 日誌的最後幾行
    echo -e "${BLUE}📋 Pinggy Tunnel 日誌：${NC}"
    docker compose logs --tail=10 pinggy-tunnel
    
    echo -e "${YELLOW}💡 如果看到 'tunnel established' 或類似訊息，表示連線成功${NC}"
}

# 主執行流程
main() {
    check_docker
    stop_existing
    start_core_services
    start_tunnel
    wait_and_show_status
    check_tunnel_status
}

# 處理中斷信號
trap 'echo -e "\n${YELLOW}⚠️  收到中斷信號，正在停止服務...${NC}"; docker compose --profile tunnel down; exit 1' INT TERM

# 執行主流程
main

echo -e "${GREEN}🚀 系統已完全啟動！${NC}"
echo -e "${GREEN}✨ 現在你可以關閉 SSH 視窗，服務會在背景繼續運行${NC}"
echo -e "${GREEN}🌍 外網訪問：https://hlsbwbzaat.a.pinggy.link${NC}"