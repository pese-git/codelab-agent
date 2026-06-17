> **Примечание:** Этот документ находится в архиве. Пути к файлам указаны в старом формате (`codelab/src/codelab/...`). Актуальная структура проекта: `src/codelab/...`

# Анализ Legacy файлов: agent/base.py и agent/state.py

> Дата: 12 июня 2026
> Статус: Утверждено
> Основание: Анализ зависимостей после рефакторинга мультиагентной архитектуры

---

## Контекст

В `MULTIAGENT_TECHNICAL_SPECIFICATION.md` (секция 10 «УДАЛЯЕМЫЕ КОМПОНЕНТЫ») указано
удалить следующие файлы после перехода на новую архитектуру:

| Файл | Причина (по spec) | Функциональность перенесена в |
|---|---|---|
| `server/agent/base.py` | Замена Agent Protocol | `server/agent/core/agent.py` |
| `server/agent/state.py` | Замена на MultiAgentConfig | `server/agent/config.py` |

Однако после рефакторинга фактическое состояние отличается от spec.

---

## server/agent/state.py — ✅ УДАЛИТЬ

### Содержимое

Единственный класс — `OrchestratorConfig` (dataclass, 27 строк):

```python
@dataclass
class OrchestratorConfig:
    enabled: bool = False
    llm_provider_class: str = "openai"
    agent_class: str = "naive"          # ← ссылается на УЖЕ УДАЛЁННЫЙ NaiveAgent
    llm_config: dict[str, Any] = field(default_factory=dict)
    model: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 8192
    enable_tools: bool = True
    tool_timeout: float = 30.0
    history_limit: int = 100
    system_prompt: str = ""
```

### Анализ зависимостей

| Потребитель | Тип зависимости |
|---|---|
| `agent/__init__.py:53` | Импорт и экспорт `OrchestratorConfig` |
| `tests/server/test_agent_base.py:6` | Импорт для 2 unit-тестов |

**Нигде больше не используется.** Конфигурация LLM и агентов теперь управляется через:
- `LLMConfig` (`server/llm/base.py`) — параметры провайдера
- `AgentsGlobalConfig` (`server/agent/config/models.py`) — мультиагентные настройки
- `ProviderConfig` (`server/toml_config/pydantic_config.py`) — TOML конфигурация

### Обоснование удаления

1. `agent_class = "naive"` — ссылается на `NaiveAgent`, который **уже удалён**
2. Все поля дублируются в современных конфигурационных классах
3. Нет потребителей кроме `__init__.py` и тестов
4. Класс не используется в DI, pipeline, стратегиях

### План удаления

1. Удалить `codelab/src/codelab/server/agent/state.py`
2. Убрать из `codelab/src/codelab/server/agent/__init__.py`:
   - Строку импорта: `from codelab.server.agent.state import OrchestratorConfig`
   - Строку экспорта: `"OrchestratorConfig"`
3. Удалить тесты в `codelab/tests/server/test_agent_base.py`:
   - `test_orchestrator_config_creation` (строки ~113-119)
   - `test_orchestrator_config_custom_values` (строки ~121-130)

---

## server/agent/base.py — ❌ НЕ УДАЛЯТЬ

### Содержимое

Классы (162 строки):

| Класс | Назначение |
|---|---|
| `AgentContext` | Контекст для `start_turn` — промпт + история + инструменты |
| `ContinuationContext` | Контекст для `continue_turn` — история с tool_results |
| `AgentResponse` (dataclass) | Результат одного LLM вызова: text, tool_calls, stop_reason, plan, usage |
| `LLMAgent` (ABC) | Абстрактный интерфейс: `start_turn`, `continue_turn`, `cancel_prompt`, `initialize`, `end_session` |

### Анализ зависимостей

**7 файлов активно используют этот модуль:**

| Файл | Что использует | Роль |
|---|---|---|
| `execution_engine.py` | `AgentContext`, `ContinuationContext` | **Критично** — сборка контекста для LLM |
| `strategies/dispatcher.py` | `AgentResponse` | Тип возврата стратегии |
| `strategies/base.py` | `AgentResponse` | Protocol `LLMCallStrategy` |
| `llm_adapter.py` | `AgentResponse` | Возврат из `handle_request()` |
| `protocol/handlers/pipeline/stages/agent_loop.py` | `AgentResponse` | Тип возврата в pipeline |
| `protocol/handlers/strategies/single_strategy.py` | `AgentResponse as BaseAgentResponse` | Конвертация результатов |
| `agent/__init__.py` | Экспорт всех классов | Публичный API модуля |

### Почему spec ошибочен

Spec секция 10 ссылается на `server/agent/core/agent.py` как замену, но:

1. **Директория `server/agent/core/` НЕ существует** — файл `core/agent.py` не был создан
2. `base.py` был **переписан**, а не остался legacy — теперь это рабочий интерфейс
3. `AgentContext` и `ContinuationContext` — **не дубликаты**, это специфичные контексты
   для двух фаз LLM вызова (новый turn vs продолжение после tool results)
4. `AgentResponse` (dataclass) — отличается от `AgentResponse` (DomainEvent) в
   `contracts/base.py`. Это **два разных класса с одинаковым именем**, код различает
   их через алиасы (`BaseAgentResponse`)

### Разрешение конфликта имён

В кодовой базе существуют два `AgentResponse`:

| Класс | Файл | Тип | Назначение |
|---|---|---|---|
| `AgentResponse` (dataclass) | `base.py:65` | Результат LLM вызова | Возвращается из `LLMAgent.start_turn()` |
| `AgentResponse` (DomainEvent) | `contracts/base.py:107` | Событие EventBus | Оборачивает `AgentResult` для шины |

Это осознанная архитектура — см. комментарий в `contracts/__init__.py`:
> «AgentResponse из contracts — это DomainEvent для EventBus,
> НЕ AgentResponse из server/agent/base.py (результат вызова LLMAgent)»

### Рекомендация

**Оставить `base.py` как есть.** Обновить `MULTIAGENT_TECHNICAL_SPECIFICATION.md`
секцию 10, убрав `base.py` из списка удаляемых файлов.

---

## Итоговая таблица

| Файл | Действие | Причина |
|---|---|---|
| `server/agent/state.py` | **Удалить** | Legacy, `agent_class="naive"` ссылается на удалённый класс, нет потребителей |
| `server/agent/base.py` | **Оставить** | Активно используется 7 файлами, содержит рабочие классы, spec устарел |
| `server/agent/naive.py` | Уже удалён | ✅ |
| `server/agent/orchestrator.py` | Уже удалён | ✅ |
| `server/agent/plan_extractor.py` | Уже перенесён | ✅ → `adapters/plan_extractor.py` |

---

## Обновление спецификации

Необходимо обновить `MULTIAGENT_TECHNICAL_SPECIFICATION.md` секцию 10:

**Было:**
```
| server/agent/base.py | Замена Agent Protocol | server/agent/core/agent.py |
```

**Стало:**
```
| server/agent/base.py | НЕ УДАЛЯТЬ — переписан, содержит рабочие классы
  (AgentContext, ContinuationContext, AgentResponse, LLMAgent),
  активно используется в ExecutionEngine и pipeline |
```
