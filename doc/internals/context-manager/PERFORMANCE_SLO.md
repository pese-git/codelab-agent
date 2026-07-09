# Context Manager — Performance SLO

> **Статус:** Канон ([ADR-002](../architecture/adr/ADR-002-context-manager-consolidation.md))
> **Дата:** 25 июня 2026
>
> Числовые цели производительности консолидированного `ContextManager` (слои A–D).
> Опирается на [CONSOLIDATED_ARCHITECTURE.md](./CONSOLIDATED_ARCHITECTURE.md),
> [INTERFACES.md](./INTERFACES.md), [DATA_MODELS.md](./DATA_MODELS.md) и наследует
> FCM-ориентиры из архива `archive/fcm/PERFORMANCE_REQUIREMENTS.md`.
>
> **Все числа ниже — целевые ориентиры, а не контрактные гарантии.** Они уточняются
> бенчмарками на Phase 1 (сбор), Phase 2 (слой хранения C) и Phase 4 (инкрементальность).
> До соответствующей фазы цель считается предварительной.

---

## Оглавление

1. [SLO: латентность](#1-slo-латентность)
2. [SLO: эффективность токенов и кэшей](#2-slo-эффективность-токенов-и-кэшей)
3. [SLO: качество сжатия](#3-slo-качество-сжатия)
4. [Бенчмарк-сценарии](#4-бенчмарк-сценарии)
5. [Бюджеты ресурсов](#5-бюджеты-ресурсов)
6. [Допустимая регрессия vs legacy](#6-допустимая-регрессия-vs-legacy)
7. [Привязка метрик к фазам](#7-привязка-метрик-к-фазам)

---

## 1. SLO: латентность

Все латентности измеряются **без LLM-вызовов слоя A** (`TaskAnalyzer.analyze()` и
`ConversationSummarizer.summarize()` — отдельные строки, см. ниже): чистый CPU-путь
`build_context()` → `ensure_context_fits()` детерминирован и не должен зависеть от сети.

| Метрика | Цель (p95) | Цель (max) | Как меряем | Фаза уточнения |
|---------|-----------|-----------|------------|----------------|
| `ContextManager.build_context()` (без LLM слоя A) | < 200 мс | < 2 с | `time.perf_counter()` вокруг вызова; гистограмма по 1000 итераций | Phase 1 |
| `ContextManager.ensure_context_fits()` — типовой путь (Prune + Skeletonize, без Summarize) | < 500 мс | — | таймер вокруг компактора при превышении `max_context_tokens - reserved_tokens` | Phase 2/3 |
| `ConversationSummarizer.summarize()` (LLM-fallback) | **вне p95** | < 5 с | отдельная гистограмма; редкий путь, не входит в бюджет `ensure_context_fits` p95 | Phase 3 |
| `TokenCounter.count()` / `count_messages()` (tiktoken) на файл ~5000 LOC | < 50 мс | < 200 мс | таймер вокруг `TiktokenCounter`; батч по items | Phase 2 |
| `CodeSkeletonizer.skeletonize()` (AST) на файл ~5000 LOC | < 200 мс | < 500 мс | таймер вокруг `PythonASTSkeletonizer`; самая тяжёлая CPU-операция p95 | Phase 2 |
| `TaskAnalyzer.analyze()` (LLM-классификация) | вне p95 | < 2 с | отдельная гистограмма; кэшируется per-turn | Phase 1 |

**Замечание о деградации.** При недоступности LLM фазы `Summarize` и `TaskAnalyzer`
выпадают (см. CONSOLIDATED_ARCHITECTURE §7); SLO `ensure_context_fits` сохраняется,
т.к. Prune + Skeletonize — чистый CPU.

---

## 2. SLO: эффективность токенов и кэшей

| Метрика | Цель | Как меряем | Фаза |
|---------|------|-----------|------|
| Cache hit rate `FileContentCache` при повторных чтениях файла | > 90% | `fcm.cache.hit / (hit + miss)` на сценарии с повторными `fs/read` того же пути | Phase 2 |
| Prompt-cache hit rate на длинной сессии (стабильный `baseline_fingerprint`) | > 70% после первого хода эпохи | доля ходов, где `PayloadEnvelope.baseline_fingerprint` не изменился между ходами → попадание в provider/KV prefix-cache | Phase 4 |
| Экономия токенов на ход: incremental (`tail` only) vs гидрация (полный baseline+tail) | > 60% на стабильном baseline (50+ ходов) | `count_messages(tail)` против `count_messages(baseline+tail)` на одном и том же ходу | Phase 4 |
| Доля ходов без пересборки baseline (`ReconcileResult.epoch_broken == False`) | > 80% в длинной сессии | счётчик `epoch_broken` в `ContextReconciler.reconcile()` | Phase 4 |

> Метрики раздела 2 — основная статья ценности Phase 4 (см.
> CONSOLIDATED_ARCHITECTURE §5: стоимость гидрации растёт квадратично по сессии).
> До Phase 4 (`incremental=false`) prompt-cache hit и экономия дельт не применимы.

---

## 3. SLO: качество сжатия

| Метрика | Цель | Как меряем | Фаза |
|---------|------|-----------|------|
| Доля сжатия `CodeSkeletonizer` (скелет vs оригинал) | 80–85% экономии токенов | `1 - count(skeleton) / count(original)` по golden-набору файлов | Phase 2 |
| Детерминизм `skeletonize()` (один вход → один выход) | 100% (байт-в-байт) | повторный прогон того же входа → идентичный выход (golden-тест, см. TESTING_STRATEGY) | Phase 2 |
| Skeleton «не выгоден» (skeleton ≥ original) | корректно пропускается | счётчик `fcm.skeleton_not_beneficial`; на таких файлах фаза Skeletonize не применяется | Phase 2 |
| `priority >= 10` (system_rules) при сжатии | никогда не усекается/не вытесняется | проверка состава `PayloadEnvelope` после `ensure_context_fits()` | Phase 3 |

---

## 4. Бенчмарк-сценарии

Эталонные сценарии для `benchmarks/context_performance.py` и `benchmarks/context_memory.py`.
Метрики снимаются по 1000 итераций (latency) и через `tracemalloc` (memory).

| # | Сценарий | Профиль | Целевой p95 | Целевая память |
|---|----------|---------|-------------|----------------|
| 1 | **Короткая сессия** | 10 сообщений, ~2000 токенов, без сжатия | `build_context` < 50 мс | < 100 KB |
| 2 | **Средняя сессия** | 50 сообщений, ~10 000 токенов | `build_context` < 200 мс | < 500 KB |
| 3 | **Длинная сессия (50+ ходов)** | 200 сообщений, ~100 000 токенов → триггер компактора | `ensure_context_fits` < 1 с; prompt-cache hit > 70% (Phase 4) | < 2 MB |
| 4 | **Большой файл** | 1 файл ~50 000 токенов (~5000 LOC) → AST-скелетирование | `skeletonize` < 500 мс; скелет < 15–20% оригинала | — |
| 5 | **Большой проект** | `ContextGatherer` по дереву 1000+ файлов; отбор целевых | `gather()` (без LLM) < 1 с; точность отбора растёт на Phase 5 | — |

Сценарий 3 — ключевой для слоёв B/C совместно: первый ход прогревает `FileContentCache`
и фиксирует baseline эпохи; последующие ходы должны давать кэш-хит и экономию дельт.

---

## 5. Бюджеты ресурсов

### 5.1. Память

| Компонент | На сессию | 1000 сессий | Max | Источник лимита |
|-----------|-----------|-------------|-----|------------------|
| `FileContentCache` / `InMemoryFileCache` | < 1 MB | < 1 GB | 2 GB | LRU при `cache_max_files = 1000` (`ContextConfig.cache_max_files`) |
| Контекст-скоуп (items слоя C) | < 500 KB | < 500 MB | 1 GB | priority-based eviction (`ContextItem.priority`) |
| **Итого overhead Context Manager** | **< 2 MB** | **< 2 GB** | **4 GB** | сумма выше |

**Оценка RAM на сессию.** При `cache_max_files = 1000` и среднем файле ~1–5 KB
содержимого `FileContentCache` остаётся < 1 MB на сессию; вместе с items скоупа
целевой потолок — **< 2 MB на сессию**. `SessionFileCacheRegistry` отвечает за
lifecycle кэшей: освобождение при закрытии сессии — обязательное условие удержания
бюджета 1000 сессий < 2 GB.

### 5.2. Пропускная способность (ориентиры)

| Метрика | Цель |
|---------|------|
| Конкурентные сессии | 1000 |
| `build_context()` calls/sec | 100 |
| Cache hit rate `FileContentCache` | > 80% (общий), > 90% на повторных чтениях |

---

## 6. Допустимая регрессия vs legacy

База — `context_compactor.py` (legacy `ContextCompactor`), который остаётся активным
при `agents.context.enabled = false`.

| Метрика | Legacy | Цель Context Manager | Макс. регрессия |
|---------|--------|----------------------|------------------|
| Latency `build_context` p50 | ~30 мс | < 45 мс | +50% |
| Latency `build_context` p95 | ~150 мс | < 225 мс | +50% |
| Память на сессию | ~500 KB | < 1 MB | +100% |

**Обоснование допуска.** Рост латентности компенсируется качеством (умный сбор слоя A,
AST-скелеты, приоритеты) и экономией на длинных сессиях (Phase 4). Регрессия > 100% по
латентности или > 2x по памяти — триггер отката на legacy (`enabled=false`).

---

## 7. Привязка метрик к фазам

| Фаза | Что измеряем впервые | Контрольные SLO |
|------|----------------------|------------------|
| **Phase 1** | `build_context` latency, `gather()`, точность отбора файлов | latency p95 § 1; качество отбора ≥ 80% |
| **Phase 2** | `TokenCounter`, `CodeSkeletonizer`, `FileContentCache` hit rate | § 1 (counting/skeletonize), § 2 (cache hit > 90%), § 3 (сжатие 80–85%) |
| **Phase 3** | компактор end-to-end, деградация без LLM | `ensure_context_fits` p95 § 1; `priority>=10` не усекается § 3 |
| **Phase 4** | prompt-cache hit, экономия дельт, `epoch_broken` | весь § 2 |
| **Phase 5** | `gather()` на больших проектах (сценарий 5) | точность отбора, latency § 4 |

> Числа подлежат калибровке: после первого бенчмарк-прогона фазы значения в таблицах
> § 1–§ 3 пересматриваются и фиксируются как baseline для алертов
> (см. `archive/fcm/PERFORMANCE_REQUIREMENTS.md` §5 — пороги мониторинга и алертов).
