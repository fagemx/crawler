#!/bin/bash

# 檢查端口佔用情況的腳本

echo "🔍 檢查系統端口佔用情況"
echo "=========================="

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 需要檢查的端口列表
ports=(
    "5432:PostgreSQL"
    "6379:Redis" 
    "8501:Streamlit UI"
    "8000:Orchestrator"
    "8003:Content Writer"
    "8004:Clarification"
    "8005:Vision Agent"
    "8006:Playwright Crawler"
    "8007:Post Analyzer"
    "8010:Form API"
    "9000:RustFS"
    "4222:NATS"
    "8222:NATS HTTP"
    "10100:MCP Server"
)

echo -e "${BLUE}📊 端口佔用檢查：${NC}"
echo ""

for port_info in "${ports[@]}"; do
    port=$(echo $port_info | cut -d: -f1)
    service=$(echo $port_info | cut -d: -f2)
    
    # 檢查端口是否被佔用
    if netstat -tlnp 2>/dev/null | grep -q ":$port "; then
        process=$(netstat -tlnp 2>/dev/null | grep ":$port " | awk '{print $7}' | head -1)
        echo -e "${RED}❌ $port ($service) - 被佔用: $process${NC}"
    else
        echo -e "${GREEN}✅ $port ($service) - 可用${NC}"
    fi
done

echo ""
echo -e "${BLUE}🔍 詳細端口資訊：${NC}"
echo ""

# 顯示所有相關端口的詳細資訊
for port_info in "${ports[@]}"; do
    port=$(echo $port_info | cut -d: -f1)
    service=$(echo $port_info | cut -d: -f2)
    
    result=$(netstat -tlnp 2>/dev/null | grep ":$port ")
    if [ ! -z "$result" ]; then
        echo -e "${YELLOW}Port $port ($service):${NC}"
        echo "$result"
        echo ""
    fi
done

echo -e "${BLUE}💡 建議：${NC}"
echo -e "${YELLOW}如果發現端口衝突，可以：${NC}"
echo -e "${YELLOW}1. 停止衝突的服務：sudo systemctl stop [service-name]${NC}"
echo -e "${YELLOW}2. 修改 docker-compose.yml 中的端口映射${NC}"
echo -e "${YELLOW}3. 使用 ./manage_system.sh start 啟動系統${NC}"