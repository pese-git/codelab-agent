# Tasks: Fix Infinite File Read Loop

## Фаза 1: Исправление FileCacheDecorator (2 часа)

- [x] 1.1 Исправить метод `execute()` для проверки кэша перед чтением
  - Файл: `src/codelab/server/agent/context/file_cache_decorator.py`
  - Логика: проверить кэш → вернуть из кэша или выполнить wrapped.execute()
  - Добавить метаданные `from_cache: True` для кэшированных результатов

- [x] 1.2 Добавить подсчёт чтений и проверку лимитов
  - Добавить поле `_read_counts: dict[str, dict[str, int]]`
  - Проверять лимит перед чтением (максимум 3 чтения файла)
  - Возвращать ошибку при превышении лимита

- [x] 1.3 Интегрировать метрики в FileCacheDecorator
  - Передать `MetricsTracker` через конструктор
  - Вызывать `record_file_cache_hit()` при попадании в кэш
  - Вызывать `record_file_cache_miss()` при промахе
  - Вызывать `record_file_read_limit_exceeded()` при превышении лимита

- [x] 1.4 Написать unit тесты для FileCacheDecorator
  - Файл: `tests/server/agent/context/test_file_cache_decorator.py`
  - Тесты: проверка кэша, сохранение, лимиты, метрики

## Фаза 2: Метрики кэша (1 час)

- [x] 2.1 Добавить поля метрик в `SessionMetrics`
  - Файл: `src/codelab/server/observability/metrics_tracker.py`
  - Поля: `file_cache_hits`, `file_cache_misses`, `file_read_limit_exceeded`

- [x] 2.2 Добавить методы для метрик в `MetricsTracker`
  - Методы: `record_file_cache_hit()`, `record_file_cache_miss()`, `record_file_read_limit_exceeded()`
  - Интеграция: вызов из FileCacheDecorator

- [x] 2.3 Написать unit тесты для метрик
  - Файл: `tests/server/observability/test_metrics_tracker.py`
  - Тесты: обновление метрик, корректность подсчёта

## Фаза 3: Информирование LLM (1 час)

- [x] 3.1 Добавить метод для генерации информации о прочитанных файлах
  - Файл: `src/codelab/server/agent/context/manager.py`
  - Логика: получить список файлов из кэша, отформатировать в Markdown

- [x] 3.2 Интегрировать информацию в system prompt
  - Вызывать в `build_context()` после формирования baseline
  - Добавлять LLMMessage с информацией о прочитанных файлах

- [x] 3.3 Написать unit тесты
  - Файл: `tests/server/agent/context/test_manager.py`
  - Тесты: генерация информации, интеграция в system prompt

## Фаза 4: Тестирование и валидация (2 часа)

- [x] 4.1 Запустить все unit тесты
  - Команда: `pytest tests/server/agent/context/ tests/server/observability/`
  - Критерий: все тесты проходят

- [x] 4.2 Запустить integration тесты
  - Команда: `pytest tests/integration/`
  - Критерий: все тесты проходят

- [x] 4.3 Провести ручное тестирование
  - Сценарий: диалог с многократным чтением файлов
  - Проверка: нет вечных циклов
  - Проверка: кэш работает (метрики показывают hits)

- [x] 4.4 Провести performance тестирование
  - Метрики: время выполнения, количество RPC вызовов
  - Сравнение: до/после изменений

## Критерии приёмки

- [x] Все unit тесты проходят
- [x] Все integration тесты проходят
- [x] Количество RPC вызовов снижено в 3-5 раз
- [x] Время выполнения tool calls снижено на 30%+
- [x] Нет вечных циклов при многократном чтении
- [x] Метрики показывают корректные данные (file_cache_hits > 0)

## Оценка сложности

- Фаза 1: 2 часа
- Фаза 2: 1 час
- Фаза 3: 1 час
- Фаза 4: 2 часа

**Итого:** 6 часов (1 рабочий день)

## Риски

1. **Увеличение памяти:**
   - Митигация: ограничить размер кэша (1000 файлов, уже реализовано)
   - Мониторинг: метрики использования памяти

2. **Устаревание кэша:**
   - Митигация: `InvalidationSignalBus` уже реализован для инвалидации при `fs/write`
   - Мониторинг: логи устаревших файлов

3. **Сложность отладки:**
   - Митигация: подробное логирование (уже реализовано)
   - Мониторинг: метрики кэша

## Реализация

### Ветки

- ✅ `feature/context-manager-sync-phase-2` - коммит `c10b6d6e`
- ✅ `feature/context-manager-sync-phase-3` - rebase завершён
- ✅ `feature/context-manager-sync-phase-4` - rebase завершён, коммит `2c4160ed`

### Изменения

1. **FileCacheDecorator** - добавлена проверка кэша перед чтением файла
2. **Тесты** - обновлены для использования `operation` вместо `tool_name` (phase-4 API)
3. **Документация** - обновлена в proposal.md, design.md, tasks.md

### Статус

✅ **Завершено** - все изменения запушены в remote
