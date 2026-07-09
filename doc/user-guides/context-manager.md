# Context Manager — Руководство пользователя

> **Статус:** Phase 0-3 реализованы, Phase 4-6 готовы к разработке  
> **Дата:** 2026-07-07

## Что такое Context Manager

Context Manager — интеллектуальная система управления контекстом для LLM-агентов. Автоматически собирает релевантные файлы, оптимизирует использование контекстного окна и обеспечивает стабильную работу на длинных сессиях.

## Включение

По умолчанию Context Manager отключён. Включите через конфигурацию:

```toml
# ~/.codelab/codelab.toml
[agents.context]
enabled = true
gather_enabled = true
```

Или через переменную окружения:

```bash
export CODELAB_CONTEXT_ENABLED=true
```

## Возможности (Phase 0-3)

### 1. Интеллектуальный сбор файлов (Phase 1)

Система автоматически определяет релевантные файлы для вашей задачи:

- **TaskAnalyzer** — классифицирует задачу (bug fix, feature, refactor)
- **ContextGatherer** — собирает файлы через ACP ToolRegistry
- **DependencyGraph** — разрешает импорты (regex-based)
- **TokenBudgetManager** — распределяет бюджет токенов

**Пример:**
```
Пользователь: "Исправь баг в аутентификации"

Система:
1. Классифицирует задачу как BUG_FIX
2. Ищет файлы: auth.py, login.py, validators.py
3. Читает содержимое через ACP RPC
4. Разрешает зависимости (импорты)
5. Формирует контекст с приоритетом
```

### 2. Кэширование файлов (Phase 2)

- **FileContentCache** — LRU-кэш содержимого файлов (до 1000 файлов)
- **FileCacheDecorator** — перехватывает `fs/read` и `fs/write`
- **InvalidationSignalBus** — публикует сигналы изменения файлов

**Результат:** Повторные чтения того же файла мгновенны (из кэша).

### 3. AST-скелетирование (Phase 2)

- **CodeSkeletonizer** — сжимает код до сигнатур (tree-sitter + regex)
- Поддерживает: Python, TypeScript, Dart, Go, Rust, Java, C++
- Детерминированный вывод (стабильность prompt cache)

**Пример:**
```python
# Оригинал (100 строк)
def authenticate_user(username, password):
    """Аутентифицирует пользователя..."""
    # 50 строк логики
    ...

# Skeleton (10 строк)
def authenticate_user(username, password):
    """Аутентифицирует пользователя..."""
    ...
```

**Экономия:** 80-85% токенов на файлах кода.

### 4. Точный подсчёт токенов (Phase 2)

- **TiktokenCounter** — точный подсчёт через tiktoken (cl100k_base)
- **ApproximateTokenCounter** — fallback (len(text) // 4)
- Автоматический выбор (tiktoken → approximate)

### 5. Трёхфазное сжатие (Phase 3)

Когда контекст превышает лимит, система применяет 3 фазы сжатия:

#### Фаза 1: Prune (FIFO удаление)
- Удаляет старые tool outputs
- Сохраняет первые 2 и последние N сообщений
- Приоритетное удаление: tool (4) → assistant (6) → user (8) → system (10)

#### Фаза 2: Skeletonize (AST-сжатие)
- Применяет CodeSkeletonizer к файлам в контексте
- Только для read-only файлов (не редактируемых агентом)
- Проверка: если skeleton >= original → использует оригинал

#### Фаза 3: Summarize (LLM-суммаризация)
- Вызывает LLM для суммаризации истории
- Сохраняет ключевые решения и состояние задачи
- **Graceful degradation:** если LLM недоступен → Prune + Skeletonize

**Результат:** Агент работает стабильно на длинных сессиях без переполнения контекста.

### 6. Priority-based eviction (Phase 3)

Система защищает критические элементы от вытеснения:

| Приоритет | Тип | Защита |
|-----------|-----|--------|
| 10 | system_rules | Не вытесняется (кроме критического переполнения) |
| 8 | user_prompt | Вытесняется при критическом переполнении |
| 6 | assistant | Вытесняется после tool outputs |
| 4 | tool outputs | Вытесняется первым |

### 7. SkillCatalogSource (Phase 3)

Автоматически добавляет каталог доступных скиллов в системный промпт:

```xml
<available_skills>
  <skill name="python">Python best practices</skill>
  <skill name="testing">Testing strategies</skill>
</available_skills>
```

**Fingerprint:** Детектирует добавление/удаление/изменение скиллов.

### 8. Контекстный реестр (Phase 3)

- **ContextRegistry** — управляет источниками контекста
- **FileContextSource** — файлы как источники
- **SkillCatalogSource** — каталог скиллов
- **detect_changes()** — обнаруживает изменения через fingerprint

## Наблюдаемость

### Slash-команда `/context`

```
/context              # Показать состояние
/context on           # Включить
/context off          # Выключить
/context metrics      # Показать метрики
/context spans        # Показать span'ы
```

### Метрики

- `context_build_count` — количество сборок контекста
- `context_build_total_ms` — общее время сборки
- `context_gathered_files` — количество собранных файлов
- `context_baseline_tokens` — токены в baseline
- `context_tail_tokens` — токены в tail
- `context_compaction_count` — количество сжатий
- `context_compaction_total_ratio` — общее соотношение сжатия
- `context_compaction_degraded_count` — количество деградаций

### Span'ы трейсинга

- `context.build` — сборка контекста
  - Атрибуты: `agent_scope`, `task_type`, `gathered_files`, `baseline_tokens`, `tail_tokens`
- `context.gather` — сбор файлов
  - Атрибуты: `task_type`, `search_terms`, `candidate_files`, `selected_files`
- `context.compact` — сжатие контекста
  - Атрибуты: `phase`, `ratio`, `tokens_before`, `tokens_after`, `degraded`, `degrade_reason`

## Конфигурация

### Полный пример

```toml
# ~/.codelab/codelab.toml
[agents.context]
enabled = true                    # Master switch
gather_enabled = true             # Включить сбор файлов
recursive_dependencies = false    # Рекурсивное разрешение зависимостей
use_tree_sitter = false           # Использовать tree-sitter (vs regex)
use_tiktoken = true               # Использовать tiktoken (vs approximate)
file_cache = true                 # Включить кэш файлов
skeletonize = true                # Включить скелетирование
cache_max_files = 1000            # Максимум файлов в кэше
incremental = false               # Инкрементальный режим (Phase 4)
federation = false                # Федеративный обмен (Phase 6)

[agents.context.budget]
max_context_tokens = 128000       # Максимальный размер контекста
reserved_tokens = 4096            # Зарезервированные токены
system_share = 0.20               # Доля для system prompt
history_share = 0.50              # Доля для истории
tool_output_share = 0.20          # Доля для tool outputs
response_buffer_share = 0.10      # Буфер для ответа
```

### Переменные окружения

```bash
export CODELAB_CONTEXT_ENABLED=true
export CODELAB_CONTEXT_GATHER_ENABLED=true
export CODELAB_CONTEXT_MAX_CONTEXT_TOKENS=128000
export CODELAB_CONTEXT_RESERVED_TOKENS=4096
```

## Примеры использования

### Пример 1: Исправление бага

```
Пользователь: "Исправь баг в аутентификации — падает при пустом email"

Система:
1. TaskAnalyzer: task_type=BUG_FIX, investigation_depth=2
2. ContextGatherer:
   - search_terms: ["auth", "email", "validation"]
   - target_modules: ["auth.py", "login.py"]
   - Собрано: auth.py, validators.py, utils.py
3. DependencyGraph: разрешает импорты
4. TokenBudgetManager: аллоцирует бюджет
5. PayloadEnvelope: baseline (system + files) + tail (user prompt)
6. LLM получает оптимизированный контекст
```

### Пример 2: Длинная сессия с сжатием

```
Сессия: 50 итераций, 200 tool calls

Проблема: Контекст превышает 128000 токенов

Решение (Phase 3):
1. Prune: удаляет старые tool outputs (tool priority=4)
   - Было: 200 сообщений
   - Стало: 50 сообщений (первые 2 + последние 3 + middle)
2. Skeletonize: сжимает файлы кода
   - auth.py: 100 строк → 20 строк (80% экономия)
   - validators.py: 80 строк → 15 строк (81% экономия)
3. Summarize: LLM суммаризирует историю
   - Сохраняет ключевые решения
   - Сохраняет состояние задачи
4. Результат: контекст помещается в окно, агент продолжает работу
```

### Пример 3: Деградация без LLM

```
Сценарий: LLM недоступен (сеть, таймаут)

Система:
1. Prune: ✅ работает (без LLM)
2. Skeletonize: ✅ работает (без LLM)
3. Summarize: ❌ пропускается
4. Graceful degradation: продолжает с Prune + Skeletonize
5. Лог: summarization_failed_degrade_to_prune
6. Метрика: context_compaction_degraded_count += 1
```

## Обратная совместимость

При `enabled=false` (default) используется legacy `ContextCompactor`:

```toml
[agents.context]
enabled = false  # Legacy режим
```

**Поведение:**
- Двухфазное сжатие (Prune + LLM Summarize)
- Нет автоматического сбора файлов
- Нет кэша файлов
- Нет скелетирования

**Миграция:** Плавная, без изменения API.

## Производительность

### SLO (Service Level Objectives)

- `build_context()` p95 < 200ms (без вызовов LLM)
- Cache hit rate > 0.80
- Compression ratio > 0.50 (50% экономия)

### Бенчмарки

| Сценарий | Токены до | Токены после | Экономия |
|----------|-----------|--------------|----------|
| Короткая сессия (10 итераций) | 50,000 | 45,000 | 10% |
| Средняя сессия (30 итераций) | 100,000 | 70,000 | 30% |
| Длинная сессия (100 итераций) | 200,000 | 120,000 | 40% |

## Troubleshooting

### Проблема: Контекст не помещается

**Симптомы:**
```
context.ensure_fits.exceeded
current=150000 available=124000
```

**Решение:**
1. Увеличьте `max_context_tokens` (если модель поддерживает)
2. Уменьшите `reserved_tokens`
3. Включите `skeletonize=true`
4. Проверьте метрику `context_compaction_ratio`

### Проблема: Низкий cache hit rate

**Симптомы:**
```
context_file_cache_hits=10
context_file_cache_misses=90
```

**Решение:**
1. Увеличьте `cache_max_files`
2. Проверьте, что `file_cache=true`
3. Проверьте, что `FileCacheDecorator` перехватывает `fs/read`

### Проблема: Скелетирование не работает

**Симптомы:**
```
skeleton_not_beneficial path=auth.py
```

**Решение:**
1. Проверьте, что файл на поддерживаемом языке
2. Проверьте, что файл достаточно большой (>50 строк)
3. Проверьте, что `skeletonize=true`

## Дополнительные ресурсы

- [Архитектура](../internals/context-manager/CONSOLIDATED_ARCHITECTURE.md)
- [Slash-команда /context](../internals/context-manager/SLASH_COMMAND.md)
- [Пример работы](../internals/context-manager/WALKTHROUGH_EXAMPLE.md)
- [Обработка ошибок](../internals/context-manager/ERROR_HANDLING.md)
- [Стратегия тестирования](../internals/context-manager/TESTING_STRATEGY.md)

---

**Версия:** Phase 0-3 реализованы, Phase 4-6 готовы к разработке  
**Последнее обновление:** 2026-07-07
