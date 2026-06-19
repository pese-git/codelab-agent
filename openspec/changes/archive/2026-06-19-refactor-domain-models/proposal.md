# Proposal: Рефакторизация доменных моделей

## Контекст

Текущие модели данных в проекте смешивают несколько уровней абстракции:
- **Domain-логика** (бизнес-сущности)
- **ACP Transport** (wire format протокола)
- **LLM-specific** (специфичные для LLM провайдеров данные)

Это нарушает принципы Clean Architecture и создаёт следующие проблемы:

### Проблема 1: Три модели `ToolCall`

В проекте существуют три разные модели `ToolCall`:
- `server/models.py:106` — Pydantic модель (мёртвый код, не используется)
- `server/agent/contracts/base.py:58` — Domain контракт шины (frozen dataclass)
- `server/protocol/state.py:150` — Protocol layer state (смешивает domain + ACP)

**Последствия:** Путаница в использовании, дублирование логики, сложность поддержки.

### Проблема 2: `HistoryMessage` — union из 3 типов

```python
class HistoryMessage(BaseModel):
    content: list[MessageContent] | str | list[dict[str, Any]] | None
    text: str | None  # дублирует content
```

**Последствия:** Невозможно типизировать код, работающий с историей. Domain модель зависит от transport формата.

### Проблема 3: `SessionState` — God Object

`SessionState` содержит 30+ полей и отвечает за:
- Хранение конфигурации
- Хранение истории
- Управление tool calls
- Управление permissions
- Управление plans
- Multi-agent поддержку

**Последствия:** Нарушение SRP, сложность тестирования, невозможность переиспользования компонентов.

### Проблема 4: `AgentContext.prompt` — ACP format в domain

```python
@dataclass
class AgentContext:
    prompt: list[dict[str, Any]]  # ACP ContentBlock format
```

**Последствия:** Domain модель зависит от transport формата. Невозможно эволюционировать domain независимо.

### Проблема 5: `AgentResponse.tool_calls` — LLM model в domain

```python
@dataclass
class AgentResponse:
    tool_calls: list[LLMToolCall]  # LLM-specific
```

**Последствия:** Domain контракт зависит от infrastructure (LLM провайдер).

### Проблема 6: `ToolExecutionResult.content` — ACP format в domain

```python
@dataclass
class ToolExecutionResult:
    content: list[dict[str, Any]]  # ACP ContentBlock
```

**Последствия:** Domain модель знает про transport. Невозможно переиспользовать executor для других протоколов.

### Проблема 7: `PlanStep` не соответствует ACP spec

Текущие поля: `step_number`, `description`, `status`, `result`
ACP spec (11-Agent Plan.md): `content`, `priority`, `status`

**Последствия:** Несоответствие спецификации, путаница при маппинге.

### Проблема 8: Клиент `Session` — нет бизнес-логики

```python
@dataclass
class Session:
    client_capabilities: dict[str, Any]  # нет типизации
```

**Последствия:** Нет инкапсуляции бизнес-логики, все поля — `dict[str, Any]`.

## Решение

Разделить модели на уровни согласно Clean Architecture:

1. **Domain Layer** — бизнес-сущности (frozen dataclass)
2. **Protocol/Transport Layer** — DTO для ACP wire format (Pydantic)
3. **Mapping Layer** — конвертеры между слоями

### Принципы

- **SRP** — каждая модель отвечает за один уровень
- **DIP** — domain не зависит от transport/infrastructure
- **OCP** — добавление нового типа не требует изменения существующих моделей
- **Testability** — domain модели тестируются изолированно

## Цели

1. Устранить дублирование моделей `ToolCall`
2. Разделить `HistoryMessage` на domain и transport
3. Разбить `SessionState` на агрегаты
4. Устранить ACP/LLM зависимости из domain моделей
5. Ввести типизированные модели вместо `dict[str, Any]`
6. Обеспечить обратную совместимость storage format

## Не цели

- Полная переделка архитектуры проекта
- Изменение ACP протокола
- Рефакторинг клиентской архитектуры (кроме `Session` entity)

## Capabilities

### New Capabilities

- `session-aggregate`: Агрегат Session с value objects (SessionConfig, ConversationHistory, ToolCallRegistry, PermissionState, AgentPlan, MultiAgentState)
- `tool-call-models`: Разделение ToolCall на domain (ToolCall) и transport (ToolCallDTO)
- `history-message-models`: Разделение HistoryMessage на domain (ConversationMessage) и transport (HistoryMessageDTO)
- `agent-context-models`: Domain модели AgentContext с UserPrompt
- `tool-execution-result-models`: Domain ToolExecutionResult без ACP content
- `plan-models`: Domain PlanEntry, соответствующий ACP spec

### Modified Capabilities

- `session-state`: Уменьшение SessionState до тонкого DTO, делегирование бизнес-логики агрегатам
- `agent-message-contracts`: Устранение дублирования ToolCall, использование domain контрактов

## Impact

**Архитектура:**
- Введение Domain Layer в server (отсутствует)
- Введение Mapping Layer на границах
- Разделение Protocol Layer на domain + DTO

**Код:**
- ~21 новых файлов (domain модели, DTO, мапперы)
- ~41 изменённых файлов (миграция на новые модели)
- ~90 новых тестов

**Storage:**
- Миграция schema_version: 3 → 4
- Обратная совместимость через model_validator

**Риски:**
- Высокий риск при миграции SessionState (20+ файлов)
- Средний риск при миграции ToolCall/HistoryMessage (5+ файлов)
- Низкий риск при создании новых domain моделей

**Митигация:**
- Поэтапная миграция (6 фаз)
- Независимые фазы можно merge отдельно
- TODO-комментарии для фиксации архитектурного долга
