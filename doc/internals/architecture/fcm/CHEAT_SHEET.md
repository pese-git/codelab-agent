# Federated Context Manager — Cheat Sheet

> Быстрая шпаргалка для разработчиков

---

## Импорт

```python
from codelab.server.agent.context import (
    FederatedContextManager,
    AgentContextScope,
    ContextItem,
    ContextType,
    ASTSkeletonizer,
    TokenCounter,
)
```

---

## Основные операции

### Создание FCM

```python
fcm = FederatedContextManager(
    event_bus=event_bus,      # опционально
    tracer=tracer,            # опционально
    token_counter=TokenCounter(),
)
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
