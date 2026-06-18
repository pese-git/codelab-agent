## Context

### Current State

Клиентская часть CodeLab имеет два крупных сервиса, нарушающих принципы Clean Architecture:

**ChatViewModel** (1229 строк):
- 35 методов с 11 ответственностями
- `_handle_session_update()` — 200+ строк if/elif цепочки
- File I/O в async-контексте (блокирует event loop)
- Невозможно тестировать компоненты изолированно

**ACPTransportService** (1321 строка):
- 40 методов с 10 ответственностями
- Обработка `fs/*` и `terminal/*` RPC в одном классе
- Сложная логика request/response lifecycle
- Тесная связь с конкретными callback реализациями

### Constraints

- **Python 3.12+** — используем Protocol, runtime_checkable, type aliases
- **Clean Architecture** — Domain ← Application ← Infrastructure ← Presentation ← TUI
- **dishka DI** — декларативная регистрация компонентов
- **EventBus** — слабая связанность через события
- **Observable pattern** — реактивные обновления UI
- **asyncio** — все I/O операции async-safe

### Stakeholders

- **Разработчики** — нуждаются в тестируемом и расширяемом коде
- **DevOps** — нуждаются в стабильной промышленной эксплуатации
- **Пользователи** — нуждаются в отзывчивом UI без блокировок

## Goals / Non-Goals

**Goals:**

1. **SRP (Single Responsibility)** — каждый класс имеет одну ответственность
2. **OCP (Open/Closed)** — расширение без модификации существующего кода
3. **Testability** — каждый компонент тестируется изолированно
4. **Async Safety** — все I/O операции через `asyncio.to_thread`
5. **Error Isolation** — ошибка в одном handler не ломает другие
6. **Backward Compatibility** — публичный API не меняется

**Non-Goals:**

1. **Hot-reload** — конфигурация handlers при старте, без runtime замены
2. **Plugin System** — handlers регистрируются через DI, не динамически
3. **Multi-backend Persistence** — только File-based реализация (но Protocol позволяет расширение)
4. **Performance Optimization** — фокус на архитектуре, не на оптимизации
5. **UI Changes** — TUI компоненты не меняются

## Decisions

### Decision 1: Strategy/Dispatcher Pattern для Session Updates

**Решение:** Использовать Strategy pattern с `SessionUpdateHandler` Protocol и `SessionUpdateDispatcher` для маршрутизации.

**Обоснование:**
- **OCP** — новый тип update = новый handler, существующие не трогаем
- **Testability** — каждый handler тестируется изолированно с mock context
- **Error Isolation** — dispatcher ловит исключения в handler'ах
- **Extensibility** — легко добавить новые типы updates

**Альтернативы:**
- ❌ **Processor (монолитный)** — нарушает OCP, сложно тестировать
- ❌ **Chain of Responsibility** — избыточно для фиксированного набора типов
- ❌ **Visitor Pattern** — требует изменения всех handlers при добавлении типа

**Пример:**
```python
class SessionUpdateHandler(Protocol):
    def can_handle(self, update_type: str) -> bool: ...
    def handle(self, update_data: dict, context: ChatUpdateContext) -> None: ...

class MessageChunkHandler:
    def can_handle(self, update_type: str) -> bool:
        return update_type in {"agent_message_chunk", "user_message_chunk"}
    
    def handle(self, update_data: dict, context: ChatUpdateContext) -> None:
        # Обработка message chunks
        ...
```

### Decision 2: Protocol-based Persistence Port

**Решение:** `ChatPersistencePort` как Protocol, `FileChatPersistence` как реализация.

**Обоснование:**
- **DIP (Dependency Inversion)** — ChatViewModel зависит от абстракции, не реализации
- **Testability** — легко mock'ать persistence в тестах
- **Extensibility** — можно добавить SQLite/Redis без изменения ViewModel
- **Async Safety** — все операции через `asyncio.to_thread`

**Альтернативы:**
- ❌ **Concrete FileChatPersistence** — жёсткая связь, сложно тестировать
- ❌ **Abstract Base Class** — избыточно для одного метода, Protocol легче
- ❌ **Repository Pattern** — слишком абстрактно для простой задачи

**Пример:**
```python
class ChatPersistencePort(Protocol):
    async def save_messages(
        self, session_id: str, messages: list[dict[str, str]],
        replay_updates: list[dict[str, Any]] | None = None
    ) -> None: ...
    
    async def load_messages(self, session_id: str) -> list[dict[str, str]]: ...

class FileChatPersistence:
    def __init__(self, history_dir: Path) -> None:
        self._history_dir = history_dir
    
    async def save_messages(self, session_id: str, messages: list[dict[str, str]], ...) -> None:
        await asyncio.to_thread(self._write_json, ...)
```

### Decision 3: ChatUpdateContext для передачи состояния

**Решение:** `ChatUpdateContext` dataclass содержит всё необходимое для handler'а.

**Обоснование:**
- **Immutability** — context создаётся один раз, не меняется dispatcher'ом
- **Testability** — легко создать mock context в тестах
- **Flexibility** — handler'ы могут использовать разные поля context
- **Type Safety** — явные типы для всех полей

**Альтернативы:**
- ❌ **Передача отдельных параметров** — сложно расширять, много параметров
- ❌ **Global State** — нарушает SRP, сложно тестировать
- ❌ **Mutable Context** — handler'ы могут ломать состояние друг друга

**Пример:**
```python
@dataclass
class ChatUpdateContext:
    session_id: str
    state: ChatSessionState
    sink: ChatUpdateSink
    plan_vm: PlanViewModel | None = None
    event_bus: EventBus | None = None
```

### Decision 4: Callback Executors для FS и Terminal

**Решение:** `FsCallbackExecutor` и `TerminalCallbackExecutor` как отдельные сервисы.

**Обоснование:**
- **SRP** — executors отвечают только за выполнение callbacks
- **Async Safety** — все операции через `asyncio.to_thread`
- **Error Boundaries** — executors ловят исключения и возвращают error результаты
- **Reusability** — executors могут использоваться другими компонентами

**Альтернативы:**
- ❌ **Callbacks в ChatViewModel** — нарушает SRP, сложно тестировать
- ❌ **Handlers в ACPTransportService** — тесная связь с transport
- ❌ **Global callback registry** — сложно управлять lifecycle

**Пример:**
```python
class FsCallbackExecutor:
    def __init__(self, base_path: Path) -> None:
        self._base_path = base_path
    
    async def read_file(self, path: str) -> tuple[str | None, str | None]:
        try:
            content = await asyncio.to_thread(self._read_sync, path)
            return content, None
        except Exception as e:
            return None, str(e)
```

### Decision 5: Client RPC Dispatcher

**Решение:** `ClientRpcDispatcher` + специализированные handlers для каждого RPC метода.

**Обоснование:**
- **SRP** — dispatcher отвечает только за маршрутизацию
- **OCP** — новый RPC метод = новый handler
- **Error Isolation** — dispatcher ловит исключения в handler'ах
- **Logging** — централизованное логирование всех RPC

**Альтернативы:**
- ❌ **If/elif в ACPTransportService** — нарушает OCP, сложно расширять
- ❌ **Dict-based routing** — нет type safety, сложно отлаживать
- ❌ **Chain of Responsibility** — избыточно для фиксированного набора методов

**Пример:**
```python
class RpcHandler(Protocol):
    def can_handle(self, method: str) -> bool: ...
    async def handle(self, rpc_id: str | int, params: dict) -> dict | None: ...

class FsReadHandler:
    def can_handle(self, method: str) -> bool:
        return method == "fs/read_text_file"
    
    async def handle(self, rpc_id: str | int, params: dict) -> dict | None:
        content, error = await self._executor.read_file(params["path"])
        if error:
            return {"error": {"code": -32603, "message": error}}
        return {"content": content}
```

### Decision 6: DI через dishka

**Решение:** Регистрация всех handlers и dispatcher'ов через dishka Provider'ы.

**Обоснование:**
- **Consistency** — единый подход к DI во всём проекте
- **Testability** — легко mock'ать зависимости в тестах
- **Lifecycle Management** — dishka управляет созданием/уничтожением
- **Explicit Dependencies** — все зависимости видны в сигнатурах

**Альтернативы:**
- ❌ **Manual instantiation** — сложно управлять зависимостями
- ❌ **Service Locator** — нарушает DIP, сложно тестировать
- ❌ **Factory Pattern** — избыточно для статической конфигурации

**Пример:**
```python
class ViewModelProvider(Provider):
    @provide(scope=Scope.APP)
    def get_message_chunk_handler(self) -> SessionUpdateHandler:
        return MessageChunkHandler()
    
    @provide(scope=Scope.APP)
    def get_session_update_dispatcher(
        self,
        message_chunk: MessageChunkHandler,
        tool_call: ToolCallHandler,
        plan_update: PlanUpdateHandler,
    ) -> SessionUpdateDispatcher:
        return SessionUpdateDispatcher([message_chunk, tool_call, plan_update])
```

### Decision 7: ChatUpdateSink для синхронизации Observable

**Решение:** `ChatUpdateSink` Protocol абстрагирует обновление Observable свойств.

**Обоснование:**
- **Decoupling** — handlers не знают про Observable, только про sink
- **Testability** — легко mock'ать sink в тестах
- **Flexibility** — sink может обновлять несколько Observable сразу
- **Type Safety** — явные методы для каждого типа обновления

**Альтернативы:**
- ❌ **Прямой доступ к Observable** — handlers зависят от ChatViewModel
- ❌ **EventBus для обновлений** — избыточно для синхронных обновлений
- ❌ **Callback функции** — сложно управлять lifecycle

**Пример:**
```python
class ChatUpdateSink(Protocol):
    def sync_messages(self, session_id: str, messages: list[dict[str, str]]) -> None: ...
    def sync_tool_calls(self, session_id: str, tool_calls: list[dict[str, Any]]) -> None: ...
    def sync_streaming(self, session_id: str, text: str, is_streaming: bool) -> None: ...
```

## Risks / Trade-offs

### Risk 1: Breaking Existing Tests

**Риск:** Существующие тесты `test_presentation_chat_view_model.py` могут сломаться из-за изменения внутренней структуры.

**Митигация:**
- Сохранить публичный API ChatViewModel (методы, Observable свойства)
- Обновить импорты в тестах
- Добавить интеграционные тесты для новой структуры
- Запускать `make check` после каждого шага

### Risk 2: Performance Overhead

**Риск:** Dispatcher добавляет overhead на поиск handler'а.

**Митигация:**
- Линейный поиск по списку handlers (O(n), где n ~ 5-10)
- Overhead незначителен по сравнению с network I/O
- Benchmark до/после для критичных путей

### Risk 3: Circular Dependencies

**Риск:** Handlers могут зависеть от ChatViewModel, создавая циклические зависимости.

**Митигация:**
- Handlers зависят только от ChatUpdateContext и ChatUpdateSink
- ChatViewModel реализует ChatUpdateSink
- DI контейнер разрешает зависимости автоматически

### Risk 4: Error Handling Complexity

**Риск:** Ошибки в handler'ах могут быть проигнорированы или неправильно обработаны.

**Митигация:**
- Dispatcher ловит все исключения и логирует их
- Handlers возвращают результат или выбрасывают исключения
- ChatViewModel проверяет результат и обновляет UI соответственно

### Risk 5: Migration Complexity

**Риск:** Пошаговая миграция может привести к нестабильности.

**Митигация:**
- Создавать новые компоненты параллельно с существующими
- Делегировать из старых классов в новые через adapter pattern
- Удалять старый код только после подтверждения работоспособности
- Feature flags для переключения между старой и новой реализацией (если нужно)

### Trade-off 1: Complexity vs Flexibility

**Компромисс:** Strategy/Dispatcher добавляет сложность (больше файлов, абстракций) ради гибкости (OCP, testability).

**Обоснование:**
- Для промышленной эксплуатации гибкость важнее простоты
- Количество handlers небольшое (~5-10), сложность управляема
- Тестируемость критична для долгосрочной поддержки

### Trade-off 2: Protocol vs ABC

**Компромисс:** Protocol легче ABC, но не предоставляет базовую реализацию.

**Обоснование:**
- Для простых интерфейсов (1-2 метода) Protocol достаточно
- ABC избыточно для Strategy pattern
- Python 3.12+ поддерживает Protocol хорошо

### Trade-off 3: Async Overhead

**Компромисс:** `asyncio.to_thread` добавляет overhead на переключение контекста.

**Обоснование:**
- File I/O операции медленные, overhead незначителен
- Критично для отзывчивости UI (не блокируем event loop)
- Альтернатива (sync I/O) неприемлема для TUI

## Migration Plan

### Phase 1: Foundation (2 часа)

1. Создать `contracts.py` с Protocol интерфейсами
2. Создать `context.py` с ChatUpdateContext
3. Создать `chat_session_state.py` с ChatSessionState
4. Написать тесты для контрактов

### Phase 2: Persistence (3 часа)

1. Создать `FileChatPersistence` с async методами
2. Написать тесты для persistence
3. Интегрировать в ChatViewModel через adapter

### Phase 3: Executors (3 часа)

1. Создать `FsCallbackExecutor` с async методами
2. Создать `TerminalCallbackExecutor` с lifecycle management
3. Написать тесты для executors
4. Интегрировать в ChatViewModel через adapter

### Phase 4: Handlers (4 часа)

1. Создать `MessageChunkHandler`
2. Создать `ToolCallHandler`
3. Создать `PlanUpdateHandler`
4. Создать `ConfigOptionHandler`
5. Написать тесты для каждого handler

### Phase 5: Dispatcher (2 часа)

1. Создать `SessionUpdateDispatcher`
2. Написать тесты для dispatcher
3. Интегрировать в ChatViewModel

### Phase 6: Refactor ChatViewModel (3 часа)

1. Удалить старый код из ChatViewModel
2. Делегировать в новые компоненты
3. Обновить DI контейнер
4. Запустить `make check`

### Phase 7: ACPTransportService (4 часа)

1. Создать `ClientRpcDispatcher`
2. Создать RPC handlers
3. Создать `RequestExecutor`
4. Рефакторить ACPTransportService
5. Обновить DI контейнер
6. Запустить `make check`

### Phase 8: Integration Tests (2 часа)

1. Интеграционные тесты для ChatViewModel
2. Интеграционные тесты для ACPTransportService
3. End-to-end тесты для полного flow

**Total:** ~23 часа

## Open Questions

### Question 1: Error Recovery Strategy

**Вопрос:** Как обрабатывать критические ошибки в handler'ах?

**Варианты:**
- A) Логировать и продолжать (текущий подход)
- B) Логировать и уведомлять пользователя через UI
- C) Логировать и отправлять error event через EventBus

**Решение:** Комбинация A + B — логировать + показывать toast в UI для критических ошибок.

### Question 2: Persistence Error Handling

**Вопрос:** Что делать, если persistence недоступен (диск полный, permission denied)?

**Варианты:**
- A) Логировать и продолжать (потеря истории)
- B) Логировать и блокировать UI (показать ошибку)
- C) Логировать и переключать на in-memory persistence

**Решение:** Комбинация A + C — логировать + переключать на in-memory с предупреждением.

### Question 3: Terminal State Management

**Вопрос:** Как управлять состоянием terminal при reconnect?

**Варианты:**
- A) Очистить все terminal states при reconnect
- B) Сохранить terminal states и восстановить при reconnect
- C) Пометить terminal states как stale и пересоздать при необходимости

**Решение:** Вариант C — помечать как stale, пересоздавать при необходимости.

### Question 4: Handler Priority

**Вопрос:** Что делать, если несколько handlers могут обработать один update_type?

**Варианты:**
- A) Использовать первый найденный handler
- B) Использовать все найденные handlers (chain)
- C) Выбросить ошибку (конфликт конфигурации)

**Решение:** Вариант A — использовать первый найденный. Handlers регистрируются в порядке приоритета.

### Question 5: Testing Strategy

**Вопрос:** Как тестировать dispatcher с множеством handlers?

**Варианты:**
- A) Тестировать каждый handler изолированно + dispatcher с mock handlers
- B) Тестировать dispatcher с реальными handlers (интеграционные тесты)
- C) Комбинация A + B

**Решение:** Вариант C — unit тесты для handlers + интеграционные тесты для dispatcher.
