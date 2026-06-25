# Phase 6 — Мультиагент (спецификация для разработки)

> **Статус:** Готово к разработке после предыдущих фаз — [ADR-002](../architecture/adr/ADR-002-context-manager-consolidation.md)
> **Длительность:** 2 недели
> **Цель:** реализовать обработку ответов субагентов (`process_subagent_response`) и изоляцию субагентов в child-сессиях через `ChildSessionManager` — это **дефолт и единственный путь MVP**. Федеративный `share_item()` — опционально за флагом и кандидат на отказ.

Phase 6 опирается на `ContextManager.process_subagent_response()` ([INTERFACES.md §1](./INTERFACES.md)),
`ChildSessionManager` ([INTERFACES.md §5](./INTERFACES.md)) и `SubagentResult` ([DATA_MODELS.md §5](./DATA_MODELS.md)),
замороженные в Phase 0. Используется только мультиагентными стратегиями (Orchestrated/Choreography/Hierarchical).
См. [CONSOLIDATED_ARCHITECTURE.md §10 (Phase 6)](./CONSOLIDATED_ARCHITECTURE.md) и [§8 (мультиагент)](./CONSOLIDATED_ARCHITECTURE.md).

> **ВАЖНО про федерацию.** Федеративный `share_item()` — **кандидат на отказ** (ADR-002 §«Мультиагент»):
> его выгоды уже покрыты `FileContentCache` из Phase 2 (общий кэш содержимого файлов между сессиями)
> и `process_subagent_response` (суммаризованный возврат результата родителю). Федерация включается
> **только при обоснованном сценарии**, не закрываемом изоляцией; **бремя доказательства — на том, кто включает флаг**.

---

## Задачи

### T6.1 — Изоляция субагентов в child-сессиях (дефолт MVP)
- Реализовать `ChildSessionManager.create_child(parent, subagent_scope)`: создание изолированной `SessionState` для субагента с собственным контекстом.
- Реализовать `ChildSessionManager.collect_summary(child)` → `SubagentResult` с суммаризованным результатом.
- Это **единственный путь MVP**: субагент не делит контекст с родителем напрямую.
- **Acceptance:** субагент работает в изолированной child-сессии; контекст родителя не загрязняется промежуточными ходами субагента; `collect_summary` возвращает `SubagentResult`.

### T6.2 — process_subagent_response (суммаризация → родитель)
- Реализовать `ContextManager.process_subagent_response(parent_scope, subagent_scope, response)` → `SubagentResult`.
- По умолчанию — суммаризация (изоляция): результат субагента сворачивается в `SubagentResult.summary` через `ConversationSummarizer`; `shared_items` пуст.
- Родитель получает только `summary` (+ `token_count`, `source_scope`) как `agent_report` (`ContextType.AGENT_REPORT`, priority=7).
- **Acceptance:** родитель получает суммаризованный результат в `SubagentResult.summary`; без федерации `shared_items == []`; токены родителя растут на размер summary, а не полного диалога субагента.

### T6.3 — Федеративный share_item() (опционально, за флагом)
- Добавить федеративный путь шеринга `ContextItem` между сессиями: `process_subagent_response` заполняет `SubagentResult.shared_items` вместо/вдобавок к суммаризации.
- За флагом `agents.context.multiagent.federation` (`ContextConfig.federation`, default `False`). При `False` путь недоступен — работает только изоляция.
- Перед включением — задокументировать сценарий, не закрываемый изоляцией + `FileContentCache`; бремя доказательства на инициаторе.
- **Acceptance:** при `federation=False` (default) федеративный путь полностью выключен, поведение = изоляция; при `federation=True` `shared_items` заполняется; в репозитории зафиксировано обоснование включения.

### T6.4 — Конфиг и наблюдаемость
- Подключить флаг к загрузчику `[agents.context.multiagent.*]` и env-overrides `CODELAB_CONTEXT_*`.
- Метрики/логи: число child-сессий, размер summary в токенах, экономия токенов родителя относительно полного диалога субагента, статус федерации (вкл/выкл).
- **Acceptance:** флаг `federation` читается из TOML/env, по умолчанию `False`; логируется режим (изоляция/федерация) и экономия токенов.

---

## Definition of Done для Phase 6

- [ ] `ChildSessionManager` изолирует субагентов в child-сессиях — дефолт и единственный путь MVP.
- [ ] `process_subagent_response` возвращает `SubagentResult.summary`; родитель не получает полный диалог субагента.
- [ ] Без федерации `shared_items` всегда пуст; контекст родителя не загрязняется.
- [ ] Федеративный `share_item()` за флагом `agents.context.multiagent.federation`, по умолчанию выключен.
- [ ] Обоснование включения федерации задокументировано; без него флаг не включается.
- [ ] Сигнатуры `ContextManager`/`ChildSessionManager` не изменены (заморозка Phase 0 соблюдена).

---

## Что Phase 6 НЕ делает (важно)

- Не делает федерацию дефолтом — путь MVP — изоляция в child-сессиях.
- Не вводит федерацию без обоснованного сценария, не закрываемого изоляцией + `FileContentCache` (Phase 2).
- Не меняет сигнатуры интерфейсов из [INTERFACES.md](./INTERFACES.md).
- Не дублирует кэш содержимого файлов — общий доступ к файлам идёт через `FileContentCache`, а не федерацию.
- Не меняет поведение одноагентной стратегии (Single) — `process_subagent_response` ей не вызывается.

---

## Риски и митигации

| Риск | Митигация |
|------|-----------|
| Федерация вводится «по инерции», хотя её выгоды покрыты Phase 2 + суммаризацией | Федерация — кандидат на отказ; флаг по умолчанию `False`; бремя доказательства на инициаторе; обоснование фиксируется в репозитории |
| Контекст родителя загрязняется промежуточными ходами субагента | Изоляция в child-сессии по умолчанию; родитель получает только `SubagentResult.summary` |
| Суммаризация теряет ключевые решения субагента | `ConversationSummarizer` с требованием сохранять решения и состояние задачи; метрика размера/полноты summary |
| Федеративный шеринг ломает кэш-стабильность baseline родителя | Federation за флагом; влияние на `baseline_fingerprint` измеряется кэш-хитом; по умолчанию выключено |
| Рост числа child-сессий нагружает рантайм | Метрика числа child-сессий; child-сессии короткоживущие, сворачиваются в summary после `collect_summary` |
