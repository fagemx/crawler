# 📦 依賴管理指南

## pyproject.toml 現代化依賴管理

本專案使用 `pyproject.toml` 進行現代化的 Python 依賴管理，支援模組化安裝和靈活的功能組合。

### 🎯 核心理念

- **模組化設計**：按功能分組依賴，按需安裝
- **版本控制**：精確的版本範圍管理
- **開發友好**：開發和生產環境分離
- **擴展性**：輕鬆添加新功能模組

### 📋 依賴分組

#### 核心依賴（必需）
```toml
dependencies = [
    "fastapi>=0.104.1,<0.105.0",      # Web 框架
    "uvicorn[standard]>=0.24.0",       # ASGI 服務器
    "pydantic>=2.5.0,<3.0.0",         # 數據驗證
    "apify-client>=1.7.1,<2.0.0",     # 爬蟲客戶端
    "httpx>=0.25.2,<0.26.0",          # HTTP 客戶端
    # ... 其他核心依賴
]
```

#### 可選依賴組

| 組名 | 用途 | 主要包 |
|------|------|--------|
| `ai` | AI 和 LLM 功能 | google-generativeai, openai |
| `ui` | Web 用戶介面 | streamlit |
| `database` | 數據持久化 | sqlalchemy, asyncpg |
| `messaging` | 訊息佇列 | redis, nats-py |
| `monitoring` | 監控追蹤 | opentelemetry, prometheus |
| `data` | 數據處理 | pandas, numpy |
| `security` | 安全認證 | bcrypt, python-jose |
| `dev` | 開發工具 | pytest, black, mypy |

### 🚀 安裝方式

#### 基礎安裝
```bash
# 只安裝核心功能（爬蟲）
pip install -e .
```

#### 功能模組安裝
```bash
# 安裝 AI 功能
pip install -e .[ai]

# 安裝 UI 功能
pip install -e .[ui]

# 安裝資料庫功能
pip install -e .[database]

# 組合安裝
pip install -e .[ai,ui,database]
```

#### 預設組合
```bash
# 完整功能（生產環境）
pip install -e .[full]

# 生產環境（不含開發工具）
pip install -e .[production]

# 開發環境
pip install -e .[dev]
```

### 🔧 開發工具整合

#### 代碼格式化
```bash
# 使用 hatch 環境
hatch run format

# 或直接使用工具
black .
isort .
```

#### 代碼檢查
```bash
# 完整檢查
hatch run check

# 單獨檢查
hatch run lint
hatch run test
```

#### 測試執行
```bash
# 基本測試
hatch run test

# 覆蓋率測試
hatch run test-cov

# 快速測試
hatch run test-fast
```

### 📊 依賴版本策略

#### 版本範圍策略
- **寬鬆策略**：`>=X.Y.Z` - 允許所有後續版本，獲得最新功能和安全更新
- **僅在必要時限制**：只有在已知版本衝突時才設置上限
- **最小版本要求**：設置已測試的最低版本作為下限

#### 範例說明
```toml
"fastapi>=0.100.0"        # 允許所有 0.100.0 以上版本
"pydantic>=2.0.0"         # 允許所有 2.x 版本
"apify-client>=1.0.0"     # 允許所有 1.x 版本，包括最新的 1.12.0
```

#### 優勢
- ✅ 自動獲得最新功能和安全更新
- ✅ 避免依賴過時問題
- ✅ 減少版本衝突
- ✅ 更好的生態系統兼容性

### 🎯 使用場景

#### 場景 1：基礎爬蟲開發
```bash
# 只需要爬蟲功能
pip install -e .

# 測試爬蟲
python test_crawler.py
```

#### 場景 2：添加 AI 分析功能
```bash
# 添加 AI 依賴
pip install -e .[ai]

# 現在可以使用 Gemini API
```

#### 場景 3：完整系統開發
```bash
# 安裝所有功能
pip install -e .[full,dev]

# 開始完整開發
hatch run dev
```

#### 場景 4：生產部署
```bash
# 只安裝生產需要的依賴
pip install -e .[production]

# 不包含開發工具，減少容器大小
```

### 🔄 依賴更新流程

#### 1. 檢查過期依賴
```bash
pip list --outdated
```

#### 2. 更新 pyproject.toml
```toml
# 更新版本範圍
"fastapi>=0.105.0,<0.106.0"  # 從 0.104.x 升級到 0.105.x
```

#### 3. 測試兼容性
```bash
# 重新安裝
pip install -e .[dev]

# 運行測試
hatch run test
```

#### 4. 鎖定版本（可選）
```bash
# 生成鎖定檔案
pip freeze > requirements-lock.txt
```

### 🐳 Docker 整合

#### Dockerfile 範例
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml .

# 只安裝生產依賴
RUN pip install -e .[production]

COPY . .
CMD ["uvicorn", "agents.crawler.main:app", "--host", "0.0.0.0"]
```

#### 多階段構建
```dockerfile
# 開發階段
FROM python:3.11 as development
RUN pip install -e .[full,dev]

# 生產階段
FROM python:3.11-slim as production
RUN pip install -e .[production]
```

### 📈 擴展新功能

#### 添加新的依賴組
```toml
[project.optional-dependencies]
# 新增機器學習功能
ml = [
    "scikit-learn>=1.3.0,<2.0.0",
    "torch>=2.0.0,<3.0.0",
    "transformers>=4.30.0,<5.0.0",
]

# 新增圖像處理功能
image = [
    "pillow>=10.0.0,<11.0.0",
    "opencv-python>=4.8.0,<5.0.0",
]
```

#### 使用新功能
```bash
# 安裝新功能
pip install -e .[ml,image]

# 組合使用
pip install -e .[ai,ml,image]
```

### 🔍 故障排除

#### 常見問題

1. **依賴衝突**
```bash
# 檢查依賴樹
pip show package-name

# 解決衝突
pip install --upgrade package-name
```

2. **版本不兼容**
```bash
# 檢查兼容性
pip check

# 降級到兼容版本
pip install "package-name<version"
```

3. **安裝失敗**
```bash
# 清理快取
pip cache purge

# 重新安裝
pip install --no-cache-dir -e .
```

### 📚 最佳實踐

#### 1. 版本管理
- 使用語義化版本控制
- 定期更新依賴
- 測試新版本兼容性

#### 2. 模組設計
- 按功能分組依賴
- 避免循環依賴
- 保持核心依賴最小化

#### 3. 開發流程
- 使用虛擬環境
- 鎖定生產版本
- 自動化測試

#### 4. 部署策略
- 分離開發和生產依賴
- 使用多階段 Docker 構建
- 監控依賴安全性

---

**總結**：pyproject.toml 提供了現代化、靈活的依賴管理方式，支援模組化安裝和精確的版本控制，讓專案更易維護和擴展。