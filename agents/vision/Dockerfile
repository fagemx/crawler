# Vision Agent Dockerfile
FROM python:3.11-slim

# 設置工作目錄
WORKDIR /app

# 安裝系統依賴
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 複製必要的專案檔案
COPY pyproject.toml README.md LICENSE ./

# 安裝 Python 依賴（包含可選依賴組）
RUN pip install --no-cache-dir -e ".[messaging,monitoring,ai,database,security]"

# 複製應用程式碼
COPY . .

# 設置環境變數
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 健康檢查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8005/health || exit 1

# 暴露端口
EXPOSE 8005

# 啟動命令
CMD ["uvicorn", "agents.vision.main:app", "--host", "0.0.0.0", "--port", "8005"]