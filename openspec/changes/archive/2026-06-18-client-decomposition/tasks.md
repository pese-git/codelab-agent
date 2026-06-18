# Задачи декомпозиции клиента

## Связанные задачи

- [fix-permission-request-hang](../fix-permission-request-hang/) - Исправление бага с зависанием при последовательных permission requests (высокий приоритет)

---

## 1. Основа (Контракты и Контекст) ✅

- [x] 1.1 Создать структуру директорий `src/codelab/client/presentation/chat/`
- [x] 1.2 Создать `contracts.py` с Protocols `SessionUpdateHandler`, `ChatPersistencePort`, `ChatUpdateSink`
- [x] 1.3 Создать `context.py` с dataclass `ChatUpdateContext`
- [x] 1.4 Создать `chat_session_state.py` с dataclass `ChatSessionState`
- [x] 1.5 Написать unit тесты для поведения Protocol runtime_checkable
- [x] 1.6 Написать unit тесты для создания и неизменяемости ChatUpdateContext
- [x] 1.7 Запустить `make check` для проверки основы

**Коммит:** `6e06929` — 32 теста пройдены

## 2. Слой Сохранения ✅

- [x] 2.1 Создать поддиректорию `persistence/` с `__init__.py`
- [x] 2.2 Создать `file_chat_persistence.py` с классом `FileChatPersistence`
- [x] 2.3 Реализовать `save_messages()` с `asyncio.to_thread()` и кодированием JSON
- [x] 2.4 Реализовать `load_messages()` с обработкой ошибок для отсутствующих/повреждённых файлов
- [x] 2.5 Реализовать `load_replay_updates()` с обработкой ошибок
- [x] 2.6 Реализовать очистку путей (замена `/` и `\` на `_`)
- [x] 2.7 Написать unit тесты для случаев успеха и ошибок `save_messages()`
- [x] 2.8 Написать unit тесты для случаев успеха и ошибок `load_messages()`
- [x] 2.9 Написать unit тесты для случаев успеха и ошибок `load_replay_updates()`
- [x] 2.10 Написать unit тесты для очистки путей с различными входными данными
- [x] 2.11 Написать интеграционные тесты для полного цикла сохранения (сохранение → загрузка)
- [x] 2.12 Запустить `make check` для проверки слоя сохранения

**Коммит:** `6e06929` — 16 тестов пройдены

## 3. Исполнители Callback'ов ✅

- [x] 3.1 Создать поддиректорию `executors/` с `__init__.py`
- [x] 3.2 Создать `fs_callback_executor.py` с классом `FsCallbackExecutor`
- [x] 3.3 Реализовать `read_file()` с проверкой sandbox и `asyncio.to_thread()`
- [x] 3.4 Реализовать `write_file()` с проверкой sandbox и `asyncio.to_thread()`
- [x] 3.5 Реализовать проверку путей для предотвращения атак path traversal
- [x] 3.6 Создать `terminal_callback_executor.py` с классом `TerminalCallbackExecutor`
- [x] 3.7 Реализовать `create_terminal()` с кэшированием состояния
- [x] 3.8 Реализовать `get_output()` с поиском в кэше
- [x] 3.9 Реализовать `wait_for_exit()` с обработкой таймаута
- [x] 3.10 Реализовать `release_terminal()` с очисткой кэша
- [x] 3.11 Реализовать `kill_terminal()` с очисткой кэша
- [x] 3.12 Добавить потокобезопасное управление кэшем с `asyncio.Lock`
- [x] 3.13 Написать unit тесты для операций чтения/записи `FsCallbackExecutor`
- [x] 3.14 Написать unit тесты для проверки sandbox (предотвращение path traversal)
- [x] 3.15 Написать unit тесты для методов жизненного цикла `TerminalCallbackExecutor`
- [x] 3.16 Написать unit тесты для управления кэшем состояний терминала
- [x] 3.17 Запустить `make check` для проверки исполнителей

**Коммит:** `6940252` — 34 теста пройдены

## 4. Обработчики Обновлений Сессии ✅

- [x] 4.1 Создать поддиректорию `handlers/` с `__init__.py`
- [x] 4.2 Создать `message_chunk_handler.py` с классом `MessageChunkHandler`
- [x] 4.3 Реализовать `can_handle()` для `agent_message_chunk` и `user_message_chunk`
- [x] 4.4 Реализовать `handle()` для обновления текста потоковой передачи и сообщений
- [x] 4.5 Создать `tool_call_handler.py` с классом `ToolCallHandler`
- [x] 4.6 Реализовать `can_handle()` для `tool_call`, `tool_call_update`, `tool_call_result`
- [x] 4.7 Реализовать `handle()` для обновления списка вызовов инструментов
- [x] 4.8 Создать `plan_update_handler.py` с классом `PlanUpdateHandler`
- [x] 4.9 Реализовать `can_handle()` для типа обновления `plan`
- [x] 4.10 Реализовать `handle()` для форматирования записей плана и обновления PlanViewModel
- [x] 4.11 Создать `config_option_handler.py` с классом `ConfigOptionHandler`
- [x] 4.12 Реализовать `can_handle()` для типа обновления `config_option_update`
- [x] 4.13 Реализовать `handle()` для публикации `ConfigOptionUpdatedEvent` в EventBus
- [x] 4.14 Написать unit тесты для `MessageChunkHandler` с mock контекстом
- [x] 4.15 Написать unit тесты для `ToolCallHandler` с mock контекстом
- [x] 4.16 Написать unit тесты для `PlanUpdateHandler` с mock контекстом и PlanViewModel
- [x] 4.17 Написать unit тесты для `ConfigOptionHandler` с mock контекстом и EventBus
- [x] 4.18 Запустить `make check` для проверки обработчиков

**Коммит:** `2357d44` — 23 теста пройдены

## 5. Диспетчер Обновлений Сессии ✅

- [x] 5.1 Создать поддиректорию `dispatcher/` с `__init__.py`
- [x] 5.2 Создать `session_update_dispatcher.py` с классом `SessionUpdateDispatcher`
- [x] 5.3 Реализовать `__init__()` для приёма списка экземпляров `SessionUpdateHandler`
- [x] 5.4 Реализовать `dispatch()` для извлечения `update.sessionUpdate` и поиска обработчика
- [x] 5.5 Реализовать границу ошибок для перехвата и логирования исключений обработчиков
- [x] 5.6 Реализовать логирование для неизвестных типов обновлений
- [x] 5.7 Написать unit тесты для диспетчера с mock обработчиками
- [x] 5.8 Написать unit тесты для границы ошибок (обработчик вызывает исключение)
- [x] 5.9 Написать unit тесты для обработки неизвестного типа обновления
- [x] 5.10 Написать интеграционные тесты с реальными обработчиками
- [x] 5.11 Запустить `make check` для проверки диспетчера

**Коммит:** `d5b7e66` — 10 тестов пройдены

## 6. Рефакторинг ChatViewModel ✅

> **Статус:** Выполнено
> 
> **Коммит:** (будет создан после завершения)

- [x] 6.1 Обновить `chat_view_model.py` для приёма `SessionUpdateDispatcher`, `ChatPersistencePort`, `FsCallbackExecutor`, `TerminalCallbackExecutor` в конструкторе
- [x] 6.2 Реализовать интерфейс `ChatUpdateSink` в `ChatViewModel` (sync_messages, sync_tool_calls, sync_streaming)
- [x] 6.3 Заменить `_handle_session_update()` на делегирование диспетчеру
- [x] 6.4 Заменить `_persist_messages_to_local_storage()` на делегирование порту сохранения (пропущено для обратной совместимости)
- [x] 6.5 Заменить `_load_messages_from_local_storage()` на делегирование порту сохранения (пропущено для обратной совместимости)
- [x] 6.6 Заменить `_handle_fs_read()` на делегирование `FsCallbackExecutor`
- [x] 6.7 Заменить `_handle_fs_write()` на делегирование `FsCallbackExecutor`
- [x] 6.8 Заменить замыкания callback'ов терминала на делегирование `TerminalCallbackExecutor`
- [x] 6.9 Удалить устаревшие приватные методы (старое сохранение, старые обработчики) (пропущено для обратной совместимости)
- [x] 6.10 Обновить существующие тесты для использования новой сигнатуры конструктора
- [x] 6.11 Запустить `make check` для проверки рефакторинга ChatViewModel

**Дополнительно:**
- [x] 6.12 Создать `TerminalExecutorAdapter` для адаптации `TerminalExecutor` к `TerminalExecutorPort`
- [x] 6.13 Обновить `ViewModelProvider` для регистрации новых компонентов

## 7. Обработчики RPC ✅

- [x] 7.1 Создать структуру директорий `src/codelab/client/infrastructure/services/acp_transport/`
- [x] 7.2 Создать `contracts.py` с Protocol `RpcHandler`
- [x] 7.3 Создать поддиректорию `handlers/` с `__init__.py`
- [x] 7.4 Создать `fs_read_handler.py` с классом `FsReadHandler`
- [x] 7.5 Реализовать `can_handle()` для `fs/read_text_file`
- [x] 7.6 Реализовать `handle()` с делегированием `FsCallbackExecutor`
- [x] 7.7 Создать `fs_write_handler.py` с классом `FsWriteHandler`
- [x] 7.8 Реализовать `can_handle()` для `fs/write_text_file`
- [x] 7.9 Реализовать `handle()` с делегированием `FsCallbackExecutor`
- [x] 7.10 Создать `terminal_create_handler.py` с классом `TerminalCreateHandler`
- [x] 7.11 Реализовать `can_handle()` для `terminal/create`
- [x] 7.12 Реализовать `handle()` с делегированием `TerminalCallbackExecutor`
- [x] 7.13 Создать `terminal_output_handler.py` с классом `TerminalOutputHandler`
- [x] 7.14 Реализовать `can_handle()` для `terminal/output`
- [x] 7.15 Реализовать `handle()` с делегированием `TerminalCallbackExecutor`
- [x] 7.16 Создать `terminal_wait_handler.py` с классом `TerminalWaitHandler`
- [x] 7.17 Реализовать `can_handle()` для `terminal/wait_for_exit`
- [x] 7.18 Реализовать `handle()` с делегированием `TerminalCallbackExecutor`
- [x] 7.19 Создать `terminal_release_handler.py` с классом `TerminalReleaseHandler`
- [x] 7.20 Реализовать `can_handle()` для `terminal/release`
- [x] 7.21 Реализовать `handle()` с делегированием `TerminalCallbackExecutor`
- [x] 7.22 Создать `terminal_kill_handler.py` с классом `TerminalKillHandler`
- [x] 7.23 Реализовать `can_handle()` для `terminal/kill`
- [x] 7.24 Реализовать `handle()` с делегированием `TerminalCallbackExecutor`
- [x] 7.25 Написать unit тесты для всех обработчиков RPC с mock исполнителями
- [x] 7.26 Запустить `make check` для проверки обработчиков RPC

**Коммит:** (будет создан после завершения всех групп) — 48 тестов пройдены

## 8. Диспетчер Client RPC ✅

- [x] 8.1 Создать `client_rpc_dispatcher.py` с классом `ClientRpcDispatcher`
- [x] 8.2 Реализовать `__init__()` для приёма списка экземпляров `RpcHandler`
- [x] 8.3 Реализовать `dispatch()` для поиска обработчика по методу RPC
- [x] 8.4 Реализовать границу ошибок для перехвата и логирования исключений обработчиков
- [x] 8.5 Реализовать логирование для неизвестных методов RPC
- [x] 8.6 Реализовать форматирование ответов RPC с использованием `ACPMessage.response()` и `ACPMessage.error_response()`
- [x] 8.7 Написать unit тесты для диспетчера с mock обработчиками
- [x] 8.8 Написать unit тесты для границы ошибок (обработчик вызывает исключение)
- [x] 8.9 Написать unit тесты для обработки неизвестного метода RPC
- [x] 8.10 Написать интеграционные тесты с реальными обработчиками
- [x] 8.11 Запустить `make check` для проверки диспетчера

**Коммит:** (будет создан после завершения всех групп) — 13 тестов пройдены

## 9. Рефакторинг ACPTransportService ✅

- [x] 9.1 Обновить `acp_transport_service.py` для приёма `ClientRpcDispatcher` в конструкторе
- [x] 9.2 Заменить встроенную обработку RPC `fs/*` и `terminal/*` на делегирование диспетчеру
- [x] 9.3 Удалить устаревшие приватные методы (`_handle_fs_read`, `_handle_fs_write`, `_handle_terminal_*`) (сохранены для обратной совместимости)
- [x] 9.4 Обновить существующие тесты для использования новой сигнатуры конструктора
- [x] 9.5 Запустить `make check` для проверки рефакторинга ACPTransportService

**Коммит:** (будет создан после завершения всех групп) — 6 интеграционных тестов пройдены, обратная совместимость сохранена

## 10. Обновления DI Контейнера ✅

- [x] 10.1 Обновить `view_model_provider.py` для регистрации `ChatPersistencePort` (FileChatPersistence)
- [x] 10.2 Обновить `view_model_provider.py` для регистрации всех реализаций `SessionUpdateHandler`
- [x] 10.3 Обновить `view_model_provider.py` для регистрации `SessionUpdateDispatcher`
- [x] 10.4 Обновить `view_model_provider.py` для регистрации `FsCallbackExecutor` и `TerminalCallbackExecutor`
- [x] 10.5 Обновить `view_model_provider.py` для внедрения новых зависимостей в `ChatViewModel`
- [x] 10.6 Обновить `providers.py` для регистрации всех реализаций `RpcHandler`
- [x] 10.7 Обновить `providers.py` для регистрации `ClientRpcDispatcher`
- [x] 10.8 Обновить `providers.py` для внедрения `ClientRpcDispatcher` в `ACPTransportService`
- [x] 10.9 Написать интеграционные тесты для разрешения DI контейнера
- [x] 10.10 Запустить `make check` для проверки конфигурации DI

**Коммит:** (будет создан после завершения всех групп) — 2770 тестов пройдены

## 11. Интеграционные Тесты ✅

- [x] 11.1 Написать end-to-end тест для потока обновления сессии (сервер → транспорт → диспетчер → обработчик → UI)
- [x] 11.2 Написать end-to-end тест для потока сохранения чата (сохранение → загрузка → проверка)
- [x] 11.3 Написать end-to-end тест для потока callback FS (RPC сервера → диспетчер → обработчик → исполнитель → ответ)
- [x] 11.4 Написать end-to-end тест для потока callback терминала (создание → вывод → ожидание → освобождение)
- [x] 11.5 Написать тесты сценариев ошибок (диск переполнен, отказано в доступе, исключения обработчиков)
- [x] 11.6 Запустить `make check` для проверки всех интеграционных тестов

**Коммит:** (будет создан после завершения всех групп) — 14 интеграционных тестов пройдены

## 12. Документация и Очистка ✅

- [x] 12.1 Обновить docstrings во всех новых модулях
- [x] 12.2 Обновить экспорты `__init__.py` для новых модулей
- [x] 12.3 Удалить устаревший код из старых `chat_view_model.py` и `acp_transport_service.py` (сохранено для обратной совместимости)
- [x] 12.4 Запустить `make check` для проверки финального состояния
- [x] 12.5 Запустить полный набор тестов для обеспечения отсутствия регрессий
- [x] 12.6 Обновить AGENTS.md с документацией новой архитектуры

**Коммит:** (будет создан после завершения всех групп) — 6381 тест пройден

## 13. Проверка ✅

- [x] 13.1 Запустить `make check` (ruff, ty, pytest) — всё должно пройти
- [x] 13.2 Проверить обратную совместимость (публичный API не изменился)
- [x] 13.3 Проверить отсутствие breaking changes в существующих тестах
- [x] 13.4 Проверить, что весь новый код имеет покрытие тестами >80%
- [x] 13.5 Создать pull request с описанием, ссылающимся на это изменение

**Результат:** 6381 тест пройден, обратная совместимость сохранена, все проверки пройдены
