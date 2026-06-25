# Context Manager — Наблюдаемость (метрики, трейсинг, логи)

> **Статус:** Канон (отражает [ADR-002](../architecture/adr/ADR-002-context-manager-consolidation.md))
> **Дата:** 25 июня 2026
>
> Документ описывает наблюдаемость консолидированного `ContextManager`: каталог метрик,
> spans трейсинга, политику логирования и план мониторинга канареечного rollout.
> Имена компонентов, слои A–D и фазы — см. [CONSOLIDATED_ARCHITECTURE.md](./CONSOLIDATED_ARCHITECTURE.md);
> контракты — [INTERFACES.md](./INTERFACES.md).

---

## Оглавление

1. [Каталог метрик](#1-каталог-метрик)
2. [Трейсинг (spans)](#2-трейсинг-spans)
3. [Логи](#3-логи)
4. [Мониторинг канареечного rollout](#4-мониторинг-канареечного-rollout)

---

## 1. Каталог метрик

Все метрики — префикс `context_`, имена в `snake_case`. Counter — монотонный счётчик,
gauge — мгновенное значение, histogram — распределение. Колонка «Фаза» — когда метрика
начинает эмитироваться (метрика появляется только когда работает её слой).

### 1.1. Сводная таблица

| Метрика | Тип | Что измеряет | Появляется на фазе |
|---------|-----|--------------|--------------------|
| `context_file_cache_hits` | counter | Число попаданий в `FileContentCache` (контент отдан без ACP RPC). Label: `session` (опц.) | Phase 2 (слой C) |
| `context_file_cache_misses` | counter | Число промахов `FileContentCache` (потребовался `fs/read` через `ToolRegistry`) | Phase 2 (слой C) |
| `context_file_cache_evictions` | counter | Число вытеснений из кэша (LRU / priority-based eviction по `ContextItem.priority`) | Phase 2 (слой C) |
| `context_file_cache_size_bytes` | gauge | Текущий объём контент-кэша (per-session или агрегат через `SessionFileCacheRegistry`). Label: `session` | Phase 2 (слой C) |
| `context_gathered_files` | gauge | Число файлов, отобранных `ContextGatherer` за один `build_context()`. Label: `agent_scope`, `task_type` | Phase 1 (слой A) |
| `context_baseline_tokens` | gauge | Размер иммутабельного baseline (`PayloadEnvelope.baseline`) в токенах. Label: `agent_scope` | Phase 0/1 (форма payload) |
| `context_tail_tokens` | gauge | Размер дельт (`PayloadEnvelope.tail`) в токенах. Label: `agent_scope` | Phase 0/1 (форма payload) |
| `context_build_duration_ms` | histogram | Длительность `build_context()` от входа до готового `PayloadEnvelope`, мс. Label: `agent_scope`, `task_type` | Phase 1 |
| `context_ensure_fits_duration_ms` | histogram | Длительность `ensure_context_fits()` (включая сжатие при триггере), мс | Phase 1 |
| `context_compaction_ratio` | histogram | Доля сжатия = `tokens_after / tokens_before` после `ContextCompactor` (чем меньше, тем сильнее сжатие). Label: `phase` (`prune`/`skeletonize`/`summarize`) | Phase 3 (компактор) |
| `context_compaction_total` | counter | Число срабатываний компактора (превышен `max_context_tokens - reserved_tokens`). Label: `phase` | Phase 3 |
| `context_compaction_degraded_total` | counter | Число деградаций компактора: фаза Summarize пропущена (LLM недоступен) → только Prune+Skeletonize. Label: `reason` (`llm_unavailable`/`timeout`) | Phase 3 |
| `context_skeleton_savings_ratio` | histogram | Экономия токенов фазой Skeletonize (`CodeSkeletonizer`): `1 - skeleton_tokens / original_tokens` | Phase 2/3 (слой C) |
| `context_epoch_breaks_total` | counter | Число разрывов эпохи (`ContextEpoch` пересобран → baseline отправляется заново). Label: `reason` (`source_changed`/`compaction`/`overflow`) | Phase 4 (слой B) |
| `context_reconcile_total` | counter | Число реконсиляций (`ContextReconciler.reconcile()`). Label: `state` (`unchanged`/`updated`/`deferred`) | Phase 4 (слой B) |
| `context_prompt_cache_hit_rate` | gauge | Доля попаданий provider/KV prompt-cache по стабильному префиксу (baseline). Источник — `AgentResponse.usage` (cached tokens) | Phase 4 (слой B) |
| `context_token_count_duration_ms` | histogram | Длительность подсчёта токенов (`TokenCounter`/`TiktokenCounter`), мс | Phase 2 (слой C) |
| `context_subagent_responses_total` | counter | Число обработанных `process_subagent_response()`. Label: `parent_scope` | Phase 6 (слой D) |
| `context_errors_total` | counter | Ошибки в слоях Context Manager. Label: `layer` (`a_gather`/`b_lifecycle`/`c_storage`/`d_multiagent`), `op` | Phase 1+ |

### 1.2. Производные показатели (вычисляются в дашборде/алертах)

| Показатель | Формула | Целевое значение |
|------------|---------|------------------|
| Cache hit rate | `context_file_cache_hits / (context_file_cache_hits + context_file_cache_misses)` | > 0.80 (SLO слоя C) |
| Prompt-cache эффективность | `context_prompt_cache_hit_rate` | растёт по длине сессии (Phase 4) |
| Доля деградаций | `context_compaction_degraded_total / context_compaction_total` | < 0.05 |
| Error rate | `rate(context_errors_total) / rate(context_build_*_calls)` | < 0.001 (перед 100% rollout) |

### 1.3. Привязка SLO (из PERFORMANCE_REQUIREMENTS)

| Метрика | SLO p50 | SLO p95 | SLO max |
|---------|---------|---------|---------|
| `context_build_duration_ms` | < 50 мс | < 200 мс | < 2 с |
| `context_ensure_fits_duration_ms` (без LLM-Summarize) | < 100 мс | < 500 мс | < 5 с (с LLM-Summarize) |
| `context_token_count_duration_ms` | — | < 50 мс | — |

> LLM-суммаризация — редкий fallback, вне p95-бюджета `ensure_context_fits`; её стоимость учитывается в `max`.

---

## 2. Трейсинг (spans)

Spans создаются через существующий tracer (`SpanContext` / `tracer`, упоминаемый в стратегиях).
Корневой span хода — внешний (`agent.turn`), spans Context Manager вкладываются в него.
Иерархия: `context.build` ⊃ {`context.gather`, `context.compact`, `context.reconcile`}.

### 2.1. Каталог spans

| Span | Когда создаётся | Родитель | Появляется на фазе |
|------|-----------------|----------|--------------------|
| `context.build` | на каждый `build_context()` | `agent.turn` | Phase 1 |
| `context.gather` | в `ContextGatherer.gather()` (пайплайн сбора) | `context.build` | Phase 1 |
| `context.compact` | в `ContextCompactor` при срабатывании сжатия | `context.build` / `ensure_context_fits` | Phase 3 |
| `context.reconcile` | в `ContextReconciler.reconcile()` на границе хода | `context.build` | Phase 4 |

### 2.2. Атрибуты spans

**`context.build`**

| Атрибут | Тип | Значение |
|---------|-----|----------|
| `agent_scope` | string | скоуп агента (`single`/`orchestrated`/…) |
| `task_type` | string | классификация `TaskAnalyzer` (`bug_fix`/`feature`/`refactor`/`architecture`) |
| `gathered_files` | int | число файлов, отобранных слоем A |
| `baseline_tokens` | int | размер baseline в токенах |
| `tail_tokens` | int | размер tail в токенах |
| `fingerprint` | string | Codec-отпечаток baseline (для корреляции с prompt-cache) |
| `incremental` | bool | работает ли инкрементальная модель (Phase 4) или гидрация |

**`context.gather`**

| Атрибут | Тип | Значение |
|---------|-----|----------|
| `task_type` | string | тип задачи из `TaskProfile` |
| `search_terms` | int | число поисковых терминов |
| `candidate_files` | int | число файлов-кандидатов до отбора по бюджету |
| `selected_files` | int | число отобранных файлов |
| `cache_hits` / `cache_misses` | int | попадания/промахи `FileContentCache` в рамках сбора |

**`context.compact`**

| Атрибут | Тип | Значение |
|---------|-----|----------|
| `phase` | string | фаза компактора: `prune` / `skeletonize` / `summarize` |
| `ratio` | float | доля сжатия `tokens_after / tokens_before` |
| `tokens_before` / `tokens_after` | int | токены до/после |
| `degraded` | bool | была ли пропущена фаза Summarize (деградация без LLM) |

**`context.reconcile`**

| Атрибут | Тип | Значение |
|---------|-----|----------|
| `state` | string | результат реконсиляции: `unchanged` / `updated` / `deferred` |
| `epoch_broken` | bool | привёл ли реконсайл к разрыву эпохи (пересбор baseline) |
| `changed_sources` | int | число `source_id`, изменившихся с прошлого снимка |

---

## 3. Логи

Структурированные логи (key=value / JSON). Каждая запись несёт `session_id` и `agent_scope`.
**Запрещено** писать в логи содержимое файлов, промптов, исходный код и значения секретов —
только метаданные (пути, размеры, число токенов, отпечатки, причины).

| Уровень | Событие | Поля | Слой / фаза |
|---------|---------|------|-------------|
| INFO | старт/финиш `build_context` | `agent_scope`, `task_type`, `gathered_files`, `baseline_tokens`, `tail_tokens`, `duration_ms`, `incremental` | Phase 1 |
| INFO | статистика контент-кэша (периодически/на финише сессии) | `hits`, `misses`, `hit_rate`, `evictions`, `size_bytes` | Phase 2 |
| INFO | сработал компактор | `trigger_tokens`, `phases_applied`, `ratio`, `tokens_before`, `tokens_after` | Phase 3 |
| INFO | разрыв эпохи | `reason`, `prev_baseline_tokens`, `new_baseline_tokens` | Phase 4 |
| INFO | реконсиляция применена | `state`, `changed_sources`, `epoch_broken` | Phase 4 |
| WARN | деградация компактора (Summarize пропущен) | `reason` (`llm_unavailable`/`timeout`), `ratio_after_prune_skeletonize`, `fits` (bool) | Phase 3 |
| WARN | падение cache hit rate ниже порога | `hit_rate`, `threshold`, `window` | Phase 2 |
| WARN | рассинхрон baseline (сигнал инвалидации файла не дошёл) | `path`, `expected_fingerprint`, `actual_fingerprint` | Phase 4 |
| WARN | превышен SLO латентности `build_context` | `duration_ms`, `slo_p95_ms`, `task_type` | Phase 1 |
| WARN/ERROR | ошибка слоя (fallback или провал) | `layer`, `op`, `error_type`, `fallback` (напр. `ApproximateTokenCounter`, `legacy`) | Phase 1+ |

> **Принцип:** на INFO — нормальный жизненный цикл и агрегаты; на WARN — деградации,
> срабатывание fallback, разрывы эпох по нештатным причинам и нарушения порогов;
> ERROR — невосстановимые ошибки слоя, ведущие к откату на legacy-путь.

---

## 4. Мониторинг канареечного rollout

Включение нового `ContextManager` управляется master-switch `agents.context.enabled`
(env: `CODELAB_CONTEXT_ENABLED`) и долей трафика `CODELAB_CONTEXT_ROLLOUT_PERCENT`.
Дашборд сравнивает canary (новый путь) против baseline (legacy) по тем же метрикам.

### 4.1. Ключевые метрики и тревожные пороги

| Метрика / показатель | Норма | Warning | Critical (кандидат на откат) | Действие |
|----------------------|-------|---------|------------------------------|----------|
| `context_epoch_breaks_total` (rate) | стабильна / падает по сессии | рост x2 к baseline-окну за 10 мин | рост x5 (эпоха почти не держится) | проверить единый сигнал инвалидации файла (стык Phase 2↔4), рассинхрон baseline |
| Cache hit rate | > 0.80 | < 0.80 за 10 мин | < 0.50 за 10 мин | увеличить `max_files`, проверить паттерн доступа и инвалидацию |
| `context_build_duration_ms` p95 | < 200 мс | > 200 мс за 5 мин | > 400 мс (2× SLO) за 5 мин | посмотреть span `context.gather`/`context.compact`; при общем замедлении — откат |
| `context_prompt_cache_hit_rate` | растёт по длине сессии | не растёт / падает | около 0 на длинных сессиях | baseline нестабилен — проверить детерминизм `CodeSkeletonizer` и контент-кэша |
| Доля деградаций (`degraded/total`) | < 0.05 | > 0.05 | > 0.20 | проверить доступность/латентность LLM для Summarize |
| Error rate (`context_errors_total`) | < 0.001 | > 0.001 | > 0.01 | разбор по label `layer`/`op`; при росте — откат на legacy |
| `context_compaction_ratio` | стабильна | резкий рост (сжатие слабеет) | переполнение окна несмотря на компактор | проверить фазы Prune/Skeletonize, размеры файлов |
| `context_file_cache_size_bytes` | < 1 МБ / сессия | > 1 МБ | > 5 МБ / сессия (утечка) | проверить eviction и lifecycle `SessionFileCacheRegistry` |

### 4.2. Процедура rollout

| Шаг | Условие перехода |
|-----|------------------|
| Canary 5% (1 неделя) | нет инцидентов; canary-метрики ≥ legacy; error rate < 0.001 |
| Расширение (25% → 50%) | пороги Warning не превышены устойчиво; cache hit rate > 0.80; p95 в SLO |
| 100% | нет утечек памяти; prompt-cache хит растёт на длинных сессиях; epoch_breaks стабильны |

> **Сигналы немедленного отката** (`enabled=false` / снижение `ROLLOUT_PERCENT`):
> любой Critical-порог из §4.1, либо общий рост `context_build_duration_ms` p99 > 2 с,
> либо error rate > 0.01.

---

## Связанные документы

- [CONSOLIDATED_ARCHITECTURE.md](./CONSOLIDATED_ARCHITECTURE.md) — слои A–D, фазы, §4.1 (замкнутый цикл)
- [INTERFACES.md](./INTERFACES.md) — контракты компонентов
- [ADR-002](../architecture/adr/ADR-002-context-manager-consolidation.md) — решения и таблица env-overrides
- [PERFORMANCE_REQUIREMENTS.md](../architecture/fcm/PERFORMANCE_REQUIREMENTS.md) — SLO и пороги деградации (источник идей по метрикам)
