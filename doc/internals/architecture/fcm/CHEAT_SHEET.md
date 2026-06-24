# Federated Context Manager — Cheat Sheet

> Быстрая шпаргалка для разработчиков (v2.1 — слоистая архитектура + ABC + FileContentCache)

---

## Импорт (слоистая архитектура)

```python
# Слой 1: Утилиты
from codelab.server.agent.context.token_counter import (
    TokenCounter,              # ABC
    TiktokenCounter,           # Реализация (точный)
    ApproximateTokenCounter,   # Реализация (fallback)
    create_token_counter,      # Factory Method
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
    FederatedContextManager,   # Реализация
)
from codelab.server.agent.context.items import ContextItem, ContextType
from codelab.server.agent.context.scope import AgentContextScope

# Decorators
from codelab.server.tools.executors.decorators.cache_invalidation import (
    CacheInvalidationDecorator,  # Инвалидация кэша при записи
)
```

---

## Основные операции

### Создание компонентов (слоистая архитектура)

```python
# Слой 1: Утилиты
token_counter = create_token_counter()  # Factory Method
skeletonizer = PythonASTSkeletonizer()
file_cache = InMemoryFileCache(max_size=1000)
cache_registry = SessionFileCacheRegistry(max_cache_size=1000)

# Слой 2: Сжатие
compactor = DefaultContextCompactor(
    token_counter=token_counter,
    skeletonizer=skeletonizer,
    max_context_tokens=128000,
    reserved_tokens=4096,
)

# Слой 3: Оркестрация
fcm = FederatedContextManager(
    token_counter=token_counter,
    skeletonizer=skeletonizer,
    compactor=compactor,
    file_cache=file_cache,
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

### CacheInvalidationDecorator

```python
# Создание chain of decorators (в DI или factory)
from codelab.server.tools.executors.filesystem_executor import FileSystemToolExecutor
from codelab.server.tools.executors.decorators.cache_invalidation import CacheInvalidationDecorator

base_executor = FileSystemToolExecutor(bridge, permission_checker)
executor_with_cache = CacheInvalidationDecorator(base_executor, file_cache=cache)

# Теперь при успешной записи кэш автоматически инвалидируется
result = await executor_with_cache.execute(
    session=session,
    arguments={"operation": "write", "path": "src/db.py", "content": "..."},
)
# Кэш для "src/db.py" инвалидирован автоматически
```

### Работа со скоупами

```python
# Создать скоуп
scope = await fcm.create_scope("agent_name", max_tokens=4000)

# Добавить элемент
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

```python
from codelab.server.agent.context.ast_skeletonizer import skeletonize

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
result = skeletonize(code, "db.py")
# class Database:
#     def connect(self): ...
#     def query(self, sql: str) -> dict: ...
```

---

## Подсчёт токенов

```python
counter = TokenCounter()

# Точный подсчёт (если tiktoken установлен)
tokens = counter.count("Hello, world!")

# Проверка режима
if counter.has_tiktoken:
    print("Точный подсчёт")
else:
    print("Fallback: len // 4")
```

---

## Конфигурация

### TOML

```toml
[agents.context]
enabled = true
cache_max_size = 1000
summarization_model = "openai/gpt-4o-mini"

[agents.context.skeletonization]
enabled = true
min_saving_percent = 50
```

### Feature flag

```python
if config.context.enabled:
    fcm = FederatedContextManager(...)
else:
    fcm = None

engine = ExecutionEngine(
    ...,
    context_manager=fcm,
)
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
| `Scope not found` | Скоуп не создан | Вызвать `create_scope()` |
| `Item not found` | Элемент не добавлен | Вызвать `add_to_scope()` |
| `Token limit exceeded` | Превышен бюджет | Проверить `max_tokens` |

---

## Ссылки

- [Полная архитектура](./ARCHITECTURE.md)
- [Руководство по интеграции](./INTEGRATION_GUIDE.md)
- [Диаграммы](./DIAGRAMS.md)
