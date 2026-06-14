# Spec: strategy-registry

## ДОБАВЛЕННЫЕ Требования

### Требование: StrategyDescriptor

Система ДОЛЖНА предоставлять `StrategyDescriptor` — self-describing стратегию выполнения:

```python
@dataclass
class StrategyDescriptor:
    name: str                    # Уникальный идентификатор ("single", "hierarchical", etc.)
    display_name: str            # Отображаемое имя для UI ("Single", "Hierarchical", etc.)
    description: str             # Описание для UI ("Single agent execution", etc.)
    factory: Callable            # Функция создания экземпляра стратегии
    validator: Callable          # Функция проверки доступности через AgentRegistry
```

**Поля:**
- `name`: уникальный идентификатор стратегии (например, "single", "multi_orchestrated", "hierarchical")
- `display_name`: отображаемое имя для UI (например, "Single", "Multi-Orchestrated")
- `description`: описание стратегии для UI (например, "Single agent execution via EventBus")
- `factory`: Callable[[StrategyDependencies], LLMCallStrategy] — создает экземпляр стратегии
- `validator`: Callable[[AgentRegistry], bool] — проверяет доступность стратегии

### Требование: StrategyDependencies

Система ДОЛЖНА предоставлять `StrategyDependencies` — контейнер зависимостей для DI:

```python
@dataclass
class StrategyDependencies:
    event_bus: AgentEventBus
    execution_engine: ExecutionEngine
    tracer: Tracer | None = None
    agent_name: str = "primary"
```

**Поля:**
- `event_bus`: шина событий для вызова агентов
- `execution_engine`: движок выполнения для сборки контекста
- `tracer`: tracer для observability (опционально)
- `agent_name`: имя агента по умолчанию

### Требование: StrategyRegistry

Система ДОЛЖНА предоставлять `StrategyRegistry` — единый источник истины о доступных стратегиях:

```python
class StrategyRegistry:
    def register(self, descriptor: StrategyDescriptor) -> None:
        """Зарегистрировать стратегию."""
    
    def get(self, name: str) -> StrategyDescriptor | None:
        """Получить descriptor по имени."""
    
    def get_available(self, agent_registry: AgentRegistry) -> list[StrategyDescriptor]:
        """Получить список доступных стратегий (validator возвращает True)."""
    
    def create_instance(self, name: str, deps: StrategyDependencies) -> LLMCallStrategy | None:
        """Создать экземпляр стратегии через factory."""
    
    def list_all(self) -> list[StrategyDescriptor]:
        """Получить все зарегистрированные стратегии."""
```

**Методы:**
- `register(descriptor)`: зарегистрировать стратегию в реестре
- `get(name)`: получить descriptor по имени (None если не найдена)
- `get_available(agent_registry)`: получить список стратегий, доступных для выполнения (validator возвращает True)
- `create_instance(name, deps)`: создать экземпляр стратегии через factory (None если не найдена)
- `list_all()`: получить все зарегистрированные стратегии

### Требование: SingleStrategy Descriptor

SingleStrategy ДОЛЖНА предоставлять `SINGLE_STRATEGY_DESCRIPTOR`:

```python
SINGLE_STRATEGY_DESCRIPTOR = StrategyDescriptor(
    name="single",
    display_name="Single",
    description="Single agent execution via EventBus",
    factory=lambda deps: SingleStrategy(
        event_bus=deps.event_bus,
        execution_engine=deps.execution_engine,
        tracer=deps.tracer,
        agent_name=deps.agent_name,
    ),
    validator=lambda registry: True,  # всегда доступна
)
```

**Характеристики:**
- `name`: "single"
- `display_name`: "Single"
- `description`: "Single agent execution via EventBus"
- `validator`: всегда возвращает True (single всегда доступна)

### Требование: Регистрация стратегий при старте

Система ДОЛЖНА регистрировать все доступные стратегии при старте через DI:

```python
@provide(scope=Scope.APP)
def get_strategy_registry(self) -> StrategyRegistry:
    registry = StrategyRegistry()
    registry.register(SINGLE_STRATEGY_DESCRIPTOR)
    # Будущее: registry.register(ORCHESTRATED_STRATEGY_DESCRIPTOR)
    return registry
```

### Требование: Динамическое формирование configOptions

ACPProtocol ДОЛЖЕН формировать configOptions для `_active_strategy` динамически:

```python
def _build_active_strategy_config_spec(self) -> dict[str, Any]:
    available = self._strategy_registry.get_available(self._agent_registry)
    options = [
        {
            "value": desc.name,
            "name": desc.display_name,
            "description": desc.description,
        }
        for desc in available
    ]
    return {
        "id": "_active_strategy",
        "name": "Strategy",
        "category": "strategy",
        "type": "select",
        "default": current,
        "options": options,
    }
```

**Характеристики:**
- Использует `StrategyRegistry.get_available(agent_registry)` для получения доступных стратегий
- Включает ТОЛЬКО доступные стратегии в configOptions
- Использует `display_name` и `description` из `StrategyDescriptor`
- Обновляется при изменении AgentRegistry (hot reload)

### Требование: Валидация через Registry

StrategyDispatcher ДОЛЖЕН валидировать доступность стратегии через Registry:

```python
def select_strategy(self, session, context_meta) -> tuple[str, str | None]:
    available = self._strategy_registry.get_available(self._agent_registry)
    available_names = [d.name for d in available]
    
    if requested in available_names:
        return requested, None
    
    # Fallback
    return fallback, requested
```

### Требование: Создание экземпляра через Registry

StrategyDispatcher ДОЛЖЕН создавать экземпляр стратегии через Registry:

```python
def get_current_strategy(self) -> LLMCallStrategy | None:
    return self._strategy_registry.create_instance(
        self._current_strategy_name,
        self._deps,
    )
```

# Spec: strategy-validation

## ДОБАВЛЕННЫЕ Требования

### Требование: Проверка совместимости mode

StrategyRegistry ДОЛЖЕН валидировать совместимость mode + стратегии через `validator` в `StrategyDescriptor`:

```python
def _validate_strategy(mode: str, registry: AgentRegistry) -> bool:
    """Проверить доступность стратегии. Вернуть True если доступна."""
```

### Требование: Правила валидации

Валидация ДОЛЖНА следовать этим правилам:
- Single: всегда проходит (validator возвращает True)
- Orchestrated: has_orchestrator И has_subagent
- Choreography: len(subagents) >= 2
- Hierarchical: has_primary И has_subagent
- Unknown mode: возвращается False (недоступна)

### Требование: Validator в StrategyDescriptor

Каждая стратегия ДОЛЖНА предоставлять `validator` в `StrategyDescriptor`:

```python
validator=lambda registry: (
    registry.get_orchestrator() is not None and
    len(registry.get_subagents()) > 0
)
```

**Характеристики:**
- Принимает `AgentRegistry` как параметр
- Возвращает `True` если стратегия доступна
- Возвращает `False` если стратегия недоступна
- Использует методы Registry для проверки наличия агентов
