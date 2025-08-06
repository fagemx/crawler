#!/bin/bash

# 資料庫快速修復腳本 - 緊急情況使用
# 使用方式: ./scripts/quick_fix_database.sh

set -e

echo "🚨 執行資料庫快速修復..."

DB_CONTAINER="social-media-postgres"
DB_NAME="social_media_db"
DB_USER="postgres"

# 檢查容器是否運行
if ! docker ps | grep -q $DB_CONTAINER; then
    echo "🔧 啟動 PostgreSQL 容器..."
    docker-compose up -d postgres
    sleep 10
fi

# 確保資料庫存在
echo "🔍 檢查資料庫..."
if ! docker exec $DB_CONTAINER psql -U $DB_USER -lqt | cut -d \| -f 1 | grep -qw $DB_NAME; then
    echo "🚀 創建資料庫..."
    docker exec $DB_CONTAINER psql -U $DB_USER -c "CREATE DATABASE $DB_NAME;"
fi

# 執行修復腳本
echo "🔧 執行修復腳本..."
docker exec -i $DB_CONTAINER psql -U $DB_USER -d $DB_NAME < scripts/fix_ubuntu_database.sql

echo "✅ 快速修復完成！"

# 測試連接
if docker exec $DB_CONTAINER psql -U $DB_USER -d $DB_NAME -c "SELECT 1;" > /dev/null 2>&1; then
    echo "✅ 資料庫連接測試成功"
else
    echo "❌ 資料庫連接測試失敗"
    exit 1
fi