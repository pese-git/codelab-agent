# Spec: llm-adapter

## ДОБАВЛЕННЫЕ Требования

### Требование: Реализация LLMAgent Protocol

Система ДОЛЖНА предоставлять `LLMAdapter`, реализующий протокол `LLMAgent`:

```python
async def call(
    messages: list[LLMMessage],
    tools: list[ToolDefinition] | None = None,
    config: dict | None = None,
    parent_span: SpanContext | None = None,
) -> AgentResult:
```

> **Примечание:** Использовать `LLMMessage` из `server/llm/models.py`, `ToolDefinition` из `server/tools/base.py`.

### Требование: Единственный LLM вызов

LLMAdapter ДОЛЖЕН:
- Вызывать LLM провайдер с messages и tools ровно один раз
- Возвращать `AgentResult` с text, tool_calls, usage, stop_reason, agent_name
- Поддерживать отмену через asyncio.Task

> **Архитектурное решение:** LLMAdapter делает ровно один вызов LLM провайдера.
> Цикл tool-calling выполняется в LLMLoopStage/AgentLoop, а не в LLMAdapter.
> Это обеспечивает единую точку для permissions, MCP, notifications.
> См. [ADR-001](../../../doc/architecture/adr/ADR-001-llm-adapter-single-call.md).

### Требование: Регистрация в EventBus

LLMAdapter ДОЛЖЕН регистрировать себя как `RequestHandler` в AgentEventBus:

```python
async def _handle_request(request: AgentRequest, parent_span: SpanContext | None) -> AgentResult:
    result = await self.call(request.messages, request.tools, parent_span=parent_span)
    return result
```

> **Примечание:** Возвращает `AgentResult` напрямую. Шина оборачивает в `AgentResponse` (DomainEvent) с добавлением `request_id`.

### Требование: Поддержка отмены

LLMAdapter ДОЛЖЕН поддерживать отмену через `asyncio.Task`:
- Отслеживать активные задачи в dict `_active_tasks`
- Возвращать `AgentResult(stop_reason="cancelled")` при отмене
- Очищать ссылку на задачу при завершении

### Требование: Переиспользование существующих компонентов

LLMAdapter ДОЛЖЕН переиспользовать:
- `acp_name_to_llm_name()` из `server/tools/mapping.py` для конвертации имён инструментов
- `PlanExtractor` из `server/agent/plan_extractor.py` для извлечения плана из ответа

# Spec: agent-result-usage

## ДОБАВЛЕННЫЕ Требования

### Требование: Сохранение Usage

`AgentResult` ДОЛЖЕН включать поле `usage: dict | None` с информацией о токенах из ответа LLM провайдера:
- `input_tokens: int`
- `output_tokens: int`
- `total_tokens: int`

Эта информация ДОЛЖНА сохраняться из ответа LLM провайдера и не теряться при обработке.

> **Примечание:** `usage` может быть `None` если провайдер не вернул информацию о токенах (например, Mock провайдер).

# Spec: llm-tracing

## ДОБАВЛЕННЫЕ Требования

### Требование: Tracer Span для каждого LLM вызова

Каждый LLM вызов ДОЛЖЕН создавать span трассировки с:
- Имя: "llm_call"
- Родитель: parent_span из AgentRequest
- Атрибуты: model, provider, input_tokens, output_tokens, latency_ms

### Требование: Распространение контекста Span

LLMAdapter ДОЛЖЕН распространять контекст span через цепочку вызовов:
- parent_span → span LLM вызова → spans выполнения инструментов
