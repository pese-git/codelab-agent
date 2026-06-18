## ADDED Requirements

### Requirement: ChatPersistencePort Protocol
Система ДОЛЖНА определять Protocol интерфейс `ChatPersistencePort` с async методами для сохранения и загрузки истории чата. Protocol ДОЛЖЕН использовать декоратор `@runtime_checkable`.

#### Scenario: Protocol defines save_messages
- **WHEN** Protocol `ChatPersistencePort` определён
- **THEN** он ДОЛЖЕН включать `async def save_messages(session_id: str, messages: list[dict[str, str]], replay_updates: list[dict[str, Any]] | None = None) -> None`

#### Scenario: Protocol defines load_messages
- **WHEN** Protocol `ChatPersistencePort` определён
- **THEN** он ДОЛЖЕН включать `async def load_messages(session_id: str) -> list[dict[str, str]]`

#### Scenario: Protocol defines load_replay_updates
- **WHEN** Protocol `ChatPersistencePort` определён
- **THEN** он ДОЛЖЕН включать `async def load_replay_updates(session_id: str) -> list[dict[str, Any]]`

#### Scenario: Protocol is runtime checkable
- **WHEN** класс реализует все методы `ChatPersistencePort`
- **THEN** `isinstance(instance, ChatPersistencePort)` ДОЛЖЕН возвращать True

### Requirement: FileChatPersistence initialization
Система ДОЛЖНА предоставлять класс `FileChatPersistence`, реализующий `ChatPersistencePort` с использованием файлового хранилища. Класс ДОЛЖЕН принимать параметр `history_dir: Path` и создавать директорию, если она не существует.

#### Scenario: Initialize with valid directory
- **WHEN** `FileChatPersistence` инициализирован с существующим путём к директории
- **THEN** экземпляр ДОЛЖЕН сохранить путь к директории
- **THEN** экземпляр НЕ ДОЛЖЕН вызывать какие-либо исключения

#### Scenario: Initialize with non-existent directory
- **WHEN** `FileChatPersistence` инициализирован с несуществующим путём к директории
- **THEN** экземпляр ДОЛЖЕН создать директорию (включая родительские)
- **THEN** экземпляр ДОЛЖЕН сохранить путь к директории

#### Scenario: Initialize with inaccessible directory
- **WHEN** `FileChatPersistence` инициализирован с путём, который не может быть создан (отказано в доступе)
- **THEN** экземпляр ДОЛЖЕН записать предупреждение в лог
- **THEN** экземпляр ДОЛЖЕН всё равно сохранить путь к директории (операции будут завершаться с ошибкой корректно)

### Requirement: FileChatPersistence save_messages
Система ДОЛЖНА реализовывать метод `save_messages()`, который записывает сообщения и обновления воспроизведения в JSON файл. Метод ДОЛЖЕН использовать `asyncio.to_thread()` для неблокирующего ввода-вывода.

#### Scenario: Save messages successfully
- **WHEN** `save_messages()` вызван с валидным session_id и сообщениями
- **THEN** метод ДОЛЖЕН записать JSON файл с именем `{session_id}.json` в history_dir
- **THEN** JSON файл ДОЛЖЕН содержать `{"messages": [...], "replay_updates": [...]}`
- **THEN** метод НЕ ДОЛЖЕН блокировать event loop

#### Scenario: Save messages with None replay_updates
- **WHEN** `save_messages()` вызван с `replay_updates=None`
- **THEN** JSON файл ДОЛЖЕН содержать `{"messages": [...], "replay_updates": []}`

#### Scenario: Save messages with invalid session_id
- **WHEN** `save_messages()` вызван с session_id, содержащим разделители путей
- **THEN** метод ДОЛЖЕН очистить session_id (заменить `/` и `\` на `_`)
- **THEN** метод ДОЛЖЕН записать в очищенный путь файла

#### Scenario: Save messages fails due to disk error
- **WHEN** `save_messages()` завершается с ошибкой из-за переполнения диска или ошибки прав доступа
- **THEN** метод ДОЛЖЕН записать предупреждение в лог с session_id и деталями ошибки
- **THEN** метод НЕ ДОЛЖЕН вызывать исключение
- **THEN** метод ДОЛЖЕН вернуть None (корректная деградация)

### Requirement: FileChatPersistence load_messages
Система ДОЛЖНА реализовывать метод `load_messages()`, который читает сообщения из JSON файла. Метод ДОЛЖЕН использовать `asyncio.to_thread()` для неблокирующего ввода-вывода.

#### Scenario: Load messages from existing file
- **WHEN** `load_messages()` вызван с session_id, для которого есть сохранённый файл
- **THEN** метод ДОЛЖЕН прочитать JSON файл
- **THEN** метод ДОЛЖЕН вернуть список `messages` из JSON
- **THEN** метод НЕ ДОЛЖЕН блокировать event loop

#### Scenario: Load messages from non-existent file
- **WHEN** `load_messages()` вызван с session_id, для которого нет сохранённого файла
- **THEN** метод ДОЛЖЕН вернуть пустой список `[]`
- **THEN** метод НЕ ДОЛЖЕН вызывать исключение

#### Scenario: Load messages from corrupted file
- **WHEN** `load_messages()` вызван и JSON файл повреждён (невалидный JSON)
- **THEN** метод ДОЛЖЕН записать предупреждение в лог с session_id и деталями ошибки
- **THEN** метод ДОЛЖЕН вернуть пустой список `[]`
- **THEN** метод НЕ ДОЛЖЕН вызывать исключение

#### Scenario: Load messages with invalid structure
- **WHEN** `load_messages()` вызван и JSON файл имеет невалидную структуру (не dict, или messages не list)
- **THEN** метод ДОЛЖЕН записать предупреждение в лог
- **THEN** метод ДОЛЖЕН вернуть пустой список `[]`

### Requirement: FileChatPersistence load_replay_updates
Система ДОЛЖНА реализовывать метод `load_replay_updates()`, который читает обновления воспроизведения из JSON файла. Метод ДОЛЖЕН использовать `asyncio.to_thread()` для неблокирующего ввода-вывода.

#### Scenario: Load replay updates from existing file
- **WHEN** `load_replay_updates()` вызван с session_id, для которого есть сохранённый файл
- **THEN** метод ДОЛЖЕН прочитать JSON файл
- **THEN** метод ДОЛЖЕН вернуть список `replay_updates` из JSON
- **THEN** метод НЕ ДОЛЖЕН блокировать event loop

#### Scenario: Load replay updates from non-existent file
- **WHEN** `load_replay_updates()` вызван с session_id, для которого нет сохранённого файла
- **THEN** метод ДОЛЖЕН вернуть пустой список `[]`
- **THEN** метод НЕ ДОЛЖЕН вызывать исключение

#### Scenario: Load replay updates from corrupted file
- **WHEN** `load_replay_updates()` вызван и JSON файл повреждён
- **THEN** метод ДОЛЖЕН записать предупреждение в лог
- **THEN** метод ДОЛЖЕН вернуть пустой список `[]`

### Requirement: FileChatPersistence file path sanitization
Система ДОЛЖНА очищать session_id при конструировании путей к файлам для предотвращения атак path traversal. Метод ДОЛЖЕН заменять `/` и `\` на `_`.

#### Scenario: Sanitize session_id with slashes
- **WHEN** session_id равен `"session/with/slashes"`
- **THEN** путь к файлу ДОЛЖЕН быть `history_dir / "session_with_slashes.json"`

#### Scenario: Sanitize session_id with backslashes
- **WHEN** session_id равен `"session\\with\\backslashes"`
- **THEN** путь к файлу ДОЛЖЕН быть `history_dir / "session_with_backslashes.json"`

#### Scenario: Sanitize session_id with mixed separators
- **WHEN** session_id равен `"session/with\\both"`
- **THEN** путь к файлу ДОЛЖЕН быть `history_dir / "session_with_both.json"`

### Requirement: FileChatPersistence JSON encoding
Система ДОЛЖНА кодировать сообщения и обновления воспроизведения как JSON с кодировкой UTF-8 и ensure_ascii=False для поддержки международных символов.

#### Scenario: Save messages with Unicode characters
- **WHEN** сообщения содержат символы Unicode (например, русский текст)
- **THEN** JSON файл ДОЛЖЕН сохранять символы без экранирования
- **THEN** JSON файл ДОЛЖЕН быть закодирован как UTF-8

#### Scenario: Load messages with Unicode characters
- **WHEN** JSON файл содержит символы Unicode
- **THEN** `load_messages()` ДОЛЖЕН вернуть символы корректно декодированными
- **THEN** метод ДОЛЖЕН использовать кодировку UTF-8

### Requirement: DI registration of FileChatPersistence
Система ДОЛЖНА регистрировать `FileChatPersistence` в DI контейнере dishka как `ChatPersistencePort`. Регистрация ДОЛЖНА использовать `history_dir` из `ClientConfig`.

#### Scenario: Persistence registration
- **WHEN** DI контейнер создан
- **THEN** `ChatPersistencePort` ДОЛЖЕН разрешаться в экземпляр `FileChatPersistence`
- **THEN** экземпляр ДОЛЖЕН использовать `config.history_dir` или по умолчанию `~/.codelab/data/history`

#### Scenario: Persistence as singleton
- **WHEN** `ChatPersistencePort` запрашивается несколько раз из DI контейнера
- **THEN** ДОЛЖЕН возвращаться тот же экземпляр каждый раз
- **THEN** область ДОЛЖНА быть `Scope.APP`

### Requirement: ChatViewModel integration with persistence
Система ДОЛЖНА рефакторить `ChatViewModel` для использования `ChatPersistencePort` вместо прямого ввода-вывода файлов. ViewModel ДОЛЖНА делегировать все операции сохранения порту.

#### Scenario: ViewModel saves messages via port
- **WHEN** ChatViewModel необходимо сохранить сообщения
- **THEN** он ДОЛЖЕН вызвать `persistence.save_messages(session_id, messages, replay_updates)`
- **THEN** он НЕ ДОЛЖЕН выполнять прямой ввод-вывод файлов

#### Scenario: ViewModel loads messages via port
- **WHEN** ChatViewModel необходимо загрузить сообщения для сессии
- **THEN** он ДОЛЖЕН вызвать `persistence.load_messages(session_id)`
- **THEN** он НЕ ДОЛЖЕН выполнять прямой ввод-вывод файлов

#### Scenario: ViewModel handles persistence errors
- **WHEN** операции сохранения завершаются с ошибкой (ошибка диска, ошибка прав доступа)
- **THEN** ChatViewModel ДОЛЖЕН продолжить функционирование
- **THEN** ChatViewModel ДОЛЖЕН записать ошибку в лог
- **THEN** ChatViewModel ДОЛЖЕН использовать состояние в памяти как запасной вариант
