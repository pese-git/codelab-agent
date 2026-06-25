# Context Manager — Стратегия обработки ошибок

> **Статус:** Канон (отражает [ADR-002](../architecture/adr/ADR-002-context-manager-consolidation.md))
> **Дата:** 25 июня 2026
>
> Документ описывает поведение консолидированного `ContextManager` (слои A–D) при сбоях.
> Опирается на [CONSOLIDATED_ARCHITECTURE.md](./CONSOLIDATED_ARCHITECTURE.md),
> [INTERFACES.md](./INTERFACES.md) и [DATA_MODELS.md](./DATA_MODELS.md) — использует точные
> имена компонентов, методов и фаз оттуда.

---

## Оглавление

1. [Главный принцип](#1-главный-принцип)
2. [Слой A — сбор контекста](#2-слой-a--сбор-контекста)
3. [Слой C — хранение и эффективность](#3-слой-c--хранение-и-эффективность)
4. [Слой B — жизненный цикл (Phase 4)](#4-слой-b--жизненный-цикл-phase-4)
5. [Слой D — мультиагентный обмен](#5-слой-d--мультиагентный-обмен)
6. [Бюджет — деградация после 3 фаз сжатия](#6-бюджет--деградация-после-3-фаз-сжатия)
7. [Инварианты обработки ошибок](#7-инварианты-обработки-ошибок)

---

## 1. Главный принцип

**Graceful degradation, не падать в горячем пути.**

Горячий путь — это замкнутый цикл формирования payload из
[§4.1 CONSOLIDATED_ARCHITECTURE](./CONSOLIDATED_ARCHITECTURE.md#41-замкнутый-цикл-как-payloadenvelope-уходит-в-llm-и-как-tool_result-возвращается-в-fcm):
`build_context()` → `PayloadEnvelope` → `ensure_context_fits()` → `to_messages()` →
`EventBus.send_request()` → tool-цикл → следующий `build_context()`. Любой сбой
внутри подготовки payload **обязан** деградировать до более простого, но валидного
результата, а не прерывать ход агента.

Классификация сбоев и реакция:

| Категория | Реакция | Пример |
|-----------|---------|--------|
| **Конфигурация** (невалидный конфиг при старте) | Fail fast при инициализации (вне горячего пути) | `system_share + history_share + ... > 1.0` |
| **Runtime, восстановимая** | Fallback + лог `warning`/`info`, ход продолжается | `tiktoken` недоступен, AST не парсится, LLM упал |
| **Деградация качества/бюджета** | Жёсткое усечение + лог + метрика, ход продолжается | payload не влез после 3 фаз |
| **Сбой субагента** (слой D, изолирован) | Пометка об ошибке родителю, родитель не виснет | таймаут child-сессии |

Что **не** относится к горячему пути и допускает `raise`: конфигурационные ошибки на
старте (`ContextConfig`) и явные программные ошибки контракта вне цикла подготовки payload.

---

## 2. Слой A — сбор контекста

Компоненты: `TaskAnalyzer.analyze()`, `ContextGatherer.gather()`, `DependencyGraph`,
`TokenBudgetManager.allocate()` / `bound_content()`. Весь I/O слоя A идёт через
ACP `ToolRegistry` (правило ADR-002 — у `ContextGatherer` собственного I/O нет).

Принцип слоя A: **сбор — best-effort**. Любой источник может не ответить; собираем то,
что доступно, и продолжаем. Отсутствие части контекста снижает релевантность, но не
делает ход невозможным.

| Ошибка | Поведение | Лог / метрика | Влияние на пользователя |
|--------|-----------|----------------|--------------------------|
| `TaskAnalyzer.analyze()`: LLM-классификация упала (сеть/таймаут/провайдер) | Вернуть дефолтный `TaskProfile`: `task_type=FEATURE`, `search_terms` = эвристика из текста prompt, `target_modules=[]`, `investigation_depth=1`, `needs_tests=False` | `warning` `task_analysis_llm_failed_using_default`, поля `error_type`, метрика `context.task_analysis.fallback` | Сбор чуть менее точен (шире/мельче), но идёт; ответ не блокируется |
| `TaskAnalyzer.analyze()`: LLM вернул невалидный/непарсящийся ответ (не JSON, неизвестный `task_type`) | Тот же дефолтный `TaskProfile`; распознанные поля частично переносятся, нераспознанные — дефолт | `warning` `task_analysis_invalid_response`, поля `raw_excerpt`, `parse_error` | Как выше — деградация релевантности, не отказ |
| `ContextGatherer.gather()`: ACP RPC `project_tree()` упал | Продолжить с пустым деревом → опереться на `search()` и явные `target_modules` из `TaskProfile` | `warning` `gather_project_tree_failed`, метрика `context.gather.rpc_error{op="project_tree"}` | Может быть пропущен релевантный файл; ход продолжается |
| `ContextGatherer.gather()`: ACP RPC `search()` упал | Пропустить шаг поиска; отбор по дереву + зависимостям из `DependencyGraph` | `warning` `gather_search_failed`, метрика `...{op="search"}` | Меньше кандидатов; не отказ |
| `ContextGatherer.gather()`: ACP RPC `read_file()` упал для отдельного файла | Пропустить этот файл, продолжить со следующими; **не** прерывать сборку | `warning` `gather_read_file_failed`, поля `path`, метрика `...{op="read_file"}` | Конкретный файл отсутствует в контексте |
| Файл не читается: нет прав / удалён / бинарный | Пропустить файл (не добавлять `ContextItem`), продолжить сборку | `info` `gather_file_skipped`, поле `reason` (`permission`/`not_found`/`binary`) | Файл молча отсутствует; остальной сбор полный |
| Все RPC слоя A упали разом | Вернуть то, что собрано (возможно пусто) → payload строится из `session.history` + системного промпта | `error` `gather_all_sources_failed`, метрика `context.gather.empty_result` | Деградация до «голого» диалога без подтянутых файлов; ход идёт |
| `DependencyGraph.get_dependencies()`: regex не распознал импорты | Вернуть пустой список зависимостей (как «нет рёбер»), не бросать | `debug` `dependency_parse_empty`, поле `path` | Транзитивные файлы не подтянуты (ожидаемо до Phase 5) |
| `TokenBudgetManager.bound_content()`: контент больше выделенного лимита | Усечь, сохранив начало и конец (контракт `bound_content`) | `info` `content_bounded`, поля `original_tokens`, `bound_tokens` | Часть середины файла отсутствует; явная, не тихая потеря |

Итог по A: `gather()` возвращает `list[ContextItem]` — частичный список валиден,
пустой список валиден. `build_context()` всегда получает достаточно для `PayloadEnvelope`.

---

## 3. Слой C — хранение и эффективность

Компоненты: `TokenCounter` (`TiktokenCounter` / `ApproximateTokenCounter`),
`CodeSkeletonizer` (`PythonASTSkeletonizer`), `FileContentCache` / `InMemoryFileCache`,
`SessionFileCacheRegistry`, `FileCacheDecorator`.

Принцип слоя C: **эффективность опциональна**. Кэш, точный счётчик и скелетирование
ускоряют/уплотняют, но их отказ всегда имеет корректный «медленный» путь.

| Ошибка | Поведение | Лог / метрика | Влияние на пользователя |
|--------|-----------|----------------|--------------------------|
| `tiktoken` недоступен (ImportError при создании `TokenCounter`) | Фабрика возвращает `ApproximateTokenCounter` (≈ `len // 4`); рекомендуется увеличить `reserved_tokens` (буфер) при approximate-режиме | `warning` `tiktoken_not_available_using_fallback`, метрика `context.token_counter.mode{mode="approximate"}` | Подсчёт менее точен → чуть консервативнее бюджет; корректности нет угрозы |
| `TiktokenCounter.count()` упал на конкретном входе (редко) | Fallback к приближённой оценке для этого вызова | `error` `tiktoken_encoding_failed_using_fallback`, поле `content_length` | Затронут один элемент, не весь payload |
| `CodeSkeletonizer.can_handle(path)` → `False` (не Python / не поддерживается) | Скелетирование пропускается, исходный код используется как есть | `debug` `skeletonize_unsupported`, поле `language` | Файл занимает больше токенов, но цел |
| `CodeSkeletonizer.skeletonize()`: `SyntaxError` (битый/неполный код) | Вернуть исходный код как есть (поведение `can_handle=False` де-факто); фаза Skeletonize для файла — no-op | `warning` `skeletonize_syntax_error`, поля `path`, `line_number` | Нет сжатия для файла; код сохранён целиком |
| `CodeSkeletonizer.skeletonize()`: прочая ошибка AST | Вернуть исходный код как есть | `error` `skeletonize_unexpected_error`, поле `error_type` | Нет сжатия; код цел |
| Скелет оказался **не меньше** оригинала | Использовать оригинал (детерминированный выбор по `token_count`) | `info` `skeleton_not_beneficial`, поля `original_tokens`, `skeleton_tokens` | Без вреда; просто без экономии |
| `FileContentCache.get()` — промах (нет в кэше) | Не ошибка: обычный путь — ACP RPC `read_file()` через `ToolRegistry`, затем `set()` | `debug` `file_cache_miss`, метрика `context.file_cache.hit_rate` | Чуть больше задержка на первое чтение |
| `InMemoryFileCache`: переполнение (LRU eviction при `cache_max_files`) | Вытеснить наименее недавний; следующее чтение вытесненного — RPC-miss | `debug` `file_cache_evicted`, метрика `context.file_cache.evictions` | Минимальное; редкий повторный RPC |
| `FileCacheDecorator`: `invalidate()` упал при `fs/write` | Ветка обёрнута в `try/except`: ошибка логируется, **не пробрасывается** — stale-кэш лучше упавшего tool-исполнения. Параллельно фиксируется как **потерянный сигнал инвалидации** (см. §4) | `error` `file_cache_invalidation_failed`, поле `path`, метрика `context.invalidation.lost` | Tool-исполнение успешно; риск устаревшего содержимого до следующей записи/реконсиляции |
| `FileCacheDecorator`: `set()` упал при `fs/read` | Логируем, не пробрасываем; tool-результат отдаётся как есть (кэш просто не прогрелся) | `error` `file_cache_set_failed`, поле `path` | Повторное чтение пойдёт RPC; не отказ |

> **Детерминизм — требование, а не удобство.** `CodeSkeletonizer.skeletonize()` и
> `FileContentCache` обязаны давать байт-в-байт стабильный вывод: фоллбэк «вернуть оригинал»
> тоже детерминирован. Иначе baseline дрейфует → `baseline_fingerprint` меняется →
> промах prompt-cache (тихая потеря экономии слоя B).

---

## 4. Слой B — жизненный цикл (Phase 4)

Компоненты: `ContextEpoch`, `ContextSnapshot` (Codec-`fingerprints` + `diff()`),
`ContextReconciler.snapshot()` / `reconcile()` (→ `ReconcileResult`),
`ConversationSummarizer.summarize()`. Активны при `incremental=true` (Phase 4);
до этого `baseline` пересобирается каждый ход и эти отказы не наступают.

Принцип слоя B: **stale хуже, чем дорого**. При любой неуверенности в реконсиляции
консервативный выбор — пересобрать baseline (`epoch_broken=True`): теряем prompt-cache хит,
но гарантируем актуальность. Лучше один дорогой ход, чем устаревший контекст.

### 4.1. Сжатие — фаза Summarize (часть `ensure_context_fits()`)

| Ошибка | Поведение | Лог / метрика | Влияние на пользователя |
|--------|-----------|----------------|--------------------------|
| `ConversationSummarizer.summarize()`: LLM упал/таймаут/нет провайдера | Деградация компактора до **Prune + Skeletonize** (фазы 1–2): сохранить первые 2 и последние N сообщений, середину удалить напрямую вместо суммаризации | `warning` `summarization_failed_degrade_to_prune`, поле `error_type` (или `summarization_skipped_no_llm`), метрика `context.summarize.fallback` | Контекст сжат грубее (середина срезана, а не сжата с сохранением решений); ход не падает |
| `ConversationSummarizer`: вернул пустой/невалидный результат | Считать как сбой → деградация до Prune+Skeletonize | `warning` `summarization_invalid_output` | Как выше |

### 4.2. Реконсиляция (`ContextReconciler.reconcile()` → `ReconcileResult`)

| Ошибка / ситуация | Поведение | Лог / метрика | Влияние на пользователя |
|-------------------|-----------|----------------|--------------------------|
| Реконсайлер **не уверен** в изменении источника (отпечаток нечитаем / `fingerprint()` упал / неоднозначный `diff()`) | Консервативно: `ReconcileResult(state=UPDATED, epoch_broken=True)` — пересобрать `baseline` заново, а не рисковать stale | `warning` `reconcile_uncertain_breaking_epoch`, поля `source_id`, метрика `context.epoch.broken{reason="uncertain"}` | Этот ход дороже (промах prompt-cache), но контекст актуален |
| Изменение замечено вне безопасной границы хода | `ChangeState.DEFERRED` — применить на следующей границе; baseline пока стабилен | `info` `reconcile_deferred`, поле `source_id` | Обновление отложено на 1 ход; не вредит корректности (изменение придёт) |
| `ContextReconciler.snapshot()` упал (не удалось собрать `fingerprints`) | Деградация эпохи: пересобрать baseline (`epoch_broken=True`); как при гидрации | `error` `snapshot_failed_rebuilding_baseline`, метрика `context.epoch.broken{reason="snapshot_error"}` | Дороже на ход; корректно |
| **Сигнал инвалидации файла потерян** (см. слой C: `invalidate()` упал, а snapshot его не «увидел») | Двойная защита от тихого рассинхрона baseline: (1) `ContextSnapshot.diff()` сравнивает Codec-`fingerprints` источников **независимо** от сигнала кэша — расхождение содержимого ловится при следующем `snapshot()`, даже если сигнал не дошёл; (2) счётчик потерянных сигналов из слоя C (`context.invalidation.lost`) служит детектором: ненулевой рост → возможен stale-кэш. Обнаруженное расхождение → `epoch_broken=True` | `warning` `invalidation_signal_missed_detected_by_snapshot`, метрики `context.invalidation.lost`, `context.epoch.broken{reason="signal_missed"}` | Худший случай — один stale-ход до ближайшего `snapshot()`-сравнения, затем самоисцеление через пересборку baseline |

> **Почему это безопасно.** `ContextSnapshot` сравнивает **содержимое через Codec-отпечатки**,
> а не таймстемпы и не доверяет одному лишь сигналу кэша. Сигнал инвалидации — оптимизация
> (раннее срабатывание); отпечатки — гарантия корректности. Единый источник истины из
> [§6 CONSOLIDATED_ARCHITECTURE](./CONSOLIDATED_ARCHITECTURE.md#6-кэширование) (стык Phase 2 ↔ Phase 4)
> делает потерю сигнала восстановимой, а не тихим багом.

---

## 5. Слой D — мультиагентный обмен

Компоненты: `ChildSessionManager.create_child()` / `collect_summary()`,
`process_subagent_response()` → `SubagentResult`. По умолчанию — изоляция в child-сессиях.

Принцип слоя D: **изоляция локализует сбой**. Падение субагента не должно зависать
или обрушивать родительский ход — родитель получает пометку об ошибке как результат.

| Ошибка | Поведение | Лог / метрика | Влияние на пользователя |
|--------|-----------|----------------|--------------------------|
| Субагент упал (исключение в child-сессии) | `process_subagent_response()` возвращает `SubagentResult` с `summary`, описывающим ошибку (напр. «субагент `<scope>` завершился с ошибкой: …»), `token_count` маленький, `source_scope` сохранён | `error` `subagent_failed`, поля `subagent_scope`, `error_type`, метрика `context.subagent.failures` | Родитель видит явную пометку об ошибке в контексте и продолжает (может перепланировать), а не виснет |
| Субагент завис → таймаут child-сессии | `ChildSessionManager.collect_summary()` по таймауту отменяет child-задачу и возвращает `SubagentResult` с пометкой `timeout`; родитель **не блокируется** | `warning` `subagent_timeout`, поля `subagent_scope`, `timeout_sec`, метрика `context.subagent.timeouts` | Родительский ход не зависает; результат субагента помечен как незавершённый |
| `create_child()` упал (не удалось создать child-сессию) | Вернуть родителю `SubagentResult`-ошибку; не ронять родительскую стратегию | `error` `child_session_create_failed`, поле `subagent_scope` | Делегирование не состоялось; родитель уведомлён, продолжает сам |
| Ответ субагента не суммаризуется (LLM суммаризации упал) | Деградация: вернуть усечённый сырой результат субагента (`bound_content`) вместо суммари | `warning` `subagent_summary_degraded`, метрика `context.subagent.summary_fallback` | Родитель получает менее сжатый, но валидный результат |

> Федеративный `share_item()` — кандидат на отказ (ADR-002 §8) и не входит в Phase 0/MVP;
> его failure-режимы здесь не рассматриваются.

---

## 6. Бюджет — деградация после 3 фаз сжатия

Сценарий: `ensure_context_fits()` прогнал все три фазы компактора
(Prune → Skeletonize → Summarize), а `PayloadEnvelope.token_count` всё равно превышает
`max_context_tokens - reserved_tokens`. Это последний рубеж — **краш недопустим**.

| Ошибка | Поведение | Лог / метрика | Влияние на пользователя |
|--------|-----------|----------------|--------------------------|
| После Prune+Skeletonize+Summarize payload не влезает | **Жёсткое усечение** через `TokenBudgetManager.bound_content()` по приоритетам `ContextItem.priority`: вытесняем элементы от низшего приоритета вверх (`file_skeleton`=3 → `terminal_output`=4 → `file_content`=5 → …), сохраняя `system_rules`=10 и `user_prompt`=8 | `warning` `payload_hard_truncated`, поля `before_tokens`, `after_tokens`, `dropped_items`, метрика `context.budget.hard_truncation` | Часть контекста потеряна явно (не тихо); ответ возможен. Логируется как деградация качества |
| `system_rules` (priority ≥ 10) сами по себе превышают бюджет | Конфигурационная аномалия: усечь даже критические как крайнюю меру + `error`-лог (не `raise` в горячем пути — иначе зависнет ход) | `error` `critical_items_exceed_budget`, поля `system_tokens`, `max_context_tokens`, метрика `context.budget.critical_overflow` | Серьёзная деградация (урезан системный промпт); сигнал админу через метрику/алерт, но ход живёт |
| Бюджет рассчитан по `ApproximateTokenCounter` и реальное окно превышено провайдером | Approximate-режим уже закладывает увеличенный `reserved_tokens`; при отказе провайдера по длине — повторное `ensure_context_fits()` с ужесточённым лимитом | `warning` `budget_underestimated_retry`, метрика `context.budget.provider_overflow` | Один лишний цикл сжатия; ход завершается |

> **Граница fail-fast vs. degrade.** Превышение бюджета критическими элементами в FCM-каноне
> трактовалось как `raise` (конфиг-ошибка). В консолидированной архитектуре это **горячий путь**
> (`ensure_context_fits()` внутри цикла подготовки payload), поэтому реакция — деградация с
> громким `error`-логом и метрикой, а fail-fast переносится на валидацию `ContextConfig` при старте.

---

## 7. Инварианты обработки ошибок

Эти инварианты обязательны для всех реализаций слоёв A–D и проверяются тестами.

1. **Горячий путь не бросает.** Методы цикла подготовки payload — `build_context()`,
   `ensure_context_fits()`, `process_subagent_response()` — и всё, что они вызывают
   (`gather()`, `analyze()`, `count()`, `skeletonize()`, `reconcile()`, `summarize()`),
   **никогда не пробрасывают исключение наружу**. Любой внутренний сбой ловится и
   переводится в валидный (возможно деградированный) результат. `raise` разрешён только
   вне горячего пути — при валидации `ContextConfig` на старте.

2. **Деградация всегда логируется — нет тихих сбоев.** Запрещены `except: pass`.
   Каждый фоллбэк сопровождается structured-логом (`event` в snake_case, `error_type`,
   domain-поля) и инкрементом метрики `context.*.fallback` / `context.*.error`. Деградация,
   которую не видно в логах/метриках, считается багом.

3. **Fallback детерминирован.** Один и тот же сбой при одном входе → один и тот же
   деградированный выход. В частности: `CodeSkeletonizer` при ошибке возвращает исходный код
   как есть (стабильно); `TokenCounter` — фиксированную приближённую формулу;
   реконсиляция при неуверенности — всегда `epoch_broken=True`. Это сохраняет стабильность
   `baseline_fingerprint` и предсказуемость поведения под нагрузкой.

4. **Сбой локализован своим слоем.** Ошибка слоя A (сбор) не отменяет слой C (хранение);
   ошибка субагента (D) не валит родителя; потеря сигнала кэша (C) ловится отпечатками
   снапшота (B). Каскад сбоев недопустим: каждый слой имеет собственный безопасный путь.

5. **Корректность важнее экономии.** При конфликте «дёшево, но рискованно stale» против
   «дорого, но актуально» — выбирается актуальность (`epoch_broken=True`, пересборка baseline,
   жёсткое усечение с логом). Потеря prompt-cache хита — приемлемая цена за валидный контекст.

---

## Связанные документы

- [CONSOLIDATED_ARCHITECTURE.md](./CONSOLIDATED_ARCHITECTURE.md) — слои A–D, §4.1 поток данных, §6 кэширование, §7 сжатие
- [INTERFACES.md](./INTERFACES.md) — контракты `ContextManager` и компонентов слоёв
- [DATA_MODELS.md](./DATA_MODELS.md) — `PayloadEnvelope`, `ReconcileResult`, `ContextItem`, `TaskProfile`
- [ADR-002](../architecture/adr/ADR-002-context-manager-consolidation.md) — решения консолидации
