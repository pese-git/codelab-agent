# Slash-команда /context — наблюдаемость Context Manager

> **Статус:** Реализовано (Phase 1)
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
/context              # Сводка метрик (по умолчанию)
/context spans        # Последние трассировочные span'ы
/context on           # Включить Context Manager
/context off          # Выключить Context Manager
```

---

## Подкоманды

### `/context` (без аргументов) — сводка метрик

Показывает текущее состояние Context Manager и агрегированные метрики сессии.

**Вывод:**
```
📦 **Context Manager** ✅

**Статус:** `enabled=true`, `gather=on`

**Метрики сессии:**
• Сборок контекста: `15`
• Среднее время сборки: `245.3ms`
• Собрано файлов: `42`
• Baseline токенов: `18,450`
• Tail токенов: `3,200`

**Последние сборки:**
  1. `180ms`, 5 файлов, 12,300 токенов
  2. `310ms`, 8 файлов, 15,600 токенов
  3. `220ms`, 4 файла, 9,800 токенов
  4. `290ms`, 7 файлов, 14,200 токенов
  5. `260ms`, 6 файлов, 11,500 токенов

Для span'ов: `/context spans`
Для управления: `/context on|off`
```

**Источники данных:**
- `MetricsTracker.get_metrics(session_id)` — агрегированные метрики
- `session.config_values["context_enabled"]` — runtime override (приоритет над конфигом)
- `ContextConfig.enabled` — конфигурация из TOML
- `MetricsTracker.debug` — флаг включения детальных деталей

**Логика:**
- Если `context_build_count == 0` → выводится «нет данных (сборок не было)»
- Если `debug == true` → показываются последние 5 сборок с деталями
- Runtime override из `session.config_values` имеет приоритет над `ContextConfig`

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
