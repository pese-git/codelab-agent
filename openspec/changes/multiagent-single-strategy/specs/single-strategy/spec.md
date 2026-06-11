# Spec: single-strategy

## ДОБАВЛЕННЫЕ Требования

### Требование: Выполнение SingleStrategy

Система ДОЛЖНА предоставлять `SingleStrategy`, которая:
- Вызывает единственного зарегистрированного агента через `EventBus.send_request()`
- Возвращает ответ агента вызывающему
- Использует тот же паттерн вызова, что и все остальные стратегии (uniformity)

### Требование: Поток SingleStrategy

SingleStrategy ДОЛЖНА:
1. Построить AgentRequest из контекста (messages, tools, correlation_id, session_id)
2. Вызвать `event_bus.send_request(request, parent_span)`
3. Вернуть AgentResponse вызывающему

### Требование: Без валидации mode

SingleStrategy НЕ ДОЛЖНА проверять `mode` агента — любой зарегистрированный агент (primary, subagent, orchestrator) работает идентично.

# Spec: execution-engine

## ДОБАВЛЕННЫЕ Требования

### Требование: Композиция ExecutionEngine

Система ДОЛЖНА предоставлять `ExecutionEngine`, состоящий из:
- `HistoryBuilder` — конвертирует SessionState.history в список LLMMessage
- `ToolFilter` — фильтрует инструменты по runtime capabilities клиента
- `MessageSanitizer` — восстанавливает orphaned tool calls
- `PlanExtractor` — извлекает план из ответа LLM

### Требование: HistoryBuilder

HistoryBuilder ДОЛЖЕН:
- Конвертировать записи SessionState.history в формат LLMMessage
- Поддерживать форматы: {"role","text"}, {"role","content"}, {"role","tool_calls"}
- Обрабатывать сообщения tool calls с tool_call_id

### Требование: ToolFilter

ToolFilter ДОЛЖЕН:
- Возвращать пустой список если runtime_capabilities равен None
- Фильтровать fs/* инструменты по capabilities fs_read/fs_write
- Фильтровать terminal/* инструменты по capability terminal
- Исключать инструменты без совпадающих capabilities

### Требование: MessageSanitizer

MessageSanitizer ДОЛЖЕН:
- Обнаруживать assistant сообщения с tool_calls, но без tool results
- Вставлять synthetic tool result: "Error: Tool execution did not complete"

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
- `(new_history: list[Message], was_compacted: bool, method: str)`
- method: "none" | "prune" | "summarize"
