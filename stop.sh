#!/bin/bash

# 停止所有服務

echo "🛑 停止所有服務..."

docker compose --profile tunnel down

echo "✅ 所有服務已停止"