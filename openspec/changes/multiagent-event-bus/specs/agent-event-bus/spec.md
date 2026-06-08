# Spec: agent-event-bus

## ДОБАВЛЕННЫЕ Требования

### Требование: Интерфейс AbstractEventBus

Система ДОЛЖНА предоставлять ABC `AbstractEventBus` со следующими методами:

- `subscribe(event_type: type, handler: Handler) -> Subscription` — подписаться на события указанного типа
- `unsubscribe(subscription: Subscription) -> None` — отменить подписку
- `async publish(event: DomainEvent) -> None` — опубликовать событие (fire-and-forget)
- `async clear() -> None` — очистить все подписки и зарегистрированных агентов

### Требование: Протокол AgentRoutingInterface

Система ДОЛЖНА предоставлять протокол `AgentRoutingInterface` со следующими методами:

- `async register_agent(agent_name: str, handler: RequestHandler) -> None`
- `async unregister_agent(agent_name: str) -> None`
- `async send_request(request: AgentRequest, parent_span: SpanContext | None) -> AgentResponse`
- `async broadcast(broadcast: ContextBroadcast) -> list[ChoreographyAnswer]`

> **Примечание:** `send_request()` возвращает `AgentResponse` (DomainEvent с `request_id`, `text`, `tool_calls`, `usage: TokenUsage`, `stop_reason`, `agent_name`).

### Требование: Реализация AgentEventBus

Система ДОЛЖНА реализовывать оба интерфейса `AbstractEventBus` и `AgentRoutingInterface` в едином классе `AgentEventBus`.

### Требование: Гарантии публикации

Метод `publish()` ДОЛЖЕН:
- Вызывать всех подписчиков на тип события параллельно через `asyncio.gather(return_exceptions=True)`
- Логировать ошибки отдельных обработчиков, не прерывая работу остальных
- Завершаться только после выполнения всех обработчиков (детерминировано для тестов)
- Не гарантировать порядок вызова обработчиков

### Требование: Гарантии отправки запроса

Метод `send_request()` ДОЛЖЕН:
- Вызывать `AgentNotFoundError` если target_agent не зарегистрирован
- Повторять отправку до 3 раз с экспоненциальной задержкой
- Вызывать `AgentDispatchError` если все повторные попытки исчерпаны
- Распространять контекст parent_span для tracing
- Возвращать `AgentResponse` (DomainEvent) обёрнутый из `AgentResult`

### Требование: Гарантии broadcast

Метод `broadcast()` ДОЛЖЕН:
- Отправлять всем зарегистрированным агентам параллельно
- Возвращать список `ChoreographyAnswer`, включая ответы с ошибками
- Не падать при ошибке обработчиков отдельных агентов (собирать ошибки, логировать, продолжать)
