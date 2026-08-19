# Design: Поддержка AGENTS.md инструкций

## Context

### Текущее состояние

CodeLab-агент формирует system prompt через `SystemPromptBuilder`, который объединяет:
1. Agent prompt (роль из `AgentRegistry`)
2. Global prompt (из `config.agent.system_prompt`)
3. MCP info (список подключённых MCP-серверов)

**Проблема**: отсутствует механизм загрузки проектных инструкций из `AGENTS.md`.

### Ограничения ACP-протокола

| Метод | Статус | Использование |
|-------|--------|---------------|
| `session/new` | Есть | Получение `cwd` — корня для discovery |
| `fs/read_text_file` | Есть | Чтение файлов в remote-режиме |
| `fs/list_directory` | **Нет** | Нельзя обойти дерево в remote |
| `fs/watch` | **Нет** | Нельзя подписаться на изменения в remote |

### Stakeholders

- **Пользователь** — хочет, чтобы агент учитывал контекст проекта
- **Агент (LLM)** — получает дополнительные инструкции в system prompt
- **Клиент (Zed/IDE)** — предоставляет `cwd` и `fs/read_text_file`

---

## Goals / Non-Goals

### Goals

1. **Загрузка инструкций** из `AGENTS.md` (и совместимых файлов) в system prompt
2. **Два режима работы**: `local` (прямое чтение) и `remote` (через ACP)
3. **Конфигурируемость** через `codelab.toml`
4. **Защита от prompt injection** — санитизация содержимого
5. **Кэширование** для избежания повторного чтения
6. **Тестируемость** — все компоненты с интерфейсами

### Non-Goals

1. **Иерархия в remote-режиме** — нет `fs/list_directory` в ACP
2. **File watching в real-time** — только polling или mtime
3. **Поддержка бинарных файлов** — только текстовые `.md` файлы
4. **Синтаксический парсинг Markdown** — инструкции передаются как текст
5. **Модификация ACP-протокола** — используем существующие методы

---

## Decisions

### Decision 1: Структура модуля `instructions/`

**Решение**: Создать отдельный модуль `src/codelab/server/agent/instructions/` с компонентами:

```
instructions/
├── config.py          # Pydantic модель конфигурации
├── protocol.py        # AgentsFileReader Protocol
├── local_reader.py    # LocalAgentsFileReader
├── remote_reader.py   # RemoteAgentsFileReader
├── discovery.py       # AgentsFileDiscovery
├── merger.py          # AgentsFileMerger
├── sanitizer.py       # AgentsFileSanitizer
└── resolver.py        # AgentsInstructionsResolver
```

**Обоснование**:
- SRP — каждый компонент отвечает за одну задачу
- OCP — легко добавить новый reader без изменения resolver
- Тестируемость — каждый компонент изолирован

**Альтернативы**:
- ❌ Один файл `agents_md.py` — сложно тестировать, нарушает SRP
- ❌ Интеграция в `system_prompt_builder.py` — смешение ответственности

---

### Decision 2: Protocol для readers

**Решение**: Использовать `typing.Protocol` для абстракции чтения файлов:

```python
class AgentsFileReader(Protocol):
    async def read(self, session: SessionState, path: Path) -> str | None: ...
```

**Обоснование**:
- Структурная типизация — не нужно наследование
- Легко mock-ить в тестах
- Поддерживает оба режима (local/remote)

**Альтернативы**:
- ❌ ABC с наследованием — избыточно для двух реализаций
- ❌ Union тип — сложно расширять

---

### Decision 3: Порядок инструкций в system prompt

**Решение**: Инструкции размещаются **между** agent prompt и global prompt:

```
1. Agent Prompt (роль)
2. AGENTS.md instructions ← NEW
3. Global Prompt (общие инструкции)
4. MCP Info (справка)
```

**Обоснование**:
- LLM лучше запоминает начало (primacy effect) и конец (recency effect)
- Контекст проекта важнее общих инструкций
- Роль агента — самая важная информация

**Альтернативы**:
- ❌ После global prompt — менее приоритетно
- ❌ Первым — роль агента важнее

---

### Decision 4: Стратегия выбора режима

**Решение**: Явный конфиг через `codelab.toml`:

```toml
[agents.instructions]
mode = "local"  # "local" | "remote"
```

**Обоснование**:
- Детерминированность — пользователь контролирует поведение
- Простота — не нужно угадывать режим
- Соответствует запросу пользователя

**Альтернативы**:
- ❌ Auto-detect (проверка `Path(cwd).exists()`) — хрупко, неявно
- ❌ По транспорту (stdio = local) — не всегда верно

---

### Decision 5: Discovery без иерархии (Phase 1)

**Решение**: Только root-level — поиск в `cwd` без обхода подкаталогов:

```python
def discover(self, cwd: Path) -> list[Path]:
    for name in self._file_names:
        path = cwd / name
        if path.exists():
            return [path]  # Первый найденный
    return []
```

**Обоснование**:
- Соответствует поведению Zed для external agents
- Простота реализации
- Достаточно для MVP

**Альтернативы**:
- ❌ Полная иерархия сразу — сложно, не работает в remote
- ❌ Обход всех подкаталогов — дорого, может найти лишнее

---

### Decision 6: Санитизация от prompt injection

**Решение**: Regex-паттерны для удаления опасных конструкций:

```python
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"you\s+are\s+now\s+(a|an)\s+",
    r"system\s*:",
]
```

**Обоснование**:
- Простая защита от очевидных атак
- Не влияет на нормальные инструкции
- Можно расширять

**Альтернативы**:
- ❌ Полная валидация — сложно, может сломать нормальные инструкции
- ❌ Без санитизации — уязвимость

---

### Decision 7: Кэширование с hash-проверкой

**Решение**: Кэш по `session_id` с hash содержимого:

```python
@dataclass
class CacheEntry:
    content: str
    files_hash: dict[str, int]  # path → hash
    timestamp: float
```

**Обоснование**:
- Быстрая проверка изменений (hash vs mtime)
- Per-session кэш — изоляция
- Для remote — polling каждый turn

**Альтернативы**:
- ❌ LRU кэш — избыточно для per-session данных
- ❌ Без кэша — повторное чтение каждый turn

---

### Decision 8: Интеграция через DI

**Решение**: Регистрация в `dishka` DI-контейнере:

```python
@provide(scope=Scope.APP)
def get_agents_instructions_resolver(self, config: AppConfig) -> AgentsInstructionsResolver:
    ...
```

**Обоснование**:
- Соответствует существующей архитектуре
- Легко mock-ить в тестах
- Централизованное создание зависимостей

---

## Risks / Trade-offs

### Risk 1: Remote-режим без иерархии

**Риск**: В remote-режиме нельзя обойти дерево каталогов — только root-level.

**Митигация**:
- Документировать ограничение
- Предложить клиентам передавать пути через `_meta` (нестандартное расширение)
- Phase 3: добавить hierarchy для local-режима

---

### Risk 2: Производительность remote-режима

**Риск**: +1 RTT на каждый prompt turn для чтения AGENTS.md.

**Митигация**:
- Кэширование с hash-проверкой
- `max_file_size` лимит (100KB по умолчанию)
- Опциональный `watch = false` для отключения polling

---

### Risk 3: Prompt injection через AGENTS.md

**Риск**: Злоумышленник может создать `AGENTS.md` с вредоносными инструкциями.

**Митигация**:
- Санитизация regex-паттернами
- System prompt имеет высший приоритет над AGENTS.md
- Документировать: "не доверяйте AGENTS.md из ненадёжных источников"

---

### Risk 4: Несовместимость с клиентами

**Риск**: Некоторые клиенты не поддерживают `fs/read_text_file`.

**Митигация**:
- Проверка `clientCapabilities.fs.readTextFile` при `initialize`
- Fallback: если capability отсутствует, использовать `mode = "local"` или пропустить инструкции
- Логирование предупреждения

---

### Risk 5: Большие файлы инструкций

**Риск**: `AGENTS.md` может быть слишком большим (займёт много токенов).

**Митигация**:
- `max_file_size` лимит (100KB ≈ 25K токенов)
- Рекомендация в документации: "50-150 строк оптимально"
- В будущем: суммаризация через LLM

---

## Migration Plan

### Phase 1: MVP (текущая)

1. Создать модуль `instructions/`
2. Реализовать `LocalAgentsFileReader`
3. Интегрировать в `SystemPromptBuilder`
4. Добавить конфигурацию
5. Покрыть тестами

**Rollback**: Удалить модуль, вернуть старый `SystemPromptBuilder`.

### Phase 2: Remote mode

1. Реализовать `RemoteAgentsFileReader`
2. Модифицировать `Resolver` для runtime bridge injection
3. Проверка capabilities при `initialize`

### Phase 3: Hierarchy (local only)

1. Расширить `AgentsFileDiscovery._find_hierarchy()`
2. Добавить конфигурацию `hierarchy = true`

### Phase 4: Watch mechanism

1. Реализовать `AgentsFileWatcher` (mtime для local)
2. Polling для remote
3. Интеграция в `Resolver`

---

## Open Questions

1. **Нужен ли fallback при ошибке чтения?** — Пропустить инструкции или вернуть ошибку?
   - **Решение**: Пропустить, логировать warning.

2. **Поддерживать ли `.agents.md` (hidden file)?**
   - **Решение**: Нет, только `AGENTS.md`, `CLAUDE.md`, `.cursorrules`.

3. **Нужен ли API для получения списка загруженных инструкций?**
   - **Решение**: Нет в Phase 1. Можно добавить через `_meta` в response.

4. **Как обрабатывать конфликт инструкций (root vs subdirectory)?**
   - **Решение**: Local overrides parent (как `.editorconfig`).
