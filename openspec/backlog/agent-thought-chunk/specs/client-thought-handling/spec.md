## ADDED Requirements

### Requirement: ChatSessionState thinking fields
Система SHALL расширить `ChatSessionState` полями для хранения thinking state.

#### Scenario: thinking_text field
- **WHEN** `ChatSessionState` инициализирован
- **THEN** поле `thinking_text: str` ДОЛЖНО быть инициализировано пустой строкой

#### Scenario: is_thinking_streaming field
- **WHEN** `ChatSessionState` инициализирован
- **THEN** поле `is_thinking_streaming: bool` ДОЛЖНО быть инициализировано `False`

#### Scenario: clear resets thinking
- **WHEN** вызван `ChatSessionState.clear()`
- **THEN** `thinking_text` ДОЛЖЕН быть сброшен в пустую строку
- **THEN** `is_thinking_streaming` ДОЛЖЕН быть сброшен в `False`

### Requirement: ChatSessionState thinking methods
Система SHALL предоставлять методы для управления thinking state.

#### Scenario: append_streaming_thought
- **WHEN** вызван `append_streaming_thought(text)`
- **THEN** `thinking_text` ДОЛЖЕН быть дополнен переданным текстом
- **THEN** `is_thinking_streaming` ДОЛЖЕН быть установлен в `True`

#### Scenario: finalize_thinking
- **WHEN** вызван `finalize_thinking()`
- **THEN** `thinking_text` ДОЛЖЕН быть сброшен в пустую строку
- **THEN** `is_thinking_streaming` ДОЛЖЕН быть установлен в `False`

### Requirement: ThoughtChunkHandler implementation
Система SHALL предоставлять `ThoughtChunkHandler`, реализующий `SessionUpdateHandler` protocol.

#### Scenario: can_handle agent_thought_chunk
- **WHEN** вызван `can_handle("agent_thought_chunk")`
- **THEN** метод ДОЛЖЕН вернуть `True`

#### Scenario: can_handle other types
- **WHEN** вызван `can_handle("agent_message_chunk")`
- **THEN** метод ДОЛЖЕН вернуть `False`

#### Scenario: handle thought chunk with text
- **WHEN** handler получает `agent_thought_chunk` с текстовым content
- **THEN** handler ДОЛЖЕН вызвать `context.state.append_streaming_thought(text)`
- **THEN** handler ДОЛЖЕН вызвать `context.sink.sync_thinking()` с обновлённым state

#### Scenario: handle thought chunk with empty text
- **WHEN** handler получает `agent_thought_chunk` с пустым text
- **THEN** handler НЕ ДОЛЖЕН изменять state
- **THEN** handler НЕ ДОЛЖЕН вызывать sink

### Requirement: ChatUpdateSink sync_thinking
Система SHALL расширить `ChatUpdateSink` protocol методом `sync_thinking`.

#### Scenario: sync_thinking signature
- **WHEN** класс реализует `ChatUpdateSink`
- **THEN** класс ДОЛЖЕН определять метод `sync_thinking(session_id: str, text: str, is_streaming: bool) -> None`

#### Scenario: sync_thinking called by handler
- **WHEN** `ThoughtChunkHandler` вызывает `context.sink.sync_thinking()`
- **THEN** sink ДОЛЖЕН обновить Observable thinking properties
- **THEN** UI ДОЛЖНО реактивно обновиться

### Requirement: SessionUpdateDispatcher thought registration
Система SHALL регистрировать `ThoughtChunkHandler` в `SessionUpdateDispatcher`.

#### Scenario: Dispatcher routes agent_thought_chunk
- **WHEN** dispatcher получает обновление с `sessionUpdate: "agent_thought_chunk"`
- **WHEN** `ThoughtChunkHandler` зарегистрирован
- **THEN** dispatcher ДОЛЖЕН вызвать `ThoughtChunkHandler.handle()`

#### Scenario: Dispatcher O(1) lookup
- **WHEN** dispatcher инициализирован
- **THEN** `_handler_map` ДОЛЖЕН содержать entry для `"agent_thought_chunk"`
- **THEN** lookup ДОЛЖЕН быть O(1)

### Requirement: MessageChunkHandler finalize thinking
Система SHALL финализировать thinking при получении `agent_message_chunk`.

#### Scenario: Finalize thinking on first message chunk
- **WHEN** `MessageChunkHandler` получает `agent_message_chunk`
- **WHEN** `context.state.is_thinking_streaming` равен `True`
- **THEN** handler ДОЛЖЕН вызвать `context.state.finalize_thinking()`
- **THEN** handler ДОЛЖЕН вызвать `context.sink.sync_thinking()` с пустым текстом

#### Scenario: No finalize when not thinking
- **WHEN** `MessageChunkHandler` получает `agent_message_chunk`
- **WHEN** `context.state.is_thinking_streaming` равен `False`
- **THEN** handler НЕ ДОЛЖЕН вызывать `finalize_thinking()`

### Requirement: DI registration of ThoughtChunkHandler
Система SHALL регистрировать `ThoughtChunkHandler` в DI контейнере dishka.

#### Scenario: Handler registration
- **WHEN** DI контейнер создан
- **THEN** `ThoughtChunkHandler` ДОЛЖЕН быть зарегистрирован как `SessionUpdateHandler`
- **THEN** handler ДОЛЖЕН быть синглтоном с `Scope.APP`

#### Scenario: Dispatcher includes ThoughtChunkHandler
- **WHEN** `SessionUpdateDispatcher` создаётся через DI
- **THEN** dispatcher ДОЛЖЕН быть создан с `ThoughtChunkHandler` в списке handlers
