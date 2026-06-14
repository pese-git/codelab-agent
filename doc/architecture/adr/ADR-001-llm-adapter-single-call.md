# ADR-001: LLMAdapter — Single Call Pattern

**Дата:** 9 июня 2026  
**Статус:** Принято  
**Контекст:** Интеграция мультиагентной архитектуры

## Контекст

В рамках изменения `multiagent-llm-adapter` (архивировано 2026-06-08) задача 1.4 была сформулирована как:

> "Реализовать внутренний метод `_execute()`: цикл LLM вызовов (макс. 5 итераций)"

Это привело к реализации цикла tool-calling внутри `LLMAdapter._execute()`, что противоречит:

1. **Технической спецификации** (§3.4): "LLMAdapter сохраняет: **Single LLM call pattern**"
2. **Архитектурному разделению слоёв** (§2.2): Agent Layer (LLMAdapter) ≠ ACP Layer (LLMLoopStage)
3. **Существующей реализации LLMAdapter** (`llm_adapter.py`): один `create_completion()`, цикл в LLMLoopStage

### Проблемы дублирующегося цикла

| Проблема | Описание |
|----------|----------|
| Два цикла | LLMAdapter (5 итераций) + LLMLoopStage (10 итераций) — непредсказуемое поведение |
| Bypass permissions | Tool execution в LLMAdapter обходит PermissionManager |
| Bypass MCP | LLMAdapter передаёт `session_id=""` — MCP executor не работает |
| Bypass notifications | LLMLoopStage отправляет `session/update` клиенту, LLMAdapter — нет |
| Блокировка стратегий | OrchestratedStrategy требует один LLM call для маршрутизации; цикл блокирует delegation |

## Решение

**LLMAdapter делает ровно ОДИН вызов LLM провайдера.** Цикл tool-calling, permissions, MCP, notifications — ответственность LLMLoopStage.

### Изменения

| Компонент | Изменение |
|-----------|-----------|
| `LLMAdapter` | Удалён `_execute()` цикл (~129 строк). `call()` → один `create_completion()` |
| `SingleStrategy` | Фикс: конвертация `ToolCall → LLMToolCall`, проброс `usage` |
| `AgentFactory` | Новый: создание LLMAdapter per-agent с правильной моделью |
| `AgentRegistry` | Заменён stub handler на реальный LLMAdapter через AgentFactory |
| `StrategyDispatcher` | Новый: routing по mode (single, multi_orchestrated, ...) |
| `LLMLoopStage` | Добавлен feature flag `use_event_bus` для безопасной миграции |
| `ChoreographyAnswer` | Добавлено поле `tool_calls: list[ToolCall]` |

### Feature flag миграции

```python
# codelab.toml
[agents]
use_event_bus = false  # по умолчанию — legacy путь
```

- `false` (default): legacy путь через `AgentOrchestrator → NaiveAgent` (удалён 2026-06-12)
- `true`: новый путь через `StrategyDispatcher → SingleStrategy → EventBus → LLMAdapter`

## Последствия

### Положительные

- ✅ Соответствие спецификации (§3.4: "Single LLM call pattern")
- ✅ Tool execution через PermissionManager, MCP, notifications
- ✅ Поддержка всех 4 стратегий (single, orchestrated, choreography, hierarchical)
- ✅ Separation of concerns: LLMAdapter ≠ инфраструктура
- ✅ Безопасная миграция через feature flag

### Отрицательные

- ⚠️ Архивная задача 1.4 была сформулирована неверно (документально зафиксировано)
- ⚠️ ~50 тестов обновлено (удалены тесты цикла, добавлены тесты single call)
- ⚠️ LLMAdapter уменьшился с 368 до ~250 строк (удаление цикла)

### Нейтральные

- `AgentOrchestrator` и `NaiveAgent` удалены (2026-06-12), заменены на `ExecutionEngine` + `LLMAdapter`
- 3558 существующих тестов остаются зелёными (feature flag = false по умолчанию)

## Ссылки

| Документ | Раздел |
|----------|--------|
| `doc/architecture/MULTIAGENT_TECHNICAL_SPECIFICATION.md` | §3.4: LLMAdapter spec |
| `doc/architecture/MULTIAGENT_TECHNICAL_SPECIFICATION.md` | §2.2: Layer boundaries |
| `openspec/changes/archive/2026-06-08-multiagent-llm-adapter/tasks.md` | Задача 1.4 (ошибка формулировки) |
| `codelab/src/codelab/server/agent/llm_adapter.py` | LLMAdapter.call() (эталон single call) |
