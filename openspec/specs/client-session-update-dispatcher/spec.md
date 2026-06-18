## ADDED Requirements

### Requirement: SessionUpdateHandler Protocol
Система ДОЛЖНА определять Protocol интерфейс `SessionUpdateHandler` с двумя методами: `can_handle(update_type: str) -> bool` и `handle(update_data: dict[str, Any], context: ChatUpdateContext) -> None`. Все обработчики обновлений сессии ДОЛЖНЫ реализовывать этот Protocol.

#### Scenario: Handler implements Protocol
- **WHEN** класс реализует Protocol `SessionUpdateHandler`
- **THEN** класс ДОЛЖЕН определять метод `can_handle(update_type: str) -> bool`
- **THEN** класс ДОЛЖЕН определять метод `handle(update_data: dict[str, Any], context: ChatUpdateContext) -> None`

#### Scenario: Protocol is runtime checkable
- **WHEN** `SessionUpdateHandler` декорирован `@runtime_checkable`
- **THEN** `isinstance(handler, SessionUpdateHandler)` ДОЛЖЕН возвращать True для корректных реализаций

### Requirement: SessionUpdateDispatcher registration
Система ДОЛЖНА предоставлять класс `SessionUpdateDispatcher`, который принимает список экземпляров `SessionUpdateHandler` при инициализации. Диспетчер ДОЛЖЕН перебирать обработчики в порядке регистрации при диспетчеризации обновлений.

#### Scenario: Dispatcher accepts handler list
- **WHEN** `SessionUpdateDispatcher` инициализирован списком обработчиков
- **THEN** диспетчер ДОЛЖЕН сохранить обработчики в предоставленном порядке
- **THEN** диспетчер ДОЛЖЕН проверить, что все обработчики реализуют Protocol `SessionUpdateHandler`

#### Scenario: Empty handler list
- **WHEN** `SessionUpdateDispatcher` инициализирован пустым списком
- **THEN** диспетчер ДОЛЖЕН записать предупреждение в лог
- **THEN** диспетчер ДОЛЖЕН принять конфигурацию без вызова исключения

### Requirement: SessionUpdateDispatcher dispatch logic
Система ДОЛЖНА диспетчеризировать обновления сессии, извлекая `update.sessionUpdate` из данных обновления и находя первый обработчик, чей `can_handle()` возвращает True. Диспетчер ДОЛЖЕН вызвать метод `handle()` обработчика с данными обновления и контекстом.

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

### Requirement: MessageChunkHandler implementation
Система ДОЛЖНА предоставлять `MessageChunkHandler`, который обрабатывает типы обновлений `agent_message_chunk` и `user_message_chunk`. Обработчик ДОЛЖЕН извлекать текстовое содержимое и обновлять состояние сессии соответствующим образом.

#### Scenario: Handle agent_message_chunk
- **WHEN** обработчик получает обновление `agent_message_chunk` с текстовым содержимым
- **THEN** обработчик ДОЛЖЕН добавить текст к `context.state.streaming_text`
- **THEN** обработчик ДОЛЖЕН вызвать `context.sink.sync_streaming()` с обновлённым текстом

#### Scenario: Handle user_message_chunk
- **WHEN** обработчик получает обновление `user_message_chunk` с текстовым содержимым
- **THEN** обработчик ДОЛЖЕН добавить `{"role": "user", "content": text}` к `context.state.messages`
- **THEN** обработчик ДОЛЖЕН вызвать `context.sink.sync_messages()` с обновлёнными сообщениями

#### Scenario: Empty text content
- **WHEN** обработчик получает обновление с пустым или отсутствующим текстовым содержимым
- **THEN** обработчик НЕ ДОЛЖЕН изменять состояние сессии
- **THEN** обработчик НЕ ДОЛЖЕН вызывать методы sink

### Requirement: ToolCallHandler implementation
Система ДОЛЖНА предоставлять `ToolCallHandler`, который обрабатывает типы обновлений `tool_call`, `tool_call_update` и `tool_call_result`. Обработчик ДОЛЖЕН обновлять список вызовов инструментов в состоянии сессии.

#### Scenario: Handle tool_call creation
- **WHEN** обработчик получает обновление `tool_call` с toolCallId
- **THEN** обработчик ДОЛЖЕН создать новую запись вызова инструмента в `context.state.tool_calls`
- **THEN** обработчик ДОЛЖЕН вызвать `context.sink.sync_tool_calls()` с обновлённым списком

#### Scenario: Handle tool_call_update
- **WHEN** обработчик получает обновление `tool_call_update` с существующим toolCallId
- **THEN** обработчик ДОЛЖЕН обновить существующую запись вызова инструмента с новым статусом/заголовком
- **THEN** обработчик ДОЛЖЕН вызвать `context.sink.sync_tool_calls()` с обновлённым списком

#### Scenario: Handle tool_call_result
- **WHEN** обработчик получает обновление `tool_call_result`
- **THEN** обработчик ДОЛЖЕН записать результат в лог
- **THEN** обработчик НЕ ДОЛЖЕН изменять список tool_calls (результат хранится отдельно)

### Requirement: PlanUpdateHandler implementation
Система ДОЛЖНА предоставлять `PlanUpdateHandler`, который обрабатывает типы обновлений `plan`. Обработчик ДОЛЖЕН форматировать записи плана и обновлять PlanViewModel.

#### Scenario: Handle plan update with entries
- **WHEN** обработчик получает обновление `plan` с непустым списком записей
- **WHEN** `context.plan_vm` не равен None
- **THEN** обработчик ДОЛЖЕН форматировать записи в читаемый текст
- **THEN** обработчик ДОЛЖЕН вызвать `context.plan_vm.set_plan()` с форматированным текстом

#### Scenario: Handle plan update without PlanViewModel
- **WHEN** обработчик получает обновление `plan`
- **WHEN** `context.plan_vm` равен None
- **THEN** обработчик ДОЛЖЕН записать отладочное сообщение в лог
- **THEN** обработчик НЕ ДОЛЖЕН вызывать исключение

#### Scenario: Handle empty plan
- **WHEN** обработчик получает обновление `plan` с пустым списком записей
- **THEN** обработчик ДОЛЖЕН вызвать `context.plan_vm.set_plan("")` для очистки плана

### Requirement: ConfigOptionHandler implementation
Система ДОЛЖНА предоставлять `ConfigOptionHandler`, который обрабатывает типы обновлений `config_option_update`. Обработчик ДОЛЖЕН публиковать событие `ConfigOptionUpdatedEvent` в EventBus.

#### Scenario: Handle config_option_update with options
- **WHEN** обработчик получает обновление `config_option_update` с непустыми configOptions
- **WHEN** `context.event_bus` не равен None
- **THEN** обработчик ДОЛЖЕН создать `ConfigOptionUpdatedEvent` с session_id и config_options
- **THEN** обработчик ДОЛЖЕН опубликовать событие в `context.event_bus`

#### Scenario: Handle config_option_update without EventBus
- **WHEN** обработчик получает обновление `config_option_update`
- **WHEN** `context.event_bus` равен None
- **THEN** обработчик ДОЛЖЕН записать отладочное сообщение в лог
- **THEN** обработчик НЕ ДОЛЖЕН вызывать исключение

### Requirement: ChatUpdateContext structure
Система ДОЛЖНА определять dataclass `ChatUpdateContext`, содержащий: `session_id: str`, `state: ChatSessionState`, `sink: ChatUpdateSink`, и опциональные `plan_vm: PlanViewModel | None`, `event_bus: EventBus | None`, `logger: BoundLogger | None`.

#### Scenario: Context creation
- **WHEN** `ChatUpdateContext` создан с обязательными полями
- **THEN** контекст ДОЛЖЕН содержать все предоставленные значения
- **THEN** опциональные поля ДОЛЖНЫ по умолчанию быть None

#### Scenario: Context immutability
- **WHEN** контекст передаётся обработчику
- **THEN** обработчик ДОЛЖЕН иметь возможность изменять `context.state`
- **THEN** обработчик НЕ ДОЛЖЕН изменять `context.session_id` или `context.sink`

### Requirement: ChatUpdateSink Protocol
Система ДОЛЖНА определять Protocol `ChatUpdateSink` с методами: `sync_messages(session_id: str, messages: list[dict[str, str]]) -> None`, `sync_tool_calls(session_id: str, tool_calls: list[dict[str, Any]]) -> None`, `sync_streaming(session_id: str, text: str, is_streaming: bool) -> None`.

#### Scenario: Sink implementation
- **WHEN** класс реализует Protocol `ChatUpdateSink`
- **THEN** класс ДОЛЖЕН определить все три метода sync
- **THEN** каждый метод ДОЛЖЕН обновлять соответствующее свойство Observable

#### Scenario: Sink called by handler
- **WHEN** обработчик вызывает `context.sink.sync_messages()`
- **THEN** sink ДОЛЖЕН обновить Observable `messages`
- **THEN** UI ДОЛЖЕН реактивно обновиться для отображения новых сообщений

### Requirement: DI registration of handlers
Система ДОЛЖНА регистрировать все обработчики обновлений сессии в DI контейнере dishka через `ViewModelProvider`. Каждый обработчик ДОЛЖЕН быть предоставлен как синглтон с `Scope.APP`.

#### Scenario: Handler registration
- **WHEN** DI контейнер создан
- **THEN** `MessageChunkHandler` ДОЛЖЕН быть зарегистрирован как `SessionUpdateHandler`
- **THEN** `ToolCallHandler` ДОЛЖЕН быть зарегистрирован как `SessionUpdateHandler`
- **THEN** `PlanUpdateHandler` ДОЛЖЕН быть зарегистрирован как `SessionUpdateHandler`
- **THEN** `ConfigOptionHandler` ДОЛЖЕН быть зарегистрирован как `SessionUpdateHandler`

#### Scenario: Dispatcher registration
- **WHEN** DI контейнер создан
- **THEN** `SessionUpdateDispatcher` ДОЛЖЕН быть зарегистрирован со всеми внедрёнными обработчиками
- **THEN** диспетчер ДОЛЖЕН быть синглтоном с `Scope.APP`
