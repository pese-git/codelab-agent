# Спецификация возможности Context Observability

## ADDED Requirements

### Requirement: Slash-команда /context предоставляет полную наблюдаемость
Система MUST предоставлять интерфейс для наблюдения за состоянием Context Manager через slash-команду `/context` с подкомандами для различных аспектов.

#### Scenario: /context config показывает полную конфигурацию
- **WHEN** пользователь выполняет `/context config`
- **THEN** система выводит все поля `ContextConfig` с форматированием, включая budget allocation в токенах (рассчитанные из процентов от `max_context_tokens`), runtime overrides из `session.config_values`
- **AND** вывод включает секции: Общие (enabled, gather_enabled, incremental, federation), Анализ (analyzer_model, recursive_dependencies), Оптимизация (use_tree_sitter, use_tiktoken, file_cache, skeletonize, cache_max_files), Бюджет (max_context_tokens, reserved_tokens, system/history/tool_output/response_buffer в процентах и токенах), Runtime overrides

#### Scenario: /context last показывает детали последней сборки
- **WHEN** пользователь выполняет `/context last`
- **THEN** система выводит stage timings (extract, analyze, gather, baseline, tail, fingerprint), task_type, fingerprint, candidate vs selected files, baseline/tail tokens из последнего элемента `context_build_details`
- **AND** если `context_build_details` пуст (debug mode выключен или сборок не было) — выводит сообщение "Детали недоступны. Включите debug mode: `--observability-debug`"

#### Scenario: /context files показывает список собранных файлов
- **WHEN** пользователь выполняет `/context files`
- **THEN** система выводит список файлов из последней сборки с токенами на файл (из `context_build_details["file_paths"]`), общее количество токенов и файлов
- **AND** если `file_paths` отсутствует или пуст — выводит сообщение "Список файлов недоступен"

#### Scenario: /context graph показывает статистику графа зависимостей
- **WHEN** пользователь выполняет `/context graph`
- **THEN** система выводит files_in_graph, total_dependencies, total_dependents, project_files_cached из `DependencyGraph.get_stats()`
- **AND** если граф не инициализирован (сборок не было) — выводит сообщение "Граф зависимостей не инициализирован"

#### Scenario: /context profile показывает последний профиль задачи
- **WHEN** пользователь выполняет `/context profile`
- **THEN** система выводит task_type, search_terms, target_modules, investigation_depth, needs_tests из сохранённого `TaskProfile`
- **AND** если профиль не сохранён (сборок не было) — выводит сообщение "Профиль задачи недоступен"

#### Scenario: Расширенная сводка /context показывает метрики LLM и агента
- **WHEN** пользователь выполняет `/context` (без аргументов)
- **THEN** система выводит расширенную сводку с секциями: Контекст (существующие метрики: сборки, файлы, baseline/tail токены), LLM (calls, input_tokens, output_tokens), Агент (responses, errors)
- **AND** если метрики отсутствуют (сборок/вызовов не было) — выводит "нет данных" для соответствующей секции

#### Scenario: /context неизвестная подкоманда показывает подсказку
- **WHEN** пользователь выполняет `/context unknown`
- **THEN** система выводит ошибку и список всех доступных подкоманд, включая новые: config, last, files, graph, profile

### Requirement: MetricsTracker сохраняет расширенные данные сборки
Система MUST сохранять расширенные данные сборки контекста в debug-режиме для диагностики через slash-команду.

#### Scenario: record_context_build() принимает расширенные параметры
- **WHEN** `DefaultContextManager.build_context()` завершает сборку
- **THEN** система вызывает `record_context_build()` с опциональными параметрами: `task_type: str = ""`, `file_paths: list[str] | None = None`, `candidate_count: int = 0`, `stage_timings: dict[str, float] | None = None`, `graph_stats: dict[str, int] | None = None`
- **AND** все новые параметры опциональны с дефолтными значениями для обратной совместимости

#### Scenario: context_build_details содержит все расширенные данные
- **WHEN** `metrics_tracker.debug == True` и вызывается `record_context_build()`
- **THEN** `context_build_details` содержит dict с полями: `build_duration_ms`, `gathered_files`, `baseline_tokens`, `tail_tokens`, `task_type`, `file_paths`, `candidate_count`, `stage_timings`, `graph_stats`, `timestamp`
- **AND** если параметр не передан — соответствующее поле содержит дефолтное значение (пустая строка, пустой список, 0, пустой dict)

### Requirement: DependencyGraph экспортирует статистику
Система MUST предоставлять метод `get_stats()` для экспорта статистики графа зависимостей.

#### Scenario: get_stats() возвращает агрегированную статистику
- **WHEN** вызывается `DependencyGraph.get_stats()`
- **THEN** система возвращает dict с полями: `files_in_graph` (количество файлов в `_dependencies`), `total_dependencies` (сумма длин всех множеств в `_dependencies`), `total_dependents` (сумма длин всех множеств в `_dependents`), `project_files_cached` (количество файлов в `_project_files` или 0 если None)

#### Scenario: get_stats() работает для пустого графа
- **WHEN** граф пуст (нет добавленных файлов)
- **THEN** `get_stats()` возвращает `{"files_in_graph": 0, "total_dependencies": 0, "total_dependents": 0, "project_files_cached": 0}`

### Requirement: DefaultContextManager собирает расширенные данные
Система MUST хронометрировать каждую стадию сборки и собирать расширенные данные для передачи в MetricsTracker.

#### Scenario: build_context() хронометрирует стадии
- **WHEN** `build_context()` выполняется
- **THEN** система измеряет длительность каждой стадии в миллисекундах: `extract_ms` (извлечение текста промпта), `analyze_ms` (TaskAnalyzer.analyze), `gather_ms` (ContextGatherer.gather), `baseline_ms` (формирование baseline), `tail_ms` (формирование tail из истории), `fingerprint_ms` (вычисление fingerprint)
- **AND** передаёт `stage_timings` dict в `record_context_build()`

#### Scenario: build_context() собирает file_paths и candidate_count
- **WHEN** `ContextGatherer.gather()` завершается
- **THEN** система собирает `file_paths` из `items` (список `item.id` для каждого `ContextItem`), `candidate_count` из gatherer (количество уникальных кандидатов до отбора по бюджету)
- **AND** передаёт эти данные в `record_context_build()`

#### Scenario: build_context() собирает graph_stats
- **WHЕН** сборка завершается
- **THEN** система вызывает `dependency_graph.get_stats()` и передаёт результат в `record_context_build(graph_stats=...)`

#### Scenario: build_context() передаёт task_type
- **WHEN** `TaskAnalyzer.analyze()` завершается успешно
- **THEN** система извлекает `profile.task_type` и передаёт в `record_context_build(task_type=...)`

### Requirement: TaskProfile сохраняется для диагностики
Система MUST сохранять последний `TaskProfile` для каждой сессии для отображения через `/context profile`.

#### Scenario: TaskProfile сохраняется после анализа
- **WHEN** `TaskAnalyzer.analyze()` завершается успешно
- **THEN** система сохраняет `TaskProfile` в `SessionMetrics.last_task_profile` (новое поле типа `dict[str, Any] | None`)
- **AND** профиль сериализуется в dict: `{"task_type": str, "search_terms": list[str], "target_modules": list[str], "investigation_depth": int, "needs_tests": bool}`

#### Scenario: /context profile читает сохранённый профиль
- **WHEN** пользователь выполняет `/context profile`
- **THEN** система читает `metrics.last_task_profile` для текущей сессии и выводит его поля в формате Markdown
- **AND** если `last_task_profile is None` — выводит сообщение "Профиль задачи недоступен (сборок не было)"

### Requirement: Обратная совместимость расширенных метрик
Система MUST гарантировать обратную совместимость при расширении `record_context_build()`.

#### Scenario: Существующие вызовы record_context_build() не ломаются
- **WHEN** существующий код вызывает `record_context_build()` без новых параметров
- **THEN** вызов завершается успешно, новые поля в `context_build_details` содержат дефолтные значения
- **AND** агрегированные метрики (`context_build_count`, `context_build_total_ms`, etc.) обновляются как прежде

#### Scenario: Новые подкоманды /context не ломают существующие
- **WHEN** пользователь выполняет существующие подкоманды `/context`, `/context spans`, `/context on`, `/context off`
- **THEN** поведение остаётся идентичным текущей реализации
- **AND** вывод расширенной сводки `/context` включает новые секции (LLM, Агент), но существующие поля сохраняются

## MODIFIED Requirements

### Requirement: SessionMetrics содержит расширенные поля
Система MUST расширить `SessionMetrics` новыми полями для хранения расширенных данных.

#### Scenario: SessionMetrics имеет last_task_profile
- **WHEN** создаётся новый `SessionMetrics`
- **THEN** поле `last_task_profile: dict[str, Any] | None` инициализируется значением `None`
- **AND** поле доступно для чтения через `metrics.last_task_profile`

## Implementation Notes

### Файлы для изменения

1. `src/codelab/server/observability/metrics_tracker.py` — расширение `record_context_build()`, добавление `last_task_profile` в `SessionMetrics`
2. `src/codelab/server/agent/context/dependency_graph.py` — добавление `get_stats()`
3. `src/codelab/server/agent/context/manager.py` — хронометраж стадий, сбор расширенных данных
4. `src/codelab/server/protocol/handlers/slash_commands/builtin/context.py` — новые подкоманды, расширенная сводка
5. `tests/server/protocol/handlers/slash_commands/test_context.py` — тесты новых подкоманд
6. `tests/server/agent/context/test_dependency_graph.py` — тест `get_stats()`
7. `tests/server/agent/context/test_observability.py` — тест расширенных метрик

### Обратная совместимость

- `record_context_build()` — новые параметры опциональные с дефолтами, существующие вызовы не ломаются
- `get_stats()` — новый метод, ничего не ломает
- Новые подкоманды `/context` — additive, существующие не меняются
- Расширенная сводка — добавляет секции, существующие поля сохраняются

### Зависимости от других возможностей

- `context-gather` — `TaskProfile`, `ContextItem`, `ContextGatherer` (для сбора file_paths, candidate_count)
- `agent-context-models` — `ContextConfig`, `TaskProfile` (для `/context config`, `/context profile`)
- `session-state` — `SessionState.config_values` (для runtime overrides в `/context config`)
