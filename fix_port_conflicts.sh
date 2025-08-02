#!/bin/bash

# 解決端口衝突的腳本

set -e

echo "🔧 解決端口衝突"
echo "================"

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 檢查是否以 root 權限運行
check_root() {
    if [ "$EUID" -ne 0 ]; then
        echo -e "${RED}❌ 此腳本需要 sudo 權限來停止系統服務${NC}"
        echo -e "${YELLOW}請使用：sudo ./fix_port_conflicts.sh${NC}"
        exit 1
    fi
}

# 停止可能衝突的系統服務
stop_conflicting_services() {
    echo -e "${BLUE}🛑 停止可能衝突的系統服務...${NC}"
    
    services_to_stop=(
        "nats-server"
        "postgresql" 
        "redis-server"
        "redis"
    )
    
    for service in "${services_to_stop[@]}"; do
        if systemctl is-active --quiet "$service" 2>/dev/null; then
            echo -e "${YELLOW}停止服務: $service${NC}"
            systemctl stop "$service" || true
            systemctl disable "$service" || true
        else
            echo -e "${GREEN}服務 $service 未運行或不存在${NC}"
        fi
    done
    
    # 檢查並殺死佔用關鍵端口的進程
    critical_ports=(4222 5432 6379 8501)
    
    for port in "${critical_ports[@]}"; do
        pid=$(netstat -tlnp 2>/dev/null | grep ":$port " | awk '{print $7}' | cut -d'/' -f1 | head -1)
        if [ ! -z "$pid" ] && [ "$pid" != "-" ]; then
            echo -e "${YELLOW}殺死佔用端口 $port 的進程 (PID: $pid)${NC}"
            kill -9 "$pid" 2>/dev/null || true
        fi
    done
}

# 檢查端口是否已釋放
verify_ports_free() {
    echo -e "${BLUE}🔍 驗證端口是否已釋放...${NC}"
    
    critical_ports=(4222 5432 6379 8501)
    conflicts_found=false
    
    for port in "${critical_ports[@]}"; do
        if netstat -tlnp 2>/dev/null | grep -q ":$port "; then
            process=$(netstat -tlnp 2>/dev/null | grep ":$port " | awk '{print $7}' | head -1)
            echo -e "${RED}❌ 端口 $port 仍被佔用: $process${NC}"
            conflicts_found=true
        else
            echo -e "${GREEN}✅ 端口 $port 已釋放${NC}"
        fi
    done
    
    if [ "$conflicts_found" = true ]; then
        echo -e "${RED}⚠️  仍有端口衝突，請手動處理${NC}"
        return 1
    else
        echo -e "${GREEN}✅ 所有關鍵端口已釋放${NC}"
        return 0
    fi
}

# 創建備用的 docker-compose 配置（使用不同端口）
create_alternative_config() {
    echo -e "${BLUE}📝 創建備用配置（使用替代端口）...${NC}"
    
    cp docker-compose.yml docker-compose.yml.backup
    
    # 修改端口映射以避免衝突
    sed -i 's/"4222:4222"/"14222:4222"/g' docker-compose.yml
    sed -i 's/"5432:5432"/"15432:5432"/g' docker-compose.yml  
    sed -i 's/"6379:6379"/"16379:6379"/g' docker-compose.yml
    sed -i 's/"8501:8501"/"18501:8501"/g' docker-compose.yml
    
    echo -e "${GREEN}✅ 備用配置已創建${NC}"
    echo -e "${YELLOW}💡 如果仍有衝突，可以使用替代端口：${NC}"
    echo -e "${YELLOW}   - UI: http://localhost:18501${NC}"
    echo -e "${YELLOW}   - PostgreSQL: localhost:15432${NC}"
    echo -e "${YELLOW}   - Redis: localhost:16379${NC}"
    echo -e "${YELLOW}   - NATS: localhost:14222${NC}"
}

# 恢復原始配置
restore_original_config() {
    if [ -f "docker-compose.yml.backup" ]; then
        echo -e "${BLUE}🔄 恢復原始配置...${NC}"
        cp docker-compose.yml.backup docker-compose.yml
        echo -e "${GREEN}✅ 原始配置已恢復${NC}"
    fi
}

# 主執行流程
main() {
    echo -e "${BLUE}開始解決端口衝突...${NC}"
    
    # 檢查權限
    check_root
    
    # 停止衝突服務
    stop_conflicting_services
    
    # 等待服務完全停止
    echo -e "${BLUE}⏳ 等待服務完全停止...${NC}"
    sleep 5
    
    # 驗證端口是否釋放
    if verify_ports_free; then
        echo -e "${GREEN}🎉 端口衝突已解決！${NC}"
        echo -e "${GREEN}現在可以啟動 Docker 服務：${NC}"
        echo -e "${GREEN}./manage_system.sh start-tunnel${NC}"
    else
        echo -e "${YELLOW}⚠️  仍有端口衝突，創建備用配置...${NC}"
        create_alternative_config
        echo -e "${YELLOW}請使用備用端口啟動服務${NC}"
    fi
}

# 處理中斷信號
trap 'echo -e "\n${YELLOW}⚠️  操作被中斷${NC}"; exit 1' INT TERM

# 如果傳入參數 "restore"，則恢復原始配置
if [ "$1" = "restore" ]; then
    restore_original_config
    exit 0
fi

# 執行主流程
main