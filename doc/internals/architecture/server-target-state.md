# Серверная архитектура — целевое состояние (post write-фаза)

> **Статус:** целевое (to-be). Отражает состояние серверной части **после** завершения
> доменной миграции сессии (ADR-006, write-фаза) и разблокированных ей Workstream ADR-005
> **C** (прод turn-loop через `AgentRunner`) и **B** (доменная эмиссия `UpdateSink`).
>
> **Основание:** ADR-003 (вариант B), ADR-005 (ACP-независимое ядро, порты), ADR-006 (write-фаза),
> `openspec/changes/session-domain-write-phase/{proposal,design}.md`, карта D4.1
> (`d4.1-mutation-map.md`), раздел «Архитектура» в `CLAUDE.md`.
>
> Помечено ✳ — вводится write-фазой (ADR-006 D4-a: `TurnState`/`SessionRuntime`).
> Помечено ⓒ/ⓑ — достигается после Workstream C/B соответственно.
>
> Этот документ — целевой референс; питает задачу **D.3** (синхронизация канонического
> `ARCHITECTURE.md` и его Mermaid после реализации).

## 1. Компоненты по слоям и зависимости

```mermaid
flowchart TB
    classDef driving fill:#eef7ff,stroke:#3b82f6,color:#0b3a66;
    classDef adapter fill:#fff4e6,stroke:#d97706,color:#5c3b00;
    classDef core fill:#eafaf0,stroke:#16a34a,color:#08361c;
    classDef domain fill:#e8ecff,stroke:#4f46e5,color:#1e1b4b;
    classDef infra fill:#f3f4f6,stroke:#6b7280,color:#111827;
    classDef port fill:#fdf2f8,stroke:#db2777,color:#500724,stroke-dasharray:4 3;

    %% ============ DRIVING ADAPTERS ============
    subgraph L0["Driving-адаптеры (вход)"]
        direction LR
        TR["Transport<br/>stdio_runner · websocket"]
        ACPD["ACP JSON-RPC driver<br/>(session/*, fs/*, terminal/*)"]
        FAKE["Fake driver<br/>(тест-харнесс, не-ACP)"]
    end

    %% ============ PROTOCOL (ACP-адаптер) ============
    subgraph L1["protocol — ACP-адаптер (application)"]
        direction TB
        CMD["commands<br/>session_new · session_load · session_prompt<br/>session_cancel · permission_response"]
        ORCH["prompt_orchestrator"]
        subgraph PIPE["pipeline (PromptContext: session=domain.Session ⓒ)"]
            direction LR
            ST1["validation"] --> ST2["slash_commands"] --> ST3["turn_lifecycle"] --> ST4["directives"] --> ST5["agent_loop<br/>loop · llm_caller · tool_processor · updates"] --> ST6["llm_loop"]
        end
        subgraph HND["handlers (доменные операции агрегата)"]
            direction LR
            H1["turn_lifecycle_manager"]
            H2["state_manager"]
            H3["permission_manager"]
            H4["tool_call_handler"]
            H5["client_rpc_handler"]
            H6["replay_manager"]
            H7["mcp_session_manager"]
        end
        subgraph BND["Граница wire/storage"]
            MAP["SessionMapper<br/>(domain.Session ↔ SessionState-DTO)"]
            WDTO["SessionState<br/>(тонкий wire-DTO: replay/init)"]
        end
    end

    %% ============ DRIVEN PORTS (agent.contracts) ============
    subgraph PORTS["agent.contracts — driven-порты (ABC)"]
        direction LR
        P1["SessionView (read)"]:::port
        P2["ContentCodec"]:::port
        P3["ToolGateway"]:::port
        P4["UpdateSink"]:::port
        P5["LLMAdapter"]:::port
    end

    %% ============ AGENT CORE (ACP-независимое ядро) ============
    subgraph L2["agent.core — ACP-независимое ядро (application)"]
        direction TB
        RUN["AgentRunner<br/>(прод turn-loop ⓒ)"]
        ENG["ExecutionEngine"]
        subgraph STR["strategies"]
            direction LR
            S1["single"]
            S2["orchestrated"]
            S3["hierarchical"]
            S4["choreography"]
        end
        HB["history_builder · system_prompt_builder · message_sanitizer"]
        CSF["ChildSessionFactory"]
    end

    %% ============ CONTEXT MANAGER ============
    subgraph L3["agent.context — Context Manager (4 слоя A–D)"]
        direction LR
        CA["A · Сбор<br/>TaskAnalyzer · ContextGatherer<br/>DependencyGraph · TokenBudget · Registry"]
        CB["B · Жизненный цикл<br/>ContextEpoch · Snapshot · Reconciler"]
        CC["C · Хранение<br/>FileContentCache · Skeletonizer<br/>TokenCounter · ThreePhaseCompactor"]
        CD["D · Мультиагент<br/>ChildSessionManager"]
    end

    %% ============ DOMAIN (рабочая модель, ядро) ============
    subgraph L4["domain — рабочая модель (innermost)"]
        direction TB
        AGG["Session (Aggregate Root)"]
        subgraph VOS["Value Objects"]
            direction LR
            V1["SessionConfig"]
            V2["ConversationHistory"]
            V3["ToolCallRegistry"]
            V4["PermissionState"]
            V5["AgentPlan"]
            V6["MultiAgentState"]
            V7["TurnState ✳"]
            V8["SessionRuntime ✳"]
        end
        TCX["ToolContext<br/>(проекция агрегата для executor'ов)"]
        AGG --- VOS
    end

    %% ============ TOOLS ============
    subgraph L5["tools (infrastructure)"]
        direction TB
        TREG["ToolRegistry"]
        TEXE["ToolExecutorProtocol.execute(ToolContext)"]
        subgraph EXE["executors"]
            direction LR
            E1["filesystem"]
            E2["terminal"]
            E3["plan"]
            E4["mcp"]
        end
        DEC["decorators<br/>file_cache · metrics · retry · timeout · tracing"]
    end

    %% ============ LLM ============
    subgraph L6["llm (infrastructure)"]
        direction LR
        LAD["LLMAdapter (single-call, ADR-001)"]
        subgraph PROV["providers"]
            direction LR
            PR1["anthropic"]
            PR2["openai_compatible"]
            PR3["scripted_mock"]
        end
    end

    %% ============ STORAGE ============
    subgraph L7["storage (infrastructure) — на domain.Session"]
        direction LR
        SBASE["SessionStorage (ABC)<br/>save/load(domain.Session)"]
        SJSON["JsonFileStorage<br/>versioned schema v7"]
        SMEM["InMemoryStorage"]
        SCACHE["CachedStorage (Decorator)"]
    end

    %% ============ CLIENT RPC / MCP ============
    subgraph L8["client_rpc · mcp (infrastructure)"]
        direction LR
        CRPC["ClientRPCService<br/>(fs/* · terminal/*)"]
        MCPM["MCP manager · stdio/sse transport"]
    end

    %% ---------- Потоки ----------
    TR --> ACPD
    FAKE -.->|валидирует порты| RUN
    ACPD --> CMD
    CMD -->|load/save| SBASE
    CMD --> ORCH
    ORCH --> PIPE
    ORCH --> HND
    PIPE --> HND
    ORCH --> RUN
    RUN --> ENG --> STR
    ENG --> HB
    RUN --> CSF
    ENG --> L3

    %% Доменные операции агрегата
    HND -->|мутации = доменные операции| AGG
    ORCH -->|строит на входе turn| MAP
    MAP <-->|только сериализация| AGG
    MAP --> WDTO
    CMD -.->|replay/init| WDTO

    %% Порты: ядро зависит ТОЛЬКО от портов и домена
    RUN -.-> P1 & P4 & P5
    ENG -.-> P2 & P3 & P5
    L3 -.-> P3
    RUN --> AGG

    %% Реализации портов в адаптерах/инфраструктуре
    HND -. implements .-> P1
    MAP -. implements .-> P2
    ST5 -. implements .-> P4
    TREG -. implements .-> P3
    LAD -. implements .-> P5

    %% Tools на ToolContext (проекция домена)
    TCX --> AGG
    TEXE --> TCX
    TREG --> TEXE --> EXE
    TEXE --> DEC
    E4 --> MCPM
    E1 & E2 --> CRPC
    DEC -->|file I/O через ToolGateway| CRPC

    %% LLM
    LAD --> PROV

    %% Storage impls
    SBASE --> SJSON & SMEM
    SCACHE --> SBASE
    SJSON <-. сериализация .-> MAP

    class TR,ACPD,FAKE driving;
    class CMD,ORCH,PIPE,ST1,ST2,ST3,ST4,ST5,ST6,HND,H1,H2,H3,H4,H5,H6,H7,BND,MAP,WDTO adapter;
    class L2,RUN,ENG,STR,S1,S2,S3,S4,HB,CSF,L3,CA,CB,CC,CD core;
    class L4,AGG,VOS,V1,V2,V3,V4,V5,V6,V7,V8,TCX domain;
    class L5,TREG,TEXE,EXE,E1,E2,E3,E4,DEC,L6,LAD,PROV,PR1,PR2,PR3,L7,SBASE,SJSON,SMEM,SCACHE,L8,CRPC,MCPM infra;
```

**Легенда рёбер:** сплошное — поток данных/вызовов; `-.->` — зависимость от driven-порта;
`-. implements .->` — реализация порта в адаптере/инфраструктуре.

## 2. Правило зависимостей (import-linter «Server layers», после закрытия ADR-003)

```mermaid
flowchart LR
    classDef dom fill:#e8ecff,stroke:#4f46e5;
    classDef app fill:#eafaf0,stroke:#16a34a;
    classDef inf fill:#f3f4f6,stroke:#6b7280;

    DOM["domain<br/>(Session + VO, ToolContext)"]:::dom
    APP["application<br/>agent.core · agent.context · protocol(handlers/pipeline)"]:::app
    INF["infrastructure<br/>storage · tools · llm · client_rpc · mcp · transport"]:::inf

    INF -->|зависит от| APP -->|зависит от| DOM
    DOM -. НЕ зависит .-x APP
    APP -. НЕ зависит .-x INF
```

**Инвариант достигнут (2026-08-03, ADR-006 фаза D):** `agent.core` → **0 рёбер** к `protocol`;
`ignore_imports` **пуст** (сняты `file_cache_decorator`, `tools.executors.decorators.base` и
`storage.base` → `protocol.state`). Документ сессии живёт не в `protocol`, а в
`storage/document.py` под именем `SessionDocument`: «состояние сессии» — это доменный `Session`,
а на диске лежит документ.

## 3. Ключевые сдвиги относительно as-is

| Аспект | Было (as-is) | Стало (target) |
|---|---|---|
| Рабочая модель turn'а | `protocol.SessionState` (Pydantic, мутируется по стадиям) | `domain.Session` (агрегат, доменные операции) |
| Документ сессии | source-of-truth + сериализация под именем `SessionState` | **`SessionDocument`** в `storage/`, только сериализация |
| Точка конвертации | размазана | единственная — `SessionMapper` |
| `storage` типизирован на | `SessionState` (рантайм-импорт из `protocol`) | `domain.Session` на порту, `SessionDocument` внутри |
| Executor'ы получают | `SessionState` | доменный `ToolContext` (проекция) |
| `agent.core → protocol` | остаточные рёбра в `ignore_imports` | **0 рёбер**, `ignore_imports` пуст |
| turn-loop | внутри protocol-пайплайна | прод-loop через `AgentRunner` (ⓒ) |
| Эмиссия `session/update` | сборка wire в ядре | доменная эмиссия через порт `UpdateSink` (ⓑ) |

## 4. Паттерны (DDD/hexagonal)

- **Aggregate Root** — `domain.Session`: полная рабочая+персистируемая модель (состояние сессии
  + turn-runtime как доменные VO `TurnState`/`SessionRuntime`), доменные инварианты и операции;
  тредится одной ссылкой (`PromptContext.session`).
- **Anti-Corruption / Mapper** — `SessionMapper`: единственная точка `domain ↔ wire/storage`,
  round-trip без потерь; апгрейд версий формата хранения.
- **Repository** — `SessionStorage` над `domain.Session`; `JsonFile`/`InMemory` + **Decorator**
  `CachedStorage`.
- **Ports & Adapters (hexagonal)** — driven-порты `SessionView`/`ContentCodec`/`ToolGateway`/
  `UpdateSink`/`LLMAdapter` (заморожены, ADR-005); driving-адаптеры ACP-driver и fake driver.
- **Adapter** — `ToolContext`: проекция агрегата для executor'ов.
- **Wire-DTO** — `SessionState` (в `protocol`): тонкий маппинг для ACP-подмножества (replay/init);
  `available_commands` — ACP wire-DTO; `mcp_prompt_handlers` — transient (`exclude=True`).
</content>
