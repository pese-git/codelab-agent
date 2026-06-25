# Federated Context Manager — Cheat Sheet

> Быстрая шпаргалка для разработчиков (v2.3 — единый путь формирования payload,
> слоистая архитектура, ABC + Factory). Канонические сигнатуры — см.
> `ARCHITECTURE.md §3.7` и `INTEGRATION_GUIDE.md §4`.

---

## Импорт (слоистая архитектура)

```python
# Слой 1: Утилиты
from codelab.server.agent.context.token_counter import (
    TokenCounter,              # ABC (НЕ инстанцируется напрямую)
    TiktokenCounter,           # Реализация (точный)
    ApproximateTokenCounter,   # Реализация (fallback)
    create_token_counter,      # Factory Method ← используйте это
)
from codelab.server.agent.context.ast_skeletonizer import (
    CodeSkeletonizer,          # ABC
    PythonASTSkeletonizer,     # Реализация
)
from codelab.server.agent.context.file_cache import (
    FileContentCache,          # ABC (Repository)
    InMemoryFileCache,         # Реализация (LRU)
    SessionFileCacheRegistry,  # Registry (кэши по сессиям)
)

# Слой 2: Сжатие
from codelab.server.agent.context.compactor import (
    ContextCompactor,          # ABC
    DefaultContextCompactor,   # Реализация
)

# Слой 3: Оркестрация
from codelab.server.agent.context.manager import (
    ContextManager,            # ABC
    FederatedContextManager,   # Реализация (наследует ContextManager)
)
from codelab.server.agent.context.items import ContextItem, ContextType
from codelab.server.agent.context.scope import AgentContextScope

# Decorators
from codelab.server.tools.executors.decorators.file_cache import (
    FileCacheDecorator,  # read-cache + write-invalidation + опц. FCM scope
)
```

---

## Единый путь формирования payload

Все стратегии используют **единый путь** через `ExecutionEngine.build_context()`:

```python
# SingleStrategy — 1 глобальный скоуп
context = await engine.build_context(
    session=session,
    prompt=prompt,
    agent_scope="single",  # по умолчанию
)

# OrchestratedStrategy — N скоупов
await fcm.create_scope("coder_agent", max_tokens=16000)
await fcm.add_to_scope("coder_agent", "src/db.py", "file_content", code)
context = await engine.build_context(
    session=session,
    prompt=prompt,
    agent_scope="coder_agent",
)
```

**Логика гидратации:**
- Если скоуп не существует → `hydrate_from_history()` (SingleStrategy)
- Если скоуп существует → использовать как есть (Multi-agent)

---

## Основные операции

### Создание компонентов (слоистая архитектура)

```python
# Слой 1: Утилиты
token_counter = create_token_counter()      # Factory: Tiktoken или Approximate
skeletonizer = PythonASTSkeletonizer()
cache_registry = SessionFileCacheRegistry(max_cache_size=1000)
file_cache = cache_registry.get_or_create(session_id="session_123")

# Слой 2: Сжатие
compactor = DefaultContextCompactor(
    token_counter=token_counter,
    skeletonizer=skeletonizer,
    max_context_tokens=128000,
    reserved_tokens=4096,
)

# Слой 3: Оркестрация (каноническая сигнатура — позиционно совпадает везде)
fcm = FederatedContextManager(
    token_counter=token_counter,
    skeletonizer=skeletonizer,
    compactor=compactor,
    file_cache=file_cache,
    event_bus=event_bus,   # опционально (observability)
    tracer=tracer,         # опционально (observability)
)
```

### FileContentCache

```python
# Получить кэш для сессии
cache = cache_registry.get_or_create(session_id="session_123")

# Кэширование файла
cache.set("src/db.py", "class Database: ...")

# Получение из кэша
content = cache.get("src/db.py")  # "class Database: ..." или None

# Инвалидация при записи
cache.invalidate("src/db.py")

# Очистка кэша сессии
cache_registry.remove(session_id="session_123")
```

### FileCacheDecorator

```python
from codelab.server.tools.executors.filesystem_executor import FileSystemToolExecutor
from codelab.server.tools.executors.decorators.file_cache import FileCacheDecorator

base_executor = FileSystemToolExecutor(bridge, permission_checker)
executor_with_cache = FileCacheDecorator(
    base_executor,
    file_cache=cache,
    context_manager=fcm,  # опционально: регистрировать read/terminal в FCM scope
)

# Успешный write → cache.invalidate(path) автоматически
# Успешный full read → cache.set(path, content) + FCM.add_to_scope (если задан)
result = await executor_with_cache.execute(
    session=session,
    arguments={"operation": "write", "path": "src/db.py", "content": "..."},
)
```

> `context_manager` опционален: без него декоратор работает как чистый
> file-cache (read-cache + invalidation), что нужно для `enable_fcm=false`.

### Работа со скоупами

```python
# Создать скоуп (max_tokens должен быть > 0, иначе ValueError)
scope = await fcm.create_scope("agent_name", max_tokens=4000)

# Добавить элемент (item > max_tokens → усекается, EDGE_CASES §1)
await fcm.add_to_scope(
    scope_name="agent_name",
    item_id="src/file.py",
    content_type="file_content",  # или agent_report, system_rules, ...
    content="def hello(): pass",
    priority=5,  # 0-4 низкий, 5-9 высокий, 10+ критический
)

# Получить элемент
item = scope.get("src/file.py")

# Удалить элемент
scope.remove("src/file.py")
```

### Шеринг между агентами

```python
await fcm.share_item(
    source_scope="search_agent",
    target_scope="coder_agent",
    item_id="src/file.py",
    new_priority=6,  # опционально
)
```

### Получение payload для LLM

```python
messages = await fcm.optimize_and_build_payload("agent_name")
# Returns: list[LLMMessage]
# ⚠️ Бросает ValueError, если сумма критических элементов (priority>=10)
#    превышает scope.max_tokens (EDGE_CASES §2).
```

---

## Типы контекста (ContextType)

| Тип | Описание | Пример |
|-----|----------|--------|
| `file_content` | Содержимое файла | Исходный код Python |
| `file_skeleton` | AST-скелет файла | Сигнатуры классов/функций |
| `terminal_output` | Вывод терминала | Результат команды |
| `user_prompt` | Промпт пользователя | Текст запроса |
| `system_rules` | Системные правила | System prompt |
| `agent_report` | Отчёт агента | Bug report, анализ |

---

## Приоритеты

| Диапазон | Значение | Примеры |
|----------|----------|---------|
| 0-4 | Низкий | Старые логи, устаревшие отчёты |
| 5-9 | Высокий | Текущие файлы, активные отчёты |
| 10+ | Критический | System rules (не вытесняются) |

---

## AST-скелетирование

Скелетонизатор — это **Strategy** (инъецируемый объект `CodeSkeletonizer`),
а не модульная функция:

```python
skeletonizer = PythonASTSkeletonizer()

# Исходный код: 200 токенов
code = """
class Database:
    def connect(self):
        # 50 строк логики
        pass

    def query(self, sql: str) -> dict:
        # 30 строк логики
        pass
"""

# Скелет: 30 токенов
result = skeletonizer.skeletonize(code, file_id="db.py")
# class Database:
#     def connect(self): ...
#     def query(self, sql: str) -> dict: ...
```

> Edge case (EDGE_CASES §3): для minified-кода скелет может оказаться не
> меньше оригинала — FCM в этом случае оставляет оригинал.

---

## Подсчёт токенов

`TokenCounter` — это ABC. Создавайте реализацию через фабрику:

```python
counter = create_token_counter()  # TiktokenCounter или ApproximateTokenCounter

tokens = counter.count("Hello, world!")

# Проверка режима — через тип, а не через атрибут
from codelab.server.agent.context.token_counter import TiktokenCounter
if isinstance(counter, TiktokenCounter):
    print("Точный подсчёт (tiktoken)")
else:
    print("Fallback: len // 4")
```

---

## Конфигурация

### TOML

```toml
[agents.context]
enable_fcm = true                  # master switch (каноническое имя)
use_tiktoken = true
enable_ast_skeletonization = true
enable_file_cache = true

[agents.context.cache]
max_size = 1000

[agents.context.compaction]
max_context_tokens = 128000
reserved_tokens = 4096
```

### Feature flag

FCM и legacy `ContextCompactor` — **взаимоисключающие** пути
(`ExecutionEngine` принимает либо `context_manager`, либо `compactor`):

```python
if config.agents.context.enable_fcm:
    fcm = FederatedContextManager(...)
    engine = ExecutionEngine(tool_registry=..., context_manager=fcm)
else:
    engine = ExecutionEngine(tool_registry=..., compactor=ContextCompactor(...))
```

---

## Тестирование

```bash
# Все тесты FCM
pytest tests/server/agent/context/ -v

# С coverage
pytest tests/server/agent/context/ --cov=codelab.server.agent.context

# Конкретный тест
pytest tests/server/agent/context/test_manager.py::test_share_item -v
```

---

## Отладка

### Логирование

```python
import logging
logging.getLogger("codelab.server.agent.context").setLevel(logging.DEBUG)
```

### Проверка состояния

```python
# Количество скоупов
len(fcm.scopes)

# Токены в скоупе
scope.get_total_tokens()

# Элементы по приоритету
items = scope.get_items_by_priority()
```

---

## Частые ошибки

| Ошибка | Причина | Решение |
|--------|---------|---------|
| `Scope '...' not found` | Скоуп не создан | Вызвать `create_scope()` |
| `Item '...' not found` | Элемент не добавлен | Вызвать `add_to_scope()` |
| `Critical items ... exceed scope budget` | Сумма priority>=10 > max_tokens | Уменьшить критические или поднять `max_tokens` |
| `max_tokens must be positive` | `create_scope(..., max_tokens<=0)` | Передать положительный лимит |
| `TypeError: Can't instantiate abstract class TokenCounter` | Прямой вызов `TokenCounter()` | Использовать `create_token_counter()` |

---

## Ссылки

- [Полная архитектура](./ARCHITECTURE.md)
- [Руководство по интеграции](./INTEGRATION_GUIDE.md)
- [Диаграммы](./DIAGRAMS.md)
- [Edge cases](./EDGE_CASES.md)
- [Обработка ошибок](./ERROR_HANDLING.md)
