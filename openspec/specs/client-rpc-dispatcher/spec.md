## ADDED Requirements

### Requirement: RpcHandler Protocol
Система ДОЛЖНА определять Protocol интерфейс `RpcHandler` с двумя методами: `can_handle(method: str) -> bool` и `async def handle(rpc_id: str | int, params: dict[str, Any]) -> dict[str, Any] | None`. Все обработчики RPC ДОЛЖНЫ реализовывать этот Protocol.

#### Scenario: Handler implements Protocol
- **WHEN** класс реализует Protocol `RpcHandler`
- **THEN** класс ДОЛЖЕН определять метод `can_handle(method: str) -> bool`
- **THEN** класс ДОЛЖЕН определять метод `async def handle(rpc_id: str | int, params: dict[str, Any]) -> dict[str, Any] | None`

#### Scenario: Protocol is runtime checkable
- **WHEN** `RpcHandler` декорирован `@runtime_checkable`
- **THEN** `isinstance(handler, RpcHandler)` ДОЛЖЕН возвращать True для корректных реализаций

### Requirement: ClientRpcDispatcher initialization
Система ДОЛЖНА предоставлять класс `ClientRpcDispatcher`, который принимает список экземпляров `RpcHandler` при инициализации. Диспетчер ДОЛЖЕН перебирать обработчики в порядке регистрации при диспетчеризации RPC запросов.

#### Scenario: Dispatcher accepts handler list
- **WHEN** `ClientRpcDispatcher` инициализирован списком обработчиков
- **THEN** диспетчер ДОЛЖЕН сохранить обработчики в предоставленном порядке
- **THEN** диспетчер ДОЛЖЕН проверить, что все обработчики реализуют Protocol `RpcHandler`

#### Scenario: Empty handler list
- **WHEN** `ClientRpcDispatcher` инициализирован пустым списком
- **THEN** диспетчер ДОЛЖЕН записать предупреждение в лог
- **THEN** диспетчер ДОЛЖЕН принять конфигурацию без вызова исключения

### Requirement: ClientRpcDispatcher dispatch logic
Система ДОЛЖНА диспетчеризировать RPC запросы, находя первый обработчик, чей `can_handle()` возвращает True для метода RPC. Диспетчер ДОЛЖЕН вызвать метод `handle()` обработчика и вернуть результат.

#### Scenario: Handler found for RPC method
- **WHEN** диспетчер получает RPC запрос с методом "fs/read_text_file"
- **WHEN** `FsReadHandler.can_handle("fs/read_text_file")` возвращает True
- **THEN** диспетчер ДОЛЖЕН вызвать `FsReadHandler.handle(rpc_id, params)`
- **THEN** диспетчер ДОЛЖЕН вернуть результат обработчика
- **THEN** диспетчер НЕ ДОЛЖЕН вызывать какие-либо другие обработчики

#### Scenario: No handler found for RPC method
- **WHEN** диспетчер получает RPC запрос с неизвестным методом
- **WHEN** ни один `can_handle()` обработчика не возвращает True
- **THEN** диспетчер ДОЛЖЕН вернуть ответ об ошибке `{"error": {"code": -32601, "message": "Method not found: {method}"}}`
- **THEN** диспетчер ДОЛЖЕН записать предупреждение в лог с именем метода

#### Scenario: Handler raises exception
- **WHEN** метод `handle()` обработчика вызывает исключение
- **THEN** диспетчер ДОЛЖЕН перехватить исключение
- **THEN** диспетчер ДОЛЖЕН вернуть ответ об ошибке `{"error": {"code": -32603, "message": str(e)}}`
- **THEN** диспетчер ДОЛЖЕН записать ошибку в лог с именем обработчика и методом RPC

### Requirement: FsReadHandler implementation
Система ДОЛЖНА предоставлять `FsReadHandler`, который обрабатывает метод RPC `fs/read_text_file`. Обработчик ДОЛЖЕН использовать `FsCallbackExecutor` для чтения файлов и возвращать соответствующие ответы.

#### Scenario: Handle fs/read_text_file successfully
- **WHEN** обработчик получает запрос `fs/read_text_file` с валидным путём
- **WHEN** `executor.read_file(path)` возвращает `(content, None)`
- **THEN** обработчик ДОЛЖЕН вернуть `{"content": content}`

#### Scenario: Handle fs/read_text_file with error
- **WHEN** обработчик получает запрос `fs/read_text_file`
- **WHEN** `executor.read_file(path)` возвращает `(None, error_message)`
- **THEN** обработчик ДОЛЖЕН вернуть `{"error": {"code": -32603, "message": error_message}}`

#### Scenario: Handle fs/read_text_file with missing path
- **WHEN** обработчик получает запрос `fs/read_text_file` без параметра `path`
- **THEN** обработчик ДОЛЖЕН вернуть `{"error": {"code": -32602, "message": "Missing required parameter: path"}}`

### Requirement: FsWriteHandler implementation
Система ДОЛЖНА предоставлять `FsWriteHandler`, который обрабатывает метод RPC `fs/write_text_file`. Обработчик ДОЛЖЕН использовать `FsCallbackExecutor` для записи файлов и возвращать соответствующие ответы.

#### Scenario: Handle fs/write_text_file successfully
- **WHEN** обработчик получает запрос `fs/write_text_file` с валидным путём и содержимым
- **WHEN** `executor.write_file(path, content)` возвращает `None`
- **THEN** обработчик ДОЛЖЕН вернуть `{}` (пустой ответ об успехе)

#### Scenario: Handle fs/write_text_file with error
- **WHEN** обработчик получает запрос `fs/write_text_file`
- **WHEN** `executor.write_file(path, content)` возвращает error_message
- **THEN** обработчик ДОЛЖЕН вернуть `{"error": {"code": -32603, "message": error_message}}`

#### Scenario: Handle fs/write_text_file with missing parameters
- **WHEN** обработчик получает запрос `fs/write_text_file` без `path` или `content`
- **THEN** обработчик ДОЛЖЕН вернуть `{"error": {"code": -32602, "message": "Missing required parameter: {param}"}}`

### Requirement: TerminalCreateHandler implementation
Система ДОЛЖНА предоставлять `TerminalCreateHandler`, который обрабатывает метод RPC `terminal/create`. Обработчик ДОЛЖЕН использовать `TerminalCallbackExecutor` для создания терминалов и возвращать terminal_id.

#### Scenario: Handle terminal/create successfully
- **WHEN** обработчик получает запрос `terminal/create` с валидной командой
- **WHEN** `executor.create_terminal(command)` возвращает `(terminal_id, None)`
- **THEN** обработчик ДОЛЖЕН вернуть `{"terminalId": terminal_id}`

#### Scenario: Handle terminal/create with error
- **WHEN** обработчик получает запрос `terminal/create`
- **WHEN** `executor.create_terminal(command)` возвращает `(None, error_message)`
- **THEN** обработчик ДОЛЖЕН вернуть `{"error": {"code": -32603, "message": error_message}}`

#### Scenario: Handle terminal/create with missing command
- **WHEN** обработчик получает запрос `terminal/create` без параметра `command`
- **THEN** обработчик ДОЛЖЕН вернуть `{"error": {"code": -32602, "message": "Missing required parameter: command"}}`

### Requirement: TerminalOutputHandler implementation
Система ДОЛЖНА предоставлять `TerminalOutputHandler`, который обрабатывает метод RPC `terminal/output`. Обработчик ДОЛЖЕН использовать `TerminalCallbackExecutor` для получения вывода терминала.

#### Scenario: Handle terminal/output successfully
- **WHEN** обработчик получает запрос `terminal/output` с валидным terminalId
- **WHEN** `executor.get_output(terminal_id)` возвращает `(output_data, None)`
- **THEN** обработчик ДОЛЖЕН вернуть output_data

#### Scenario: Handle terminal/output with error
- **WHEN** обработчик получает запрос `terminal/output`
- **WHEN** `executor.get_output(terminal_id)` возвращает `(None, error_message)`
- **THEN** обработчик ДОЛЖЕН вернуть `{"error": {"code": -32603, "message": error_message}}`

### Requirement: TerminalWaitHandler implementation
Система ДОЛЖНА предоставлять `TerminalWaitHandler`, который обрабатывает метод RPC `terminal/wait_for_exit`. Обработчик ДОЛЖЕН использовать `TerminalCallbackExecutor` для ожидания завершения терминала.

#### Scenario: Handle terminal/wait_for_exit successfully
- **WHEN** обработчик получает запрос `terminal/wait_for_exit` с валидным terminalId
- **WHEN** `executor.wait_for_exit(terminal_id)` возвращает `((exit_code, output), None)`
- **THEN** обработчик ДОЛЖЕН вернуть `{"exitCode": exit_code, "output": output}`

#### Scenario: Handle terminal/wait_for_exit with error
- **WHEN** обработчик получает запрос `terminal/wait_for_exit`
- **WHEN** `executor.wait_for_exit(terminal_id)` возвращает `(None, error_message)`
- **THEN** обработчик ДОЛЖЕН вернуть `{"error": {"code": -32603, "message": error_message}}`

### Requirement: TerminalReleaseHandler implementation
Система ДОЛЖНА предоставлять `TerminalReleaseHandler`, который обрабатывает метод RPC `terminal/release`. Обработчик ДОЛЖЕН использовать `TerminalCallbackExecutor` для освобождения ресурсов терминала.

#### Scenario: Handle terminal/release successfully
- **WHEN** обработчик получает запрос `terminal/release` с валидным terminalId
- **WHEN** `executor.release_terminal(terminal_id)` возвращает `None`
- **THEN** обработчик ДОЛЖЕН вернуть `{}` (пустой ответ об успехе)

#### Scenario: Handle terminal/release with error
- **WHEN** обработчик получает запрос `terminal/release`
- **WHEN** `executor.release_terminal(terminal_id)` возвращает error_message
- **THEN** обработчик ДОЛЖЕН вернуть `{"error": {"code": -32603, "message": error_message}}`

### Requirement: TerminalKillHandler implementation
Система ДОЛЖНА предоставлять `TerminalKillHandler`, который обрабатывает метод RPC `terminal/kill`. Обработчик ДОЛЖЕН использовать `TerminalCallbackExecutor` для завершения процессов терминала.

#### Scenario: Handle terminal/kill successfully
- **WHEN** обработчик получает запрос `terminal/kill` с валидным terminalId
- **WHEN** `executor.kill_terminal(terminal_id)` возвращает `(True, None)`
- **THEN** обработчик ДОЛЖЕН вернуть `{}` (пустой ответ об успехе)

#### Scenario: Handle terminal/kill with error
- **WHEN** обработчик получает запрос `terminal/kill`
- **WHEN** `executor.kill_terminal(terminal_id)` возвращает `(False, error_message)`
- **THEN** обработчик ДОЛЖЕН вернуть `{"error": {"code": -32603, "message": error_message}}`

### Requirement: RPC response formatting
Система ДОЛЖНА форматировать все ответы RPC в соответствии со спецификацией JSON-RPC 2.0. Ответы об успехе ДОЛЖНЫ использовать `ACPMessage.response(rpc_id, result)`, а ответы об ошибке ДОЛЖНЫ использовать `ACPMessage.error_response(rpc_id, code=..., message=...)`.

#### Scenario: Format success response
- **WHEN** обработчик возвращает dict с результатом
- **THEN** диспетчер ДОЛЖЕН обернуть его в `ACPMessage.response(rpc_id, result)`
- **THEN** ответ ДОЛЖЕН иметь `{"jsonrpc": "2.0", "id": rpc_id, "result": {...}}`

#### Scenario: Format error response
- **WHEN** обработчик возвращает dict с ошибкой `{"error": {"code": N, "message": "..."}}`
- **THEN** диспетчер ДОЛЖЕН обернуть его в `ACPMessage.error_response(rpc_id, code=N, message="...")`
- **THEN** ответ ДОЛЖЕН иметь `{"jsonrpc": "2.0", "id": rpc_id, "error": {"code": N, "message": "..."}}`

### Requirement: DI registration of RPC handlers
Система ДОЛЖНА регистрировать все обработчики RPC в DI контейнере dishka через `ClientProvider`. Каждый обработчик ДОЛЖЕН быть предоставлен как синглтон с `Scope.APP`.

#### Scenario: Handler registration
- **WHEN** DI контейнер создан
- **THEN** `FsReadHandler` ДОЛЖЕН быть зарегистрирован как `RpcHandler`
- **THEN** `FsWriteHandler` ДОЛЖЕН быть зарегистрирован как `RpcHandler`
- **THEN** `TerminalCreateHandler` ДОЛЖЕН быть зарегистрирован как `RpcHandler`
- **THEN** `TerminalOutputHandler` ДОЛЖЕН быть зарегистрирован как `RpcHandler`
- **THEN** `TerminalWaitHandler` ДОЛЖЕН быть зарегистрирован как `RpcHandler`
- **THEN** `TerminalReleaseHandler` ДОЛЖЕН быть зарегистрирован как `RpcHandler`
- **THEN** `TerminalKillHandler` ДОЛЖЕН быть зарегистрирован как `RpcHandler`

#### Scenario: Dispatcher registration
- **WHEN** DI контейнер создан
- **THEN** `ClientRpcDispatcher` ДОЛЖЕН быть зарегистрирован со всеми внедрёнными обработчиками
- **THEN** диспетчер ДОЛЖЕН быть синглтоном с `Scope.APP`

### Requirement: ACPTransportService integration with dispatcher
Система ДОЛЖНА рефакторить `ACPTransportService` для использования `ClientRpcDispatcher` вместо встроенной обработки RPC. Сервис ДОЛЖЕН делегировать все RPC запросы `fs/*` и `terminal/*` диспетчеру.

#### Scenario: Service delegates to dispatcher
- **WHEN** ACPTransportService получает RPC запрос `fs/read_text_file`
- **THEN** он ДОЛЖЕН вызвать `dispatcher.dispatch(method, rpc_id, params)`
- **THEN** он ДОЛЖЕН отправить ответ диспетчера обратно на сервер
- **THEN** он НЕ ДОЛЖЕН обрабатывать RPC встроенно

#### Scenario: Service handles dispatcher errors
- **WHEN** диспетчер возвращает ответ об ошибке
- **THEN** ACPTransportService ДОЛЖЕН отправить ответ об ошибке на сервер
- **THEN** ACPTransportService ДОЛЖЕН записать ошибку в лог
- **THEN** ACPTransportService ДОЛЖЕН продолжить обработку других запросов

### Requirement: RPC logging
Система ДОЛЖНА логировать все RPC запросы и ответы с соответствующим контекстом. Диспетчер ДОЛЖЕН логировать метод RPC, rpc_id и имя обработчика.

#### Scenario: Log incoming RPC request
- **WHEN** диспетчер получает RPC запрос
- **THEN** диспетчер ДОЛЖЕН записать сообщение уровня `info` с методом и rpc_id

#### Scenario: Log handler execution
- **WHEN** диспетчер вызывает обработчик
- **THEN** диспетчер ДОЛЖЕН записать сообщение уровня `debug` с именем обработчика

#### Scenario: Log RPC response
- **WHEN** диспетчер возвращает ответ
- **THEN** диспетчер ДОЛЖЕН записать сообщение уровня `debug` с методом и rpc_id
- **THEN** лог ДОЛЖЕН включать, является ли ответ успехом или ошибкой

#### Scenario: Log handler errors
- **WHEN** обработчик вызывает исключение
- **THEN** диспетчер ДОЛЖЕН записать сообщение уровня `error` с именем обработчика, методом и деталями исключения
