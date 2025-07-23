# A2A Expense Reimbursement Agent 實作指南

> 來源：[A2A Samples - ADK Expense Reimbursement](https://github.com/a2aproject/a2a-samples/tree/main/samples/python/agents/adk_expense_reimbursement)

## 一分鐘理解核心概念

這是一個**費用報銷（Expense Reimbursement）任務的 AI Agent 實作範例**，在 A2A 框架下演示了如何讓 LLM 驅動的代理人模擬「線上報銷流程」，並可直接整合到 A2A 工作流中自動串聯。

### 核心功能
- **互動式表單填寫**：動態生成和處理報銷表單
- **資訊收集與驗證**：逐步收集必要的報銷資訊
- **自動化審批流程**：基於規則的簡單審批機制
- **A2A 協議整合**：可與其他 Agent 無縫協作

## 系統工作流程

### 完整報銷流程

```
用戶提出報銷請求
    ↓
Agent 判斷資訊完整性
    ↓
缺少資訊 → 動態生成表單 → 用戶填寫
    ↓
資訊完整 → 執行審批邏輯
    ↓
回傳審批結果（批准/拒絕）
```

### 實際交互範例

```
1. 用戶：「我要報銷6月24日出差倫敦的機票 500 美元」
   ↓
2. Agent 分析：有日期、金額，缺少詳細用途說明
   ↓
3. 生成表單：請補充「business justification/purpose」
   ↓
4. 用戶填寫：「Business trip to London for client meeting」
   ↓
5. 資訊完整 → 調用 reimburse() → 回傳「status: approved」
```

## 技術架構解析

### 1. ReimbursementAgentExecutor（A2A 橋接層）

#### 核心職責
負責處理 A2A 協議進來的請求，並將其轉換為內部 Agent 可處理的格式。

#### 關鍵實現
```python
class ReimbursementAgentExecutor(AgentExecutor):
    def __init__(self):
        self.agent = ReimbursementAgent()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        query = context.get_user_input()
        task = context.current_task
        
        # 創建任務更新器
        updater = TaskUpdater(event_queue, task.id, task.contextId)
        
        # 流式處理 Agent 回應
        async for item in self.agent.stream(query, task.contextId):
            if item['is_task_complete']:
                # 處理完成狀態
                await updater.add_artifact([Part(root=TextPart(text=item['content']))], name='form')
                await updater.complete()
            else:
                # 處理進行中狀態
                await updater.update_status(TaskState.working, new_agent_text_message(item['updates']))
```

#### 重要設計特點
1. **任務狀態管理**：支援 working、input_required、completed、failed 等狀態
2. **流式處理**：實時回傳處理進度
3. **錯誤處理**：優雅處理異常狀況

### 2. ReimbursementAgent（核心業務邏輯）

#### 核心職責
使用 Google ADK 框架實現的 LLM Agent，負責實際的報銷流程處理。

#### 工具函數設計

**create_request_form() - 動態表單生成**
```python
def create_request_form(date: str = None, amount: str = None, purpose: str = None) -> dict:
    """創建報銷申請表單，缺少的欄位會顯示提示文字"""
    request_id = 'request_id_' + str(random.randint(1000000, 9999999))
    return {
        'request_id': request_id,
        'date': '<transaction date>' if not date else date,
        'amount': '<transaction dollar amount>' if not amount else amount,
        'purpose': '<business justification/purpose>' if not purpose else purpose,
    }
```

**return_form() - 結構化表單回傳**
```python
def return_form(form_request: dict, tool_context: ToolContext, instructions: str = None) -> dict:
    """將表單資料組裝成結構化 JSON 格式"""
    form_dict = {
        'type': 'form',
        'form': {
            'type': 'object',
            'properties': {
                'date': {'type': 'string', 'format': 'date', 'title': 'Date'},
                'amount': {'type': 'string', 'format': 'number', 'title': 'Amount'},
                'purpose': {'type': 'string', 'title': 'Purpose'},
                'request_id': {'type': 'string', 'title': 'Request ID'},
            },
            'required': list(form_request.keys()),
        },
        'form_data': form_request,
        'instructions': instructions,
    }
    return json.dumps(form_dict)
```

**reimburse() - 審批執行**
```python
def reimburse(request_id: str) -> dict:
    """執行報銷審批邏輯"""
    if request_id not in request_ids:
        return {'request_id': request_id, 'status': 'Error: Invalid request_id.'}
    return {'request_id': request_id, 'status': 'approved'}
```

#### Agent 配置與指令

```python
def _build_agent(self) -> LlmAgent:
    return LlmAgent(
        model=LiteLlm(model='gemini/gemini-2.0-flash-001'),
        name='reimbursement_agent',
        description='處理員工報銷流程的代理人',
        instruction="""
        你是處理員工報銷的代理人。收到報銷請求時：
        
        1. 首先使用 create_request_form() 創建申請表單
        2. 檢查是否包含所有必要資訊：日期、金額、業務用途
        3. 如果資訊不完整，使用 return_form() 要求用戶補充
        4. 資訊完整後，使用 reimburse() 執行審批
        5. 回傳包含 request_id 和審批狀態的結果
        """,
        tools=[create_request_form, reimburse, return_form],
    )
```

### 3. 流式處理機制

#### 核心實現
```python
async def stream(self, query, session_id) -> AsyncIterable[dict[str, Any]]:
    # 獲取或創建會話
    session = await self._runner.session_service.get_session(
        app_name=self._agent.name, user_id=self._user_id, session_id=session_id
    ) or await self._runner.session_service.create_session(
        app_name=self._agent.name, user_id=self._user_id, session_id=session_id
    )
    
    # 處理用戶輸入
    content = types.Content(role='user', parts=[types.Part.from_text(text=query)])
    
    # 流式執行並回傳結果
    async for event in self._runner.run_async(user_id=self._user_id, session_id=session.id, new_message=content):
        if event.is_final_response():
            # 處理最終回應
            yield {'is_task_complete': True, 'content': response}
        else:
            # 處理中間狀態
            yield {'is_task_complete': False, 'updates': self.get_processing_message()}
```

## 系統特點分析

### ✅ 優勢特點

1. **高度自動化**
   - 自動判斷資訊完整性
   - 動態生成所需表單
   - 無需手寫複雜的條件判斷邏輯

2. **靈活的互動機制**
   - 支援多輪對話
   - 可暫停等待用戶輸入
   - 流式回傳處理進度

3. **標準化整合**
   - 完全符合 A2A 協議
   - 可與其他 Agent 無縫協作
   - 支援 MCP 註冊和發現

4. **可擴展架構**
   - 基於 Function Calling 的工具系統
   - 易於添加新的驗證規則
   - 支援複雜的審批流程

### ⚠️ 當前限制

1. **簡化的驗證邏輯**
   - 只檢查欄位是否填寫完整
   - 沒有內容合理性驗證
   - 缺少公司政策規則檢查

2. **基礎的資料存儲**
   - request_id 只存在記憶體中
   - 沒有持久化的資料庫
   - 缺少歷史記錄和查詢功能

3. **簡單的審批機制**
   - 只有批准/拒絕兩種狀態
   - 沒有多層審批流程
   - 缺少權限和角色管理

## 企業級擴展方向

### 資料持久化
```python
# 添加資料庫支援
class DatabaseManager:
    async def save_request(self, request_data: dict) -> str:
        # 保存到資料庫並返回 request_id
        pass
    
    async def get_request(self, request_id: str) -> dict:
        # 從資料庫查詢申請記錄
        pass
```

### 合規性驗證
```python
def validate_expense(amount: float, purpose: str, category: str) -> dict:
    """驗證費用是否符合公司政策"""
    # 檢查金額上限
    # 驗證費用類別
    # 檢查用途合理性
    pass
```

### 多層審批流程
```python
def get_approval_workflow(amount: float, department: str) -> list:
    """根據金額和部門決定審批流程"""
    # 小額：直接主管審批
    # 中額：部門主管 + 財務審批
    # 大額：多層審批流程
    pass
```

## 實際應用場景

### 🏢 企業內部系統
- **HR 系統整合**：員工報銷申請自動化
- **財務流程**：費用審批和記帳自動化
- **差旅管理**：出差費用報銷標準化

### 🔄 工作流整合
- **多 Agent 協作**：與差旅預訂、發票處理等 Agent 協同
- **ERP 系統對接**：與企業資源規劃系統整合
- **通知系統**：自動發送審批通知和狀態更新

### 📊 數據分析
- **費用統計**：部門和個人費用分析
- **合規監控**：異常費用自動標記
- **預算管理**：實時預算使用追蹤

## 開發指南

### 快速開始
1. **環境設置**：安裝 A2A SDK 和 Google ADK
2. **配置模型**：設置 LiteLLM 和 Gemini 模型
3. **工具註冊**：實現自定義的業務邏輯工具
4. **測試驗證**：使用 A2A 客戶端測試功能

### 自定義擴展
1. **添加新工具**：實現額外的業務邏輯函數
2. **修改 Prompt**：調整 Agent 的行為指令
3. **整合外部系統**：連接資料庫和第三方 API
4. **部署配置**：設置生產環境的運行參數

## 總結

這個 A2A Expense Reimbursement Agent 展示了如何使用現代 AI 技術構建智能的業務流程自動化系統。雖然當前實現相對簡化，但其架構設計為企業級擴展提供了堅實的基礎。

### 關鍵價值
- **技術示範**：展示 A2A + ADK 的實際應用
- **架構參考**：提供可擴展的系統設計模式
- **開發基礎**：為企業級報銷系統提供起點

這種設計特別適合需要高度自動化和智能化的企業內部流程，是現代 AI 驅動業務流程自動化的優秀範例。