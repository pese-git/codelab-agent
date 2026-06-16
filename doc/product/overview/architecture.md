# Архитектура CodeLab

> Обзор архитектуры системы и взаимодействия компонентов.

## Общая архитектура

CodeLab реализует клиент-серверную архитектуру, определённую [Agent Client Protocol (ACP)](../../protocols/Agent%20Client%20Protocol/get-started/02-Architecture.md).

```mermaid
graph TB
    subgraph Client["Клиент (Clean Architecture + MVVM)"]
        TUI["TUI Components<br/>45+ widgets"]
        VM[14 ViewModels]
        UC[Use Cases]
        TS["ACPTransportService<br/>WebSocket / stdio"]
        BgLoop[BackgroundReceiveLoop]
    end
    
    subgraph Transport["Транспорт"]
        WS["WebSocket<br/>JSON-RPC 2.0"]
        STDIO["stdio<br/>stdin/stdout"]
    end
    
    subgraph Server["Сервер (Dishka DI)"]
        HTTP[ACPHttpServer]
        AP[ACPProtocol]
        PO[PromptOrchestrator]
        EE[ExecutionEngine]
        TR[ToolRegistry]
        MCP[MCPManager]
        Storage["SessionStorage<br/>LRU Cache"]
    end
    
    subgraph External["Внешние системы"]
        LLM["LLM Providers<br/>OpenAI/Anthropic/OpenRouter/Zen/Go/Ollama/LMStudio/Mock"]
        FS[File System]
        TERM[Terminal]
    end
    
    TUI --> VM --> UC --> TS
    TS --> BgLoop
    TS --> WS & STDIO
    WS & STDIO --> HTTP --> AP --> PO
    PO --> EE --> LLM
    PO --> TR --> FS & TERM
    PO --> MCP
    AP --> Storage
```

## Компоненты системы

### Клиент (Client)

Клиент реализует **Clean Architecture** с 5 слоями и **MVVM паттерн** для реактивного UI:

```mermaid
graph TB
    subgraph TUI["TUI Layer (45 компонентов)"]
        Chat[ChatView]
        Sidebar[Sidebar]
        FileTree[FileTree]
        Prompt[PromptInput]
        ToolPanel[ToolPanel]
        CmdPalette[CommandPalette]
    end
    
    subgraph Presentation["Presentation Layer"]
        VM1[UIViewModel]
        VM2[SessionViewModel]
        VM3[ChatViewModel]
        VM4[PlanViewModel]
        VM5[TerminalViewModel]
        VM6[FileSystemViewModel]
        VM7[FileViewerViewModel]
        VM8[PermissionViewModel]
        VM9[TerminalLogViewModel]
        VM10[ModelSelectorViewModel]
        VM11[ModeSelectorViewModel]
        VM12[AgentSelectorViewModel]
        VM13[StrategySelectorViewModel]
        VM14[ConfigOptionSelectorViewModel]
    end
    
    subgraph Application["Application Layer"]
        UC1[InitializeUseCase]
        UC2[CreateSessionUseCase]
        UC3[SendPromptUseCase]
        UC4[ListSessionsUseCase]
        SM[UIStateMachine]
        PH[PermissionHandler]
    end
    
    subgraph Infrastructure["Infrastructure Layer"]
        DI[Dishka Container]
        TS[ACPTransportService]
        BgLoop[BackgroundReceiveLoop]
        Router[MessageRouter]
        Queues[RoutingQueues]
        EB[EventBus]
        Handlers[FS/Terminal Handlers]
    end
    
    subgraph Domain["Domain Layer"]
        Entities["Session, Message"]
        Repos[Repositories]
        Events[16 Domain Events]
    end
    
    Chat & Sidebar & FileTree & Prompt & ToolPanel & CmdPalette --> VM1 & VM2 & VM3 & VM4 & VM5 & VM6 & VM7 & VM8 & VM9 & VM10 & VM11 & VM12 & VM13 & VM14
    VM1 & VM2 & VM3 & VM4 & VM5 & VM6 & VM7 & VM8 & VM9 & VM10 & VM11 & VM12 & VM13 & VM14 --> UC1 & UC2 & UC3 & UC4
    UC1 & UC2 & UC3 & UC4 --> SM & PH
    SM & PH --> DI
    DI --> TS & EB & Handlers
    TS --> BgLoop --> Router --> Queues
    Queues --> EB --> Entities & Repos & Events
```

**Слои клиента:**
- **TUI Layer** — 45+ Textual компонентов (ChatView, Sidebar, FileTree, CommandPalette, ModelSelector, и др.)
- **Presentation** — 14 ViewModels с Observable состоянием (MVVM): 9 базовых + 5 selector ViewModels
- **Application** — 5 Use Cases, UIStateMachine, PermissionHandler
- **Infrastructure** — Dishka DI, ACPTransportService, BackgroundReceiveLoop, MessageRouter, EventBus
- **Domain** — Session, Message, Permission, ToolCall, Repository интерфейсы, 16 Domain Events

### Сервер (Server)

Сервер использует **Dishka DI контейнер** с двумя скоупами и **Pipeline систему** для обработки промптов:

```mermaid
graph TB
    subgraph Transport["Transport Layer"]
        HTTP[ACPHttpServer]
        WS[WebSocketTransport]
        STDIO[StdioServerTransport]
    end
    
    subgraph Protocol["Protocol Layer"]
        AP["ACPProtocol<br/>REQUEST scope"]
        PO["PromptOrchestrator<br/>APP scope"]
    end
    
    subgraph Pipeline["Pipeline (7 стадий)"]
        V[ValidationStage]
        SC[SlashCommandStage]
        PB[PlanBuildingStage]
        TL1[TurnLifecycleStage open]
        DS[DirectivesStage]
        LL[LLMLoopStage]
        TL2[TurnLifecycleStage close]
    end
    
    subgraph Managers["Managers (APP scope)"]
        SM[StateManager]
        PBuilder[PlanBuilder]
        TLCM[TurnLifecycleManager]
        TCH[ToolCallHandler]
        PM[PermissionManager]
        CRH[ClientRPCHandler]
        GPM[GlobalPolicyManager]
    end
    
    subgraph Agent["Agent Layer"]
        AO[AgentOrchestrator]
        EE[ExecutionEngine]
        AL[AgentLoop]
        LLM["LLM Registry<br/>8+ Providers"]
    end
    
    subgraph Tools["Tools Layer"]
        TR[ToolRegistry]
        FS[FileSystemExecutor]
        TE[TerminalToolExecutor]
        Bridge[ClientRPCBridge]
    end
    
    subgraph MCP["MCP Layer"]
        MM[MCPManager]
        MT[MCPToolAdapter]
        MTE[MCPToolExecutor]
        SRR[SessionRuntimeRegistry]
    end
    
    subgraph Storage["Storage Layer"]
        SS["SessionStorage<br/>LRU Cache"]
        GPS[GlobalPolicyStorage]
    end
    
    subgraph Observability["Observability Layer"]
        Tracer[Tracer]
        Timeline[EventTimeline]
        Metrics[MetricsTracker]
    end
    
    HTTP --> WS & STDIO
    WS & STDIO --> AP
    AP --> PO
    PO --> Pipeline
    V --> SC --> PB --> TL1 --> DS --> LL --> TL2
    PO --> SM & PBuilder & TLCM & TCH & PM & CRH & GPM
    LL --> AO --> EE --> LLM
    LL --> TR --> FS & TE --> Bridge
    LL --> MM --> MT
    LL --> MTE
    SRR --> MM
    AP --> SS
    PM --> GPS
    EE -.-> Tracer & Timeline & Metrics
```

**Скоупы DI контейнера:**
- **APP scope** — синглтоны на всё время жизни сервера (LLM, ToolRegistry, менеджеры, pipeline)
- **REQUEST scope** — на одно WebSocket соединение (ClientRPCService, ACPProtocol)

**Менеджеры:**
| Менеджер | Ответственность |
|----------|-----------------|
| `StateManager` | Управление состоянием сессии |
| `PlanBuilder` | Построение планов выполнения |
| `TurnLifecycleManager` | Жизненный цикл prompt-turn |
| `ToolCallHandler` | Обработка tool calls |
| `PermissionManager` | Управление разрешениями |
| `ClientRPCHandler` | Обработка agent→client RPC |
| `GlobalPolicyManager` | Глобальные политики разрешений |

**Pipeline стадии:**
1. `ValidationStage` — валидация входных данных
2. `SlashCommandStage` — обработка `/help`, `/mode`, `/status`, `/strategy`
3. `PlanBuildingStage` — построение плана
4. `TurnLifecycleStage(open)` — открытие turn
5. `DirectivesStage` — обработка директив промпта
6. `LLMLoopStage` — основной цикл LLM с tool calls
7. `TurnLifecycleStage(close)` — закрытие turn

## Background Receive Loop (Клиент)

Для избежания race condition при конкурентном доступе к WebSocket, клиент использует единый фоновый цикл получения сообщений:

```mermaid
graph TD
    A["WebSocket.receive_text()"] --> B["BackgroundReceiveLoop"]
    B --> C["MessageRouter.route()"]
    C --> D{"Тип сообщения"}
    D -->|session/update| E["notification_queue"]
    D -->|session/request_permission| F["permission_queue"]
    D -->|fs/* или terminal/*| E
    D -->|есть id| G["response_queue[id]"]
    D -->|session/cancel| E
    E --> H["Callbacks в request_with_callbacks()"]
    F --> I["PermissionHandler"]
    G --> J["asyncio.Future.set_result()"]
```

**Ключевые особенности:**
- **Единственный receive()** — избегает RuntimeError при конкурентном доступе
- **Три типа очередей:** response (per-request), notification (shared), permission (shared)
- **Graceful shutdown** — await stop() с 5-секундным таймаутом
- **Broadcast ошибок** — при разрыве соединения все ожидающие очереди получают уведомление

## Двухуровневая история

На сервере существует **двухуровневая система истории**:

| Аспект | SessionState.history | events_history |
|--------|----------------------|-----------------|
| **Содержание** | Message objects (user/assistant) | Structured events (started, added, completed) |
| **Использование** | Передача LLM для контекста | Восстановление state при session/load |
| **Обновление** | Централизованно в PromptOrchestrator | Через TurnLifecycleManager |
| **Размер** | Компактный (только сообщения) | Расширенный (все события) |

**ReplayManager** использует `events_history` для полного восстановления состояния сессии при `session/load`.

## MCP интеграция

Модуль `server/mcp/` обеспечивает подключение внешних MCP-серверов для расширения инструментов агента.

```mermaid
graph TB
    subgraph "MCP Layer"
        MM[MCPManager]
        MC[MCPClient]
        TA[MCPToolAdapter]
        TE[MCPToolExecutor]
    end
    
    subgraph "Transports"
        STDIO[StdioTransport]
        HTTP[HttpTransport]
        SSE[SseTransport]
    end
    
    subgraph "Runtime"
        SRR[SessionRuntimeRegistry]
        SRS[SessionRuntimeState]
    end
    
    subgraph "Protocol"
        LL[LLMLoopStage]
        TR[ToolRegistry]
    end
    
    LL -->|mcp_manager| MM
    MM --> MC
    MM --> TA
    MM --> TE
    MC --> STDIO & HTTP & SSE
    SRR --> SRS
    SRS --> MM
    TE --> TR
```

### Компоненты

| Компонент | Файл | Описание |
|-----------|------|----------|
| `MCPClient` | `client.py` | Клиент для одного MCP-сервера с state machine (Created → Connecting → Initializing → Ready) |
| `MCPManager` | `manager.py` | Управление несколькими MCP-серверами, auto-reconnect, health check |
| `MCPToolAdapter` | `tool_adapter.py` | Адаптация MCP инструментов к ACP ToolDefinition, kind inference |
| `MCPToolExecutor` | `executors/mcp_executor.py` | Executor для MCP инструментов через ToolRegistry |
| `StdioTransport` | `transport.py` | Запуск MCP-серверов через stdio subprocess |
| `HttpTransport` | `transport.py` | HTTP POST с JSON-RPC для удалённых серверов |
| `SseTransport` | `transport.py` | Server-Sent Events (deprecated в MCP spec) |
| `SessionRuntimeRegistry` | `session_runtime.py` | REQUEST-scoped реестр runtime объектов (отделяет MCP manager от SessionState) |

### MCP модели данных

| Модель | Описание |
|--------|----------|
| `MCPServerConfig` | Конфигурация сервера: type, command, args, url, headers, env, retry config |
| `MCPTool` | Определение инструмента: name, description, inputSchema, annotations |
| `MCPToolAnnotations` | Аннотации для kind inference: readOnlyHint, destructiveHint, idempotentHint, openWorldHint |
| `MCPResource` | Ресурс MCP: uri, name, description, mimeType |
| `MCPPrompt` | Промпт MCP: name, description, arguments |

### Именование MCP инструментов

`mcp:server_id:tool_name` — namespace для избежания конфликтов с встроенными инструментами.

### Kind Inference

Автоматическое определение типа MCP инструмента для системы разрешений:

```mermaid
graph TD
    A[MCP Tool] --> B{Есть annotations?}
    B -->|Да| C[ToolAnnotations]
    B -->|Нет| D{Анализ имени}
    
    C -->|readOnlyHint=true| E[read]
    C -->|destructiveHint=true| F[execute]
    C -->|idempotentHint=true| G[edit]
    C -->|openWorldHint=true| F
    
    D -->|read_*, get_*, list_*| E
    D -->|write_*, create_*, delete_*| F
    D -->|update_*, modify_*| G
    D -->|Не определено| H[other]
```

### Auto-reconnect

```mermaid
stateDiagram-v2
    [*] --> Ready
    Ready --> Connected: Сервер подключён
    Connected --> Failure: Ошибка соединения
    Failure --> Reconnecting: Запуск reconnect
    Reconnecting --> Connected: Успешное подключение
    Reconnecting --> Failed: Превышены попытки
    Failed --> [*]
    
    note right of Reconnecting
      Exponential backoff:
      1s → 2s → 4s → 8s → 16s → 30s
      + jitter 10%
    end note
```

### SessionRuntimeRegistry

Отделяет runtime объекты (MCP manager) от сериализуемого SessionState:

- **Проблема:** SessionState сохраняется в JSON, но MCPManager содержит subprocesses
- **Решение:** SessionRuntimeRegistry хранит MCP manager отдельно
- **Скоуп:** REQUEST-scoped через Dishka
- **Cleanup:** Автоматический shutdown MCP subprocesses при disconnect

> **Подробная документация:** [MCP серверы (user guide)](../user-guide/extensions/mcp-servers.md) · [MCP разработка (dev guide)](../developer-guide/mcp-development.md)

## Протокол ACP

Взаимодействие происходит через JSON-RPC 2.0:

```mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    participant A as Agent (LLM)
    
    Note over C,S: Инициализация
    C->>S: initialize
    S-->>C: capabilities
    
    Note over C,S: Сессия
    C->>S: session/new
    S-->>C: session_id
    
    Note over C,S: Prompt Turn
    C->>S: session/prompt
    
    loop Agent работает
        S->>A: LLM запрос
        A-->>S: tool_call
        S-->>C: notification (tool_call)
        S->>C: session/request_permission
        C-->>S: permission response
        S-->>C: notification (result)
    end
    
    S-->>C: session/update {stopReason}
```

**Методы протокола:**
| Метод | Направление | Описание |
|-------|-------------|----------|
| `initialize` | C→S | Инициализация, обмен capabilities |
| `authenticate` | C→S | Аутентификация (API key) |
| `session/new` | C→S | Создание новой сессии |
| `session/load` | C→S | Загрузка существующей сессии |
| `session/list` | C→S | Список сессий |
| `session/prompt` | C→S | Отправка промпта |
| `session/cancel` | C→S | Отмена текущего промпта |
| `session/update` | S→C | Уведомление о ходе выполнения |
| `session/request_permission` | S→C | Запрос разрешения |
| `session/request_permission_response` | C→S | Ответ на запрос разрешения |
| `session/set_config_option` | C→S | Установка опции конфигурации |
| `session/set_mode` | C→S | Установка режима сессии |

## Агент и LLM

### Цикл обработки prompt

Полный путь запроса от пользователя до ответа LLM:

```mermaid
sequenceDiagram
    participant U as Пользователь
    participant C as Client
    participant S as ACPProtocol
    participant PO as PromptOrchestrator
    participant LL as LLMLoopStage
    participant AL as AgentLoop
    participant EE as ExecutionEngine
    participant LLM as OpenAIProvider
    participant TR as ToolRegistry
    participant TM as ToolMapping

    U->>C: Вводит prompt
    C->>S: session/prompt
    S->>PO: handle_prompt()
    PO->>LL: process(context)

    loop LLM Loop (до 10 итераций)
        AL->>EE: execute(context)
        EE->>TM: acp_name_to_llm_name() для инструментов
        TM-->>EE: LLM-совместимые имена (с _)
        EE->>LLM: create_completion(messages, tools)
        LLM-->>EE: LLMResponse(text, tool_calls, stop_reason)
        EE-->>AL: AgentResponse

        alt stop_reason = end_turn
            AL-->>LL: stop_reason=end_turn
            LL-->>PO: stop_reason=end_turn
            PO-->>S: ProtocolOutcome
            S-->>C: session/update + result
            C-->>U: Показывает ответ
        else stop_reason = tool_use
            loop Для каждого tool call
                LL->>TM: llm_name_to_acp_name(tool_name)
                TM-->>LL: ACP имя (с /)
                LL->>TR: execute_tool() или request_permission
                TR-->>LL: ToolResult
                S-->>C: session/update (статус инструмента)
            end
            LL->>LL: continue_turn с tool_results
        end
    end
```

### LLM Loop — алгоритм

```mermaid
flowchart TD
    START([session/prompt]) --> HIST["Подготовить историю сообщений"]
    HIST --> TOOLS["Получить список инструментов"]
    TOOLS --> MAP1["acp_name_to_llm_name()<br/>/ → _"]
    MAP1 --> CANCEL{"Отмена<br/>запрошена?"}
    CANCEL -->|Да| CANCELLED([stop_reason = cancelled])
    CANCEL -->|Нет| LLM["Вызов LLM API"]
    LLM --> PARSE["Разобрать ответ"]
    PARSE --> HAS_TOOLS{"Есть<br/>tool calls?"}

    HAS_TOOLS -->|Нет| END_TURN([stop_reason = end_turn])

    HAS_TOOLS -->|Да| FOREACH["Для каждого tool call"]
    FOREACH --> MAP2["llm_name_to_acp_name()<br/>_ → /"]
    MAP2 --> POLICY{"Политика"}
    POLICY -->|allow| EXEC["Выполнить инструмент"]
    POLICY -->|ask| PERM(["Запросить разрешение<br/>Пайплайн приостановлен"])
    POLICY -->|reject| FAIL["Пометить failed"]

    EXEC --> RESULT["ToolResult"]
    FAIL --> RESULT
    RESULT --> MORE{"Ещё<br/>tool calls?"}
    MORE -->|Да| FOREACH
    MORE -->|Нет| MAXITER{"Макс.<br/>итераций?"}
    MAXITER -->|Да| MAX([stop_reason = max_turn_requests])
    MAXITER -->|Нет| CANCEL
```

### Отмена prompt

```mermaid
sequenceDiagram
    participant U as Пользователь
    participant C as Client
    participant TS as ACPTransportService
    participant S as ACPProtocol
    participant PO as PromptOrchestrator
    participant AL as AgentLoop
    participant LLM as OpenAI API

    Note over AL,LLM: asyncio.Task — HTTP запрос к LLM
    AL->>LLM: POST /chat/completions

    U->>C: Нажимает Stop
    Note over TS: cancel_prompt() обходит<br/>_callbacks_request_lock
    C->>TS: stop_button_pressed
    TS->>S: session/cancel (немедленно)
    S->>PO: cancel_prompt(session_id)
    PO->>AL: active_task.cancel()
    LLM--xAL: CancelledError
    AL-->>PO: stop_reason=cancelled
    PO-->>S: stop_reason=cancelled
    S-->>C: session/update {stopReason: cancelled}
    C-->>U: Стриминг остановлен
```

## Мультиагентная система

### Архитектура

Сервер поддерживает несколько стратегий выполнения агентов через EventBus-архитектуру:

```mermaid
graph TB
    subgraph "Strategy Layer"
        SD[StrategyDispatcher]
        SR[StrategyRegistry]
        DESC[StrategyDescriptor]
    end

    subgraph "Agent Layer"
        AR[AgentRegistry]
        AF[AgentFactory]
        EB[AgentEventBus]
        AL[LLMAdapter]
    end

    subgraph "Strategies"
        SS[SingleStrategy]
        MS[Multi-Orchestrated]
        MC[Multi-Choreographed]
        H[Hierarchical]
    end

    subgraph "Config"
        ACL[AgentConfigLoader]
        ACR[AgentConfigResolver]
    end

    SD --> SR
    SR --> DESC
    SD --> SS & MS & MC & H
    SS --> EB
    EB --> AL
    AR --> AF --> AL
    AR --> EB
    ACL --> ACR --> AR
```

### Стратегии выполнения

| Стратегия | ID | Описание |
|-----------|----|----------|
| **Single** | `single` | Один агент через EventBus. Базовая стратегия, всегда доступна |
| **Multi-Orchestrated** | `multi_orchestrated` | Оркестратор + subагенты |
| **Multi-Choreographed** | `multi_choreographed` | Peer-to-peer collaboration через broadcast |
| **Hierarchical** | `hierarchical` | Primary делегирует subагентам |

### StrategyDispatcher — приоритет выбора

```mermaid
flowchart TD
    A[Запрос] --> B{context_meta active_strategy?}
    B -->|Да| C[Slash command override]
    B -->|Нет| D{config_values _active_strategy?}
    D -->|Да| E[Persistent config]
    D -->|Нет| F[Server default]
    C --> G{Доступна?}
    E --> G
    F --> G
    G -->|Да| H[Использовать]
    G -->|Нет| I[Fallback strategy]
    I --> J{Fallback доступен?}
    J -->|Да| H
    J -->|Нет| K[Первая доступная]
```

### LLMCallStrategy Protocol

```python
class LLMCallStrategy(Protocol):
    async def execute(self, session, prompt, mcp_manager) -> AgentResponse: ...
    async def continue_execution(self, session, mcp_manager) -> AgentResponse: ...
```

`AgentLoop` зависит от абстракции (DIP), конкретные стратегии реализуют Protocol. Добавление новой стратегии не требует изменения `AgentLoop` (OCP).

### StrategyDescriptor — self-describing стратегии

```python
@dataclass
class StrategyDescriptor:
    name: str                          # "single", "hierarchical"
    display_name: str                  # "Single", "Hierarchical"
    description: str                   # Описание для UI
    factory: Callable[[StrategyDependencies], LLMCallStrategy]
    validator: Callable[[AgentRegistry], bool]  # Проверка доступности
```

### AgentRegistry

Единый реестр агентов с загрузкой конфигураций из 4 источников:

```mermaid
flowchart LR
    subgraph "Источники (приоритет от низшего к высшему)"
        GT["~/.codelab/codelab.toml<br/>[agents.definitions.*]"]
        GM["~/.codelab/agents/*.md"]
        PT["codelab.toml<br/>[agents.definitions.*]"]
        PM[".codelab/agents/*.md"]
    end

    GT --> GM --> PT --> PM --> AR[AgentRegistry]
    AR --> AF[AgentFactory]
    AF --> EB[AgentEventBus]
```

### Роли агентов

| Роль | Описание |
|------|----------|
| `primary` | Основной агент, обрабатывает запросы пользователя |
| `subagent` | Subагент для делегирования задач |
| `orchestrator` | Оркестратор, управляет subагентами |

### Формат Markdown-конфигурации агента

```markdown
---
name: coder
role: primary
model: openai/gpt-4o
temperature: 0.0
priority: 10
permissions:
  edit: true
  bash: true
---
Ты — эксперт-разработчик. Пиши чистый код...
```

### AgentEventBus

In-memory шина межагентской коммуникации. Реализует два интерфейса:

| Интерфейс | Назначение |
|-----------|------------|
| `AbstractEventBus` (pub/sub) | Observability: MetricsTracker, EventTimeline подписываются на события |
| `AgentRoutingInterface` (routing) | Стратегии отправляют запросы агентам через `send_request()` и `broadcast()` |

```mermaid
sequenceDiagram
    participant S as Strategy
    participant EB as AgentEventBus
    participant A as LLMAdapter (agent)
    participant OBS as Observability

    S->>EB: send_request(AgentRequest)
    EB->>A: handler(request)
    A-->>EB: AgentResult
    EB->>EB: wrap in AgentResponse
    EB->>OBS: publish(AgentResponse)
    EB-->>S: AgentResponse
```

**Retry:** `send_request()` повторяет до `max_attempts` (по умолчанию 3) с exponential backoff.

**Broadcast:** `broadcast()` рассылает `ContextBroadcast` всем агентам параллельно, собирает `ChoreographyAnswer`. При частичном падении — `BroadcastPartialFailure`.

### Domain Events

| Событие | Описание |
|---------|----------|
| `AgentRegistered` | Агент зарегистрирован в шине |
| `AgentUnregistered` | Агент удалён из шины |
| `AgentListChanged` | Список агентов изменился (пакетная операция) |
| `AgentResponse` | Ответ агента (для observability) |
| `AgentRequest` | Запрос к агенту |
| `ContextBroadcast` | Broadcast всем агентам |
| `ChoreographyAnswer` | Ответ агента на broadcast |

### AgentFactory

Фабрика создания `LLMAdapter` из конфигурации агента. Каждый агент может использовать свою модель:

```python
class AgentFactory:
    async def create_adapter(self, agent: ResolvedAgent) -> LLMAdapter:
        # Резолвит model → LLMProvider через LLMProviderRegistry
        # Создаёт LLMAdapter с правильным провайдером
        # Кэширует adapter per agent_name
```

### Slash-команда `/strategy`

```
/strategy              # Показать текущую strategy и доступные
/strategy hierarchical # Переключить на hierarchical
```

Сохраняет выбор в `session.config_values["_active_strategy"]` для persistence между turn'ами.

## Observability

### Архитектура

```mermaid
graph TB
    subgraph "Collection"
        Tracer[Tracer]
        MT[MetricsTracker]
        ET[EventTimeline]
    end

    subgraph "Event Bus"
        EB[AgentEventBus]
    end

    subgraph "Exporters"
        FSE[FileSpanExporter]
        FME[FileMetricsExporter]
        FEE[FileEventExporter]
    end

    subgraph "Storage"
        SD["~/.codelab/data/observability/spans/"]
        MD["~/.codelab/data/observability/metrics/"]
        ED["~/.codelab/data/observability/events/"]
    end

    EB -->|subscribe| MT
    EB -->|subscribe| ET
    Tracer --> FSE --> SD
    MT --> FME --> MD
    ET --> FEE --> ED
```

### Tracer

Span hierarchy с context propagation:

```mermaid
graph TD
    S1["strategy_execution"] --> S2["bus_request"]
    S2 --> S3["llm_call"]
    S2 --> S4["tool_execution"]
```

| Компонент | Описание |
|-----------|----------|
| `SpanContext` | ID, name, parent_id, attributes, start/end_time, session_id |
| `Tracer` | Управление span'ами: start/end/current, стек активных span'ов |
| `debug` mode | Сохраняет полные атрибуты span'ов |

### MetricsTracker

Автоматический сбор метрик через подписку на EventBus:

| Метрика | Описание |
|---------|----------|
| `bus_dispatch_count` / `bus_dispatch_total_ms` | Dispatch операции |
| `llm_call_count` / `llm_total_input_tokens` / `llm_total_output_tokens` | LLM вызовы |
| `compression_count` / `compression_total_ratio` | Context compression |
| `slicer_count` / `slicer_total_original_tokens` / `slicer_total_sliced_tokens` | Token slicing |
| `strategy_execution_count` / `strategy_execution_total_ms` | Выполнение стратегий |
| `agent_responses` / `agent_errors` | Ответы и ошибки агентов |

### EventTimeline

Хронология событий сессии. Автоматически подписывается на:
- `AgentRegistered`, `AgentUnregistered`, `AgentListChanged`, `AgentResponse`

### File Exporters

| Экспортёр | Формат файла | Режим |
|-----------|-------------|-------|
| `FileSpanExporter` | `spans/YYYY-MM-DD-HH-MM-SS.json` | Write + ротация |
| `FileMetricsExporter` | `metrics/YYYY-MM-DD.json` | Overwrite (atomic) |
| `FileEventExporter` | `events/YYYY-MM-DD.json` | Append + ротация |

Все экспортёры поддерживают:
- **Ротация** при превышении `max_file_size` (по умолчанию 10MB)
- **Cleanup** удаление файлов старше `max_age_days` (по умолчанию 30 дней)
- **ExportMetrics** — метрики экспорта (total_exports, failed_exports, total_items_exported)
- **Background flush** через `ObservabilityFlushManager` (APP scope)

### Конфигурация observability

```toml
[observability]
enabled = true
export_dir = "~/.codelab/data/observability"
flush_interval = 60       # секунды
max_file_size = 10485760  # 10MB
```

## Middleware (Protocol Layer)

Middleware применяется в порядке onion pattern: первое в списке — внешнее, последнее — ближе к обработчику.

```mermaid
flowchart LR
    REQ[Request] --> MW1[Middleware 1]
    MW1 --> MW2[Middleware 2]
    MW2 --> H[Handler]
    H --> MW2
    MW2 --> MW1
    MW1 --> RES[Response]
```

### Встроенные middleware

| Middleware | Описание |
|------------|----------|
| `message_trace_middleware` | Трассировка JSON-RPC сообщений (вкл. через `--trace-messages`) |

**Message Trace Middleware:**
- Логирует входящие запросы и исходящие ответы с полным payload
- Пишет в отдельный logger `codelab.trace` (JSON формат)
- Поддерживает обрезку payload через `max_payload_length`
- Контекст: `connection_id`, `request_id`, `direction` (in/out)

```python
trace_mw = create_message_trace_middleware(
    enabled=True,
    connection_id="abc123",
    max_payload_length=4096,
)
protocol = ACPProtocol(middleware=[trace_mw])
```

## LLM подсистема (детали)

### Model Discovery

```python
class ModelDiscovery(ABC):
    async def discover_models(self) -> list[ModelInfo]: ...
```

| Реализация | Описание |
|------------|----------|
| `StaticDiscovery` | Статический список моделей из `ProviderInfo` (используется сейчас) |
| `DiscoveryConfig` | Конфигурация: `enabled`, `refresh_interval`, `default_models` |

Extension points: `OllamaDiscovery` (dynamic через Ollama API), `LMStudioDiscovery` — future.

### Telemetry

```python
class TelemetrySink(ABC):
    async def record_request(self, provider_id, model_id, latency_ms, success): ...
    async def record_cost(self, provider_id, model_id, cost_usd): ...
```

| Реализация | Описание |
|------------|----------|
| `NoOpTelemetry` | Заглушка (используется сейчас) |

Extension points: `PrometheusTelemetry`, `DatadogTelemetry` — future.

### LLM Timeouts

```toml
[llm.timeout]
connect = 30.0   # Таймаут подключения к API (секунды)
read = 300.0     # Таймаут ожидания ответа (секунды)
write = 30.0     # Таймаут отправки запроса (секунды)
pool = 30.0      # Таймаут ожидания соединения из пула (секунды)
```

CLI: `--llm-timeout-connect`, `--llm-timeout-read`, `--llm-timeout-write`, `--llm-timeout-pool`.

## Потоки данных

### Prompt Turn

Цикл обработки пользовательского запроса:

```mermaid
flowchart TD
    A[User Prompt] --> B[session/prompt]
    B --> C{Agent Planning}
    C --> D[Generate Plan]
    D --> E{Execute Tools}
    
    E --> F[Tool Call]
    F --> G{Need Permission?}
    G -->|Yes| H[Request Permission]
    H --> I{User Decision}
    I -->|Allow| J[Execute]
    I -->|Deny| K[Skip]
    G -->|No| J
    
    J --> L[Tool Result]
    K --> L
    L --> M{More Tools?}
    M -->|Yes| E
    M -->|No| N[Final Response]
    N --> O[prompt/finished]
```

### Система разрешений

```mermaid
flowchart LR
    subgraph "Permission Flow"
        Tool[Tool Call] --> Check{Check Policy}
        Check -->|Auto-Allow| Execute[Execute]
        Check -->|Auto-Deny| Skip[Skip]
        Check -->|Ask|         Request["Request<br/>Permission"]
        Request --> User{User}
        User -->|Allow| Execute
        User -->|Allow All|         Policy["Update<br/>Policy"]
        Policy --> Execute
        User -->|Deny| Skip
    end
```

## Хранение данных

### Структура сессий

```mermaid
erDiagram
    SESSION ||--o{ MESSAGE : contains
    SESSION ||--o{ TOOL_CALL : has
    SESSION {
        string id PK
        string name
        datetime created_at
        json config
        json context
    }
    MESSAGE {
        string id PK
        string session_id FK
        string role
        json content
        datetime timestamp
    }
    TOOL_CALL {
        string id PK
        string session_id FK
        string tool_name
        json arguments
        json result
        string status
    }
```

## Директории проекта

```
codelab/src/codelab/
├── shared/              # Общие модули
│   ├── messages.py      # JSON-RPC сообщения
│   ├── logging.py       # Структурированное логирование
│   └── content/         # Типы контента ACP
│
├── server/              # Серверная часть
│   ├── di.py            # Dishka DI контейнер
│   ├── config.py        # Pydantic конфигурация
│   ├── http_server.py   # HTTP/WebSocket сервер
│   ├── web_app.py       # Web UI (textual-web)
│   ├── rpc_holder.py    # ClientRPCServiceHolder
│   ├── protocol/        # ACP протокол
│   │   ├── core.py      # ACPProtocol (dispatcher)
│   │   ├── state.py     # SessionState, ToolCallState
│   │   ├── handlers/    # Обработчики методов
│   │   │   ├── auth.py
│   │   │   ├── session.py
│   │   │   ├── prompt.py
│   │   │   ├── permissions.py
│   │   │   ├── config.py
│   │   │   ├── prompt_orchestrator.py  # Главный координатор
│   │   │   ├── pipeline/               # 7 стадий pipeline
│   │   │   ├── slash_commands/         # /help, /mode, /status, /strategy
│   │   │   ├── middleware/             # message_trace middleware
│   │   │   └── ... (менеджеры)
│   │   └── content/     # Extractor, Validator, Formatter
│   ├── agent/           # LLM агент (ExecutionEngine, AgentLoop, Strategies, EventBus)
│   │   ├── strategies/  # StrategyRegistry, StrategyDispatcher, SingleStrategy
│   │   ├── config/      # AgentConfigLoader, AgentConfigResolver (TOML + Markdown)
│   │   ├── contracts/   # DomainEvent, AgentRequest, AgentResponse, Broadcast
│   │   └── event_bus/   # AgentEventBus (pub/sub + routing)
│   ├── tools/           # Инструменты (registry, executors)
│   ├── storage/         # Хранилище сессий (LRU cache)
│   ├── mcp/             # MCP интеграция
│   ├── client_rpc/      # Agent→Client RPC
│   ├── llm/             # LLM подсистема (Registry, 8+ Providers, Fallback, Events)
│   ├── observability/   # Tracer, Metrics, Timeline, Exporters
│   └── transport/       # WebSocket, stdio
│
└── client/              # Клиентская часть
    ├── domain/          # Domain Layer (entities, repos)
    ├── application/     # Application Layer (use cases)
    ├── infrastructure/  # Infrastructure Layer (DI, transport)
    │   ├── services/    # ACPTransportService, BackgroundReceiveLoop
    │   ├── handlers/    # FS, Terminal handlers
    │   └── events/      # EventBus
    ├── presentation/    # ViewModels (MVVM, 14 штук)
    └── tui/             # TUI компоненты (45+ файлов)
        ├── app.py       # ACPClientApp
        ├── components/  # ChatView, Sidebar, FileTree, ...
        ├── navigation/  # NavigationManager
        └── themes/      # Dark/Light themes
```

## См. также

- [Введение](introduction.md) — общая информация о CodeLab
- [Сценарии использования](use-cases.md) — примеры применения
- [Спецификация ACP](../../protocols/Agent%20Client%20Protocol/protocol/01-Overview.md) — детали протокола
