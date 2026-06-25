# Phase 1 — MVP-сбор (спецификация для разработки)

> **Статус:** Готово к разработке после Phase 0 — [ADR-002](../architecture/adr/ADR-002-context-manager-consolidation.md)
> **Длительность:** 3 недели
> **Цель:** реализовать слой A (`TaskAnalyzer` → `ContextGatherer` → `DependencyGraph(regex)` → `TokenBudgetManager`) через ACP `ToolRegistry`. Для типовой задачи система сама отбирает релевантные файлы, e2e работает на одной модели, бюджет токенов соблюдается, качество ≥80%.

Phase 1 наполняет замороженные в Phase 0 интерфейсы реализациями слоя A. Сигнатуры из
[INTERFACES.md](./INTERFACES.md) §2 и модели из [DATA_MODELS.md](./DATA_MODELS.md) §1–2 — **не меняются**.
Поведение payload — **гидрация**: `baseline` пересобирается каждый ход, инкрементальности ещё нет
(см. [CONSOLIDATED_ARCHITECTURE.md §5](./CONSOLIDATED_ARCHITECTURE.md) — «гибридный мост, Phase 1»).

---

## Задачи

### T1.1 — `TaskAnalyzer` (LLM-классификация задачи)
- `task_analyzer.py` — реализация `TaskAnalyzer.analyze(prompt, session) -> TaskProfile`.
- LLM-классификация: prompt → `TaskType` (`bug_fix`/`feature`/`refactor`/`architecture`), извлечение `search_terms`, `target_modules`, `investigation_depth` (1–3), `needs_tests`.
- Структурированный вывод парсится в `TaskProfile` (`frozen`); деградация при невалидном ответе LLM → дефолтный профиль (`FEATURE`, термины из эвристики по prompt, depth=1).
- **Acceptance:** на наборе размеченных prompt классификация попадает в правильный `TaskType` в ≥80% случаев; `analyze()` всегда возвращает валидный `TaskProfile` (даже при сбое LLM).

### T1.2 — `DependencyGraph` на regex
- `dependency_graph.py` — реализация ABC `DependencyGraph`: `add_file(path, imports)`, `get_dependencies(path, *, recursive=False)`, `get_dependents(path)`.
- Извлечение импортов regex'ом (Python `import`/`from … import`); `recursive=False` всегда в Phase 1 (рекурсия — Phase 5, флаг `recursive_dependencies`).
- Внутреннее хранилище — прямые и обратные рёбра; нормализация путей модулей в пути файлов в пределах проекта.
- **Acceptance:** unit-тесты: импорты разных форм извлекаются; `get_dependencies` возвращает прямые зависимости, `get_dependents` — обратные; при `recursive=True` поведение задокументировано как не-Phase-1 (no-op за пределами прямого уровня).

### T1.3 — `ContextGatherer` (пайплайн через ACP `ToolRegistry`)
- `gatherer.py` — реализация `ContextGatherer.gather(profile, session) -> list[ContextItem]`.
- Пайплайн строго через ACP `ToolRegistry` (без собственного I/O): `project_tree()` → `search()` по `profile.search_terms` → `read_file()` целевых кандидатов.
- По прочитанным файлам наполняется `DependencyGraph` (T1.2); отбор файлов — кандидаты поиска + их прямые зависимости/зависимые, отсечение по `profile.investigation_depth` и `BuildOptions.max_files`.
- Каждый файл → `ContextItem` (`type=FILE_CONTENT`, `id=path`, `priority` по умолчанию из [DATA_MODELS.md §3](./DATA_MODELS.md), `owner_scope=agent_scope`, `token_count` оценкой).
- **Acceptance:** для типовой задачи в тестовом репозитории gatherer возвращает релевантные файлы; все обращения к ФС идут через `ToolRegistry` (проверяется моком — собственного `open()`/`read()` нет).

### T1.4 — `TokenBudgetManager` (allocate + bound_content)
- `budget.py` — реализация ABC `TokenBudgetManager`: `allocate(total_tokens) -> BudgetAllocation`, `bound_content(content, max_tokens) -> str`.
- `allocate()` делит бюджет по долям из `ContextConfig` (`system_share`/`history_share`/`tool_output_share`/`response_buffer_share`) → `BudgetAllocation`.
- `bound_content()` усекает содержимое, сохраняя начало и конец (как зафиксировано в INTERFACES.md §2).
- Подсчёт токенов в Phase 1 — приближённый (точный `TiktokenCounter` — Phase 2); интерфейс не завязан на реализацию счётчика.
- **Acceptance:** сумма долей `BudgetAllocation` ≤ `total_tokens`; доли соответствуют конфигу; `bound_content` укладывается в `max_tokens` и сохраняет голову+хвост; unit-тесты на граничные значения.

### T1.5 — Интеграция в `ContextManager.build_context()` (гидрация)
- `manager.py` — реализация `build_context(session, prompt, *, agent_scope, system_prompt, options) -> PayloadEnvelope`, оркеструющая слой A: `TaskAnalyzer.analyze()` → `ContextGatherer.gather()` → бюджетирование через `TokenBudgetManager`.
- Сборка `PayloadEnvelope`: `baseline` = system_prompt + стабильный префикс (собранные `ContextItem` → `LLMMessage`), `tail` = текущий ход (user/assistant/tool); `baseline_fingerprint` вычисляется, `token_count` заполняется.
- **Поведение гидрации:** `baseline` пересобирается **каждый ход** (`incremental=false`); `baseline_fingerprint` может меняться — это допустимо в Phase 1.
- `BuildOptions` (если передан) перекрывает конфиг для вызова (`max_files`, `incremental`, `skeletonize`).
- Выбор реализации — по флагу `agents.context.enabled` (иначе legacy, как в Phase 0); сбор активен при `gather_enabled`.
- **Acceptance:** `build_context()` возвращает `PayloadEnvelope` (не «плоский» список); `to_messages()` = `baseline + tail`; при `enabled=true` payload содержит отобранные релевантные файлы.

### T1.6 — Соблюдение бюджета на пути формирования payload
- В `build_context()` суммарная оценка токенов сверяется с `allocate()`; превышение долей history/tool_output → `bound_content()` по соответствующим `ContextItem`, отсечение низкоприоритетных (priority по умолчанию из DATA_MODELS §3).
- Тяжёлое 3-фазное сжатие (`ensure_context_fits()`) в Phase 1 **не реализуется** (Prune/Skeletonize/Summarize — Phase 2/3); используется только бюджетное усечение слоя A.
- **Acceptance:** для большого набора файлов итоговый `PayloadEnvelope.token_count` не превышает `max_context_tokens - reserved_tokens`; элементы с `priority>=10` (`system_rules`) не усекаются.

### T1.7 — e2e-тест сбора на одной модели
- e2e: prompt типовой задачи → `build_context()` → `PayloadEnvelope` → `to_messages()` → LLM-вызов на одной модели; ACP `ToolRegistry` замокан/прогнан на тестовом репозитории.
- Метрика качества отбора: доля релевантных файлов, попавших в `baseline`, на размеченном наборе задач.
- **Acceptance:** e2e зелёный; система сама отбирает релевантные файлы без ручного указания; качество отбора ≥80%; бюджет соблюдён.

---

## Definition of Done для Phase 1

- [ ] `TaskAnalyzer` классифицирует задачу в `TaskProfile`; деградация без LLM работает.
- [ ] `DependencyGraph` (regex) извлекает импорты, отдаёт зависимости/зависимых.
- [ ] `ContextGatherer` проходит пайплайн `project_tree → search → read_file → graph → отбор` строго через ACP `ToolRegistry`.
- [ ] `TokenBudgetManager` аллоцирует по долям конфига и усекает `bound_content`.
- [ ] `build_context()` возвращает `PayloadEnvelope` (baseline+tail) с поведением гидрации.
- [ ] Бюджет токенов соблюдается (`token_count` ≤ `max - reserved`); priority-элементы защищены.
- [ ] e2e на одной модели зелёный; качество отбора ≥80%.
- [ ] Сигнатуры из INTERFACES.md §2 и модели DATA_MODELS.md §1–2 не изменены.

---

## Что Phase 1 НЕ делает (важно)

- Не реализует слой C — `TokenCounter`(tiktoken), `FileContentCache`/`SessionFileCacheRegistry`/`FileCacheDecorator`, `CodeSkeletonizer`(AST) — это Phase 2. Подсчёт токенов — приближённый.
- Не реализует инкрементальность — `ContextEpoch`/`ContextSnapshot`/`ContextReconciliation`: `baseline` пересобирается каждый ход (Phase 4).
- Не реализует полное 3-фазное сжатие `ensure_context_fits()` (Prune→Skeletonize→Summarize) — Phase 2/3; только бюджетное усечение слоя A.
- Не делает собственный I/O: весь `gather` идёт через ACP `ToolRegistry` (`project_tree`/`search`/`read_file`).
- Не делает рекурсивное разрешение зависимостей и tree-sitter (`recursive_dependencies`/`use_tree_sitter`) — Phase 5.
- Не реализует мультиагентный обмен `process_subagent_response()`/`ChildSessionManager` — Phase 6.

---

## Риски и митигации

| Риск | Митигация |
|------|-----------|
| LLM-классификация нестабильна → мусорный `TaskProfile` | Структурированный вывод + строгий парсинг + детерминированный дефолтный профиль при сбое (T1.1); метрика ≥80% как acceptance |
| Gatherer тайком делает собственный I/O в обход ACP | Code-review правило + тест с моком `ToolRegistry`: любой `open()`/`read()` в обход — фейл (T1.3) |
| regex-граф ложно срабатывает/пропускает импорты | Покрыть формы импортов unit-тестами; `recursive=False` ограничивает радиус ошибки до прямого уровня (T1.2) |
| Приближённый счётчик недооценивает токены → переполнение окна | Консервативная оценка с запасом; точный `TiktokenCounter` приходит в Phase 2 за тем же интерфейсом |
| Гидрация каждый ход дорога на длинных сессиях | Осознанный компромисс MVP: форма `baseline/tail` уже заложена (Phase 0) → инкрементальность включается в Phase 4 без переписывания ядра |
| Бюджетное усечение режет важный контент | Защита `priority>=10` (`system_rules`) от усечения; `bound_content` сохраняет голову+хвост (T1.6) |
