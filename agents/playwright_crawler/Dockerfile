# Playwright Crawler Agent Dockerfile
FROM python:3.11-slim

# 設定工作目錄
WORKDIR /app

# 安裝系統依賴，包括 Playwright 需要的瀏覽器依賴
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    wget \
    && rm -rf /var/lib/apt/lists/*

# 複製必要的專案檔案
COPY pyproject.toml README.md LICENSE ./

# 安裝 Python 依賴（包含可選依賴組）
RUN pip install --no-cache-dir -e ".[messaging,playwright_crawler]"

# 複製應用程式碼
COPY . .

# 設置環境變數
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 安裝 Playwright 瀏覽器
RUN python -m playwright install chromium --with-deps

# 健康檢查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8006/health || exit 1

# 開放端口
EXPOSE 8006

# 啟動命令
CMD ["python", "-m", "uvicorn", "agents.playwright_crawler.main:app", "--host", "0.0.0.0", "--port", "8006"] 