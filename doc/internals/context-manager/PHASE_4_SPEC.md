# Phase 4 — Инкрементальность (спецификация для разработки)

> **Статус:** Готово к разработке после Phase 0–3 — [ADR-002](../architecture/adr/ADR-002-context-manager-consolidation.md)
> **Длительность:** 2 недели
> **Цель:** ГЛАВНАЯ оптимизация длинных сессий — отправлять иммутабельный `baseline` один раз за эпоху, далее только дельты (`tail`), за тем же `baseline/tail` API, заложенным в Phase 0. Стабильный префикс → кэш-хит у провайдера/KV. Переключение по флагу `agents.context.lifecycle.incremental` без изменения сигнатур.

Phase 4 — поздняя оптимизация за **зафиксированным** API. Сигнатуры из Phase 0 не меняются;
включаются только реализации `ContextEpoch` + `ContextSnapshot` + `ContextReconciler`. Опирается на
[CONSOLIDATED_ARCHITECTURE.md §5–6, §10](./CONSOLIDATED_ARCHITECTURE.md),
[INTERFACES.md §3](./INTERFACES.md) и [DATA_MODELS.md §1, §4](./DATA_MODELS.md).

---

## Задачи

### T4.1 — `ContextEpoch`: иммутабельный baseline эпохи
- Реализовать управление `ContextEpoch` (`epoch_id`, `baseline`, `baseline_fingerprint`, `mid_conversation_messages`) в `context/epoch.py`.
- Старт эпохи: один раз отрендерить `ContextRegistry.render_baseline()`, зафиксировать `baseline` и `baseline_fingerprint` (Codec-отпечаток стабильного префикса).
- Дельты хода аккумулируются в `mid_conversation_messages`; полный контекст — `get_full_context()`.
- **Acceptance:** в рамках одной эпохи `baseline` и `baseline_fingerprint` неизменны; baseline рендерится один раз; повторные ходы не пересобирают префикс.

### T4.2 — `ContextSnapshot` + Codec-детект изменений
- Реализовать `ContextReconciler.snapshot(registry)` → `ContextSnapshot{fingerprints: source_id → Codec-отпечаток}` через `ContextSource.fingerprint()` / `ContextRegistry.detect_changes()`.
- Детект изменений — **только** `ContextSnapshot.diff()` (Codec-сравнение отпечатков), **НЕ таймстемпы** (`last_accessed`/mtime для детекта запрещены).
- **Acceptance:** `diff()` возвращает `source_id` источников с изменившимся отпечатком; идентичный контент даёт идентичный отпечаток → пустой diff; unit-тесты на стабильность детекта.

### T4.3 — `ContextReconciler.reconcile()`: дельты на безопасных границах хода
- Реализовать `reconcile(epoch, registry)` → `ReconcileResult{state, updated_sources, new_tail_messages, epoch_broken}`.
- Применять изменения **только на безопасной границе хода — после оседания тулов** (завершён tool-цикл, нет «в полёте» tool-call). Изменение, замеченное в неподходящий момент → `ChangeState.DEFERRED` (применится на следующей границе).
- Состояния: `UNCHANGED` (пустой diff — ничего не шлём), `UPDATED` (изменения отрендерены `render_updates()` в `new_tail_messages`, baseline цел), `DEFERRED` (отложено).
- Изменение системных/baseline-источников, которое нельзя выразить дельтой → `epoch_broken=True` (пересбор baseline, новая эпоха).
- **Acceptance:** дельты применяются строго на границах хода; изменение в середине tool-цикла даёт `DEFERRED`, не рвёт ход; `UPDATED` не трогает `baseline_fingerprint`.

### T4.4 — Единый сигнал инвалидации файла (стык Phase 2 ↔ 4) — КРИТИЧНО
- `FileCacheDecorator` (Phase 2, write-invalidation по `fs/write`) и snapshot-детект (T4.2) **ОБЯЗАНЫ слушать один источник истины** об изменении файла — Codec-сравнение содержимого.
- `FileContentCache.invalidate(path)` публикует сигнал изменения в этот единый источник; `ContextRegistry.detect_changes()` / `ContextReconciler.snapshot()` потребляют его же.
- Запрещены два независимых пути детекта (кэш инвалидируется, а snapshot этого не видит → модель работает на устаревшем baseline = тихий рассинхрон).
- **Acceptance:** `fs/write` по файлу из baseline → инвалидация кэша И ненулевой `diff()` за один сигнал; нет состояния «кэш сброшен, baseline устарел»; интеграционный тест read→write→reconcile.

### T4.5 — Переключение `build_context()` гидрация → инкрементальное (за тем же API)
- В `ExecutionEngine`/`ContextManager.build_context()` выбирать поведение по `agents.context.lifecycle.incremental` (и per-call override `BuildOptions.incremental`; `None` → из конфига).
- `incremental=false` → поведение Phase 1–3 (гидрация: baseline пересобирается каждый ход).
- `incremental=true` → baseline из активной `ContextEpoch`, `tail` = `mid_conversation_messages` + `ReconcileResult.new_tail_messages`.
- **Сигнатура `build_context()` не меняется** — оба пути возвращают `PayloadEnvelope`; `LLMAdapter` по-прежнему получает `to_messages()`.
- **Acceptance:** переключение флага в обе стороны не ломает поведение и не меняет API; результат при `incremental=false` бит-в-бит как до Phase 4.

### T4.6 — Включение provider/KV prefix-cache
- Гарантировать стабильность `baseline_fingerprint` в эпохе (детерминированный рендер источников + детерминированный `CodeSkeletonizer` из Phase 2) → одинаковый токенизированный префикс → prompt-cache хит у провайдера / KV-prefix-cache локальной модели.
- Прокинуть стабильный префикс в адаптер так, чтобы провайдерский cache-маркер ставился на `baseline`.
- **Acceptance:** на длинной сессии измеримый кэш-хит и экономия токенов (метрики: доля переотправленных токенов, cached-input по ответам провайдера); экономия растёт с длиной сессии.

---

## Definition of Done для Phase 4

- [ ] `ContextEpoch` фиксирует `baseline`/`baseline_fingerprint` один раз за эпоху.
- [ ] `ContextSnapshot.diff()` (Codec-детект, не таймстемпы) — единственный детектор изменений.
- [ ] `ContextReconciler.reconcile()` применяет дельты на безопасных границах хода; `UNCHANGED`/`UPDATED`/`DEFERRED` работают.
- [ ] Единый сигнал инвалидации: `FileCacheDecorator` и snapshot-детект слушают один источник; нет рассинхрона при `fs/write`.
- [ ] `build_context()` переключается по `incremental` без изменения сигнатур; `incremental=false` — без регрессий.
- [ ] Provider/KV prefix-cache включён; измеримый кэш-хит/экономия токенов на длинной сессии.

---

## Что Phase 4 НЕ делает (важно)

- **Не меняет сигнатуры API** — `build_context()`/`ensure_context_fits()`/`process_subagent_response()` заморожены в Phase 0; добавляются только реализации за тем же `baseline/tail` фундаментом.
- Не вводит федеративный шеринг (`share_item()`) — он рвёт стабильность эпох (прошаренный item ломает baseline другого агента), кандидат на отказ; см. Phase 6.
- Не расширяет `DependencyGraph` (рекурсия/tree-sitter — Phase 5).
- Не меняет поведение при `incremental=false` (остаётся гидрация Phase 1–3).

---

## Риски и митигации

| Риск | Митигация |
|------|-----------|
| Рассинхрон baseline: кэш инвалидирован, а snapshot не заметил изменение → модель на устаревшем префиксе (тихий баг) | Единый источник истины (T4.4): `FileCacheDecorator` и snapshot-детект слушают один Codec-сигнал; запрет двух путей детекта; интеграционный тест read→write→reconcile |
| Разрыв эпохи и потеря prompt-cache: частый `epoch_broken=True` обнуляет экономию | Выражать изменения дельтой через `render_updates()` (`UPDATED`), а не пересбором; `epoch_broken` — только для неизбежных изменений baseline-источников; метрика частоты разрывов как регрессионный порог |
| Ложные срабатывания детекта: недетерминированный рендер/скелетирование даёт «изменение» без изменения контента → лишние дельты и порча кэша | Детерминированный `CodeSkeletonizer` (Phase 2) + детерминированный рендер источников; детект только по Codec-отпечатку контента (не mtime/таймстемп); тест «идентичный контент → пустой diff» |
| Дельта применена в середине tool-цикла → порча хода | Реконсиляция только на безопасной границе после оседания тулов; иначе `ChangeState.DEFERRED` |
