# Slash-команда /context — наблюдаемость Context Manager

> **Статус:** Реализовано (Phase 1; расширенная наблюдаемость — config/last/files/graph/profile)
> **Компонент:** `src/codelab/server/protocol/handlers/slash_commands/builtin/context.py`
> **Зависимости:** MetricsTracker, ContextConfig, Tracer (опционально)

Команда `/context` предоставляет интерфейс для наблюдения за состоянием Context Manager, диагностики проблем и управления включением/выключением в runtime.

---

## Назначение

Context Manager — критический компонент, отвечающий за сбор, бюджетирование и оптимизацию контекста для LLM. Команда `/context` решает три задачи:

1. **Наблюдаемость** — показывает метрики сборки контекста (время, количество файлов, токены)
2. **Диагностика** — отображает трассировочные span'ы для анализа производительности
3. **Управление** — позволяет включить/выключить Context Manager без перезапуска сервера

---

## Синтаксис

```
/context              # Расширенная сводка (Контекст, LLM, Агент)
/context config       # Полная действующая конфигурация с бюджетом
/context last         # Детали последней сборки (тайминги стадий, файлы, токены)
/context files        # Список собранных файлов с токенами
/context graph        # Статистика графа зависимостей
/context profile      # Последний профиль задачи (TaskAnalyzer)
/context spans        # Последние трассировочные span'ы
/context on           # Включить Context Manager
/context off          # Выключить Context Manager
```

---

## Подкоманды

### `/context` (без аргументов) — расширенная сводка

Показывает текущее состояние Context Manager и агрегированные метрики сессии по трём
секциям: **Контекст**, **LLM**, **Агент**.

**Вывод:**
```
📦 **Context Manager** ✅

**Статус:** `enabled=true`, `gather=on`

**Контекст:**
• Сборок: `15`
• Среднее время: `245.3ms`
• Собрано файлов: `42`
• Baseline токенов: `18,450`
• Tail токенов: `3,200`

**LLM:**
• Вызовов: `15`
• Input tokens: `210,300`
• Output tokens: `18,400`

**Агент:**
• Ответов: `15`
• Ошибок: `0`

Для конфигурации: `/context config`
Для деталей: `/context last`
Для файлов: `/context files`
Для графа: `/context graph`
Для профиля: `/context profile`
Для span'ов: `/context spans`
Для управления: `/context on|off`
```

**Источники данных:**
- `MetricsTracker.get_metrics(session_id)` — агрегированные метрики (Контекст, LLM, Агент)
- `session.config_values["context_enabled"]` / `["context_gather_enabled"]` — runtime override (приоритет над конфигом)
- `ContextConfig.enabled` / `.gather_enabled` — конфигурация из TOML

**Логика:**
- Каждая секция при отсутствии данных выводит «нет данных (…)»
- Runtime override из `session.config_values` имеет приоритет над `ContextConfig`

---

### `/context config` — действующая конфигурация

Показывает полную конфигурацию `ContextConfig` с бюджетом, рассчитанным в токенах из
процентных долей, и runtime-override'ами из `session.config_values` (ключи `context_*`).

**Вывод:**
```
📋 **Конфигурация Context Manager:**

**Общие:**
• enabled: `true`
• gather_enabled: `true`
• incremental: `false`
• federation: `false`

**Анализ:**
• analyzer_model: `openai/gpt-4o-mini`
• recursive_dependencies: `false`

**Оптимизация:**
• use_tree_sitter: `false`
• use_tiktoken: `true`
• file_cache: `true` (max: `1,000` файлов)
• skeletonize: `true`

**Бюджет:**
• max_context_tokens: `128,000`
• reserved_tokens: `4,096`
• system: `20%` → `25,600 tokens`
• history: `50%` → `64,000 tokens`
• tool_output: `20%` → `25,600 tokens`
• response_buffer: `10%` → `12,800 tokens`
```

---

### `/context last` — детали последней сборки

Показывает детали последней сборки из `MetricsTracker` `context_build_details[-1]`:
тайминги стадий, тип задачи, fingerprint, число выбранных/кандидатных файлов, токены,
статистику графа и первые 10 файлов с токенами.

**Вывод:**
```
🔬 **Последняя сборка контекста:**

**Общее:**
• Длительность: `245ms`
• task_type: `feature`
• fingerprint: `a1b2c3…`

**Стадии:**
• extract: `2ms`
• analyze: `120ms`
• gather: `95ms`
• baseline: `18ms`
• tail: `5ms`
• fingerprint: `5ms`

**Файлы:**
• selected: `5`
• candidates: `12`

**Токены:**
• baseline: `12,300`
• tail: `3,200`
```

Если сборок не было → «📭 Детали недоступны. Сборок контекста ещё не было.»

---

### `/context files` — собранные файлы

Список файлов последней сборки с токенами на файл и суммой токенов.

**Вывод:**
```
📁 **Собранные файлы** (последняя сборка, 3 файла, 12,300 tokens):

1. `auth.py` — `5,400 tokens`
2. `validators.py` — `4,200 tokens`
3. `utils.py` — `2,700 tokens`
```

---

### `/context graph` — граф зависимостей

Статистика графа зависимостей из `DependencyGraph.get_stats()` последней сборки.

**Вывод:**
```
🕸️ **Граф зависимостей:**

• files_in_graph: `42`
• total_dependencies: `128`
• total_dependents: `95`
• project_files_cached: `310`
```

---

### `/context profile` — профиль задачи

Последний профиль задачи из `MetricsTracker.last_task_profile` (результат `TaskAnalyzer`).

**Вывод:**
```
🎯 **Последний профиль задачи:**

• task_type: `bug_fix`
• search_terms: `['auth', 'email', 'validation']`
• target_modules: `['auth.py', 'login.py']`
• investigation_depth: `2`
• needs_tests: `true`
```

---

### `/context spans` — трассировочные span'ы

Показывает последние 10 span'ов, связанных с контекстом (`context.build`, `context.gather`).

**Вывод:**
```
🔍 **Последние span'ы контекста** (источник: memory):

• **context.build** — `245ms` | scope: `single`, task: `feature`, files: `5`, tokens: `12,300`
• **context.gather** — `180ms` | task: `feature`, candidates: `12`, selected: `5`
• **context.build** — `310ms` | scope: `single`, task: `bug_fix`, files: `8`, tokens: `15,600`
• **context.gather** — `220ms` | task: `bug_fix`, candidates: `15`, selected: `8`
```

**Источники данных:**
- `Tracer.get_completed_spans(session_id)` — span'ы из памяти
- `~/.codelab/data/observability/spans/*.json` — экспортированные span'ы (fallback)

**Логика:**
1. Сначала проверяется память (актуальные span'ы)
2. Если пусто → читается из последнего экспортированного файла
3. Фильтруются только span'ы с именем, начинающимся на `context.`
4. Берутся последние 10 span'ов

**Атрибуты span'ов:**

| Span | Атрибуты | Описание |
|------|----------|----------|
| `context.build` | `agent_scope`, `task_type`, `gathered_files`, `baseline_tokens`, `tail_tokens` | Сборка контекста |
| `context.gather` | `task_type`, `candidate_files`, `selected_files` | Сбор файлов |

**Когда использовать:**
- Диагностика медленных сборок (`build_duration_ms > 500ms`)
- Анализ качества отбора файлов (`selected_files / candidate_files`)
- Проверка классификации задач (`task_type`)

---

### `/context on` — включить Context Manager

Включает Context Manager для текущей сессии (runtime override).

**Вывод:**
```
✅ Context Manager включён.
```

**Логика:**
- Устанавливает `session.config_values["context_enabled"] = "true"`
- Runtime override имеет приоритет над `ContextConfig.enabled`
- Если уже включён → выводит «ℹ️ Context Manager уже включён.»

**Эффект:**
- Следующий вызов `ExecutionEngine.build_context()` использует `DefaultContextManager`
- Legacy `ContextCompactor` не используется

---

### `/context off` — выключить Context Manager

Выключает Context Manager для текущей сессии (runtime override).

**Вывод:**
```
✅ Context Manager выключен.
```

**Логика:**
- Устанавливает `session.config_values["context_enabled"] = "false"`
- Runtime override имеет приоритет над `ContextConfig.enabled`
- Если уже выключен → выводит «ℹ️ Context Manager уже выключен.»

**Эффект:**
- Следующий вызов `ExecutionEngine.build_context()` использует legacy `ContextCompactor`
- `DefaultContextManager` не используется

---

## Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                    SlashCommandRouter                        │
│  (маршрутизация /context → ContextCommandHandler)           │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              ContextCommandHandler                           │
│  - execute(args, session) → CommandResult                   │
│  - get_definition() → AvailableCommand                      │
└─────────────────────────────────────────────────────────────┘
                            ↓
        ┌───────────────────┼───────────────────┐
        ↓                   ↓                   ↓
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│MetricsTracker│   │ ContextConfig│   │   Tracer     │
│(метрики)     │   │(конфиг)      │   │(span'ы)      │
└──────────────┘   └──────────────┘   └──────────────┘
```

**Зависимости:**
- `MetricsTracker` — обязательная, предоставляет метрики сессии
- `ContextConfig` — обязательная, предоставляет конфигурацию
- `Tracer` — опциональная, предоставляет span'ы (если `None` → `/context spans` возвращает ошибку)

**Интеграция в DI:**
```python
# src/codelab/server/di.py
@provide(scope=Scope.APP)
async def provide_context_command_handler(
    self,
    metrics_tracker: MetricsTracker,
    config: ContextConfig,
    tracer: Tracer | None,
) -> ContextCommandHandler:
    return ContextCommandHandler(metrics_tracker, config, tracer)
```

---

## Примеры использования

### Пример 1: Диагностика медленной сборки

**Проблема:** Пользователь замечает, что ответы агента стали медленнее.

**Действия:**
1. Выполнить `/context` — посмотреть среднее время сборки
2. Если `avg_build_ms > 500ms` → выполнить `/context spans`
3. Проверить `context.gather` span'ы — если `candidate_files >> selected_files`, значит граф зависимостей слишком большой
4. Решение: уменьшить `max_files` в конфигурации или отключить `recursive_dependencies`

**Ожидаемый вывод:**
```
/context
📦 **Context Manager** ✅

**Статус:** `enabled=true`, `gather=on`

**Метрики сессии:**
• Сборок контекста: `20`
• Среднее время сборки: `680.5ms`  ← высоко!
• Собрано файлов: `85`
• Baseline токенов: `45,200`

/context spans
🔍 **Последние span'ы контекста** (источник: memory):

• **context.build** — `720ms` | scope: `single`, task: `feature`, files: `12`, tokens: `18,400`
• **context.gather** — `580ms` | task: `feature`, candidates: `45`, selected: `12`  ← много кандидатов
```

**Решение:**
```toml
# ~/.codelab/codelab.toml
[agents.context]
gather_max_files = 8  # уменьшить с 10 до 8
recursive_dependencies = false  # отключить рекурсию
```

---

### Пример 2: Проверка качества отбора файлов

**Проблема:** Агент не находит нужные файлы для задачи.

**Действия:**
1. Выполнить `/context spans` — проверить `task_type` (правильно ли классифицирована задача)
2. Проверить `gathered_files` — сколько файлов собрано
3. Если файлов мало → увеличить `investigation_depth` в `TaskAnalyzer`
4. Если файлов много, но не те → проверить `search_terms` в `TaskProfile`

**Ожидаемый вывод:**
```
/context spans
🔍 **Последние span'ы контекста** (источник: memory):

• **context.build** — `245ms` | scope: `single`, task: `bug_fix`, files: `3`, tokens: `8,200`
• **context.gather** — `180ms` | task: `bug_fix`, candidates: `8`, selected: `3`
```

**Анализ:**
- `task_type: bug_fix` — правильно классифицировано
- `selected: 3` — мало файлов для bug fix
- Решение: увеличить `investigation_depth` с 1 до 2

---

### Пример 3: Runtime переключение

**Сценарий:** Пользователь хочет временно отключить Context Manager для сравнения с legacy поведением.

**Действия:**
1. Выполнить `/context off` — выключить Context Manager
2. Работать с агентом (используется legacy `ContextCompactor`)
3. Выполнить `/context on` — включить обратно
4. Сравнить качество ответов

**Вывод:**
```
/context off
✅ Context Manager выключен.

# ... работа с агентом ...

/context on
✅ Context Manager включён.
```

---

## Конфигурация

Команда `/context` использует следующие параметры конфигурации:

### TOML (`~/.codelab/codelab.toml`)

```toml
[agents.context]
enabled = true                  # Master switch (default: false)
gather_enabled = true           # Включить сбор файлов (default: true)

[agents.context.budget]
max_context_tokens = 128000     # Максимальный размер контекста
reserved_tokens = 4096          # Зарезервированные токены
```

### Environment variables (приоритет выше TOML)

```bash
CODELAB_CONTEXT_ENABLED=true
CODELAB_CONTEXT_GATHER_ENABLED=true
```

### Runtime override (приоритет выше всего)

```python
session.config_values["context_enabled"] = "true"  # из /context on
```

**Приоритет:**
1. Runtime override (`session.config_values`)
2. Environment variable (`CODELAB_CONTEXT_*`)
3. TOML конфигурация (`[agents.context.*]`)
4. Default значения (`ContextConfig`)

---

## Наблюдаемость

### Метрики (MetricsTracker)

| Метрика | Тип | Описание |
|---------|-----|----------|
| `context_build_count` | counter | Количество сборок контекста |
| `context_build_total_ms` | counter | Суммарное время сборки (мс) |
| `context_gathered_files` | counter | Суммарное количество собранных файлов |
| `context_baseline_tokens` | counter | Суммарное количество baseline токенов |
| `context_tail_tokens` | counter | Суммарное количество tail токенов |

**Агрегация:** метрики агрегируются per-session (по `session_id`).

### Span'ы (Tracer)

| Span | Атрибуты | Описание |
|------|----------|----------|
| `context.build` | `agent_scope`, `task_type`, `gathered_files`, `baseline_tokens`, `tail_tokens` | Сборка контекста |
| `context.gather` | `task_type`, `candidate_files`, `selected_files` | Сбор файлов |

**Экспорт:** span'ы экспортируются в `~/.codelab/data/observability/spans/*.json` (формат JSON).

### Логи (structlog)

```
context.build.start               # Начало сборки
context.build.task_analysis.complete  # Завершение классификации задачи
context.build.gather.complete     # Завершение сбора файлов
context.build.complete            # Завершение сборки
context.ensure_fits.check         # Проверка соответствия бюджету
context.subagent.process.start    # Начало обработки ответа субагента
```

**Уровень:** `INFO` для ключевых событий, `DEBUG` для деталей.

---

## Troubleshooting

### Проблема: `/context spans` возвращает «Нет span'ов контекста»

**Причины:**
1. Tracer не инициализирован → проверить `tracer is not None`
2. Сборок не было → выполнить `/context` и проверить `context_build_count`
3. Span'ы экспортированы и удалены из памяти → проверить `~/.codelab/data/observability/spans/`

**Решение:**
- Если `tracer is None` → проверить DI конфигурацию
- Если `context_build_count == 0` → выполнить промпт для агента
- Если span'ы экспортированы → команда автоматически читает из последнего файла

---

### Проблема: `/context on` не включает Context Manager

**Причины:**
1. Runtime override уже установлен → проверить `session.config_values["context_enabled"]`
2. Legacy `ContextCompactor` используется → проверить `ExecutionEngine.context_manager is not None`

**Решение:**
- Выполнить `/context` — проверить статус
- Если `enabled=false` после `/context on` → проверить DI (контекст менеджер не инжектируется)

---

### Проблема: метрики показывают `context_build_count == 0`

**Причины:**
1. Context Manager выключен → выполнить `/context on`
2. Сессия новая, сборок не было → выполнить промпт для агента
3. MetricsTracker не инициализирован → проверить DI конфигурацию

**Решение:**
- Выполнить `/context` — проверить статус
- Если `enabled=true` и `context_build_count == 0` → выполнить промпт
- Если метрики не появляются → проверить `metrics_tracker.record_context_build()` в `DefaultContextManager`

---

## Связанные документы

- [CONSOLIDATED_ARCHITECTURE.md](./CONSOLIDATED_ARCHITECTURE.md) — архитектура Context Manager
- [OBSERVABILITY.md](./OBSERVABILITY.md) — каталог метрик и span'ов
- [PHASE_1_SPEC.md](./PHASE_1_SPEC.md) — спецификация Phase 1 (MVP-сбор)
- [INTERFACES.md](./INTERFACES.md) — контракты Context Manager
