# План реализации: Динамический выбор стратегии и агентов

## Обзор

Реализация архитектурно правильного разделения ответственности:
- **Execution Strategy** — server-side config (TOML/CLI/ENV), override через `/strategy`
- **Permission Mode** — ACP standard config option (`mode`)
- **Agent Selection** — custom config option (`_agent`) с динамическим списком из Registry

## Архитектурные решения (подтверждено)

| Концепция | Уровень | Источник | ACP Config Option | Slash Override |
|-----------|---------|----------|-------------------|----------------|
| **Execution Strategy** | Server | TOML/CLI/ENV | ❌ Нет | ✅ `/strategy` |
| **Permission Mode** | Session | ACP configOption | ✅ `mode` | ✅ `/mode` |
| **Agent Selection** | Session | ACP configOption | ✅ `_agent` | ❌ Нет |

## Миграция ACP

- Мигрировать с legacy `modes` API на `configOptions`
- Сохранить обратную совместимость (отправлять оба для старых клиентов)

---

## Задачи

### 1. Переименовать `AgentsConfig.mode` → `AgentsConfig.strategy`

**Файл:** `codelab/src/codelab/server/config.py`

**Изменения:**
```python
class AgentsConfig(BaseModel):
    """Конфигурация мультиагентной системы."""
    
    strategy: str = "single"  # вместо mode
    fallback_strategy: str = "single"  # вместо fallback_mode
    default_model: str = "openai/gpt-4o"
    max_steps: int = 7
```

**Обновить:**
- Все ссылки на `agents.mode` → `agents.strategy`
- Все ссылки на `agents.fallback_mode` → `agents.fallback_strategy`
- TOML конфигурацию (breaking change — документировать)

---

### 2. Обновить ACPProtocol — configOptions вместо modes

**Файл:** `codelab/src/codelab/server/protocol/core.py`

**Изменения:**

```python
class ACPProtocol:
    def __init__(
        self,
        # ... существующие параметры
        agent_registry: AgentRegistry | None = None,
    ) -> None:
        self._agent_registry = agent_registry
        # ... остальное
    
    def _build_config_specs(self) -> dict[str, dict[str, Any]]:
        """Построить config specs с mode и _agent."""
        # mode — ACP standard (permission behavior)
        mode_spec = {
            "id": "mode",
            "name": "Session Mode",
            "description": "Controls how the agent requests permission",
            "category": "mode",
            "type": "select",
            "default": "ask",
            "options": [
                {"value": "ask", "name": "Ask", "description": "Request permission before changes"},
                {"value": "code", "name": "Code", "description": "Execute without confirmation"}
            ]
        }
        
        # _agent — custom category (agent selection)
        agent_spec = self._build_agent_config_spec()
        
        # model — из config_option_builder
        if self._config_option_builder:
            default_model = self._get_default_model()
            return self._config_option_builder.build_config_specs(
                default_model=default_model,
                additional_specs={
                    "mode": mode_spec,
                    "_agent": agent_spec,
                },
            )
        return {"mode": mode_spec, "_agent": agent_spec}
    
    def _build_agent_config_spec(self) -> dict[str, Any]:
        """Построить config spec для _agent из AgentRegistry."""
        if not self._agent_registry or not self._agent_registry.is_initialized:
            return {
                "id": "_agent",
                "name": "Agent",
                "category": "_agent",
                "type": "select",
                "default": "primary",
                "options": [{"value": "primary", "name": "Primary", "description": "Default agent"}]
            }
        
        # Получаем primary agents из Registry
        primary_agents = self._agent_registry.get_primary_agents()
        
        # Сортируем по priority
        sorted_agents = sorted(primary_agents.values(), key=lambda a: a.priority)
        
        options = []
        for agent in sorted_agents:
            options.append({
                "value": agent.name,
                "name": agent.name.capitalize(),
                "description": f"{agent.model} (priority: {agent.priority})",
            })
        
        default_agent = sorted_agents[0].name if sorted_agents else "primary"
        
        return {
            "id": "_agent",
            "name": "Agent",
            "category": "_agent",
            "type": "select",
            "default": default_agent,
            "options": options,
        }
```

**Обновить session/new response:**
- Отправлять `configOptions` с `mode` и `_agent`
- Отправлять `modes` для обратной совместимости (legacy)

---

### 3. Обновить StrategyDispatcher

**Файл:** `codelab/src/codelab/server/agent/strategies/dispatcher.py`

**Изменения:**

```python
class StrategyDispatcher:
    def __init__(
        self,
        event_bus: AgentEventBus,
        execution_engine: ExecutionEngine,
        agent_registry: AgentRegistry,  # ← новый параметр
        tracer: Tracer | None = None,
        strategy: str = "single",  # ← из AgentsConfig.strategy
    ) -> None:
        self._event_bus = event_bus
        self._execution_engine = execution_engine
        self._agent_registry = agent_registry
        self._tracer = tracer
        self._strategy_name = strategy  # "single", "multi_orchestrated", etc.
        self._strategies: dict[str, Any] = {}
        
        # Регистрируем SingleStrategy (единственная реализованная)
        from codelab.server.protocol.handlers.strategies.single_strategy import SingleStrategy
        self._strategies["single"] = SingleStrategy(
            event_bus=event_bus,
            execution_engine=execution_engine,
            tracer=tracer,
            agent_name="primary",  # default, будет переопределён
        )
    
    async def execute(
        self,
        session: SessionState,
        prompt: str,
        system_prompt: str | None = None,
        mcp_manager: Any | None = None,
        parent_span: SpanContext | None = None,
    ) -> AgentResponse:
        """Выполнить стратегию."""
        # 1. Получаем strategy из server config
        strategy = self._strategies.get(self._strategy_name)
        if strategy is None:
            raise ValueError(f"Unknown strategy: {self._strategy_name}")
        
        # 2. Получаем agent_name из session config
        agent_name = session.config_values.get("_agent", "primary")
        
        # 3. Проверяем наличие в Registry
        agent = self._agent_registry.get(agent_name)
        if agent is None:
            raise ValueError(
                f"Agent '{agent_name}' not found in registry. "
                f"Available: {list(self._agent_registry.get_all().keys())}"
            )
        
        # 4. Выполняем с правильным agent_name
        return await strategy.execute(
            session=session,
            prompt=prompt,
            system_prompt=system_prompt,
            mcp_manager=mcp_manager,
            parent_span=parent_span,
            agent_name=agent_name,  # ← передаём agent_name
        )
    
    def set_strategy(self, strategy_name: str) -> None:
        """Runtime override стратегии (для /strategy slash command)."""
        if strategy_name not in self._strategies:
            raise ValueError(f"Unknown strategy: {strategy_name}")
        self._strategy_name = strategy_name
```

---

### 4. Обновить SingleStrategy

**Файл:** `codelab/src/codelab/server/protocol/handlers/strategies/single_strategy.py`

**Изменения:**

```python
class SingleStrategy:
    async def execute(
        self,
        session: SessionState,
        prompt: str,
        system_prompt: str | None = None,
        mcp_manager: Any | None = None,
        parent_span: SpanContext | None = None,
        agent_name: str | None = None,  # ← новый параметр
    ) -> BaseAgentResponse:
        target_agent = agent_name or self.agent_name
        
        # ... остальной код, но используем target_agent
        request = AgentRequest(
            target_agent=target_agent,  # ← используем target_agent
            # ...
        )
        
        # Tracing
        if span and self.tracer:
            self.tracer.end_span(
                span,
                attributes={
                    "agent_name": target_agent,  # ← используем target_agent
                    # ...
                },
            )
    
    async def continue_execution(
        self,
        session: SessionState,
        mcp_manager: Any | None = None,
        parent_span: SpanContext | None = None,
        agent_name: str | None = None,  # ← новый параметр
    ) -> BaseAgentResponse:
        target_agent = agent_name or self.agent_name
        # ... аналогично execute()
```

---

### 5. Обновить DI провайдеры

**Файл:** `codelab/src/codelab/server/di.py`

**Изменения:**

```python
class MultiAgentProvider(Provider):
    @provide(scope=Scope.APP)
    def get_strategy_dispatcher(
        self,
        config: Annotated[AppConfig, from_context(provides=AppConfig)],
        event_bus: AgentEventBus,
        execution_engine: ExecutionEngine,
        agent_registry: AgentRegistry,  # ← новый параметр
        tracer: Tracer,
    ) -> StrategyDispatcher:
        """Создаёт StrategyDispatcher."""
        return StrategyDispatcher(
            event_bus=event_bus,
            execution_engine=execution_engine,
            agent_registry=agent_registry,  # ← передаём Registry
            tracer=tracer,
            strategy=config.agents.strategy,  # ← из config
        )

class RequestProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_acp_protocol(
        self,
        # ... существующие параметры
        agent_registry: AgentRegistry,  # ← новый параметр
    ) -> ACPProtocol:
        """Создаёт ACPProtocol для текущего соединения."""
        return ACPProtocol(
            # ... существующие параметры
            agent_registry=agent_registry,  # ← передаём Registry
        )
```

---

### 6. Обновить LLMLoopStage

**Файл:** `codelab/src/codelab/server/protocol/handlers/pipeline/stages/llm_loop.py`

**Изменения:**

```python
class LLMLoopStage(PromptStage):
    def __init__(
        self,
        # ... существующие параметры
        strategy: str = "single",  # ← вместо use_event_bus
    ) -> None:
        # ...
        self._strategy = strategy
        
        # Логирование
        logger.info(
            "LLMLoopStage initialized",
            strategy=strategy,
            tracer_enabled=tracer is not None,
        )
    
    async def process(self, context: PromptContext) -> PromptContext:
        # Используем strategy из server config
        if self._strategy_dispatcher is not None:
            return await self._process_via_event_bus(context)
        
        # Legacy путь (если strategy_dispatcher не настроен)
        # ...
```

---

### 7. Добавить slash command `/strategy`

**Файл:** `codelab/src/codelab/server/protocol/handlers/slash_commands/builtin/strategy.py` (новый файл)

```python
"""Handler для команды /strategy."""

from __future__ import annotations

from typing import TYPE_CHECKING

from codelab.server.models import AvailableCommand, AvailableCommandInput

from ..base import CommandHandler, CommandResult

if TYPE_CHECKING:
    from codelab.server.protocol.state import SessionState

AVAILABLE_STRATEGIES = ["single", "multi_orchestrated", "hierarchical"]


class StrategyCommandHandler(CommandHandler):
    """Handler для команды /strategy.
    
    Показывает или изменяет execution strategy.
    """
    
    def __init__(self, strategy_dispatcher: StrategyDispatcher) -> None:
        self._strategy_dispatcher = strategy_dispatcher
    
    def execute(
        self,
        args: list[str],
        session: SessionState,
    ) -> CommandResult:
        """Выполняет команду /strategy."""
        current_strategy = self._strategy_dispatcher._strategy_name
        
        if not args:
            # Показать текущую strategy
            lines = [
                f"🎯 **Текущая strategy:** `{current_strategy}`",
                "",
                "**Доступные strategies:**",
            ]
            for strategy in AVAILABLE_STRATEGIES:
                marker = "→" if strategy == current_strategy else " "
                lines.append(f" {marker} `{strategy}`")
            
            lines.append("")
            lines.append("Для смены: `/strategy <имя>`")
            
            return CommandResult(
                content=[{"type": "text", "text": "\n".join(lines)}]
            )
        
        # Установить новую strategy
        new_strategy = args[0].lower()
        
        if new_strategy not in AVAILABLE_STRATEGIES:
            return CommandResult(
                content=[{
                    "type": "text",
                    "text": (
                        f"❌ Неизвестная strategy: `{new_strategy}`\n\n"
                        f"Доступные: {', '.join(f'`{s}`' for s in AVAILABLE_STRATEGIES)}"
                    ),
                }]
            )
        
        try:
            self._strategy_dispatcher.set_strategy(new_strategy)
        except ValueError as e:
            return CommandResult(
                content=[{"type": "text", "text": f"❌ {e}"}]
            )
        
        return CommandResult(
            content=[{
                "type": "text",
                "text": f"✅ Strategy изменена: `{current_strategy}` → `{new_strategy}`",
            }]
        )
    
    def get_definition(self) -> AvailableCommand:
        """Возвращает определение команды /strategy."""
        return AvailableCommand(
            name="strategy",
            description="Показать или изменить execution strategy",
            input=AvailableCommandInput(
                hint="имя strategy (single, multi_orchestrated, hierarchical)"
            ),
        )
```

**Регистрация в SlashCommandsProvider:**
```python
class SlashCommandsProvider(Provider):
    @provide(scope=Scope.APP)
    def get_command_registry(
        self,
        strategy_dispatcher: StrategyDispatcher,
    ) -> CommandRegistry:
        registry = CommandRegistry()
        registry.register(StatusCommandHandler())
        registry.register(ModeCommandHandler())
        registry.register(StrategyCommandHandler(strategy_dispatcher))  # ← новый
        registry.register(HelpCommandHandler(registry))
        return registry
```

---

### 8. Обновить session.py — configOptions вместо modes

**Файл:** `codelab/src/codelab/server/protocol/handlers/session.py`

**Изменения:**

```python
def build_config_options(
    values: dict[str, str],
    specs: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Построить configOptions для ACP response."""
    options = []
    for config_id, spec in specs.items():
        option = {
            "id": config_id,
            "name": spec["name"],
            "category": spec.get("category", ""),
            "type": spec.get("type", "select"),
            "currentValue": values.get(config_id, spec.get("default", "")),
            "options": spec.get("options", []),
        }
        if "description" in spec:
            option["description"] = spec["description"]
        options.append(option)
    return options

def build_modes_state(
    values: dict[str, str],
    specs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Построить modes для обратной совместимости (legacy)."""
    mode_spec = specs.get("mode", {})
    current_mode = values.get("mode", mode_spec.get("default", "ask"))
    available_modes = [
        {"id": opt["value"], "name": opt["name"], "description": opt.get("description", "")}
        for opt in mode_spec.get("options", [])
    ]
    return {
        "currentModeId": current_mode,
        "availableModes": available_modes,
    }
```

---

### 9. Обновить тесты

**Файлы:**

1. **`tests/server/test_config.py`**
   - Переименовать `mode` → `strategy` в тестах
   - Переименовать `fallback_mode` → `fallback_strategy`

2. **`tests/server/test_protocol.py`**
   - Обновить тесты config_specs — проверить `mode` и `_agent`
   - Обновить тесты session/new response — проверить configOptions

3. **`tests/server/agent/strategies/test_dispatcher.py`** (новый файл)
   - Тест: StrategyDispatcher использует AgentsConfig.strategy
   - Тест: StrategyDispatcher получает agent_name из config_values["_agent"]
   - Тест: Ошибка если агент не найден в Registry
   - Тест: set_strategy() для runtime override

4. **`tests/server/protocol/handlers/slash_commands/test_strategy.py`** (новый файл)
   - Тест: `/strategy` показывает текущую strategy
   - Тест: `/strategy single` меняет strategy
   - Тест: `/strategy unknown` возвращает ошибку

5. **`tests/server/observability/`**
   - Проверить что observability работает с новым flow
   - Проверить что span содержит правильный `agent_name`

---

### 10. Интеграционные тесты

**Файл:** `tests/server/test_strategy_integration.py` (новый файл)

**Тесты:**

1. **Тест полного flow:**
   - Создать AgentRegistry с несколькими primary agents
   - Создать сессию с `config_values["_agent"] = "coder"`
   - Вызвать `session/prompt`
   - Проверить что вызван агент "coder"
   - Проверить что observability span содержит `agent_name="coder"`

2. **Тест configOptions:**
   - Проверить что session/new возвращает configOptions с `mode` и `_agent`
   - Проверить что `_agent` options формируются из AgentRegistry

3. **Тест /strategy slash command:**
   - Вызвать `/strategy` — показать текущую
   - Вызвать `/strategy multi_orchestrated` — изменить
   - Проверить что StrategyDispatcher обновлён

4. **Тест fallback:**
   - Создать сессию с `config_values["_agent"] = "nonexistent"`
   - Вызвать `session/prompt`
   - Проверить что возвращена ошибка "Agent not found"

---

### 11. Обновить документацию

**Файл:** `codelab/README.md`

**Изменения:**
- Обновить пример TOML конфигурации: `mode` → `strategy`
- Добавить описание slash command `/strategy`
- Добавить описание config options `mode` и `_agent`

---

## Порядок реализации

1. **Config** — переименовать `mode` → `strategy` в `AgentsConfig`
2. **StrategyDispatcher** — добавить `agent_registry`, обновить логику
3. **SingleStrategy** — добавить параметр `agent_name` в `execute()`
4. **ACPProtocol** — добавить `agent_registry`, обновить `_build_config_specs()`
5. **session.py** — обновить `build_config_options()` и `build_modes_state()`
6. **DI** — обновить провайдеры
7. **LLMLoopStage** — обновить для работы с `strategy`
8. **Slash command `/strategy`** — создать и зарегистрировать
9. **Тесты** — обновить существующие, добавить новые
10. **Интеграционные тесты** — проверить полный flow
11. **Документация** — обновить README

---

## Breaking Changes

1. **TOML конфигурация:**
   ```toml
   # Было:
   [agents]
   mode = "single"
   fallback_mode = "single"
   
   # Стало:
   [agents]
   strategy = "single"
   fallback_strategy = "single"
   ```

2. **Session config_values:**
   - `config_values["mode"]` теперь содержит permission mode (ask/code), НЕ execution strategy
   - `config_values["_agent"]` — имя агента для вызова

---

## Метрики успеха

- [ ] `AgentsConfig.strategy` загружается из TOML
- [ ] ACPProtocol возвращает configOptions с `mode` и `_agent`
- [ ] IDE получает список primary agents для `_agent` dropdown
- [ ] StrategyDispatcher использует правильный agent_name
- [ ] Observability span содержит правильный `agent_name`
- [ ] `/strategy` slash command работает
- [ ] Legacy `modes` API работает для обратной совместимости
- [ ] Все существующие тесты проходят
- [ ] Новые интеграционные тесты проходят
