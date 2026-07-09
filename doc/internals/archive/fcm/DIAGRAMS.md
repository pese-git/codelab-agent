# Federated Context Manager — Диаграммы

> **ARCHIVED.** Этот документ архивирован. Каноническая документация — в [`doc/internals/context-manager/`](../../context-manager/). См. также [ADR-002](../adr/ADR-002-context-manager-consolidation.md).


> **Версия:** 2.3
> **Дата:** 25 июня 2026
>
> Все диаграммы соответствуют слоистой архитектуре (Слой 1/2/3),
> единому пути формирования payload и кэшу на базе `FileContentCache`
> (`ACPCache`/`Shared Memory Bridge` из ранних версий удалены).

---

## 1. Общая архитектура системы

```mermaid
graph TB
    subgraph User["Пользователь"]
        Dev["Разработчик"]
    end

    subgraph Client["Client (TUI)"]
        TUI["Textual UI"]
        Transport["ACP Transport"]
        RPCHandler["RPC Handler<br/>(fs/*, terminal/*)"]
    end

    subgraph Server["Server"]
        subgraph Protocol["Protocol Layer"]
            ACP["ACPProtocol"]
            Pipeline["PromptPipeline"]
            AgentLoop["AgentLoop"]
        end

        subgraph Agent["Agent Layer"]
            Dispatcher["StrategyDispatcher"]

            subgraph Strategies["Стратегии"]
                Single["SingleStrategy"]
                Orch["OrchestratedStrategy"]
                Chor["ChoreographyStrategy"]
                Hier["HierarchicalStrategy"]
            end

            Engine["ExecutionEngine<br/>build_context()"]
        end

        subgraph FCM["Federated Context Manager (Слой 3)"]
            Manager["FederatedContextManager"]

            subgraph Scopes["Скоупы"]
                S1["Scope: plan_agent"]
                S2["Scope: search_agent"]
                S3["Scope: coder_agent"]
            end

            subgraph L2["Слой 2"]
                Compactor["ContextCompactor<br/>(Prune+Skeletonize+Summarize)"]
            end

            subgraph L1["Слой 1"]
                Skeletonizer["CodeSkeletonizer"]
                TokenCounter["TokenCounter"]
                FileCache["FileContentCache"]
            end
        end

        subgraph Decorators["Tool Executor Decorators"]
            FCDec["FileCacheDecorator"]
        end

        subgraph EventBus["AgentEventBus"]
            Bus["In-Memory Bus"]
            Agents["LLMAdapter (coder)<br/>LLMAdapter (tester)<br/>LLMAdapter (orchestrator)"]
        end

        subgraph Observability["Observability"]
            Tracer["Tracer"]
            Metrics["MetricsTracker"]
            Timeline["EventTimeline"]
        end
    end

    Dev --> TUI
    TUI --> Transport
    Transport -->|"ACP Protocol"| ACP
    ACP --> Pipeline
    Pipeline --> AgentLoop
    AgentLoop --> Dispatcher
    Dispatcher --> Strategies
    Strategies --> Engine
    Engine -->|"все стратегии"| Manager

    Manager --> Scopes
    Manager -->|"delegate"| Compactor
    Manager --> Skeletonizer
    Manager --> TokenCounter
    Manager --> FileCache
    Compactor --> Skeletonizer
    Compactor --> TokenCounter

    RPCHandler -->|"fs/read результат"| FCDec
    FCDec --> FileCache
    FCDec -->|"add_to_scope()"| Scopes

    Strategies --> Bus
    Bus --> Agents

    Manager -.-> Tracer
    Manager -.-> Metrics
    Manager -.-> Timeline

    style FCM fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    style EventBus fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    style Observability fill:#fce4ec,stroke:#c2185b,stroke-width:2px
    style Decorators fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
```

---

## 2. Поток данных при мультиагентном запросе

```mermaid
sequenceDiagram
    autonumber
    actor User as Разработчик
    participant Client as ACP Client
    participant Server as Server
    participant FCM as FederatedContextManager
    participant Dec as FileCacheDecorator
    participant Cache as FileContentCache
    participant Search as Search Agent
    participant Coder as Coder Agent
    participant LLM as LLM API

    User->>Client: "Найди баг в db.py и исправь"
    Client->>Server: session/prompt

    Server->>FCM: create_scope("orchestrator")
    Server->>FCM: add_to_scope("orchestrator", "prompt", ...)

    Server->>Search: Делегирование поиска
    Search->>Dec: fs/read("src/db.py")
    Dec->>Cache: set("src/db.py", content)
    Dec->>FCM: add_to_scope("search_agent", "src/db.py", "file_content", content)
    Search->>FCM: add_to_scope("search_agent", "bug_report", "agent_report", report, priority=9)
    Search-->>Server: Задача выполнена

    Server->>FCM: share_item("search_agent", "coder_agent", "src/db.py")
    Server->>FCM: share_item("search_agent", "coder_agent", "bug_report")

    Server->>Coder: Делегирование исправления
    Coder->>FCM: optimize_and_build_payload("coder_agent")

    Note over FCM: 1. Критические vs динамические<br/>2. Ранжирование по приоритету<br/>3. AST-скелетирование при нехватке бюджета<br/>4. Формирование payload

    FCM-->>Coder: Optimized payload
    Coder->>LLM: Prompt + контекст
    LLM-->>Coder: Готовый патч
    Coder-->>Server: Результат
    Server-->>Client: session/update
    Client-->>User: Отображение результата
```

---

## 3. Структура скоупов в памяти

```mermaid
graph LR
    subgraph FCM["Federated Context Manager"]
        subgraph Cache["FileContentCache (per session)"]
            C1["src/db.py → content"]
            C2["src/utils.py → content"]
        end

        subgraph PlanScope["Scope: plan_agent"]
            PlanRules["system_rules<br/>priority: 10<br/>────────────<br/>Ты — планировщик..."]
            PlanBudget["max_tokens: 8000"]
        end

        subgraph SearchScope["Scope: search_agent"]
            SearchRules["system_rules<br/>priority: 10"]
            SearchBudget["max_tokens: 4000"]
            SearchFile["file_content<br/>priority: 5<br/>src/db.py"]
            SearchReport["agent_report<br/>priority: 9<br/>bug_report"]
        end

        subgraph CoderScope["Scope: coder_agent"]
            CoderRules["system_rules<br/>priority: 10"]
            CoderBudget["max_tokens: 16000"]
            CoderFile["file_content<br/>priority: 6<br/>src/db.py (shared)"]
            CoderReport["agent_report<br/>priority: 9<br/>bug_report (shared)"]
        end
    end

    Cache -->|"FileCacheDecorator / Bridge"| SearchScope
    SearchScope -->|"share_item()"| CoderScope

    style FCM fill:#f5f5f5,stroke:#333,stroke-width:2px
    style Cache fill:#e3f2fd,stroke:#1565c0
    style PlanScope fill:#fff3e0,stroke:#e65100
    style SearchScope fill:#e8f5e9,stroke:#2e7d32
    style CoderScope fill:#fce4ec,stroke:#c2185b
```

---

## 4. AST-скелетирование

```mermaid
graph TB
    subgraph Input["Исходный код (200 токенов)"]
        Code["class DatabaseConnector:<br/>    @connection_watcher<br/>    def connect(self):<br/>        print('Connecting...')<br/>        # 50 строк логики<br/>        ...<br/><br/>    def execute_query(self, query: str) -> dict:<br/>        if not query:<br/>            raise ValueError(...)<br/>        # 30 строк логики<br/>        ..."]
    end

    subgraph Skeletonizer["PythonASTSkeletonizer (CodeSkeletonizer)"]
        Parse["ast.parse()"]
        Visit["_ASTVisitor.visit()"]
        Extract["Извлечение:<br/>- ClassDef<br/>- FunctionDef / AsyncFunctionDef<br/>- декораторы<br/>- аргументы<br/>- return type"]
    end

    subgraph Output["Скелет (30 токенов)"]
        Skeleton["class DatabaseConnector:<br/>    @connection_watcher<br/>    def connect(self): ...<br/><br/>    def execute_query(self, query: str) -> dict: ..."]
    end

    Code --> Parse
    Parse --> Visit
    Visit --> Extract
    Extract --> Skeleton

    style Input fill:#ffebee,stroke:#c62828,stroke-width:2px
    style Skeletonizer fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    style Output fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
```

> Экономия ~85% токенов. Edge case (EDGE_CASES §3): если скелет не меньше
> оригинала (minified-код), используется оригинал.

---

## 5. Приоритизация и вытеснение

```mermaid
graph TD
    subgraph Scoring["Priority Scoring Algorithm"]
        Items["Все элементы скоупа"]

        Split{"priority >= 10?"}

        SystemItems["system_items<br/>(не вытесняются)"]
        DynamicItems["dynamic_items<br/>(кандидаты на вытеснение)"]

        CritCheck{"system_tokens<br/>> max_tokens?"}
        Raise["raise ValueError<br/>(critical items exceed budget)"]

        Sort["Сортировка:<br/>1. priority DESC<br/>2. last_accessed DESC"]

        Budget["available_budget =<br/>max_tokens - system_tokens"]

        Loop{"Для каждого элемента:"}

        Fit{"token_count <= budget?"}
        Include["Включить в payload"]

        IsFile{"type == file_content?"}
        Skeletonize["AST-скелетирование"]
        SkeletonFit{"skeleton < original<br/>и помещается?"}
        IncludeSkeleton["Включить скелет"]

        Evict["Вытеснить<br/>(+ ContextOverflow)"]

        UpdateBudget["budget -= token_count"]
    end

    Items --> Split
    Split -->|Yes| SystemItems
    Split -->|No| DynamicItems
    SystemItems --> CritCheck
    CritCheck -->|Yes| Raise
    CritCheck -->|No| Budget
    DynamicItems --> Sort
    Sort --> Loop
    Loop --> Fit
    Fit -->|Yes| Include
    Include --> UpdateBudget
    UpdateBudget --> Loop
    Fit -->|No| IsFile
    IsFile -->|Yes| Skeletonize
    Skeletonize --> SkeletonFit
    SkeletonFit -->|Yes| IncludeSkeleton
    IncludeSkeleton --> UpdateBudget
    SkeletonFit -->|No| Evict
    IsFile -->|No| Evict

    style Scoring fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
```

---

## 6. Интеграция с ExecutionEngine

```mermaid
graph TB
    subgraph Before["До FCM (legacy)"]
        Engine1["ExecutionEngine"]
        Builder1["HistoryBuilder"]
        Compactor1["ContextCompactor<br/>(Prune + Summarize)"]
        Filter1["ToolFilter"]

        Engine1 --> Builder1
        Engine1 --> Compactor1
        Engine1 --> Filter1
    end

    subgraph After["После FCM (единый путь)"]
        Engine2["ExecutionEngine<br/>build_context()"]
        Filter2["ToolFilter"]

        subgraph FCM2["FederatedContextManager (Слой 3)"]
            OBP["optimize_and_build_payload()"]
            HS["hydrate_from_history()"]
            CC2["ContextCompactor<br/>(Слой 2, внутри FCM)"]
        end

        Engine2 --> Filter2
        Engine2 -->|"все стратегии"| FCM2
        OBP -->|"delegate"| CC2
    end

    Before --> After

    style Before fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style After fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    style FCM2 fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
```

> Ключевое отличие: `ContextCompactor` — это **Слой 2 внутри FCM**, а не
> сосед `ExecutionEngine`. Движок общается только с FCM (FCM-путь) либо с
> legacy-компактором (legacy-путь) — пути взаимоисключающие.

---

## 7. Жизненный цикл элемента контекста

```mermaid
stateDiagram-v2
    [*] --> Created: add_to_scope()
    Created --> Active: Добавлен в скоуп
    Active --> Active: touch() при доступе
    Active --> Shared: share_item()
    Shared --> Active: Получен в target scope
    Active --> Skeletonized: Превышен бюджет (file_content)
    Skeletonized --> Active: Скелет включён
    Active --> Evicted: Вытеснен (ContextOverflow)
    Evicted --> [*]

    note right of Created
        Инициализация:
        - id, type, content
        - priority, owner_scope
        - token_count
        - усечение если > max_tokens
    end note

    note right of Shared
        Копирование:
        - Новый owner_scope
        - Опциональный new_priority
        - Без RPC запросов
    end note

    note right of Skeletonized
        AST-сжатие:
        - Сохранение сигнатур
        - Удаление тел функций
        - Только если скелет < оригинала
    end note
```

---

## 8. Компоненты FCM

```mermaid
classDiagram
    class ContextManager {
        <<ABC>>
        +create_scope(name, max_tokens) AgentContextScope
        +add_to_scope(scope, id, type, content, priority)
        +share_item(source, target, id, priority)
        +hydrate_from_history(scope, history, system_prompt)
        +optimize_and_build_payload(scope) list~LLMMessage~
    }

    class FederatedContextManager {
        +dict~str, AgentContextScope~ scopes
        +TokenCounter token_counter
        +CodeSkeletonizer skeletonizer
        +ContextCompactor compactor
        +FileContentCache file_cache
        +AgentEventBus event_bus
        +Tracer tracer
    }

    class AgentContextScope {
        +str scope_name
        +int max_tokens
        +dict~str, ContextItem~ registry
        +add(item: ContextItem)
        +get(item_id: str) ContextItem
        +remove(item_id: str)
        +get_total_tokens() int
        +get_items_by_priority() list~ContextItem~
    }

    class ContextItem {
        +str id
        +ContextType type
        +str content
        +int priority
        +str owner_scope
        +float last_accessed
        +int token_count
        +touch() ContextItem
    }

    class TokenCounter {
        <<ABC>>
        +count(content: str) int
    }

    class CodeSkeletonizer {
        <<ABC>>
        +skeletonize(code, file_id, language) str
    }

    class ContextCompactor {
        <<ABC>>
        +compact_if_needed(history) tuple
    }

    class FileContentCache {
        <<ABC>>
        +get(path) str
        +set(path, content)
        +invalidate(path)
        +clear()
    }

    ContextManager <|-- FederatedContextManager
    FederatedContextManager "1" *-- "*" AgentContextScope
    AgentContextScope "1" *-- "*" ContextItem
    FederatedContextManager --> TokenCounter
    FederatedContextManager --> CodeSkeletonizer
    FederatedContextManager --> ContextCompactor
    FederatedContextManager --> FileContentCache
```

---

## 9. События EventBus

```mermaid
graph LR
    subgraph Events["Domain Events (модульные dataclass)"]
        ItemAdded["ContextItemAdded<br/>────────────<br/>scope_name<br/>item_id<br/>item_type<br/>token_count"]

        Shared["ContextShared<br/>────────────<br/>source_scope<br/>target_scope<br/>item_id<br/>new_priority"]

        Overflow["ContextOverflow<br/>────────────<br/>scope_name<br/>max_tokens<br/>current_tokens<br/>evicted_items"]
    end

    subgraph Publishers["Публикует FederatedContextManager"]
        AddOp["add_to_scope()"]
        ShareOp["share_item()"]
        OptOp["optimize_and_build_payload()"]
    end

    subgraph Subscribers["Подписаны"]
        Metrics["MetricsTracker"]
        Timeline["EventTimeline"]
        Tracer["Tracer"]
    end

    AddOp -->|"publish()"| ItemAdded
    ShareOp -->|"publish()"| Shared
    OptOp -->|"publish() при вытеснении"| Overflow

    ItemAdded --> Metrics
    ItemAdded --> Timeline
    Shared --> Metrics
    Shared --> Timeline
    Shared --> Tracer
    Overflow --> Metrics
    Overflow --> Timeline

    style Events fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
```

---

## 10. Путь внедрения (Gantt)

> Соответствует Phase 0–5 из `MIGRATION_PLAN.md` (источник истины по roadmap).

```mermaid
gantt
    title План внедрения FCM (Phase 0-5)
    dateFormat  YYYY-MM-DD
    section Phase 0: Preparation
    Feature flags + ExecutionEngine (compactor+context_manager)  :a1, 2026-06-25, 5d
    agent_scope в build_context + backward-compat тесты          :a2, after a1, 2d

    section Phase 1: Слой 1 (Утилиты)
    TokenCounter + CodeSkeletonizer + FileContentCache           :b1, after a2, 5d
    SessionFileCacheRegistry + FileCacheDecorator                :b2, after b1, 3d

    section Phase 2: Слой 2 (Сжатие)
    DefaultContextCompactor (Prune→Skeletonize→Summarize)        :c1, after b2, 4d

    section Phase 3: Слой 3 (Оркестрация)
    ContextItem + AgentContextScope + FederatedContextManager    :d1, after c1, 5d
    hydrate_from_history + интеграция _build_via_fcm             :d2, after d1, 3d

    section Phase 4: Feature Flag Rollout
    Canary 5% → 25% → 50% → 100%                                 :e1, after d2, 10d

    section Phase 5: Cleanup
    Удаление legacy ContextCompactor + флагов                    :f1, after e1, 5d
```
