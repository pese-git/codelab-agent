# План реализации: AgentLoop — унифицированный цикл итераций LLM

## Обзор

Рефакторинг `LLMLoopStage` с выделением цикла итераций в отдельный компонент `AgentLoop`,
использующий Strategy Pattern для поддержки разных способов вызова LLM.

## Архитектурные решения

| Решение | Обоснование |
|---------|-------------|
| `AgentLoop` в отдельном файле | SRP — цикл отдельно от pipeline stage |
| `LLMCallStrategy` Protocol | DIP — зависимость от абстракции |
| `LegacyCallStrategy` адаптер | OCP — legacy без изменения AgentLoop |
| `resume_after_permission()` в AgentLoop | High Cohesion — часть жизненного цикла |
| `max_turn_requests` вместо `max_iterations` | Соответствие ACP спецификации |

## Соответствие ACP спецификации

| ACP требование | Реализация |
|----------------|------------|
| `loop Until completion` (05-Prompt Turn.md:30) | `AgentLoop.run()` с циклом |
| `max_turn_requests` stop reason (05-Prompt Turn.md:278) | `StopReason.MAX_TURN_REQUESTS` |
| Tool results back to LLM (05-Prompt Turn.md:261-263) | `continue_execution()` |
| Permission flow (08-Tool Calls.md:110-166) | `resume_after_permission()` |

---

## Структура файлов

```
src/codelab/server/
├── agent/strategies/
│   ├── base.py                    # LLMCallStrategy Protocol
│   ├── dispatcher.py              # StrategyDispatcher (уже есть, адаптировать)
│   └── legacy_adapter.py          # LegacyCallStrategy (НОВЫЙ)
├── protocol/handlers/pipeline/stages/
│   ├── agent_loop.py              # AgentLoop (НОВЫЙ)
│   └── llm_loop.py                # LLMLoopStage (рефакторинг → тонкий адаптер)
└── protocol/
    └── stop_reasons.py            # StopReason enum (НОВЫЙ)
```

---

## Задачи

### 1. Создать `StopReason` enum

**Файл:** `src/codelab/server/protocol/stop_reasons.py`

```python
from enum import StrEnum

class StopReason(StrEnum):
    """Причины остановки prompt turn (ACP 05-Prompt Turn.md)."""
    
    END_TURN = "end_turn"
    MAX_TOKENS = "max_tokens"
    MAX_TURN_REQUESTS = "max_turn_requests"
    REFUSAL = "refusal"
    CANCELLED = "cancelled"
```

---

### 2. Создать `LLMCallStrategy` Protocol

**Файл:** `src/codelab/server/agent/strategies/base.py`

```python
from typing import Protocol, Any

class LLMCallStrategy(Protocol):
    """Интерфейс для стратегии вызова LLM."""
    
    async def execute(
        self,
        session: "SessionState",
        prompt: str | None,
        mcp_manager: Any | None = None,
    ) -> "AgentResponse":
        """Выполнить вызов LLM с начальным prompt."""
        ...
    
    async def continue_execution(
        self,
        session: "SessionState",
        mcp_manager: Any | None = None,
    ) -> "AgentResponse":
        """Продолжить выполнение после tool_results."""
        ...
```

---

### 3. Создать `LegacyCallStrategy` адаптер

**Файл:** `src/codelab/server/agent/strategies/legacy_adapter.py`

```python
class LegacyCallStrategy:
    """Адаптер AgentOrchestrator под LLMCallStrategy.
    
    Сохраняет legacy путь (AgentOrchestrator + NaiveAgent)
    для обратной совместимости.
    """
    
    def __init__(self, orchestrator: AgentOrchestrator):
        self._orchestrator = orchestrator
    
    async def execute(self, session, prompt, mcp_manager=None):
        return await self._orchestrator.process_prompt(session, prompt, mcp_manager)
    
    async def continue_execution(self, session, mcp_manager=None):
        return await self._orchestrator.continue_with_tool_results(session, [], mcp_manager)
```

---

### 4. Адаптировать `StrategyDispatcher` под `LLMCallStrategy`

**Файл:** `src/codelab/server/agent/strategies/dispatcher.py`

**Изменения:**
- Убедиться что сигнатуры `execute()` и `continue_execution()` совпадают с Protocol
- Добавить type hints для соответствия Protocol

---

### 5. Создать `AgentLoop`

**Файл:** `src/codelab/server/protocol/handlers/pipeline/stages/agent_loop.py`

```python
class AgentLoop:
    """Универсальный цикл итераций LLM tool-calling.
    
    Соответствует ACP 05-Prompt Turn.md:
    - loop Until completion (строка 30)
    - max_turn_requests stop reason (строка 278)
    - Tool results back to LLM (строки 261-263)
    """
    
    def __init__(
        self,
        strategy: LLMCallStrategy,
        tool_registry: ToolRegistry,
        tool_call_handler: ToolCallHandler,
        permission_manager: PermissionManager,
        state_manager: StateManager,
        content_extractor: ContentExtractor,
        content_formatter: ContentFormatter,
        replay_manager: ReplayManager,
        plan_builder: PlanBuilder,
        max_turn_requests: int = 10,
    ):
        ...
    
    async def run(
        self,
        session: SessionState,
        session_id: str,
        initial_prompt: str | None = None,
        mcp_manager: Any | None = None,
    ) -> AgentLoopResult:
        """Запустить цикл итераций."""
        iteration = 0
        
        while iteration < self._max_turn_requests:
            iteration += 1
            
            # Вызов LLM
            if iteration == 1 and initial_prompt:
                response = await self._strategy.execute(session, initial_prompt, mcp_manager)
            else:
                response = await self._strategy.continue_execution(session, mcp_manager)
            
            # Обработка ответа
            if not response.tool_calls:
                return AgentLoopResult(text=response.text, stop_reason=StopReason.END_TURN)
            
            # Обработка tool_calls
            tool_result = await self._process_tool_calls(...)
            
            # Permission pause
            if tool_result.pending_permission:
                return AgentLoopResult(pending_permission=True, ...)
            
            # Продолжить цикл
        
        return AgentLoopResult(stop_reason=StopReason.MAX_TURN_REQUESTS)
    
    async def resume_after_permission(
        self,
        session: SessionState,
        session_id: str,
        tool_call_id: str,
        mcp_manager: Any | None = None,
    ) -> AgentLoopResult:
        """Продолжить цикл после permission approval.
        
        1. Выполняет pending tool
        2. Продолжает цикл с tool_results
        """
        # Выполнить pending tool
        tool_result = await self._execute_pending_tool(tool_call_id, ...)
        
        # Продолжить цикл (tool_results уже в session.history)
        return await self.run(session, session_id, initial_prompt=None, mcp_manager=mcp_manager)
```

---

### 6. Рефакторить `LLMLoopStage`

**Файл:** `src/codelab/server/protocol/handlers/pipeline/stages/llm_loop.py`

**Изменения:**
- Удалить `_run_llm_loop` (legacy) — заменён `AgentLoop.run()`
- Удалить `_process_via_event_bus` — заменён `AgentLoop.run()`
- Удалить `_process_tool_calls_for_llm_loop` — перенесён в `AgentLoop`
- Оставить тонкий адаптер к pipeline

```python
class LLMLoopStage(PromptStage):
    """Тонкий адаптер pipeline → AgentLoop."""
    
    def __init__(self, ...):
        self._agent_loop: AgentLoop | None = None
    
    def _get_or_create_agent_loop(self, context: PromptContext) -> AgentLoop:
        """Лениво создать AgentLoop с нужной стратегией."""
        if self._agent_loop is not None:
            return self._agent_loop
        
        # Определяем стратегию
        if self._strategy_dispatcher is not None:
            strategy = self._strategy_dispatcher  # EventBusStrategy
        else:
            agent_orchestrator = context.meta.get("agent_orchestrator")
            strategy = LegacyCallStrategy(agent_orchestrator)
        
        self._agent_loop = AgentLoop(
            strategy=strategy,
            tool_registry=self._tool_registry,
            ...
        )
        return self._agent_loop
    
    async def process(self, context: PromptContext) -> PromptContext:
        agent_loop = self._get_or_create_agent_loop(context)
        
        result = await agent_loop.run(
            session=context.session,
            session_id=context.session_id,
            initial_prompt=context.raw_text,
            mcp_manager=self._get_mcp_manager(context),
        )
        
        context.notifications.extend(result.notifications)
        context.stop_reason = result.stop_reason or StopReason.END_TURN
        context.pending_permission = result.pending_permission
        
        return context
    
    async def execute_pending_tool(self, session, session_id, tool_call_id, ...):
        """Permission resume — делегируем AgentLoop."""
        agent_loop = self._get_or_create_agent_loop(context)
        
        return await agent_loop.resume_after_permission(
            session=session,
            session_id=session_id,
            tool_call_id=tool_call_id,
            mcp_manager=mcp_manager,
        )
```

---

### 7. Обновить DI провайдеры

**Файл:** `src/codelab/server/di.py`

**Изменения:**
- Обновить `PipelineProvider.get_llm_loop_stage()` для передачи новых зависимостей

---

### 8. Обновить тесты

**Файлы:**
- `tests/server/protocol/handlers/pipeline/stages/test_agent_loop.py` (НОВЫЙ)
- `tests/server/agent/strategies/test_legacy_adapter.py` (НОВЫЙ)
- `tests/server/protocol/handlers/pipeline/stages/test_llm_loop.py` (обновить)

---

## Порядок реализации

1. **Создать `StopReason` enum** — stop_reasons.py
2. **Создать `LLMCallStrategy` Protocol** — strategies/base.py
3. **Создать `LegacyCallStrategy`** — strategies/legacy_adapter.py
4. **Адаптировать `StrategyDispatcher`** — обновить сигнатуры
5. **Создать `AgentLoop`** — agent_loop.py
6. **Рефакторить `LLMLoopStage`** — тонкий адаптер
7. **Обновить DI** — PipelineProvider
8. **Обновить тесты** — новые + обновлённые
9. **Удалить мёртвый код** — `_run_llm_loop`, `_process_via_event_bus`

---

## Метрики успеха

- [ ] `StopReason` enum содержит все значения из ACP
- [ ] `AgentLoop.run()` реализует цикл итераций
- [ ] `AgentLoop.resume_after_permission()` реализует permission resume
- [ ] `LLMLoopStage` — тонкий адаптер (< 50 строк)
- [ ] Legacy путь работает через `LegacyCallStrategy`
- [ ] EventBus путь работает через `StrategyDispatcher`
- [ ] Все существующие тесты проходят
- [ ] Новые тесты для `AgentLoop` проходят
- [ ] Код соответствует ACP спецификации
