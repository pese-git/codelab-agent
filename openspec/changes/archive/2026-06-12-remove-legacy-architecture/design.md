# Design: Remove Legacy Architecture

## Текущая архитектура (с legacy)

```mermaid
graph TD
    A[ACPProtocol] -->|agent_orchestrator| B[AgentOrchestrator]
    A -->|prompt_orchestrator| C[PromptOrchestrator]
    C -->|agent_orchestrator in meta| D[LLMLoopStage]
    D -->|strategy_dispatcher| E[StrategyDispatcher]
    D -->|fallback| F[LegacyCallStrategy]
    F -->|адаптирует| B
    B -->|использует| G[NaiveAgent]
    B -->|model_resolver| H[ModelResolver]
    B -->|cancel_prompt| G
    
    E -->|single| I[SingleStrategy]
    I -->|event_bus| J[AgentEventBus]
    J -->|send_request| K[LLMAdapter]
    
    style F fill:#ffcccc
    style B fill:#ffcccc
    style G fill:#ffcccc
```

## Новая архитектура (без legacy)

```mermaid
graph TD
    A[ACPProtocol] -->|model_resolver| H[ModelResolver]
    A -->|prompt_orchestrator| C[PromptOrchestrator]
    C --> D[LLMLoopStage]
    D -->|strategy_dispatcher| E[StrategyDispatcher]
    D -->|strategy_dispatcher| I[SingleStrategy]
    
    E -->|single| I
    I -->|event_bus| J[AgentEventBus]
    J -->|send_request| K[LLMAdapter]
    K -->|cancel_prompt| K
    
    H -->|resolve| L[LLMProviderRegistry]
    
    style A fill:#ccffcc
    style C fill:#ccffcc
    style D fill:#ccffcc
    style E fill:#ccffcc
    style I fill:#ccffcc
    style J fill:#ccffcc
    style K fill:#ccffcc
    style H fill:#ccffcc
    style L fill:#ccffcc
```

## Компоненты

### 1. ModelResolver (standalone)

**Текущее состояние:** `AgentOrchestrator.model_resolver` — привязан к оркестратору.

**Новое состояние:** Отдельный компонент DI, создаётся в `RegistryProvider`.

```python
# di.py — новый провайдер
class ModelResolverProvider(Provider):
    @provide(scope=Scope.APP)
    def get_model_resolver(
        self,
        registry: LLMProviderRegistry,
        config: AppConfig,
    ) -> ModelResolver:
        return ModelResolver(
            registry=registry,
            default_provider=config.llm.provider,
            provider_configs=config.llm.providers,
        )
```

**Использование:**
- `core.py:294` — `_get_default_model()` через `model_resolver`
- `core.py:1291` — `_handle_set_config_option()` для инвалидации кэша

### 2. LLMAdapter.cancel_prompt()

**Текущее состояние:** `NaiveAgent._active_tasks` + `NaiveAgent.cancel_prompt()`.

**Новое состояние:** `LLMAdapter` уже имеет `_active_tasks` и `cancel_all()`. Нужно добавить `cancel_prompt(session_id)`.

```python
# llm_adapter.py — новый метод
async def cancel_prompt(self, session_id: str) -> None:
    """Отменить активный LLM запрос для сессии."""
    for task_id, task in list(self._active_tasks.items()):
        if not task.done():
            task.cancel()
```

**Использование:**
- `core.py:1246` — `_handle_session_cancel()` через `llm_adapter.cancel_prompt()`

### 3. PromptOrchestrator без agent_orchestrator

**Текущее состояние:** `handle_prompt()` принимает `agent_orchestrator` и кладёт в `context.meta`.

**Новое состояние:** Убрать параметр, `LLMLoopStage` всегда использует `StrategyDispatcher`.

### 4. LLMLoopStage без fallback

**Текущее состояние:** Если нет `strategy_dispatcher`, создаёт `LegacyCallStrategy(agent_orchestrator)`.

**Новое состояние:** `strategy_dispatcher` обязателен. Если нет — `ValueError`.

## Sequence Diagram: Prompt handling (новый путь)

```mermaid
sequenceDiagram
    participant Client as Client
    participant ACP as ACPProtocol
    participant PO as PromptOrchestrator
    participant Pipeline as PromptPipeline
    participant LLM as LLMLoopStage
    participant SD as StrategyDispatcher
    participant SS as SingleStrategy
    participant EB as AgentEventBus
    participant LA as LLMAdapter
    
    Client->>ACP: session/prompt
    ACP->>PO: handle_prompt()
    PO->>Pipeline: run(context)
    Pipeline->>LLM: process(context)
    LLM->>SD: select_strategy()
    SD-->>LLM: "single"
    LLM->>SD: set_current_strategy("single")
    LLM->>SD: get_current_strategy()
    SD-->>LLM: SingleStrategy
    LLM->>SS: execute(session, prompt)
    SS->>EB: send_request(AgentRequest)
    EB->>LA: handle_request(request)
    LA->>LA: build_context(ExecutionEngine)
    LA->>LA: chat.completions.create()
    LA-->>EB: AgentResult
    EB-->>SS: AgentResponse
    SS-->>LLM: AgentResponse
    LLM-->>Pipeline: PromptContext
    Pipeline-->>PO: PromptContext
    PO-->>ACP: ProtocolOutcome
    ACP-->>Client: session/update notifications
```

## Migration Guide

### Для разработчиков

1. **ModelResolver** — получать из DI, не из `AgentOrchestrator`
2. **cancel_prompt** — вызывать `llm_adapter.cancel_prompt(session_id)`
3. **LLMLoopStage** — всегда передавать `strategy_dispatcher`

### Для пользователей

Никаких изменений не требуется. API ACP протокола остаётся совместимым.
