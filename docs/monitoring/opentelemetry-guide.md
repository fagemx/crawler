# OpenTelemetry (OTel) 完整指南

## 一句話解釋

OpenTelemetry（OTel）是一個標準和工具組，讓你可以在自己的程式碼裡，輕鬆記錄每一步發生了什麼，並且把這些「追蹤資訊」傳到一個可視化平台（像 Jaeger、Grafana、Datadog）來分析整個系統的行為與瓶頸。

## 生活比喻

假設你有一間餐廳，有很多部門（點餐、煮菜、送餐、結帳）。你想知道：

- 每個客人從點餐到吃到飯，到離開，到底經過了哪些步驟？
- 每個步驟花多少時間？
- 哪個環節最容易卡住？

OpenTelemetry 就像一個「隱形的監察員」，會自動在每個流程點都記錄「現在在做什麼、花了多久」，等到客人走了（一次請求完成），你就能在一張圖表上看到完整流程樹：

```
先點餐 → 等廚房 → 上菜 → 吃飯 → 結帳
點餐花 2 分鐘，廚房等了 10 分鐘，上菜 1 分鐘，吃飯 30 分鐘...
```

## 程式/技術的解釋

### 1. OTel 可以做什麼？

- 幫你自動或手動記錄每個「請求」經過的所有步驟
- 支援分散式系統（多台服務/多個語言/多個服務串來串去）
- 把這些資料「export」到追蹤平台（如 Jaeger、Grafana Tempo、Datadog）

### 2. 關鍵字說明

- **Trace（追蹤）**：一個完整的請求過程（像上一段客人的全流程）
- **Span（片段）**：流程中的每一小段（像「點餐」、「等廚房」、「上菜」）
- **Instrumentation**：在程式裡插追蹤點（有自動/手動兩種）

### 3. 支援很多語言

Python、Go、Java、Node.js...（基本上主流語言都有 SDK）

## 實際程式碼小範例（Python）

```python
from opentelemetry import trace

tracer = trace.get_tracer("restaurant-app")

def order_food():
    with tracer.start_as_current_span("點餐"):
        # 做點餐的邏輯
        pass

def cook_food():
    with tracer.start_as_current_span("煮菜"):
        # 做煮菜的邏輯
        pass

def serve_food():
    with tracer.start_as_current_span("上菜"):
        # 做上菜的邏輯
        pass

def main_flow():
    order_food()
    cook_food()
    serve_food()
```

這樣你每跑一次 `main_flow`，就會在 Jaeger/Grafana 看到一個完整流程，清楚知道每段花多少時間。

## 重點總結

- OTel 是一套通用標準 + SDK工具，記錄並傳送程式裡的「發生了什麼事」
- 最終讓你在視覺化平台看到所有服務/流程的每個細節，輕鬆定位慢點、bug、異常
- 你只要會在程式碼裡插 trace，就能用現成的 Jaeger/Grafana 追蹤分析，不管你是 AI agent、web 服務還是 API

## 小提示

- 很多 Web 框架/資料庫/HTTP 請求庫已經有自動 instrumentation，甚至不用自己插太多程式碼！
- OTel 的 trace id 可以自動串連跨服務的請求（從 API → AI Agent → 資料庫，每一層都接起來）

## A2A (Agent-to-Agent) Tracing 深度解析

### 核心問題：只能追蹤用 ADK 的 agent 嗎？

**結論先講**：不是一定要用 ADK，A2A tracing 本質上是跟 OpenTelemetry 這類 tracing 標準整合，理論上可以追蹤任何支援 OpenTelemetry 的 agent 或服務。

### A2A Tracing 的底層原理

這個專案用 OpenTelemetry（OTel）這個通用分散式追蹤標準：

- 任何程式，只要你在程式碼中插入 OTel 的 trace/span，並設定正確的 exporter（如 Jaeger、Zipkin、Tempo 等），都可以「被追蹤」
- 你要追蹤 Django、FastAPI、Flask 寫的服務都可以（只要加 OTel tracing）

### 為什麼範例用 ADK？

這個 sample 是要「快速示範 agent-to-agent 架構下怎麼 trace 每一個 agent 步驟」：

- 用 Google ADK 可以馬上支援 agent、session、tool（像 google_search_tool）、span creation 等等
- 不用自己刻一堆底層邏輯
- ADK 本身支援了 trace/telemetry，所以 sample 直接沿用，方便教學

### 不用 ADK 的替代方案

✅ **完全可以！** 只要你的「AgentExecutor」或服務有插入 OpenTelemetry trace，就能追蹤：

```python
from opentelemetry import trace

tracer = trace.get_tracer("my-custom-agent")

def my_agent_logic():
    with tracer.start_as_current_span("process_user_input"):
        # 這裡就會有一個 span 出現在 Jaeger！
        # 做處理...
        pass
```

上面這樣寫，不管是不是 ADK，只要有 OTel，就會出現在 Jaeger。

### 在 A2A SDK/Server 整合

你可以自己實作一個 AgentExecutor，裡面用 OTel 的 trace 包住你的邏輯流程即可：

- 追蹤的 granularity（細緻度）和邏輯都可以自己設計
- 關鍵在於「程式有沒有插入 OpenTelemetry 的追蹤點」

### 支援的 Agent 框架

你可以追蹤：
- 用 ADK 的 agent
- LangChain 框架
- Transformers pipeline
- 自己寫的 microservice
- 任何支援 OTel 的服務

**只要有 OTel，A2A trace/Grafana/Jaeger 就能吃到資料。**

### 進階：怎麼追蹤其他 agent？

1. 在你自己的 agent/server/service 加上 OTel tracing SDK（Python、Go、Node.js 各種語言都有）
2. 設定 exporter（如 Jaeger）成一樣的 endpoint
3. 就能把 trace 合併起來在 Jaeger/Grafana 看到一整條鏈

## ADK QnA Agent 實作範例

以下是一個完整的 ADK Agent 實作，展示如何整合 OpenTelemetry tracing：

```python
import logging
import os
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import TaskState, TextPart, UnsupportedOperationError
from a2a.utils import new_agent_text_message
from a2a.utils.errors import ServerError
from google.adk import Runner
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.sessions import InMemorySessionService
from google.adk.tools import google_search_tool
from google.genai import types

logger = logging.getLogger(__name__)

class QnAAgentExecutor(AgentExecutor):
    """Agent executor that uses the ADK to answer questions."""
    
    def __init__(self):
        self.agent = None
        self.runner = None
    
    def _init_agent(self):
        LITELLM_MODEL = os.getenv('LITELLM_MODEL', 'gemini/gemini-2.0-flash-exp')
        
        self.agent = LlmAgent(
            model=LiteLlm(model=LITELLM_MODEL),
            name='question_answer_agent',
            description='A helpful assistant agent that can answer questions.',
            instruction="""Respond to the query using google search""",
            tools=[google_search_tool.google_search],
        )
        
        self.runner = Runner(
            app_name=self.agent.name,
            agent=self.agent,
            artifact_service=InMemoryArtifactService(),
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
        )
    
    async def cancel(self, context: RequestContext, event_queue: EventQueue):
        raise ServerError(error=UnsupportedOperationError())
    
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if self.agent is None:
            self._init_agent()
        
        logger.debug(f'Executing agent {self.agent.name}')
        query = context.get_user_input()
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        
        if not context.current_task:
            await updater.submit()
            await updater.start_work()
        
        content = types.Content(role='user', parts=[types.Part(text=query)])
        
        session = await self.runner.session_service.get_session(
            app_name=self.runner.app_name,
            user_id='123',
            session_id=context.context_id,
        ) or await self.runner.session_service.create_session(
            app_name=self.runner.app_name,
            user_id='123',
            session_id=context.context_id,
        )
        
        async for event in self.runner.run_async(
            session_id=session.id, 
            user_id='123', 
            new_message=content
        ):
            logger.debug(f'Event from ADK {event}')
            
            if event.is_final_response():
                parts = event.content.parts
                text_parts = [TextPart(text=part.text) for part in parts if part.text]
                
                await updater.add_artifact(text_parts, name='result')
                await updater.complete()
                break
            
            await updater.update_status(
                TaskState.working, 
                message=new_agent_text_message('Working...')
            )
        else:
            logger.debug('Agent failed to complete')
            await updater.update_status(
                TaskState.failed,
                message=new_agent_text_message('Failed to generate a response.'),
            )
```

### 關鍵架構組件說明

1. **AgentExecutor**: A2A 框架的核心執行器
2. **Runner**: ADK 的主要執行環境
3. **LlmAgent**: 配置 LLM 模型和工具的代理
4. **TaskUpdater**: 負責更新任務狀態和事件推送
5. **Session Management**: 處理對話會話的持久化

## A2A Telemetry 完整範例專案

> 來源：[A2A Samples - Telemetry](https://github.com/a2aproject/a2a-samples/tree/main/samples/python/agents/a2a_telemetry)

### 什麼時候可以用到這個範例？

這個範例專案特別適合以下情境：

- **學習分散式追蹤**：想了解如何在 A2A SDK 中啟用和配置 OpenTelemetry
- **Agent 監控需求**：需要監控 AI Agent 的執行流程和效能瓶頸
- **多服務整合**：要追蹤跨多個服務的請求鏈路
- **生產環境準備**：準備將 Agent 系統部署到生產環境前的監控設置
- **問題排查**：需要詳細的執行軌跡來診斷系統問題

### 專案核心功能

- **Agent**：使用 Google Search 工具回答問題的對話式代理
- **Tracing**：基於 `__main__.py` 配置啟用追蹤功能
- **Trace Export**：將追蹤資料發送到 Docker 中運行的 Jaeger 後端
- **視覺化**：可在 Jaeger UI 和 Grafana 中查看和分析追蹤資料

### 檔案結構說明

- `__main__.py`：應用程式主入口，設置 OpenTelemetry tracer、Jaeger exporter 並啟動 A2A Server
- `agent_executor.py`：包含代理邏輯，整合 Google Search 工具和自定義 span 創建
- `docker-compose.yaml`：Docker Compose 檔案，輕鬆設置和運行 Jaeger 和 Grafana 服務

### 環境需求

- Python 3.10+
- Docker 和 Docker Compose
- Google API Key

### 快速開始

#### 1. 設置環境變數

```bash
export GOOGLE_API_KEY="YOUR_GOOGLE_API_KEY"
```

#### 2. 啟動 Jaeger 和 Grafana

```bash
docker compose up -d
```

這將啟動：
- **Jaeger**：UI 可在 `http://localhost:16686` 訪問
- **Grafana**：UI 可在 `http://localhost:3000` 訪問（預設登入：`admin`/`admin`）

**重要提醒**：Python 應用程式配置為通過 OTLP gRPC 向 Jaeger 發送追蹤資料。確保端口 `4317` 從主機映射到 Jaeger 容器。

#### 3. 運行應用程式

```bash
uv run .
```

應用程式將在端口 10020 上啟動。使用 CLI 或 UI 工具與代理互動，追蹤資料會被收集並發送到 Jaeger。

### 查看追蹤資料

#### Jaeger UI

1. 打開瀏覽器訪問：`http://localhost:16686`
2. 在左側邊欄搜索區域的「Service」下拉選單中選擇 `a2a-telemetry-sample`
3. 點擊「Find Traces」按鈕查看追蹤列表
4. 點擊任何追蹤查看詳細的 span 層次結構、日誌和標籤

#### Grafana UI

1. **訪問 Grafana**：打開 `http://localhost:3000`，使用預設憑證登入
2. **添加 Jaeger 資料源**：
   - 導航到「Connections」→「Add new connection」
   - 搜索並選擇「Jaeger」
   - 配置 URL：`http://jaeger:16686`
   - 點擊「Save & Test」
3. **探索追蹤**：
   - 導航到「Explore」
   - 選擇 Jaeger 資料源
   - 使用「Service」下拉選單選擇 `a2a-telemetry-sample`

### 停止服務

```bash
docker compose down
```

### 安全注意事項

**重要免責聲明**：此範例程式碼僅供示範用途。在構建生產應用程式時，必須將任何不在你直接控制下的代理視為潛在的不可信實體。

所有來自外部代理的資料都應作為不可信輸入處理，包括：
- AgentCard 資料
- 訊息內容
- 工件資料
- 任務狀態

開發者有責任實施適當的安全措施，如輸入驗證和憑證安全處理。

## 總結

- **ADK 的角色**：讓 agent 行為、記憶、工具調用、session 等功能「統一接口」
- **靈活性**：不必強綁 ADK，只要支援 OpenTelemetry 標準就能整合
- **擴展性**：可以追蹤任何插入 OTel trace 的服務或 agent
- **實用性**：完整的範例專案提供從開發到部署的完整監控解決方案

## 下一步

如果你想看更具體的 OTel 教學，或要知道怎麼安裝/整合到某個 Python 專案，隨時可以問我！