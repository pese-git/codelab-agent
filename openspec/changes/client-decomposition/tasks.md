## 1. Основа (Контракты и Контекст)

- [ ] 1.1 Создать структуру директорий `src/codelab/client/presentation/chat/`
- [ ] 1.2 Создать `contracts.py` с Protocols `SessionUpdateHandler`, `ChatPersistencePort`, `ChatUpdateSink`
- [ ] 1.3 Создать `context.py` с dataclass `ChatUpdateContext`
- [ ] 1.4 Создать `chat_session_state.py` с dataclass `ChatSessionState`
- [ ] 1.5 Написать unit тесты для поведения Protocol runtime_checkable
- [ ] 1.6 Написать unit тесты для создания и неизменяемости ChatUpdateContext
- [ ] 1.7 Запустить `make check` для проверки основы

## 2. Слой Сохранения

- [ ] 2.1 Создать поддиректорию `persistence/` с `__init__.py`
- [ ] 2.2 Создать `file_chat_persistence.py` с классом `FileChatPersistence`
- [ ] 2.3 Реализовать `save_messages()` с `asyncio.to_thread()` и кодированием JSON
- [ ] 2.4 Реализовать `load_messages()` с обработкой ошибок для отсутствующих/повреждённых файлов
- [ ] 2.5 Реализовать `load_replay_updates()` с обработкой ошибок
- [ ] 2.6 Реализовать очистку путей (замена `/` и `\` на `_`)
- [ ] 2.7 Написать unit тесты для случаев успеха и ошибок `save_messages()`
- [ ] 2.8 Написать unit тесты для случаев успеха и ошибок `load_messages()`
- [ ] 2.9 Написать unit тесты для случаев успеха и ошибок `load_replay_updates()`
- [ ] 2.10 Написать unit тесты для очистки путей с различными входными данными
- [ ] 2.11 Написать интеграционные тесты для полного цикла сохранения (сохранение → загрузка)
- [ ] 2.12 Запустить `make check` для проверки слоя сохранения

## 3. Исполнители Callback'ов

- [ ] 3.1 Создать поддиректорию `executors/` с `__init__.py`
- [ ] 3.2 Создать `fs_callback_executor.py` с классом `FsCallbackExecutor`
- [ ] 3.3 Реализовать `read_file()` с проверкой sandbox и `asyncio.to_thread()`
- [ ] 3.4 Реализовать `write_file()` с проверкой sandbox и `asyncio.to_thread()`
- [ ] 3.5 Реализовать проверку путей для предотвращения атак path traversal
- [ ] 3.6 Создать `terminal_callback_executor.py` с классом `TerminalCallbackExecutor`
- [ ] 3.7 Реализовать `create_terminal()` с кэшированием состояния
- [ ] 3.8 Реализовать `get_output()` с поиском в кэше
- [ ] 3.9 Реализовать `wait_for_exit()` с обработкой таймаута
- [ ] 3.10 Реализовать `release_terminal()` с очисткой кэша
- [ ] 3.11 Реализовать `kill_terminal()` с очисткой кэша
- [ ] 3.12 Добавить потокобезопасное управление кэшем с `asyncio.Lock`
- [ ] 3.13 Написать unit тесты для операций чтения/записи `FsCallbackExecutor`
- [ ] 3.14 Написать unit тесты для проверки sandbox (предотвращение path traversal)
- [ ] 3.15 Написать unit тесты для методов жизненного цикла `TerminalCallbackExecutor`
- [ ] 3.16 Написать unit тесты для управления кэшем состояний терминала
- [ ] 3.17 Запустить `make check` для проверки исполнителей

## 4. Обработчики Обновлений Сессии

- [ ] 4.1 Создать поддиректорию `handlers/` с `__init__.py`
- [ ] 4.2 Создать `message_chunk_handler.py` с классом `MessageChunkHandler`
- [ ] 4.3 Реализовать `can_handle()` для `agent_message_chunk` и `user_message_chunk`
- [ ] 4.4 Реализовать `handle()` для обновления текста потоковой передачи и сообщений
- [ ] 4.5 Создать `tool_call_handler.py` с классом `ToolCallHandler`
- [ ] 4.6 Реализовать `can_handle()` для `tool_call`, `tool_call_update`, `tool_call_result`
- [ ] 4.7 Реализовать `handle()` для обновления списка вызовов инструментов
- [ ] 4.8 Создать `plan_update_handler.py` с классом `PlanUpdateHandler`
- [ ] 4.9 Реализовать `can_handle()` для типа обновления `plan`
- [ ] 4.10 Реализовать `handle()` для форматирования записей плана и обновления PlanViewModel
- [ ] 4.11 Создать `config_option_handler.py` с классом `ConfigOptionHandler`
- [ ] 4.12 Реализовать `can_handle()` для типа обновления `config_option_update`
- [ ] 4.13 Реализовать `handle()` для публикации `ConfigOptionUpdatedEvent` в EventBus
- [ ] 4.14 Написать unit тесты для `MessageChunkHandler` с mock контекстом
- [ ] 4.15 Написать unit тесты для `ToolCallHandler` с mock контекстом
- [ ] 4.16 Написать unit тесты для `PlanUpdateHandler` с mock контекстом и PlanViewModel
- [ ] 4.17 Написать unit тесты для `ConfigOptionHandler` с mock контекстом и EventBus
- [ ] 4.18 Запустить `make check` для проверки обработчиков

## 5. Диспетчер Обновлений Сессии

- [ ] 5.1 Создать поддиректорию `dispatcher/` с `__init__.py`
- [ ] 5.2 Создать `session_update_dispatcher.py` с классом `SessionUpdateDispatcher`
- [ ] 5.3 Реализовать `__init__()` для приёма списка экземпляров `SessionUpdateHandler`
- [ ] 5.4 Реализовать `dispatch()` для извлечения `update.sessionUpdate` и поиска обработчика
- [ ] 5.5 Реализовать границу ошибок для перехвата и логирования исключений обработчиков
- [ ] 5.6 Реализовать логирование для неизвестных типов обновлений
- [ ] 5.7 Написать unit тесты для диспетчера с mock обработчиками
- [ ] 5.8 Написать unit тесты для границы ошибок (обработчик вызывает исключение)
- [ ] 5.9 Написать unit тесты для обработки неизвестного типа обновления
- [ ] 5.10 Написать интеграционные тесты с реальными обработчиками
- [ ] 5.11 Запустить `make check` для проверки диспетчера

## 6. Рефакторинг ChatViewModel

- [ ] 6.1 Обновить `chat_view_model.py` для приёма `SessionUpdateDispatcher`, `ChatPersistencePort`, `FsCallbackExecutor`, `TerminalCallbackExecutor` в конструкторе
- [ ] 6.2 Реализовать интерфейс `ChatUpdateSink` в `ChatViewModel` (sync_messages, sync_tool_calls, sync_streaming)
- [ ] 6.3 Заменить `_handle_session_update()` на делегирование диспетчеру
- [ ] 6.4 Заменить `_persist_messages_to_local_storage()` на делегирование порту сохранения
- [ ] 6.5 Заменить `_load_messages_from_local_storage()` на делегирование порту сохранения
- [ ] 6.6 Заменить `_handle_fs_read()` на делегирование `FsCallbackExecutor`
- [ ] 6.7 Заменить `_handle_fs_write()` на делегирование `FsCallbackExecutor`
- [ ] 6.8 Заменить замыкания callback'ов терминала на делегирование `TerminalCallbackExecutor`
- [ ] 6.9 Удалить устаревшие приватные методы (старое сохранение, старые обработчики)
- [ ] 6.10 Обновить существующие тесты для использования новой сигнатуры конструктора
- [ ] 6.11 Запустить `make check` для проверки рефакторинга ChatViewModel

## 7. Обработчики RPC

- [ ] 7.1 Создать структуру директорий `src/codelab/client/infrastructure/services/acp_transport/`
- [ ] 7.2 Создать `contracts.py` с Protocol `RpcHandler`
- [ ] 7.3 Создать поддиректорию `handlers/` с `__init__.py`
- [ ] 7.4 Создать `fs_read_handler.py` с классом `FsReadHandler`
- [ ] 7.5 Реализовать `can_handle()` для `fs/read_text_file`
- [ ] 7.6 Реализовать `handle()` с делегированием `FsCallbackExecutor`
- [ ] 7.7 Создать `fs_write_handler.py` с классом `FsWriteHandler`
- [ ] 7.8 Реализовать `can_handle()` для `fs/write_text_file`
- [ ] 7.9 Реализовать `handle()` с делегированием `FsCallbackExecutor`
- [ ] 7.10 Создать `terminal_create_handler.py` с классом `TerminalCreateHandler`
- [ ] 7.11 Реализовать `can_handle()` для `terminal/create`
- [ ] 7.12 Реализовать `handle()` с делегированием `TerminalCallbackExecutor`
- [ ] 7.13 Создать `terminal_output_handler.py` с классом `TerminalOutputHandler`
- [ ] 7.14 Реализовать `can_handle()` для `terminal/output`
- [ ] 7.15 Реализовать `handle()` с делегированием `TerminalCallbackExecutor`
- [ ] 7.16 Создать `terminal_wait_handler.py` с классом `TerminalWaitHandler`
- [ ] 7.17 Реализовать `can_handle()` для `terminal/wait_for_exit`
- [ ] 7.18 Реализовать `handle()` с делегированием `TerminalCallbackExecutor`
- [ ] 7.19 Создать `terminal_release_handler.py` с классом `TerminalReleaseHandler`
- [ ] 7.20 Реализовать `can_handle()` для `terminal/release`
- [ ] 7.21 Реализовать `handle()` с делегированием `TerminalCallbackExecutor`
- [ ] 7.22 Создать `terminal_kill_handler.py` с классом `TerminalKillHandler`
- [ ] 7.23 Реализовать `can_handle()` для `terminal/kill`
- [ ] 7.24 Реализовать `handle()` с делегированием `TerminalCallbackExecutor`
- [ ] 7.25 Написать unit тесты для всех обработчиков RPC с mock исполнителями
- [ ] 7.26 Запустить `make check` для проверки обработчиков RPC

## 8. Диспетчер Client RPC

- [ ] 8.1 Создать `client_rpc_dispatcher.py` с классом `ClientRpcDispatcher`
- [ ] 8.2 Реализовать `__init__()` для приёма списка экземпляров `RpcHandler`
- [ ] 8.3 Реализовать `dispatch()` для поиска обработчика по методу RPC
- [ ] 8.4 Реализовать границу ошибок для перехвата и логирования исключений обработчиков
- [ ] 8.5 Реализовать логирование для неизвестных методов RPC
- [ ] 8.6 Реализовать форматирование ответов RPC с использованием `ACPMessage.response()` и `ACPMessage.error_response()`
- [ ] 8.7 Написать unit тесты для диспетчера с mock обработчиками
- [ ] 8.8 Написать unit тесты для границы ошибок (обработчик вызывает исключение)
- [ ] 8.9 Написать unit тесты для обработки неизвестного метода RPC
- [ ] 8.10 Написать интеграционные тесты с реальными обработчиками
- [ ] 8.11 Запустить `make check` для проверки диспетчера

## 9. Рефакторинг ACPTransportService

- [ ] 9.1 Обновить `acp_transport_service.py` для приёма `ClientRpcDispatcher` в конструкторе
- [ ] 9.2 Заменить встроенную обработку RPC `fs/*` и `terminal/*` на делегирование диспетчеру
- [ ] 9.3 Удалить устаревшие приватные методы (`_handle_fs_read`, `_handle_fs_write`, `_handle_terminal_*`)
- [ ] 9.4 Обновить существующие тесты для использования новой сигнатуры конструктора
- [ ] 9.5 Запустить `make check` для проверки рефакторинга ACPTransportService

## 10. Обновления DI Контейнера

- [ ] 10.1 Обновить `view_model_provider.py` для регистрации `ChatPersistencePort` (FileChatPersistence)
- [ ] 10.2 Обновить `view_model_provider.py` для регистрации всех реализаций `SessionUpdateHandler`
- [ ] 10.3 Обновить `view_model_provider.py` для регистрации `SessionUpdateDispatcher`
- [ ] 10.4 Обновить `view_model_provider.py` для регистрации `FsCallbackExecutor` и `TerminalCallbackExecutor`
- [ ] 10.5 Обновить `view_model_provider.py` для внедрения новых зависимостей в `ChatViewModel`
- [ ] 10.6 Обновить `providers.py` для регистрации всех реализаций `RpcHandler`
- [ ] 10.7 Обновить `providers.py` для регистрации `ClientRpcDispatcher`
- [ ] 10.8 Обновить `providers.py` для внедрения `ClientRpcDispatcher` в `ACPTransportService`
- [ ] 10.9 Написать интеграционные тесты для разрешения DI контейнера
- [ ] 10.10 Запустить `make check` для проверки конфигурации DI

## 11. Интеграционные Тесты

- [ ] 11.1 Написать end-to-end тест для потока обновления сессии (сервер → транспорт → диспетчер → обработчик → UI)
- [ ] 11.2 Написать end-to-end тест для потока сохранения чата (сохранение → загрузка → проверка)
- [ ] 11.3 Написать end-to-end тест для потока callback FS (RPC сервера → диспетчер → обработчик → исполнитель → ответ)
- [ ] 11.4 Написать end-to-end тест для потока callback терминала (создание → вывод → ожидание → освобождение)
- [ ] 11.5 Написать тесты сценариев ошибок (диск переполнен, отказано в доступе, исключения обработчиков)
- [ ] 11.6 Запустить `make check` для проверки всех интеграционных тестов

## 12. Документация и Очистка

- [ ] 12.1 Обновить docstrings во всех новых модулях
- [ ] 12.2 Обновить экспорты `__init__.py` для новых модулей
- [ ] 12.3 Удалить устаревший код из старых `chat_view_model.py` и `acp_transport_service.py`
- [ ] 12.4 Запустить `make check` для проверки финального состояния
- [ ] 12.5 Запустить полный набор тестов для обеспечения отсутствия регрессий
- [ ] 12.6 Обновить AGENTS.md с документацией новой архитектуры

## 13. Проверка

- [ ] 13.1 Запустить `make check` (ruff, ty, pytest) — всё должно пройти
- [ ] 13.2 Проверить обратную совместимость (публичный API не изменился)
- [ ] 13.3 Проверить отсутствие breaking changes в существующих тестах
- [ ] 13.4 Проверить, что весь новый код имеет покрытие тестами >80%
- [ ] 13.5 Создать pull request с описанием, ссылающимся на это изменение
