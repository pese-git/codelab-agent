## ADDED Requirements

### Requirement: FsCallbackExecutor initialization
Система ДОЛЖНА предоставлять класс `FsCallbackExecutor`, который принимает параметр `base_path: Path` для принудительного применения sandbox. Исполнитель ДОЛЖЕН проверить, что base_path существует и является директорией.

#### Scenario: Initialize with valid base_path
- **WHEN** `FsCallbackExecutor` инициализирован с существующим путём к директории
- **THEN** экземпляр ДОЛЖЕН сохранить base_path
- **THEN** экземпляр НЕ ДОЛЖЕН вызывать какие-либо исключения

#### Scenario: Initialize with non-existent base_path
- **WHEN** `FsCallbackExecutor` инициализирован с несуществующим путём
- **THEN** экземпляр ДОЛЖЕН вызвать `ValueError` с описательным сообщением
- **THEN** экземпляр НЕ ДОЛЖЕН быть создан

#### Scenario: Initialize with file instead of directory
- **WHEN** `FsCallbackExecutor` инициализирован с путём, который является файлом
- **THEN** экземпляр ДОЛЖЕН вызвать `ValueError` с описательным сообщением

### Requirement: FsCallbackExecutor read_file
Система ДОЛЖНА реализовывать метод `read_file(path: str) -> tuple[str | None, str | None]`, который читает содержимое файла асинхронно. Метод ДОЛЖЕН использовать `asyncio.to_thread()` для неблокирующего ввода-вывода и применять ограничения sandbox.

#### Scenario: Read existing file within sandbox
- **WHEN** `read_file()` вызван с путём внутри base_path
- **WHEN** файл существует и доступен для чтения
- **THEN** метод ДОЛЖЕН вернуть `(content, None)`, где content — текст файла
- **THEN** метод НЕ ДОЛЖЕН блокировать event loop

#### Scenario: Read file outside sandbox
- **WHEN** `read_file()` вызван с путём вне base_path (например, `../../etc/passwd`)
- **THEN** метод ДОЛЖЕН вернуть `(None, "Path outside sandbox: {path}")`
- **THEN** метод НЕ ДОЛЖЕН читать файл

#### Scenario: Read non-existent file
- **WHEN** `read_file()` вызван с путём, который не существует
- **THEN** метод ДОЛЖЕН вернуть `(None, "File not found: {path}")`
- **THEN** метод НЕ ДОЛЖЕН вызывать исключение

#### Scenario: Read file with permission error
- **WHEN** `read_file()` вызван с путём, который недоступен для чтения
- **THEN** метод ДОЛЖЕН вернуть `(None, "Permission denied: {path}")`
- **THEN** метод НЕ ДОЛЖЕН вызывать исключение

#### Scenario: Read file with encoding error
- **WHEN** `read_file()` вызван с бинарным файлом
- **THEN** метод ДОЛЖЕН вернуть `(None, "Encoding error: {path}")`
- **THEN** метод НЕ ДОЛЖЕН вызывать исключение

### Requirement: FsCallbackExecutor write_file
Система ДОЛЖНА реализовывать метод `write_file(path: str, content: str) -> str | None`, который записывает содержимое в файл асинхронно. Метод ДОЛЖЕН использовать `asyncio.to_thread()` для неблокирующего ввода-вывода и применять ограничения sandbox.

#### Scenario: Write file within sandbox
- **WHEN** `write_file()` вызван с путём внутри base_path и валидным содержимым
- **THEN** метод ДОЛЖЕН записать содержимое в файл
- **THEN** метод ДОЛЖЕН вернуть `None` (успех)
- **THEN** метод НЕ ДОЛЖЕН блокировать event loop

#### Scenario: Write file outside sandbox
- **WHEN** `write_file()` вызван с путём вне base_path
- **THEN** метод ДОЛЖЕН вернуть `"Path outside sandbox: {path}"`
- **THEN** метод НЕ ДОЛЖЕН записывать файл

#### Scenario: Write file with permission error
- **WHEN** `write_file()` вызван с путём, который недоступен для записи
- **THEN** метод ДОЛЖЕН вернуть `"Permission denied: {path}"`
- **THEN** метод НЕ ДОЛЖЕН вызывать исключение

#### Scenario: Write file creates parent directories
- **WHEN** `write_file()` вызван с путём, где родительские директории не существуют
- **THEN** метод ДОЛЖЕН создать родительские директории
- **THEN** метод ДОЛЖЕН успешно записать файл

### Requirement: FsCallbackExecutor path validation
Система ДОЛЖНА проверять, что все пути к файлам находятся внутри sandbox (base_path). Проверка ДОЛЖНА разрешать символические ссылки и нормализовывать пути для предотвращения атак path traversal.

#### Scenario: Validate path with symbolic links
- **WHEN** путь содержит символические ссылки, которые разрешаются вне base_path
- **THEN** проверка ДОЛЖНА обнаружить выход за пределы
- **THEN** операция ДОЛЖНА быть отклонена

#### Scenario: Validate path with .. components
- **WHEN** путь содержит компоненты `..`, которые разрешаются вне base_path
- **THEN** проверка ДОЛЖНА обнаружить выход за пределы
- **THEN** операция ДОЛЖНА быть отклонена

#### Scenario: Validate path with absolute path
- **WHEN** путь является абсолютным и находится вне base_path
- **THEN** проверка ДОЛЖНА обнаружить выход за пределы
- **THEN** операция ДОЛЖНА быть отклонена

### Requirement: TerminalCallbackExecutor initialization
Система ДОЛЖНА предоставлять класс `TerminalCallbackExecutor`, который управляет жизненным циклом терминала. Исполнитель ДОЛЖЕН поддерживать кэш состояний терминала, ключом которого является terminal_id.

#### Scenario: Initialize executor
- **WHEN** `TerminalCallbackExecutor` инициализирован
- **THEN** экземпляр ДОЛЖЕН создать пустой кэш состояний терминала
- **THEN** экземпляр НЕ ДОЛЖЕН вызывать какие-либо исключения

### Requirement: TerminalCallbackExecutor create_terminal
Система ДОЛЖНА реализовывать метод `create_terminal(command: str) -> tuple[str | None, str | None]`, который создаёт новый терминал и выполняет команду. Метод ДОЛЖЕН вернуть `(terminal_id, None)` при успехе или `(None, error_message)` при ошибке.

#### Scenario: Create terminal successfully
- **WHEN** `create_terminal()` вызван с валидной командой
- **THEN** метод ДОЛЖЕН создать новый терминал через базовый исполнитель
- **THEN** метод ДОЛЖЕН кэшировать состояние терминала
- **THEN** метод ДОЛЖЕН вернуть `(terminal_id, None)`

#### Scenario: Create terminal with invalid command
- **WHEN** `create_terminal()` вызван с пустой командой
- **THEN** метод ДОЛЖЕН вернуть `(None, "Command cannot be empty")`

#### Scenario: Create terminal fails
- **WHEN** `create_terminal()` завершается с ошибкой из-за ошибки базового исполнителя
- **THEN** метод ДОЛЖЕН вернуть `(None, error_message)`
- **THEN** метод НЕ ДОЛЖЕН кэшировать какое-либо состояние терминала

### Requirement: TerminalCallbackExecutor get_output
Система ДОЛЖНА реализовывать метод `get_output(terminal_id: str) -> tuple[dict[str, Any] | None, str | None]`, который получает вывод терминала. Метод ДОЛЖЕН вернуть данные вывода или сообщение об ошибке.

#### Scenario: Get output from existing terminal
- **WHEN** `get_output()` вызван с terminal_id из кэша
- **THEN** метод ДОЛЖЕН получить вывод из базового исполнителя
- **THEN** метод ДОЛЖЕН вернуть `({"output": "...", "isComplete": true, "exitCode": N}, None)`

#### Scenario: Get output from non-existent terminal
- **WHEN** `get_output()` вызван с terminal_id, которого нет в кэше
- **THEN** метод ДОЛЖЕН вернуть `(None, "Terminal not found: {terminal_id}")`

#### Scenario: Get output fails
- **WHEN** `get_output()` завершается с ошибкой из-за ошибки базового исполнителя
- **THEN** метод ДОЛЖЕН вернуть `(None, error_message)`

### Requirement: TerminalCallbackExecutor wait_for_exit
Система ДОЛЖНА реализовывать метод `wait_for_exit(terminal_id: str) -> tuple[tuple[int | None, str | None] | None, str | None]`, который ожидает завершения терминала. Метод ДОЛЖЕН вернуть статус выхода или сообщение об ошибке.

#### Scenario: Wait for exit successfully
- **WHEN** `wait_for_exit()` вызван с terminal_id из кэша
- **WHEN** терминал завершается нормально
- **THEN** метод ДОЛЖЕН вернуть `((exit_code, output), None)`

#### Scenario: Wait for exit from non-existent terminal
- **WHEN** `wait_for_exit()` вызван с terminal_id, которого нет в кэше
- **THEN** метод ДОЛЖЕН вернуть `(None, "Terminal not found: {terminal_id}")`

#### Scenario: Wait for exit with timeout
- **WHEN** `wait_for_exit()` истекает время ожидания терминала
- **THEN** метод ДОЛЖЕН вернуть `((None, "Timeout waiting for terminal"), None)`

### Requirement: TerminalCallbackExecutor release_terminal
Система ДОЛЖНА реализовывать метод `release_terminal(terminal_id: str) -> str | None`, который освобождает ресурсы терминала. Метод ДОЛЖЕН удалить терминал из кэша.

#### Scenario: Release existing terminal
- **WHEN** `release_terminal()` вызван с terminal_id из кэша
- **THEN** метод ДОЛЖЕН освободить ресурсы через базовый исполнитель
- **THEN** метод ДОЛЖЕН удалить терминал из кэша
- **THEN** метод ДОЛЖЕН вернуть `None` (успех)

#### Scenario: Release non-existent terminal
- **WHEN** `release_terminal()` вызван с terminal_id, которого нет в кэше
- **THEN** метод ДОЛЖЕН вернуть `"Terminal not found: {terminal_id}"`

#### Scenario: Release terminal fails
- **WHEN** `release_terminal()` завершается с ошибкой из-за ошибки базового исполнителя
- **THEN** метод ДОЛЖЕН всё равно удалить терминал из кэша
- **THEN** метод ДОЛЖЕН вернуть `error_message`

### Requirement: TerminalCallbackExecutor kill_terminal
Система ДОЛЖНА реализовывать метод `kill_terminal(terminal_id: str) -> tuple[bool, str | None]`, который принудительно завершает терминал. Метод ДОЛЖЕН вернуть статус успеха или сообщение об ошибке.

#### Scenario: Kill existing terminal
- **WHEN** `kill_terminal()` вызван с terminal_id из кэша
- **THEN** метод ДОЛЖЕН завершить процесс терминала
- **THEN** метод ДОЛЖЕН удалить терминал из кэша
- **THEN** метод ДОЛЖЕН вернуть `(True, None)`

#### Scenario: Kill non-existent terminal
- **WHEN** `kill_terminal()` вызван с terminal_id, которого нет в кэше
- **THEN** метод ДОЛЖЕН вернуть `(False, "Terminal not found: {terminal_id}")`

### Requirement: TerminalCallbackExecutor state cache management
Система ДОЛЖНА поддерживать потокобезопасный кэш состояний терминала. Кэш ДОЛЖЕН очищаться при освобождении или завершении терминалов.

#### Scenario: Cache is thread-safe
- **WHEN** несколько асинхронных задач обращаются к кэшу одновременно
- **THEN** кэш НЕ ДОЛЖЕН повреждать данные
- **THEN** кэш ДОЛЖЕН использовать соответствующую синхронизацию (asyncio.Lock)

#### Scenario: Cache cleanup on release
- **WHEN** терминал освобождается
- **THEN** состояние терминала ДОЛЖНО быть удалено из кэша
- **THEN** последующие вызовы с тем же terminal_id ДОЛЖНЫ возвращать "not found"

#### Scenario: Cache cleanup on kill
- **WHEN** терминал завершается
- **THEN** состояние терминала ДОЛЖНО быть удалено из кэша
- **THEN** последующие вызовы с тем же terminal_id ДОЛЖНЫ возвращать "not found"

### Requirement: DI registration of executors
Система ДОЛЖНА регистрировать `FsCallbackExecutor` и `TerminalCallbackExecutor` в DI контейнере dishka. Оба исполнителя ДОЛЖНЫ быть синглтонами с `Scope.APP`.

#### Scenario: FsCallbackExecutor registration
- **WHEN** DI контейнер создан
- **THEN** `FsCallbackExecutor` ДОЛЖЕН быть зарегистрирован с `base_path` из `ClientConfig.cwd`
- **THEN** экземпляр ДОЛЖЕН быть синглтоном с `Scope.APP`

#### Scenario: TerminalCallbackExecutor registration
- **WHEN** DI контейнер создан
- **THEN** `TerminalCallbackExecutor` ДОЛЖЕН быть зарегистрирован
- **THEN** экземпляр ДОЛЖЕН быть синглтоном с `Scope.APP`

### Requirement: ChatViewModel integration with executors
Система ДОЛЖНА рефакторить `ChatViewModel` для использования `FsCallbackExecutor` и `TerminalCallbackExecutor` вместо прямых вызовов исполнителей. ViewModel ДОЛЖНА делегировать все операции FS и терминала исполнителям.

#### Scenario: ViewModel uses FsCallbackExecutor
- **WHEN** ChatViewModel необходимо обработать callback `fs/read`
- **THEN** он ДОЛЖЕН вызвать `fs_executor.read_file(path)`
- **THEN** он НЕ ДОЛЖЕН выполнять прямой ввод-вывод файлов

#### Scenario: ViewModel uses TerminalCallbackExecutor
- **WHEN** ChatViewModel необходимо обработать callback `terminal/create`
- **THEN** он ДОЛЖЕН вызвать `terminal_executor.create_terminal(command)`
- **THEN** он НЕ ДОЛЖЕН напрямую создавать терминалы

#### Scenario: ViewModel handles executor errors
- **WHEN** операции исполнителя завершаются с ошибкой
- **THEN** ChatViewModel ДОЛЖЕН обработать ошибку корректно
- **THEN** ChatViewModel ДОЛЖЕН записать ошибку в лог
- **THEN** ChatViewModel ДОЛЖЕН вернуть соответствующий ответ об ошибке серверу
