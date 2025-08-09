FROM python:3.11-slim

WORKDIR /app

# 安裝系統依賴
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 複製必要的專案檔案
COPY pyproject.toml README.md LICENSE ./

# 安裝專案依賴（包含 database、messaging、ai、monitoring 組，提供 structlog）
RUN pip install --no-cache-dir -e ".[database,messaging,ai,monitoring]"

# 複製其餘專案檔案
COPY . .

# 健康檢查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8003/health || exit 1

# 啟動服務
CMD ["uvicorn", "agents.content_writer.main:app", "--host", "0.0.0.0", "--port", "8003", "--reload"]