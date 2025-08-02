#!/bin/bash

# 只啟動 Streamlit UI（假設其他服務已運行）
# 替代手動運行 restart_streamlit.py

set -e

echo "🎨 啟動 Streamlit UI (Docker)"
echo "============================="

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 檢查必要服務是否運行
check_dependencies() {
    echo -e "${BLUE}🔍 檢查依賴服務...${NC}"
    
    required_services=("orchestrator-agent" "form-api" "redis")
    
    for service in "${required_services[@]}"; do
        if ! docker compose ps -q "$service" | grep -q .; then
            echo -e "${RED}❌ $service 未運行${NC}"
            echo -e "${YELLOW}💡 請先啟動完整系統：./start_docker_ui.sh${NC}"
            exit 1
        else
            echo -e "${GREEN}✅ $service 正在運行${NC}"
        fi
    done
}

# 重啟 UI 服務
restart_ui() {
    echo -e "${BLUE}🔄 重啟 Streamlit UI...${NC}"
    
    # 停止現有 UI
    docker compose stop streamlit-ui
    docker compose rm -f streamlit-ui
    
    # 重新構建和啟動
    docker compose up -d --build streamlit-ui
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ UI 重啟成功${NC}"
    else
        echo -e "${RED}❌ UI 重啟失敗${NC}"
        echo -e "${YELLOW}📋 檢查日誌：docker compose logs streamlit-ui${NC}"
        exit 1
    fi
}

# 等待服務就緒
wait_for_ui() {
    echo -e "${BLUE}⏳ 等待 UI 服務就緒...${NC}"
    
    for i in {1..30}; do
        if curl -s http://localhost:8501/_stcore/health > /dev/null 2>&1; then
            echo -e "${GREEN}✅ UI 服務已就緒${NC}"
            break
        fi
        
        if [ $i -eq 30 ]; then
            echo -e "${RED}❌ UI 服務啟動超時${NC}"
            echo -e "${YELLOW}📋 檢查日誌：docker compose logs streamlit-ui${NC}"
            exit 1
        fi
        
        echo -e "${YELLOW}⏳ 等待中... ($i/30)${NC}"
        sleep 2
    done
}

# 顯示結果
show_result() {
    echo -e "${GREEN}🎉 Streamlit UI 啟動完成！${NC}"
    echo -e "${GREEN}================================${NC}"
    echo -e "${GREEN}🌐 訪問地址: http://localhost:8501${NC}"
    echo -e "${GREEN}================================${NC}"
    
    echo -e "${YELLOW}💡 提示：${NC}"
    echo -e "${YELLOW}   - 查看 UI 日誌：docker compose logs -f streamlit-ui${NC}"
    echo -e "${YELLOW}   - 重啟 UI：./start_ui_only.sh${NC}"
    echo -e "${YELLOW}   - 停止 UI：docker compose stop streamlit-ui${NC}"
}

# 主執行流程
main() {
    check_dependencies
    restart_ui
    wait_for_ui
    show_result
}

# 執行主流程
main