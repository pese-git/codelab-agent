# Federated Context Manager — Диаграммы

> **Версия:** 1.0  
> **Дата:** 24 июня 2026

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
            
            Engine["ExecutionEngine"]
            Compactor["ContextCompactor"]
        end
        
        subgraph FCM["Federated Context Manager"]
            Manager["FederatedContextManager"]
            
            subgraph Scopes["Скоупы"]
                S1["Scope: plan_agent"]
                S2["Scope: search_agent"]
                S3["Scope: coder_agent"]
            end
            
            Bridge["Shared Memory Bridge"]
            Skeletonizer["ASTSkeletonizer"]
            Cache["ACP Cache"]
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
    Engine --> Compactor
    Engine --> Manager
    
    Manager --> Scopes
    Manager --> Bridge
    Manager --> Skeletonizer
    Manager --> Cache
    
    Strategies --> Bus
    Bus --> Agents
    
    Manager -.-> Tracer
    Manager -.-> Metrics
    Manager -.-> Timeline
    
    RPCHandler -->|"RPC ответы"| Cache
    
    style FCM fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    style EventBus fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    style Observability fill:#fce4ec,stroke:#c2185b,stroke-width:2px
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
    participant Search as Search Agent
    participant Coder as Coder Agent
    participant LLM as LLM API
    
    User->>Client: "Найди баг в db.py и исправь"
    Client->>Server: session/prompt
    
    Server->>FCM: create_scope("orchestrator")
    Server->>FCM: add_to_scope("orchestrator", "prompt", ...)
    
    Server->>Search: Делегирование поиска
    Search->>FCM: get_from_cache("src/db.py")
    FCM-->>Search: content (из кэша)
    
    Search->>FCM: add_to_scope("search", "src/db.py", content)
    Search->>FCM: add_to_scope("search", "bug_report", report, priority=9)
    Search-->>Server: Задача выполнена
    
    Server->>FCM: share_item("search", "coder", "src/db.py")
    Server->>FCM: share_item("search", "coder", "bug_report")
    
    Server->>Coder: Делегирование исправления
    Coder->>FCM: optimize_and_build_payload("coder")
    
    Note over FCM: 1. Ранжирование по приоритету<br/>2. AST-скелетирование<br/>3. Формирование payload
    
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
        subgraph Global["Глобальный кэш"]
            Cache["ACPCache<br/>────────────<br/>src/db.py → content<br/>src/utils.py → content<br/>terminal_1 → output"]
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
            CoderFile["file_content<br/>priority: 6<br/>src/db.py"]
            CoderReport["agent_report<br/>priority: 9<br/>bug_report"]
        end
    end
    
    Cache -->|"get_from_cache()"| SearchScope
    Cache -->|"get_from_cache()"| CoderScope
    
    SearchScope -->|"share_item()"| CoderScope
    
    style FCM fill:#f5f5f5,stroke:#333,stroke-width:2px
    style Global fill:#e3f2fd,stroke:#1565c0
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
    
    subgraph Skeletonizer["ASTSkeletonizer"]
        Parse["ast.parse()"]
        Visit["NodeVisitor.visit()"]
        Extract["Извлечение:<br/>- ClassDef<br/>- FunctionDef<br/>- декораторы<br/>- аргументы<br/>- return type"]
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
    
    note1["Экономия: 85% токенов"]
```

---

## 5. Приоритизация и вытеснение

```mermaid
graph TD
    subgraph Scoring["Priority Scoring Algorithm"]
        Items["Все элементы скоупа"]
        
        Split{"priority >= 10?"}
        
        SystemItems["system_items<br/>(не вытесняются)"]
        DynamicItems["dynamic_items<br/>(кандидаты на вытеснение)"]
        
        Sort["Сортировка:<br/>1. priority DESC<br/>2. last_accessed DESC"]
        
        Budget["available_budget =<br/>max_tokens - system_tokens"]
        
        Loop{"Для каждого элемента:"}
        
        Fit{"token_count <= budget?"}
        Include["Включить в payload"]
        
        IsFile{"type == file_content?"}
        Skeletonize["AST-скелетирование"]
        SkeletonFit{"skeleton_tokens <= budget?"}
        IncludeSkeleton["Включить скелет"]
        
        Evict["Вытеснить"]
        
        UpdateBudget["budget -= token_count"]
    end
    
    Items --> Split
    Split -->|Yes| SystemItems
    Split -->|No| DynamicItems
    DynamicItems --> Sort
    SystemItems --> Budget
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
    subgraph Before["До FCM"]
        Engine1["ExecutionEngine"]
        Builder1["HistoryBuilder"]
        Compactor1["ContextCompactor<br/>(Prune + Summarize)"]
        Filter1["ToolFilter"]
        
        Engine1 --> Builder1
        Engine1 --> Compactor1
        Engine1 --> Filter1
    end
    
    subgraph After["После FCM"]
        Engine2["ExecutionEngine"]
        Builder2["HistoryBuilder"]
        Compactor2["ContextCompactor<br/>(Prune + Skeletonize + Summarize)"]
        Filter2["ToolFilter"]
        FCM2["FederatedContextManager"]
        
        Engine2 --> Builder2
        Engine2 --> Compactor2
        Engine2 --> Filter2
        Engine2 --> FCM2
        
        Compactor2 -.->|"Использует<br/>ASTSkeletonizer"| FCM2
    end
    
    Before --> After
    
    style Before fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style After fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
```

---

## 7. Жизненный цикл элемента контекста

```mermaid
stateDiagram-v2
    [*] --> Created: add_to_scope()
    Created --> Active: Добавлен в скоуп
    Active --> Active: touch() при доступе
    Active --> Shared: share_item()
    Shared --> Active: Получен в target scope
    Active --> Skeletonized: Превышен бюджет
    Skeletonized --> Active: Скелет включён
    Active --> Evicted: Вытеснен (LRU)
    Evicted --> [*]
    
    note right of Created
        Инициализация:
        - id, type, content
        - priority, owner_scope
        - token_count
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
        - Экономия ~85% токенов
    end note
```

---

## 8. Компоненты FCM

```mermaid
classDiagram
    class FederatedContextManager {
        +dict~str, AgentContextScope~ scopes
        +AgentEventBus event_bus
        +Tracer tracer
        +TokenCounter token_counter
        +create_scope(name, max_tokens) AgentContextScope
        +add_to_scope(scope, id, type, content, priority)
        +share_item(source, target, id, priority)
        +optimize_and_build_payload(scope) list~LLMMessage~
    }
    
    class AgentContextScope {
        +str scope_name
        +int max_tokens
        +dict~str, ContextItem~ registry
        +add(item: ContextItem)
        +get(item_id: str) ContextItem
        +remove(item_id: str)
        +get_total_tokens() int
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
    
    class ASTSkeletonizer {
        +int indent
        +list~str~ result
        +visit_ClassDef(node)
        +visit_FunctionDef(node)
        +visit_AsyncFunctionDef(node)
    }
    
    class TokenCounter {
        -Encoding _encoding
        -bool _has_tiktoken
        +count(content: str) int
    }
    
    class ACPCache {
        -dict~str, str~ _cache
        +get(key: str) str
        +set(key: str, content: str)
        +invalidate(key: str)
    }
    
    FederatedContextManager "1" *-- "*" AgentContextScope
    AgentContextScope "1" *-- "*" ContextItem
    FederatedContextManager --> ASTSkeletonizer
    FederatedContextManager --> TokenCounter
    FederatedContextManager --> ACPCache
```

---

## 9. События EventBus

```mermaid
graph LR
    subgraph Events["Domain Events"]
        ItemAdded["ContextItemAdded<br/>────────────<br/>scope_name<br/>item_id<br/>item_type<br/>token_count"]
        
        Shared["ContextShared<br/>────────────<br/>source_scope<br/>target_scope<br/>item_id<br/>new_priority"]
        
        Overflow["ContextOverflow<br/>────────────<br/>scope_name<br/>max_tokens<br/>current_tokens<br/>evicted_items"]
    end
    
    subgraph Publishers["Публикуют"]
        Manager["FederatedContextManager"]
    end
    
    subgraph Subscribers["Подписаны"]
        Metrics["MetricsTracker"]
        Timeline["EventTimeline"]
        Tracer["Tracer"]
    end
    
    Manager -->|"publish()"| ItemAdded
    Manager -->|"publish()"| Shared
    Manager -->|"publish()"| Overflow
    
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

```mermaid
gantt
    title План внедрения FCM
    dateFormat  YYYY-MM-DD
    section Фаза 1: ASTSkeletonizer
    Реализация ASTSkeletonizer     :a1, 2026-06-25, 3d
    Интеграция в ContextCompactor  :a2, after a1, 2d
    Тесты                          :a3, after a2, 2d
    
    section Фаза 2: TokenCounter
    Реализация TokenCounter        :b1, after a3, 2d
    Замена _estimate_tokens        :b2, after b1, 1d
    Тесты                          :b3, after b2, 1d
    
    section Фаза 3: ContextItem + Scope
    Реализация ContextItem         :c1, after b3, 2d
    Реализация AgentContextScope   :c2, after c1, 2d
    Тесты                          :c3, after c2, 2d
    
    section Фаза 4: FederatedContextManager
    Реализация FCM                 :d1, after c3, 3d
    Интеграция с EventBus          :d2, after d1, 2d
    Тесты                          :d3, after d2, 2d
    
    section Фаза 5: Интеграция
    Интеграция в ExecutionEngine   :e1, after d3, 2d
    Интеграция в стратегии         :e2, after e1, 3d
    E2E тесты                      :e3, after e2, 3d
```
