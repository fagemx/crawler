#!/bin/bash

# Docker 環境下啟動完整系統（包含 UI）
# 替代手動運行 restart_streamlit.py

set -e

echo "🚀 啟動 Docker 環境（包含 Streamlit UI）"
echo "=========================================="

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
    
    if ! command -v docker compose &> /dev/null; then
        echo -e "${RED}❌ docker compose 未安裝${NC}"
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        echo -e "${RED}❌ Docker daemon 未運行${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✅ Docker 環境檢查通過${NC}"
}

# 停止現有服務（如果有的話）
stop_existing() {
    echo -e "${YELLOW}🛑 停止現有服務...${NC}"
    docker compose down --remove-orphans
}

# 構建和啟動核心服務
start_core_services() {
    echo -e "${BLUE}🏗️  構建和啟動核心服務...${NC}"
    
    # 按順序啟動服務
    echo -e "${BLUE}📊 啟動基礎設施服務...${NC}"
    docker compose up -d postgres redis rustfs nats
    
    echo -e "${BLUE}⏳ 等待基礎設施就緒...${NC}"
    sleep 10
    
    echo -e "${BLUE}🤖 啟動 MCP Server...${NC}"
    docker compose up -d mcp-server
    
    echo -e "${BLUE}⏳ 等待 MCP Server 就緒...${NC}"
    sleep 5
    
    echo -e "${BLUE}🎯 啟動 Agent 服務...${NC}"
    docker compose up -d orchestrator-agent clarification-agent content-writer-agent form-api vision-agent playwright-crawler-agent
    
    echo -e "${BLUE}⏳ 等待 Agent 服務就緒...${NC}"
    sleep 10
}

# 套用資料庫初始化/修復（冪等）
apply_db_init() {
    echo -e "${BLUE}🛠  套用資料庫初始化/修復腳本...${NC}"
    if [ -f scripts/init-db.sql ]; then
        docker compose exec -T postgres psql -U postgres -d social_media_db < scripts/init-db.sql || true
    else
        echo -e "${YELLOW}⚠️  找不到 scripts/init-db.sql，略過${NC}"
    fi]
}

# 啟動 UI 服務
start_ui() {
    echo -e "${BLUE}🎨 構建和啟動 Streamlit UI...${NC}"
    docker compose up -d streamlit-ui
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ UI 服務啟動成功${NC}"
    else
        echo -e "${RED}❌ UI 服務啟動失敗${NC}"
        echo -e "${YELLOW}📋 檢查日誌：docker compose logs streamlit-ui${NC}"
        exit 1
    fi
}

# 等待服務就緒並顯示狀態
wait_and_show_status() {
    echo -e "${BLUE}⏳ 等待所有服務就緒...${NC}"
    sleep 15
    
    echo -e "${GREEN}🎉 系統啟動完成！${NC}"
    echo -e "${GREEN}================================${NC}"
    echo -e "${GREEN}🌐 Streamlit UI: http://localhost:8501${NC}"
    echo -e "${GREEN}🤖 Orchestrator: http://localhost:8000${NC}"
    echo -e "${GREEN}📝 Form API: http://localhost:8010${NC}"
    echo -e "${GREEN}🔍 MCP Server: http://localhost:10100${NC}"
    echo -e "${GREEN}================================${NC}"
    
    echo -e "${BLUE}📊 服務狀態：${NC}"
    docker compose ps
    
    echo -e "${YELLOW}💡 提示：${NC}"
    echo -e "${YELLOW}   - 查看日誌：docker compose logs -f [service-name]${NC}"
    echo -e "${YELLOW}   - 停止服務：docker compose down${NC}"
    echo -e "${YELLOW}   - 重啟 UI：docker compose restart streamlit-ui${NC}"
}

# 主執行流程
main() {
    check_docker
    stop_existing
    start_core_services
    apply_db_init
    start_ui
    wait_and_show_status
}

# 處理中斷信號
trap 'echo -e "\n${YELLOW}⚠️  收到中斷信號，正在停止服務...${NC}"; docker compose down; exit 1' INT TERM

# 執行主流程
main

echo -e "${GREEN}🚀 系統已完全啟動！現在你可以訪問 http://localhost:8501 使用 UI${NC}"