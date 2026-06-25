# Context Manager — План интеграции стратегий

> **Статус:** Канон — [ADR-002](../architecture/adr/ADR-002-context-manager-consolidation.md)
> **Дата:** 25 июня 2026
>
> Как каждая из 4 стратегий (`Single` / `Orchestrated` / `Choreography` / `Hierarchical`)
> подключается к единому `ContextManager`. Опирается на [INTERFACES.md](./INTERFACES.md),
> [CONSOLIDATED_ARCHITECTURE.md §4](./CONSOLIDATED_ARCHITECTURE.md) и реальные контракты кода.

---

## 1. Общая точка интеграции

Все стратегии реализуют протокол `LLMCallStrategy` (`strategies/base.py`):

```python
class LLMCallStrategy(Protocol):
    async def execute(self, session, prompt, mcp_manager=None, *, system_prompt=None, ...): ...
    async def continue_execution(self, session, mcp_manager=None, ...): ...
```

Единственная точка, где стратегия соприкасается с контекстом — вызов **`ExecutionEngine.build_context()`**. Сегодня он внутри вызывает legacy `ContextCompactor`; после интеграции — делегирует в `ContextManager`.

```
Strategy.execute() / continue_execution()
   └─> ExecutionEngine.build_context(session, prompt, *, agent_scope, system_prompt)
          └─> ContextManager.build_context(...) -> PayloadEnvelope
          └─> ContextManager.ensure_context_fits(envelope, ...) -> PayloadEnvelope
   └─> request.messages = envelope.to_messages()
   └─> EventBus.send_request(request)   # для мультиагентных — N агентов
```

**Принцип:** стратегии НЕ знают о слоях A–D и о том, гидрация это или эпохи. Они работают только с `build_context()` / `ensure_context_fits()` (+ `process_subagent_response()` для мультиагента). Это и есть «единый путь» из ADR-002.

### Что меняется в `ExecutionEngine.build_context()`
- Возвращаемый тип: `AgentContext`/`ContinuationContext` → внутри строится через `PayloadEnvelope`; `context.conversation_history` = `envelope.to_messages()` (обратная совместимость для `EventBus`/`AgentRequest`).
- Новый параметр `agent_scope: str = "single"` — идентификатор скоупа агента.
- Выбор реализации (`ContextManager` vs legacy) — по флагу `agents.context.enabled`.

---

## 2. SingleStrategy

**Методы ContextManager:** `build_context()` + `ensure_context_fits()`.

| Аспект | Поведение |
|--------|-----------|
| Скоуп | один, `agent_scope="single"` (генерируется автоматически) |
| Сбор (слой A) | `TaskAnalyzer`+`Gatherer` наполняют скоуп релевантными файлами |
| Жизненный цикл (B) | гидрация (Phase 1) → инкрементальная эпоха (Phase 4) — прозрачно |
| Мультиагент (D) | не используется |

**Интеграция:**
- `execute()`: `build_context(session, prompt, agent_scope="single", system_prompt=...)` → `ensure_context_fits()` → `request.messages = envelope.to_messages()`.
- `continue_execution()`: то же, `prompt=""`; tail пополняется tool_results из `session.history`.
- **Изменения минимальны** — это эталонный путь, на нём отлаживается Phase 1.

---

## 3. OrchestratedStrategy

**Методы:** `build_context()` + `process_subagent_response()` + `ensure_context_fits()`.

| Аспект | Поведение |
|--------|-----------|
| Скоупы | оркестратор (`agent_scope="orchestrator"`) + по скоупу на суб-агента |
| Маршрутизация | оркестратор делает 1 LLM-вызов → делегирует субагенту через `EventBus` |
| Возврат результата | `process_subagent_response(parent="orchestrator", subagent=..., response)` → `SubagentResult.summary` добавляется в скоуп оркестратора |
| Изоляция (D) | субагент работает в child-сессии (`ChildSessionManager`); родителю — только суммаризация |

**Интеграция:**
- Перед делегированием: `build_context(agent_scope="orchestrator")` для решения о маршруте.
- Для каждого субагента: отдельный `build_context(agent_scope="<subagent>")`.
- После ответа субагента: `process_subagent_response(...)` — результат как `ContextType.AGENT_REPORT` (priority=7) в скоуп оркестратора.
- `ensure_context_fits()` на скоупе оркестратора между раундами делегирования.

---

## 4. ChoreographyStrategy

**Методы:** `build_context()` + `process_subagent_response()` (только для winner).

| Аспект | Поведение |
|--------|-----------|
| Скоупы | по скоупу на каждого участника broadcast |
| Координация | `EventBus.broadcast()` всем агентам; конкурентные ответы |
| Возврат результата | `process_subagent_response()` вызывается **только для победителя** (winner), остальные ответы отбрасываются |
| Изоляция (D) | каждый участник изолирован; нет общего контекста между ними |

**Интеграция:**
- Каждому участнику — свой `build_context(agent_scope="<participant>")` перед broadcast.
- После сбора ответов: выбрать winner → `process_subagent_response(parent, winner_scope, winner_response)`; ответы проигравших не вливаются в контекст (экономия токенов).
- **Без федерации:** участники не делятся items между собой (ADR-002 §«Мультиагент»).

---

## 5. HierarchicalStrategy

**Методы:** `build_context()` + `process_subagent_response()` + `ensure_context_fits()`.

| Аспект | Поведение |
|--------|-----------|
| Скоупы | дерево: родитель + child-сессии на каждый уровень |
| Координация | point-to-point + `ChildSessionManager` создаёт child-сессии для глубоких задач |
| Возврат результата | снизу вверх: `process_subagent_response()` суммаризует ответ ребёнка для родителя на каждом уровне |
| Жизненный цикл (B) | у каждого уровня свой `ContextEpoch`; `ensure_context_fits()` на каждом уровне |

**Интеграция:**
- Родитель: `build_context(agent_scope="root")`.
- Делегирование вниз: `ChildSessionManager.create_child(parent, subagent_scope)` → у ребёнка свой scope и эпоха.
- Возврат: `ChildSessionManager.collect_summary(child)` → `process_subagent_response()` → `SubagentResult.summary` родителю.
- `ensure_context_fits()` обязательно на каждом уровне — иерархия склонна к росту контекста.

---

## 6. Сводная матрица

| Стратегия | `build_context` | `ensure_context_fits` | `process_subagent_response` | Скоупы | Child-сессии |
|-----------|:---:|:---:|:---:|--------|:---:|
| Single | ✅ | ✅ | — | 1 | — |
| Orchestrated | ✅ | ✅ | ✅ | 1 + N | ✅ |
| Choreography | ✅ | — | ✅ (winner) | N | ✅ |
| Hierarchical | ✅ | ✅ | ✅ | дерево | ✅ |

---

## 7. Порядок интеграции по фазам

| Фаза | Что подключается к стратегиям |
|------|-------------------------------|
| **Phase 0** | `ExecutionEngine.build_context()` возвращает через `PayloadEnvelope`; параметр `agent_scope`; стратегии не меняют поведения (флаг off) |
| **Phase 1** | `SingleStrategy` полностью на новом `build_context()` (гидрация). Эталон отладки слоя A |
| **Phase 3** | `ensure_context_fits()` (3-фазное сжатие) включается для Single и Hierarchical |
| **Phase 4** | инкрементальные эпохи — прозрачно для всех стратегий (за тем же API) |
| **Phase 6** | `process_subagent_response()` + `ChildSessionManager` → Orchestrated / Choreography / Hierarchical |

**Вывод:** мультиагентные стратегии (Orchestrated/Choreography/Hierarchical) функционально завершаются на **Phase 6**; `SingleStrategy` работоспособна уже с **Phase 1**. Это согласовано с roadmap ADR-002 (слой D — Phase 6).

---

## 8. Требования к интеграции (инварианты)

1. **Единственная точка контекста** — стратегии вызывают только `build_context()`/`ensure_context_fits()`/`process_subagent_response()`, не обращаясь к слоям A–D напрямую.
2. **`PayloadEnvelope` не «протекает» плоским списком** — `to_messages()` вызывается только на границе с `EventBus`/`AgentRequest`.
3. **Изоляция по умолчанию** — субагенты в child-сессиях; федеративный шеринг не используется (кандидат на отказ).
4. **Прозрачность жизненного цикла** — переключение гидрация↔эпохи (флаг `lifecycle.incremental`) не требует изменений в стратегиях.
