## Tasks

### 1. HistoryBuilder — рефакторинг из AgentOrchestrator

> **Существующий код:** `AgentOrchestrator._convert_to_llm_messages()` уже конвертирует `session.history` → `list[LLMMessage]`. Задача — извлечь логику в отдельный переиспользуемый класс.

- [x] 1.1 Создать `codelab/src/codelab/server/agent/history_builder.py`
- [x] 1.2 Создать класс `HistoryBuilder` с методом `build(session_history, system_prompt?) → list[LLMMessage]`
- [x] 1.3 Перенести логику из `AgentOrchestrator._convert_to_llm_messages()` в `HistoryBuilder.build()`
  - Поддержка форматов: `{"role","text"}`, `{"role","content"}`, `{"role","tool_calls"}`
  - Конвертация content list → str для text блоков
  - Обработка Pydantic моделей через `model_dump()`
- [x] 1.4 Добавить поддержку system prompt как отдельного параметра
- [x] 1.5 Написать тесты: конвертация различных форматов history
- [x] 1.6 Написать тесты: system prompt добавляется первым сообщением

### 2. ToolFilter — рефакторинг из AgentOrchestrator

> **Существующий код:** `AgentOrchestrator._filter_tools_by_capabilities()` уже фильтрует инструменты по capabilities клиента. `_SERVER_SIDE_TOOL_KINDS` (think, plan) всегда доступны. Задача — извлечь в отдельный класс с поддержкой MCP.

- [x] 2.1 Создать `codelab/src/codelab/server/agent/tool_filter.py`
- [x] 2.2 Создать класс `ToolFilter` с методом `filter(tools, capabilities, mcp_tools?) → list[ToolDefinition]`
- [x] 2.3 Перенести логику из `_filter_tools_by_capabilities()`:
  - Серверные инструменты (think, plan) всегда включаются
  - Без capabilities → только серверные инструменты
  - fs/read_text_file → fs_read, fs/write_text_file → fs_write, terminal/* → terminal
- [x] 2.4 Добавить поддержку MCP инструментов: MCP tools включаются независимо от client capabilities (они выполняются на сервере)
- [x] 2.5 Написать тесты: фильтрация с различными capabilities
- [x] 2.6 Написать тесты: MCP tools включаются всегда
- [x] 2.7 Написать тесты: capabilities is None → только серверные + MCP

### 3. MessageSanitizer — рефакторинг из AgentOrchestrator

> **Существующий код:** `AgentOrchestrator._sanitize_orphaned_tool_calls()` уже обнаруживает assistant messages с tool_calls без соответствующих tool responses и вставляет synthetic error. Задача — извлечь.

- [x] 3.1 Создать `codelab/src/codelab/server/agent/message_sanitizer.py`
- [x] 3.2 Создать класс `MessageSanitizer` с методом `sanitize(messages) → list[LLMMessage]`
- [x] 3.3 Перенести логику из `_sanitize_orphaned_tool_calls()`:
  - Детекция orphaned tool calls: assistant с tool_calls, но нет tool results
  - Вставка synthetic tool result: "Error: Tool execution did not complete"
- [x] 3.4 Написать тесты: обнаружение и исправление orphaned tool calls
- [x] 3.5 Написать тесты: корректная история без изменений

### 4. ContextCompactor — новый компонент

> **Новый компонент.** Не существует в текущем коде. Двухфазное сжатие контекста для длинных сессий.

- [x] 4.1 Создать `codelab/src/codelab/server/agent/context_compactor.py`
- [x] 4.2 Создать `ContextCompactor.__init__`: llm, model, max_context_tokens, reserved_tokens
- [x] 4.3 Реализовать `compact_if_needed(history) → tuple[list[LLMMessage], bool, str]`
- [x] 4.4 Реализовать `_prune_old_tool_outputs(history)` — Фаза 1: FIFO удаление старых tool results
- [x] 4.5 Guard: history <= 5 → вернуть без изменений
- [x] 4.6 Сохранить первые 2 сообщения, последние 3, prune middle tool results
- [x] 4.7 Реализовать `_summarize_conversation(history)` — Фаза 2: LLM суммаризация средних сообщений
- [x] 4.8 Guard: history <= 5 → вернуть без изменений
- [x] 4.9 Суммаризировать средние сообщения, сохранить начало + конец
- [x] 4.10 Написать тесты: prune с достаточным уменьшением
- [x] 4.11 Написать тесты: prune недостаточно → summarize
- [x] 4.12 Написать тесты: условие срабатывания (limit - reserved)
- [x] 4.13 Написать тесты: короткая история (<= 5) → без compaction

### 5. ExecutionEngine — замена AgentOrchestrator

> **Заменяет** `AgentOrchestrator`. Композиция из переиспользуемых компонентов. Миграция атомарная — после завершения `AgentOrchestrator` удаляется.

- [x] 5.1 Создать `codelab/src/codelab/server/agent/execution_engine.py`
- [x] 5.2 Создать `ExecutionEngine` с композицией: `HistoryBuilder`, `ToolFilter`, `MessageSanitizer`, `PlanExtractor` (существующий), `ContextCompactor`
- [x] 5.3 Реализовать `build_context(session, prompt, mcp_manager?) → AgentContext`:
  - `HistoryBuilder.build()` — конвертация истории
  - `ToolFilter.filter()` — фильтрация инструментов + MCP
  - `MessageSanitizer.sanitize()` — исправление orphaned tool calls
  - Переиспользовать существующий `PlanExtractor` из `server/agent/plan_extractor.py`
- [x] 5.4 Реализовать `ensure_context_fits(session_id) → tuple[list[LLMMessage], bool, str]`
  - Использовать `ContextCompactor.compact_if_needed()`
- [x] 5.5 Написать тесты: поток build context
- [x] 5.6 Написать тесты: ensure_context_fits с compaction

### 6. SingleStrategy

- [x] 6.1 Создать пакет `codelab/src/codelab/server/protocol/handlers/strategies/` с `__init__.py`
- [x] 6.2 Создать `codelab/src/codelab/server/protocol/handlers/strategies/single_strategy.py`
- [x] 6.3 Создать класс `SingleStrategy` с полями: `event_bus`, `execution_engine`, `tracer`
- [x] 6.4 Реализовать `execute(context) → AgentResponse`:
  - Построить `AgentRequest` из context
  - Вызвать `event_bus.send_request(request, parent_span)`
  - Вернуть `AgentResponse` (DomainEvent от шины)
- [x] 6.5 Интегрировать Tracer: `start_span("single_strategy")` → `end_span`
- [x] 6.6 Интегрировать ContextCompactor: `ensure_context_fits` перед LLM call
- [x] 6.7 Написать unit тесты: execute → send_request → AgentResponse
- [x] 6.8 Написать unit тесты: интеграция compaction контекста
- [x] 6.9 Написать integration тесты: полный цикл через EventBus + LLMAdapter

### 7. Интеграция PromptOrchestrator

> **Миграция:** `ExecutionEngine` заменяет `AgentOrchestrator` в pipeline. `LLMLoopStage` получает `ExecutionEngine` + `AgentEventBus` вместо `AgentOrchestrator`.

- [x] 7.1 Обновить `prompt_orchestrator.py` — передать `ExecutionEngine` в meta контекста вместо `AgentOrchestrator`
- [x] 7.2 Обновить `LLMLoopStage` — использовать `ExecutionEngine.build_context()` + `SingleStrategy.execute()` вместо `agent_orchestrator.process_prompt()`
- [x] 7.3 После полной миграции удалить `AgentOrchestrator` из кодовой базы
- [x] 7.4 Написать тесты: интеграция с pipeline
