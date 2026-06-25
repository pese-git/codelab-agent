# Реализация Context Manager — Задачи

## Фаза 0: Основа (1 неделя)

- [x] 0.1 Создать структуру пакета `src/codelab/server/agent/context/` с `__init__.py`
- [x] 0.2 Реализовать модели данных в `models.py`: `PayloadEnvelope`, `TaskProfile`, `BudgetAllocation`, `BuildOptions`, `ContextConfig`, `ContextItem`, `ContextEpoch`, `ContextSnapshot`, `ReconcileResult`, `SubagentResult`, перечисления (`TaskType`, `ContextType`, `ChangeState`)
- [x] 0.3 Написать unit тесты для `PayloadEnvelope.to_messages()` и `ContextSnapshot.diff()`
- [x] 0.4 Определить ABC интерфейсы в `interfaces.py`: `ContextManager`, `TaskAnalyzer`, `ContextGatherer`, `DependencyGraph`, `TokenBudgetManager`, `ContextSource`, `ContextRegistry`, `ConversationSummarizer`, `ContextReconciler`, `TokenCounter`, `CodeSkeletonizer`, `FileContentCache`, `ContextCompactor`, `ChildSessionManager`
- [x] 0.5 Проверить, что все ABC имеют декораторы `@abstractmethod`; mypy/pyright проходит
- [x] 0.6 Ввести `PayloadEnvelope` в тип возврата `ExecutionEngine.build_context()` с адаптером `to_messages()` на границе `LLMAdapter`
- [x] 0.7 Реализовать загрузчик feature flags: TOML `[agents.context.*]` → `ContextConfig` с переопределениями env `CODELAB_CONTEXT_*`
- [x] 0.8 Объявить устаревшим `agents.context.enable_fcm` → алиас на `agents.context.enabled` с предупреждением
- [x] 0.9 Обернуть legacy `context_compactor.py` в реализацию `ContextCompactor(ABC)` без изменения логики
- [x] 0.10 Обновить `ExecutionEngine` для выбора реализации по флагу `agents.context.enabled`
- [x] 0.11 Проверить, что `enabled=false` (по умолчанию) сохраняет legacy поведение; все существующие тесты `test_context_compactor.py` проходят
- [x] 0.12 Архивировать `doc/internals/architecture/fcm/` → `doc/internals/archive/fcm/` с заголовком перенаправления на ADR-002
- [x] 0.13 Обновить перекрёстные ссылки в `doc/internals/` для указания на новый канон `doc/internals/context-manager/`
- [x] 0.14 Написать интеграционный тест: `PayloadEnvelope` проходит через `ExecutionEngine` → границу `LLMAdapter`

## Фаза 1: MVP сбор (3 недели)

- [ ] 1.1 Реализовать `TaskAnalyzer.analyze()` с классификацией на основе LLM (BUG_FIX/FEATURE/REFACTOR/ARCHITECTURE)
- [ ] 1.2 Реализовать fallback `TaskProfile` по умолчанию при сбое классификации LLM
- [ ] 1.3 Написать unit тесты для `TaskAnalyzer` с замоканым LLM провайдером
- [ ] 1.4 Реализовать конвейер `ContextGatherer.gather()`: `project_tree()` → `search()` → `read_file()` → граф зависимостей → отбор
- [ ] 1.5 Обеспечить, чтобы `ContextGatherer` выполнял весь I/O через ACP `ToolRegistry`, без прямого доступа к файлам
- [ ] 1.6 Реализовать обнаружение бинарных файлов (по расширению и ошибке декодирования UTF-8)
- [ ] 1.7 Реализовать фильтрацию пустых файлов/файлов только с пробелами
- [ ] 1.8 Написать unit тесты для `ContextGatherer` с замоканым `ToolRegistry`
- [ ] 1.9 Реализовать `DependencyGraph` с парсингом импортов на основе regex (Фаза 1)
- [ ] 1.10 Реализовать методы `get_dependencies(recursive=False)` и `get_dependents()`
- [ ] 1.11 Реализовать защиту от циклических импортов с множеством посещённых
- [ ] 1.12 Написать unit тесты для `DependencyGraph`, включая циклические импорты
- [ ] 1.13 Реализовать `TokenBudgetManager.allocate()` с настраиваемыми долями (system/history/tool_output/response_buffer)
- [ ] 1.14 Реализовать `TokenBudgetManager.bound_content()` с сохранением начала и конца
- [ ] 1.15 Написать unit тесты для `TokenBudgetManager`
- [ ] 1.16 Реализовать `ContextRegistry` с `register()`, `render_baseline()`, `render_updates()`, `detect_changes()`
- [ ] 1.17 Реализовать ABC `ContextSource` с `source_id`, `render()`, `fingerprint()` (на основе Codec)
- [ ] 1.18 Написать unit тесты для `ContextRegistry` и `ContextSource`
- [ ] 1.19 Интегрировать Слой A с `ExecutionEngine.build_context()`: `TaskAnalyzer` → `ContextGatherer` → `DependencyGraph` → `TokenBudgetManager`
- [ ] 1.20 Написать интеграционный тест: `build_context()` собирает релевантные файлы для примера задачи
- [ ] 1.21 Написать e2e тест: `SingleStrategy` → `ExecutionEngine` → `ContextManager` → точность сбора файлов ≥80%
- [ ] 1.22 Добавить метрики: `context_gathered_files`, `context_build_duration_ms`, `context_baseline_tokens`, `context_tail_tokens`
- [ ] 1.23 Добавить span трейсинга: `context.build` с атрибутами (`agent_scope`, `task_type`, `gathered_files`, `baseline_tokens`, `tail_tokens`)
- [ ] 1.24 Добавить span трейсинга: `context.gather` с атрибутами (`task_type`, `search_terms`, `candidate_files`, `selected_files`)
- [ ] 1.25 Проверить, что feature flag `agents.context.gather.enabled=false` отключает автоматический сбор

## Фаза 2: Слой хранения (2 недели)

- [ ] 2.1 Реализовать ABC `TokenCounter` с методами `count()` и `count_messages()`
- [ ] 2.2 Реализовать `TiktokenCounter` с использованием библиотеки tiktoken
- [ ] 2.3 Реализовать fallback `ApproximateTokenCounter` (`len(text) // 4`)
- [ ] 2.4 Реализовать фабрику: попробовать импорт tiktoken, fallback на approximate с предупреждающим логом
- [ ] 2.5 Написать unit тесты для точности `TokenCounter` и fallback
- [ ] 2.6 Реализовать ABC `FileContentCache` с методами `get()`, `set()`, `invalidate()`
- [ ] 2.7 Реализовать `InMemoryFileCache` с LRU eviction при `cache_max_files`
- [ ] 2.8 Обеспечить, чтобы `invalidate()` публиковал сигнал изменения в единый источник истины
- [ ] 2.9 Написать unit тесты для `FileContentCache`, включая LRU eviction и сигнал инвалидации
- [ ] 2.10 Реализовать `SessionFileCacheRegistry` для жизненного цикла кэша каждой сессии
- [ ] 2.11 Обеспечить, чтобы registry освобождал память кэша при закрытии сессии
- [ ] 2.12 Написать unit тесты для жизненного цикла `SessionFileCacheRegistry`
- [ ] 2.13 Реализовать `FileCacheDecorator`, оборачивающий `ToolExecutor`
- [ ] 2.14 Перехватывать успешный `fs/read` → вызывать `FileContentCache.set(path, content)`
- [ ] 2.15 Перехватывать успешный `fs/write` → вызывать `FileContentCache.invalidate(path)` + публиковать сигнал
- [ ] 2.16 Обеспечить, чтобы ошибки decorator логировались, но не распространялись (выполнение инструмента успешно)
- [ ] 2.17 Написать unit тесты для `FileCacheDecorator` с замоканым `ToolExecutor`
- [ ] 2.18 Реализовать ABC `CodeSkeletonizer` с методами `can_handle()` и `skeletonize()`
- [ ] 2.19 Реализовать `PythonASTSkeletonizer` с использованием модуля Python `ast`
- [ ] 2.20 Обеспечить детерминированность скелетирования: стабильный порядок AST, отсортированные импорты, нормализованные пробелы
- [ ] 2.21 Реализовать fallback: вернуть оригинальный код при `SyntaxError` или неподдерживаемом языке
- [ ] 2.22 Реализовать проверку: если количество токенов skeleton >= оригинала, использовать оригинал
- [ ] 2.23 Написать golden тесты: 100 запусков на одном входе → байт-идентичный вывод
- [ ] 2.24 Написать unit тесты для `CodeSkeletonizer`, включая детерминизм и fallback
- [ ] 2.25 Реализовать dataclass `ContextItem` с `id`, `type`, `content`, `priority`, `owner_scope`, `token_count`, `last_accessed`
- [ ] 2.26 Добавить метрики: `context_file_cache_hits`, `context_file_cache_misses`, `context_file_cache_evictions`, `context_file_cache_size_bytes`, `context_token_count_duration_ms`, `context_skeleton_savings_ratio`
- [ ] 2.27 Проверить, что feature flag `agents.context.storage.enabled=false` отключает кэширование и скелетирование

## Фаза 3: Источники + сжатие (1 неделя)

- [ ] 3.1 Реализовать `SkillContextSource` для каталога навыков в системном промпте
- [ ] 3.2 Зарегистрировать `SkillContextSource` в `ContextRegistry`
- [ ] 3.3 Написать unit тесты для рендеринга `SkillContextSource` и обнаружения изменений
- [ ] 3.4 Реализовать 3-фазный `ContextCompactor`: `compact_if_needed()` с Prune → Skeletonize → Summarize
- [ ] 3.5 Реализовать фазу Prune: FIFO удаление старых выводов инструментов, сохранение первых 2 и последних N сообщений
- [ ] 3.6 Обеспечить, чтобы Prune удалял пары `tool_call` + `tool_result` вместе (без сирот)
- [ ] 3.7 Реализовать фазу Skeletonize: применить `CodeSkeletonizer` к большим файлам только для чтения
- [ ] 3.8 Реализовать фазу Summarize: вызвать `ConversationSummarizer.summarize()`, если Prune + Skeletonize недостаточно
- [ ] 3.9 Реализовать graceful degradation: если LLM недоступен, пропустить Summarize, продолжить с Prune + Skeletonize
- [ ] 3.10 Обеспечить, чтобы сигнатура `compact_if_needed()` соответствовала legacy для бесшовной миграции
- [ ] 3.11 Написать unit тесты для `ContextCompactor`, включая все три фазы и деградацию
- [ ] 3.12 Реализовать `ConversationSummarizer.summarize()` с LLM провайдером
- [ ] 3.13 Реализовать fallback: вернуть усечённый сырой результат при сбое суммаризации
- [ ] 3.14 Написать unit тесты для `ConversationSummarizer` с замоканым LLM провайдером
- [ ] 3.15 Реализовать метод `ensure_context_fits()` в `ContextManager`
- [ ] 3.16 Реализовать жёсткое усечение через `TokenBudgetManager.bound_content()`, если payload всё ещё превышает бюджет после 3 фаз
- [ ] 3.17 Обеспечить, чтобы элементы с `priority >= 10` не вытеснялись, если нет критического переполнения
- [ ] 3.18 Реализовать санитизацию осиротевших сообщений: удалить `tool_result` без `tool_call`, добавить placeholder для `tool_call` без `tool_result`
- [ ] 3.19 Написать unit тесты для `ensure_context_fits()`, включая жёсткое усечение и санитизацию
- [ ] 3.20 Добавить метрики: `context_compaction_ratio`, `context_compaction_total`, `context_compaction_degraded_total`
- [ ] 3.21 Добавить span трейсинга: `context.compact` с атрибутами (`phase`, `ratio`, `tokens_before`, `tokens_after`, `degraded`)

## Фаза 4: Инкрементальный жизненный цикл (2 недели)

- [ ] 4.1 Реализовать dataclass `ContextEpoch` с `epoch_id`, `baseline`, `baseline_fingerprint`, `mid_conversation_messages`
- [ ] 4.2 Реализовать `ContextEpoch.get_full_context()`, возвращающий `[*baseline, *mid_conversation_messages]`
- [ ] 4.3 Реализовать dataclass `ContextSnapshot` с `fingerprints: dict[str, str]`
- [ ] 4.4 Реализовать `ContextSnapshot.diff()`, сравнивающий fingerprints и возвращающий список изменённых `source_id`
- [ ] 4.5 Реализовать `ContextReconciler.snapshot()`, собирающий fingerprints всех источников
- [ ] 4.6 Реализовать `ContextReconciler.reconcile()`, возвращающий `ReconcileResult` с `state`, `updated_sources`, `new_tail_messages`, `epoch_broken`
- [ ] 4.7 Реализовать состояние `UNCHANGED`: ни один источник не изменился, baseline стабилен
- [ ] 4.8 Реализовать состояние `UPDATED`: источники изменились на безопасной границе, baseline перестроен (`epoch_broken=True`)
- [ ] 4.9 Реализовать состояние `DEFERRED`: изменение обнаружено в середине хода, применяется на следующей границе
- [ ] 4.10 Реализовать консервативный fallback: неопределённое изменение → `epoch_broken=True`
- [ ] 4.11 Написать unit тесты для `ContextReconciler`, включая все состояния и консервативный fallback
- [ ] 4.12 Интегрировать единый сигнал инвалидации: `FileCacheDecorator.invalidate()` публикует в единый источник
- [ ] 4.13 Обеспечить, чтобы `ContextSnapshot.diff()` обнаруживал изменения независимо от сигнала кэша (двойная защита)
- [ ] 4.14 Написать интеграционный тест: `fs/write` → `invalidate()` → `reconcile()` обнаруживает изменение
- [ ] 4.15 Написать интеграционный тест: потерянный сигнал инвалидации обнаруживается сравнением snapshot
- [ ] 4.16 Реализовать вычисление `baseline_fingerprint` по канонизированному содержимому baseline
- [ ] 4.17 Обеспечить, чтобы идентичный baseline производил идентичный fingerprint (детерминированный хэш)
- [ ] 4.18 Реализовать инкрементальный режим: отправлять только `tail`, когда baseline не изменён (попадание в prompt cache)
- [ ] 4.19 Написать интеграционный тест: стабильный baseline → `epoch_broken=False` → отправка только tail
- [ ] 4.20 Написать интеграционный тест: изменение baseline → `epoch_broken=True` → отправка полного baseline
- [ ] 4.21 Обеспечить, чтобы разрывы эпох были ограничены: не более одного за ход
- [ ] 4.22 Реализовать debounce `DEFERRED`: накапливать изменения, применять вместе на следующей границе
- [ ] 4.23 Добавить метрики: `context_epoch_breaks_total`, `context_reconcile_total`, `context_prompt_cache_hit_rate`
- [ ] 4.24 Добавить span трейсинга: `context.reconcile` с атрибутами (`state`, `epoch_broken`, `changed_sources`)
- [ ] 4.25 Проверить, что feature flag `agents.context.lifecycle.incremental=false` использует режим гидрации (baseline перестраивается каждый ход)
- [ ] 4.26 Проверить, что feature flag `agents.context.lifecycle.incremental=true` использует режим эпох (baseline стабилен, отправка только tail)

## Фаза 5: Полный DependencyGraph (2 недели)

- [ ] 5.1 Реализовать рекурсивное разрешение зависимостей в `DependencyGraph.get_dependencies(recursive=True)`
- [ ] 5.2 Обеспечить, чтобы рекурсивное разрешение использовало множество посещённых для предотвращения бесконечных циклов
- [ ] 5.3 Обеспечить, чтобы порядок результата был детерминированным (по порядку первого посещения)
- [ ] 5.4 Написать unit тесты для рекурсивного разрешения зависимостей, включая транзитивные зависимости
- [ ] 5.5 Написать интеграционный тест: большой проект (1000+ файлов) → `gather()` завершается за <1с
- [ ] 5.6 (Опционально) Реализовать парсинг импортов на основе tree-sitter для улучшенной точности
- [ ] 5.7 (Опционально) Написать unit тесты, сравнивающие точность tree-sitter и regex
- [ ] 5.8 Добавить метрики: `context_gathered_files` с label `task_type` для больших проектов
- [ ] 5.9 Проверить, что feature flag `agents.context.gather.recursive_dependencies=false` использует не рекурсивный режим
- [ ] 5.10 Проверить, что feature flag `agents.context.gather.use_tree_sitter=true` использует tree-sitter, если реализован

## Фаза 6: Мультиагент (2 недели)

- [ ] 6.1 Реализовать `ChildSessionManager.create_child()`, создающий изолированную дочернюю сессию
- [ ] 6.2 Обеспечить, чтобы дочерняя сессия имела отдельные `agent_scope` и `ContextEpoch`
- [ ] 6.3 Реализовать `ChildSessionManager.collect_summary()`, возвращающий `SubagentResult`
- [ ] 6.4 Написать unit тесты для `ChildSessionManager`, включая изоляцию и сбор summary
- [ ] 6.5 Реализовать `process_subagent_response()`, суммаризирующий результат субагента для родителя
- [ ] 6.6 Добавить summary в область родителя как `ContextType.AGENT_REPORT` с `priority=7`
- [ ] 6.7 Реализовать graceful degradation: если суммаризация завершается сбоем, вернуть усечённый сырой результат
- [ ] 6.8 Реализовать обработку сбоя субагента: вернуть summary ошибки родителю, не ломать родителя
- [ ] 6.9 Реализовать обработку таймаута субагента: отменить дочернюю задачу, вернуть метку таймаута родителю
- [ ] 6.10 Написать unit тесты для `process_subagent_response()`, включая сбой и таймаут
- [ ] 6.11 Интегрировать `OrchestratedStrategy` с `ContextManager`: `build_context()` + `process_subagent_response()` + `ensure_context_fits()`
- [ ] 6.12 Написать интеграционный тест: `OrchestratedStrategy` → оркестратор + субагенты → суммаризированные результаты
- [ ] 6.13 Интегрировать `ChoreographyStrategy` с `ContextManager`: `build_context()` + `process_subagent_response()` (только победитель)
- [ ] 6.14 Написать интеграционный тест: `ChoreographyStrategy` → broadcast → победитель обработан, остальные отброшены
- [ ] 6.15 Интегрировать `HierarchicalStrategy` с `ContextManager`: `build_context()` + `process_subagent_response()` + `ensure_context_fits()` на каждом уровне
- [ ] 6.16 Написать интеграционный тест: `HierarchicalStrategy` → дерево агентов → суммаризация снизу вверх
- [ ] 6.17 Обеспечить, чтобы модель жизненного цикла (гидрация vs эпоха) была прозрачной для стратегий
- [ ] 6.18 Написать тест: стратегия не знает о модели жизненного цикла, использует только API `build_context()`
- [ ] 6.19 (Опционально) Реализовать федеративный `share_item()` за feature flag `agents.context.multiagent.federation=true`
- [ ] 6.20 (Опционально) Написать тест: федерация конфликтует со стабильностью эпохи → `epoch_broken=True`
- [ ] 6.21 Добавить метрики: `context_subagent_responses_total`, `context.subagent.failures`, `context.subagent.timeouts`
- [ ] 6.22 Проверить, что feature flag `agents.context.multiagent.federation=false` использует только изоляцию

## Сквозные задачи

- [ ] X.1 Написать end-to-end тест: полный цикл агента с `ContextManager` (Фазы 1-6 включены)
- [ ] X.2 Реализовать логику canary rollout: `CODELAB_CONTEXT_ROLLOUT_PERCENT` для постепенного rollout
- [ ] X.3 Написать дашборд мониторинга canary: сравнение метрик canary vs legacy
- [ ] X.4 Определить критерии отката: error rate > 0.01, p95 latency > 400ms, cache hit rate < 0.50
- [ ] X.5 Написать runbook: как включать/отключать функции, как откатывать, как мониторить
- [ ] X.6 Обновить `README.md` с документацией Context Manager
- [ ] X.7 Обновить `AGENTS.md` с соглашениями Context Manager
- [ ] X.8 Провести code review: все фазы проверены командой архитектуры
- [ ] X.9 Провести security review: защита от prompt injection, блокировка чувствительных путей
- [ ] X.10 Провести performance review: результаты бенчмарков против целей SLO

## Критерии успеха

- [ ] S.1 Все фазы 0-6 реализованы согласно спецификациям
- [ ] S.2 Legacy `ContextCompactor` работает при `enabled=false` без регрессий
- [ ] S.3 `PayloadEnvelope` — единственный формат payload в пути формирования
- [ ] S.4 Graceful degradation: горячий путь никогда не падает, каждый сбой имеет fallback
- [ ] S.5 Наблюдаемость: 20+ метрик, spans трейсинга, структурированные логи
- [ ] S.6 Canary rollout: 5% → 25% → 50% → 100% с метриками и критериями отката
- [ ] S.7 Все краевые случаи из EDGE_CASES.md имеют приёмочные тесты
- [ ] S.8 Вся обработка ошибок из ERROR_HANDLING.md имеет тесты
- [ ] S.9 SLO производительности выполнены: `build_context()` p95 < 200ms, cache hit rate > 0.80
- [ ] S.10 Документация обновлена: CONSOLIDATED_ARCHITECTURE.md, INTERFACES.md, DATA_MODELS.md
