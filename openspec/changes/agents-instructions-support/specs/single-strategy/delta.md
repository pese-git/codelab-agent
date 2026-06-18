# Delta Spec: single-strategy (agents-instructions-support)

## ИЗМЕНЁННЫЕ Требования

### `SystemPromptBuilder` — интеграция инструкций

**Было**:
```python
class SystemPromptBuilder:
    def __init__(
        self,
        global_prompt: str = "",
        agent_registry: AgentRegistry | None = None,
    ) -> None: ...
    
    def build(
        self,
        session: SessionState,
        mcp_manager: Any | None = None,
    ) -> str | None: ...
```

**Стало**:
```python
class SystemPromptBuilder:
    def __init__(
        self,
        global_prompt: str = "",
        agent_registry: AgentRegistry | None = None,
        instructions_resolver: AgentsInstructionsResolver | None = None,  # NEW
    ) -> None: ...
    
    async def build(  # async теперь!
        self,
        session: SessionState,
        mcp_manager: Any | None = None,
        client_rpc_bridge: ClientRPCBridge | None = None,  # NEW
    ) -> str | None: ...
```

---

## ДОБАВЛЕННЫЕ Требования

### Требование: Порядок формирования system prompt

`SystemPromptBuilder.build()` ДОЛЖЕН формировать system prompt в следующем порядке:

```
1. Agent Prompt (роль агента из AgentRegistry)
2. AGENTS.md instructions (из AgentsInstructionsResolver) ← NEW
3. Global Prompt (из config.agent.system_prompt)
4. MCP Info (список подключённых MCP серверов)
```

**Обоснование**: Конкретное → общее. Контекст проекта важнее общих инструкций.

---

### Требование: Интеграция с AgentsInstructionsResolver

`SystemPromptBuilder` ДОЛЖЕН:
1. Принимать опциональный `instructions_resolver` в конструкторе
2. Вызывать `resolver.resolve(session, bridge)` для получения инструкций
3. Инжектировать инструкции между agent prompt и global prompt
4. Если resolver отсутствует или инструкции пустые — пропускать этот блок

**Пример**:
```python
async def build(self, session, mcp_manager=None, client_rpc_bridge=None):
    parts = []
    
    # 1. Agent prompt
    agent_prompt = self._resolve_agent_prompt(session)
    if agent_prompt:
        parts.append(agent_prompt)
    
    # 2. Instructions (NEW)
    if self._instructions_resolver:
        instructions = await self._instructions_resolver.resolve(
            session, bridge=client_rpc_bridge
        )
        if instructions:
            parts.append(instructions)
    
    # 3. Global prompt
    if self._global_prompt:
        parts.append(self._global_prompt)
    
    # 4. MCP info
    if mcp_manager:
        mcp_info = self._format_mcp_info(mcp_manager)
        if mcp_info:
            parts.append(mcp_info)
    
    return "\n\n".join(parts) if parts else None
```

---

### Требование: Формат инструкций в system prompt

Инструкции ДОЛЖНЫ форматироваться с указанием источника:

```markdown
### Instructions from `/project/AGENTS.md`

Use pytest for testing.
Run `make check` before committing.
```

---

### Требование: Async переход

`SystemPromptBuilder.build()` ДОЛЖЕН стать `async` методом, так как `AgentsInstructionsResolver.resolve()` — async (для remote чтения).

**Влияние на вызывающий код**:
- `AgentLoop.run()` — уже async, изменений не требует
- `LLMLoopStage` — уже async, изменений не требует
- Тесты — требуют обновления на `await builder.build(...)`

---

### Требование: Обратная совместимость

`SystemPromptBuilder` ДОЛЖЕН работать без `instructions_resolver`:
- Если `instructions_resolver=None` — блок инструкций пропускается
- Существующие тесты продолжают работать (после обновления на async)
- Конфигурация без `[agents.instructions]` использует defaults

---

## Зависимости

| Компонент | Тип зависимости |
|-----------|-----------------|
| `AgentsInstructionsResolver` | Опциональная (может быть None) |
| `ClientRPCBridge` | Опциональная (для remote режима) |
| `SessionState` | Обязательная (для `cwd`) |

---

## Тестовые сценарии

### TC-1: Build без instructions_resolver

**Дано**:
- `instructions_resolver = None`
- Agent prompt: `"Ты — программист"`
- Global prompt: `"Используй инструменты"`

**Когда**: Вызван `build(session)`

**Тогда**: System prompt содержит только agent + global prompt

---

### TC-2: Build с инструкциями

**Дано**:
- `instructions_resolver` возвращает `"Use pytest"`
- Agent prompt: `"Ты — программист"`

**Когда**: Вызван `await build(session)`

**Тогда**: System prompt содержит agent prompt + instructions

---

### TC-3: Build с пустыми инструкциями

**Дано**:
- `instructions_resolver` возвращает `""`
- Agent prompt: `"Ты — программист"`

**Когда**: Вызван `await build(session)`

**Тогда**: System prompt содержит только agent prompt (инструкции пропущены)
