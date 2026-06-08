## Tasks

### 1. Infrastructure — контракты сообщений

> **Важно:** `AgentResponse` уже существует в `codelab/server/agent/base.py` и используется текущей архитектурой. Для шины событий создаём **новые** контракты в пакете `contracts/`:
> - `AgentResponse` — DomainEvent для EventBus (не путать с `base.py:AgentResponse`)
> - `AgentResult` — возвращаемое значение `Agent.call()`
> - `TokenUsage` — типизированная структура токенов

- [ ] 1.1 Создать пакет `codelab/src/codelab/server/agent/contracts/` с `__init__.py`
- [ ] 1.2 Определить `DomainEvent` base class (frozen dataclass с `timestamp: float`, `session_id: str`)
- [ ] 1.3 Создать `TokenUsage` frozen dataclass: `input_tokens: int`, `output_tokens: int`, `total_tokens: int`
- [ ] 1.4 Создать `ToolCall` frozen dataclass для контрактов шины: `id: str`, `name: str`, `arguments: dict`
  - Отличается от `LLMToolCall` из `server/llm/models.py` — это контракт шины, не LLM-специфичный
- [ ] 1.5 Создать `AgentRequest` frozen dataclass (DomainEvent): `target_agent: str`, `messages: list[Message]`, `tools: list[ToolDefinition]`, `correlation_id: str`, `session_id: str`
  - Использовать `Message` из `server/llm/models.py` (alias LLMMessage), `ToolDefinition` из `server/tools/base.py`
- [ ] 1.6 Создать `AgentResponse` frozen dataclass (DomainEvent): `request_id: str`, `text: str`, `tool_calls: list[ToolCall]`, `usage: TokenUsage`, `stop_reason: str`, `agent_name: str`
  - Это НЕ `AgentResponse` из `base.py` — это DomainEvent для EventBus
  - `AgentResult` от LLMAdapter оборачивается в `AgentResponse` шиной
- [ ] 1.7 Создать `AgentResult` frozen dataclass: `text: str`, `tool_calls: list[ToolCall]`, `usage: TokenUsage`, `stop_reason: str`, `agent_name: str`, `error: str | None = None`
  - Возвращаемое значение `Agent.call()` — LLMAdapter возвращает это, EventBus оборачивает в `AgentResponse`
- [ ] 1.8 Создать `ContextBroadcast` frozen dataclass (DomainEvent): `context: list[Message]`, `available_agents: list[str]`, `step: int`, `correlation_id: str`, `session_id: str`
- [ ] 1.9 Создать `ChoreographyAnswer` frozen dataclass (DomainEvent): `agent_name: str`, `action_taken: bool`, `reasoning: str`, `output: str | None`, `status_signal: Literal["continue", "completed"]`, `usage: TokenUsage`
- [ ] 1.10 Создать `AgentRegistered` frozen dataclass (DomainEvent): `agent_name: str`, `capabilities: dict`, `mode: str`
- [ ] 1.11 Создать `AgentUnregistered` frozen dataclass (DomainEvent): `agent_name: str`
- [ ] 1.12 Создать `AgentListChanged` frozen dataclass (DomainEvent): `added: list[str]`, `removed: list[str]`
- [ ] 1.13 Создать `AgentBusError` base exception class
- [ ] 1.14 Создать `AgentNotFoundError(AgentBusError)` exception
- [ ] 1.15 Создать `AgentDispatchError(AgentBusError)` exception
- [ ] 1.16 Написать тесты для всех контрактов (dataclass fields, frozen, inheritance, DomainEvent)

### 2. AbstractEventBus Interface

- [ ] 2.1 Создать `AbstractEventBus` ABC с методами: subscribe, unsubscribe, publish, clear
- [ ] 2.2 Создать `Subscription` dataclass с полями: event_type, handler, is_active, cancel()
- [ ] 2.3 Создать `Handler` Protocol
- [ ] 2.4 Написать тесты для Subscription (cancel, is_active)

### 3. AgentRoutingInterface Protocol

- [ ] 3.1 Создать `AgentRoutingInterface` Protocol с методами: register_agent, unregister_agent, send_request, broadcast
- [ ] 3.2 Создать `RequestHandler` Protocol: `async __call__(request: AgentRequest, parent_span: SpanContext | None) -> AgentResponse`

### 4. AgentEventBus Implementation

- [ ] 4.1 Создать `AgentEventBus` класс, реализующий AbstractEventBus + AgentRoutingInterface
- [ ] 4.2 Реализовать `subscribe()` — добавить handler в dict[type, list]
- [ ] 4.3 Реализовать `unsubscribe()` — пометить subscription.is_active = False
- [ ] 4.4 Реализовать `publish()` — asyncio.gather(return_exceptions=True) для параллельного вызова
- [ ] 4.5 Реализовать `clear()` — очистить subscribers и agents
- [ ] 4.6 Реализовать `register_agent()` — добавить в dict[str, RequestHandler]
- [ ] 4.7 Реализовать `unregister_agent()` — удалить из dict
- [ ] 4.8 Реализовать `send_request()` — lookup agent, dispatch с retry, вернуть `AgentResponse`
- [ ] 4.9 Реализовать `broadcast()` — параллельный dispatch ко всем агентам, вернуть `list[ChoreographyAnswer]`
- [ ] 4.10 Добавить RetryConfig: max_attempts=3, exponential backoff
- [ ] 4.11 Написать unit тесты: subscribe/unsubscribe lifecycle
- [ ] 4.12 Написать unit тесты: publish с несколькими подписчиками
- [ ] 4.13 Написать unit тесты: publish с ошибкой одного подписчика (не прерывает остальных)
- [ ] 4.14 Написать integration тесты: register_agent → send_request → AgentResponse
- [ ] 4.15 Написать integration тесты: broadcast → list[ChoreographyAnswer]
- [ ] 4.16 Написать error тесты: AgentNotFoundError, AgentDispatchError
- [ ] 4.17 Написать retry тесты: handler fails twice, succeeds on 3rd attempt
- [ ] 4.18 Написать concurrency тесты: parallel publish, parallel send_request

### 5. Exports

- [ ] 5.1 Обновить `codelab/src/codelab/server/agent/__init__.py` с экспортами новых классов
- [ ] 5.2 Проверить импорты через `make check`
