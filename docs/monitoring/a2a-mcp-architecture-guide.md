# A2A + MCP 多代理協同架構指南

> 來源：[A2A Samples - MCP](https://github.com/a2aproject/a2a-samples/tree/main/samples/python/agents/a2a_mcp)

## 一分鐘理解核心概念

這是目前最前沿的「多代理（Agent）協同」設計之一，主軸是**讓各種 AI Agent 可以動態發現彼此、自動合作執行任務**。

### 1. 什麼是 MCP？

**Model Context Protocol（MCP）** 就像是一個「工具/Agent 的總圖書館 + 查號台」：

- 任何 Agent（AI 工具、API、功能服務…）都要先「註冊名片」（Agent Card，類似 API 文件）
- 被放到 MCP 統一管理
- 當你想找能做某件事的 Agent，就來 MCP 搜尋和抓取「Agent Card」，再跟他溝通

### 2. 什麼是 A2A？

**Agent-to-Agent (A2A) protocol** 規範了「兩個 AI Agent 怎麼像 API 那樣互相呼叫」的標準格式：

- 身份識別
- 能做什麼（actions/functions）
- 怎麼互動（endpoint、message 格式）

## 架構工作流程

### 核心組件

1. **MCP Server（註冊中心）**：負責存放所有 Agent Card
2. **Orchestrator Agent（總指揮）**：收到用戶需求，負責調度協調
3. **Planner Agent（規劃師）**：分析需求、拆解任務
4. **Task Agent（執行者）**：各自專精特定功能

### 完整流程示例

假設用戶提出：「我要去法國旅遊」

```
用戶需求：「我要去法國旅遊」
    ↓
Orchestrator Agent 收到需求
    ↓
詢問 Planner Agent 如何拆解
    ↓
Planner 回應：「需要訂機票 → 訂飯店 → 租車」
    ↓
Orchestrator 查詢 MCP：「誰能訂機票？誰能訂飯店？誰能租車？」
    ↓
MCP 回傳可用 Agent Cards
    ↓
Orchestrator 透過 A2A 協議分派任務：
- 機票 Agent：查找巴黎機票
- 飯店 Agent：搜尋巴黎住宿
- 租車 Agent：預訂租車服務
    ↓
收集所有結果，整理後回傳給用戶
```

## 生活化比喻

### MCP = 人才仲介公司 / App Store

你可以想像 MCP 就像一間「人才仲介公司」或「App Store」：

- 要找做設計的、會寫程式的、會會計的（不同 agent）
- MCP 幫你找最適合的 candidate
- 告訴你他的聯絡方式（endpoint）和能力清單（actions）
- 有新人才加入、舊的離職，你不用改產品邏輯
- 只要查詢 MCP 就能拿到最新可用人員名單

## 架構優點

### 🔄 高度動態、可擴展
- 隨時加 agent、改 agent，不用動到 orchestrator
- 新功能即插即用

### 🔧 解耦合設計
- 規劃、調度、任務執行分工明確
- 各組件獨立開發和維護

### 🤖 自動適配
- 根據任務內容自動找最合適的 agent
- 像 AI 版的 microservices

### 📈 容錯與重試
- 任務失敗可自動重試
- 支援動態調整（replanning）

## 實作要點

### Agent Card 結構
每個 Agent 都有一張「名片」，包含：
- 身份資訊（名稱、描述）
- 能力清單（支援的 actions）
- 通訊方式（endpoint、協議）
- 使用說明（參數格式、回傳值）

### MCP Server 職責
- Agent Card 的登記和查詢
- 不參與任務執行
- 可用 file、DB、甚至向量檢索來存放

### Orchestrator Agent 特點
- 不需要知道所有 Agent 細節
- 只要會找 agent_card、用標準格式溝通
- 負責任務分派和結果彙整

### Planner Agent 靈活性
- 可以是 LLM 驅動
- 可以是 LangGraph agent
- 可以是規則引擎

## 適用場景

### 🌟 動態 AI 服務平台
- 需要頻繁新增/移除功能
- 多個 AI 服務需要協同工作
- 要求高度可擴展性

### 🚀 Serverless AI Functions
- LLM agent 動態生成/部署
- 即插即用的服務架構
- 自動化工作流程

### 🏢 企業級 AI 整合
- 整合多個部門的 AI 工具
- 統一的服務發現機制
- 標準化的通訊協議

## 技術實現細節

### MCP 核心功能
```python
# MCP 提供的標準介面
def list_resources():
    """列舉所有可用的 Agent"""
    pass

def get_agent_card(agent_id):
    """查詢特定 Agent 的詳細資訊"""
    pass

def register_agent(agent_card):
    """註冊新的 Agent"""
    pass
```

### A2A 通訊範例
```python
# A2A 標準訊息格式
{
    "agent_id": "hotel_booking_agent",
    "action": "search_hotels",
    "parameters": {
        "location": "Paris",
        "check_in": "2024-06-01",
        "check_out": "2024-06-05"
    }
}
```

## MCP 與 A2A 協同運作機制

### 一分鐘白話對比：A2A 與 MCP 各做什麼？

#### MCP = 註冊中心 + 查號台 + 工具倉庫
- 管「誰是誰、能做什麼」，提供 Agent 的卡片（身份證+API定義）
- 讓 Orchestrator/其他 Agent 可以查詢/篩選/取得 Agent Cards、工具描述、資料資源
- 也可做像 plugin store/resource store/DB query 這種角色

#### A2A = 標準化的 Agent 溝通協定
- 定義「一個 Agent 怎麼直接和另一個 Agent 溝通/下指令/傳遞結果」
- 你有了 Agent Card（MCP查到），才能知道用什麼endpoint、什麼格式、什麼 actions 來調用他
- 真正的 runtime 呼叫、互動、狀態管理，全靠 A2A

### 實際場景流程

假設有三種 Agent（訂機票/訂飯店/租車），MCP 有這三張卡片，A2A 是溝通的語言。

#### Step 1：Orchestrator 要處理「訂機票」
1. 先問 MCP：「有哪些會訂機票的 Agent？」
2. 調用 MCP 的 find_agent 工具，給一個自然語言 query（如 "Book a flight from SFO to LHR"）
3. MCP 回給你最符合的 Agent Card（其實就是一份包含 endpoint/功能/格式的 JSON）

#### Step 2：拿到 Agent Card → 用 A2A 溝通協定跟對方溝通
1. 根據 Agent Card 裡的 endpoint, supported actions，直接用 A2A 協定（比如 REST, SSE, Streaming, whatever）發送 booking request，等對方 streaming 回結果
2. Agent 根據流程問你「缺 cabin class」、「缺出發地」…，你再根據回覆填資料，一直到完成
3. 同理，下一個「訂飯店」也是這樣，先用 MCP 查 agent，再 A2A 溝通

### 流程圖解釋

```
+---------------------+
|    Orchestrator     |           <--- 問題入口
+---------------------+
          |
          |  (1. 查詢)
          v
+---------------------+
|        MCP          |           <--- 註冊中心，查到 agent card (JSON)
+---------------------+
          |
          |  (2. 取得 agent card)
          v
+---------------------+
|   [Task Agent]      |           <--- 根據 card，用A2A跟這個Agent直接通訊/串流
+---------------------+
```

**核心流程**：
1. 先用 MCP 找到正確的 agent（和它的定義/endpoint/能做什麼）
2. 再用 A2A 協定直接執行具體工作與回傳資料

### 具體旅遊場景順序

```
1. User 提需求 → Orchestrator
   ↓
2. Orchestrator 用 MCP 查 find_agent("flight booking") 
   → MCP 回 booking agent 的 Card
   ↓
3. Orchestrator 拿這個 Card（裡面有 endpoint, 功能），用 A2A 協定發請求
   ↓
4. Task Agent (比如 Airline Agent) streaming 回答（A2A格式），要資料再追問，直到完成
   ↓
5. Orchestrator 拿到回覆，再決定下一步（例如去查飯店，重複上面流程）
```

### Agent Card 實際應用範例

#### Hotel Booking Agent 卡片如何被用到

1. **Orchestrator 想訂飯店**，先問 MCP：「有沒有支援 book_accommodation 的 agent？」
2. **MCP 回傳這張卡片**（有 endpoint/功能等資訊）
3. **Orchestrator 依照卡片內容**，建立 A2A 客戶端向 `http://localhost:10104/` 發起 A2A 請求
4. **根據卡片的 skills 描述、inputModes**，包裝對應資料傳送
5. **對方支援 streaming**，Orchestrator 也可以邊收邊處理結果

### 功能對比總結表

| 項目 | MCP | A2A |
|------|-----|-----|
| **負責什麼？** | Agent 註冊/查找/管理 | 代理之間標準化溝通、任務下發 |
| **用來做？** | 找到合適的 agent/資源/工具 | 執行具體的工作、交換資料 |
| **交互格式？** | 工具調用（如 find_agent）、資源查詢（如 agent_cards/list） | message/streaming，task artifact，標準事件格式 |
| **常見入口？** | MCP client/session，或 Agent 內嵌 MCP 查詢 | A2AClient（如 SDK），或 Agent 之間串流 |

### 動態擴充優勢

你只要新增一個 agent，把卡片丟到 MCP 註冊中心，所有用這個 MCP 的 orchestrator/agent 馬上都能發現、查找、選擇它。不用改寫主程式，只要卡片格式正確（有 endpoint、skills、範例），A2A 溝通照走。

### 一句話總結

**MCP 是 agent 註冊、查找和管理的大腦，A2A 是 agent 之間直接互動與任務協作的通用語言。你先透過 MCP 找到誰能做這件事，再用 A2A「跟對方真正講話」。**

## 進階思考

### 🤔 常見問題

**Q: MCP 卡片格式長什麼樣？**
A: 包含 agent 身份、能力、endpoint、參數規格等結構化資訊

**Q: A2A 訊息互動範例？**
A: 標準化的 JSON 格式，包含動作、參數、回傳值規範

**Q: 怎麼讓 LLM 或自訂 agent 也能加入 MCP？**
A: 實作標準的 Agent Card 格式和 A2A 通訊協議即可

**Q: 要怎麼改成自己的任務場景？**
A: 定義你的任務類型，創建對應的 Planner 和 Task Agents

## 未來發展方向

### 🔮 技術演進
- 更智能的任務規劃算法
- 基於向量搜索的 Agent 發現
- 自動化的 Agent 組合優化

### 🌐 生態系統
- 標準化的 Agent Marketplace
- 跨平台的 Agent 互操作性
- 社群驅動的 Agent 開發

## 總結

這套 A2A + MCP 架構代表了 AI 工程的未來方向：

- **動態性**：Agent 可以即插即用
- **標準化**：統一的發現和通訊協議
- **智能化**：自動任務分解和執行
- **可擴展**：輕鬆添加新功能和服務

這種設計特別適合需要高度靈活性和可擴展性的 AI 應用場景，是現代 AI 工程師必須掌握的重要架構模式。