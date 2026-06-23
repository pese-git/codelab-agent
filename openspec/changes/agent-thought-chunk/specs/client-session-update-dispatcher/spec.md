## MODIFIED Requirements

### Requirement: SessionUpdateDispatcher registration
Система SHALL предоставлять класс `SessionUpdateDispatcher`, который принимает список экземпляров `SessionUpdateHandler` при инициализации. Диспетчер SHALL перебирать обработчики в порядке регистрации при диспетчеризации обновлений. Диспетчер SHALL поддерживать обработку `agent_thought_chunk` через `ThoughtChunkHandler`.

#### Scenario: Dispatcher accepts handler list
- **WHEN** `SessionUpdateDispatcher` инициализирован списком обработчиков
- **THEN** диспетчер ДОЛЖЕН сохранить обработчики в предоставленном порядке
- **THEN** диспетчер ДОЛЖЕН проверить, что все обработчики реализуют Protocol `SessionUpdateHandler`

#### Scenario: Empty handler list
- **WHEN** `SessionUpdateDispatcher` инициализирован пустым списком
- **THEN** диспетчер ДОЛЖЕН записать предупреждение в лог
- **THEN** диспетчер ДОЛЖЕН принять конфигурацию без вызова исключения

#### Scenario: Dispatcher includes ThoughtChunkHandler
- **WHEN** `SessionUpdateDispatcher` инициализирован через DI
- **THEN** `ThoughtChunkHandler` ДОЛЖЕН быть в списке handlers
- **THEN** `_handler_map` ДОЛЖЕН содержать entry для `"agent_thought_chunk"`

### Requirement: SessionUpdateDispatcher dispatch logic
Система SHALL диспетчеризировать обновления сессии, извлекая `update.sessionUpdate` из данных обновления и находя первый обработчик, чей `can_handle()` возвращает True. Диспетчер SHALL вызвать метод `handle()` обработчика с данными обновления и контекстом. Диспетчер SHALL маршрутизировать `agent_thought_chunk` к `ThoughtChunkHandler`.

#### Scenario: Handler found for update type
- **WHEN** диспетчер получает обновление с типом `sessionUpdate` "agent_message_chunk"
- **WHEN** `MessageChunkHandler.can_handle("agent_message_chunk")` возвращает True
- **THEN** диспетчер ДОЛЖЕН вызвать `MessageChunkHandler.handle(update_data, context)`
- **THEN** диспетчер НЕ ДОЛЖЕН вызывать какие-либо другие обработчики

#### Scenario: No handler found for update type
- **WHEN** диспетчер получает обновление с неизвестным типом `sessionUpdate`
- **WHEN** ни один `can_handle()` обработчика не возвращает True
- **THEN** диспетчер ДОЛЖЕН записать предупреждение в лог с типом обновления
- **THEN** диспетчер НЕ ДОЛЖЕН вызывать исключение

#### Scenario: Handler raises exception
- **WHEN** метод `handle()` обработчика вызывает исключение
- **THEN** диспетчер ДОЛЖЕН перехватить исключение
- **THEN** диспетчер ДОЛЖЕН записать ошибку в лог с именем обработчика и типом обновления
- **THEN** диспетчер ДОЛЖЕН продолжить обработку (не распространять исключение)

#### Scenario: Dispatch agent_thought_chunk
- **WHEN** диспетчер получает обновление с типом `sessionUpdate` "agent_thought_chunk"
- **WHEN** `ThoughtChunkHandler.can_handle("agent_thought_chunk")` возвращает True
- **THEN** диспетчер ДОЛЖЕН вызвать `ThoughtChunkHandler.handle(update_data, context)`

### Requirement: DI registration of handlers
Система SHALL регистрировать все обработчики обновлений сессии в DI контейнере dishka через `ViewModelProvider`. Каждый обработчик SHALL быть предоставлен как синглтон с `Scope.APP`.

#### Scenario: Handler registration
- **WHEN** DI контейнер создан
- **THEN** `MessageChunkHandler` ДОЛЖЕН быть зарегистрирован как `SessionUpdateHandler`
- **THEN** `ToolCallHandler` ДОЛЖЕН быть зарегистрирован как `SessionUpdateHandler`
- **THEN** `PlanUpdateHandler` ДОЛЖЕН быть зарегистрирован как `SessionUpdateHandler`
- **THEN** `ConfigOptionHandler` ДОЛЖЕН быть зарегистрирован как `SessionUpdateHandler`
- **THEN** `ThoughtChunkHandler` ДОЛЖЕН быть зарегистрирован как `SessionUpdateHandler`

#### Scenario: Dispatcher registration
- **WHEN** DI контейнер создан
- **THEN** `SessionUpdateDispatcher` ДОЛЖЕН быть зарегистрирован со всеми внедрёнными обработчиками
- **THEN** диспетчер ДОЛЖЕН быть синглтоном с `Scope.APP`
