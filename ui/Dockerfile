FROM python:3.11-slim

WORKDIR /app

# 安裝系統依賴
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 複製 pyproject.toml 和相關檔案
COPY pyproject.toml .
COPY README.md .

# 安裝專案依賴（包含 UI 相關依賴）
RUN pip install --no-cache-dir -e ".[ui,ai,database,data]"

# 複製專案檔案
COPY . .

# 設置 Python 路徑
ENV PYTHONPATH=/app

# 健康檢查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# 啟動 Streamlit
CMD ["streamlit", "run", "ui/streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true", "--server.enableCORS=false"]