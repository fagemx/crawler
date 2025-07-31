# 統一 LLM 客戶端架構文檔

## 概述

本文檔描述了社交媒體內容生成系統的統一 LLM 客戶端架構，支持多供應商管理、智能路由、成本追蹤和性能監控。

## 架構設計

### 核心組件

1. **LLMManager** - 統一 LLM 管理器
2. **BaseLLMProvider** - LLM 供應商基類
3. **GeminiProvider** - Gemini 供應商實現
4. **OpenAIProvider** - OpenAI 供應商實現
5. **LLMRequest/LLMResponse** - 標準化請求/響應數據結構

### 文件結構

```
common/
├── llm_manager.py          # 統一 LLM 管理器（新）
├── llm_client.py           # 舊版客戶端（向後兼容）
└── settings.py             # 配置管理
```

## 主要特性

### 1. 統一接口

所有 Agent 都使用相同的接口調用 LLM：

```python
from common.llm_manager import chat_completion

# 簡單調用
content = await chat_completion(
    messages=[
        {"role": "system", "content": "你是一位專業的社群寫手"},
        {"role": "user", "content": "請寫一篇貼文"}
    ],
    model="gemini-2.0-flash",
    temperature=0.7,
    provider="gemini"
)
```

### 2. 多供應商支持

目前支持的供應商：
- **Gemini** (主要) - gemini-2.0-flash
- **OpenAI** (備用) - gpt-4o-mini
- **Claude** (計劃中)
- **OpenRouter** (計劃中)

### 3. 智能路由

- 自動選擇可用的供應商
- 支援備用供應商切換
- 基於成本和性能的路由策略

### 4. 成本追蹤

每個供應商都有詳細的使用統計：
- 總請求數
- Token 使用量
- 總成本
- 平均延遲
- 成功率

### 5. 性能監控

實時監控各供應商的：
- 響應時間
- 可用性
- 錯誤率
- 使用量趨勢

## 當前配置

### Agent 配置

所有使用 LLM 的 Agent 都配置為使用 Gemini 2.0 Flash：

1. **Orchestrator Agent (8000)** - 總協調器
   - 不直接使用 LLM
   
2. **Clarification Agent (8004)** - 智能問題生成
   - 模型: gemini-2.0-flash
   - 溫度: 0.3 (低溫度確保一致性)
   - 最大 Token: 1500
   
3. **Content Writer Agent (8003)** - 內容生成
   - 模型: gemini-2.0-flash
   - 溫度: 0.7 (適中創造性)
   - 最大 Token: 800

### 環境變數配置

```bash
# Gemini API 配置
GEMINI_API_KEY=your_gemini_api_key
GOOGLE_API_KEY=your_google_api_key  # 備用

# OpenAI API 配置（備用）
OPENAI_API_KEY=your_openai_api_key
```

## 使用方式

### 基本使用

```python
from common.llm_manager import get_llm_manager, chat_completion

# 方式 1: 使用便利函數
content = await chat_completion(
    messages=messages,
    model="gemini-2.0-flash",
    provider="gemini"
)

# 方式 2: 使用管理器
manager = get_llm_manager()
response = await manager.chat_completion(
    messages=messages,
    model="gemini-2.0-flash",
    provider="gemini"
)
print(response.content)  # 內容
print(response.cost)     # 成本
print(response.latency)  # 延遲
```

### 向後兼容

舊代碼仍然可以使用 LLMClient：

```python
from common.llm_manager import LLMClient

client = LLMClient("gemini")
response = await client.chat_completion(messages)
# 返回 OpenAI 格式的響應
```

## 成本配置

### Gemini 成本 (每 1M tokens)

| 模型 | 輸入成本 | 輸出成本 |
|------|----------|----------|
| gemini-2.0-flash | $0.075 | $0.30 |
| gemini-1.5-pro | $3.50 | $10.50 |
| gemini-1.5-flash | $0.075 | $0.30 |

### OpenAI 成本 (每 1M tokens)

| 模型 | 輸入成本 | 輸出成本 |
|------|----------|----------|
| gpt-4o | $2.50 | $10.00 |
| gpt-4o-mini | $0.15 | $0.60 |

## 監控和統計

### 獲取使用統計

```python
from common.llm_manager import get_llm_manager

manager = get_llm_manager()

# 獲取所有供應商統計
all_stats = manager.get_all_stats()

# 獲取特定供應商統計
gemini_stats = manager.get_provider_stats(LLMProvider.GEMINI)
print(f"總請求數: {gemini_stats.total_requests}")
print(f"總成本: ${gemini_stats.total_cost:.4f}")
print(f"平均延遲: {gemini_stats.avg_latency:.2f}s")
print(f"成功率: {gemini_stats.success_rate:.2%}")
```

## 測試

### 運行集成測試

```bash
python test_gemini_integration.py
```

測試包括：
1. 健康檢查所有服務
2. 完整的澄清→生成流程
3. 直接測試 Content Writer
4. 驗證 Gemini 2.0 Flash 正常工作

## 未來擴展

### 計劃中的功能

1. **更多供應商支持**
   - Claude (Anthropic)
   - OpenRouter
   - 本地模型 (Ollama)

2. **智能緩存**
   - Redis 緩存相似請求
   - 語義相似度匹配
   - 成本優化

3. **高級路由**
   - 基於內容類型的路由
   - 負載均衡
   - 故障轉移

4. **監控儀表板**
   - 實時使用統計
   - 成本分析
   - 性能圖表

### 添加新供應商

1. 繼承 `BaseLLMProvider`
2. 實現必要方法
3. 在 `LLMManager` 中註冊
4. 更新配置和文檔

```python
class NewProvider(BaseLLMProvider):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(LLMProvider.NEW_PROVIDER, config)
    
    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        # 實現具體邏輯
        pass
    
    def is_available(self) -> bool:
        # 檢查可用性
        pass
    
    def get_cost_per_token(self, model: str) -> Dict[str, float]:
        # 返回成本配置
        pass
```

## 故障排除

### 常見問題

1. **API 密鑰未配置**
   - 檢查環境變數 `GEMINI_API_KEY`
   - 確認密鑰有效性

2. **模型不存在**
   - 檢查模型名稱拼寫
   - 確認供應商支持該模型

3. **請求超時**
   - 檢查網絡連接
   - 調整超時設置

4. **成本異常**
   - 檢查 token 計算邏輯
   - 更新成本配置

### 日誌檢查

```bash
# 檢查 Content Writer 日誌
docker-compose logs content-writer-agent

# 檢查 Clarification Agent 日誌  
docker-compose logs clarification-agent

# 檢查所有服務健康狀態
curl http://localhost:8000/health
curl http://localhost:8003/health
curl http://localhost:8004/health
```

## 總結

新的統一 LLM 客戶端架構提供了：

✅ **統一接口** - 所有 Agent 使用相同的 API  
✅ **多供應商支持** - 輕鬆切換和管理不同供應商  
✅ **成本追蹤** - 詳細的使用統計和成本分析  
✅ **性能監控** - 實時監控響應時間和可用性  
✅ **向後兼容** - 舊代碼無需修改即可使用  
✅ **易於擴展** - 簡單添加新供應商和功能  

這個架構為系統提供了強大的 LLM 管理能力，同時保持了簡潔易用的接口。