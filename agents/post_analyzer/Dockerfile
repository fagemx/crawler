# Post Analyzer Agent Dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安裝系統依賴
RUN apt-get update && apt-get install -y curl gcc && rm -rf /var/lib/apt/lists/*

# 複製項目配置
COPY pyproject.toml README.md LICENSE ./

# 安裝 Python 依賴（包含可選依賴組）
RUN pip install --no-cache-dir -e ".[database,messaging,ai,monitoring]"

# 複製應用程式碼
COPY . .

# 設置環境變數
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 健康檢查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8007/health || exit 1

# 啟動服務
CMD ["python", "-m", "uvicorn", "agents.post_analyzer.main:app", "--host", "0.0.0.0", "--port", "8007", "--reload"]