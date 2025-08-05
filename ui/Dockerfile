FROM python:3.11-slim

WORKDIR /app

# 安裝系統依賴（包括 Playwright 需要的依賴）
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    gnupg \
    ca-certificates \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# 直接安裝 UI 需要的套件（包括 Playwright）
RUN pip install --no-cache-dir \
    streamlit>=1.28.0 \
    fastapi>=0.100.0 \
    httpx>=0.24.0 \
    requests>=2.28.0 \
    pandas>=2.0.0 \
    numpy>=1.24.0 \
    pydantic>=2.0.0 \
    pydantic-settings>=2.0.0 \
    python-dotenv>=1.0.0 \
    asyncpg>=0.28.0 \
    psycopg2-binary>=2.9.0 \
    sqlmodel>=0.0.14 \
    redis>=4.5.0 \
    aiohttp>=3.8.0 \
    structlog>=23.0.0 \
    Pillow>=10.0.0 \
    google-generativeai>=0.3.0 \
    boto3>=1.28.0 \
    beautifulsoup4>=4.12.0 \
    lxml>=4.9.0 \
    python-multipart>=0.0.6 \
    click>=8.1.0 \
    playwright>=1.40.0

# 安裝 Playwright 瀏覽器
RUN playwright install chromium
RUN playwright install-deps chromium

# 複製專案檔案
COPY . .

# 設置 Python 路徑
ENV PYTHONPATH=/app

# 健康檢查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# 啟動 Streamlit 使用 start_streamlit_ui.py 腳本
CMD ["python", "scripts/start_streamlit_ui.py"]