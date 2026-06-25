# Delta-спецификация agent-event-bus

## MODIFIED Requirements

### Requirement: Гарантии отправки запроса

Метод `send_request()` MUST:
- Вызывать `AgentNotFoundError`, если target_agent не зарегистрирован
- Повторять отправку до 3 раз с экспоненциальной задержкой
- Вызывать `AgentDispatchError`, если все повторные попытки исчерпаны
- Распространять контекст parent_span для tracing
- Возвращать `AgentResponse` (DomainEvent), обёрнутый из `AgentResult`
- Принимать `messages` из `PayloadEnvelope.to_messages()` на границе с `ContextManager`

#### Scenario: AgentRequest из PayloadEnvelope
- **WHEN** стратегия формирует `AgentRequest`
- **THEN** `request.messages` формируется через `envelope.to_messages()` на границе с `EventBus`

#### Scenario: PayloadEnvelope не протекает
- **WHEN** `ContextManager` возвращает `PayloadEnvelope`
- **THEN** `PayloadEnvelope` не передаётся в `EventBus` напрямую, только через `to_messages()` на границе

### Requirement: Интеграция с ContextManager

`AgentEventBus` MUST работать с `ContextManager` через `ExecutionEngine`:
- Стратегии вызывают `ExecutionEngine.build_context()` → получают `PayloadEnvelope`
- Стратегии конвертируют `envelope.to_messages()` → `AgentRequest.messages`
- `EventBus.send_request()` принимает `AgentRequest` с плоским списком сообщений

#### Scenario: Прозрачная интеграция
- **WHEN** стратегия использует `ContextManager`
- **THEN** `EventBus` не знает о `PayloadEnvelope`, работает с плоским списком сообщений

#### Scenario: Обратная совместимость
- **WHEN** используется legacy `ContextCompactor`
- **THEN** `EventBus` работает как прежде, без изменений
