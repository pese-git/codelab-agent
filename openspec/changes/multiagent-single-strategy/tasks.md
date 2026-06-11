## Tasks

### 1. HistoryBuilder

- [ ] 1.1 Создать `codelab/src/codelab/server/agent/history_builder.py`
- [ ] 1.2 Реализовать `HistoryBuilder.build(session_history) → list[LLMMessage]`
- [ ] 1.3 Поддержка форматов: {"role","text"}, {"role","content"}, {"role","tool_calls"}
- [ ] 1.4 Написать тесты: конвертация различных форматов history

### 2. ToolFilter

- [ ] 2.1 Создать `codelab/src/codelab/server/agent/tool_filter.py`
- [ ] 2.2 Реализовать `ToolFilter.filter(tools, capabilities) → list[ToolDefinition]`
- [ ] 2.3 Обработка: capabilities is None → вернуть []
- [ ] 2.4 Фильтрация fs/* по fs_read/fs_write
- [ ] 2.5 Фильтрация terminal/* по terminal
- [ ] 2.6 Написать тесты: фильтрация с различными capabilities

### 3. MessageSanitizer

- [ ] 3.1 Создать `codelab/src/codelab/server/agent/message_sanitizer.py`
- [ ] 3.2 Реализовать `MessageSanitizer.sanitize(messages) → list[LLMMessage]`
- [ ] 3.3 Детекция orphaned tool calls: assistant с tool_calls, но нет tool results
- [ ] 3.4 Вставка synthetic tool result: "Error: Tool execution did not complete"
- [ ] 3.5 Написать тесты: обнаружение и исправление orphaned tool calls

### 4. ContextCompactor

- [ ] 4.1 Создать `codelab/src/codelab/server/agent/context_compactor.py`
- [ ] 4.2 Реализовать `ContextCompactor.__init__`: llm, model, max_context_tokens, reserved_tokens
- [ ] 4.3 Реализовать `compact_if_needed(history) → tuple[list[Message], bool, str]`
- [ ] 4.4 Реализовать `_prune_old_tool_outputs(history)` — Фаза 1: FIFO удаление
- [ ] 4.5 Guard: history <= 5 → вернуть без изменений
- [ ] 4.6 Сохранить первые 2 сообщения, последние 3, prune middle tool results
- [ ] 4.7 Реализовать `_summarize_conversation(history)` — Фаза 2: LLM суммаризация
- [ ] 4.8 Guard: history <= 5 → вернуть без изменений
- [ ] 4.9 Суммаризировать средние сообщения, сохранить начало + конец
- [ ] 4.10 Написать тесты: prune с достаточным уменьшением
- [ ] 4.11 Написать тесты: prune недостаточно → summarize
- [ ] 4.12 Написать тесты: условие срабатывания (limit - reserved)
- [ ] 4.13 Написать тесты: короткая история (<= 5) → без compaction

### 5. ExecutionEngine

- [ ] 5.1 Создать `codelab/src/codelab/server/agent/execution_engine.py`
- [ ] 5.2 Создать `ExecutionEngine` с композицией: HistoryBuilder, ToolFilter, MessageSanitizer, PlanExtractor, ContextCompactor
- [ ] 5.3 Реализовать `build_context(session, prompt) → AgentContext`
- [ ] 5.4 Реализовать `ensure_context_fits(session_id) → tuple[list[Message], bool]`
- [ ] 5.5 Написать тесты: поток build context
- [ ] 5.6 Написать тесты: ensure_context_fits с compaction

### 6. SingleStrategy

- [ ] 6.1 Создать пакет `codelab/src/codelab/server/protocol/handlers/strategies/` с `__init__.py`
- [ ] 6.2 Создать `codelab/src/codelab/server/protocol/handlers/strategies/single_strategy.py`
- [ ] 6.3 Создать класс `SingleStrategy` с полями: event_bus, execution_engine, tracer
- [ ] 6.4 Реализовать `execute(context) → AgentResponse`:
  - Построить AgentRequest из context
  - Вызвать event_bus.send_request(request, parent_span)
  - Вернуть AgentResponse
- [ ] 6.5 Интегрировать Tracer: start_span("single_strategy") → end_span
- [ ] 6.6 Интегрировать ContextCompactor: ensure_context_fits перед LLM call
- [ ] 6.7 Написать unit тесты: execute → send_request → response
- [ ] 6.8 Написать unit тесты: интеграция compaction контекста
- [ ] 6.9 Написать integration тесты: полный цикл через EventBus + LLMAdapter

### 7. Интеграция PromptOrchestrator

- [ ] 7.1 Обновить `prompt_orchestrator.py` для использования ExecutionEngine вместо AgentOrchestrator
- [ ] 7.2 Интегрировать SingleStrategy в LLMLoopStage
- [ ] 7.3 Написать тесты: интеграция с pipeline
