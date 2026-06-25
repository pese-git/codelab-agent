# Спецификация возможности Context Gather

## ADDED Requirements

### Requirement: Анализ задачи классифицирует намерение пользователя
Система ДОЛЖНА анализировать промпт пользователя для классификации типа задачи и извлечения стратегии поиска.

#### Scenario: Классификация задачи исправления бага
- **WHEN** пользователь отправляет промпт "Fix crash when email is empty in auth"
- **THEN** система классифицирует задачу как `BUG_FIX` с `investigation_depth=2` и `needs_tests=True`

#### Scenario: Классификация задачи новой функциональности
- **WHEN** пользователь отправляет промпт "Add user authentication with OAuth"
- **THEN** система классифицирует задачу как `FEATURE` с `investigation_depth=3` и `needs_tests=True`

#### Scenario: Fallback при сбое LLM-классификации
- **WHEN** LLM-классификация завершается сбоем (ошибка сети, таймаут, невалидный ответ)
- **THEN** система возвращает дефолтный `TaskProfile` с `task_type=FEATURE`, `investigation_depth=1` и эвристическими поисковыми терминами, извлечёнными из текста промпта

### Requirement: Context Gatherer собирает релевантные файлы
Система ДОЛЖНА собирать релевантные файлы через ACP ToolRegistry используя конвейер: `project_tree()` → `search()` → `read_file()` → граф зависимостей → отбор.

#### Scenario: Успешный сбор файлов
- **WHEN** TaskProfile имеет `search_terms=["email", "auth"]` и `target_modules=["auth"]`
- **THEN** система вызывает `project_tree()`, `search(["email", "auth"])`, читает файлы-кандидаты и возвращает `list[ContextItem]` с `type=FILE_CONTENT`

#### Scenario: Сбой ACP RPC для project_tree
- **WHEN** RPC `project_tree()` завершается сбоем
- **THEN** система продолжает с пустым деревом, полагается на `search()` и `target_modules` из TaskProfile, логирует warning `gather_project_tree_failed`

#### Scenario: Сбой ACP RPC для search
- **WHEN** RPC `search()` завершается сбоем
- **THEN** система пропускает шаг поиска, продолжает с деревом + зависимостями из DependencyGraph, логирует warning `gather_search_failed`

#### Scenario: Сбой ACP RPC для read_file
- **WHEN** RPC `read_file()` завершается сбоем для конкретного файла
- **THEN** система пропускает этот файл, продолжает с остальными файлами, логирует warning `gather_read_file_failed` с полем `path`

#### Scenario: Все RPC завершаются сбоем
- **WHEN** все ACP RPC завершаются сбоем одновременно
- **THEN** система возвращает пустой или частичный `list[ContextItem]`, логирует error `gather_all_sources_failed`, payload строится только из `session.history` + системного промпта

### Requirement: Бинарные файлы фильтруются
Система ДОЛЖНА обнаруживать и исключать бинарные файлы из сбора контекста.

#### Scenario: Обнаружение бинарного файла по расширению
- **WHEN** файл имеет бинарное расширение (`.png`, `.zip`, `.pdf`, `.exe`)
- **THEN** система пропускает файл без вызова `read_file()`, логирует info `gather_file_skipped` с `reason=binary`

#### Scenario: Обнаружение бинарного файла по содержимому
- **WHEN** `read_file()` возвращает содержимое, которое не декодируется UTF-8
- **THEN** система перехватывает `UnicodeDecodeError`, исключает файл из результата, логирует info `gather_file_skipped` с `reason=binary`

### Requirement: Пустые файлы фильтруются
Система ДОЛЖНА исключать пустые файлы или файлы только с пробелами из сбора контекста.

#### Scenario: Фильтрация пустых файлов
- **WHEN** содержимое файла `""` или содержит только пробелы
- **THEN** система не добавляет `ContextItem` для этого файла, продолжает с остальными файлами

### Requirement: Граф зависимостей разрешает импорты
Система ДОЛЖНА строить и запрашивать граф зависимостей для разрешения импортов файлов.

#### Scenario: Разрешение зависимостей на основе regex (Phase 1)
- **WHEN** файл `auth/login.py` импортирует `auth/validators.py`
- **THEN** `DependencyGraph.get_dependencies("auth/login.py")` возвращает `["auth/validators.py"]`

#### Scenario: Обработка циклических импортов
- **WHEN** файлы имеют циклические импорты (`a.py` → `b.py` → `a.py`)
- **THEN** `get_dependencies(recursive=True)` использует множество посещённых для предотвращения бесконечной рекурсии, возвращает каждый файл ровно один раз, порядок результата детерминирован

#### Scenario: Рекурсивное разрешение зависимостей (Phase 5)
- **WHEN** `recursive=True` и файл имеет транзитивные зависимости
- **THEN** система разрешает все транзитивные зависимости, возвращает полное дерево зависимостей

### Requirement: Распределение токенов бюджета
Система ДОЛЖНА распределять бюджет токенов между system, history, tool output и response buffer.

#### Scenario: Распределение бюджета с долями по умолчанию
- **WHEN** `max_context_tokens=128000` и доли по умолчанию (system=0.20, history=0.50, tool_output=0.20, response_buffer=0.10)
- **THEN** `allocate()` возвращает `BudgetAllocation` с `system_tokens=25600`, `history_tokens=64000`, `tool_output_tokens=25600`, `response_buffer_tokens=12800`

#### Scenario: Ограничение содержимого
- **WHEN** содержимое файла превышает выделенные `max_tokens`
- **THEN** `bound_content(content, max_tokens)` обрезает содержимое, сохраняя начало и конец, логирует info `content_bounded` с `original_tokens` и `bound_tokens`

### Requirement: Context Registry управляет источниками
Система ДОЛЖНА управлять источниками контекста через паттерн registry с рендерингом baseline и updates.

#### Scenario: Регистрация источника
- **WHEN** `ContextSource` регистрируется через `register(source)`
- **THEN** источник добавляется в registry с уникальным `source_id`

#### Scenario: Рендеринг baseline
- **WHEN** вызывается `render_baseline()`
- **THEN** система рендерит все зарегистрированные источники, возвращает объединённую строку

#### Scenario: Обнаружение изменений через fingerprint
- **WHEN** вызывается `detect_changes()`
- **THEN** система сравнивает текущие fingerprints с предыдущим snapshot, возвращает список изменённых `source_id`

### Requirement: Gatherer не имеет прямого I/O
Система ДОЛЖНА гарантировать, что `ContextGatherer` выполняет весь I/O через ACP `ToolRegistry`, а не напрямую.

#### Scenario: I/O через ToolRegistry
- **WHEN** `ContextGatherer.gather()` нужно читать файлы
- **THEN** система вызывает методы `ToolRegistry` (`project_tree`, `search`, `read_file`), не выполняет прямой доступ к файловой системе
