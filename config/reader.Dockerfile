# 修正版 Reader Dockerfile - 包含TypeScript編譯步驟
# syntax=docker/dockerfile:1
FROM lwthiker/curl-impersonate:0.6-chrome-slim-bullseye as curl-base

FROM node:22 as builder

# 安裝系統依賴
RUN apt-get update \
    && apt-get install -y wget gnupg \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list' \
    && apt-get update \
    && apt-get install -y google-chrome-stable fonts-ipafont-gothic fonts-wqy-zenhei fonts-thai-tlwg fonts-kacst fonts-freefont-ttf libxss1 zstd \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# 複製 curl-impersonate 庫
COPY --from=curl-base /usr/local/lib/libcurl-impersonate.so /usr/local/lib/libcurl-impersonate.so

WORKDIR /app

# 先複製依賴檔案
COPY package.json package-lock.json ./
COPY tsconfig.json ./
COPY integrity-check.cjs ./

# 安裝依賴
RUN npm ci

# 複製源碼和必要目錄
COPY src ./src
COPY public ./public
COPY thinapps-shared ./thinapps-shared

# 創建licensed目錄（原始Dockerfile需要）
RUN mkdir -p ./licensed

# 構建項目
RUN npm run build

# 創建用戶
RUN groupadd -r jina
RUN useradd -g jina -G audio,video -m jina

# 設置Chrome配置
USER jina
RUN rm -rf ~/.config/chromium && mkdir -p ~/.config/chromium

# 執行dry-run測試
RUN NODE_COMPILE_CACHE=node_modules npm run dry-run

# 環境變數
ENV OVERRIDE_CHROME_EXECUTABLE_PATH=/usr/bin/google-chrome-stable
ENV LD_PRELOAD=/usr/local/lib/libcurl-impersonate.so 
ENV CURL_IMPERSONATE=chrome116 
ENV CURL_IMPERSONATE_HEADERS=no
ENV NODE_COMPILE_CACHE=node_modules
ENV PORT=8080

# 暴露端口
EXPOSE 8080

# 健康檢查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/ || exit 1

# 啟動命令
ENTRYPOINT ["node"]
CMD ["build/stand-alone/crawl.js"]