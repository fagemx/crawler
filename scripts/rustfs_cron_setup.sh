#!/bin/bash

# RustFS 定期維護設置腳本
# 用於設置 cron 任務來自動管理 RustFS

set -e

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 獲取腳本目錄
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
MANAGER_SCRIPT="$PROJECT_DIR/rustfs_auto_manager.py"

echo -e "${BLUE}🔧 RustFS 定期維護設置${NC}"
echo -e "${BLUE}========================${NC}"

# 檢查 Python 腳本是否存在
if [ ! -f "$MANAGER_SCRIPT" ]; then
    echo -e "${RED}❌ 找不到管理腳本: $MANAGER_SCRIPT${NC}"
    exit 1
fi

echo -e "${GREEN}✅ 找到管理腳本: $MANAGER_SCRIPT${NC}"

# 檢查是否為 Windows 環境
if [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]] || [[ "$OS" == "Windows_NT" ]]; then
    echo -e "${YELLOW}⚠️ Windows 環境檢測到${NC}"
    echo -e "${YELLOW}請使用 Windows 任務排程器來設置定期任務：${NC}"
    echo ""
    echo -e "${BLUE}Windows 任務排程器設置：${NC}"
    echo "1. 開啟 Windows 任務排程器"
    echo "2. 建立基本任務"
    echo "3. 名稱: RustFS Auto Maintenance"
    echo "4. 觸發程序: 每日執行"
    echo "5. 時間: 02:00"
    echo "6. 動作: 啟動程式"
    echo "7. 程式: python"
    echo "8. 引數: \"$MANAGER_SCRIPT\" --action auto"
    echo "9. 起始於: \"$PROJECT_DIR\""
    echo ""
    echo -e "${BLUE}或使用 PowerShell 手動執行：${NC}"
    echo "cd \"$PROJECT_DIR\""
    echo "python rustfs_auto_manager.py --action auto"
    exit 0
fi

# Linux/macOS 環境設置 cron 任務
echo -e "${BLUE}🕐 設置 cron 任務...${NC}"

# 創建 cron 任務
CRON_ENTRY="0 2 * * * cd $PROJECT_DIR && python3 $MANAGER_SCRIPT --action auto >> $PROJECT_DIR/logs/rustfs_maintenance.log 2>&1"

# 檢查是否已存在相同的任務
if crontab -l 2>/dev/null | grep -q "rustfs_auto_manager.py"; then
    echo -e "${YELLOW}⚠️ 已存在 RustFS 維護任務${NC}"
    echo -e "${YELLOW}是否要更新現有任務？ (y/N)${NC}"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        # 移除舊任務
        crontab -l 2>/dev/null | grep -v "rustfs_auto_manager.py" | crontab -
        echo -e "${GREEN}✅ 已移除舊任務${NC}"
    else
        echo -e "${BLUE}ℹ️ 保持現有任務不變${NC}"
        exit 0
    fi
fi

# 添加新任務
(crontab -l 2>/dev/null; echo "$CRON_ENTRY") | crontab -

echo -e "${GREEN}✅ 已添加 cron 任務: 每天凌晨 2:00 執行 RustFS 維護${NC}"

# 創建日誌目錄
mkdir -p "$PROJECT_DIR/logs"

# 顯示當前的 cron 任務
echo ""
echo -e "${BLUE}📋 當前 cron 任務:${NC}"
crontab -l | grep -E "(rustfs|RustFS)" || echo "無相關任務"

echo ""
echo -e "${GREEN}🎉 設置完成！${NC}"
echo -e "${BLUE}維護任務將在每天凌晨 2:00 自動執行${NC}"
echo ""
echo -e "${BLUE}手動測試指令:${NC}"
echo "cd $PROJECT_DIR"
echo "python3 rustfs_auto_manager.py --action health    # 檢查健康狀態"
echo "python3 rustfs_auto_manager.py --action cleanup   # 執行清理"
echo "python3 rustfs_auto_manager.py --action auto      # 自動維護"
echo ""
echo -e "${BLUE}監控指令:${NC}"
echo "python3 rustfs_auto_manager.py --action monitor   # 持續監控模式"
