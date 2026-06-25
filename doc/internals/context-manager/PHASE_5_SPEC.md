# Phase 5 — Полный DependencyGraph (спецификация для разработки)

> **Статус:** Готово к разработке после предыдущих фаз — [ADR-002](../architecture/adr/ADR-002-context-manager-consolidation.md)
> **Длительность:** 2 недели
> **Цель:** довести `DependencyGraph` до рекурсивного разрешения транзитивных зависимостей (`get_dependencies(recursive=True)`) и опционально заменить regex-парсинг импортов на tree-sitter — всё за флагами, regex остаётся дефолтом.

Phase 5 опирается на интерфейс `DependencyGraph` ([INTERFACES.md §2](./INTERFACES.md)),
замороженный в Phase 0, и на сбор контекста (`ContextGatherer`) из Phase 1.
Сигнатуры не меняются — добавляется только реализация рекурсии и альтернативный парсер.
См. [CONSOLIDATED_ARCHITECTURE.md §10 (Phase 5)](./CONSOLIDATED_ARCHITECTURE.md) и [§3 (Слой A)](./CONSOLIDATED_ARCHITECTURE.md).

---

## Задачи

### T5.1 — Рекурсивное разрешение зависимостей
- Реализовать `DependencyGraph.get_dependencies(path, *, recursive=True)`: обход графа в глубину/ширину с возвратом транзитивного замыкания зависимостей.
- Защита от циклов (visited-set) и от взрывного роста: ограничение глубины из `TaskProfile.investigation_depth` (1–3).
- За флагом `agents.context.gather.recursive_dependencies` (`ContextConfig.recursive_dependencies`, default `False`): при `False` поведение Phase 1 (только прямые зависимости).
- **Acceptance:** `get_dependencies(p, recursive=True)` возвращает транзитивное замыкание без дублей и без зацикливания на циклических импортах; при `recursive_dependencies=False` результат идентичен Phase 1.

### T5.2 — Интеграция рекурсии в ContextGatherer
- `ContextGatherer.gather()` использует рекурсивный обход при включённом флаге для отбора файлов; глубина ограничена `investigation_depth`.
- Отбор остаётся в рамках бюджета `TokenBudgetManager` — транзитивные файлы добавляются по приоритету, пока не исчерпан `history_tokens`.
- **Acceptance:** на большом проекте точность отбора релевантных файлов растёт относительно прямых зависимостей; отбор не выходит за токен-бюджет; порядок добавления детерминирован.

### T5.3 — Tree-sitter парсер импортов (опционально)
- Альтернативная реализация извлечения импортов через tree-sitter для языков с грамматикой; питает `DependencyGraph.add_file(path, imports)`.
- За флагом `agents.context.gather.use_tree_sitter` (`ContextConfig.use_tree_sitter`, default `False`); fallback на regex при отсутствии грамматики или ошибке парсинга.
- **Acceptance:** при `use_tree_sitter=True` импорты извлекаются точнее regex на поддерживаемых языках; при `False` или непокрытом языке используется regex; tree-sitter не является обязательной зависимостью рантайма (мягкий импорт).

### T5.4 — Конфиг и наблюдаемость
- Подключить флаги к загрузчику `[agents.context.gather.*]` и env-overrides `CODELAB_CONTEXT_*` (как в Phase 0).
- Метрики/логи: число разрешённых транзитивных узлов, глубина обхода, парсер (regex/tree-sitter), доля fallback.
- **Acceptance:** оба флага читаются из TOML и перекрываются env; логируется выбранный парсер и глубина; флаги по умолчанию выключены/regex.

---

## Definition of Done для Phase 5

- [ ] `get_dependencies(recursive=True)` возвращает транзитивное замыкание, устойчив к циклам, ограничен по глубине.
- [ ] `recursive_dependencies` по умолчанию `False`; при `False` — поведение Phase 1 бит-в-бит.
- [ ] `use_tree_sitter` по умолчанию `False`; regex остаётся дефолтом с автоматическим fallback.
- [ ] Точность отбора файлов на большом проекте измерена и улучшена при включённой рекурсии.
- [ ] Флаги читаются из TOML/env; добавлены метрики обхода и парсера.
- [ ] Сигнатуры `DependencyGraph` не изменены (заморозка Phase 0 соблюдена).

---

## Что Phase 5 НЕ делает (важно)

- Не меняет сигнатуры интерфейсов из [INTERFACES.md](./INTERFACES.md) — только добавляет реализации.
- Не делает tree-sitter дефолтом и не вводит его как жёсткую зависимость рантайма.
- Не трогает слой жизненного цикла (Epoch/Snapshot/Reconciliation — Phase 4) и мультиагент (Phase 6).
- Не меняет поведение при `recursive_dependencies=False` и `use_tree_sitter=False`.

---

## Риски и митигации

| Риск | Митигация |
|------|-----------|
| Рекурсивный обход взрывается по числу файлов/токенов на больших проектах | Ограничение глубины через `investigation_depth` (1–3) + отбор в рамках `TokenBudgetManager`; ранний выход при исчерпании бюджета |
| Циклические импорты приводят к зацикливанию | Обязательный visited-set; покрытие unit-тестом на циклический граф |
| tree-sitter как зависимость утяжеляет рантайм / ломает сборку | Мягкий (опциональный) импорт за флагом; regex — дефолт; автоматический fallback при отсутствии грамматики |
| Расхождение результатов regex и tree-sitter дестабилизирует отбор | Парсер логируется; на baseline-стабильность не влияет (отбор файлов, не сжатие); сравнительный тест на наборе фикстур |
| Включение `recursive_dependencies` ухудшает кэш-хит из-за роста baseline | Флаг выключен по умолчанию; влияние на baseline_fingerprint фиксируется метрикой кэш-хита |
