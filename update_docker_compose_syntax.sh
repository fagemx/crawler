#!/bin/bash

# 批量更新所有檔案中的 docker-compose 為 docker compose

echo "🔄 批量更新 docker-compose 語法..."

# 顏色定義
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 要更新的檔案列表
files=(
    "docs/DEPLOYMENT_GUIDE.md"
    "README_DEPLOYMENT.md"
    "OPERATIONS_MANUAL.md"
    "start_with_tunnel.sh"
    "start_ui_ubuntu.sh"
    "manage_system.sh"
    "fix_docker_issues.sh"
)

# 批量替換函數
update_file() {
    local file="$1"
    if [ -f "$file" ]; then
        echo -e "${BLUE}更新檔案: $file${NC}"
        
        # 替換 docker-compose 為 docker compose（但保留在註解中的說明）
        sed -i 's/docker-compose --/docker compose --/g' "$file"
        sed -i 's/docker-compose up/docker compose up/g' "$file"
        sed -i 's/docker-compose down/docker compose down/g' "$file"
        sed -i 's/docker-compose ps/docker compose ps/g' "$file"
        sed -i 's/docker-compose logs/docker compose logs/g' "$file"
        sed -i 's/docker-compose restart/docker compose restart/g' "$file"
        sed -i 's/docker-compose stop/docker compose stop/g' "$file"
        sed -i 's/docker-compose build/docker compose build/g' "$file"
        sed -i 's/docker-compose rm/docker compose rm/g' "$file"
        sed -i 's/docker-compose exec/docker compose exec/g' "$file"
        
        # 但保留安裝指令中的 docker-compose
        sed -i 's/apt install docker compose/apt install docker-compose/g' "$file"
        sed -i 's/install docker compose-plugin/install docker-compose-plugin/g' "$file"
        
        echo -e "${GREEN}✅ 完成: $file${NC}"
    else
        echo "⚠️  檔案不存在: $file"
    fi
}

# 更新所有檔案
for file in "${files[@]}"; do
    update_file "$file"
done

echo -e "${GREEN}🎉 批量更新完成！${NC}"
echo -e "${BLUE}💡 注意：安裝指令仍使用 docker-compose，執行指令使用 docker compose${NC}"