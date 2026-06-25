# Delta-спецификация single-strategy

## MODIFIED Requirements

### Requirement: Поток SingleStrategy

SingleStrategy ДОЛЖНА:
1. Вызвать `ExecutionEngine.build_context(session, prompt, agent_scope="single", system_prompt=...)`
2. Получить `PayloadEnvelope` от `ContextManager.build_context()`
3. Вызвать `ContextManager.ensure_context_fits(envelope, max_context_tokens, reserved_tokens)`
4. Конвертировать `envelope.to_messages()` в `AgentRequest.messages`
5. Вызвать `event_bus.send_request(request, parent_span)`
6. Вернуть `AgentResponse` вызывающему

#### Scenario: SingleStrategy с ContextManager
- **WHEN** вызывается `SingleStrategy.execute()`
- **THEN** стратегия использует `ContextManager.build_context()` и `ensure_context_fits()` вместо прямого вызова legacy `ContextCompactor`

#### Scenario: Конвертация PayloadEnvelope
- **WHEN** `PayloadEnvelope` получен от `build_context()`
- **THEN** стратегия вызывает `envelope.to_messages()` для получения плоского списка сообщений для `AgentRequest`

### Requirement: ExecutionEngine.build_context с ContextManager

`ExecutionEngine.build_context(session, prompt, *, agent_scope, system_prompt, options)` ДОЛЖЕН:
1. Вызвать `ContextManager.build_context(session, prompt, agent_scope=agent_scope, system_prompt=system_prompt, options=options)`
2. Получить `PayloadEnvelope`
3. Вызвать `ContextManager.ensure_context_fits(envelope, max_context_tokens, reserved_tokens)`
4. Сформировать `AgentContext` с `conversation_history = envelope.to_messages()`

#### Scenario: ExecutionEngine делегирует ContextManager
- **WHEN** вызывается `ExecutionEngine.build_context()`
- **THEN** выполнение делегируется `ContextManager`, legacy `ContextCompactor` используется только при `agents.context.enabled=false`

#### Scenario: AgentContext из PayloadEnvelope
- **WHEN** `PayloadEnvelope` получен
- **THEN** `AgentContext.conversation_history` формируется через `envelope.to_messages()`

### Requirement: Выбор реализации ContextManager

`ExecutionEngine` ДОЛЖЕН выбирать реализацию по флагу `agents.context.enabled`:
- `enabled=true` → использовать новый `ContextManager`
- `enabled=false` (по умолчанию) → использовать legacy `ContextCompactor`

#### Scenario: Legacy режим
- **WHEN** `agents.context.enabled=false`
- **THEN** `ExecutionEngine` использует legacy `ContextCompactor`, поведение бит-в-бит как до Phase 0

#### Scenario: Новый режим
- **WHEN** `agents.context.enabled=true`
- **THEN** `ExecutionEngine` использует новый `ContextManager` с полной функциональностью
