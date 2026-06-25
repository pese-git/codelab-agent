# Phase 0 — Каркас + контракты (спецификация для разработки)

> **Статус:** Готово к разработке — [ADR-002](../architecture/adr/ADR-002-context-manager-consolidation.md)
> **Длительность:** 1 неделя
> **Цель:** заморозить контракты и заложить фундамент `baseline/tail`, не меняя поведения системы (флаг `enabled=false` → работает legacy).

Phase 0 — это **точка входа** в реализацию. После неё интерфейсы не меняются по сигнатурам;
последующие фазы добавляют только реализации. Опирается на [INTERFACES.md](./INTERFACES.md)
и [DATA_MODELS.md](./DATA_MODELS.md).

---

## Задачи

### T0.1 — Скелет пакета и модели данных
- Создать пакет `src/codelab/server/agent/context/`.
- `models.py` — все dataclass из [DATA_MODELS.md](./DATA_MODELS.md): `PayloadEnvelope`, `TaskProfile`, `ContextItem`, `ContextEpoch`, `ContextSnapshot`, `ReconcileResult`, `SubagentResult`, `BudgetAllocation`, `BuildOptions`, `ContextConfig`, енумы.
- **Acceptance:** модели импортируются, `PayloadEnvelope.to_messages()` и `ContextSnapshot.diff()` покрыты unit-тестами.

### T0.2 — Заморозка ABC
- `interfaces.py` (или по файлам слоёв) — все ABC из [INTERFACES.md](./INTERFACES.md): `ContextManager`, `TaskAnalyzer`, `ContextGatherer`, `DependencyGraph`, `TokenBudgetManager`, `ContextSource`, `ContextRegistry`, `ConversationSummarizer`, `ContextReconciler`, `TokenCounter`, `CodeSkeletonizer`, `FileContentCache`, `ContextCompactor`, `ChildSessionManager`.
- **Acceptance:** все ABC объявлены, `@abstractmethod` проставлены; попытка инстанцировать падает; mypy/pyright проходит.

### T0.3 — `PayloadEnvelope` в пути формирования (фундамент)
- Ввести `PayloadEnvelope` как возвращаемый тип сборки контекста в `ExecutionEngine.build_context()`.
- Адаптер `to_messages()` на границе с `LLMAdapter` (он по-прежнему получает `list[LLMMessage]`).
- **Acceptance:** payload проходит через `PayloadEnvelope`; в MVP `baseline` = весь стабильный префикс, `tail` = текущий ход; внешнее поведение не изменилось.

### T0.4 — Feature-флаги `agents.context.*`
- `ContextConfig` + загрузчик TOML `[agents.context.*]` + env-overrides `CODELAB_CONTEXT_*`.
- Депрекейт `agents.context.enable_fcm` → алиас на `agents.context.enabled` с warning.
- **Acceptance:** `enabled=false` (default) → используется legacy `ContextCompactor`; env перекрывает TOML; депрекейт-warning логируется.

### T0.5 — Legacy-мост
- Обернуть существующий `context_compactor.py` в реализацию `ContextCompactor(ABC)` без изменения логики (сигнатура `compact_if_needed()` уже совместима).
- `ExecutionEngine` выбирает реализацию по флагу `enabled`.
- **Acceptance:** при `enabled=false` поведение бит-в-бит как до Phase 0; все существующие тесты `test_context_compactor.py` зелёные.

### T0.6 — Архивация FCM-доков
- Перенести `doc/internals/architecture/fcm/` → `doc/internals/archive/fcm/` с шапкой-редиректом на ADR-002 и канон.
- Обновить ссылки в `doc/internals/`.
- **Acceptance:** канон — `doc/internals/context-manager/`; `fcm/` в архиве; битых ссылок нет.

---

## Definition of Done для Phase 0

- [ ] Пакет `context/` с моделями и ABC создан, типизация проходит.
- [ ] `PayloadEnvelope` (baseline/tail) — в пути формирования payload.
- [ ] Флаги `agents.context.*` + env-overrides работают; `enable_fcm` задепрекейчен.
- [ ] `enabled=false` → legacy-поведение без регрессий (все тесты зелёные).
- [ ] FCM-доки архивированы, канон един.
- [ ] Интерфейсы зафиксированы в `INTERFACES.md` и помечены как замороженные.

---

## Что Phase 0 НЕ делает (важно)

- Не реализует сбор контекста (`TaskAnalyzer`/`Gatherer`) — это Phase 1.
- Не реализует слой C (кэш/скелетонайзер/tiktoken) — Phase 2.
- Не реализует инкрементальность (`Epoch`/`Snapshot`/`Reconciliation`) — Phase 4, но **форма данных под неё закладывается здесь**.
- Не меняет поведение при `enabled=false`.

---

## Риски и митигации

| Риск | Митигация |
|------|-----------|
| `PayloadEnvelope` протечёт «плоским» списком и форма размоется | Code-review правило: сборка возвращает только `PayloadEnvelope`; `LLMAdapter` — единственная точка `to_messages()` |
| Депрекейт `enable_fcm` сломает существующие конфиги | Алиас + warning, не hard-fail; удаление — отдельной задачей в Phase 5+ |
| Заморозка интерфейсов окажется неполной → ломающие правки позже | Phase 0 ревьюится всеми владельцами слоёв до старта Phase 1 |
