# Spec: strategy-selector-ui

## ДОБАВЛЕННЫЕ Требования

### Требование: StrategySelectorViewModel

Клиент ДОЛЖЕН предоставлять `StrategySelectorViewModel` для управления выбором стратегии выполнения:

```python
class StrategySelectorViewModel(BaseViewModel):
    available_strategies: Observable[list[StrategyOption]]
    current_strategy: Observable[str | None]
    is_loading: Observable[bool]
    error_message: Observable[str | None]
    is_modal_open: Observable[bool]
    
    def update_strategies_from_config(config_options, session_id) -> None: ...
    async def _select_strategy(session_id, strategy_value) -> None: ...
```

**Observable свойства:**
- `available_strategies`: список доступных стратегий для выбора
- `current_strategy`: текущая выбранная стратегия
- `is_loading`: флаг загрузки (во время set_config_option)
- `error_message`: последняя ошибка (если была)
- `is_modal_open`: флаг открытия модального окна

**Методы:**
- `update_strategies_from_config(config_options, session_id)`: обновить список стратегий из configOptions
- `_select_strategy(session_id, strategy_value)`: отправить запрос на смену стратегии через coordinator

### Требование: StrategyOption

Клиент ДОЛЖЕН предоставлять `StrategyOption` dataclass для представления опции стратегии:

```python
@dataclass
class StrategyOption:
    value: str        # "single", "hierarchical", etc.
    label: str        # "Single", "Hierarchical", etc.
    description: str  # "Single agent execution", etc.
```

**Поля:**
- `value`: уникальное значение стратегии (используется для set_config_option)
- `label`: отображаемое имя стратегии
- `description`: описание стратегии для UI

### Требование: Обновление из configOptions

StrategySelectorViewModel ДОЛЖЕН обновлять список стратегий из configOptions:

```python
def update_strategies_from_config(
    self,
    config_options: list[dict[str, Any]],
    session_id: str | None = None,
) -> None:
    """Обновить список стратегий из configOptions.
    
    Ищет option с id="_active_strategy".
    """
    # 1. Найти option с id="_active_strategy"
    # 2. Извлечь currentValue или default
    # 3. Извлечь options (список стратегий)
    # 4. Распарсить в StrategyOption
    # 5. Обновить available_strategies и current_strategy
```

**Логика:**
1. Найти option с `id="_active_strategy"` в configOptions
2. Извлечь `currentValue` или `default` как текущую стратегию
3. Извлечь `options` (список стратегий)
4. Распарсить каждый option в `StrategyOption`
5. Обновить `available_strategies` и `current_strategy`

### Требование: Отправка set_config_option

StrategySelectorViewModel ДОЛЖЕН отправлять запрос на смену стратегии через coordinator:

```python
async def _select_strategy(self, session_id: str, strategy_value: str) -> None:
    """Отправить запрос на смену стратегии."""
    self.is_loading.value = True
    try:
        result = await self.coordinator.set_config_option(
            session_id, "_active_strategy", strategy_value
        )
        if result and "configOptions" in result:
            self.update_strategies_from_config(result["configOptions"], session_id)
        self.current_strategy.value = strategy_value
    except Exception as e:
        self.error_message.value = str(e)
    finally:
        self.is_loading.value = False
```

**Логика:**
1. Установить `is_loading = True`
2. Вызвать `coordinator.set_config_option(session_id, "_active_strategy", strategy_value)`
3. Если ответ содержит `configOptions`, обновить ViewModel
4. Обновить `current_strategy`
5. При ошибке — сохранить в `error_message`
6. Установить `is_loading = False`

### Требование: StrategySelectorModal

Клиент ДОЛЖЕН предоставлять `StrategySelectorModal` — модальное окно для выбора стратегии:

```python
class StrategySelectorModal(ModalScreen[str | None]):
    BINDINGS = [
        ("escape", "close", "Закрыть"),
        ("up", "previous", "Предыдущая"),
        ("down", "next", "Следующая"),
        ("enter", "select", "Выбрать"),
    ]
    
    def compose(self) -> ComposeResult: ...
    def action_select(self) -> None: ...
    def action_previous(self) -> None: ...
    def action_next(self) -> None: ...
```

**BINDINGS:**
- `Escape`: закрыть modal
- `↑`: предыдущая стратегия
- `↓`: следующая стратегия
- `Enter`: выбрать текущую стратегию

**Компоненты:**
- Заголовок: "Выбор стратегии"
- Текущая стратегия: отображается зеленым цветом
- Список стратегий: с навигацией и выделением текущей
- Подсказка: "↑↓ навигация | Enter выбрать | Esc закрыть"

### Требование: StrategyItem

Клиент ДОЛЖЕН предоставлять `StrategyItem` — элемент списка стратегий:

```python
class StrategyItem(Static):
    class Selected(Message):
        def __init__(self, strategy: StrategyOption) -> None: ...
    
    def compose(self) -> ComposeResult: ...
    def on_click(self) -> None: ...
```

**Компоненты:**
- Название стратегии (жирным)
- Описание стратегии (курсивом)
- Маркер текущей стратегии (зеленая полоска слева)
- Выделение при наведении/выборе

**События:**
- `Selected`: публикуется при клике на элемент

### Требование: Hotkey для открытия

TUI ДОЛЖНО поддерживать hotkey для открытия `StrategySelectorModal`:

```python
BINDINGS = [
    # ... существующие ...
    ("ctrl+s", "open_strategy_selector", "Strategy"),
]

async def action_open_strategy_selector(self) -> None:
    """Открыть модальное окно выбора стратегии."""
    session_id = self._session_vm.current_session_id.value
    if session_id:
        modal = StrategySelectorModal(self._strategy_selector_vm, session_id)
        result = await self.push_screen_wait(modal)
        if result:
            await self._strategy_selector_vm.select_strategy_cmd.execute(
                session_id, result
            )
```

**Hotkey:** `Ctrl+S`

**Логика:**
1. Проверить что активна сессия
2. Создать `StrategySelectorModal` с ViewModel и session_id
3. Открыть modal и ждать результат
4. Если пользователь выбрал стратегию, выполнить `select_strategy_cmd`

### Требование: Интеграция с config_option_update

Клиент ДОЛЖЕН обновлять StrategySelectorViewModel при получении `config_option_update`:

```python
def _on_config_option_updated(self, event: ConfigOptionUpdatedEvent) -> None:
    """Обновить StrategySelectorViewModel новыми данными."""
    if event.config_options:
        self._strategy_selector_vm.update_strategies_from_config(
            event.config_options,
            event.session_id,
        )
```

**Логика:**
1. Подписаться на событие `config_option_updated` в `on_mount()`
2. При получении события вызвать `update_strategies_from_config()`
3. Передать `config_options` и `session_id` из события

### Требование: Инициализация ViewModel

TUI App ДОЛЖНА инициализировать `StrategySelectorViewModel` при старте:

```python
def __init__(self, ...):
    # Создать StrategySelectorViewModel
    self._strategy_selector_vm = StrategySelectorViewModel(
        coordinator=self._session_coordinator,
        event_bus=self._event_bus,
    )
```

**Зависимости:**
- `coordinator`: SessionCoordinator для работы с сервером
- `event_bus`: EventBus для публикации/подписки на события

# Spec: strategy-selector-view-model

## ДОБАВЛЕННЫЕ Требования

### Требование: Парсинг StrategyOption

StrategySelectorViewModel ДОЛЖЕН парсить raw options в StrategyOption:

```python
def _parse_strategy_options(
    self,
    raw_options: list[dict[str, Any]],
) -> list[StrategyOption]:
    """Парсить raw options в StrategyOption."""
    strategies = []
    for opt in raw_options:
        strategies.append(
            StrategyOption(
                value=opt.get("value", ""),
                label=opt.get("name", opt.get("value", "")),
                description=opt.get("description", ""),
            )
        )
    return strategies
```

**Логика:**
- Извлечь `value` из option
- Извлечь `name` как `label` (fallback на `value`)
- Извлечь `description` (по умолчанию пустая строка)

### Требование: Кэширование configOptions

StrategySelectorViewModel ДОЛЖЕН кэшировать configOptions по session_id:

```python
def update_strategies_from_config(
    self,
    config_options: list[dict[str, Any]],
    session_id: str | None = None,
) -> None:
    if session_id:
        self._config_cache[session_id] = {
            opt["id"]: opt for opt in config_options if "id" in opt
        }
```

**Логика:**
- Если передан `session_id`, сохранить все configOptions в кэш
- Кэш представляет собой dict: `session_id → {config_id → config_option}`

# Spec: strategy-selector-modal

## ДОБАВЛЕННЫЕ Требования

### Требование: Отображение списка стратегий

StrategySelectorModal ДОЛЖЕН отображать список стратегий из ViewModel:

```python
def compose(self) -> ComposeResult:
    with Container():
        yield Static("Выбор стратегии", classes="modal-title")
        
        current = self._view_model.current_strategy.value
        if current:
            yield Static(f"Текущая: {current}", classes="current-strategy")
        
        with VerticalScroll(classes="strategies-scroll"):
            strategies = self._view_model.available_strategies.value
            for i, strategy in enumerate(strategies):
                yield StrategyItem(
                    strategy,
                    selected=(i == self._selected_index),
                    is_current=(strategy.value == current),
                )
        
        yield Static("↑↓ навигация | Enter выбрать | Esc закрыть", classes="hint")
```

**Компоненты:**
- Заголовок: "Выбор стратегии"
- Текущая стратегия: отображается если есть
- Список стратегий: VerticalScroll с StrategyItem
- Подсказка: горячие клавиши

### Требование: Навигация по списку

StrategySelectorModal ДОЛЖЕН поддерживать навигацию по списку стратегий:

```python
def action_previous(self) -> None:
    """Предыдущая стратегия."""
    if self._selected_index > 0:
        self._selected_index -= 1
        self.query_one(".strategies-scroll").refresh()

def action_next(self) -> None:
    """Следующая стратегия."""
    strategies = self._view_model.available_strategies.value
    if self._selected_index < len(strategies) - 1:
        self._selected_index += 1
        self.query_one(".strategies-scroll").refresh()
```

**Логика:**
- `action_previous`: уменьшить `_selected_index` если > 0
- `action_next`: увеличить `_selected_index` если < len(strategies) - 1
- После изменения — refresh списка

### Требование: Выбор стратегии

StrategySelectorModal ДОЛЖЕН поддерживать выбор стратегии:

```python
def action_select(self) -> None:
    """Выбрать текущую стратегию."""
    strategies = self._view_model.available_strategies.value
    if 0 <= self._selected_index < len(strategies):
        selected = strategies[self._selected_index]
        self.dismiss(selected.value)
```

**Логика:**
- Проверить что `_selected_index` валиден
- Получить выбранную стратегию из списка
- Вызвать `dismiss(selected.value)` для закрытия modal и возврата результата

### Требование: Обработка клика

StrategyItem ДОЛЖЕН публиковать событие `Selected` при клике:

```python
def on_click(self) -> None:
    self.post_message(self.Selected(self._strategy))
```

**Логика:**
- При клике на элемент — опубликовать событие `Selected` с данными стратегии
- Modal должен обработать это событие и вызвать `dismiss()`

# Spec: strategy-selector-integration

## ДОБАВЛЕННЫЕ Требования

### Требование: Подписка на config_option_updated

TUI App ДОЛЖНА подписаться на событие `config_option_updated`:

```python
def on_mount(self) -> None:
    self._event_bus.subscribe(
        "config_option_updated",
        self._on_config_option_updated,
    )
```

**Логика:**
- В `on_mount()` подписаться на событие `config_option_updated`
- При получении события — вызвать `_on_config_option_updated()`

### Требание: Обновление ViewModel

TUI App ДОЛЖНА обновлять StrategySelectorViewModel при получении события:

```python
def _on_config_option_updated(self, event: ConfigOptionUpdatedEvent) -> None:
    """Обновить StrategySelectorViewModel новыми данными."""
    if event.config_options:
        self._strategy_selector_vm.update_strategies_from_config(
            event.config_options,
            event.session_id,
        )
```

**Логика:**
- Проверить что `event.config_options` не пуст
- Вызвать `update_strategies_from_config()` с данными из события

### Требование: Открытие modal

TUI App ДОЛЖНА поддерживать открытие StrategySelectorModal через hotkey:

```python
async def action_open_strategy_selector(self) -> None:
    """Открыть модальное окно выбора стратегии."""
    session_id = self._session_vm.current_session_id.value
    if session_id:
        modal = StrategySelectorModal(
            self._strategy_selector_vm,
            session_id,
        )
        result = await self.push_screen_wait(modal)
        if result:
            await self._strategy_selector_vm.select_strategy_cmd.execute(
                session_id, result
            )
```

**Логика:**
- Проверить что активна сессия
- Создать StrategySelectorModal с ViewModel и session_id
- Открыть modal и ждать результат
- Если пользователь выбрал стратегию, выполнить select_strategy_cmd

### Требование: Hotkey Ctrl+S

TUI App ДОЛЖНА поддерживать hotkey `Ctrl+S` для открытия StrategySelectorModal:

```python
BINDINGS = [
    # ... существующие ...
    ("ctrl+s", "open_strategy_selector", "Strategy"),
]
```

**Hotkey:** `Ctrl+S`

**Описание:** "Strategy" (отображается в footer)
