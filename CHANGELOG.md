# Changelog

Все значительные изменения в этом проекте будут документированы в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), проект следует [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added — ACP Protocol Refactoring (feature/acp-ref)

#### Декомпозиция ACPProtocol (God Object → Facade + 6 компонентов)
- **ACPProtocol** сокращён с 2190 до ~400 LOC — теперь Facade, делегирующий обработку:
  - `CommandRegistry` — Command Pattern: реестр обработчиков команд
  - `ResponseRouter` — маршрутизация permission и client RPC responses
  - `BackgroundExecutor` — фоновое выполнение tools, завершение turns
  - `MCPSessionManager` — MCP lifecycle per session (init, reconnect, prompts)
  - `ConfigSpecBuilder` — построение config specs из AgentRegistry, StrategyRegistry, LLMProviderRegistry
  - `PromptOrchestratorBuilder` — Builder для PromptOrchestrator (12+ компонентов)
- Применённые паттерны: Facade, Command, Builder, Strategy, Chain of Responsibility, Observer
- Файлы: `protocol/core.py`, `protocol/notification_bus.py`, `protocol/response_router.py`, `protocol/background_executor.py`, `protocol/mcp_session_manager.py`, `protocol/config_spec_builder.py`, `protocol/orchestrator_builder.py`

#### SessionNotificationBus (Observer pattern)
- Per-session шина: бизнес-логика публикует notifications, транспорт доставляет
- Буферизация сообщений до подписки транспорта
- `clear_buffer()` на `session/load` — реплей истории авторитетен, предотвращает двойную доставку
- Inline-доставка при наличии подписчиков
- Файл: `protocol/notification_bus.py`

#### Токен-стриминг (CODELAB_LLM_STREAMING)
- Живая доставка дельт ответа (`agent_message_chunk` по мере генерации)
- Двойной гейт: `config.llm.streaming` AND `provider.supports_streaming`
- Безопасный фолбэк на `_single_call` если провайдер без streaming
- `stream_completion` переписан: сборка `tool_calls` из дельт, `finish_reason`, `usage`
- Флаг: `CODELAB_LLM_STREAMING` (default off)
- Файлы: `agent/llm_adapter.py`, `protocol/handlers/pipeline/stages/agent_loop.py`, `llm/providers/openai_compatible.py`

#### WebSocket абстракция
- `WebSocketConnection` Protocol + `AiohttpWebSocketConnection` адаптер
- Улучшена тестируемость WebSocketTransport
- Файл: `transport/websocket_connection.py`

#### WebUIManager
- Извлечён из `http_server.py` (558 → ~200 LOC)
- Перенесён в `shared/web_ui.py` для избежания server→client зависимости
- Управление textual-serve subprocess и HTML generation
- Файл: `shared/web_ui.py`

#### ScriptedMockLLMProvider
- Сценарный mock-провайдер (конечный автомат) для e2e-тестов
- Сценарий через env `CODELAB_MOCK_SCENARIO` (JSON)
- Подстановка `${terminal_id}` из tool-результатов
- Файл: `llm/scripted_mock.py`

#### Дефолтный primary-агент
- `AgentRegistry` авто-регистрирует встроенного primary-агента если ни одного не определено
- `agents.default_model` теперь `None` по умолчанию, выводится из `config.llm` как `"provider/model"`
- Единая цепочка: `CODELAB_LLM_*` → `agents.default_model` → модель агента

#### CODELAB_HOME полная поддержка
- Все захардкоженные `Path.home()/.codelab` переведены на `resolve_codelab_home()`
- Полное изолирование глобального состояния: конфиг, auth, агенты, политики, история, TUI

#### Типизация
- ~20 замен `Any` на конкретные типы: `MCPManager`, `ToolCallState`, `SessionState`, callback-типы
- Все импорты через `TYPE_CHECKING` для избежания circular dependencies

#### Тестовая инфраструктура
- `agent_flow_harness.py` (597 LOC) — общий каркас e2e-тестов (stdio + ws)
- E2E-тесты: flow с разрешениями, multi-tool, plan mode, MCP, auth, multimodal, негативные ветки
- ~3,896 тестов passing

### Fixed
- **stream_completion**: корректная сборка `tool_calls` из дельт, `finish_reason`, `usage`
- **Race condition** при shutdown MCP серверов в `manager.py`
- **TimeoutError** `'Task exception was never retrieved'` в `acp_transport_service.py`
- **Missing handlers** для `available_commands_update` и `session_info_update`
- **Валидация content-блоков** `session/prompt` (ACP -32602)
- **Legacy notification** `session/mode_changed` удалён

### Audio валидация в prompt (ACP compliance): Добавлена валидация audio контента согласно ACP спецификации
  - Константа `MAX_AUDIO_DATA_SIZE` (25 MB) для ограничения размера audio данных
  - Валидация обязательных полей: `data` (str) и `mimeType` (str)
  - Проверка размера данных с возвратом стандартизированной ошибки
  - 4 новых теста для audio валидации
  - Коммит: `25a5bb4`

- **TUI виджеты для multimodal контента (P1)**: Placeholder виджеты для отображения изображений и аудио в терминале
  - `ImageContentWidget` — отображает информацию об изображении (MIME type, размер, URI)
  - `AudioContentWidget` — отображает информацию об аудио (MIME type, размер)
  - Обновлён `MessageBubble` для поддержки `content_blocks` с multimodal контентом
  - Метод `_render_content_blocks()` для рендеринга различных типов контента
  - 12 новых тестов для виджетов
  - Коммит: `ac97070`

- **Terminal output truncation с character boundary (ACP compliance)**: Корректная обрезка terminal output согласно ACP спецификации
  - Функция `truncate_to_byte_limit()` для безопасной обрезки на границе UTF-8 символа
  - Поле `was_truncated` в `TerminalSession` для отслеживания факта обрезки
  - Обновлена сигнатура `get_output()` — возвращает tuple из 4 элементов
  - `TerminalCallbackExecutor.get_output()` формирует ACP-compliant response с `truncated` флагом
  - Влияние на LLM: добавление "Output was truncated." в completion_text
  - 7 новых тестов для truncation функции
  - Коммит: `57dcd82`

### Fixed
- **Diff content ACP compliance**: Приведён формат diff content в соответствие со спецификацией ACP 08-Tool Calls.md
  - `validator.py`: REQUIRED_FIELDS для diff теперь требует `newText` вместо `diff`
  - `formatter.py`: использует `oldText`/`newText` для форматирования вместо `diff`
  - Добавлено `oldText` как опциональное поле в `sanitize_content_item()`
  - Обновлены 3 тестовых файла
  - Коммит: `c5f4423`

### Removed
- **Legacy TerminalHandler**: Удалён устаревший handler из `infrastructure/handlers/`
  - Не использовался в `ClientRpcDispatcher` (актуальный диспетчер)
  - Возвращал неправильный формат response (плоский `exitCode` вместо `exitStatus` объекта)
  - Был заменён на `TerminalOutputHandler` из `acp_transport/handlers/`
  - Удалено 640 строк кода
  - Коммит: `182511e`

### Fixed
- **Зависание второго permission request**: Исправлена проблема при которой второй permission request не отображался после одобрения первого, что приводило к зависанию сессии на 5 минут до timeout.
  - Корневая причина: `permission_task` пересоздавался локально в `_wait_for_response_with_events`, но не отменялся при выходе из метода. Осиротевший task оставался в event loop и потреблял сообщения из `permission_queue`, мешая обработке следующих permission requests.
  - Решение: добавлена отмена `permission_task` перед возвратом response и при исключениях, вынесено создание task в метод `_create_permission_task` для централизованного логирования lifecycle.
  - Добавлены 4 новых теста: `test_multiple_permission_requests_in_sequence`, `test_permission_request_during_notification_processing`, `test_permission_task_recreated_immediately`, `test_permission_task_cancelled_on_response`.

- **Stdio transport deadlock в bypass mode**: `session/prompt` теперь выполняется в фоновой задаче (`asyncio.create_task`), чтобы receive-loop мог продолжать читать stdin и маршрутизировать client RPC responses (например, ответы на `fs/read_text_file`). Раньше transport loop блокировался на `await on_message()` и не читал stdin → deadlock на 44+ секунд.
  - `StdioServerTransport` принимает callbacks для интеграции с `ACPProtocol` без прямой зависимости
  - Полный паритет с `WebSocketTransport`: deferred prompt completion, session/cancel отмена, cleanup при disconnect
  - 14 новых unit-тестов, включая регрессионный тест на bypass-mode deadlock

- **Дублирование pending_tool_execution scheduling**: Убрано двойное выполнение инструментов — ранее и `protocol.handle_and_process()`, и `_finalize_outcome_and_send()` в каждом транспорте schedule'или background task. Теперь только `handle_and_process()` отвечает за scheduling.
  - Исправлено в `StdioServerTransport` и `WebSocketTransport`
  - Убран `schedule_pending_tool` callback из stdio транспорта (упрощение API)

- **Strategy dispatcher defensive fixes**: Стратегия фиксируется на первый вызов (`_strategy_selected` флаг), `continue_execution` выбирает дефолтную стратегию если `_current_strategy_name = None`, добавлено детальное логирование (`llm_response_received`, `tool_execution_decision`).

- **Terminal output flow (ГЭП #11)**: Исправлена работа терминальных инструментов со сторонними клиентами (Zed IDE)
  - `TerminalWaitForExitResponse` теперь соответствует ACP spec (только `exitCode` и `signal`, без `output`)
  - `TerminalOutputResponse` использует `exitStatus` и `truncated` по ACP spec
  - `ClientRPCBridge.terminal_output()` — новый метод для получения output терминала
  - `TerminalToolExecutor.execute_wait_for_exit()` вызывает `terminal/output` → `wait_for_exit` → `terminal/output`
  - `ToolResult` теперь передаёт `output` в LLM (исправлена потеря output при создании ToolResult)
  - Все 2208 тестов проходят, совместимость с Zed IDE подтверждена

### Added
- **MCP Integration (Stage 8)**: Поддержка Model Context Protocol
  - Модуль `codelab/src/codelab/server/mcp/` с компонентами:
    - [`models.py`](codelab/src/codelab/server/mcp/models.py) — Pydantic модели MCP протокола
    - [`transport.py`](codelab/src/codelab/server/mcp/transport.py) — StdioTransport для запуска MCP серверов
    - [`client.py`](codelab/src/codelab/server/mcp/client.py) — MCPClient с полным жизненным циклом
    - [`tool_adapter.py`](codelab/src/codelab/server/mcp/tool_adapter.py) — MCPToolAdapter для интеграции с ToolRegistry
    - [`manager.py`](codelab/src/codelab/server/mcp/manager.py) — MCPManager для управления несколькими серверами
  - Поддержка параметра `mcpServers` в `session/new` и `session/load`
  - 27 unit-тестов для MCP модуля

---

## Этап 5: Advanced Permission Management

### Phase 2: Cross-Session Policy Restoration (2026-04-16) ✅

**Цель:** Обеспечить автоматическое восстановление permission policies при загрузке сессии.

**Реализация:**
- Проведен архитектурный анализ permission management system
- Выявлено 4 проблемы (1 HIGH, 2 MEDIUM, 1 LOW)
- Создана 4-фазная roadmap для Advanced Permission Management
- Подтверждено: permission policies автоматически восстанавливаются при session/load
- Добавлены integration тесты для проверки persistence

**Документы:**
- [`doc/architecture/archive/ADVANCED_PERMISSION_MANAGEMENT_ARCHITECTURE.md`](doc/architecture/archive/ADVANCED_PERMISSION_MANAGEMENT_ARCHITECTURE.md) (~750 строк)
  * Анализ текущей реализации (SessionState, PermissionManager, Storage)
  * 4 диаграммы Mermaid (sequence, state, class, gantt)
  * 3-уровневая storage architecture
  * 4-фазный план реализации
- [`doc/architecture/archive/ADVANCED_PERMISSION_MANAGEMENT_ANALYSIS_REPORT.md`](doc/architecture/archive/ADVANCED_PERMISSION_MANAGEMENT_ANALYSIS_REPORT.md) (~480 строк)
  * Детальный анализ 4 проблем с impact и root cause
  * Рекомендации по приоритизации
  * Риски и mitigation strategies

**Тесты:**
- [`codelab/tests/server/test_permission_policy_persistence.py`](codelab/tests/server/test_permission_policy_persistence.py) (6 integration тестов)
  * `test_allow_always_persists_across_save_load`
  * `test_reject_always_persists_across_save_load`
  * `test_multiple_permission_policies_persist`
  * `test_unknown_policy_defaults_to_ask`
  * `test_empty_permission_policy_loads_correctly`
  * `test_concurrent_save_load_operations`

**Результаты:**
- ✅ 51 permission-related тестов PASSED (15 flow + 30 manager + 6 persistence)
- ✅ 846 unit тестов PASSED (no regressions)
- ✅ Ruff check: All passed
- ✅ Backward compatible

**Commits:**
- `30b210b` - docs(stage5): Архитектура Advanced Permission Management
- `643034a` - test(stage5-phase2): Add integration tests for permission policy persistence

**Статус:** Phase 2 завершена ✅
**Следующее:** Phase 3 (Global Policy Management) - Future work


1. Описывайте свои изменения в CHANGELOG.md в разделе [Unreleased]
2. Используйте подрубрики: Added, Changed, Deprecated, Removed, Fixed, Security
3. Один логический блок изменений = один коммит
4. Запускайте `make check` перед commit

## v0.2.0 (2026-07-17)

### Feat

- **context**: Phase 6 — Мультиагент (ChildSessionManager + process_subagent_response)
- **context**: Phase 5 — recursive dependencies + Dart import support
- **llm**: честный контракт для неподключённого [llm.fallback] (P2-24)
- **agent**: P2-22 ЗАКРЫТ — детектор зацикливания агента на повторном tool-call
- **context**: замер tail_ms/fingerprint_ms в build_context Phase 4
- **context**: живой candidate_count в build_context Phase 4
- **context**: интегрировать наблюдаемость /context в build_context Phase 4
- **context**: complete Phase 4 implementation with full integration
- **context**: реализовать Phase 3 — 3-фазное сжатие контекста
- **context**: мультиязыковый skeletonizer на tree-sitter
- **context**: реализовать Слой C — TokenCounter, FileContentCache, CodeSkeletonizer
- **context**: живой candidate_count + синхронизация докам и tasks
- **context**: расширенная наблюдаемость через /context
- **context**: настраиваемая модель TaskAnalyzer через analyzer_model
- **context**: улучшить поиск файлов в ContextGatherer
- **context**: автоматическое извлечение структуры проекта через ProjectStructureDecorator
- **context**: добавить slash-команду /context для наблюдения за состоянием Context Manager
- **context**: завершить Phase 1 — ContextRegistry, метрики, трейсинг, e2e тесты
- **context**: добавить детальное трассировочное логирование в ContextManager
- **context**: реализовать Phase 1 - интеллектуальный сбор контекста
- **context**: реализовать Phase 0 — каркас и контракты Context Manager
- **server**: живой токен-стриминг под флагом CODELAB_LLM_STREAMING (A4)
- **agent**: on_delta в слое стратегий (стриминговый путь через шину)
- **agent**: стриминг-handler в LLMAdapter (_handle_request_streaming)
- **agent**: стриминг в AgentEventBus (send_request_streaming)
- **config**: флаг токен-стриминга CODELAB_LLM_STREAMING (дефолт off)
- **server**: живая доставка turn-нотификаций через NotificationBus
- **test**: сценарный Mock LLM (конечный автомат) + e2e flow-тесты через stdio
- **agent**: встроенный дефолтный primary-агент + вывод default_model из llm
- **observability**: добавить flush при disconnect/shutdown и propagate session_id в spans
- **mcp**: реализовать Phase 2 Observability - метрики и трейсинг
- **mcp**: реализовать Phase 1 MCP fallback - timeout и retry
- **client**: добавить поддержку мультимодальных промптов
- terminal output truncation с character boundary (ACP compliance)
- добавить TUI виджеты для multimodal контента (P1)
- добавить валидацию audio контента в prompt
- добавить поддержку audio content в ACP pipeline
- реализована мультимодальная поддержка промптов
- **immediate-notification-delivery**: реализовать немедленную отправку notifications
- **terminal-embedding**: добавить логирование и документацию для immediate notification delivery
- **terminal-embedding**: реализовать встраивание terminal в tool calls
- переработать PromptInput с inline-селекторами
- интегрировать FollowAlongService в клиентский ToolCallHandler
- **client**: завершена декомпозиция клиента
- **client**: рефакторинг ChatViewModel с делегированием новым компонентам
- **client**: добавить SessionUpdateDispatcher (Группа 5)
- **client**: добавить обработчики обновлений сессии (Группа 4)
- **client**: добавить исполнители callback'ов (Группа 3)
- **client**: добавить основу декомпозиции ChatViewModel (Группы 1-2)
- **client**: add detailed scroll_end logging for permission widget debugging
- **client**: add detailed logging for permission request debugging
- **tui**: redesign PromptInput with inline dropdown selectors
- add opencode agents and configuration
- add commitizen, pre-commit hooks, and CI release workflow

### Fix

- **plan**: P2-26 — хранить latest_plan в ACP-форме {content,priority,status}
- **agent**: P2-25 — доставлять failed-статус tool'а немедленно при исключении
- **tui**: устранить 4 мёртвых биндинга (P2-16 смежный пробел)
- **agent**: P2-23 ЗАКРЫТ — не терять output terminal-результата при ненулевом exit code
- **tui**: P2-16 ЗАКРЫТ — единый источник раскладки клавиш + guardrail
- **tui**: P2-19 ЗАКРЫТ — фокус и очередь permission-модалов
- **tui**: устранить фриз UI во время стриминга ответа агента
- **tools**: P2-21 ЗАКРЫТ — ранний reject неизвестного tool + валидация fs read path
- **terminal**: P2-18 ЗАКРЫТ — серверный alias для terminalId (устранён recreate-loop)
- **context**: P2-15 — пропускать холостой LLM-вызов TaskAnalyzer без structured output
- **context**: P2-20 — фильтровать SQLite-сайдкары и .codegraph в ContextGatherer
- **types**: P0-14 — устранить 4 ошибки ty, восстановить гейт make check
- **client-rpc**: забирать исключение future_task в _call_method (P11)
- **client**: graceful-обработка close-фреймов WebSocket (P13)
- **replay**: сериализовать план в session/load (P12)
- **context**: last_task_profile не сохранялся в MetricsTracker
- обновить тесты FileCacheDecorator для phase-4 API
- **context**: tail из session.history в incremental/hydration phase-4 (4.D1)
- **context**: рабочий рефреш изменённых файлов в incremental (4.D2)
- **context**: изолировать per-session состояние Context Manager
- **context**: ретрай при недооценке бюджета (D.1) + спека вложенного budget (D.2')
- **context**: исправить RPC ошибки при чтении бинарных файлов
- **context**: читать бюджет из вложенной секции [agents.context.budget]
- добавить проверку кэша перед чтением файла в FileCacheDecorator
- **context**: tree-sitter скелетизация по байтам + честный docstring skeletonize()
- **context**: structlog везде + graceful fallback tree-sitter
- **context**: нормализация путей для матчинга target_modules с project_files
- **context**: устранить расхождения /context со спекой observability
- **context**: tail строится из session.history, а не из prompt (4.D1)
- **context**: укоренять граф зависимостей в session.cwd, а не в cwd сервера
- **context**: проверять бинарность ДО чтения файла (RPC-safety)
- **context**: изолировать per-session граф зависимостей
- **context**: детерминизм dependents, сигнатура gather, удаление мёртвого кода
- **di**: PromptOrchestratorBuilder использует CommandRegistry из DI
- **context**: исправить подсчёт метрик gathered_files
- **context**: ProjectStructureDecorator проверяет operation вместо tool_name
- **context**: передать LLM провайдер и реализовать комбинированное чтение span'ов
- **di**: интегрировать DefaultContextManager в ExecutionEngine
- **context**: интегрировать ContextConfig из TOML в команду /context
- **terminal**: auto-set cwd from session for terminal/create
- **tests**: добавить фикстуру для сброса кэша structlog
- **tools**: добавить валидацию путей для предотвращения выхода за cwd
- **protocol**: исправить race condition и дублирование метрик
- **observability**: исправить дублирование метрик и мигрировать на structlog
- **docs**: починить рендеринг Mermaid sequence diagram в примере
- **server**: убрать хардкод built-in команд в MCPSessionManager
- **docs**: исправить парсинг Mermaid в §6 (curly braces в Export labels)
- **docs**: исправить парсинг Mermaid в §6 (curly braces in label)
- **docs**: исправить парсинг Mermaid в §5.2-5.3 (parentheses in labels)
- **docs**: исправить синтаксис Mermaid (subbus → subgraph)
- **llm**: корректный stream_completion со сборкой tool_calls из дельт
- **server**: восстановить warning при отсутствии send callback
- **server**: восстановить поведение после декомпозиции ACPProtocol
- **protocol**: валидировать content-блоки session/prompt (ACP -32602)
- **protocol**: удалить legacy session/mode_changed notification
- уважать CODELAB_HOME во всех местах чтения глобального состояния
- **agent**: загрузка агентов уважает CODELAB_HOME
- исправить MarkupError в chat_view.py, вызывавший зависание сессии
- привести diff content в соответствие с ACP спецификацией
- увеличить порог latency в benchmark тесте
- Image domain model соответствие ACP spec (format → mime_type)
- исправить формат tools для OpenAI API
- **websocket**: использовать handle_and_process для permission response
- **websocket**: добавить логирование для диагностики tool calls зависания в pending
- немедленная отправка notification в resume_after_permission
- **immediate-notification-delivery**: убрать batch отправку notifications и добавить latency logging
- **immediate-notification-delivery**: обновлять callback в переиспользуемом AgentLoop
- **immediate-notification-delivery**: исправить дублирование permission request
- **immediate-notification-delivery**: передавать callback через pipeline для initial prompt
- **terminal-embedding**: передавать terminal content через permission flow
- использовать английский формат заголовков требований для openspec
- исправить заголовки delta specs для openspec archive
- добавить client_capabilities при создании сессии в TUI
- **client**: исправить зависание второго permission request
- исправить DeprecationWarning в ConfigOptionHandler
- **client**: исправить проблему с отображением ответов агента в ChatView
- **client**: исправить вызов метода handle_session_update_dispatched
- исправить отображение PermissionRequest в TUI
- **client**: preserve permission widget during ChatView updates
- **client**: use call_after_refresh for scroll_end in permission widget
- **client**: add logging for permission request debugging
- **tui**: remove label prefix from InlineSelector display
- **tui**: fix InlineSelector text visibility
- **tui**: subscribe InlineSelector to Observable in __init__
- **tui**: sanitize model/option IDs to avoid invalid Textual identifiers
- исправления в TUI компонентах
- handle transport errors and ensure plugin cleanup
- add missing ACPMessage.error_response() method in client
- suppress test warnings and fix asyncio marks

### Refactor

- **tui**: удалить неиспользуемый TerminalPanel (P2-8)
- **tui**: P2-17 ЗАКРЫТ — удалён неадоптированный NavigationManager
- **complexity**: P0-2 ЗАКРЫТ — снять последние 9 блоков (11→<=10), C901 11→10
- **complexity**: P0-2 — снять блоки сложности 12, затянуть C901 12→11
- **complexity**: P0-2 — снять все блоки сложности >12, затянуть C901 20→12
- **server**: DRY-фабрика _build_agent_loop в LLMLoopStage (P1-4, шаг 6)
- **server**: AgentLoop — тонкий фасад, снизить _run_iteration (P1-4, шаг 5)
- **server**: извлечь ToolCallProcessor из AgentLoop (P1-4, шаг 4)
- **server**: извлечь LlmCaller из AgentLoop (P1-4, шаг 3)
- **server**: agent_loop.py → пакет + извлечь SessionUpdateSink (P1-4)
- **server**: вынести path-matching хелперы gatherer.py в file_matching (P1-4)
- **server**: разбить prompt.py на пакет prompt/ по осям изменения (P1-4)
- **client**: вынести RequestCallbackCoordinator из acp_transport_service (P1-4, шаг 3b/3)
- **client**: вынести PermissionResponder из acp_transport_service (P1-4, шаг 3a/3)
- **client**: снять вестигиальные fs/terminal callbacks с транспортного порта (P1-4, шаг 2/3)
- **client**: удалить мёртвый legacy client-RPC путь из acp_transport_service (P1-4, шаг 1/3)
- **mcp**: разнести transport.py по модулям + честная иерархия исключений (P1-4)
- **tui**: вынести Connection/Session/Chat/ConfigOptions контроллеры из app.py (P1-4)
- **tui**: единый источник видимости sidebar + dispose NavigationManager (P1-4, P2-17)
- **tui**: вынести ModalController и tool-call parser из app.py (P1-4, P0-2)
- **chat**: декомпозировать ChatViewModel, вынести ReplayReducer (P1-4)
- **di**: разбить God Object server/di.py на пакет по доменам (P1-4)
- **tui**: разбить ToolPanel._on_tool_calls_changed (P0-2)
- **agent**: разбить AgentLoop.run (P0-2)
- **llm**: разбить OpenAICompatibleProvider.stream_completion (P0-2)
- **pipeline**: разбить DirectivesStage.process (P0-2)
- **context**: разбить _find_similar_files (P0-2)
- **context**: разбить DefaultContextManager.build_context (P0-2)
- **context**: разбить ACPContextGatherer.gather (P0-2)
- **cli**: разбить run_server (P0-2)
- **context**: разбить ThreePhaseCompactor._phase_hard_truncate (P0-2)
- **config**: разбить AppConfig._merge_llm_config (P0-2)
- **transport**: разбить WebSocketTransport.run (P0-2)
- **agent**: разбить AgentLoop._process_tool_calls (P0-2)
- **protocol**: разбить resolve_pending_client_rpc_response (P0-2)
- **context**: перевести budget/config_loader/dependency_graph на structlog
- **typing**: replace Any with concrete types across server
- **server**: extract WebUIManager from http_server.py
- **transport**: WebSocket abstraction и исправления багов из логов
- **protocol**: replace Any with concrete types in ACPProtocol.__init__
- **server**: убрать legacy direct-instantiation путь из ACPProtocol
- **server**: декомпозиция God Object ACPProtocol
- **test**: вынести stdio-каркас e2e в harness + гейт multimodal по capabilities
- **test**: вынести общий harness flow-тестов агента (stdio + ws)
- **client**: архитектурный рефакторинг мультимодального контента
- **protocol**: применение Command Pattern для обработки ACP-методов
- убрать таймауты из транспорта и permission request
- удалить legacy TerminalHandler
- убрать создание diff на сервере для fs/write_text_file
- разделить domain и protocol слои моделей
- **client**: удалить legacy код из ChatViewModel
- **client**: делегирование ответственностей ChatViewModel новым компонентам
- **client**: устранение DRY и улучшение типизации
- **client**: удаление мёртвого кода и исправление архитектурных нарушений
- reduce complexity of request_with_callbacks

### Perf

- оптимизация производительности компонентов декомпозиции

## v0.1.0 (2026-06-16)

### Feat

- complete acp-protocol-mode-integration with tests
- **mode**: add debug logging to tool_policy decision chain
- **mode**: unify tool policy decision logic and add comprehensive tests
- complete blocks 6-8, move child mode inheritance to strategy specs
- implement ACP Protocol mode integration (blocks 1-5)
- создать openspec change для интеграции ACP Protocol mode
- создать openspec change для переименования AgentMode → AgentRole
- создать openspec changes для трёх мультиагентных стратегий
- **server**: integrate ContextCompactor into ExecutionEngine
- **remove-legacy**: Phases 6-9 — delete legacy files, tests, and update docstrings
- **remove-legacy**: Phases 3-5 — remove agent_orchestrator from PromptOrchestrator, LLMLoopStage, and DI
- **remove-legacy**: Phase 2 — extract cancel_prompt into LLMAdapter
- **remove-legacy**: Phase 2 — extract cancel_prompt into LLMAdapter
- **remove-legacy**: Phase 1 — extract ModelResolver as standalone DI component
- **client**: универсальный механизм выбора config options
- **server**: динамическая генерация available_commands из CommandRegistry
- **server**: интегрировать StrategyDispatcher в Pipeline и Slash Commands
- **server**: обновить DI для StrategyRegistry
- **server**: добавить _active_strategy в configOptions
- **server**: обновить StrategyDispatcher для использования StrategyRegistry
- **server**: добавить StrategyRegistry и StrategyDescriptor
- **server**: добавить multi-agent поля в SessionState (v1 → v3 миграция)
- **agent-loop**: добавить тесты, документацию и исправить баги
- **observability**: Phase 1 - mark_exported/clear_exported, lazy dir creation, cleanup, metrics
- **agent-loop**: реализовать AgentLoop — унифицированный цикл итераций LLM
- **strategy**: dynamic strategy & agent selection
- **observability**: добавить file persistence для spans, events и metrics
- add AgentRegistry to DI and agents configuration to AppConfig
- integrate EventBus and MultiAgent components into DI container
- integrate observability components into DI container
- mark deprecated components with @deprecated annotation
- integrate LLMAdapter single call pattern with EventBus
- implement multiagent single strategy (50/50 tasks)
- implement multiagent LLM adapter (28/28 tasks)
- implement multiagent agent registry (48/48 tasks)
- implement multiagent observability (33/33 tasks)
- implement multiagent event bus (43/43 tasks)
- add configurable LLM timeouts and fix terminal command parsing
- добавить тесты MCP client TOML config — mcp_servers passing
- implement proper JSON-RPC 2.0 message classification and incoming request handling
- implement MCP Roots support and fix orphaned tool call logging
- Sprint 1 — MCP Image/Resource content + Progress notifications
- поддержка HTTP/SSE транспортов MCP и исправление бага с mcp_manager
- переместить MCP prompt handlers в SessionRuntimeState
- полная интеграция MCP Prompts как slash commands
- defensive MCP re-initialization on session/prompt
- send initial available_commands_update after MCP server connect
- добавить openspec changes для мультиагентной инфраструктуры
- MCP client TOML config + configurable stdio receive timeout
- добавить HTTP/SSE транспорты и MCP capabilities
- implement SessionRuntimeRegistry for MCP lifecycle management
- добавить логирование system message и MCP информации
- добавить system message с MCP информацией для LLM
- добавить тег MCP сервера в описание инструментов для LLM
- MCP Tools в LLM Loop — kind inference и интеграционные тесты
- **tui**: добавить систему тем с TOML/CLI/env конфигурацией
- add message trace logging for JSON-RPC messages
- добавить UI для выбора LLM модели в клиенте
- per-process log files with PID in filename
- динамическая смена LLM провайдера через ACP протокол
- populate configOptions.model from TOML config via Pydantic Settings
- update module exports for all new LLM components
- integrate ProviderEventBus into provider initialization flow
- add CLI arguments for fallback configuration
- integrate ModelResolver into AgentOrchestrator
- add ConfigOptionBuilder and model switching via ACP configOptions
- update config and DI for multi-provider LLM
- multi-provider LLM foundation (phases 1-9)
- normalize file paths for LLM-driven tool calls
- реализовать stdio транспорт для ACP протокола
- вынести сборку PromptPipeline и CommandRegistry в DI
- интегрировать Dishka DI-контейнер в сервер ACP
- **security**: добавить ограничение размера WebSocket сообщений и длины промпта
- **server**: вынести asyncio.Future из SessionState в PendingRequestRegistry
- **tui**: адаптация layout под OpenCode (dock-region)
- **sidebar**: интеграция SearchInput для фильтрации сессий
- **tui**: реализация MainLayout с LayoutConfig, toggle_bottom_panel и событиями
- **tui**: добавлены тесты для ContextMenu
- **tui**: добавлен CollapsiblePanel модуль и AccordionGroup alias
- **tui**: добавлены тесты для SearchInput компонента
- **tui**: интеграция ActionBar для быстрых действий
- **client**: интеграция PermissionRequest как альтернативы InlinePermissionWidget
- **tui**: интеграция TerminalPanel функционала в TerminalOutputPanel
- **tui**: интеграция MessageBubble в ChatView для улучшенного рендеринга
- **tui**: интеграция FileChangePreview как модального окна
- **tui**: интеграция ToolCallList в ToolPanel с обновлением статусов
- **tui**: интеграция ToolCallList в ToolPanel
- **tui**: интегрировать ProgressBar в ToolPanel
- **tui**: интегрировать LoadingIndicator в ChatView
- **tui**: интегрировать Toast/ToastContainer в TUI приложение
- **tui**: Phase 5 - Polish UI components
- **tui**: Phase 4 - Advanced UI Components
- **tui**: Phase 3 - Tool Components миграция из OpenCode
- **tui**: Фаза 2 - Session Components миграция из OpenCode
- **tui**: Фаза 1 - Core Layout миграция UI из OpenCode
- **web-ui**: заменён textual-web на textual-serve для локального Web UI
- **codelab**: добавить textual-web в основные зависимости
- **cli**: автогенерация ~/.codelab/config/.env при первом запуске
- **codelab**: добавить загрузку .env файла при запуске
- **codelab**: добавить инициализацию домашней директории ~/.codelab
- **tui**: добавлена кнопка Send для отправки промпта
- **codelab**: добавить Web UI на базе Textual Web
- **codelab**: добавить тесты и обновить документацию
- **codelab**: добавить единый CLI с режимами serve/connect/local
- **codelab**: migrate client modules from acp-client
- **codelab**: добавить shared модули (messages, logging, content)
- **codelab**: создать базовую структуру unified пакета
- **slash-commands**: интеграция slash commands в PromptOrchestrator
- **slash-commands**: реализована инфраструктура slash commands
- **scripts**: улучшен скрипт test_mcp.sh для тестирования MCP интеграции
- интеграция MCP в session/new и session/load
- **mcp**: интеграция MCP с ACPProtocol и тесты
- **mcp**: добавлены MCPManager, MCPToolAdapter и обработчики протокола
- **mcp**: add base MCP module (models, transport, client)
- **server**: Этап 7 - Agent Plan Generation (LLM → план)
- **agent**: добавить инструкции по update_plan в system prompt
- **server**: Этап 6 - Session Load Replay с ReplayManager
- **server**: LLM loop после permission approval (ACP Protocol Step 6)
- **protocol**: implement LLM loop in PromptOrchestrator for BUG #3
- RPC без timeout с поддержкой отмены и исправление routing response
- улучшить логирование flow работы tools с permission request
- **stage5-phase3**: Global Policy Management - Core Implementation
- Phase 3 Manager Layer - GlobalPolicyManager singleton with 34 unit tests
- **storage**: реализация GlobalPolicyStorage для Phase 3 - управление глобальными policies
- **stage4**: Этап 4 Фазы 1-2 - Content Integration в Tool Calls
- configure client history path and align permission flow
- добавить callbacks для файловой системы и терминала в ChatViewModel
- реализовать ClientRPCService для вызовов методов на клиенте
- добавлены integration тесты для Content типов
- реализация Content типов для acp-client
- реализация Content типов для ACP протокола (Этап 1)
- **client**: improve TUI navigation and help UX
- Реализовать обработку user_message_chunk в ChatViewModel
- **client**: реализована Message Routing инфраструктура для решения concurrent receive
- Этап 6 - Интеграция WebSocket транспорта с PromptOrchestrator
- добавить Pydantic типизацию для history, available_commands, latest_plan
- add exception hierarchy for acp-server
- добавить флаги логирования и логирование на всех уровнях в acp-server
- добавить Pydantic settings для глобальной конфигурации acp-server
- **acp-client**: добавлен параметр -cwd для указания пути к проекту
- инициализация ~/.acp-client и сохранение логов по умолчанию
- **acp-client**: реализована полная интеграция Use Cases с Transport Service
- **acp-client**: реализована интеграция ACPTransportService с WebSocket
- NavigationManager и исправление ScreenStackError
- добавлены методы clear_messages, add_system_message, finish_agent_message в ChatView
- добавлена MVVM архитектура - Observable, BaseViewModel, SessionViewModel, ChatViewModel, UIViewModel (Phase 4.1-4.4)
- добавлена Event-Driven архитектура и Plugin System (Phase 3.1-3.2)
- **acp-client**: Phase 1 - Infrastructure abstraction layer (Quick Wins)
- **client**: close stage 11 hotkeys and focus polish
- **client**: добавить merge и dedupe для history cache
- **client**: добавить timeout для permission modal
- **client**: добавить modal просмотр полного terminal output
- **client**: добавить базовый config manager для TUI
- **client**: добавить history cache fallback для replay
- **client**: добавить UIStateMachine и обновить roadmap статус
- **client**: добавить persistent permission policy manager
- **client**: добавить terminal output в tool panel
- **client**: добавить terminal manager и wiring в TUI
- **client**: добавить индикаторы изменений и поиск в file viewer
- **client**: добавить fs integration и file viewer в TUI
- **client**: добавить PlanPanel и routing plan updates в TUI
- **client**: добавить хоткеи навигации и очистки чата в TUI
- **client**: централизовать connection-state статусы в TUI
- **client**: добавить offline-guard отправки prompt в TUI
- **client**: сохранять UI state TUI между запусками
- **client**: добавить очередь failed операций для Ctrl+R retry
- **client**: обобщить Ctrl+R на retry любой failed операции
- **client**: добавить retry prompt и reconnect state в TUI
- **client**: улучшить UX модала разрешений в TUI
- **client**: добавить permission modal и tool panel в TUI
- **client**: добавить историю prompt в TUI
- **client**: отображать replay при переключении сессии
- **client**: переиспользовать persistent WS в TUI
- **client**: добавить выбор сессий в TUI sidebar
- **client**: добавить базовый Textual TUI и запуск через CLI
- **acp-client**: добавить структурированное логирование
- **acp-server**: добавить JsonFileStorage для persistence сессий
- **acp-server**: добавить абстракцию SessionStorage
- **acp-server**: добавить структурированное логирование с structlog

### Fix

- resolve 8 ty type checker errors
- **test**: add _current_strategy_name to mock in strategy reuse test
- **server**: пробрасывать ClientRPCResponseError из bridge в executor
- убрать дублирование pending_tool_execution scheduling
- strategy dispatcher defensive fixes and bypass mode tests
- stdio transport deadlock in bypass mode
- добавить mode check в _decide_tool_execution для LLM tool calls
- send plan notification on update_plan tool execution
- resolve all 67 pre-existing lint errors
- **server**: разрешить дополнительные поля в ACPMessage для совместимости с IntelliJ IDEA
- **server,client**: исправить потерю истории сессии при перезапуске
- **server**: добавить /strategy в список доступных команд
- **agent-loop**: переиспользовать стратегию при permission resume
- **agent-loop**: добавлять tool results в session.history
- **agent-loop**: исправить тесты и DI после рефакторинга
- **agent**: передавать model агента в LLMAdapter
- **llm**: архитектурное исправление инициализации провайдеров
- **di**: инициализировать AgentRegistry при создании
- use pytest.mark.asyncio for context compactor tests
- apply lint fixes for agent-registry (unused imports, StrEnum, frozen test)
- rename test_registry.py to test_agent_registry.py to avoid module name conflict
- **openspec**: согласовать спецификацию с MULTIAGENT_TECHNICAL_SPECIFICATION.md
- заменить kind="mcp" на inferred kind согласно ACP spec
- resolve MarkupError in TUI by using textual.widgets.Markdown
- add auto-restart mechanism for receive loop with exponential backoff
- исправить тесты SessionState.mcp_manager (использовать runtime_registry)
- исправить тесты ConfigOptionBuilder (label→name, pricing→_pricing)
- исправить падающие тесты (CodeBlock, MCPConfigLoader)
- correct MCP capabilities check for empty dict
- correct context_window_limit from 8000 to 128000 to enable compaction trigger
- исправить нумерацию секций в MULTIAGENT_TECHNICAL_SPECIFICATION.md
- save session after execute_pending_tool to persist permission_request_id
- **tui**: исправить белый фон под ToolPanel растягиванием на всю высоту
- **tui**: добавить background для компонентов чтобы избежать белого фона в темной теме
- **tui**: добавить background для контейнеров layout чтобы избежать белого фона в темной теме
- **tui**: обновлять иконку темы через свойство icon вместо несуществующего update()
- **markdown**: исправить SyntaxWarning с невалидной escape-последовательностью
- invalid CSS property border-left-width in ModelItem
- resolve dotted TOML model keys and use config model for default
- replace invalid border-left-width with heavy border style in Textual CSS
- restore config_options and tool_calls during session replay
- use actual llm.provider for default model reference
- LMStudio provider initialization without API key
- strip provider prefix from model ID before sending to API
- устранить дублирование логов и добавить singleton lock для stdio сервера
- remove codelab.toml.example from config chain and fix Python 3.14 event loop error
- исправить порядок загрузки TOML файлов чтобы auth.toml перезаписывал шаблонные env vars
- skip .env creation if codelab.toml already exists
- исправить импорт LLMToolCall из models вместо base
- convert sync fallback tests to async to fix test isolation
- удалить зависающий тест integration_timeout (timeout параметр deprecated в ClientRPCService)
- align RPC responses with ACP protocol spec (empty response means success)
- добавить тесты terminal output flow и исправить обработку signal завершения
- pass tool output to LLM in ToolResult
- align terminal/output response with ACP spec
- align terminal/wait_for_exit with ACP spec
- make terminal response fields optional for third-party ACP clients
- resolve terminal tools execution failure due to missing output field
- устранить дублирование ответов и добавить client capabilities в stdio режиме
- resolve stdio deadlock and LLM tool name validation
- экранировать все Rich-теги в InlineMarkdown для предотвращения MarkupError
- устранить дублирование директив, починить имена инструментов, удалить мёртвый код
- исправить отмену промпта — cancel не ждёт завершения session/prompt
- привести session/update и session/list к спецификации ACP
- передать GlobalPolicyManager через DI в LLMLoopStage и PromptOrchestrator
- очистить stale active_turn в _handle_session_prompt и добавить DI orchestrator path
- очищать stale active_turn при старте нового prompt-turn
- вернуть success в ответе fs/write_text_file — агент больше не уходит в pending
- устранить двойной кэш — удалить _cache из JsonFileStorage
- устранить дублирование в PermissionManager и исправить mcp_manager тип
- переименовать TestViewModel → MockViewModel в тестах
- убрать f-strings в structlog — заменить на структурированные логи
- заменить mcp_manager: Any на строгий тип MCPManager | None
- удалить все # type: ignore из production-кода (34 → 0)
- убрать дублирование и мёртвый код в GlobalPolicyManager
- исправить asyncio.Lock в GlobalPolicyManager для корректной работы в тестах
- **security**: устранить F-string инъекцию в запуске Web UI subprocess
- заменить startswith на is_relative_to для защиты от path traversal
- **terminal**: устранить ошибку terminal/create и восстановление corrupted сессий
- **security**: устранить shell injection в TerminalExecutor.execute()
- **tui**: исправлен action_toggle_theme - Theme.name вместо Theme.value
- **tui**: исправлен ProgressBar для работы со словарями tool_calls
- **client**: исправлена ошибка отступов в request_with_callbacks
- исправлено 15 ошибок типизации ty check
- исправлены критические ошибки типизации
- **client**: prevent deadlock and improve permission handling in transport
- **tests**: исправить 95 неудавшихся тестов после рефакторинга
- **web_app**: исправить проверку наличия textual-web
- **serve**: добавить вывод логов в консоль для режима serve
- хранение данных в ~/.codelab/data/
- **codelab**: использовать setup_logging из shared для записи логов в файл
- синхронизация env переменных с CODELAB_ префиксом
- **codelab**: добавлены недостающие зависимости и модули
- **slash-commands**: исправлен формат session/update для UI
- **scripts**: убран вызов нереализованного метода session/mcp/list
- удалены методы session/mcp/* (нарушение ACP протокола)
- **plan**: убран статус cancelled для соответствия протоколу ACP
- исправлено отображение плана в acp-client UI
- изменить kind для write_text_file с 'write' на 'edit'
- **server**: сохранение assistant message с tool_calls в историю LLM loop
- **client**: исправлен is_permission_request() - убрана проверка id is None
- **tool-execution**: исправлены критические баги BUG#1 и BUG#2
- исправить signature mismatch в App.show_permission_modal для приема on_choice callback
- инициализация GlobalPolicyManager в ACPProtocol
- unblock client RPC during prompt turns
- исправлена критическая ошибка 'This event loop is already running' в fs_read/fs_write callback
- добавить session в AgentContext для выполнения tool calls
- **protocol**: align prompt completion with ACP spec
- **client**: завершать prompt по session/turn_complete и разблокировать input
- **client**: preserve first user message in session/load replay
- **client**: обработка всех session/update уведомлений при загрузке сессии
- **client**: обработка всех session/update уведомлений при загрузке сессии
- **client**: исправлена интеграция Message Routing с RoutingQueues API
- synchronize WebSocket receive() calls with asyncio.Lock
- Исправить тесты WebSocket Этапа 6 согласно спецификации ACP
- Безопасное переключение сессий с очисткой незавершенных операций
- исправить style issues в тестах и обработчиках (E501, F841, line length violations)
- удалить неиспользованный импорт pytest в test_directive_resolver
- persist and restore local chat history
- restore persisted sessions across restarts
- разделить системный ACK и ответ LLM в чате
- восстановить историю чата при переключении сессий
- **docs**: исправлены критические противоречия с ACP протоколом
- **client**: исправлено отображение диалога в ChatView
- добавить параметр cwd в создание сессии (Ctrl+N)
- **client**: добавлены обязательные параметры в запрос initialize
- **acp-client**: устранить type checking ошибки (57→35)
- **acp-client**: улучшена типизация и исправлены все падающие тесты
- **acp-client**: исправлена проблема с отображением ответов от сервера в ChatView
- исправлены lint ошибки в presentation layer
- исправлены lint и import issues в Phase 3
- hotfix catch exception
- **client**: добавить retry для offline-blocked prompt в TUI
- **client**: стабилизировать retry/cancel статусы в TUI
- **client**: добавить retry после reconnect в TUI transport
- **client**: корректно восстанавливать replay при старте TUI

### Refactor

- move codelab/ package to repository root
- **agent**: TOML backward compatibility mode → role + docs update
- завершить rename-agent-mode-to-role — backward compat tests, docs, specs
- сжать AGENTS.md до 185 строк, добавить якоря и группировку
- перенести 'Запрещено' в начало, убрать дублирование секций
- переименовать AgentMode → AgentRole, mode → role
- удалить legacy OrchestratorConfig из agent/state.py
- **server**: ToolFilter — kind-based фильтрация вместо hardcoded имён
- внедрить SystemPromptBuilder в pipeline
- **llm_loop**: удалить legacy методы, использовать AgentLoop
- **openspec**: актуализировать мультиагентную спецификацию по MULTIAGENT_TECHNICAL_SPECIFICATION.md
- единый интерфейс MCP транспортов через TransportFactory
- **tui**: migrate to Textual Theme API for dynamic theme switching
- **tui**: заменить hex цвета в компонентах на theme-aware стили
- **tui**: разделить app.tcss на layout и theme стили
- remove deprecated LLMSectionConfig and TOMLConfig classes
- migrate to AppConfig.load() with pydantic-settings, add comprehensive config tests
- **agent**: split LLMAgent.process_prompt into start_turn/continue_turn
- устранить мнимую циклическую зависимость PermissionHandler ↔ SessionCoordinator
- использовать абстрактный TransportService в PermissionHandler и вынести logger в отдельный провайдер
- улучшить DI-интеграцию и исправить CommandPalette
- удалить legacy методы ping/echo/shutdown
- удалить legacy-обёртки session_prompt/session_cancel
- сделать pipeline и command_registry обязательными параметрами PromptOrchestrator
- мигрировать DI-контейнер на dishka
- удалить дубликаты content-тестов из tests/client/
- дедуплицировать unit-тесты content в tests/shared/content/
- инжектировать PromptOrchestrator через конструктор ACPProtocol
- **storage**: заменить ручную сериализацию в JsonFileStorage на Pydantic
- устранить дублирование пакетов content
- завершить миграцию PromptOrchestrator на Pipeline
- разбить PromptOrchestrator на Pipeline стадии
- заменить цепочку if/else на реестр обработчиков в ACPProtocol
- заменить acp-client/acp-server на codelab
- удалены устаревшие директории acp-client/ и acp-server/, исправлены ошибки линтинга
- перенос тестов в codelab, обновление AGENTS.md и Makefile
- обновить переменные окружения на префикс CODELAB_
- **plan**: remove description field for ACP protocol compliance
- implement clean architecture for tool execution via permission flow
- SessionFactory для централизации создания сессий
- удалить legacy-слой в acp-client
- **client**: унифицировать политику ошибок connection-state в TUI
- **client**: модуляризация client.py - этап 2.8 (финал)
- **client**: модуляризация client.py - этап 2.7
- **client**: модуляризация client.py - этап 2.6
- **client**: модуляризация client.py - этап 2.5
- **client**: модуляризация client.py - этап 2.4
- **client**: модуляризация client.py - этап 2.3
- **client**: модуляризация client.py - этапы 2.1-2.2
- **acp-server**: модуляризация protocol и добавление логирования
