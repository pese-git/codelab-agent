# Context Manager — Стратегия тестирования

> **Статус:** Канон ([ADR-002](../architecture/adr/ADR-002-context-manager-consolidation.md))
> **Дата:** 25 июня 2026
>
> Уровни тестов, рисковые места, golden/snapshot-тесты и тест-матрица по фазам
> для консолидированного `ContextManager`. Имена методов — из
> [INTERFACES.md](./INTERFACES.md); модели — из [DATA_MODELS.md](./DATA_MODELS.md);
> числовые цели — из [PERFORMANCE_SLO.md](./PERFORMANCE_SLO.md).

---

## Оглавление

1. [Уровни тестов](#1-уровни-тестов)
2. [Особо рисковые места](#2-особо-рисковые-места)
3. [Golden / snapshot-тесты](#3-golden--snapshot-тесты)
4. [Фикстуры](#4-фикстуры)
5. [Тест-матрица по фазам](#5-тест-матрица-по-фазам)

---

## 1. Уровни тестов

| Уровень | Что тестируем | Границы (что мокается) | Где |
|---------|---------------|------------------------|-----|
| **unit** | Каждый ABC и его реализация по отдельности | всё внешнее замокано (ToolRegistry, LLMProvider, файловый I/O) | `tests/unit/context/` |
| **integration** | `build_context()` → `ensure_context_fits()` end-to-end через `ContextManager` | реальные слои A–C; мок `ToolRegistry` + мок `LLMProvider` | `tests/integration/context/` |
| **e2e** | стратегия (Single/Orchestrated/Choreography/Hierarchical) + `ContextManager` | замоканные `ToolRegistry` и `LLMProvider`, реальная склейка с `ExecutionEngine` | `tests/e2e/context/` |

### 1.1. Unit — по компонентам слоёв

| Компонент (ABC) | Ключевые проверки |
|-----------------|-------------------|
| `TaskAnalyzer.analyze()` | возвращает `TaskProfile` с валидным `task_type`/`investigation_depth` (1–3); `prompt` = текст текущего хода, не вся история |
| `ContextGatherer.gather()` | пайплайн `project_tree()`→`search()`→`read_file()` только через `ToolRegistry`; собственного I/O нет |
| `DependencyGraph` | `add_file()` / `get_dependencies(recursive=...)` / `get_dependents()`; regex-режим (Phase 1) |
| `TokenBudgetManager` | `allocate()` даёт корректный `BudgetAllocation` (суммы долей); `bound_content()` сохраняет начало и конец |
| `ContextSource` / `ContextRegistry` | `render_baseline()` / `render_updates()` / `detect_changes()`; `fingerprint()` — Codec, не таймстемп |
| `TokenCounter` | `count()` / `count_messages()`; `TiktokenCounter` точность, `ApproximateTokenCounter` fallback |
| `CodeSkeletonizer` | `can_handle()`; `skeletonize()` детерминизм + доля сжатия (см. §2) |
| `FileContentCache` | `get()`/`set()`/`invalidate()`; LRU eviction при `cache_max_files`; `invalidate()` публикует сигнал (см. §2) |
| `ContextCompactor` | `compact_if_needed()` — 3 фазы Prune→Skeletonize→Summarize; сигнатура совместима с legacy |
| `ConversationSummarizer` | `summarize()` сохраняет ключевые решения; деградация при отсутствии `LLMProvider` |
| `ContextReconciler` | `snapshot()` / `reconcile()` → корректный `ReconcileResult` (см. §2) |
| `ChildSessionManager` | `create_child()` изолирует; `collect_summary()` → `SubagentResult` |

---

## 2. Особо рисковые места

Места, где тихий баг дороже всего; покрываются отдельными целевыми тестами.

### 2.1. Детерминизм `CodeSkeletonizer` (golden)

- **Риск:** недетерминированный вывод `skeletonize()` рвёт `baseline_fingerprint` → промах prompt-cache.
- **Тесты:**
  - повторный прогон того же входа → байт-в-байт идентичный выход;
  - golden-тесты: входной файл из фикстуры → зафиксированный эталон скелета;
  - инвариант сжатия: доля экономии в коридоре 80–85% (PERFORMANCE_SLO §3);
  - `skeletonize()` не зависит от порядка обхода / окружения / времени.

### 2.2. Единый сигнал инвалидации (Phase 2 ↔ Phase 4)

- **Риск:** `fs/write` обновляет `FileContentCache`, но `ContextSnapshot` не видит изменения → stale baseline (рассинхрон, тихий баг — CONSOLIDATED_ARCHITECTURE §6).
- **Тесты:**
  - после `fs/write` по пути: `FileContentCache.invalidate()` вызван И `detect_changes()` возвращает соответствующий `source_id` — оба канала видят изменение;
  - нет состояния, где кэш сброшен, а snapshot считает источник `UNCHANGED`;
  - проверка, что детект — через Codec-`fingerprint()`, а не таймстемпы.

### 2.3. Стабильность `baseline_fingerprint` (prompt-cache хит)

- **Риск:** baseline пересобирается без фактических изменений → `epoch_broken=True` без причины → потеря кэша.
- **Тесты:**
  - неизменные источники между ходами → `baseline_fingerprint` идентичен → `ReconcileResult.epoch_broken == False`;
  - изменение одного источника → меняется только соответствующая дельта `tail`, baseline стабилен, пока reconcile не требует пересборки;
  - идентичный контент из `FileContentCache` даёт идентичный baseline байт-в-байт.

### 2.4. Бюджет токенов (`priority >= 10` не усекается)

- **Риск:** при сжатии теряются системные правила (`system_rules`, priority=10).
- **Тесты:**
  - после `ensure_context_fits()` items с `priority >= 10` присутствуют целиком;
  - eviction идёт строго по возрастанию `priority` (`file_skeleton`=3 → ... → `system_rules`=10);
  - суммарный `PayloadEnvelope.token_count` ≤ `max_context_tokens - reserved_tokens`.

### 2.5. Деградация без LLM

- **Риск:** недоступность `LLMProvider` ломает весь путь вместо мягкой деградации.
- **Тесты:**
  - мок `LLMProvider` бросает / недоступен → `ensure_context_fits()` проходит через Prune + Skeletonize, фаза Summarize пропускается;
  - `TaskAnalyzer` недоступен → сбор работает по дефолтному профилю;
  - `build_context()` возвращает валидный `PayloadEnvelope` без LLM-вызовов.

---

## 3. Golden / snapshot-тесты `PayloadEnvelope`

| Тест | Что фиксируем |
|------|---------------|
| snapshot `PayloadEnvelope` (гидрация, Phase 1) | состав `baseline` + `tail`, `token_count` на эталонной фикстуре |
| snapshot `to_messages()` | плоский `baseline + tail` — порядок и состав сообщений |
| golden `baseline_fingerprint` | стабильность отпечатка на неизменном входе |
| golden скелета файла | эталонный выход `skeletonize()` (см. §2.1) |
| snapshot `ContextSnapshot.diff()` | список изменённых `source_id` для пары снимков |

> Snapshot-тесты обновляются осознанно (review-gate): изменение эталона `PayloadEnvelope`
> или fingerprint без причины — сигнал регрессии prompt-cache.

---

## 4. Фикстуры

| Фикстура | Назначение |
|----------|------------|
| **Тестовый репозиторий** | мини-проект (несколько `.py` с импортами, тесты, README) для `ContextGatherer`/`DependencyGraph`; источник входов golden-скелетов |
| **Мок `ToolRegistry`** | детерминированные ответы `project_tree`/`search`/`read_file`/`fs/write`; счётчики вызовов для проверки кэш-хитов (RPC не повторяется) |
| **Мок `LLMProvider`** | управляемые ответы для `TaskAnalyzer.analyze()` и `ConversationSummarizer.summarize()`; режим «недоступен» для тестов деградации (§2.5) |
| **Эталонные `PayloadEnvelope` / скелеты** | golden-файлы для snapshot-тестов §3 |

---

## 5. Тест-матрица по фазам

| Фаза | Уровень | Что тестируется (методы из INTERFACES) | Рисковые места (§2) |
|------|---------|----------------------------------------|----------------------|
| **Phase 0** | unit | модели данных: `PayloadEnvelope.to_messages()`, `ContextSnapshot.diff()`; ABC не инстанцируются; legacy-мост `compact_if_needed()` без регрессий | — |
| **Phase 1** | unit + integration + e2e | `TaskAnalyzer.analyze()`, `ContextGatherer.gather()`, `DependencyGraph` (regex), `TokenBudgetManager.allocate()/bound_content()`; e2e отбор файлов ≥ 80% | §2.4 (бюджет) |
| **Phase 2** | unit + integration | `TokenCounter.count*()`, `CodeSkeletonizer.skeletonize()`, `FileContentCache.get/set/invalidate()`, `SessionFileCacheRegistry`, `FileCacheDecorator` | §2.1 (детерминизм), §2.2 (часть: invalidate+сигнал), кэш-хит без RPC |
| **Phase 3** | unit + integration | `ContextCompactor.compact_if_needed()` (3 фазы), `ConversationSummarizer.summarize()`, `ContextRegistry`/`SkillContextSource` | §2.4, §2.5 (деградация) |
| **Phase 4** | integration + e2e | `ContextReconciler.snapshot()/reconcile()`, `ContextEpoch.get_full_context()`, prompt-cache хит | §2.2 (полный стык), §2.3 (стабильность fingerprint) |
| **Phase 5** | integration | `DependencyGraph.get_dependencies(recursive=True)`, tree-sitter; точность на большом проекте (сценарий 5) | — |
| **Phase 6** | e2e | `process_subagent_response()`, `ChildSessionManager.create_child()/collect_summary()` → `SubagentResult`; изоляция скоупов | загрязнение контекста между скоупами |

> Рисковые места §2.2 и §2.3 проверяются совместно на стыке Phase 2 и Phase 4 —
> отдельным integration-набором, т.к. единичные unit-тесты по фазам этот класс багов
> (stale baseline) не ловят.
