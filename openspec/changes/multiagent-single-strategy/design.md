## Design

### Архитектура SingleStrategy

SingleStrategy — базовая стратегия выполнения, вызывает единственного агента через EventBus. Принцип uniformity — тот же паттерн вызова, что и все остальные стратегии.

### Композиция ExecutionEngine

```python
class ExecutionEngine:
    _history_builder: HistoryBuilder      # session.history → LLMMessage
    _tool_filter: ToolFilter              # filter by capabilities + MCP
    _sanitizer: MessageSanitizer          # fix orphaned tool calls
    _plan_extractor: PlanExtractor        # extract plan from response (существующий)
    _compactor: ContextCompactor          # prune + summarize
```

### Переиспользование существующего кода

| Компонент | Существующая реализация | Действие |
|-----------|------------------------|----------|
| History conversion | `AgentOrchestrator._convert_to_llm_messages()` | Рефакторинг → `HistoryBuilder` |
| Tool filtering | `AgentOrchestrator._filter_tools_by_capabilities()` | Рефакторинг → `ToolFilter` |
| Message sanitization | `AgentOrchestrator._sanitize_orphaned_tool_calls()` | Рефакторинг → `MessageSanitizer` |
| Plan extraction | `agent/plan_extractor.py` | Переиспользовать напрямую |
| Tool name mapping | `server/tools/mapping.py` | Переиспользовать напрямую |
| LLM models | `server/llm/models.py` | Переиспользовать `LLMMessage`, `LLMToolCall` |
| Tool definitions | `server/tools/base.py` | Переиспользовать `ToolDefinition` |
| MCP integration | `server/mcp/manager.py` | Переиспользовать через `ToolFilter` |

### Миграция архитектуры

`AgentOrchestrator` **заменяется** на `ExecutionEngine` — миграция атомарная, без периода сосуществования:

- `AgentOrchestrator.process_prompt()` → `ExecutionEngine.build_context()` + `SingleStrategy.execute()`
- `AgentOrchestrator.continue_with_tool_results()` → `ExecutionEngine.ensure_context_fits()` + `SingleStrategy.execute()`
- После миграции `AgentOrchestrator` удаляется из кодовой базы

### HybridContextManager (для мультиагентных стратегий)

`HybridContextManager` координирует три механизма управления контекстом:

```python
class HybridContextManager:
    _slicer: TokenSlicer              # суммаризация ответов субагентов
    _compactor: ContextCompactor      # двухфазный compaction: Prune + LLM Summarize
    _storage: SessionStorage          # создание и связывание child sessions
```

**Два независимых метода:**
- `ensure_context_fits()` — только ContextCompactor (Prune + LLM Summarize), без TokenSlicer
- `process_subagent_response()` — TokenSlicer + Child Session creation

**Когда стратегии вызывают:**

| Стратегия | Когда вызывает | Какой метод |
|-----------|---------------|-------------|
| **Single** | Перед LLM call | `ensure_context_fits()` — только compaction |
| **Orchestrated** | После каждого sub-agent response | `process_subagent_response()` + `ensure_context_fits()` |
| **Choreography** | После conflict resolution (winner) | `process_subagent_response()` — только для winner |
| **Hierarchical** | При возврате TaskResult из child session | `process_subagent_response()` + `ensure_context_fits()` |

### Ключевые решения

| Решение | Обоснование |
|---|---|
| Через EventBus | Uniformity, observability, testing |
| Композиция вместо монолита | Тестируемость, расширяемость |
| Compaction fallback | Двухфазный: Prune → LLM Summarize |
| Без Token-Slicing в Single | Нет субагентов — не нужно сжимать |
| MCP tools всегда доступны | Выполняются на сервере, не зависят от client capabilities |

### Compaction Flow

```
1. Перед LLM call: check context tokens
2. Если > trigger (limit - reserved):
   a. Prune: удалить старые tool outputs (FIFO, без LLM)
   b. Если недостаточно → LLM Summarize: сжать середину conversation
3. Сохранить первые 2 сообщения (system + initial prompt)
4. Сохранить последние 3 сообщения (recent context)
```
