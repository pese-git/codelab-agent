# Context Manager — Консолидированная архитектура

> **Статус:** Канон (отражает [ADR-002](../architecture/adr/ADR-002-context-manager-consolidation.md))
> **Дата:** 25 июня 2026
> **Заменяет:** дизайн-документы `doc/internals/architecture/fcm/` (FCM v2.3) — архивируются на Phase 0.
>
> Этот документ — единый source-of-truth по архитектуре менеджера контекста.
> Он объединяет два ранее независимых дизайна:
> - **CM** (`doc/internals/context-manager/`) — интеллект сбора и жизненный цикл контекста;
> - **FCM** (`doc/internals/architecture/fcm/`) — эффективность хранения и сжатия.
>
> Все архитектурные решения зафиксированы в ADR-002.

---

## Оглавление

1. [Назначение и проблема](#1-назначение-и-проблема)
2. [Принцип консолидации](#2-принцип-консолидации)
3. [Целевая архитектура: слои A–D](#3-целевая-архитектура-слои-ad)
4. [Единая точка входа и путь формирования payload](#4-единая-точка-входа-и-путь-формирования-payload)
5. [Жизненный цикл контекста (инкрементальная модель)](#5-жизненный-цикл-контекста-инкрементальная-модель)
6. [Кэширование](#6-кэширование)
7. [Сжатие контекста](#7-сжатие-контекста)
8. [Мультиагентный обмен](#8-мультиагентный-обмен)
9. [Конфигурация и feature-флаги](#9-конфигурация-и-feature-флаги)
10. [Фазы реализации (roadmap 0–6)](#10-фазы-реализации-roadmap-06)
11. [Структура файлов](#11-структура-файлов)
12. [Маппинг компонентов FCM → консолидированная архитектура](#12-маппинг-компонентов-fcm--консолидированная-архитектура)

---

## 1. Назначение и проблема

**Context Manager** — слой между агентами и LLM, отвечающий за сбор, отслеживание и оптимизацию контекста в мультиагентной системе CodeLab.

Решаемые проблемы:

| Проблема | Решение |
|----------|---------|
| Агент не знает, *что* читать для задачи | `TaskAnalyzer` + `ContextGatherer` + `DependencyGraph` (слой A) |
| Переотправка неизменного контекста каждый ход (дорого на длинных сессиях) | Инкрементальная модель `ContextEpoch` (слой B) |
| Повторные ACP RPC за тем же файлом | `FileContentCache` (слой C) |
| Потеря структуры кода при сжатии | AST-скелетирование `CodeSkeletonizer` (слой C) |
| Переполнение окна контекста | 3-фазное сжатие + `TokenBudgetManager` |
| Загрязнение контекста между агентами | Изоляция через `ChildSessionManager` (слой D) |

---

## 2. Принцип консолидации

Два исходных дизайна отвечали на **разные вопросы** и потому **комплементарны**:

- **CM** — *«ЧТО читать и как обновлять»* (интеллект сбора + жизненный цикл): `TaskAnalyzer`, `ContextGatherer`, `DependencyGraph`, `ContextEpoch`/`Snapshot`/`Reconciliation`, `SkillContextSource`.
- **FCM** — *«КАК хранить дёшево»* (эффективность): `FileContentCache`, `CodeSkeletonizer` (AST), `TokenCounter` (tiktoken), priority-based eviction.

Консолидация — **слияние слоёв**, а не выбор «победителя»: CM — каноническая база (верх воронки), FCM вливается слоем хранения (низ воронки).

---

## 3. Целевая архитектура: слои A–D

```
ContextManager (единая точка входа)
│
├── build_context()              ← все стратегии
├── ensure_context_fits()        ← все стратегии
└── process_subagent_response()  ← мультиагентные стратегии
   │
   ├─ Слой A. Сбор контекста (CM)
   │    TaskAnalyzer → ContextGatherer → DependencyGraph → TokenBudgetManager
   │    SkillContextSource, ContextRegistry / ContextSource
   │
   ├─ Слой B. Жизненный цикл (CM)
   │    ContextEpoch, ContextSnapshot, ContextReconciler, ConversationSummarizer
   │
   ├─ Слой C. Хранение и эффективность (FCM)
   │    FileContentCache + SessionFileCacheRegistry + FileCacheDecorator
   │    CodeSkeletonizer (AST) — фаза Skeletonize компактора
   │    TokenCounter (tiktoken) — подсчёт для TokenBudgetManager
   │    priority-based eviction (ContextItem.priority)
   │
   └─ Слой D. Мультиагентный обмен
        По умолчанию — изоляция через ChildSessionManager
        Федеративный share_item() — кандидат на отказ (см. §8)
```

### Слой A — Сбор контекста (из CM)

| Компонент | Ответственность |
|-----------|------------------|
| `TaskAnalyzer` | Классифицирует задачу (bug_fix/feature/refactor/architecture), извлекает поисковые термины, глубину исследования. LLM-классификация |
| `ContextGatherer` | Пайплайн: `project_tree()` → `search()` → `read_file()` → построение графа → отбор целевых файлов. Через ACP `ToolRegistry` |
| `DependencyGraph` | Карта импортов/зависимостей. `get_dependencies()`/`get_dependents()`. Phase 1 — regex, Phase 5 — рекурсия/tree-sitter |
| `TokenBudgetManager` | Аллокация бюджета (system/history/tool/response) — `allocate()`, `bound_content()` |
| `ContextRegistry` / `ContextSource` | Реестр источников контекста; `render_baseline()` / `render_updates()` |
| `SkillContextSource` | Каталог доступных скиллов в системном промпте + отслеживание изменений |

### Слой B — Жизненный цикл (из CM)

| Компонент | Ответственность |
|-----------|------------------|
| `ContextEpoch` | Иммутабельный baseline + `mid_conversation_messages` (дельты). `get_full_context()` |
| `ContextSnapshot` | Снимок состояния источников; `detect_changes()` через Codec-сравнение (не таймстемпы) |
| `ContextReconciler` | Применение изменений на безопасных границах хода. Состояния `UNCHANGED`/`UPDATED`/`DEFERRED` |
| `ConversationSummarizer` | Интеллектуальная суммаризация диалога при сжатии (сохраняет ключевые решения/контекст) |

### Слой C — Хранение и эффективность (из FCM)

| Компонент | Ответственность |
|-----------|------------------|
| `FileContentCache` / `InMemoryFileCache` | Кэш содержимого файлов по пути (per-session, LRU). Устранение дублей ACP RPC |
| `SessionFileCacheRegistry` | Реестр кэшей по сессиям (lifecycle) |
| `FileCacheDecorator` | Декоратор ToolExecutor: read-cache + write-invalidation. I/O — строго через ACP `ToolRegistry` |
| `CodeSkeletonizer` / `PythonASTSkeletonizer` | AST-сжатие кода до сигнатур (−85% токенов). **Детерминированный** вывод |
| `TokenCounter` / `TiktokenCounter` | Точный подсчёт токенов (fallback — `ApproximateTokenCounter`) |
| `ContextItem` (+priority) | Внутренняя модель элемента контекста; priority для eviction |

### Слой D — Мультиагентный обмен

| Компонент | Ответственность |
|-----------|------------------|
| `ChildSessionManager` | Изоляция субагентов в child-сессиях (по умолчанию) |
| `process_subagent_response()` | Суммаризация ответа субагента для родителя |
| `share_item()` (опц.) | Федеративный шеринг между скоупами. **Кандидат на отказ** (§8) |

---

## 4. Единая точка входа и путь формирования payload

Все 4 стратегии (Single/Orchestrated/Choreography/Hierarchical) проходят через `ContextManager`:

| Стратегия | Методы |
|-----------|--------|
| `SingleStrategy` | `build_context()` + `ensure_context_fits()` |
| `OrchestratedStrategy` | `build_context()` + `process_subagent_response()` + `ensure_context_fits()` |
| `ChoreographyStrategy` | `build_context()` + `process_subagent_response()` (winner only) |
| `HierarchicalStrategy` | `build_context()` + `process_subagent_response()` + `ensure_context_fits()` |

Различие стратегий — только в количестве/координации скоупов; путь формирования payload единый.

---

## 5. Жизненный цикл контекста (инкрементальная модель)

> Решение ADR-002: **принята инкрементальная модель** (обоснование — длинные сессии).

### Почему инкрементальная

При «гидрации каждый ход» стоимость переотправки стабильного префикса растёт линейно с числом ходов (квадратично по сессии). На длинных сессиях это основная статья расхода токенов/латентности. Инкрементальная модель отправляет иммутабельный baseline один раз за эпоху, далее — только дельты → стабильный префикс → кэш-хит у провайдера (или KV/prefix-cache локальных моделей).

### Фундамент: форма `baseline / tail`

API формирования payload **с первого дня** разделяет `baseline (иммутабельный)` и `tail (дельты)`. Это **фундамент, а не фича** — закладывается в Phase 0, иначе поздняя инкрементальность = переписывание ядра.

### Гибридный мост (снимает «точку невозврата»)

1. **Phase 0** — форма данных `baseline/tail` в API.
2. **Phase 1** — MVP-поведение как у гидрации (baseline тривиально пересобирается каждый ход) за этим API.
3. **Phase 4** — включить `ContextEpoch` + `ContextSnapshot` + `ContextReconciler` как оптимизацию за тем же API.

---

## 6. Кэширование

Два кэша **комплементарны**, не избыточны — кэшируют разное на разных границах:

| | `FileContentCache` (слой C) | Provider/epoch prompt-cache (слой B) |
|---|---|---|
| Что кэширует | содержимое файла по пути | токенизированный префикс (baseline) |
| Граница | server ↔ client (ACP RPC) | server ↔ LLM-провайдер (или KV) |
| Что экономит | повторное чтение файла | повторную обработку/оплату токенов |
| Инвалидация | `fs/write` по пути | изменение baseline (через `ContextSnapshot`) |

**Взаимодействие:** контент-кэш отдаёт детерминированное содержимое → файл попадает в baseline байт-в-байт идентично → стабильный префикс → кэш-хит. То же требование к `CodeSkeletonizer` (детерминированный вывод).

**Требование интеграции (Phase 2 ↔ Phase 4):** `FileCacheDecorator` и snapshot-детект **обязаны слушать единый источник истины об изменениях файла** (Codec-сравнение), иначе — рассинхрон baseline (тихий баг).

---

## 7. Сжатие контекста

Единый компактор — **3 фазы**:

1. **Prune** — FIFO-удаление старых tool-выводов (сохраняются первые 2 и последние N сообщений).
2. **Skeletonize** — AST-сжатие кода (`CodeSkeletonizer`, слой C). Заменяет тела функций на `...`, сохраняя сигнатуры.
3. **Summarize** — LLM-суммаризация (`ConversationSummarizer`, слой B), если Prune+Skeletonize недостаточно.

Триггер — превышение `max_context_tokens - reserved_tokens`. Деградация: при недоступности LLM — только Prune+Skeletonize.

---

## 8. Мультиагентный обмен

> Решение ADR-002: **изоляция — по умолчанию и единственный путь в MVP**.

- **Изоляция (по умолчанию):** субагенты в child-сессиях, родителю возвращается только суммаризованный результат. Чистые границы, предсказуемый бюджет.
- **Федерация (`share_item()`) — кандидат на полный отказ.** Обе её выгоды уже покрыты:
  1. экономия на повторном чтении файла → даёт `FileContentCache` (per-session);
  2. передача производного контекста → `process_subagent_response()`.

  При этом федерация конфликтует с изоляцией и со стабильностью эпох (прошаренный item рвёт baseline другого агента). Включать — только за флагом в Phase 6, с обоснованием сценария, не закрываемого изоляцией.

---

## 9. Конфигурация и feature-флаги

Master-switch заменяет FCM-флаг `enable_fcm`. Подфлаги мапятся на слои/фазы → канареечный rollout.

```toml
[agents.context]
enabled = false                  # Master switch: новый ContextManager vs legacy

[agents.context.gather]          # Слой A (Phase 1)
enabled = true
recursive_dependencies = false   # Phase 5
use_tree_sitter = false          # Phase 5

[agents.context.storage]         # Слой C (Phase 2)
use_tiktoken = true
file_cache = true
skeletonize = true

[agents.context.storage.cache]
max_files = 1000

[agents.context.lifecycle]       # Слой B (Phase 4)
incremental = false              # false → MVP «гидрация каждый ход»

[agents.context.budget]          # Phase 1
max_context_tokens = 128000
reserved_tokens = 4096
system_share = 0.20
history_share = 0.50
tool_output_share = 0.20
response_buffer_share = 0.10

[agents.context.multiagent]      # Слой D (Phase 6)
federation = false               # КАНДИДАТ НА ОТКАЗ
```

**Два «не-флага» (фундамент):** форма payload `baseline/tail` и изоляция мультиагента — есть всегда, флагом не управляются.

**Env-overrides** (приоритет над TOML): `CODELAB_CONTEXT_ENABLED`, `CODELAB_CONTEXT_ROLLOUT_PERCENT`, `CODELAB_CONTEXT_GATHER`, `CODELAB_CONTEXT_TIKTOKEN`, `CODELAB_CONTEXT_FILE_CACHE`, `CODELAB_CONTEXT_SKELETONIZE`, `CODELAB_CONTEXT_INCREMENTAL`, `CODELAB_CONTEXT_FEDERATION` и др. (полная таблица — в ADR-002).

---

## 10. Фазы реализации (roadmap 0–6)

> Принципы порядка: `baseline/tail` — в Phase 0; слой C (FCM) — до инкрементальности (стабилизирует baseline); инкрементальность — поздняя оптимизация за зафиксированным API.

### Phase 0 — Каркас + контракты (1 нед)
- **Что:** заморозить интерфейсы `ContextManager` (`build_context`/`ensure_context_fits`/`process_subagent_response`); **API payload с разделением `baseline/tail`**; feature-флаги `agents.context.*`; старт от `context_compactor.py` как baseline; архивировать `fcm/` → `archive/fcm/`.
- **Acceptance:** интерфейсы зафиксированы; форма `baseline/tail` есть в API; флаг `enabled=false` → работает legacy.

### Phase 1 — MVP-сбор (3 нед)
- **Что:** `TaskAnalyzer` → `ContextGatherer` → `DependencyGraph(regex)` → `TokenBudgetManager`; всё через ACP `ToolRegistry`. Поведение payload — гидрация.
- **Acceptance:** для типовой задачи система сама отбирает релевантные файлы; e2e на одной модели; бюджет токенов соблюдается. Качество ≥80%.

### Phase 2 — Слой хранения C (2 нед)
- **Что:** `TokenCounter`(tiktoken), `FileContentCache`+`SessionFileCacheRegistry`+`FileCacheDecorator`, `CodeSkeletonizer`(AST) как фаза Skeletonize.
- **Acceptance:** повторное чтение файла не вызывает RPC (кэш-хит); скелетирование детерминировано и даёт ожидаемую экономию; подсчёт токенов точный.

### Phase 3 — Источники + сжатие (1 нед)
- **Что:** `ContextRegistry`/`ContextSource`, `SkillContextSource`, единый 3-фазный компактор (Prune→Skeletonize→Summarize), `ConversationSummarizer`.
- **Acceptance:** скиллы рендерятся как источник; компактор проходит все 3 фазы; деградация без LLM работает.

### Phase 4 — Инкрементальность (2 нед)
- **Что:** `ContextEpoch` + `ContextSnapshot`(Codec-детект) + `ContextReconciler` за тем же `baseline/tail` API; включение provider/KV prefix-cache. **Единый сигнал инвалидации файла** (стык с Phase 2).
- **Acceptance:** baseline отправляется один раз за эпоху; дельты применяются на границах хода; нет рассинхрона при `fs/write`; измеримый кэш-хит на длинной сессии.

### Phase 5 — Полный DependencyGraph (2 нед)
- **Что:** рекурсивное разрешение зависимостей; опц. tree-sitter вместо regex.
- **Acceptance:** граф разрешает транзитивные зависимости; точность отбора файлов на больших проектах растёт.

### Phase 6 — Мультиагент (2 нед)
- **Что:** `process_subagent_response`, `ChildSessionManager` (изоляция, default); опц. федеративный `share_item()` за флагом.
- **Acceptance:** субагенты изолированы; родитель получает суммаризованный результат; федерация — только при обоснованном сценарии.

**Итого ~13 недель.** Критический путь к ценности: Phase 0→1 (умный контекст), Phase 4 (экономия на длинных сессиях).

### Профит для конечного пользователя по фазам

Что чувствует разработчик, общающийся с агентом, после каждой фазы:

| Фаза | Профит для пользователя |
|------|--------------------------|
| **Phase 0** | Ничего видимого — фундамент. Косвенно: возможность безопасного канареечного включения дальше |
| **Phase 1** | **Релевантность.** Агент сам находит нужные файлы под задачу — не надо вручную прикладывать контекст. Качество ответов ≥80% (против ~40% без сбора) |
| **Phase 2** | **Скорость + ёмкость.** Повторные чтения файлов без лишних запросов к клиенту (меньше задержек); AST-сжатие умещает больше кода в окно без потери структуры |
| **Phase 3** | **Выносливость диалога.** При переполнении окна контекст сжимается умно (скелеты + суммаризация ключевых решений), а не обрезается слепо; агент знает о доступных скиллах |
| **Phase 4** | **Экономия на длинных сессиях.** Стабильный префикс → prompt-cache хит: каждый ход дешевле и быстрее, стоимость не растёт квадратично (для локальных моделей — ниже латентность через KV-кэш) |
| **Phase 5** | **Точность на масштабе.** Подтягиваются транзитивные зависимости → меньше «пропустил связанный модуль» в больших проектах |
| **Phase 6** | **Сложные задачи без потери фокуса.** Субагенты исследуют в изоляции и возвращают сжатый результат → главный диалог остаётся чистым |

**Ось ценности:** Phase 1 — релевантность · Phase 2 — скорость/ёмкость · Phase 3 — выносливость диалога · Phase 4 — экономия на длинных сессиях · Phase 5 — точность на масштабе · Phase 6 — сложные задачи без замусоривания. Самый ранний ощутимый профит — Phase 1; самый значимый для длинных сессий — Phase 4.

---

## 11. Структура файлов

```
src/codelab/server/agent/context/
├── manager.py            # ContextManager (единая точка входа)
│
├── # Слой A: сбор
├── task_analyzer.py      # TaskAnalyzer
├── gatherer.py           # ContextGatherer
├── dependency_graph.py   # DependencyGraph
├── budget.py             # TokenBudgetManager
├── registry.py           # ContextRegistry, ContextSource, SkillContextSource
│
├── # Слой B: жизненный цикл
├── epoch.py              # ContextEpoch
├── snapshot.py           # ContextSnapshot, ContextReconciler
├── summarizer.py         # ConversationSummarizer
│
├── # Слой C: хранение и эффективность
├── token_counter.py      # TokenCounter, TiktokenCounter
├── ast_skeletonizer.py   # CodeSkeletonizer, PythonASTSkeletonizer
├── file_cache.py         # FileContentCache, InMemoryFileCache, SessionFileCacheRegistry
├── compactor.py          # ContextCompactor (3 фазы)
├── items.py              # ContextItem
│
└── # Слой D: мультиагент
    └── child_session.py  # ChildSessionManager

src/codelab/server/tools/executors/decorators/
└── file_cache.py         # FileCacheDecorator

# Изменяемые файлы
src/codelab/server/agent/execution_engine.py   # единый путь build_context()
src/codelab/server/protocol/state.py            # +current_agent_scope (если нужно)
```

---

## 12. Маппинг компонентов FCM → консолидированная архитектура

| FCM-компонент | Судьба | Слой |
|---------------|--------|------|
| `FederatedContextManager` | Растворяется в едином `ContextManager` | вход |
| `AgentContextScope` | Реализация изоляции; федеративный шеринг — кандидат на отказ | D |
| `ContextItem` (+priority) | Внутренняя модель элемента; priority для eviction | C |
| `FileContentCache` / `InMemoryFileCache` | Принимается as-is | C |
| `SessionFileCacheRegistry` | Принимается as-is | C |
| `FileCacheDecorator` | Принимается; I/O — через ACP `ToolRegistry` | C |
| `CodeSkeletonizer` / `PythonASTSkeletonizer` | Принимается как фаза Skeletonize | C |
| `TokenCounter` / `TiktokenCounter` | Принимается для `TokenBudgetManager` | C |
| `ContextCompactor` (3 фазы) | Сливается: Prune→Skeletonize(C)→Summarize(B) | B/C |
| `hydrate_from_history()` | Заменяется на `ContextEpoch` + реконсиляцию | B |
| `SubAgentCoordinator` | Сливается с `process_subagent_response()` + `ChildSessionManager` | D |
| `agents.context.enable_fcm` | Заменён на `agents.context.*` подфлаги | конфиг |

---

## Связанные документы

- [ADR-002: Консолидация двух дизайнов Context Manager](../architecture/adr/ADR-002-context-manager-consolidation.md) — все архитектурные решения
- `doc/internals/context-manager/` — каноническая база CM (сбор/жизненный цикл)
- `doc/internals/archive/fcm/` — архивированные дизайны FCM (детальные спеки компонентов слоя C)
- `doc/internals/system-architecture/CONTEXT_LIFECYCLE.md` — жизненный цикл контекста
