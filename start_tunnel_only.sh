#!/bin/bash

# 只啟動 Pinggy Tunnel（假設 UI 已經在運行）
# 用於單獨管理 Tunnel 服務

set -e

echo "🌐 啟動 Pinggy Tunnel"
echo "===================="

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 檢查 UI 是否運行
check_ui_running() {
    echo -e "${BLUE}🔍 檢查 Streamlit UI 是否運行...${NC}"
    
    if curl -s http://localhost:8501/_stcore/health > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Streamlit UI 正在運行${NC}"
    else
        echo -e "${RED}❌ Streamlit UI 未運行${NC}"
        echo -e "${YELLOW}💡 請先啟動 UI：docker compose up -d streamlit-ui${NC}"
        echo -e "${YELLOW}💡 或啟動完整系統：./start_with_tunnel.sh${NC}"
        exit 1
    fi
}

# 停止現有 Tunnel
stop_existing_tunnel() {
    echo -e "${YELLOW}🛑 停止現有 Tunnel...${NC}"
    docker compose stop pinggy-tunnel 2>/dev/null || true
    docker compose rm -f pinggy-tunnel 2>/dev/null || true
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

# 等待並檢查 Tunnel 狀態
check_tunnel_status() {
    echo -e "${BLUE}⏳ 等待 Tunnel 建立連線...${NC}"
    sleep 10
    
    echo -e "${BLUE}📋 Pinggy Tunnel 日誌：${NC}"
    docker compose logs --tail=15 pinggy-tunnel
    
    echo -e "${GREEN}🎉 Tunnel 啟動完成！${NC}"
    echo -e "${GREEN}================================${NC}"
    echo -e "${GREEN}🌐 本地訪問: http://localhost:8501${NC}"
    echo -e "${GREEN}🌍 外網訪問: https://hlsbwbzaat.a.pinggy.link${NC}"
    echo -e "${GREEN}================================${NC}"
    
    echo -e "${YELLOW}💡 提示：${NC}"
    echo -e "${YELLOW}   - 查看 Tunnel 日誌：docker compose logs -f pinggy-tunnel${NC}"
    echo -e "${YELLOW}   - 停止 Tunnel：docker compose stop pinggy-tunnel${NC}"
    echo -e "${YELLOW}   - 重啟 Tunnel：./start_tunnel_only.sh${NC}"
}

# 主執行流程
main() {
    check_ui_running
    stop_existing_tunnel
    start_tunnel
    check_tunnel_status
}

# 執行主流程
main

echo -e "${GREEN}✨ Pinggy Tunnel 已在背景運行，你可以關閉 SSH 視窗${NC}"