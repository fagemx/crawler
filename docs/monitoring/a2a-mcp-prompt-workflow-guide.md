# A2A + MCP Prompt 驅動工作流指南

> 延續技術細節，專注於 Prompt Engineering + 工作流管理的核心實現

## 核心設計理念

這是 A2A + MCP 多代理協同架構的「高階運作細節」，實現高自動化、結構化決策、多回合推理的關鍵技術。

### 系統核心：四大支柱

1. **Prompt 驅動**：每個 Agent 都有明確的系統提示
2. **決策樹**：結構化的資訊收集流程
3. **Chain-of-Thought**：逐步推理和詢問機制
4. **強結構化流程**：標準化的回應格式

## Agent Prompt 設計模式

### 決策樹 + Chain-of-Thought 範例

以 **Airfare Agent** 為例：

```python
AIRFARE_COT_INSTRUCTIONS = """
You are an Airline ticket booking / reservation assistant.

DECISION TREE:
1. Origin - If unknown, ask for origin
2. Destination - If unknown, ask for destination  
3. Dates - If unknown, ask for start and return dates
4. Class - If unknown, ask for cabin class

CHAIN-OF-THOUGHT PROCESS:
Before each response, reason through:
1. What information do I already have? [List all known information]
2. What is the next unknown information in the decision tree? [Identify gap]
3. How should I naturally ask for this information? [Formulate question]
4. What context from previous information should I include? [Add context]
5. If I have all the information I need, I should now proceed to search

Response format:
{"status": "input_required", "question": "What cabin class do you wish to fly?"}
"""
```

### 關鍵設計特點

#### 🎯 明確的步驟定義
- 每一個步驟、判斷點、資料模型、回應格式都明確定義
- 用範例、enum、schema 綁定，保證下游自動化流程能直接解析

#### 🧠 推理引擎化
- 強制 AI 每一步都「思考已知/未知、判斷資訊缺口、自然詢問、補充上下文」
- 防止「亂猜」，條件沒湊齊就不會往下走

#### 📊 結構化輸出
```python
# 標準回應格式
{
    "status": "completed",
    "onward": {
        "airport": "SFO",
        "date": "2025-06-01", 
        "airline": "United",
        "flight_number": "UA123",
        "travel_class": "BUSINESS",
        "cost": "1200"
    },
    "total_price": "2400"
}
```

## WorkflowGraph：動態多步任務協作

### WorkflowNode 核心功能

```python
class WorkflowNode:
    def __init__(self, task: str, node_key: str = None, node_label: str = None):
        self.id = str(uuid.uuid4())
        self.node_key = node_key  # 'planner' 或 task agent
        self.node_label = node_label
        self.task = task
        self.results = None
        self.state = Status.READY
    
    async def run_node(self, query: str, task_id: str, context_id: str):
        # 1. 根據 node_key 決定找 planner 還是 task agent
        if self.node_key == 'planner':
            agent_card = await self.get_planner_resource()
        else:
            agent_card = await self.find_agent_for_task()
        
        # 2. 透過 A2A 與 agent 溝通
        # 3. 支援 streaming 回傳任務進度
```

### WorkflowGraph 狀態管理

```python
class Status(Enum):
    READY = 'READY'
    RUNNING = 'RUNNING' 
    COMPLETED = 'COMPLETED'
    PAUSED = 'PAUSED'        # 關鍵：支援暫停等待輸入
    INITIALIZED = 'INITIALIZED'

class WorkflowGraph:
    def __init__(self):
        self.graph = nx.DiGraph()  # 有向圖
        self.nodes = {}
        self.state = Status.INITIALIZED
        self.paused_node_id = None  # 記錄暫停的節點
```

### Pause/Resume 機制

```python
async def run_workflow(self, start_node_id: str = None):
    # 拓撲排序執行節點
    sub_graph = list(nx.topological_sort(self.graph))
    
    for node_id in sub_graph:
        node = self.nodes[node_id]
        node.state = Status.RUNNING
        
        async for chunk in node.run_node(query, task_id, context_id):
            # 檢查是否需要暫停等待輸入
            if task_status_event.status.state == TaskState.input_required:
                node.state = Status.PAUSED
                self.state = Status.PAUSED
                self.paused_node_id = node.id
                yield chunk
                
        if self.state == Status.PAUSED:
            break  # 暫停整個工作流
```

## 專業 Agent Prompt 範例

### Hotel Agent 決策樹

```python
HOTELS_COT_INSTRUCTIONS = """
DECISION TREE:
1. City - If unknown, ask for the city
2. Dates - If unknown, ask for checkin and checkout dates  
3. Property Type - If unknown, ask for Hotel, AirBnB or private property
4. Room Type - If unknown, ask for Suite, Standard, Single, Double

DATAMODEL:
CREATE TABLE hotels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    city TEXT NOT NULL, 
    hotel_type TEXT NOT NULL,  -- 'HOTEL', 'AIRBNB', 'PRIVATE_PROPERTY'
    room_type TEXT NOT NULL,   -- 'STANDARD', 'SINGLE', 'DOUBLE', 'SUITE'
    price_per_night REAL NOT NULL
)

RESPONSE:
{
    "name": "[HOTEL_NAME]",
    "city": "[CITY]", 
    "hotel_type": "[ACCOMMODATION_TYPE]",
    "room_type": "[ROOM_TYPE]",
    "price_per_night": "[PRICE_PER_NIGHT]",
    "total_rate_usd": "[TOTAL_RATE]",
    "status": "completed"
}
"""
```

### Planner Agent 完整流程

```python
PLANNER_COT_INSTRUCTIONS = """
You are an ace trip planner.

DECISION TREE: (14 steps)
1. Origin → 2. Destination → 3. Dates → 4. Budget → 5. Type of travel
→ 6. No of travelers → 7. Class → 8. Checkin/Checkout dates 
→ 9. Property Type → 10. Room Type → 11. Car Rental Requirement
→ 12. Type of car → 13. Car Rental dates → 14. Generate tasks

Output format:
{
    'original_query': 'Plan my trip to London',
    'trip_info': {
        'total_budget': '5000',
        'origin': 'San Francisco',
        'destination': 'London',
        'start_date': '2025-05-12',
        'end_date': '2025-05-20'
    },
    'tasks': [
        {
            'id': 1,
            'description': 'Book round-trip economy class air tickets...',
            'status': 'pending'
        },
        {
            'id': 2, 
            'description': 'Book a suite room at a hotel...',
            'status': 'pending'
        }
    ]
}
"""
```

## 智能問答與總結系統

### QA Chain-of-Thought

```python
QA_COT_PROMPT = """
Step 1: Context Analysis
- Read trip details and conversation history
- Identify available information fields

Step 2: Question Understanding  
- Parse what information is being requested
- Identify specific data points needed

Step 3: Information Matching
- Search through JSON context for relevant information
- Check if all required data points are available

Step 4: Answer Determination
- If complete info available: formulate answer
- If partial info: determine if sufficient  
- If missing critical info: cannot answer

Response format:
{
    "can_answer": "yes" or "no",
    "answer": "Your answer here" or "Cannot answer based on provided context"
}
"""
```

### 總結生成系統

```python
SUMMARY_COT_INSTRUCTIONS = """
## Chain of Thought Process

### Step 1: Data Parsing and Validation
- Parse data structure and identify all travel components

### Step 2: Flight Information Analysis  
- Route information, schedule details, costs

### Step 3: Hotel Information Analysis
- Property details, dates, costs

### Step 4: Car Rental Analysis
- Vehicle details, rental duration, costs

### Step 5: Budget Analysis
- Individual cost categories, total trip cost

Generate comprehensive summary with:
- Trip Overview
- Flight Details (Outbound/Return)
- Accommodation Details  
- Ground Transportation
- Financial Summary
"""
```

## 實際執行流程

### 完整交互範例

```
1. User: "Plan my trip to London"
   ↓
2. Orchestrator 創建 WorkflowGraph
   ↓  
3. 添加 Planner Node → 執行決策樹收集資訊
   ↓
4. Planner 完成後返回 3 個任務：
   - Task 1: 訂機票 (Airfare Agent)
   - Task 2: 訂飯店 (Hotel Agent)  
   - Task 3: 租車 (Car Agent)
   ↓
5. 每個 Task Node 依序執行：
   - 透過 MCP 找到對應 Agent Card
   - 用 A2A 協議溝通
   - 執行各自的決策樹流程
   ↓
6. 所有任務完成 → 生成總結報告
```

## LLM 調用分析

### 核心特點：流程分層與動態調用

這套架構的精華在於「流程分層，每一層都可能會多次調用 LLM，且這些調用是動態且可追蹤的」。每個大步驟都可能觸發 1～多次 LLM 呼叫，還有 Decision Tree + Chain-of-Thought + State machine 控制。

### 全流程 LLM 調用次數總覽

一次完整的旅遊規劃請求會有哪些 LLM 調用？

假設用戶從零開始問：「幫我規劃一趟五月去倫敦的旅行」

#### 主要流程分層

1. **OrchestratorAgent**：只負責串接，不主動 LLM 呼叫，除了 summary、回答補充問題時（可能 1-2 次）

2. **PlannerAgent (LLM, LangGraph)**：
   - 接收到用戶 query → 反覆 Chain-of-Thought 拆解詢問
   - 直到湊齊完整任務規劃資訊（起點、終點、日期、預算...）
   - 每「不完整」一次都會呼叫 LLM 產生下一個問題
   - 完整資訊後，產生結構化任務清單（通常一次 LLM call）
   - **調用次數**：根據用戶輸入完整度，大約 2～7 次 LLM 調用

3. **每一個 Task Agent（Airfare、Hotels、Cars）**：
   - 根據 instruction/decision tree 反覆判斷、詢問、湊齊所有 booking info
   - 採用 Chain-of-Thought：每缺一個資料就觸發 LLM call
   - 如果查詢結果沒有符合條件，還會 fallback/再詢問用戶
   - **調用次數**：每一個任務可能 1-5 次 LLM 調用

4. **SummaryAgent (Orchestrator 內嵌)**：
   - 最後所有任務完成後，用 LLM 把所有資料組合成旅遊總結
   - **調用次數**：通常是 1 次 LLM call

### 典型請求的調用次數估算

#### 用戶只給「我要去倫敦」的情況

```
PlannerAgent 需詢問：起點、日期、預算、房型、是否租車...
→ 約 3~7 次 LLM call

拆出 3 個任務：訂機票、訂飯店、租車
每一個任務再多次 Chain-of-Thought 判斷/追問/查詢：

• 機票 Agent：出發地、目的地、日期、艙等 → 約 2~4 次
• 飯店 Agent：城市、入住/退房、房型等 → 約 2~4 次  
• 租車 Agent：城市、日期、車種 → 約 2~3 次

Orchestrator 最後 summary 回給用戶 → 1次

總計：一次完整對話下來，LLM 調用次數可能是 10~20 次
（甚至更多，取決於資訊完整度、流程中有無例外/重試/補問）
```

### 流程化拆解——每一步的 LLM 調用

以**「用戶什麼資訊都沒給」**的狀況分步說明：

#### Step 1: User → OrchestratorAgent
```
User: 「幫我規劃倫敦旅遊」
Orchestrator 接收 query，建立 workflow graph
```

#### Step 2: Orchestrator → PlannerAgent (LLM)
```
Planner 收到 query，發現資訊不足

LLM Call 1：判斷缺什麼（如起點）→ 產生「請問你的出發地？」
→ Orchestrator 轉回問 user → User 回答

LLM Call 2：判斷還缺什麼（如出發/回程日期）→「出發/回程日期？」
→ Orchestrator 轉回問 user → User 回答

依此類推，直到所有資訊齊全，這過程每缺一項資訊就 LLM Call 一次

最後一次 LLM Call：產生結構化 task list（航班/飯店/租車）
```

#### Step 3: Orchestrator 拆解任務，啟動子任務

**3.1 Airfare Agent（LLM）**
```
Agent 收到「訂 SFO 到 LHR 的機票，5/12-5/20」
若有缺項（如艙等），LLM Call → 請問艙等？
用戶回答
資訊湊齊後，LLM 根據 Prompt，組合 SQL 查詢資料庫，回傳結果
如果沒找到符合條件，再 fallback 一次（LLM Call → 問要不要升級艙等等）
```

**3.2 Hotels Agent（LLM）**
```
類似機票流程：確認城市、日期、住宿類型、房型
每缺一項 LLM Call 一次，直到查詢完成
```

**3.3 Car Rental Agent（LLM）**
```
確認城市、日期、車種等，每缺一項 LLM Call 一次，直到查詢完成
```

#### Step 4: Orchestrator 彙整所有結果，產生 summary
```
LLM Call：依照 summary prompt，自動整理完整旅遊規劃，回給用戶
```

### 動態調用的控制機制

#### 🔄 自動化調用控制
- 所有 LLM 呼叫次數是動態且自動的，不必寫死判斷
- 每一階層 agent 都可以「多次 LLM 調用」進行逐步推理、決策、追問
- 任何時候用戶/環境回應不全，流程都能暫停/resume

#### 📊 狀態追蹤機制
- 所有回傳都強結構化，自動串聯上下游 agent，無人工調整
- 流程圖/狀態全記錄、可追蹤可 debug
- 流程的每一步都對應一個 node/agent，可以獨立擴展和升級

#### 🎯 核心亮點總結
- 每一階層 agent 都可以「多次 LLM 調用」進行逐步推理、決策、追問，直到獲得完整資料
- 任何時候用戶/環境回應不全，流程都能暫停/resume
- 所有回傳都強結構化，自動串聯上下游 agent，無人工調整
- 流程圖/狀態全記錄、可追蹤可 debug

### 流程圖簡化版

```
User → Orchestrator → PlannerAgent (多次LLM調用收集資訊)
                           ↓
            拆成多個Task（航班/飯店/租車）
                           ↓
          Orchestrator串流啟動多個Task Agent
            └→ AirfareAgent (多次LLM調用收集與查詢)
            └→ HotelsAgent (多次LLM調用收集與查詢)
            └→ CarsAgent   (多次LLM調用收集與查詢)
                           ↓
              所有Task完成，Orchestrator彙整
                           ↓
              Summary LLM 產生總結，回給User
```

### 錯誤處理與 Fallback

```python
# Agent 找不到符合條件時的處理
if search_results.empty():
    return {
        "status": "input_required",
        "question": "I could not find any flights that match your criteria, but I found tickets in First Class, would you like to book that instead?"
    }
```

## 系統優勢總結

### 🏗️ 架構優勢

1. **結構化 + 標準化**：確保 Agent 間協作高度穩定
2. **靈活可插拔**：MCP 註冊中心實現即插即用
3. **自動多步推理**：複雜任務拆解與協同
4. **狀態管理**：支援暫停/恢復/重試/回饋

### 🚀 技術創新

1. **Prompt Engineering**：決策樹 + Chain-of-Thought 結合
2. **DAG Workflow**：NetworkX 驅動的動態工作流
3. **A2A/MCP Protocol**：標準化的 Agent 通訊
4. **LLM 結構化輸出**：避免 hallucination 和格式錯誤

### 💡 應用場景

- **AI 工作流自動化**：複雜業務流程的智能化
- **AI Toolchain 管理**：工具和服務的動態組合
- **智慧型協同軟體**：多 Agent 協作系統

## 擴展指南

### 添加新 Agent 的步驟

1. **設計決策樹**：定義資訊收集流程
2. **編寫 Prompt**：包含 Chain-of-Thought 推理
3. **定義資料模型**：結構化的輸入輸出格式
4. **創建 Agent Card**：註冊到 MCP Server
5. **測試整合**：驗證與 Orchestrator 的協作

### 最佳實踐

- **Prompt 設計**：明確的步驟、範例、錯誤處理
- **狀態管理**：完整的暫停/恢復機制
- **錯誤處理**：優雅的 fallback 和重試邏輯
- **監控追蹤**：完整的執行軌跡記錄

這套系統代表了 AI Native Workflow 協作的最前沿技術，將 LLM 的推理能力與工程化的流程管理完美結合。