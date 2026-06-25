# ADR-002: Консолидация двух дизайнов Context Manager (FCM ↔ CM)

**Дата:** 25 июня 2026
**Статус:** Принято
**Контекст:** Управление контекстом в мультиагентной архитектуре
**Авторы:** —
**Связанные документы:**
- `doc/internals/architecture/fcm/` — Federated Context Manager (FCM), design v2.3 — ветка `feature/context-manager`
- `doc/internals/context-manager/` — Context Manager (CM), Roadmap Phase 0–6 — ветка `feature/agent`
- `doc/internals/system-architecture/CONTEXT_LIFECYCLE.md`
- `src/codelab/server/agent/context_compactor.py` — текущий legacy-компактор

---

## Контекст

В проекте параллельно и независимо возникли **два дизайна одного и того же компонента** — менеджера контекста для мультиагентной системы:

| | **FCM** (`feature/context-manager`) | **CM** (`feature/agent`) |
|---|---|---|
| Каталог документации | `doc/internals/architecture/fcm/` | `doc/internals/context-manager/` |
| Статус | Design v2.3 | Design, Roadmap Phase 0–6 |
| Реализация | ❌ кода нет | ❌ кода нет (только legacy `context_compactor.py`) |
| План | 7–8 недель (Phase 0–5) | 11 недель (Phase 0–6) |
| Источник истины | сам себя | сам себя |

### Проблема

1. **Два source-of-truth.** Две ветки описывают канон для одного компонента. `COMPARISON.md` в CM сравнивает дизайн с внешними системами (Claude Code, OpenCode, Cursor, Codex/Gemini), но **не упоминает FCM** — команды проектировали независимо.
2. **Конфликт терминологии.** Оба дизайна заявляют «3 уровня/слоя», но с разным смыслом; оба поглощают `ContextCompactor` и `TokenSlicer`, но по-разному; оба заявляют «единую точку входа для всех стратегий».
3. **Риск двойной реализации.** Без решения до начала кода две группы напишут несовместимые подсистемы.
4. **Потеря сильных идей.** Дизайны не дублируют, а **дополняют** друг друга — наивный выбор «одного победителя» потеряет ценные части другого.

### Ключевое наблюдение

Дизайны отвечают на **разные вопросы**:

- **CM** — *«ЧТО читать и как обновлять контекст»* (интеллект сбора): `TaskAnalyzer`, `ContextGatherer`, `DependencyGraph`, `ContextEpoch`/инкрементальная реконсиляция, `SkillContextSource`.
- **FCM** — *«КАК хранить дёшево и делить между агентами»* (эффективность хранения): `FileContentCache` (устранение дублей RPC), AST-скелетонайзер, priority-based eviction, изолированные скоупы с федеративным шерингом.

Это делает консолидацию не выбором «или-или», а **слиянием комплементарных слоёв**.

---

## Сравнение дизайнов

### Концептуальная ось

| Аспект | FCM | CM |
|--------|-----|-----|
| Центральная метафора | Федерация изолированных **скоупов** агентов | Единый менеджер с **эпохами** и источниками |
| Главная проблема | Дубли RPC, потеря при сжатии, приоритеты | Сбор *правильного* контекста + инкрементальность |
| Сбор контекста | Пассивный (агент кладёт прочитанное в scope) | Активный (`TaskAnalyzer`+`Gatherer`+`Graph` сами решают) |
| Кэширование | Свой RAM `FileContentCache` | Иммутабельный `ContextEpoch`, кэш на стороне провайдера |
| Инкрементальность | нет (гидратация каждый ход — MVP) | ✅ `ContextReconciliation` (только изменённые источники) |
| Сжатие | 3 фазы: Prune→Skeletonize→Summarize + AST | Prune + `ConversationSummarizer`, AST отложен (Phase 4/X) |
| Детект изменений | по `last_accessed` | по Codec-сравнению (не таймстемпы) |
| Мультиагент | `share_item()` федеративно | `process_subagent_response()` + `ChildSessionManager` (изоляция) |
| Скиллы | — | ✅ `SkillContextSource` |
| Анализ задачи | — | ✅ `TaskAnalyzer` |
| Файловый I/O | свой Decorator + `ClientRPCBridge` | строго ACP `ToolRegistry` (LOCAL/REMOTE паритет) |
| Master switch | `agents.context.enable_fcm` | не определён |

### Совпадающие идеи (берём как общий фундамент)

1. Единая точка входа `build_context()` для всех 4 стратегий (Single/Orchestrated/Choreography/Hierarchical).
2. Замена `HybridContextManager`.
3. Поглощение `ContextCompactor` и `TokenSlicer` внутрь нового менеджера.
4. Двухфазная база сжатия Prune→Summarize (наследуется от текущего `context_compactor.py`).
5. Стадийное внедрение через нумерованные фазы с MVP-first.
6. Сокрытие сложности от LLM (low-level tools видны, runtime-сервисы — нет).

---

## Решение

Принять **единый Context Manager**, объединяющий обе концепции в одну целевую архитектуру. Каталог `doc/internals/context-manager/` (CM) становится **канонической базой** (он шире охватывает сбор контекста и жизненный цикл), а FCM вливается в него как **слой хранения и эффективности** (Storage & Efficiency Layer).

### Обоснование выбора базы

- CM покрывает «верх» воронки (что читать, как обновлять, скиллы, ACP-паритет, инкрементальность) — это то, что нельзя «доклеить» позже без переписывания.
- FCM по сути — детализированная реализация хранилища/сжатия, которая встаёт **под** воронкой CM как конкретные реализации абстракций `TokenBudgetManager`/`ContextCompactor`.
- У CM есть `COMPARISON.md` с внешним бенчмаркингом и более проработанный жизненный цикл (`CONTEXT_LIFECYCLE.md`).

### Целевая архитектура (единая)

```
ContextManager (единая точка входа — из CM)
│
├── build_context()           ← все стратегии
├── ensure_context_fits()     ← все стратегии
└── process_subagent_response() ← мультиагентные стратегии
   │
   ├─ Слой A. Сбор контекста (из CM)
   │    TaskAnalyzer → ContextGatherer → DependencyGraph → TokenBudgetManager
   │    SkillContextSource, ContextRegistry / ContextSource
   │
   ├─ Слой B. Жизненный цикл (из CM)
   │    ContextEpoch, ContextSnapshot, ContextReconciliation, ConversationSummarizer
   │
   ├─ Слой C. Хранение и эффективность (из FCM)
   │    FileContentCache + SessionFileCacheRegistry + FileCacheDecorator
   │    CodeSkeletonizer (AST) — реализация фазы Skeletonize компактора
   │    TokenCounter (tiktoken) — реализация подсчёта для TokenBudgetManager
   │    priority-based eviction (ContextItem.priority)
   │
   └─ Слой D. Мультиагентный обмен
        По умолчанию — изоляция через ChildSessionManager (из CM)
        Федеративный share_item() (FCM) — кандидат на отказ (см. «Решение по мультиагентному обмену»)
```

### Маппинг компонентов FCM → CM

| FCM-компонент | Судьба в единой архитектуре | Целевой слой |
|---------------|------------------------------|--------------|
| `FederatedContextManager` | Растворяется в едином `ContextManager` (его методы) | вход |
| `AgentContextScope` | Сохраняется как реализация изоляции; федеративный шеринг — кандидат на отказ | D |
| `ContextItem` (+priority) | Внутренняя модель элемента контекста; priority используется для eviction | C |
| `FileContentCache` / `InMemoryFileCache` | **Принимается as-is** — закрывает дубли RPC, чего нет в CM | C |
| `SessionFileCacheRegistry` | **Принимается as-is** | C |
| `FileCacheDecorator` | Принимается, но I/O — строго через ACP `ToolRegistry` (правило CM) | C |
| `CodeSkeletonizer` / `PythonASTSkeletonizer` | **Принимается** как реализация фазы Skeletonize (CM откладывал AST на Phase 4/X) | C |
| `TokenCounter` / `TiktokenCounter` | **Принимается** как реализация подсчёта токенов для `TokenBudgetManager` | C |
| `ContextCompactor` (ABC, 3 фазы) | Сливается с CM-сжатием: Prune→Skeletonize(FCM)→Summarize(`ConversationSummarizer` CM) | B/C |
| `hydrate_from_history()` | Заменяется на `ContextEpoch` + инкрементальную реконсиляцию CM (мощнее) | B |
| `SubAgentCoordinator` (бывш. Hybrid) | Сливается с `process_subagent_response()` + `ChildSessionManager` | D |
| `agents.context.enable_fcm` (master switch) | Переименовать в `agents.context.*` подфлаги по слоям | конфиг |

### Маппинг конфликтов имён

| Имя в FCM | Имя в CM | Решение |
|-----------|----------|---------|
| `ContextManager(ABC)` | `ContextManager` (конкретный, единая точка входа) | Канон — CM; FCM-ABC отбрасывается |
| `ContextCompactor` (ABC, 3 фазы) | `ContextCompactor` (legacy, 2 фазы) | Единый компактор: 3 фазы, AST из FCM, summarizer из CM |
| «3 слоя» (utils/compaction/orchestration) | «3 уровня» (tools/context-tools/runtime) | Принять терминологию CM (уровни абстракции); FCM-слои становятся внутренними слоями A–D |
| `TokenCounter` (FCM) | `TokenBudgetManager` (CM) | Разные роли: `TokenCounter` = подсчёт, `TokenBudgetManager` = аллокация; первый используется вторым |

### Что берём от каждого (итог)

**От CM (база):** `TaskAnalyzer`, `ContextGatherer`, `DependencyGraph`, `ContextEpoch`/`Snapshot`/`Reconciliation`, `ConversationSummarizer`, `SkillContextSource`, `ContextRegistry`/`ContextSource`, строгая ACP-интеграция, изоляция субагентов.

**От FCM (вливается):** `FileContentCache`(+Registry+Decorator), `PythonASTSkeletonizer`, `TiktokenCounter`, priority-based eviction, опциональный федеративный `share_item()`.

---

## Последствия

### Положительные
- Один source-of-truth и единый roadmap вместо двух конкурирующих.
- Сохраняются сильные стороны обоих дизайнов (интеллект сбора + эффективность хранения).
- AST-скелетирование и устранение дублей RPC (готовые проработки FCM) ускоряют CM-фазы.
- Чёткое разделение ролей: «что читать» (CM) vs «как хранить» (FCM).

### Отрицательные / риски
- Объединённый roadmap длиннее (нужно пересобрать фазы; ориентир — 11+ недель).
- Требуется переписать оба `COMPARISON`/`README`, чтобы убрать дублирование.
- Конфликт `ContextCompactor` (2 vs 3 фазы) и судьба legacy `context_compactor.py` требуют отдельной задачи миграции.
- Федеративный шеринг (FCM) — самая спорная часть; выносится за флаг и решается позже.

### Открытые вопросы (требуют отдельных ADR/решений)
1. ~~Единый roadmap: как пересобрать Phase 0–6 (CM) с вкраплением слоя C (FCM)?~~ — **решено**, см. раздел «Единый roadmap».
2. ~~Кэш файлов: совместимы ли RAM-кэш FCM и provider-side caching эпох CM, или один избыточен?~~ — **решено**, см. раздел «Решение по кэшированию».
3. ~~Мультиагент: изоляция (CM) по умолчанию + федерация (FCM) за флагом — или отказаться от федерации?~~ — **решено**, см. раздел «Решение по мультиагентному обмену».
4. ~~Финальная схема конфиг-флагов `agents.context.*`.~~ — **решено**, см. раздел «Схема конфиг-флагов».
5. ~~Кто владелец объединённого канона и куда переносится `doc/internals/architecture/fcm/` (архив или merge в `context-manager/`)?~~ — **решено**, см. раздел «Решение по владельцу канона и судьбе `fcm/`».

---

## Решение по жизненному циклу контекста

Это самостоятельная развилка внутри консолидации, фиксируется отдельно, т.к. определяет фундамент формирования payload.

### Развилка: две модели

| Модель | Суть | Источник |
|--------|------|----------|
| **Гидрация каждый ход** | payload пересобирается заново из истории/скоупа на каждом обращении к LLM | FCM |
| **Инкрементальная** | иммутабельный `ContextEpoch` baseline + дельты; `ContextSnapshot` детектит изменения, `ContextReconciliation` применяет их на границах хода | CM |

### Сравнение

| Критерий | Гидрация (FCM) | Инкрементальная (CM) |
|---|---|---|
| Сложность реализации | 🟢 низкая | 🔴 высокая |
| Стоимость токенов (длинные сессии) | 🔴 высокая (квадратично по сессии) | 🟢 низкая |
| Provider-side prompt caching / KV prefix-cache | 🔴 плохо (нестабильный префикс) | 🟢 отлично (стабильный baseline) |
| Латентность сборки/ход | 🟡 растёт с историей | 🟢 амортизируется |
| Риск рассинхрона контекста | 🟢 практически нет | 🟡 реальный класс багов |
| Тестируемость / replay | 🟢 простая (детерминированный вход) | 🟡 зависит от цепочки дельт |
| Можно добавить позже | — | 🔴 нет, это фундамент |

### Решение

**Принимается инкрементальная модель (CM) как целевая.**

**Обоснование — длинные сессии (подтверждённое требование).** При гидрации стоимость переотправки стабильного префикса растёт линейно с числом ходов, а суммарно по сессии — квадратично. На длинных сессиях это становится основной статьёй расхода токенов и латентности. Эффект присутствует даже без биллингового prompt caching: локальные модели (vLLM/llama.cpp, ср. ветки `llm/gemma4_26b`, `llm/qwen3.6_27b`) дают KV/prefix-cache хит на стабильном префиксе — выигрыш в latency/compute. На провайдерах с prompt caching (Claude и совместимые) выигрыш дополнительно денежный.

Главный минус инкрементальной модели — риск рассинхрона — на длинной сессии относительно **снижается**: один протестированный механизм реконсиляции окупается на сотнях ходов, тогда как налог гидрации платится каждый ход.

### Как внедрять — гибридный мост (снимает «точку невозврата»)

Инкрементальность — это **фундамент, а не фича**: добавить её поздно = переписать ядро формирования payload. Поэтому:

1. **Phase 0 — форма данных сразу.** API формирования payload с явным разделением `baseline (иммутабельный) / tail (дельты)`. Дёшево, фиксирует контракт.
2. **Phase 1 — MVP-поведение как у гидрации** за этим интерфейсом (`baseline` тривиально пересобирается каждый ход). Быстро, корректно, тестируемо.
3. **Phase 2 — включить `ContextEpoch` + `ContextSnapshot` + `ContextReconciliation`** как оптимизацию за тем же API, без переписывания ядра.

Итог: поведение FCM на старте, форма данных CM с первого дня. Инкрементальность фиксируется как **требование**, а не «возможно позже».

---

## Единый roadmap

Пересобирает фазы CM (0–6) с вплетённым слоем хранения FCM (слой C) и решением по жизненному циклу выше.

### Принципы порядка фаз
1. **`baseline/tail`-форма payload — в Phase 0** (фундамент, не фича; закрывает точку невозврата по инкрементальности).
2. **Слой C (FCM)** — это реализации абстракций сбора/бюджета; идёт *после* появления интерфейсов, но *до* инкрементальности: скелетирование и кэш файлов стабилизируют содержимое baseline → усиливают кэш-хит.
3. **Инкрементальность** (`Epoch`/`Snapshot`/`Reconciliation`) — поздняя оптимизация за уже зафиксированным API.

### Фазы

| Phase | Что | Источник | Зачем здесь |
|---|---|---|---|
| **0. Каркас + контракты** (1 нед) | Заморозить интерфейсы `ContextManager` (`build_context`/`ensure_context_fits`/`process_subagent_response`); **API payload с разделением `baseline/tail`**; feature-флаги `agents.context.*`; старт от `context_compactor.py` как baseline | CM + решение по lifecycle | Точка невозврата по инкрементальности закрывается здесь |
| **1. MVP-сбор** (3 нед) | `TaskAnalyzer` → `ContextGatherer` → `DependencyGraph(regex)` → `TokenBudgetManager`; всё через ACP `ToolRegistry`. Поведение payload — гидрация (baseline тривиально пересобирается) | CM | «Умный» контекст + рабочий e2e на простой модели жизненного цикла |
| **2. Слой хранения C** (2 нед) | `TokenCounter`(tiktoken), `FileContentCache`+`SessionFileCacheRegistry`+`FileCacheDecorator` (устранение дублей RPC), `CodeSkeletonizer`(AST) как фаза Skeletonize компактора | **FCM** | Стабилизирует содержимое baseline → готовит почву для кэш-хита перед инкрементальностью |
| **3. Источники + сжатие** (1 нед) | `ContextRegistry`/`ContextSource`, `SkillContextSource`, единый 3-фазный компактор (Prune→Skeletonize(C)→Summarize), `ConversationSummarizer` | CM + FCM | Полный набор источников за реестром; финализация сжатия |
| **4. Инкрементальность** (2 нед) | `ContextEpoch` + `ContextSnapshot`(Codec-детект) + `ContextReconciliation` за тем же `baseline/tail` API; включение provider/KV prefix-cache | CM | Главный выигрыш для длинных сессий; без переписывания ядра |
| **5. Полный DependencyGraph** (2 нед) | рекурсивное разрешение зависимостей, опц. tree-sitter вместо regex | CM | Точность отбора файлов на больших проектах |
| **6. Мультиагент** (2 нед) | `process_subagent_response`, `ChildSessionManager` (изоляция, default); опц. федеративный `share_item()` (FCM) за флагом | CM + FCM(opt) | Самая спорная часть — последней, за флагом |

**Итого ~13 недель.** Критический путь к ценности: Phase 0→1 (умный контекст), Phase 4 (экономия на длинных сессиях).

### Отличия от двух исходных планов
- Слой C (FCM) поднят **раньше** инкрементальности (в исходном FCM-плане он был ядром, в CM AST откладывался на Phase 4/X) — скелетирование/кэш стабилизируют baseline перед `Epoch`.
- Инкрементальность (CM Phase 3) сдвинута на Phase 4 — после слоя хранения, но за `baseline/tail` API из Phase 0.
- Федеративный шеринг FCM — в самый конец, опционально.

---

## Решение по кэшированию

`FileContentCache` (FCM) и provider/epoch prompt-cache (CM) — **не избыточны, а комплементарны**: кэшируют разные вещи на разных границах системы.

| | `FileContentCache` (FCM) | Provider/epoch prompt-cache (CM) |
|---|---|---|
| Что кэширует | содержимое файла по пути | токенизированный префикс промпта (baseline) |
| Граница | server ↔ client (**ACP RPC**) | server ↔ LLM-провайдер (или локальный KV) |
| Что экономит | повторное чтение файла (round-trip, I/O) | повторную обработку/оплату токенов |
| Ключ | путь файла + сессия | хэш стабильного префикса |
| Инвалидация | `fs/write` по пути | изменение baseline (через `ContextSnapshot`) |

Один отвечает на «не читай тот же файл дважды по сети», другой — «не плати за те же токены дважды у модели». Удаление любого оставляет дыру.

### Взаимодействие
Первый кэш **усиливает** второй: `FileContentCache` отдаёт детерминированное содержимое → файл попадает в baseline байт-в-байт идентично → стабильный префикс → кэш-хит у провайдера. То же требование к `CodeSkeletonizer`: скелет должен быть детерминированным, иначе ломает префикс.

### Требование интеграции (Phase 2 ↔ Phase 4)
Главный риск — не избыточность, а **рассинхрон инвалидаций**. При `fs/write`:
- `FileContentCache.invalidate(path)` сбрасывает контент-кэш, **но**
- если файл в baseline эпохи, изменение должен заметить `ContextSnapshot` и обработать `ContextReconciliation` (обновить/разорвать эпоху).

Если инвалидация контента не доходит до эпохи — модель работает на устаревшем baseline (тихий баг рассинхрона). Поэтому `FileCacheDecorator` (Phase 2) и snapshot-детект (Phase 4) **обязаны слушать единый источник истины об изменениях файла** (Codec-сравнение CM), а не два независимых сигнала. Фиксируется как требование на стыке Phase 2 и Phase 4.

---

## Решение по мультиагентному обмену

**Изоляция (CM) — по умолчанию и единственный путь в MVP.** Федеративный шеринг (FCM `share_item()`) — отложенный кандидат на **полный отказ**, а не «потом за флагом».

### Подходы
- **Изоляция (CM):** субагенты работают в child-сессиях, возвращают родителю только суммаризованный результат (`process_subagent_response` + `ChildSessionManager`). Чистые границы, предсказуемый токен-бюджет, нет перекрёстного загрязнения.
- **Федерация (FCM):** `share_item()` передаёт `ContextItem` напрямую между скоупами (search-агент прочитал файл → «делится» с coder-агентом).

### Почему федерация — кандидат на отказ
Обе её выгоды уже покрыты другими решениями roadmap:
1. **Экономия на повторном чтении файла** → даёт `FileContentCache` (Phase 2): кэш на уровне **сессии**, поэтому coder-агент читает тот же путь с кэш-хитом без RPC. Шеринг ничего не добавляет.
2. **Передача производного контекста** (отчёты, скелеты) → это `process_subagent_response()` через суммаризацию.

При этом издержки реальны:
- **Конфликт с изоляцией:** прямой шеринг сырых items размывает границы агентов и предсказуемость их бюджетов.
- **Конфликт с жизненным циклом:** item, прошаренный в середине диалога, меняет baseline другого агента → разрыв эпохи → потеря prompt-cache-хита (то, что оптимизировали в Phase 4).

### Решение
Федерацию **не строить спекулятивно**. Если она когда-либо вернётся — только за флагом в Phase 6, с конкретным сценарием, который не закрывается `FileContentCache` + `process_subagent_response`. Бремя доказательства — на том, кто захочет её включить.

---

## Схема конфиг-флагов

Флаги мапятся на слои/фазы roadmap → канареечный rollout без переписывания конфига. Master-switch заменяет FCM-флаг `agents.context.enable_fcm`.

```toml
[agents.context]
# Master switch: новый ContextManager vs legacy context_compactor.py
enabled = false

# --- Слой A: сбор контекста (Phase 1) ---
[agents.context.gather]
enabled = true                   # TaskAnalyzer → ContextGatherer → DependencyGraph
recursive_dependencies = false   # Phase 5: рекурсивный обход графа (иначе 1 уровень)
use_tree_sitter = false          # Phase 5: tree-sitter вместо regex

# --- Слой C: хранение и эффективность (Phase 2) ---
[agents.context.storage]
use_tiktoken = true              # точный подсчёт, иначе ApproximateTokenCounter
file_cache = true                # FileContentCache: устранение дублей ACP RPC
skeletonize = true               # CodeSkeletonizer (AST) как фаза компактора

[agents.context.storage.cache]
max_files = 1000                 # LRU-предел кэша файлов на сессию

# --- Слой B: жизненный цикл (Phase 4) ---
[agents.context.lifecycle]
# baseline/tail форма payload — фундамент (Phase 0), флагом НЕ управляется.
incremental = false              # ContextEpoch + Snapshot + Reconciliation.
                                 # false → MVP-поведение «гидрация каждый ход»

# --- Бюджет токенов (Phase 1) ---
[agents.context.budget]
max_context_tokens = 128000
reserved_tokens = 4096
system_share = 0.20              # доли аллокации (TokenBudgetManager)
history_share = 0.50
tool_output_share = 0.20
response_buffer_share = 0.10

# --- Слой D: мультиагент (Phase 6) ---
[agents.context.multiagent]
# изоляция (ChildSessionManager) — всегда, флагом не управляется.
federation = false               # share_item() между скоупами.
                                 # КАНДИДАТ НА ОТКАЗ — включать только с обоснованием
```

### Два «не-флага» (фундамент, не переключатели)
- **`baseline/tail` форма payload** (Phase 0) — есть всегда; `lifecycle.incremental` управляет лишь тем, заполняется ли epoch инкрементально или baseline пересобирается каждый ход.
- **Изоляция мультиагента** (`ChildSessionManager`) — всегда; флагом управляется только опциональная `federation`.

### Env-overrides

Для канареечного rollout и CI каждый флаг перекрывается переменной окружения (приоритет выше TOML):

| Переменная | Перекрывает | Тип |
|---|---|---|
| `CODELAB_CONTEXT_ENABLED` | `agents.context.enabled` | bool |
| `CODELAB_CONTEXT_ROLLOUT_PERCENT` | — (канареечный % сессий) | int 0–100 |
| `CODELAB_CONTEXT_GATHER` | `agents.context.gather.enabled` | bool |
| `CODELAB_CONTEXT_RECURSIVE_DEPS` | `agents.context.gather.recursive_dependencies` | bool |
| `CODELAB_CONTEXT_TREE_SITTER` | `agents.context.gather.use_tree_sitter` | bool |
| `CODELAB_CONTEXT_TIKTOKEN` | `agents.context.storage.use_tiktoken` | bool |
| `CODELAB_CONTEXT_FILE_CACHE` | `agents.context.storage.file_cache` | bool |
| `CODELAB_CONTEXT_SKELETONIZE` | `agents.context.storage.skeletonize` | bool |
| `CODELAB_CONTEXT_CACHE_MAX_FILES` | `agents.context.storage.cache.max_files` | int |
| `CODELAB_CONTEXT_INCREMENTAL` | `agents.context.lifecycle.incremental` | bool |
| `CODELAB_CONTEXT_MAX_TOKENS` | `agents.context.budget.max_context_tokens` | int |
| `CODELAB_CONTEXT_RESERVED_TOKENS` | `agents.context.budget.reserved_tokens` | int |
| `CODELAB_CONTEXT_FEDERATION` | `agents.context.multiagent.federation` | bool |

---

## Решение по владельцу канона и судьбе `fcm/`

### Канон
`doc/internals/context-manager/` (CM) — единственный source-of-truth по контекст-менеджеру. `ADR-002` — мета-документ над ним (фиксирует консолидацию и сквозные решения).

### Судьба `doc/internals/architecture/fcm/`
**Не удалять** — в FCM-доках детальные дизайны компонентов слоя C, нужные при реализации Phase 2. На **Phase 0**:
- архивировать `fcm/` → `doc/internals/archive/fcm/` с шапкой-редиректом на `ADR-002` и `context-manager/`;
- при реализации Phase 2 спеки компонентов слоя C (`FileContentCache`, `CodeSkeletonizer`, `TokenCounter`, `FileCacheDecorator`) мигрируют/линкуются в `context-manager/`.

> Перенос — действие **Phase 0 после слияния веток**, а не сейчас: `feature/context-manager` (где лежит `fcm/`) и `feature/agent` (где канон) ещё разошлись. ADR фиксирует решение; физический move выполняется в рамках консолидации.

### Владелец
- **Шепард ADR-002** ведёт консолидацию (поле «Авторы» заполняется при принятии ADR).
- `context-manager/` сопровождает команда-владелец ветки `feature/agent`.

### Слияние веток
`feature/context-manager` выравнивается по канону `feature/agent`; `ADR-002` переезжает вместе с консолидацией.

---

## Статус реализации

Оба дизайна — **design-only**. Из кода существует только legacy `src/codelab/server/agent/context_compactor.py` (двухфазный Prune→Summarize, покрыт тестами). Любая реализация единой архитектуры стартует от него как baseline.

---

## История

| Дата | Изменение |
|------|-----------|
| 2026-06-25 | Черновик ADR создан на основе сравнительного анализа FCM (v2.3) и CM (Phase 0–6) |
| 2026-06-25 | Добавлен раздел «Решение по жизненному циклу контекста»: принята инкрементальная модель (обоснование — длинные сессии) + гибридный мост Phase 0→2 |
| 2026-06-25 | Добавлен раздел «Единый roadmap» (Phase 0–6, ~13 недель) — закрыт открытый вопрос №1 |
| 2026-06-25 | Добавлен раздел «Решение по кэшированию» — закрыт открытый вопрос №2 |
| 2026-06-25 | Добавлен раздел «Решение по мультиагентному обмену» — закрыт открытый вопрос №3 |
| 2026-06-25 | Добавлен раздел «Схема конфиг-флагов» (TOML + env-overrides) — закрыт открытый вопрос №4 |
| 2026-06-25 | Добавлен раздел «Решение по владельцу канона и судьбе fcm/» — закрыт открытый вопрос №5; все 5 вопросов решены |
| 2026-06-25 | Статус изменён на «Принято» — все решения зафиксированы, документация доведена до состояния «готово к разработке» (фазы 0–6) |
