## Tasks

### 1. Infrastructure

- [ ] 1.1 Создать пакет `codelab/src/codelab/server/agent/contracts/` с `__init__.py`
- [ ] 1.2 Определить `DomainEvent` base class (если ещё не существует)
- [ ] 1.3 Создать `AgentRequest` frozen dataclass с полями: target_agent, messages, tools, correlation_id, session_id
- [ ] 1.4 Создать `AgentResponse` frozen dataclass с полями: request_id, text, tool_calls, usage, stop_reason, agent_name
- [ ] 1.5 Создать `AgentResult` frozen dataclass с полями: text, tool_calls, usage, stop_reason, agent_name, error
- [ ] 1.6 Создать `ContextBroadcast` frozen dataclass с полями: context, available_agents, step, correlation_id, session_id
- [ ] 1.7 Создать `ChoreographyAnswer` frozen dataclass с полями: agent_name, action_taken, reasoning, output, status_signal, usage
- [ ] 1.8 Создать `AgentRegistered` frozen dataclass: agent_name, capabilities
- [ ] 1.9 Создать `AgentUnregistered` frozen dataclass: agent_name
- [ ] 1.10 Создать `AgentListChanged` frozen dataclass: added, removed
- [ ] 1.11 Создать `AgentBusError` base exception class
- [ ] 1.12 Создать `AgentNotFoundError(AgentBusError)` exception
- [ ] 1.13 Создать `AgentDispatchError(AgentBusError)` exception
- [ ] 1.14 Написать тесты для всех контрактов (dataclass fields, frozen, inheritance)

### 2. AbstractEventBus Interface

- [ ] 2.1 Создать `AbstractEventBus` ABC с методами: subscribe, unsubscribe, publish, clear
- [ ] 2.2 Создать `Subscription` dataclass с полями: event_type, handler, is_active, cancel()
- [ ] 2.3 Создать `Handler` Protocol
- [ ] 2.4 Написать тесты для Subscription (cancel, is_active)

### 3. AgentRoutingInterface Protocol

- [ ] 3.1 Создать `AgentRoutingInterface` Protocol с методами: register_agent, unregister_agent, send_request, broadcast
- [ ] 3.2 Создать `RequestHandler` Protocol

### 4. AgentEventBus Implementation

- [ ] 4.1 Создать `AgentEventBus` класс, реализующий AbstractEventBus + AgentRoutingInterface
- [ ] 4.2 Реализовать `subscribe()` — добавить handler в dict[type, list]
- [ ] 4.3 Реализовать `unsubscribe()` — пометить subscription.is_active = False
- [ ] 4.4 Реализовать `publish()` — asyncio.gather(return_exceptions=True) для параллельного вызова
- [ ] 4.5 Реализовать `clear()` — очистить subscribers и agents
- [ ] 4.6 Реализовать `register_agent()` — добавить в dict[str, RequestHandler]
- [ ] 4.7 Реализовать `unregister_agent()` — удалить из dict
- [ ] 4.8 Реализовать `send_request()` — lookup agent, dispatch с retry
- [ ] 4.9 Реализовать `broadcast()` — параллельный dispatch ко всем агентам
- [ ] 4.10 Добавить RetryConfig: max_attempts=3, exponential backoff
- [ ] 4.11 Написать unit тесты: subscribe/unsubscribe lifecycle
- [ ] 4.12 Написать unit тесты: publish с несколькими подписчиками
- [ ] 4.13 Написать unit тесты: publish с ошибкой одного подписчика (не прерывает остальных)
- [ ] 4.14 Написать integration тесты: register_agent → send_request → response
- [ ] 4.15 Написать integration тесты: broadcast → list[ChoreographyAnswer]
- [ ] 4.16 Написать error тесты: AgentNotFoundError, AgentDispatchError
- [ ] 4.17 Написать retry тесты: handler fails twice, succeeds on 3rd attempt
- [ ] 4.18 Написать concurrency тесты: parallel publish, parallel send_request

### 5. Exports

- [ ] 5.1 Обновить `codelab/src/codelab/server/agent/__init__.py` с экспортами новых классов
- [ ] 5.2 Проверить импорты через `make check`
