# Use the official Python image from the Docker Hub
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the entire project context
COPY . .

# -----------------------------------------------------------------------------
# Plan F - 更強健的依賴安裝
# -----------------------------------------------------------------------------
# 1. 複製專案檔案
WORKDIR /app
COPY . .

# 2. 更新 pip 並設定重試和超時
RUN pip install --upgrade pip && \
    pip config set global.retries 5 && \
    pip config set global.timeout 60

# 3. 從一個可靠的鏡像安裝依賴
# 使用 requirements.txt 檔案來管理依賴，而不是在 Dockerfile 中硬式編碼
# (假設我們會在 jina agent 目錄下建立一個 requirements.txt)
COPY agents/jina/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple 

# -----------------------------------------------------------------------------

# Set Python path
ENV PYTHONPATH=/app

# FastAPI 應用程式的啟動指令
EXPOSE 8004
CMD ["uvicorn", "agents.jina.main:app", "--host", "0.0.0.0", "--port", "8004"] 