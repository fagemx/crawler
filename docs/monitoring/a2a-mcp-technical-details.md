# A2A + MCP 關鍵技術細節深度解析

> 延續 [A2A + MCP 架構指南](./a2a-mcp-architecture-guide.md)，深入探討核心組件的技術實現

## 核心組件技術解析

### 1. OrchestratorAgent（協調代理，主控台）

#### 核心職責
負責管理整個「多步驟任務」的流程、狀態、節點與 Agent 調度，本質上像一個「流程引擎 + 進度管理員」。

#### 技術細節

**WorkflowGraph 建模**
```python
class OrchestratorAgent(BaseAgent):
    def __init__(self):
        self.graph = None  # WorkflowGraph 實例
        self.results = []  # 累積所有子任務結果
        self.travel_context = {}  # 旅遊上下文資訊
        self.query_history = []  # 查詢歷史
        self.context_id = None  # 會話 ID
```

**動態狀態管理**
- 用 WorkflowGraph 儲存所有進度與中間結果
- 支援 Pause/Resume（可等待更多資訊或使用者輸入）
- 可重試、追溯、debug

**多階段回饋機制**
```python
# 處理任務狀態更新
if task_status_event.status.state == TaskState.input_required:
    question = task_status_event.status.message.parts[0].root.text
    answer = json.loads(self.answer_user_question(question))
    if answer['can_answer'] == 'yes':
        # 自動回答並恢復工作流
        query = answer['answer']
        start_node_id = self.graph.paused_node_id
        should_resume_workflow = True
```

**自動總結與問答**
```python
async def generate_summary(self) -> str:
    client = genai.Client()
    response = client.models.generate_content(
        model='gemini-2.0-flash',
        contents=prompts.SUMMARY_COT_INSTRUCTIONS.replace(
            '{travel_data}', str(self.results)
        ),
        config={'temperature': 0.0},
    )
    return response.text
```

#### 重要設計特點

1. **動態節點管理**：每步執行都會生成新的節點，並串聯在圖上（DAG）
2. **狀態更新與協同通訊**：用 TaskStatusUpdateEvent 等訊息通知各步完成、失敗或等待輸入
3. **智能問答**：可根據上下文主動回答用戶問題或請求更多資訊

### 2. LangGraphPlannerAgent（任務分解規劃代理）

#### 核心職責
負責把一個大問題（如「我要去法國」）拆解成一連串具體可執行的小任務，回傳結構化計畫。

#### 技術細節

**結構化輸出格式**
```python
class ResponseFormat(BaseModel):
    """Respond to the user in this format."""
    status: Literal['input_required', 'completed', 'error'] = 'input_required'
    question: str = Field(description='Input needed from the user to generate the plan')
    content: TaskList = Field(description='List of tasks when the plan is generated')
```

**LangGraph 整合**
```python
class LangGraphPlannerAgent(BaseAgent):
    def __init__(self):
        self.model = ChatGoogleGenerativeAI(model='gemini-2.0-flash', temperature=0.0)
        self.graph = create_react_agent(
            self.model,
            checkpointer=memory,
            prompt=prompts.PLANNER_COT_INSTRUCTIONS,
            response_format=ResponseFormat,
            tools=[],
        )
```

**流式處理**
```python
async def stream(self, query, sessionId, task_id) -> AsyncIterable[dict[str, Any]]:
    inputs = {'messages': [('user', query)]}
    config = {'configurable': {'thread_id': sessionId}}
    
    for item in self.graph.stream(inputs, config, stream_mode='values'):
        message = item['messages'][-1]
        if isinstance(message, AIMessage):
            yield {
                'response_type': 'text',
                'is_task_complete': False,
                'require_user_input': False,
                'content': message.content,
            }
```

#### 重要設計特點

1. **結構化輸出**：保證流程的每一步結果都能用程式碼讀取
2. **可插拔/可組合**：可以換成別的 LLM 或不同的任務規劃模板
3. **狀態管理**：支援多輪對話和上下文保持

### 3. TravelAgent（ADK-based 專家代理）

#### 核心職責
負責實際完成分配到的具體任務，並與 MCP 註冊中心同步支援的新工具/資料源。

#### 技術細節

**動態工具載入**
```python
async def init_agent(self):
    config = get_mcp_server_config()
    tools = await MCPToolset(
        connection_params=SseServerParams(url=config.url)
    ).get_tools()
    
    for tool in tools:
        logger.info(f'Loaded tools {tool.name}')
    
    self.agent = Agent(
        name=self.agent_name,
        instruction=self.instructions,
        model=LiteLlm(model=LITELLM_MODEL),
        tools=tools,  # 動態載入的工具
    )
```

**智能回應格式化**
```python
def format_response(self, chunk):
    patterns = [
        r'```\n(.*?)\n```',
        r'```json\s*(.*?)\s*```',
        r'```tool_outputs\s*(.*?)\s*```',
    ]
    for pattern in patterns:
        match = re.search(pattern, chunk, re.DOTALL)
        if match:
            content = match.group(1)
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return content
    return chunk
```

**流式執行**
```python
async def stream(self, query, context_id, task_id) -> AsyncIterable[dict[str, Any]]:
    if not self.agent:
        await self.init_agent()
    
    async for chunk in self.runner.run_stream(self.agent, query, context_id):
        if isinstance(chunk, dict) and chunk.get('type') == 'final_result':
            response = chunk['response']
            yield self.get_agent_response(response)
        else:
            yield {
                'is_task_complete': False,
                'require_user_input': False,
                'content': f'{self.agent_name}: Processing Request...',
            }
```

#### 重要設計特點

1. **完全模組化**：一個任務一個 agent，專注單一責任
2. **動態工具鏈接**：MCP 提供所有可用資源清單，支援即插即用
3. **例外/錯誤回報一致**：標準格式回報，避免系統不可控例外

## 綜合設計亮點

### 🏗️ 分層架構、分責明確

```
UI/CLI
    ↓
OrchestratorAgent (流程和協作)
    ↓
PlannerAgent (任務拆解) + TaskAgent (專業執行)
    ↓
MCP Server (資源註冊與發現)
```

### 🔄 動態資源註冊與發現（MCP）

- Agent 可以無痛增減，支援即插即用
- 新功能上線/下架不需要動到 agent 本體
- 只要 MCP 更新就能自動支援

### 📊 工作流圖（WorkflowGraph/DAG）

- 保證複雜多步驟流程可追蹤
- 支援暫停/恢復/重試/回饋
- 完整的狀態管理和錯誤處理

### 📡 強結構化訊息傳遞

**標準 A2A 協議格式**
```python
{
    "response_type": "data",  # 或 "text"
    "is_task_complete": True,
    "require_user_input": False,
    "content": {
        "status": "completed",
        "data": {...}
    }
}
```

### 🔧 串接 LLM/工具與資料庫

- 無縫切換不同 agent 技術棧
- ADK、LangGraph、OpenAI Function-Calling 等
- 只要包裝成標準 agent 卡片即可

## 流程圖心法

```
用戶請求
    ↓
OrchestratorAgent 接收需求與狀態管理
    ↓
呼叫 MCP Server 查找合適的 Agent Card
    ↓
A2A 溝通請求 → TaskAgent/PlannerAgent
    ↓
收集結果、回饋使用者、需要時主動問問題
    ↓
生成總結並完成任務
```

## 實作重點總結

### 🎯 如果你想模仿這種架構

1. **分工與協同全部標準化**
   - 所有 agent 都用同一組 discovery + 通訊協議（MCP + A2A）
   - 自動整合，無需手動配置

2. **多層代理結構**
   - 允許逐步拆解與執行
   - 適合任何「大型、多步驟、可拆解」的任務編排場景

3. **極度適合現代 AI 應用**
   - AI 工作流自動化
   - AI toolchain 管理
   - 智慧型協同軟體

## 進階探討方向

如果你想深入了解更細節的實作：

- **MCP Toolset 運作原理**：如何動態載入和管理工具
- **WorkflowGraph 實作邏輯**：DAG 的建構和執行機制
- **ADK/LangGraph 整合細節**：不同框架的整合方式
- **A2A 實際消息流**：協議的具體實現和通訊機制
- **自訂 agent 卡片/工具**：如何擴展系統功能

## 技術棧總覽

### 核心框架
- **Google ADK**：Agent 開發工具包
- **LangGraph**：工作流程圖框架
- **OpenTelemetry**：分散式追蹤
- **MCP Protocol**：模型上下文協議

### LLM 整合
- **Google Gemini 2.0 Flash**：主要 LLM 模型
- **LiteLLM**：多模型統一介面
- **Structured Output**：結構化回應格式

### 基礎設施
- **Pydantic**：資料驗證和序列化
- **AsyncIO**：非同步程式設計
- **JSON Schema**：資料格式定義

這份技術細節指南提供了完整的實作參考，讓你能夠理解和複製這種先進的多代理協同架構。