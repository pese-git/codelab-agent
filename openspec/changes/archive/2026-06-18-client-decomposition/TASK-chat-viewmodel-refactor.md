# Задача: Рефакторинг ChatViewModel

**Приоритет:** Высокий  
**Оценка:** 8-10 часов  
**Зависимости:** Группы 1-5 завершены (компоненты готовы к интеграции)

---

## Контекст

`ChatViewModel` (1244 строки) — монолитный класс с 11 ответственностями:

1. Управление сообщениями
2. Управление tool calls
3. Streaming text
4. Permissions
5. File System operations
6. Terminal operations
7. Persistence (file I/O)
8. Session state management
9. Replay updates
10. Event handlers
11. Plan updates

Все новые компоненты для декомпозиции уже созданы в Группах 1-5:
- `SessionUpdateDispatcher` — маршрутизация обновлений
- `ChatPersistencePort` + `FileChatPersistence` — сохранение истории
- `FsCallbackExecutor` — async-safe FS операции
- `TerminalCallbackExecutor` — управление терминалами
- `MessageChunkHandler`, `ToolCallHandler`, `PlanUpdateHandler`, `ConfigOptionHandler` — обработчики

---

## Цель

Рефакторить `ChatViewModel` для делегирования ответственностей новым компонентам, сохраняя обратную совместимость.

---

## План реализации

### Шаг 1: Добавить новые зависимости в конструктор

```python
def __init__(
    self,
    coordinator: Any,
    event_bus: Any | None = None,
    logger: Any | None = None,
    history_dir: Path | str | None = None,
    fs_executor: Any | None = None,
    terminal_executor: Any | None = None,
    plan_vm: Any | None = None,
    # Новые компоненты (опциональные для обратной совместимости)
    session_update_dispatcher: SessionUpdateDispatcher | None = None,
    chat_persistence: ChatPersistencePort | None = None,
    fs_callback_executor: FsCallbackExecutor | None = None,
    terminal_callback_executor: TerminalCallbackExecutor | None = None,
) -> None:
```

### Шаг 2: Реализовать ChatUpdateSink

`ChatViewModel` должен реализовать интерфейс `ChatUpdateSink` для интеграции с handler'ами:

```python
def sync_messages(self, session_id: str, messages: list[dict[str, str]]) -> None:
    if self._active_session_id == session_id:
        self.messages.value = list(messages)

def sync_tool_calls(self, session_id: str, tool_calls: list[dict[str, Any]]) -> None:
    if self._active_session_id == session_id:
        self.tool_calls.value = list(tool_calls)

def sync_streaming(self, session_id: str, text: str, is_streaming: bool) -> None:
    if self._active_session_id == session_id:
        self.streaming_text.value = text
        self.is_streaming.value = is_streaming
```

### Шаг 3: Заменить `_handle_session_update` на делегирование dispatcher'у

```python
def _handle_session_update(self, update_data: dict[str, Any]) -> None:
    if self._session_update_dispatcher is not None:
        # Новый путь: через dispatcher
        self._handle_session_update_dispatched(update_data)
    else:
        # Старый путь: обратная совместимость
        self._handle_session_update_legacy(update_data)
```

### Шаг 4: Заменить file I/O на `ChatPersistencePort`

Заменить `_persist_messages_to_local_storage`, `_load_messages_from_local_storage`, `_load_replay_updates_from_local_storage` на делегирование `chat_persistence`.

### Шаг 5: Заменить FS callbacks на `FsCallbackExecutor`

Заменить `_handle_fs_read`, `_handle_fs_write` на делегирование `fs_callback_executor`.

### Шаг 6: Заменить terminal callbacks на `TerminalCallbackExecutor`

Заменить вложенные функции `_on_terminal_create`, `_on_terminal_output`, etc. на делегирование `terminal_callback_executor`.

### Шаг 7: Удалить устаревший код

После подтверждения работоспособности:
- Удалить `_handle_session_update_legacy` (если dispatcher всегда доступен)
- Удалить старые методы persistence
- Удалить старые FS/terminal handlers

---

## Критические моменты

### 1. Обратная совместимость

Новые зависимости должны быть опциональными. Если dispatcher/persistence/executors не предоставлены, ChatViewModel должен работать как раньше.

### 2. Конфликт типов ChatSessionState

В `chat_view_model.py` есть свой `ChatSessionState` (dataclass). В новых компонентах есть другой `ChatSessionState` из `chat/chat_session_state.py`. Нужно:
- Унифицировать на один класс из `chat/chat_session_state.py`
- Обновить все ссылки

### 3. Observable синхронизация

Handler'ы модифицируют `ChatSessionState`, но Observable свойства (`messages`, `tool_calls`, etc.) должны обновляться через `ChatUpdateSink`. Нужно убедиться что синхронизация работает корректно.

### 4. Event loop в persistence

`ChatPersistencePort` методы async. Вызов из sync контекста требует `asyncio.create_task()` или `asyncio.ensure_future()`.

---

## Тестирование

1. **Unit тесты** для новых методов (`sync_messages`, `sync_tool_calls`, etc.)
2. **Интеграционные тесты** для dispatcher → handler → sink flow
3. **Regression тесты** — все существующие тесты `test_presentation_chat_view_model.py` должны проходить
4. **Тесты обратной совместимости** — ChatViewModel без новых зависимостей должен работать

---

## Обновление DI контейнера

После рефакторинга обновить `ViewModelProvider`:

```python
@provide(scope=Scope.APP)
def get_chat_vm(
    self,
    coordinator: SessionCoordinator,
    event_bus: EventBus,
    config: ClientConfig,
    logger: structlog.stdlib.BoundLogger,
    plan_vm: PlanViewModel,
    fs_executor: FileSystemExecutor,
    terminal_executor: TerminalExecutor,
    dispatcher: SessionUpdateDispatcher,
    persistence: ChatPersistencePort,
    fs_callback_executor: FsCallbackExecutor,
    terminal_callback_executor: TerminalCallbackExecutor,
) -> ChatViewModel:
    return ChatViewModel(
        coordinator=coordinator,
        event_bus=event_bus,
        logger=logger,
        history_dir=config.history_dir,
        fs_executor=fs_executor,
        terminal_executor=terminal_executor,
        plan_vm=plan_vm,
        session_update_dispatcher=dispatcher,
        chat_persistence=persistence,
        fs_callback_executor=fs_callback_executor,
        terminal_callback_executor=terminal_callback_executor,
    )
```

---

## Acceptance Criteria

- [ ] ChatViewModel принимает новые опциональные зависимости
- [ ] ChatViewModel реализует ChatUpdateSink
- [ ] `_handle_session_update` делегирует dispatcher'у когда доступен
- [ ] Persistence делегируется `ChatPersistencePort`
- [ ] FS callbacks делегируются `FsCallbackExecutor`
- [ ] Terminal callbacks делегируются `TerminalCallbackExecutor`
- [ ] Все существующие тесты проходят
- [ ] Новые тесты для интеграции с компонентами
- [ ] `make check` проходит (ruff, ty, pytest)

---

## Связанные коммиты

- `6e06929` — Группы 1-2 (contracts, context, state, persistence)
- `6940252` — Группа 3 (executors)
- `2357d44` — Группа 4 (handlers)
- `d5b7e66` — Группа 5 (dispatcher)
