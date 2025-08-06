#!/bin/bash

# 確保資料庫存在的自動化腳本
# 用途：在應用程式啟動前確保資料庫和表格都正確設置

set -e

DB_CONTAINER="social-media-postgres"
DB_NAME="social_media_db"
DB_USER="postgres"

echo "🔍 檢查 PostgreSQL 容器狀態..."

# 等待容器啟動
timeout=30
while ! docker exec $DB_CONTAINER pg_isready -U $DB_USER > /dev/null 2>&1; do
    echo "⏳ 等待 PostgreSQL 準備就緒..."
    sleep 2
    timeout=$((timeout-1))
    if [ $timeout -le 0 ]; then
        echo "❌ PostgreSQL 容器啟動超時"
        exit 1
    fi
done

echo "✅ PostgreSQL 容器已就緒"

# 檢查資料庫是否存在
if docker exec $DB_CONTAINER psql -U $DB_USER -lqt | cut -d \| -f 1 | grep -qw $DB_NAME; then
    echo "✅ 資料庫 $DB_NAME 已存在"
else
    echo "🚀 創建資料庫 $DB_NAME..."
    docker exec $DB_CONTAINER psql -U $DB_USER -c "CREATE DATABASE $DB_NAME;"
    echo "✅ 資料庫創建完成"
fi

# 檢查重要表格是否存在
REQUIRED_TABLES=("posts" "post_metrics" "playwright_post_metrics" "crawl_state")
MISSING_TABLES=()

for table in "${REQUIRED_TABLES[@]}"; do
    if ! docker exec $DB_CONTAINER psql -U $DB_USER -d $DB_NAME -c "\dt" | grep -q $table; then
        MISSING_TABLES+=($table)
    fi
done

if [ ${#MISSING_TABLES[@]} -gt 0 ]; then
    echo "🚀 發現缺少表格: ${MISSING_TABLES[*]}"
    echo "執行初始化腳本..."
    
    # 執行初始化腳本
    if [ -f "scripts/init-db.sql" ]; then
        docker exec -i $DB_CONTAINER psql -U $DB_USER -d $DB_NAME < scripts/init-db.sql
        echo "✅ 初始化腳本執行完成"
    else
        echo "❌ 找不到初始化腳本 scripts/init-db.sql"
        exit 1
    fi
else
    echo "✅ 所有必要表格都已存在"
fi

# 驗證表格數量
TABLE_COUNT=$(docker exec $DB_CONTAINER psql -U $DB_USER -d $DB_NAME -c "\dt" | grep -c "table")
echo "📊 資料庫中共有 $TABLE_COUNT 個表格"

echo "🎉 資料庫檢查和修復完成！"