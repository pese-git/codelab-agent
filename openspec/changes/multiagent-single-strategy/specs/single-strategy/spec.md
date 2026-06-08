# Spec: single-strategy

## ДОБАВЛЕННЫЕ Требования

### Требование: Выполнение SingleStrategy

Система ДОЛЖНА предоставлять `SingleStrategy`, которая:
- Вызывает единственного зарегистрированного агента через `EventBus.send_request()`
- Возвращает `AgentBusResponse` вызывающему
- Использует тот же паттерн вызова, что и все остальные стратегии (uniformity)

### Требование: Поток SingleStrategy

SingleStrategy ДОЛЖНА:
1. Построить `AgentRequest` из контекста (messages, tools, correlation_id, session_id, model)
2. Вызвать `event_bus.send_request(request, parent_span)`
3. Вернуть `AgentBusResponse` вызывающему

### Требование: Без валидации mode

SingleStrategy НЕ ДОЛЖНА проверять `mode` агента — любой зарегистрированный агент (primary, subagent, orchestrator) работает идентично.

# Spec: execution-engine

## ДОБАВЛЕННЫЕ Требования

### Требование: Композиция ExecutionEngine

Система ДОЛЖНА предоставлять `ExecutionEngine`, состоящий из:
- `HistoryBuilder` — конвертирует SessionState.history в список LLMMessage (рефакторинг из AgentOrchestrator)
- `ToolFilter` — фильтрует инструменты по runtime capabilities клиента + MCP tools (рефакторинг из AgentOrchestrator)
- `MessageSanitizer` — восстанавливает orphaned tool calls (рефакторинг из AgentOrchestrator)
- `PlanExtractor` — извлекает план из ответа LLM (переиспользование существующего)
- `ContextCompactor` — двухфазное сжатие контекста (новый компонент)

> **Примечание:** `ExecutionEngine` **заменяет** `AgentOrchestrator`. После полной миграции `AgentOrchestrator` удаляется.

### Требование: HistoryBuilder

HistoryBuilder ДОЛЖЕН:
- Конвертировать записи SessionState.history в формат LLMMessage
- Поддерживать форматы: `{"role","text"}`, `{"role","content"}`, `{"role","tool_calls"}`
- Обрабатывать сообщения tool calls с tool_call_id
- Конвертировать content list → str для text блоков
- Обрабатывать Pydantic модели через `model_dump()`
- Поддерживать опциональный system prompt как первый элемент результата

### Требование: ToolFilter

ToolFilter ДОЛЖЕН:
- Серверные инструменты (kind: think, plan) всегда включать независимо от capabilities
- Если runtime_capabilities равен None → вернуть только серверные инструменты
- Фильтровать fs/* инструменты по capabilities fs_read/fs_write
- Фильтровать terminal/* инструменты по capability terminal
- MCP инструменты включать всегда (выполняются на сервере, не зависят от client capabilities)

### Требование: MessageSanitizer

MessageSanitizer ДОЛЖЕН:
- Обнаруживать assistant сообщения с tool_calls, но без tool results
- Вставлять synthetic tool result: "Error: Tool execution did not complete"
- Возвращать исправленный список сообщений

### Требование: ExecutionEngine.build_context

`build_context(session, prompt, mcp_manager?)` ДОЛЖЕН:
1. Вызвать `HistoryBuilder.build(session.history)` → list[LLMMessage]
2. Вызвать `ToolFilter.filter(all_tools, runtime_capabilities, mcp_tools)` → list[ToolDefinition]
3. Вызвать `MessageSanitizer.sanitize(history)` → list[LLMMessage]
4. Вернуть `AgentContext` с собранными данными

# Spec: context-compaction

## ДОБАВЛЕННЫЕ Требования

### Требование: Двухфазная Compaction

Система ДОЛЖНА предоставлять `ContextCompactor` с двумя фазами:

**Фаза 1 — Prune:**
- Удалить самые старые tool result сообщения (FIFO)
- Не требует LLM вызовов
- Сохранить первые 2 сообщения (system + initial prompt)
- Сохранить последние 3 сообщения (recent context)
- Guard: если history <= 5 сообщений, вернуть без изменений

**Фаза 2 — LLM Summarize:**
- Если prune недостаточно, суммаризировать средние сообщения через LLM
- Сохранить первые 2 сообщения
- Суммаризировать середину в одно сообщение
- Сохранить последние 3 сообщения

### Требование: Условие срабатывания

Compaction ДОЛЖНА срабатывать когда: `context_tokens > context_window_limit - compaction_reserved_tokens`

### Требование: Возврат Compaction

Метод `compact_if_needed()` ДОЛЖЕН возвращать:
- `(new_history: list[LLMMessage], was_compacted: bool, method: str)`
- method: "none" | "prune" | "summarize"
