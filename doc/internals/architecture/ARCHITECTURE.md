# Архитектура ACP Protocol — Детальное руководство

## Оглавление

1. [Введение](#введение)
2. [Обзор системы](#обзор-системы)
3. [Архитектура на уровне компонентов](#архитектура-на-уровне-компонентов)
4. [Domain и Mapping слои в codelab.server](#domain-и-mapping-слои)
5. [Потоки данных](#потоки-данных)
6. [Транспортный слой](#транспортный-слой)
7. [Двухуровневая история в codelab.server](#двухуровневая-история)
8. [Background Receive Loop в codelab.client](#background-receive-loop)
9. [MCP Integration](#mcp-integration)
10. [Observability Layer](#observability-layer)
11. [LLM Call Strategies](#llm-call-strategies)
12. [Критические архитектурные решения](#критические-архитектурные-решения)
13. [Расширение и интеграция](#расширение-и-интеграция)

---

## Введение

ACP (Agent Client Protocol) — стандартный протокол взаимодействия между LLM-агентами и клиентами для выполнения задач с инструментами.

Проект реализован как **монорепозиторий** с двумя независимыми Python-компонентами:
- **[codelab/server](src/codelab/server/)** — серверная реализация протокола с LLM-агентом и управлением сессиями
- **[codelab/client](src/codelab/client/)** — клиентская реализация с TUI интерфейсом на базе Clean Architecture

---

## Обзор системы

### Диаграмма высокоуровневой архитектуры

```mermaid
graph TB
    subgraph Client["codelab-client (Client Side)"]
        TUI["🖥️ TUI Layer<br/>Textual UI Components"]
        Presentation["📊 Presentation Layer<br/>ViewModels + Observable"]
        Application["🎯 Application Layer<br/>Use Cases + State Machine"]
        Infrastructure["🔧 Infrastructure Layer<br/>DI, Transport, Event Bus"]
        Domain["📦 Domain Layer<br/>Entities, Events, Interfaces"]
    end
    
    subgraph Server["codelab-server (Server Side)"]
        Transport["🌐 Transport Layer<br/>WebSocket / stdio"]
        Protocol["🔄 Protocol Layer<br/>ACPProtocol + Handlers + Pipeline"]
        Agent["🤖 Agent Layer<br/>LLM Orchestration + AgentLoop"]
        Tools["🛠️ Tools Layer<br/>Executors + Registry + MCP"]
        Storage["💾 Storage Layer<br/>SessionStorage Backends"]
        Observability["📊 Observability<br/>Tracer + Metrics + Timeline"]
    end
    
    subgraph Transports["Транспорты"]
        WS["WebSocket<br/>Connection"]
        STDIO["stdio<br/>stdin/stdout"]
    end
    
    TUI --> Presentation
    Presentation --> Application
    Application --> Infrastructure
    Infrastructure --> Domain
    Infrastructure --> Transports
    
    Transports --> Transport
    WS --> Transport
    STDIO --> Transport
    Transport --> Protocol
    Protocol --> Agent
    Protocol --> Tools
    Protocol --> Storage
    Agent --> Tools
    
    style Client fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    style Server fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    style Transports fill:#fff3e0,stroke:#e65100,stroke-width:2px
```

### Таблица компонентов

| Компонент | Слой | Ответственность | Файлы |
|-----------|------|-----------------|-------|
| **TUI** | Presentation | Textual компоненты, User Interaction | `src/codelab/client/tui/` |
| **ViewModels** | Presentation | MVVM паттерн, Observable state (14 ViewModels) | `src/codelab/client/presentation/` |
| **Use Cases** | Application | Business scenarios, DTOs | `src/codelab/client/application/` |
| **DIContainer** | Infrastructure | Dependency Injection (dishka) | [`src/codelab/client/infrastructure/di_container.py`](src/codelab/client/infrastructure/di_container.py:33) |
| **BackgroundReceiveLoop** | Infrastructure | Единственный receive() на транспорт | [`src/codelab/client/infrastructure/services/background_receive_loop.py`](src/codelab/client/infrastructure/services/background_receive_loop.py:22) |
| **MessageRouter** | Infrastructure | Маршрутизация сообщений | [`src/codelab/client/infrastructure/services/message_router.py`](src/codelab/client/infrastructure/services/message_router.py:26) |
| **EventBus** | Infrastructure | Pub/Sub система событий | [`src/codelab/client/infrastructure/events/bus.py`](src/codelab/client/infrastructure/events/bus.py) |
| **StdioClientTransport** | Infrastructure | stdio транспорт (subprocess) | [`src/codelab/client/infrastructure/stdio_transport.py`](src/codelab/client/infrastructure/stdio_transport.py) |
| **ACPProtocol** | Protocol | Диспетчер методов ACP, `handle_and_process` для фоновых задач | [`src/codelab/server/protocol/core.py`](src/codelab/server/protocol/core.py:39) |
| **Handlers** | Protocol | Обработчики методов (auth, session, prompt) | [`src/codelab/server/protocol/handlers/`](src/codelab/server/protocol/handlers/) |
| **PromptPipeline** | Protocol | 7-stage pipeline: Validation → SlashCommand → PlanBuilding → TurnLifecycle(open) → Directives → LLMLoop → TurnLifecycle(close) | [`src/codelab/server/protocol/handlers/pipeline/`](src/codelab/server/protocol/handlers/pipeline/) |
| **PromptOrchestrator** | Protocol | Главный оркестратор prompt-turn | [`src/codelab/server/protocol/handlers/prompt_orchestrator.py`](src/codelab/server/protocol/handlers/prompt_orchestrator.py:32) |
| **AgentLoop** | Agent | Цикл LLM tool-calling итераций | [`src/codelab/server/protocol/handlers/pipeline/stages/agent_loop.py`](src/codelab/server/protocol/handlers/pipeline/stages/agent_loop.py) |
| **ExecutionEngine** | Agent | Композиция HistoryBuilder, ToolFilter, LLMAdapter, MessageSanitizer, PlanExtractor, ContextCompactor | [`src/codelab/server/agent/execution_engine.py`](src/codelab/server/agent/execution_engine.py) |
| **ToolRegistry** | Tools | Регистрация и управление инструментами | [`src/codelab/server/tools/registry.py`](src/codelab/server/tools/registry.py) |
| **ToolMapping** | Tools | Маппинг имён ACP ↔ LLM (fs/read → fs_read) | [`src/codelab/server/tools/mapping.py`](src/codelab/server/tools/mapping.py) |
| **MCPManager** | MCP | Управление MCP-серверами (stdio/HTTP/SSE, auto-reconnect, roots) | [`src/codelab/server/mcp/manager.py`](src/codelab/server/mcp/manager.py) |
| **Storage** | Storage | Persistence для сессий | [`src/codelab/server/storage/`](src/codelab/server/storage/) |
| **WebSocketTransport** | Transport | WebSocket endpoint | [`src/codelab/server/transport/websocket.py`](src/codelab/server/transport/websocket.py) |
| **StdioServerTransport** | Transport | stdio транспорт (stdin/stdout) | [`src/codelab/server/transport/stdio.py`](src/codelab/server/transport/stdio.py) |
| **StdioRunner** | Transport | Запуск stdio сервера с DI | [`src/codelab/server/transport/stdio_runner.py`](src/codelab/server/transport/stdio_runner.py) |
| **Tracer** | Observability | Distributed tracing | [`src/codelab/server/observability/tracer.py`](src/codelab/server/observability/tracer.py) |
| **MetricsTracker** | Observability | Metrics collection + auto-log | [`src/codelab/server/observability/metrics_tracker.py`](src/codelab/server/observability/metrics_tracker.py) |
| **EventTimeline** | Observability | Хронология событий | [`src/codelab/server/observability/event_timeline.py`](src/codelab/server/observability/event_timeline.py) |

---

## Domain и Mapping слои

### Обзор

Серверная часть (`codelab.server`) реализует **трёхслойную архитектуру** для разделения бизнес-логики и протокольных моделей:

```mermaid
graph TB
    subgraph Domain["Domain Layer (server/domain)"]
        direction TB
        Entities["Entities<br/>ToolCall, ConversationMessage, UserPrompt, PlanEntry"]
        ValueObjects["Value Objects<br/>FileLocation, SessionId"]
        Enums["Enums<br/>ToolCallStatus, MessageRole, PlanPriority, PlanStatus"]
        Aggregates["Aggregates<br/>Session, SessionConfig, ConversationHistory, ToolCallRegistry, PermissionState, AgentPlan, MultiAgentState"]
    end
    
    subgraph Mapping["Mapping Layer (server/mapping)"]
        direction TB
        ToolCallMapper["ToolCallMapper<br/>ToolCall ↔ ToolCallState"]
        HistoryMapper["HistoryMapper<br/>ConversationMessage ↔ HistoryMessage"]
        PromptMapper["PromptMapper<br/>UserPrompt ↔ ContentBlock"]
        PlanMapper["PlanMapper<br/>PlanEntry ↔ PlanStep"]
        SessionMapper["SessionMapper<br/>Session ↔ SessionState"]
        ToolResultMapper["ToolResultMapper<br/>ToolExecutionResult → ACP content"]
        LLMResponseMapper["LLMResponseMapper<br/>LLMToolCall → ToolCall"]
    end
    
    subgraph Protocol["Protocol Layer (server/protocol)"]
        direction TB
        ProtocolModels["ACP Protocol Models<br/>ToolCallState, HistoryMessage, SessionState, PlanStep"]
    end
    
    Domain <-->|to_protocol / to_domain| Mapping
    Mapping <-->|convert| Protocol
    
    style Domain fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    style Mapping fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style Protocol fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
```

### Принципы разделения

| Слой | Назначение | Примеры | Зависимости |
|------|------------|---------|-------------|
| **Domain** | Бизнес-сущности с логикой | `ToolCall`, `Session`, `PlanEntry` | Не зависит от protocol/infrastructure |
| **Protocol** | ACP wire format (Pydantic) | `ToolCallState`, `SessionState` | Сериализация/десериализация |
| **Mapping** | Конвертеры между слоями | `ToolCallMapper`, `SessionMapper` | Зависит от domain и protocol |

### Domain модели

#### ToolCall и ToolResult

```python
# Domain model (server/domain/tool_call.py)
@dataclass(frozen=True)
class ToolCall:
    id: str
    tool_name: str
    arguments: dict[str, Any]
    status: ToolCallStatus  # PENDING, RUNNING, COMPLETED, FAILED
    result: ToolResult | None
    locations: list[FileLocation]
    raw_output: dict[str, Any]
    
    @property
    def is_terminal(self) -> bool: ...

@dataclass(frozen=True)
class ToolResult:
    locations: list[FileLocation]
    raw_output: dict[str, Any]
```

#### ConversationMessage и MessageContent

```python
# Domain model (server/domain/conversation.py)
@dataclass(frozen=True)
class ConversationMessage:
    role: MessageRole  # USER, ASSISTANT, SYSTEM, TOOL
    content: MessageContent
    timestamp: datetime
    tool_calls: list[ToolCall]
    tool_call_id: str | None

@dataclass(frozen=True)
class MessageContent:
    text: str
    resources: list[Resource]
    images: list[Image]
```

#### Session Aggregate

```python
# Aggregate root (server/domain/session.py)
@dataclass
class Session:
    id: SessionId
    config: SessionConfig
    history: ConversationHistory
    tool_calls: ToolCallRegistry
    permissions: PermissionState
    plan: AgentPlan
    multi_agent: MultiAgentState
    
    # Business logic methods
    def add_message(self, message: ConversationMessage) -> None: ...
    def create_tool_call(self, tool_name: str, arguments: dict) -> ToolCall: ...
    def update_tool_call(self, tool_call_id: str, **kwargs) -> None: ...
    def set_permission_policy(self, kind: str, policy: str) -> None: ...
```

### Mapping layer

Mapper'ы обеспечивают двустороннюю конвертацию между domain и protocol моделями:

```python
# Пример: ToolCallMapper (server/mapping/tool_call_mapper.py)
class ToolCallMapper:
    @staticmethod
    def to_protocol(domain: ToolCall) -> ToolCallState:
        """Domain → Protocol (для отправки клиенту)"""
        return ToolCallState(
            tool_call_id=domain.id,
            title=domain.tool_name,
            status=domain.status.value,
            raw_input=domain.arguments,
            raw_output=domain.raw_output,
            locations=[{"path": loc.path, "line": loc.line} for loc in domain.locations],
        )
    
    @staticmethod
    def to_domain(protocol: ToolCallState) -> ToolCall:
        """Protocol → Domain (для бизнес-логики)"""
        return ToolCall(
            id=protocol.tool_call_id,
            tool_name=protocol.title,
            status=ToolCallStatus(protocol.status),
            arguments=dict(protocol.raw_input),
            raw_output=dict(protocol.raw_output),
            locations=[FileLocation(path=loc["path"], line=loc.get("line")) 
                       for loc in protocol.locations],
        )
```

### Таблица соответствия моделей

| Domain Model | ACP Protocol Model | Mapper | ACP Spec |
|--------------|-------------------|--------|----------|
| `ToolCall` | `ToolCallState` | `ToolCallMapper` | 08-Tool Calls |
| `ConversationMessage` | `HistoryMessage` | `HistoryMapper` | 05-Prompt Turn |
| `PlanEntry` | `PlanStep` | `PlanMapper` | 11-Agent Plan |
| `UserPrompt` | `ContentBlock` | `PromptMapper` | 06-Content |
| `Session` | `SessionState` | `SessionMapper` | 03-Session Setup |

### ToolExecutionResult

`ToolExecutionResult` (server/tools/base.py) — domain модель результата выполнения инструмента:

```python
@dataclass
class ToolExecutionResult:
    success: bool
    output: str | None
    error: str | None
    metadata: dict[str, Any] | None
    locations: list[FileLocation]  # Затронутые файлы
    raw_output: dict[str, Any]     # Исходный результат для ACP rawOutput
```

**Примеры использования:**

| Tool | `locations` | `raw_output` |
|------|-------------|--------------|
| `fs/read_text_file` | `[FileLocation(path, line)]` | `{"content": "...", "bytes_read": 1024}` |
| `fs/write_text_file` | `[FileLocation(path)]` | `{"bytes_written": 512, "diff": "..."}` |
| `terminal/create` | `[]` | `{"terminal_id": "term_xyz"}` |
| `terminal/wait_for_exit` | `[]` | `{"exit_code": 0, "signal": null, "output": "..."}` |
| MCP tools | `[]` | `{"result": {...}}` |

### Follow-along сервис

Клиентский `FollowAlongService` (client/infrastructure/services/follow_along.py) автоматически открывает файлы в IDE при обновлении tool calls:

```mermaid
sequenceDiagram
    participant Server
    participant Client as ToolCallHandler
    participant FollowAlong as FollowAlongService
    participant IDE as FileOpener
    
    Server->>Client: tool_call_update с locations
    Client->>Client: Обновляет состояние tool call
    Client->>FollowAlong: on_tool_call_updated(tool_call)
    FollowAlong->>FollowAlong: Проверяет enabled и locations
    FollowAlong->>IDE: open(path, line) для первого location
```

**Ключевые особенности:**
- `FileOpener` Protocol — абстракция для открытия файлов в IDE
- `StubFileOpener` — реализация для тестов
- Feature flag не нужен — если locations пуст, follow-along не срабатывает

---

## Архитектура на уровне компонентов

### codelab-server: Внутренняя структура

```mermaid
graph LR
    subgraph Transport["Transport Layer"]
        WS["WebSocket<br/>Endpoint"]
        STDIO["stdio<br/>stdin/stdout"]
        Base["AcpServerTransport<br/>Protocol Interface"]
    end
    
    subgraph Protocol["Protocol Layer"]
        Core["ACPProtocol"]
        Handlers["Handlers<br/>auth / session / prompt"]
        Pipeline["PromptPipeline<br/>7 stages"]
        PromptOrch["PromptOrchestrator<br/>(Главный координатор)"]
    end
    
    subgraph Processing["Processing"]
        AgentLoop["AgentLoop<br/>LLM итерации"]
        Engine["ExecutionEngine<br/>HistoryBuilder + ToolFilter + LLMAdapter"]
        ToolReg["ToolRegistry<br/>Управление инструментами"]
        Executors["Executors<br/>FS / Terminal / Plan / MCP"]
    end
    
    subgraph MCP["MCP Integration"]
        MCPMgr["MCPManager"]
        MCPClient["MCPClient"]
        MCPAdapt["MCPToolAdapter"]
    end
    
    subgraph Persistence["Persistence"]
        SessionStore["SessionStorage<br/>Abstract"]
        InMem["InMemoryStorage"]
        JsonFile["JsonFileStorage"]
        Cached["CachedSessionStorage"]
    end
    
    subgraph Observability["Observability"]
        Tracer["Tracer"]
        Timeline["EventTimeline"]
        Metrics["MetricsTracker"]
    end
    
    subgraph RPC["Client RPC"]
        ClientRPCService["ClientRPCService<br/>Асинхронные вызовы"]
    end
    
    WS --> Base
    STDIO --> Base
    Base --> Core
    Core --> Handlers
    Handlers --> Pipeline
    Pipeline --> PromptOrch
    PromptOrch --> AgentLoop
    AgentLoop --> Engine
    PromptOrch --> ToolReg
    ToolReg --> Executors
    ToolReg --> MCPAdapt
    MCPMgr --> MCPClient
    MCPClient --> MCPAdapt
    MCPAdapt --> Executors
    Executors --> ClientRPCService
    ClientRPCService --> Base
    
    Core --> SessionStore
    SessionStore --> InMem
    SessionStore --> JsonFile
    SessionStore --> Cached
    
    Engine -.-> Tracer
    Engine -.-> Timeline
    Engine -.-> Metrics
    
    style Transport fill:#fff3e0
    style Protocol fill:#f3e5f5
    style Processing fill:#e8f5e9
    style MCP fill:#e0f7fa
    style Persistence fill:#e0f2f1
    style Observability fill:#fce4ec
    style RPC fill:#f1f8e9
```

### codelab-client: Clean Architecture в 5 слоев

```mermaid
graph TB
    subgraph TUI["TUI Layer"]
        Chat["Chat View<br/>ChatView, MessageList, MessageBubble"]
        FileView["File Viewer<br/>FileTree, FileViewer"]
        Permission["Permission Modal<br/>PermissionModal, InlinePermissionWidget"]
        Terminal["Terminal Output<br/>TerminalOutput, TerminalPanel"]
        Tools["Tool Panel<br/>ToolCallCard, ToolCallList, FileChangePreview"]
        Config["Config Selectors<br/>ModelSelector, ConfigOptionSelector"]
    end
    
    subgraph Presentation["Presentation Layer (14 ViewModels)"]
        ChatVM["ChatViewModel"]
        FileVM["FileSystemViewModel"]
        PermVM["PermissionViewModel"]
        SessionVM["SessionViewModel"]
        UI_VM["UIViewModel"]
        PlanVM["PlanViewModel"]
        TermVM["TerminalViewModel"]
        FV_VM["FileViewerViewModel"]
        TLogVM["TerminalLogViewModel"]
        ModelVM["ModelSelectorViewModel"]
        ModeVM["ModeSelectorViewModel"]
        AgentVM["AgentSelectorViewModel"]
        StratVM["StrategySelectorViewModel"]
        ConfigVM["ConfigOptionSelectorViewModel"]
    end
    
    subgraph Application["Application Layer"]
        UseCases["Use Cases<br/>session/prompt/load"]
        StateMachine["UIStateMachine<br/>State Management"]
        DTOs["DTOs<br/>Data Transfer Objects"]
    end
    
    subgraph Infrastructure["Infrastructure Layer"]
        Transport["Transport Service<br/>WebSocket / stdio"]
        BgLoop["BackgroundReceiveLoop<br/>Единственный receive()"]
        Router["MessageRouter<br/>Маршрутизация"]
        Queues["RoutingQueues<br/>Распределение"]
        EventBus["EventBus<br/>Pub/Sub система"]
        DI["DIContainer<br/>dishka"]
        StdioTransport["StdioClientTransport<br/>subprocess"]
        
        subgraph AgentRPC["Agent → Client RPC"]
            FSHandler["FileSystemHandler"]
            TermHandler["TerminalHandler"]
            FSExec["FileSystemExecutor"]
            TermExec["TerminalExecutor"]
        end
    end
    
    subgraph Domain["Domain Layer"]
        Entities["Entities<br/>Session, Message"]
        Events["Events<br/>Domain Events"]
        Repos["Repositories<br/>Interfaces"]
    end
    
    Chat --> ChatVM
    FileView --> FileVM
    Permission --> PermVM
    Terminal --> TermVM
    Tools --> ChatVM
    Config --> ModelVM
    
    ChatVM --> UseCases
    FileVM --> UseCases
    PermVM --> UseCases
    SessionVM --> UseCases
    
    UseCases --> StateMachine
    StateMachine --> DTOs
    
    DTOs --> Transport
    DTOs --> EventBus
    
    Transport --> BgLoop
    BgLoop --> Router
    Router --> Queues
    Queues --> EventBus
    
    Router --> FSHandler
    Router --> TermHandler
    FSHandler --> FSExec
    TermHandler --> TermExec
    
    EventBus --> Entities
    EventBus --> Events
    EventBus --> Repos
    
    DI --> TUI
    DI --> Presentation
    DI --> Application
    DI --> Infrastructure
    
    style TUI fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style Presentation fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
    style Application fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
    style Infrastructure fill:#e0f2f1,stroke:#004d40,stroke-width:2px
    style Domain fill:#eceff1,stroke:#263238,stroke-width:2px
```

---

## Потоки данных

### 1. Отправка промпта (Client → Server)

```mermaid
sequenceDiagram
    actor User
    participant TUI
    participant ChatVM
    participant UseCase
    participant Transport
    participant BgLoop
    participant Server as codelab-server

    User->>TUI: Вводит промпт
    TUI->>ChatVM: prompt_text.value = "..."
    ChatVM->>UseCase: send_prompt(session_id, text)
    UseCase->>Transport: request_with_callbacks(method="session/prompt")
    
    Transport->>Transport: Отправляет JSON-RPC<br/>на WebSocket
    Transport->>Transport: Создает asyncio.Future<br/>для ожидания результата
    
    rect RGB(200, 220, 255)
        Note over BgLoop,Server: В фоне: BackgroundReceiveLoop слушает
        Server->>Transport: Начинает обработку prompt
        Server->>Transport: Отправляет session/update
        Transport->>BgLoop: receive() получает update
        BgLoop->>Router: route(message)
        Router->>Queues: Помещает в notification_queue
        Queues->>UseCase: on_update_callback вызывается
        UseCase->>ChatVM: Обновляет view_model
    end
    
    Server->>Transport: Обработка завершена<br/>отправляет result
    Transport->>BgLoop: receive() получает result
    BgLoop->>Router: route(message) → response[id]
    Router->>Queues: response_queue[id].put(result)
    Queues->>Transport: await future.set_result()
    Transport->>UseCase: Возвращает результат
    UseCase->>ChatVM: Обновляет final state
    ChatVM->>TUI: Отрисовка завершена
```

### 2. Обработка session/prompt на сервере

```mermaid
sequenceDiagram
    participant Client
    participant HttpServer
    participant ACPProtocol
    participant PromptOrch as PromptOrchestrator
    participant Agent as ExecutionEngine
    participant Tools as ToolRegistry
    participant ClientRPC as ClientRPCService

    Client->>HttpServer: session/prompt request
    HttpServer->>ACPProtocol: handle(message)
    
    ACPProtocol->>PromptOrch: process_prompt_turn(session_id, text)
    
    PromptOrch->>PromptOrch: 1. Валидация и preprocessing
    
    PromptOrch->>Agent: 2. agent.process_prompt(context)
    Agent->>Agent: Добавляет user message в LLM контекст
    Agent->>Tools: Получает доступные tools
    Agent->>Agent: Вызывает LLM
    
    Agent->>Tools: 3. Выполнение tool calls
    Tools->>ClientRPC: Запрос инструмента (fs/*, terminal/*)
    ClientRPC->>Client: RPC вызов (fs/readTextFile и т.д.)
    Client->>ClientRPC: Результат инструмента
    
    PromptOrch->>PromptOrch: 4. Обновление session/history
    PromptOrch->>PromptOrch: 5. Отправка session/update
    
    HttpServer->>Client: Итоговый результат
```

### 3. Обработка permission request на клиенте

```mermaid
sequenceDiagram
    participant Server as codelab-server
    participant BgLoop as BackgroundReceiveLoop
    participant PermVM as PermissionViewModel
    participant User as 👤 User
    participant Transport

    Server->>BgLoop: session/request_permission
    BgLoop->>Router: route(message) → permission_queue
    Router->>Queues: permission_queue.put(request)
    Queues->>PermVM: Уведомление о запросе
    
    PermVM->>PermVM: Заполняет permission data
    PermVM->>User: Показывает permission modal
    
    User->>User: Рассматривает запрос
    User->>PermVM: Нажимает Allow/Deny
    
    PermVM->>Transport: session/request_permission_response
    Transport->>Server: JSON-RPC ответ
    Server->>Server: Вычисляет result
    Server->>Transport: Отправляет session/update
    Transport->>BgLoop: receive() получает update
    BgLoop->>PermVM: on_update_callback
    PermVM->>PermVM: Обновляет state
```

### 4. Background Receive Loop: Маршрутизация сообщений

```mermaid
graph TD
    A["receive() на WebSocket<br/>await transport.receive()"]
    B["Парсинг JSON"]
    C{"Анализ сообщения"}
    
    D["message.method == 'session/update'"]
    E["message.method == 'session/request_permission'"]
    F["message.method == 'fs/*' или 'terminal/*'"]
    G["message.id присутствует"]
    H["Неизвестный тип"]
    
    D --> D1["→ notification_queue<br/>on_update_callback"]
    E --> E1["→ permission_queue<br/>on_permission_callback"]
    F --> F1["→ notification_queue<br/>request_with_callbacks callback"]
    G --> G1["→ response_queue[id]<br/>asyncio.Future.set_result"]
    H --> H1["Логирование ошибки"]
    
    A --> B --> C
    C -->|method first| D
    C -->|method first| E
    C -->|method first| F
    C -->|id check| G
    C -->|default| H
    
    D1 --> I["Распределение в очереди"]
    E1 --> I
    F1 --> I
    G1 --> I
    
    I --> J["Вызов callbacks<br/>или set asyncio.Future"]
    J --> A
    
    style A fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style C fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
    style I fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
    style J fill:#e0f2f1,stroke:#004d40,stroke-width:2px
```

---

## Транспортный слой

### Архитектура транспорта

`ACPProtocol` (dispatcher) **не зависит от транспорта** — он принимает `ACPMessage` и возвращает `ProtocolOutcome`. Транспортный слой реализует передачу сообщений между клиентом и сервером.

```mermaid
graph TB
    subgraph Server["Сервер"]
        ACP["ACPProtocol (core)<br/>transport-agnostic"]
        WS["WebSocketTransport"]
        STDIO_S["StdioServerTransport"]
        Base_S["AcpServerTransport<br/>Protocol"]
    end

    subgraph Client["Клиент"]
        WS_C["WebSocketTransport"]
        STDIO_C["StdioClientTransport<br/>(subprocess)"]
        Service["ACPTransportService"]
    end

    ACP --> Base_S
    WS --> Base_S
    STDIO_S --> Base_S
    WS_C --> WS
    STDIO_C --> STDIO_S
    Service --> WS_C
    Service --> STDIO_C
```

### Режимы работы

| Режим | Команда | Транспорт | Описание |
|-------|---------|-----------|----------|
| **Локальный** | `codelab` | stdio (subprocess) | Сервер запускается как subprocess, TUI подключается через stdio |
| **WebSocket сервер** | `codelab serve` | WebSocket | Сервер слушает ws://host:port/acp/ws |
| **stdio сервер** | `codelab serve --stdio` | stdio | Сервер читает stdin, пишет stdout (для IDE plugins) |
| **WebSocket клиент** | `codelab connect` | WebSocket | TUI подключается к удалённому серверу |
| **stdio клиент** | `codelab connect --stdio` | stdio (subprocess) | TUI запускает агент как subprocess |

### Серверный транспорт

**Интерфейс `AcpServerTransport`:**

```python
class AcpServerTransport(Protocol):
    async def run(
        self,
        on_message: Callable[[ACPMessage], Awaitable[ProtocolOutcome]],
    ) -> None: ...

    async def send(self, message: ACPMessage) -> None: ...
    async def close(self) -> None: ...
```

**Реализации:**

| Транспорт | Файл | Особенности |
|-----------|------|-------------|
| `WebSocketTransport` | `server/transport/websocket.py` | aiohttp WebSocket, Web UI |
| `StdioServerTransport` | `server/transport/stdio.py` | stdin/stdout, newline-delimited JSON-RPC |

**Ключевые детали stdio сервера:**

| Аспект | Решение |
|--------|---------|
| **Логирование** | ТОЛЬКО в stderr. Structlog handler на stderr |
| **Buffering** | `line_buffering=True` + ручной flush после каждого сообщения |
| **Agent→Client RPC** | Единый `asyncio.Lock` на запись в stdout |
| **EOF** | Graceful exit из цикла, cleanup pending operations |
| **SIGTERM/SIGINT** | Signal handlers → `close()` + `sys.exit(0)` |
| **Background Prompt** | `session/prompt` выполняется в `asyncio.create_task`, receive-loop продолжает читать stdin |

### Клиентский транспорт

**Интерфейс `Transport`:**

```python
class Transport(Protocol):
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def send_str(self, data: str) -> None: ...
    async def receive_text(self) -> str: ...
    def is_connected(self) -> bool: ...
```

**Реализации:**

| Транспорт | Файл | Особенности |
|-----------|------|-------------|
| `WebSocketTransport` | `client/infrastructure/transport.py` | aiohttp WebSocket |
| `StdioClientTransport` | `client/infrastructure/stdio_transport.py` | asyncio subprocess, background reader |

**Ключевые детали stdio клиента:**

| Аспект | Решение |
|--------|---------|
| **Запуск** | `asyncio.create_subprocess_exec(command, *args, stdin=PIPE, stdout=PIPE, stderr=PIPE)` |
| **stdout reader** | Background task → `asyncio.Queue[str]` |
| **stderr reader** | Background task → логирование |
| **Graceful shutdown** | Close stdin → wait 5s → kill if needed |
| **Process exit** | Если процесс завершился → error при `receive_text()` |

---

## Двухуровневая история

### SessionState.history vs events_history

На сервере в codelab.server существует **двухуровневая система истории**:

```mermaid
graph TB
    subgraph LLMContext["LLM Context (SessionState.history)"]
        M1["user: Привет"]
        M2["assistant: Привет!"]
        M3["user: Выполни задачу X"]
    end
    
    subgraph ReplayContext["Replay Context (events_history)"]
        E1["session/started"]
        E2["message_added: user message"]
        E3["tool_call_started"]
        E4["tool_call_completed"]
        E5["message_added: assistant message"]
    end
    
    LLMContext -->|читается| AgentLLM["ExecutionEngine<br/>для process_prompt"]
    ReplayContext -->|используется| SessionLoad["session/load<br/>для восстановления состояния"]
    
    NewPrompt["Новый prompt"]
    NewPrompt -->|добавляет в| LLMContext
    NewPrompt -->|добавляет events в| ReplayContext
    
    style LLMContext fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    style ReplayContext fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
    style AgentLLM fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style SessionLoad fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
```

**Ключевые различия:**

| Аспект | SessionState.history | events_history |
|--------|----------------------|-----------------|
| **Содержание** | Message objects (user/assistant) | Structured events (started, added, completed) |
| **Использование** | Передача LLM для контекста | Восстановление state при load |
| **Обновление** | Централизованно в PromptOrchestrator | Через TurnLifecycleManager |
| **Размер** | Компактный (только сообщения) | Расширенный (все события) |
| **Воспроизведение** | Невозможно (информация потеряна) | Полное восстановление через replay |

**Архитектурное решение:**
- **ExecutionEngine.process_prompt()** — **НЕ** модифицирует SessionState
- **PromptOrchestrator** отвечает за добавление messages в history
- **TurnLifecycleManager** добавляет события в events_history
- Это обеспечивает **разделение ответственности** и **централизованное управление**

---

## Background Receive Loop

### Проблема: Race Condition при конкурентном доступе к WebSocket

```mermaid
graph LR
    subgraph Wrong["❌ Неправильно: Race Condition"]
        T1["Task 1<br/>receive()"]
        T2["Task 2<br/>receive()"]
        WS["WebSocket"]
        Error["RuntimeError:<br/>Only one receive() allowed"]
        
        T1 -->|получает сообщение| WS
        T2 -->|пытается получить| WS
        WS --> Error
    end
    
    subgraph Right["✅ Правильно: BackgroundReceiveLoop"]
        BgLoop["BackgroundReceiveLoop<br/>Единственный receive()"]
        Q1["response_queue"]
        Q2["notification_queue"]
        Q3["permission_queue"]
        T1["Task 1<br/>ждет response[id]"]
        T2["Task 2<br/>ждет callback"]
        
        BgLoop -->|message| Router["MessageRouter"]
        Router -->|маршрутизирует| Q1
        Router -->|маршрутизирует| Q2
        Router -->|маршрутизирует| Q3
        
        Q1 -->|asyncio.Future| T1
        Q2 -->|callback| T2
        Q3 -->|permission queue| T2
    end
    
    style Wrong fill:#ffebee,stroke:#c62828,stroke-width:2px
    style Right fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
    style Error fill:#ffcdd2,stroke:#b71c1c,stroke-width:2px
```

### Архитектура BackgroundReceiveLoop

```
┌─────────────────────────────────────────────────────────┐
│         BackgroundReceiveLoop                           │
│                                                          │
│  ┌──────────────────────────────────────────────┐      │
│  │ Главный цикл (asyncio.Task)                  │      │
│  │                                               │      │
│  │  while not should_stop:                      │      │
│  │    message = await transport.receive()       │      │
│  │    routing_key = router.route(message)       │      │
│  │    queue = queues.get(routing_key)           │      │
│  │    queue.put(message)                        │      │
│  └──────────────────────────────────────────────┘      │
│                     │                                   │
│    ┌────────────────┼────────────────┐                 │
│    ▼                ▼                ▼                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐         │
│  │Response  │  │Notif.    │  │Permission    │         │
│  │Queue     │  │Queue     │  │Queue         │         │
│  │          │  │          │  │              │         │
│  │[id1]:    │  │events:   │  │requests:     │         │
│  │Future    │  │list      │  │list          │         │
│  │[id2]:    │  │          │  │              │         │
│  │Future    │  │          │  │              │         │
│  └──────────┘  └──────────┘  └──────────────┘         │
│      ▲              ▲              ▲                   │
│      │              │              │                   │
│  ┌───┴──────────────┴──────────────┴─────┐            │
│  │ Потребители:                          │            │
│  │ - request_with_callbacks              │            │
│  │ - on_update_callback                  │            │
│  │ - on_permission_callback              │            │
│  └───────────────────────────────────────┘            │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

**Ключевые особенности:**

1. **Единственный receive()** — избегает RuntimeError при конкурентном доступе
2. **Маршрутизация на основе сообщения** — router.route() определяет очередь
3. **Три типа очередей:**
   - **response_queue** — RPC ответы (по id)
   - **notification_queue** — асинхронные уведомления (session/update, fs/*, terminal/*)
   - **permission_queue** — запросы разрешений
4. **Graceful shutdown** — await stop() дожидается завершения loop
5. **Диагностика** — счетчики сообщений и ошибок для мониторинга
6. **Async callbacks** — callbacks поддерживают как sync так и async функции через `_call_callback()`, что предотвращает блокировку event loop в stdio режиме

---

## MCP Integration

CodeLab поддерживает Model Context Protocol (MCP) для подключения внешних инструментов, ресурсов и промптов.

### Компоненты

| Компонент | Файл | Ответственность |
|-----------|------|-----------------|
| `MCPManager` | `server/mcp/manager.py` | Управление несколькими MCP-серверами на сессию, auto-reconnect с backoff |
| `MCPClient` | `server/mcp/client.py` | Подключение к одному MCP-серверу с state machine |
| `MCPToolAdapter` | `server/mcp/tool_adapter.py` | Адаптация MCP tools → ACP ToolDefinition, kind inference |
| `MCPResourceMapper` | `server/mcp/resource_mapper.py` | Маппинг MCP resources → ACP ResourceLinkContent |
| `MCPPromptMapper` | `server/mcp/prompt_mapper.py` | Маппинг MCP prompts → slash commands |
| `MCPContentMapper` | `server/mcp/content_mapper.py` | Конвертация MCP content → ACP content |

### Транспорты

| Транспорт | Протокол | Статус |
|-----------|----------|--------|
| Stdio | subprocess stdin/stdout | ✅ Полностью |
| HTTP | HTTP POST/GET | ✅ Полностью |
| SSE | Server-Sent Events | ✅ Полностью |

### Функциональность

- **Tools**: MCP инструменты регистрируются в ToolRegistry с namespace `mcp:server_id:tool_name`
- **Resources**: MCP resources доступны через ResourceLinkContent
- **Prompts**: MCP prompts доступны как slash commands
- **Notifications**: Поддержка `tools/list_changed`, `resources/list_changed`, `prompts/list_changed`, progress notifications
- **Auto-reconnect**: С exponential backoff и health checks
- **Roots**: Поддержка `roots/list` и notifications
- **TOML Config**: Загрузка MCP-серверов из `codelab.toml` с env variable expansion

### Интеграция в pipeline

MCP инструменты интегрируются в `LLMLoopStage` — доступны агенту наравне с нативными инструментами. Permission flow для MCP инструментов использует kind inference для определения типа разрешения.

---

## Observability Layer

Сервер предоставляет абстрактный observability layer для трассировки, метрик и хронологии событий.

### Компоненты

| Компонент | Файл | Ответственность |
|-----------|------|-----------------|
| `Tracer` | `server/observability/tracer.py` | Distributed tracing с spans и trace IDs |
| `EventTimeline` | `server/observability/event_timeline.py` | Хронология событий сессии |
| `MetricsTracker` | `server/observability/metrics_tracker.py` | Сбор метрик + auto-log, TelemetrySink |

### Exporters

| Exporter | Файл | Формат |
|----------|------|--------|
| `FileEventExporter` | `server/observability/exporters/file_event_exporter.py` | JSON events в файл |
| `FileMetricsExporter` | `server/observability/exporters/file_metrics_exporter.py` | JSON metrics в файл |
| `FileSpanExporter` | `server/observability/exporters/file_span_exporter.py` | JSON spans в файл |

### Интеграция

Observability компоненты инжектируются через DI-контейнер и используются в `ExecutionEngine`, `AgentLoop`, `LLMAdapter` для трассировки LLM-вызовов, tool execution, и prompt turns.

---

## LLM Call Strategies

Система стратегий вызова LLM обеспечивает гибкость в управлении циклом tool-calling итераций.

### Архитектура

```mermaid
graph TD
    A[LLMCallStrategy Protocol] -->|интерфейс| B[execute]
    A -->|интерфейс| C[continue_execution]
    A -->|реализация| D[SingleStrategy ✅]
    A -->|реализация| E[StrategyDispatcher ✅]
    D -->|использует| F[EventBus]
    E -->|маршрутизирует| D
    E -->|маршрутизирует| G[MultiOrchestrated ❌]
    E -->|маршрутизирует| H[MultiChoreographed ❌]
    E -->|маршрутизирует| I[Hierarchical ❌]
    
    style D fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    style E fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    style G fill:#ffcdd2,stroke:#b71c1c,stroke-dasharray: 5 5
    style H fill:#ffcdd2,stroke:#b71c1c,stroke-dasharray: 5 5
    style I fill:#ffcdd2,stroke:#b71c1c,stroke-dasharray: 5 5
```

### Реализованные стратегии

| Стратегия | Файл | Статус | Описание |
|-----------|------|--------|----------|
| `SingleStrategy` | `protocol/handlers/strategies/single_strategy.py` | ✅ | Единственная реализованная стратегия. Один LLM-вызов → обработка tool calls → повтор |
| `StrategyDispatcher` | `agent/strategies/dispatcher.py` | ✅ | Диспетчер стратегий с priority chain + fallback. Маршрутизирует к зарегистрированным стратегиям |

### Запланированные (не реализованы)

| Стратегия | Статус | Описание |
|-----------|--------|----------|
| `MultiOrchestrated` | ❌ | Мультиагент с оркестратором |
| `MultiChoreographed` | ❌ | Мультиагент без оркестратора (choreography) |
| `Hierarchical` | ❌ | Иерархическая мультиагентная стратегия |

> **Важно:** Config specs ссылаются на `multi_orchestrated`, `multi_choreographed`, `hierarchical` стратегии, но только `single` имеет конкретную реализацию. Попытка использовать незавершённые стратегии приведёт к ошибке.

---

## Критические архитектурные решения

### 1. Абстракция SessionStorage в codelab.server

**Проблема:** Нужна гибкость в выборе хранилища (в памяти для dev, на диске для prod).

**Решение:** [`SessionStorage(ABC)`](src/codelab/server/storage/base.py) — интерфейс с двумя реализациями:

```mermaid
graph TB
    subgraph Interface["SessionStorage Abstract Interface"]
        create["async create_session()"]
        load["async load_session()"]
        list["async list_sessions()"]
        update["async update_session()"]
        delete["async delete_session()"]
    end
    
    subgraph Memory["InMemoryStorage"]
        MemDict["dict[id] = SessionState<br/>в памяти"]
    end
    
    subgraph File["JsonFileStorage"]
        FileDict["dir/id.json<br/>на диске"]
    end
    
    Interface --> Memory
    Interface --> File
    
    CLI["CLI флаг<br/>--storage"]
    CLI -->|memory://| Memory
    CLI -->|json://path| File
    
    style Interface fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
    style Memory fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
    style File fill:#fff3e0,stroke:#e65100,stroke-width:2px
```

**Преимущества:**
- ✅ Easy testing (InMemoryStorage)
- ✅ Production persistence (JsonFileStorage)
- ✅ Plug-and-play новых backends (Redis, PostgreSQL)
- ✅ Изоляция логики хранения от протокола

### 2. Транспортная абстракция

**Проблема:** Нужна поддержка нескольких транспортов (WebSocket, stdio) без дублирования бизнес-логики.

**Решение:** `ACPProtocol` transport-agnostic, транспорт реализует единый интерфейс:

```mermaid
graph TB
    subgraph Protocol["ACPProtocol (transport-agnostic)"]
        Handle["handle(message) → outcome"]
        HandleAndProcess["handle_and_process(message)\n→ handle() + background tasks"]
        BackgroundTool["_execute_tool_in_background()\n(фоновая задача)"]
        SendCallback["_send_callback()\n(отправка из фона)"]
    end
    
    subgraph Transports["Transport Implementations"]
        WS["WebSocketTransport\naiohttp WebSocket"]
        STDIO["StdioServerTransport\nstdin/stdout"]
    end
    
    WS --> HandleAndProcess
    STDIO --> HandleAndProcess
    HandleAndProcess --> Handle
    HandleAndProcess --> BackgroundTool
    BackgroundTool --> SendCallback
    SendCallback --> WS
    SendCallback --> STDIO
    
    style Protocol fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
    style Transports fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style HandleAndProcess fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
```

**Преимущества:**
- ✅ Единая бизнес-логика для всех транспортов
- ✅ Локальный режим использует stdio (соответствует spec ACP)
- ✅ `codelab serve --stdio` для интеграции с IDE plugins
- ✅ Изолированный процесс сервера в local mode

### Маппинг имён инструментов ACP ↔ LLM

**Проблема:** ACP протокол использует имена инструментов с `/` (например `fs/read_text_file`, `terminal/create`), но некоторые LLM провайдеры (Azure через OpenRouter) не поддерживают символ `/` в именах функций. Допустимый паттерн: `^[a-zA-Z0-9_\.-]+$`.

**Решение:** [`tools/mapping.py`](src/codelab/server/tools/mapping.py) обеспечивает двусторонний маппинг:

```mermaid
graph LR
    subgraph ACP["ACP Protocol Names"]
        A1["fs/read_text_file"]
        A2["fs/write_text_file"]
        A3["terminal/create"]
        A4["terminal/wait_for_exit"]
    end
    
    subgraph Mapping["ToolMapping"]
        M1["acp_name_to_llm_name()\n/ → _"]
        M2["llm_name_to_acp_name()\n_ → / (для известных префиксов)"]
    end
    
    subgraph LLM["LLM API Names"]
        L1["fs_read_text_file"]
        L2["fs_write_text_file"]
        L3["terminal_create"]
        L4["terminal_wait_for_exit"]
    end
    
    A1 --> M1 --> L1
    A2 --> M1 --> L2
    A3 --> M1 --> L3
    A4 --> M1 --> L4
    
    L1 --> M2 --> A1
    L2 --> M2 --> A2
    L3 --> M2 --> A3
    L4 --> M2 --> A4
    
    style ACP fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    style LLM fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style Mapping fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
```

**Где применяется:**

| Место | Направление | Описание |
|-------|-------------|----------|
| `LLMAdapter._convert_tools()` | ACP → LLM | При отправке инструментов в LLM API |
| `SimpleToolRegistry.to_llm_tools()` | ACP → LLM | При конвертации для LLM |
| `SimpleToolRegistry.execute_tool()` | LLM → ACP | При выполнении инструмента (lookup в registry) |
| `LLMLoopStage._process_tool_calls()` | LLM → ACP | При обработке tool calls от LLM |

**Пример:**
```python
>>> acp_name_to_llm_name("fs/read_text_file")
"fs_read_text_file"
>>> llm_name_to_acp_name("fs_read_text_file")
"fs/read_text_file"
```

### 3. Фильтрация инструментов по ClientRuntimeCapabilities

**Проблема:** Не все клиенты поддерживают все инструменты (например, некоторые не поддерживают file system операции).

**Решение:** [`ClientRuntimeCapabilities`](src/codelab/server/protocol/state.py) для фильтрации:

```python
# Пример из PromptOrchestrator
available_tools = [
    tool for tool in all_tools
    if client_capabilities.supports_tool(tool.id)
]
```

**Ключевые возможности:**
- `supports_filesystem`: Поддержка fs операций
- `supports_terminal`: Поддержка terminal операций
- `max_tool_call_iterations`: Максимальное количество итераций tool calls

### 4. ClientRPCService для асинхронных вызовов

**Проблема:** Инструменты (fs/*, terminal/*) должны выполняться асинхронно на клиенте, а сервер ждет результата.

**Решение:** [`ClientRPCService`](src/codelab/server/client_rpc/service.py) управляет [`asyncio.Future`](src/codelab/server/client_rpc/models.py):

```mermaid
graph TD
    A["Инструмент начинает выполнение"]
    B["ClientRPCService.execute_tool()"]
    C["Отправляет RPC на клиент"]
    D["Создает asyncio.Future"]
    E["await future (блокирует до результата)"]
    F["Клиент выполняет операцию"]
    G["Отправляет ответ"]
    H["ClientRPCService получает ответ"]
    I["future.set_result()"]
    J["Инструмент получает результат"]
    
    A --> B --> C --> D --> E
    F --> G --> H --> I --> J
    
    style E fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style I fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
```

### 4.1. Terminal output flow (по ACP spec)

**Проблема:** По спецификации ACP `terminal/wait_for_exit` возвращает только `exitCode` и `signal` — без output. Output получается через отдельный метод `terminal/output`.

**Решение:** [`TerminalToolExecutor.execute_wait_for_exit()`](src/codelab/server/tools/executors/terminal_executor.py) реализует корректный flow:

```mermaid
sequenceDiagram
    participant LLM
    participant Executor as TerminalToolExecutor
    participant Bridge as ClientRPCBridge
    participant Client

    LLM->>Executor: terminal/wait_for_exit(terminal_id)
    Executor->>Bridge: terminal_output(terminal_id)
    Bridge->>Client: terminal/output RPC
    Client-->>Bridge: output + exitStatus
    Bridge-->>Executor: output + is_complete + exit_code
    
    alt Terminal уже завершён (is_complete=True)
        Executor-->>LLM: ToolResult(output + exit_code)
    else Terminal ещё работает (is_complete=False)
        Executor->>Bridge: wait_terminal_exit(terminal_id)
        Bridge->>Client: terminal/wait_for_exit RPC
        Client-->>Bridge: exitCode + signal
        Bridge-->>Executor: exit_code + signal
        Executor->>Bridge: terminal_output(terminal_id)
        Bridge->>Client: terminal/output RPC
        Client-->>Bridge: финальный output
        Bridge-->>Executor: output + exitStatus
        Executor-->>LLM: ToolResult(output + exit_code + signal)
    end
```

**Ключевые изменения (2026-05-21):**
- `TerminalWaitForExitResponse` — только `exitCode` и `signal` (по spec)
- `TerminalOutputResponse` — `output`, `truncated`, `exitStatus` (по spec)
- `ClientRPCBridge.terminal_output()` — новый метод для получения output
- `ToolResult` передаёт `output` в LLM (исправлена потеря output)

### 5. PromptOrchestrator как центральный координатор

**Проблема:** Обработка prompt-turn включает множество этапов (валидация, LLM, tools, permissions, обновления).

**Решение:** [`PromptOrchestrator`](src/codelab/server/protocol/handlers/prompt_orchestrator.py) интегрирует все компоненты:

```python
class PromptOrchestrator:
    def __init__(
        self,
        state_manager: StateManager,
        plan_builder: PlanBuilder,
        turn_lifecycle_manager: TurnLifecycleManager,
        tool_call_handler: ToolCallHandler,
        permission_manager: PermissionManager,
        client_rpc_handler: ClientRPCHandler,
        tool_registry: ToolRegistry,
    ):
        # Все компоненты инжектированы
        self.state_manager = state_manager
        self.plan_builder = plan_builder
        # ...
```

**Координирует:**
1. Валидацию входных данных
2. Преобразование контекста для LLM
3. Вызов агента
4. Управление tool calls
5. Проверку разрешений
6. Обновление состояния сессии
7. Отправку events в историю

### 6. Background Prompt Execution в StdioServerTransport (устранение deadlock в bypass mode)

**Проблема:** В bypass mode (без permission gate) агент отправляет `fs/read_text_file` клиенту через Agent→Client RPC и синхронно ждёт ответа. До фикса `session/prompt` обрабатывался синхронно внутри `await on_message()` — receive-loop был заблокирован и не читал stdin. Ответ клиента приходил на stdin, но никто его не читал → **deadlock на 44+ секунд**.

```mermaid
graph TB
    subgraph Before["❌ До фикса: Deadlock"]
        A1["stdin: session/prompt"]
        A2["on_message() → BLOCKED"]
        A3["AgentLoop: fs/read_text_file"]
        A4["await client RPC response"]
        A5["stdin: client response → ❌ Никто не читает!"]
        
        A1 --> A2 --> A3 --> A4 --> A5
        A5 -.x.-> A4
        
        style A5 fill:#ffcdd2,stroke:#b71c1c,stroke-width:2px
    end
    
    subgraph After["✅ После фикса: Background execution"]
        B1["stdin: session/prompt"]
        B2["asyncio.create_task(prompt)"]
        B3["prompt task: await client RPC"]
        B4["receive-loop: продолжает читать stdin"]
        B5["stdin: client response → ✅ Доставлен!"]
        B6["prompt task: получает ответ → завершается"]
        
        B1 --> B2
        B2 --> B3
        B2 --> B4
        B4 --> B5
        B5 --> B3
        B3 --> B6
        
        style B5 fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
        style B6 fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    end
    
    Before --> After
```

**Решение:** `StdioServerTransport.run()` теперь запускает `session/prompt` в фоновой задаче через `asyncio.create_task()`, зеркально логике `WebSocketTransport`. Receive-loop продолжает читать stdin и маршрутизирует client RPC responses (`method=None, id=<rpc_id>`) в `on_message()`, где `protocol.handle()` перенаправляет на `handle_client_response()`.

**Интеграция без прямой зависимости от ACPProtocol:** Transport принимает 4 опциональных callback в `__init__`:

| Callback | Назначение | Вызывается когда |
|----------|------------|-------------------|
| `should_auto_complete` | Проверка автозавершения turn | `session/prompt` вернул outcome без response |
| `complete_active_turn` | Завершение turn + финальный response | Deferred prompt completion (после guard delay 50ms) |
| `load_pending_prompt_response` | Построение response при cancel | `session/cancel` отменяет deferred prompt task |

> **Важно:** `pending_tool_execution` обрабатывается в `protocol.handle_and_process()`,
> а не в транспорте. Транспорт только отправляет outcome — это предотвращает
> двойное выполнение tool (ранее и protocol, и transport schedule'или задачу).

**Полный паритет с WebSocketTransport:**

| Фича | WebSocket | Stdio |
|------|-----------|-------|
| Background `session/prompt` | ✅ `_process_prompt_request_in_background` | ✅ `_process_prompt_request_in_background` |
| Deferred prompt completion | ✅ `_complete_deferred_prompt` | ✅ `_complete_deferred_prompt` |
| Pending tool execution | ✅ `handle_and_process()` | ✅ `handle_and_process()` |
| `session/cancel` → отмена deferred | ✅ | ✅ |
| Cleanup при disconnect | ✅ `prompt_request_tasks` cleanup | ✅ `_cleanup_background_tasks` |

**Файлы:**
- [`src/codelab/server/transport/stdio.py`](src/codelab/server/transport/stdio.py) — основная логика
- [`src/codelab/server/transport/stdio_runner.py`](src/codelab/server/transport/stdio_runner.py) — проброс callbacks из `ACPProtocol`

**Тесты:** 14 новых unit-тестов в [`tests/server/transport/test_stdio.py`](tests/server/transport/test_stdio.py), включая регрессионный тест `test_bypass_mode_client_rpc_response_routes_during_prompt`.

---

## Расширение и интеграция

### Добавление нового инструмента в codelab.server

1. **Определить инструмент** в `tools/definitions/`
2. **Реализовать executor** в `tools/executors/`
3. **Зарегистрировать** в `PromptOrchestrator`

Пример:

```python
from acp_server.tools.base import ToolDefinition, ToolExecutor

class MyToolDefinition(ToolDefinition):
    id = "my/tool"
    name = "My Tool"
    
    async def execute(self, input_schema: dict) -> dict:
        # Реализация
        pass

class MyToolExecutor(ToolExecutor):
    async def execute(self, name: str, arguments: dict) -> dict:
        # Выполнение
        pass

# В PromptOrchestrator.__init__():
tool_registry.register("my/tool", MyToolDefinition(), MyToolExecutor())
```

### Добавление нового обработчика в codelab.client

1. **Создать handler** в `infrastructure/handlers/`
2. **Зарегистрировать** в [`HandlerRegistry`](src/codelab/client/infrastructure/handler_registry.py)
3. **Добавить tests** в `tests/`

Пример:

```python
from acp_client.infrastructure.handler_registry import HandlerRegistry

class MyHandler:
    async def handle(self, request: dict) -> dict:
        # Обработка запроса
        pass

# Регистрация:
registry = HandlerRegistry()
registry.register("my/method", MyHandler())
```

### Интеграция нового LLM провайдера

1. **Наследовать** [`BaseLLMProvider`](src/codelab/server/llm/base.py)
2. **Реализовать** `async generate()` метод
3. **Зарегистрировать** в CLI флаге `--llm-provider`

Пример:

```python
from acp_server.llm.base import BaseLLMProvider, LLMMessage

class MyLLMProvider(BaseLLMProvider):
    async def generate(self, messages: list[LLMMessage]) -> str:
        # Вызов API
        response = await my_api.generate(messages)
        return response.text
```

---

## Документы проекта

### Справочная документация

- **[codelab/README.md](codelab/README.md)** — основная документация проекта
- **[doc/product/developer-guide/](doc/product/developer-guide/)** — руководство разработчика

### Специальные документы

- **[AGENTS.md](AGENTS.md)** — инструкции для агентных ассистентов
- **[doc/architecture/ACP_IMPLEMENTATION_VERIFICATION.md](doc/architecture/ACP_IMPLEMENTATION_VERIFICATION.md)** — верифицированная матрица соответствия ACP спецификации (3,302 теста)
- **[doc/architecture/FULL_ARCHITECTURE.md](doc/architecture/FULL_ARCHITECTURE.md)** — полная схема проекта с мультиагентной экосистемой
- **[doc/Agent Client Protocol/](doc/Agent%20Client%20Protocol/)** — официальная спецификация ACP (не менять!)

---

## Заключение

Архитектура Codelab разработана для:
- ✅ **Модульности** — каждый компонент отвечает за одно
- ✅ **Расширяемости** — добавление новых компонентов не требует изменений существующих
- ✅ **Тестируемости** — все слои имеют интерфейсы для mock-объектов
- ✅ **Производительности** — асинхронность, потоковые обновления, оптимальные структуры данных
- ✅ **Безопасности** — валидация, аутентификация, логирование всех операций
