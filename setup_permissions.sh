#!/bin/bash

# 設置腳本執行權限

echo "🔧 設置腳本執行權限..."

chmod +x start_docker_ui.sh
chmod +x start_ui_only.sh
chmod +x start_with_tunnel.sh
chmod +x start_tunnel_only.sh
chmod +x manage_system.sh
chmod +x setup_permissions.sh

echo "✅ 權限設置完成！"

echo ""
echo "📋 可用腳本："
echo "  ./manage_system.sh start-tunnel  # 啟動系統+外網訪問"
echo "  ./manage_system.sh status        # 查看狀態"
echo "  ./manage_system.sh stop          # 停止服務"