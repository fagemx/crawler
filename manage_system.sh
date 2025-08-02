#!/bin/bash

# 系統管理腳本 - 統一管理所有服務
# 替代手動操作，提供簡單的管理介面

set -e

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 顯示幫助資訊
show_help() {
    echo -e "${CYAN}🛠️  系統管理腳本${NC}"
    echo -e "${CYAN}==================${NC}"
    echo ""
    echo -e "${GREEN}使用方法：${NC}"
    echo -e "  ./manage_system.sh [command]"
    echo ""
    echo -e "${GREEN}可用指令：${NC}"
    echo -e "  ${YELLOW}start${NC}        - 啟動完整系統（不含 Tunnel）"
    echo -e "  ${YELLOW}start-tunnel${NC} - 啟動完整系統 + Pinggy Tunnel"
    echo -e "  ${YELLOW}stop${NC}         - 停止所有服務"
    echo -e "  ${YELLOW}restart${NC}      - 重啟所有服務"
    echo -e "  ${YELLOW}status${NC}       - 查看服務狀態"
    echo -e "  ${YELLOW}logs${NC}         - 查看所有服務日誌"
    echo -e "  ${YELLOW}ui-logs${NC}      - 查看 UI 日誌"
    echo -e "  ${YELLOW}tunnel-logs${NC}  - 查看 Tunnel 日誌"
    echo -e "  ${YELLOW}restart-ui${NC}   - 只重啟 UI 服務"
    echo -e "  ${YELLOW}restart-tunnel${NC} - 只重啟 Tunnel 服務"
    echo -e "  ${YELLOW}clean${NC}        - 清理所有容器和數據"
    echo ""
    echo -e "${GREEN}範例：${NC}"
    echo -e "  ./manage_system.sh start-tunnel  # 啟動系統並開啟外網訪問"
    echo -e "  ./manage_system.sh status        # 查看服務狀態"
    echo -e "  ./manage_system.sh ui-logs       # 查看 UI 日誌"
}

# 啟動完整系統（不含 Tunnel）
start_system() {
    echo -e "${BLUE}🚀 啟動完整系統...${NC}"
    
    docker-compose down --remove-orphans
    
    echo -e "${BLUE}📊 啟動基礎設施...${NC}"
    docker-compose up -d postgres redis rustfs nats
    sleep 10
    
    echo -e "${BLUE}🤖 啟動 MCP Server...${NC}"
    docker-compose up -d mcp-server
    sleep 5
    
    echo -e "${BLUE}🎯 啟動 Agent 服務...${NC}"
    docker-compose up -d orchestrator-agent clarification-agent content-writer-agent form-api vision-agent playwright-crawler-agent
    sleep 10
    
    echo -e "${BLUE}🎨 啟動 UI...${NC}"
    docker-compose up -d streamlit-ui
    
    echo -e "${GREEN}✅ 系統啟動完成！${NC}"
    echo -e "${GREEN}🌐 本地訪問: http://localhost:8501${NC}"
}

# 啟動完整系統 + Tunnel
start_with_tunnel() {
    echo -e "${BLUE}🚀 啟動完整系統 + Tunnel...${NC}"
    
    start_system
    sleep 5
    
    echo -e "${BLUE}🌐 啟動 Pinggy Tunnel...${NC}"
    docker-compose --profile tunnel up -d pinggy-tunnel
    
    echo -e "${GREEN}✅ 系統 + Tunnel 啟動完成！${NC}"
    echo -e "${GREEN}🌐 本地訪問: http://localhost:8501${NC}"
    echo -e "${GREEN}🌍 外網訪問: https://hlsbwbzaat.a.pinggy.link${NC}"
}

# 停止所有服務
stop_system() {
    echo -e "${YELLOW}🛑 停止所有服務...${NC}"
    docker-compose --profile tunnel down --remove-orphans
    echo -e "${GREEN}✅ 所有服務已停止${NC}"
}

# 重啟系統
restart_system() {
    echo -e "${BLUE}🔄 重啟系統...${NC}"
    stop_system
    sleep 2
    start_system
}

# 查看服務狀態
show_status() {
    echo -e "${BLUE}📊 服務狀態：${NC}"
    docker-compose --profile tunnel ps
    
    echo -e "\n${BLUE}🌐 連線測試：${NC}"
    
    # 測試本地 UI
    if curl -s http://localhost:8501/_stcore/health > /dev/null 2>&1; then
        echo -e "${GREEN}✅ UI (8501) 可訪問${NC}"
    else
        echo -e "${RED}❌ UI (8501) 無法訪問${NC}"
    fi
    
    # 測試其他服務
    services=("8000:Orchestrator" "8010:Form API" "10100:MCP Server")
    for service in "${services[@]}"; do
        port=$(echo $service | cut -d: -f1)
        name=$(echo $service | cut -d: -f2)
        
        if curl -s http://localhost:$port/health > /dev/null 2>&1; then
            echo -e "${GREEN}✅ $name ($port) 可訪問${NC}"
        else
            echo -e "${RED}❌ $name ($port) 無法訪問${NC}"
        fi
    done
}

# 查看日誌
show_logs() {
    echo -e "${BLUE}📋 顯示所有服務日誌（最後 50 行）：${NC}"
    docker-compose --profile tunnel logs --tail=50
}

# 查看 UI 日誌
show_ui_logs() {
    echo -e "${BLUE}📋 Streamlit UI 日誌：${NC}"
    docker-compose logs -f streamlit-ui
}

# 查看 Tunnel 日誌
show_tunnel_logs() {
    echo -e "${BLUE}📋 Pinggy Tunnel 日誌：${NC}"
    docker-compose logs -f pinggy-tunnel
}

# 重啟 UI
restart_ui() {
    echo -e "${BLUE}🔄 重啟 UI 服務...${NC}"
    docker-compose restart streamlit-ui
    echo -e "${GREEN}✅ UI 重啟完成${NC}"
}

# 重啟 Tunnel
restart_tunnel() {
    echo -e "${BLUE}🔄 重啟 Tunnel 服務...${NC}"
    docker-compose restart pinggy-tunnel
    echo -e "${GREEN}✅ Tunnel 重啟完成${NC}"
}

# 清理系統
clean_system() {
    echo -e "${RED}⚠️  這將刪除所有容器和數據！${NC}"
    read -p "確定要繼續嗎？(y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}🧹 清理系統...${NC}"
        docker-compose --profile tunnel down -v --remove-orphans
        docker system prune -f
        echo -e "${GREEN}✅ 系統清理完成${NC}"
    else
        echo -e "${BLUE}取消清理操作${NC}"
    fi
}

# 主邏輯
case "${1:-help}" in
    "start")
        start_system
        ;;
    "start-tunnel")
        start_with_tunnel
        ;;
    "stop")
        stop_system
        ;;
    "restart")
        restart_system
        ;;
    "status")
        show_status
        ;;
    "logs")
        show_logs
        ;;
    "ui-logs")
        show_ui_logs
        ;;
    "tunnel-logs")
        show_tunnel_logs
        ;;
    "restart-ui")
        restart_ui
        ;;
    "restart-tunnel")
        restart_tunnel
        ;;
    "clean")
        clean_system
        ;;
    "help"|*)
        show_help
        ;;
esac