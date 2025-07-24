# syntax=docker/dockerfile:1

# 使用官方 Python 映像檔作為基礎
FROM python:3.11-slim

# 設定工作目錄
WORKDIR /app

# 安裝系統依賴，以便 Playwright 可以安裝和運行瀏覽器
# --with-deps 會安裝所有必要的系統套件
RUN apt-get update && apt-get install -y --no-install-recommends wget && \
    pip install playwright && \
    playwright install chromium --with-deps && \
    apt-get remove -y wget && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 將整個專案程式碼複製到容器中
COPY . .

# 直接安裝必要的依賴 (繞過 Poetry 的複雜依賴解析)
RUN pip install --no-cache-dir \
    fastapi>=0.104.0 \
    uvicorn>=0.24.0 \
    pydantic>=2.0.0 \
    pydantic-settings>=2.0.0 \
    playwright>=1.54.0 \
    httpx>=0.25.0

# 設定環境變數
ENV PYTHONUNBUFFERED=1

# 開放 Agent 服務的端口 (假設為 8006，後續會在 settings.py 中定義)
EXPOSE 8006

# 預設啟動命令 (使用 python -m 確保能找到 uvicorn)
CMD ["python", "-m", "uvicorn", "agents.playwright_crawler.main:app", "--host", "0.0.0.0", "--port", "8006"] 