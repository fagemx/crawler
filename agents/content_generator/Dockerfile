FROM python:3.11

WORKDIR /app

# 複製需求檔案、LICENSE 和 README
COPY pyproject.toml LICENSE README.md ./

# 安裝依賴
RUN pip install .[database,messaging,ai,monitoring]

# 複製應用程式代碼
COPY . .

# 暴露端口
EXPOSE 8008

# 啟動命令
CMD ["python", "agents/content_generator/main.py"]
