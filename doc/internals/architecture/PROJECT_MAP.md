# Карта проекта CodeLab

> **ACP (Agent Client Protocol)** — унифицированная реализация сервера агента и клиента в одном Python-пакете.
>
> **Дата генерации:** 2026-06-13 | **Ветка:** feature/agent

---

## Оглавление

1. [Общая структура](#общая-структура)
2. [Сервер (`codelab/server/`)](#сервер-codelabserver)
3. [Клиент (`codelab/client/`)](#клиент-codelabclient)
4. [Общие модули (`codelab/shared/`)](#общие-модули-codelabshared)
5. [Тесты (`tests/`)](#тесты-tests)
6. [Ключевые потоки данных](#ключевые-потоки-данных)
7. [DI-контейнер (Dishka)](#di-контейнер-dishka)
8. [Транспортный слой](#транспортный-слой)
9. [Статистика](#статистика)

---

## Общая структура

```
codelab-agent/
├── codelab/                          # Основной Python-пакет
│   ├── src/codelab/
│   │   ├── shared/                   # Общие модули (server + client)
│   │   ├── server/                   # Серверная часть (агент)
│   │   └── client/                   # Клиентская часть (TUI)
│   └── tests/                        # Тесты (client + server + shared)
├── ARCHITECTURE.md                   # Архитектурная документация
├── CHANGELOG.md                      # Журнал изменений
├── AGENTS.md                         # Инструкции для AI-ассистентов
├── Makefile                          # Команды проверки
├── doc/                              # Спецификации протоколов
└── .opencode/                        # Конфигурация opencode
```

---

## Сервер (`codelab/server/`)

### Транспортный слой

| Файл | Описание |
|------|----------|
| `transport/base.py` | Протокол `AcpServerTransport` (run, send, close) |
| `transport/stdio.py` | StdioServerTransport — stdin/stdout, background prompt execution |
| `transport/stdio_runner.py` | `run_stdio_server()` — запуск с DI, callbacks из protocol |
| `transport/websocket.py` | WebSocketTransport — aiohttp, deferred prompt, cleanup |

### Протокол (Protocol Layer)

| Файл | Описание |
|------|----------|
| `protocol/core.py` | `ACPProtocol` — диспетчер методов, `handle_and_process`, background tool |
| `protocol/state.py` | Dataclasses: `SessionState`, `ProtocolOutcome`, `PendingToolExecution` |
| `protocol/mode.py` | Режимы: plan, standard, bypass + валидация |
| `protocol/stop_reasons.py` | Enum `StopReason`: end_turn, max_tokens, cancelled, ... |
| `protocol/session_factory.py` | Фабрика создания сессий |
| `protocol/session_runtime.py` | Runtime-данные сессии |
| `protocol/pending_registry.py` | Реестр pending запросов |

#### Обработчики методов (handlers/)

| Файл | Методы ACP |
|------|------------|
| `handlers/auth.py` | `authenticate`, `initialize` |
| `handlers/session.py` | `session/new`, `session/load`, `session/list` |
| `handlers/prompt.py` | `session/prompt`, `session/cancel`, turn completion |
| `handlers/prompt_orchestrator.py` | Главный координатор prompt-turn |
| `handlers/permissions.py` | `session/request_permission` |
| `handlers/permission_manager.py` | Менеджер политик разрешений |
| `handlers/global_policy_manager.py` | Глобальные политики разрешений |
| `handlers/config.py` | `session/set_config_option`, `session/set_mode` |
| `handlers/config_option_builder.py` | Построитель опций конфигурации |
| `handlers/client_rpc_handler.py` | Обработка RPC вызовов к клиенту |
| `handlers/tool_call_handler.py` | Обработка tool calls |
| `handlers/plan_builder.py` | Построение планов агента |
| `handlers/state_manager.py` | Управление состоянием сессии |
| `handlers/turn_lifecycle_manager.py` | Жизненный цикл turn |
| `handlers/replay_manager.py` | Воспроизведение истории сессии |

#### Pipeline (handlers/pipeline/)

| Файл | Описание |
|------|----------|
| `pipeline/stages/agent_loop.py` | `AgentLoop` — унифицированный цикл итераций LLM |
| `pipeline/stages/llm_loop.py` | `LLMLoopStage` — адаптер pipeline → AgentLoop |
| `pipeline/stages/directives.py` | Обработка prompt directives |

#### Slash Commands (handlers/slash_commands/)

| Файл | Описание |
|------|----------|
| `slash_commands/builtin/` | Встроенные команды (mode, help, ...) |
| `slash_commands/router.py` | Маршрутизация slash-команд |

#### Стратегии (handlers/strategies/)

| Файл | Описание |
|------|----------|
| `strategies/single.py` | SingleStrategy — один агент на сессию |

#### Middleware (middleware/)

| Файл | Описание |
|------|----------|
| `middleware/message_trace.py` | Трассировка сообщений |

#### Prompt Handlers (prompt_handlers/)

| Файл | Описание |
|------|----------|
| `prompt_handlers/validator.py` | Валидация промптов |

#### Content (content/)

| Файл | Описание |
|------|----------|
| `content/extractor.py` | `ContentExtractor` — извлечение content из tool results |
| `content/validator.py` | `ContentValidator` — валидация по ACP spec |
| `content/formatter.py` | `ContentFormatter` — форматирование для LLM |

### Агент (Agent Layer)

| Файл | Описание |
|------|----------|
| `agent/base.py` | `LLMAgent(ABC)` — базовый интерфейс агента |
| `agent/execution_engine.py` | `ExecutionEngine` — композиция HistoryBuilder, ToolFilter, LLMAdapter, MessageSanitizer, PlanExtractor, ContextCompactor |
| `agent/llm_adapter.py` | `LLMAdapter` — адаптер LLMProvider (замена NaiveAgent) |
| `agent/factory.py` | `AgentFactory` — создание LLMAdapter per-agent |
| `agent/registry.py` | `AgentRegistry` — регистрация агентов с hot reload |
| `agent/history_builder.py` | `HistoryBuilder` — конвертация session.history → list[LLMMessage] |
| `agent/tool_filter.py` | `ToolFilter` — фильтрация инструментов по client capabilities + MCP |
| `agent/message_sanitizer.py` | `MessageSanitizer` — восстановление orphaned tool calls |
| `agent/context_compactor.py` | `ContextCompactor` — сжатие контекста при превышении лимита |
| `agent/plan_extractor.py` | `PlanExtractor` — извлечение планов из ответов LLM |
| `agent/system_prompt_builder.py` | `SystemPromptBuilder` — построение системного промпта |

> ~~`agent/orchestrator.py`~~ — `AgentOrchestrator` удалён, заменён на `ExecutionEngine`
> ~~`agent/naive.py`~~ — `NaiveAgent` удалён, заменён на `LLMAdapter`
> ~~`agent/state.py`~~ — `OrchestratorConfig` удалён, конфигурация через TOML/Markdown

#### Конфигурация агентов (agent/config/)

| Файл | Описание |
|------|----------|
| `config/models.py` | Модели конфигурации агентов |
| `config/loader.py` | Загрузчик конфигурации |
| `config/resolver.py` | Разрешение конфигурации |

#### Контракты (agent/contracts/)

| Файл | Описание |
|------|----------|
| `contracts/base.py` | Базовые контракты агентов |

#### Event Bus (agent/event_bus/)

| Файл | Описание |
|------|----------|
| `event_bus/bus.py` | Шина событий |
| `event_bus/routing.py` | Маршрутизация событий |
| `event_bus/abstract.py` | Абстрактные интерфейсы |

#### Стратегии (agent/strategies/)

| Файл | Описание |
|------|----------|
| `strategies/base.py` | `LLMCallStrategy` Protocol |
| `strategies/descriptor.py` | `StrategyDescriptor` + `StrategyDependencies` |
| `strategies/registry.py` | `StrategyRegistry` — реестр стратегий |
| `strategies/dispatcher.py` | `StrategyDispatcher` — маршрутизация (priority chain + fallback) |

### LLM провайдеры (llm/)

| Файл | Описание |
|------|----------|
| `llm/base.py` | `LLMProvider`, `LLMConfig`, `LLMCapabilities` |
| `llm/models.py` | `CompletionRequest`, `CompletionResponse`, `LLMToolCall`, `StopReason` |
| `llm/registry.py` | `LLMRegistry` — реестр провайдеров |
| `llm/resolver.py` | Разрешение провайдера |
| `llm/errors.py` | Исключения LLM |
| `llm/events.py` | События LLM |
| `llm/mock_provider.py` | Mock-провайдер для тестирования |

#### Провайдеры (llm/providers/)

| Файл | Провайдер |
|------|-----------|
| `providers/openai.py` | OpenAI |
| `providers/anthropic.py` | Anthropic |
| `providers/openrouter.py` | OpenRouter |
| `providers/openai_compatible.py` | OpenAI-compatible |
| `providers/ollama.py` | Ollama |
| `providers/lmstudio.py` | LMStudio |
| `providers/zen.py` | Zen |
| `providers/go.py` | Go |

#### Fallback (llm/fallback/)

| Файл | Описание |
|------|----------|
| `fallback/base.py` | Базовый класс fallback |
| `fallback/sequential.py` | Последовательный fallback |
| `fallback/orchestrator.py` | Оркестратор fallback |
| `fallback/circuit_breaker.py` | Circuit breaker |
| `fallback/config.py` | Конфигурация fallback |
| `fallback/factory.py` | Фабрика fallback |

#### Discovery (llm/discovery/)

| Файл | Описание |
|------|----------|
| `discovery/base.py` | Базовый класс discovery |
| `discovery/static.py` | Статическое обнаружение моделей |
| `discovery/config.py` | Конфигурация discovery |

#### Telemetry (llm/telemetry/)

| Файл | Описание |
|------|----------|
| `telemetry/base.py` | Базовый класс telemetry |
| `telemetry/noop.py` | No-op telemetry |

### Инструменты (tools/)

| Файл | Описание |
|------|----------|
| `tools/base.py` | `ToolDefinition`, `ToolExecutor`, `ToolExecutionResult` |
| `tools/registry.py` | `ToolRegistry` — регистрация и управление |
| `tools/mapping.py` | Маппинг ACP ↔ LLM имён (fs/read → fs_read) |

#### Определения (tools/definitions/)

| Файл | Описание |
|------|----------|
| `definitions/filesystem.py` | `fs/read_text_file`, `fs/write_text_file` |
| `definitions/terminal.py` | `terminal/create`, `terminal/wait_for_exit`, `terminal/release` |
| `definitions/plan.py` | Инструменты для планирования |

#### Исполнители (tools/executors/)

| Файл | Описание |
|------|----------|
| `executors/base.py` | Базовый исполнитель |
| `executors/filesystem_executor.py` | Файловые операции |
| `executors/terminal_executor.py` | Терминальные операции |
| `executors/mcp_executor.py` | MCP-инструменты |
| `executors/plan_executor.py` | Исполнение планов |

#### Интеграции (tools/integrations/)

| Файл | Описание |
|------|----------|
| `integrations/client_rpc_bridge.py` | Мост для Agent→Client RPC вызовов |
| `integrations/permission_checker.py` | Проверка разрешений |

### MCP интеграция (mcp/)

| Файл | Описание |
|------|----------|
| `mcp/models.py` | Pydantic модели MCP протокола |
| `mcp/transport.py` | StdioTransport для MCP серверов |
| `mcp/transport_factory.py` | Фабрика транспортов |
| `mcp/client.py` | `MCPClient` — жизненный цикл MCP |
| `mcp/manager.py` | `MCPManager` — управление несколькими серверами |
| `mcp/tool_adapter.py` | `MCPToolAdapter` — интеграция с ToolRegistry |
| `mcp/content_mapper.py` | Маппинг контента MCP |
| `mcp/prompt_mapper.py` | Маппинг промптов MCP |
| `mcp/resource_mapper.py` | Маппинг ресурсов MCP |

### Хранилище (storage/)

| Файл | Описание |
|------|----------|
| `storage/base.py` | `SessionStorage(ABC)` — интерфейс |
| `storage/memory.py` | `InMemoryStorage` — development |
| `storage/json_file.py` | `JsonFileStorage` — production с persistence |
| `storage/cached.py` | Кэшированное хранилище |
| `storage/global_policy_storage.py` | Хранилище глобальных политик |

### Client RPC (client_rpc/)

| Файл | Описание |
|------|----------|
| `client_rpc/service.py` | `ClientRPCService` — асинхронные вызовы к клиенту |
| `client_rpc/models.py` | Модели данных RPC |
| `client_rpc/exceptions.py` | Исключения RPC |

### Observability (observability/)

| Файл | Описание |
|------|----------|
| `observability/tracer.py` | Трассировка |
| `observability/metrics_tracker.py` | Метрики |
| `observability/event_timeline.py` | Временная шкала событий |

#### Exporters (observability/exporters/)

| Файл | Описание |
|------|----------|
| `exporters/file_event_exporter.py` | Экспорт событий в файл |
| `exporters/file_span_exporter.py` | Экспорт span'ов в файл |
| `exporters/file_metrics_exporter.py` | Экспорт метрик в файл |

### TOML конфигурация (toml_config/)

| Файл | Описание |
|------|----------|
| `toml_config/toml_loader.py` | Загрузчик TOML |
| `toml_config/pydantic_config.py` | Pydantic-модели для TOML |

### Корневые файлы сервера

| Файл | Описание |
|------|----------|
| `cli.py` | CLI entry point (`codelab serve`, `codelab connect`) |
| `config.py` | `AppConfig` — глобальная конфигурация |
| `di.py` | DI-контейнер Dishka (APP/REQUEST scope) |
| `http_server.py` | WebSocket HTTP сервер |
| `web_app.py` | Web UI (Textual Web) |
| `messages.py` | JSON-RPC сообщения (совместимость) |
| `models.py` | Pydantic модели (MessageContent, PlanStep, ToolCall, ...) |
| `exceptions.py` | Иерархия исключений (ACPError, ValidationError, ...) |
| `rpc_holder.py` | `ClientRPCServiceHolder` — мост APP↔REQUEST scope |

---

## Клиент (`codelab/client/`)

### Domain Layer

| Файл | Описание |
|------|----------|
| `domain/entities.py` | Сущности: `Session`, `Message` |
| `domain/events.py` | Domain events |
| `domain/repositories.py` | Интерфейсы репозиториев |
| `domain/services.py` | Интерфейсы сервисов |

### Application Layer

| Файл | Описание |
|------|----------|
| `application/use_cases.py` | Use Cases: send_prompt, load_session, ... |
| `application/dto.py` | Data Transfer Objects |
| `application/session_coordinator.py` | Координатор сессий |
| `application/permission_handler.py` | Обработчик разрешений |
| `application/state_machine.py` | UI State Machine |

### Infrastructure Layer

| Файл | Описание |
|------|----------|
| `infrastructure/transport.py` | WebSocket транспорт |
| `infrastructure/stdio_transport.py` | Stdio транспорт (subprocess) |
| `infrastructure/container_factory.py` | Фабрика DI-контейнера |
| `infrastructure/providers.py` | Dishka провайдеры (ClientProvider, ViewModelProvider) |
| `infrastructure/repositories.py` | Реализации репозиториев |
| `infrastructure/handler_registry.py` | Реестр обработчиков |
| `infrastructure/message_parser.py` | Парсер JSON-RPC сообщений |
| `infrastructure/client_config.py` | Конфигурация клиента |
| `infrastructure/logging_config.py` | Настройка логирования |
| `infrastructure/mcp_config_loader.py` | Загрузчик MCP конфигурации |
| `infrastructure/view_model_provider.py` | ViewModel провайдер |

#### Сервисы (infrastructure/services/)

| Файл | Описание |
|------|----------|
| `services/acp_transport_service.py` | `ACPTransportService` — транспорт с callbacks |
| `services/background_receive_loop.py` | `BackgroundReceiveLoop` — единственный receive() |
| `services/message_router.py` | `MessageRouter` — маршрутизация сообщений |
| `services/routing_queues.py` | `RoutingQueues` — очереди responses/notifications/permissions |
| `services/connection_health_monitor.py` | Монитор здоровья соединения |
| `services/file_system_executor.py` | Файловые операции на клиенте |
| `services/terminal_executor.py` | Терминальные операции на клиенте |

#### Обработчики (infrastructure/handlers/)

| Файл | Описание |
|------|----------|
| `handlers/file_system_handler.py` | `FileSystemHandler` — обработка fs/* RPC |
| `handlers/terminal_handler.py` | `TerminalHandler` — обработка terminal/* RPC |

#### События (infrastructure/events/)

| Файл | Описание |
|------|----------|
| `events/bus.py` | `EventBus` — pub/sub система |

#### Плагины (infrastructure/plugins/)

| Файл | Описание |
|------|----------|
| `plugins/base.py` | Базовый класс плагина |
| `plugins/context.py` | Контекст плагина |
| `plugins/manager.py` | Менеджер плагинов |

### Presentation Layer (MVVM)

| Файл | Описание |
|------|----------|
| `presentation/base_view_model.py` | `BaseViewModel` |
| `presentation/observable.py` | `Observable[T]` — реактивные свойства |
| `presentation/ui_view_model.py` | `UIViewModel` — статус соединения, загрузка |
| `presentation/session_view_model.py` | `SessionViewModel` — список сессий |
| `presentation/chat_view_model.py` | `ChatViewModel` — сообщения, tool calls, streaming |
| `presentation/plan_view_model.py` | `PlanViewModel` — план агента |
| `presentation/terminal_view_model.py` | `TerminalViewModel` — терминал |
| `presentation/filesystem_view_model.py` | `FileSystemViewModel` — файловое дерево |
| `presentation/file_viewer_view_model.py` | `FileViewerViewModel` — просмотр файлов |
| `presentation/permission_view_model.py` | `PermissionViewModel` — запросы разрешений |
| `presentation/terminal_log_view_model.py` | `TerminalLogViewModel` — лог терминала |
| `presentation/config_option_selector_view_model.py` | Выбор опций конфигурации |
| `presentation/model_selector_view_model.py` | Выбор модели LLM |

### TUI Layer (Textual)

| Файл | Описание |
|------|----------|
| `tui/app.py` | `ACPClientApp` — главное приложение |
| `tui/config.py` | Конфигурация TUI |
| `tui/serve_entry.py` | Точка входа для Web UI |

#### Компоненты (tui/components/)

| Файл | Описание |
|------|----------|
| `components/main_layout.py` | Основной layout |
| `components/header.py` | Шапка с статусом |
| `components/footer.py` | Подвал с сообщениями |
| `components/sidebar.py` | Боковая панель с сессиями |
| `components/chat_view.py` | Основной чат |
| `components/prompt_input.py` | Поле ввода промпта |
| `components/message_list.py` | Список сообщений |
| `components/message_bubble.py` | Пузырь сообщения |
| `components/streaming_text.py` | Потоковый текст |
| `components/tool_panel.py` | Панель инструментов |
| `components/tool_call_card.py` | Карточка tool call |
| `components/tool_call_list.py` | Список tool calls |
| `components/plan_panel.py` | Панель плана |
| `components/file_tree.py` | Дерево файлов |
| `components/file_viewer.py` | Просмотр файлов |
| `components/terminal_output.py` | Вывод терминала |
| `components/terminal_panel.py` | Панель терминала |
| `components/permission_modal.py` | Модальное окно разрешений |
| `components/permission_request.py` | Запрос разрешения |
| `components/inline_permission_widget.py` | Inline виджет разрешений |
| `components/permission_badge.py` | Бейдж разрешений |
| `components/terminal_log_modal.py` | Модальное окно лога терминала |
| `components/file_change_preview.py` | Предпросмотр изменений |
| `components/file_change_preview_modal.py` | Модалка предпросмотра |
| `components/action_bar.py` | Панель действий |
| `components/action_button.py` | Кнопка действия |
| `components/quick_actions_bar.py` | Панель быстрых действий |
| `components/status_line.py` | Строка статуса |
| `components/spinner.py` | Индикатор загрузки |
| `components/progress.py` | Прогресс-бар |
| `components/toast.py` | Toast-уведомления |
| `components/tabs.py` | Вкладки |
| `components/panel.py` | Базовая панель |
| `components/container.py` | Контейнер |
| `components/collapsible_panel.py` | Сворачиваемая панель |
| `components/context_menu.py` | Контекстное меню |
| `components/command_palette.py` | Палитра команд |
| `components/search_input.py` | Поле поиска |
| `components/help_modal.py` | Модальное окно помощи |
| `components/config_option_selector.py` | Выбор опций |
| `components/model_selector.py` | Выбор модели |
| `components/session_turn.py` | Turn сессии |
| `components/keyboard_manager.py` | Управление клавиатурой |
| `components/chat_view_permission_manager.py` | Менеджер разрешений чата |
| `components/markdown.py` | Рендер Markdown |

#### Навигация (tui/navigation/)

| Файл | Описание |
|------|----------|
| `navigation/manager.py` | `NavigationManager` — главный менеджер |
| `navigation/queue.py` | `OperationQueue` — приоритетная очередь |
| `navigation/tracker.py` | `ModalWindowTracker` — отслеживание модалей |
| `navigation/operations.py` | Операции навигации |

#### Темы (tui/themes/)

| Файл | Описание |
|------|----------|
| `themes/manager.py` | Менеджер тем (dark/light) |

#### Стили (tui/styles/)

| Файл | Описание |
|------|----------|
| `styles/app.tcss` | CSS стили Textual |

---

## Общие модули (`codelab/shared/`)

| Файл | Описание |
|------|----------|
| `messages.py` | `ACPMessage`, `JsonRpcError` — JSON-RPC сообщения |
| `logging.py` | `setup_logging()` — структурированное логирование (structlog) |

### Content Types (`shared/content/`)

| Файл | Описание |
|------|----------|
| `content/base.py` | Базовые классы контента |
| `content/text.py` | `TextContent` |
| `content/image.py` | `ImageContent` (PNG, JPEG, GIF, WebP) |
| `content/audio.py` | `AudioContent` (WAV, MP3) |
| `content/embedded.py` | `EmbeddedResourceContent` |
| `content/resource_link.py` | `ResourceLinkContent` |

---

## Тесты (`tests/`)

### Серверные тесты (`tests/server/`)

| Директория | Описание | Кол-во тестов |
|------------|----------|---------------|
| `transport/` | StdioServerTransport, WebSocketTransport | ~40 |
| `protocol/` | ACPProtocol, handlers, pipeline | ~200 |
| `agent/` | AgentLoop, strategies, dispatcher | ~100 |
| `tools/` | ToolRegistry, executors, definitions | ~80 |
| `llm/` | LLM провайдеры, fallback | ~50 |
| `mcp/` | MCP интеграция | ~30 |
| `storage/` | SessionStorage backends | ~30 |
| `observability/` | Tracer, metrics, exporters | ~20 |
| `client_rpc/` | ClientRPCService | ~30 |
| Корень | E2E, lifecycle, conformance, integration | ~150 |

**Итого:** ~730 серверных тестов

### Клиентские тесты (`tests/client/`)

| Директория | Описание | Кол-во тестов |
|------------|----------|---------------|
| `tui/` | TUI компоненты, MVVM, навигация | ~600 |
| `infrastructure/` | Transport, EventBus, plugins, handlers | ~100 |
| `presentation/` | ViewModels, Observable | ~50 |
| `application/` | Use Cases, State Machine | ~30 |
| `domain/` | Entities, Repositories | ~20 |
| Корень | Transport service, routing, DI | ~100 |

**Итого:** ~900 клиентских тестов

### Общие тесты (`tests/shared/`)

| Директория | Описание | Кол-во тестов |
|------------|----------|---------------|
| `content/` | Content Types | ~40 |
| Корень | Logging | ~10 |

**Итого:** ~50 общих тестов

---

## Ключевые потоки данных

### 1. Prompt Turn (Client → Server → LLM → Client)

```
Client TUI → ChatViewModel → UseCase → TransportService → WebSocket
                                                        ↓
Server: WebSocketTransport → ACPProtocol.handle_and_process()
                              ↓
                         PromptOrchestrator.process_prompt_turn()
                              ↓
                         LLMLoopStage → AgentLoop → LLMCallStrategy
                              ↓
                         LLM Provider (OpenAI/Anthropic/...)
                              ↓
                         AgentLoop._process_tool_calls()
                              ↓
                         ToolRegistry.execute_tool()
                              ↓
                         ClientRPCBridge → ClientRPCService → WebSocket
                                                        ↓
Client: BackgroundReceiveLoop → MessageRouter → RoutingQueues
                              ↓
                         FileSystemHandler/TerminalHandler → Executor
                              ↓
                         Response → ClientRPCService.handle_response()
                              ↓
Server: AgentLoop получает результат → continue_execution → LLM
                              ↓
                         PromptOrchestrator → complete_active_turn()
                              ↓
                         WebSocketTransport → Client TUI
```

### 2. Background Prompt Execution (Stdio Transport)

```
stdin: session/prompt
  ↓
StdioServerTransport.run() → asyncio.create_task(_process_prompt_request_in_background)
  ↓
receive-loop продолжает читать stdin ←──────────────────────────────────┐
  ↓                                                                      │
stdin: client response (method=None, id=rpc_id)                          │
  ↓                                                                      │
on_message(client_response) → protocol.handle() → handle_client_response()│
  ↓                                                                      │
ClientRPCService.handle_response() → future.set_result() ────────────────┘
  ↓
prompt task получает ответ → завершается → _finalize_outcome_and_send()
```

### 3. Permission Flow

```
AgentLoop → _decide_tool_execution() → requires_permission=True
  ↓
PermissionManager.build_permission_request()
  ↓
session/request_permission → Client → User (Allow/Deny)
  ↓
session/request_permission_response → Server
  ↓
PermissionManager.compute_result() → allow/deny/reject
  ↓
AgentLoop.resume_after_permission() → continue_execution()
```

---

## DI-контейнер (Dishka)

### Server: APP Scope (singleton)

| Компонент | Зависимости |
|-----------|-------------|
| `AppConfig` | from_context |
| `SessionStorage` | from_context |
| `LLMProvider` | AppConfig |
| `ToolRegistry` | — |
| `ExecutionEngine` | HistoryBuilder, ToolFilter, LLMAdapter, MessageSanitizer, PlanExtractor, ContextCompactor |
| `GlobalPolicyManager` | GlobalPolicyStorage |
| `StateManager`, `PlanBuilder`, `TurnLifecycleManager`, `ToolCallHandler`, `PermissionManager`, `ClientRPCHandler` | — |
| `LLMLoopStage` | ToolRegistry, ToolCallHandler, PermissionManager, StateManager, PlanBuilder, GlobalPolicyManager |
| `PromptOrchestrator` | Все менеджеры + LLMLoopStage + ClientRPCServiceHolder |

### Server: REQUEST Scope (per-connection)

| Компонент | Зависимости |
|-----------|-------------|
| `ACPProtocol` | SessionStorage, ExecutionEngine, ToolRegistry, PromptOrchestrator, ClientRPCServiceHolder |

### Client: APP Scope (singleton)

| Компонент | Зависимости |
|-----------|-------------|
| `ClientConfig` | from_context |
| `EventBus` | — |
| `TransportService` | ClientConfig |
| `SessionRepository` | — |
| `FileSystemExecutor`, `TerminalExecutor` | ClientConfig |
| `FileSystemHandler`, `TerminalHandler` | Executors |
| `SessionCoordinator`, `PermissionHandler` | TransportService, SessionRepository, EventBus |
| 14 ViewModels | EventBus, Logger, SessionCoordinator, ... |

---

## Транспортный слой

### Сравнение транспортов

| Аспект | WebSocket | Stdio |
|--------|-----------|-------|
| **Протокол** | aiohttp WebSocket | stdin/stdout (newline-delimited JSON) |
| **Background prompt** | ✅ `_process_prompt_request_in_background` | ✅ `_process_prompt_request_in_background` |
| **Deferred completion** | ✅ `_complete_deferred_prompt` | ✅ `_complete_deferred_prompt` |
| **Pending tool execution** | ✅ `handle_and_process()` | ✅ `handle_and_process()` |
| **session/cancel** | ✅ отмена deferred | ✅ отмена deferred |
| **Cleanup при disconnect** | ✅ `prompt_request_tasks` | ✅ `_cleanup_background_tasks` |
| **Логирование** | per-connection logger | stderr (structlog) |
| **Send lock** | `asyncio.Lock` (ws_send_lock) | `asyncio.Lock` (send_lock) |

---

## Статистика

| Метрика | Значение |
|---------|----------|
| **Сервер** | 57 директорий, 301 файл |
| **Клиент** | 28 директорий, 160 файлов |
| **Shared** | 4 директории, 16 файлов |
| **Тесты** | 21 директория, 153 файла |
| **Всего LOC (src)** | ~25,000+ строк |
| **Всего тестов** | ~1,680+ |
| **Тестов пройдено** | 3,817 (из 3,850, 33 pre-existing failures) |
| **LLM провайдеров** | 8 (OpenAI, Anthropic, OpenRouter, Zen, Go, Ollama, LMStudio, Mock) |
| **Агентов** | 5 (architect, ask, coder, debug, universal) |
| **MCP инструментов** | 35+ (codegraph: 8, dart-mcp-server: 27) |
| **Тем TUI** | 2 (light, dark) |
| **Режимов сессии** | 3 (plan, standard, bypass) |
