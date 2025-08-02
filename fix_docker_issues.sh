#!/bin/bash

# 修復 Docker Compose 問題

echo "🔧 修復 Docker Compose 問題..."

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 停止所有服務
echo -e "${BLUE}🛑 停止所有服務...${NC}"
docker-compose --profile tunnel down 2>/dev/null || true

# 清理 Docker 系統
echo -e "${BLUE}🧹 清理 Docker 系統...${NC}"
docker system prune -f

# 刪除可能損壞的鏡像
echo -e "${BLUE}🗑️  刪除可能損壞的鏡像...${NC}"
docker rmi social-media-content-generator_mcp-server 2>/dev/null || true
docker rmi social-media-content-generator_streamlit-ui 2>/dev/null || true

# 檢查 docker-compose 版本
echo -e "${BLUE}📋 檢查 docker-compose 版本...${NC}"
docker-compose --version

# 嘗試重新啟動
echo -e "${BLUE}🚀 重新啟動系統...${NC}"
if docker-compose --profile tunnel up -d --build; then
    echo -e "${GREEN}✅ 系統啟動成功！${NC}"
else
    echo -e "${RED}❌ 啟動失敗，嘗試使用新版本語法...${NC}"
    
    # 嘗試新版本語法
    if command -v docker &> /dev/null && docker compose version &> /dev/null 2>&1; then
        echo -e "${YELLOW}🔄 使用新版本 docker compose...${NC}"
        docker compose --profile tunnel up -d --build
    else
        echo -e "${RED}❌ 需要升級 docker-compose${NC}"
        echo -e "${YELLOW}💡 請執行: sudo apt install docker-compose-plugin${NC}"
    fi
fi

# 檢查結果
echo -e "${BLUE}📊 檢查服務狀態...${NC}"
sleep 5
docker-compose ps 2>/dev/null || docker compose ps 2>/dev/null || echo "無法檢查狀態"

echo -e "${GREEN}🎉 修復完成！${NC}"