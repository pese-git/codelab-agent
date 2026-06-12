# Spec: HierarchicalStrategy

## ДОБАВЛЕННЫЕ Требования

### Требование: TaskInvocation — доменное событие делегирования

Система ДОЛЖНА предоставлять `TaskInvocation` как доменное событие делегирования:

```python
@dataclass(frozen=True)
class TaskInvocation(DomainEvent):
    target_agent: str
    prompt: str
    tools: list[ToolDefinition]
    permission_override: dict | None = None
    correlation_id: str
    session_id: str           # parent session
```

#### Сценарий: Конвертация TaskInvocation → AgentRequest
- **КОГДА** HierarchicalStrategy делегирует задачу субагенту
- **ТОГДА** TaskInvocation конвертируется в AgentRequest
- **И** prompt оборачивается в messages: [SystemMessage(prompt)]
- **И** session_id = child_session_id (не parent)

#### Сценарий: Проверка task permissions ДО вызова шины
- **КОГДА** TaskInvocation имеет permission_override
- **ТОГДА** стратегия проверяет разрешения ДО вызова EventBus
- **И** при "ask" → session/request_permission пользователю

### Требование: TaskResult — доменный результат делегирования

Система ДОЛЖНА предоставлять `TaskResult` как доменный результат:

```python
@dataclass(frozen=True)
class TaskResult(DomainEvent):
    invocation_id: str
    success: bool
    output: str
    tool_calls: list[ToolCall]
    usage: TokenUsage
    agent_name: str
    child_session_id: str     # ID изолированной child session
```

#### Сценарий: Построение TaskResult из AgentResponse
- **КОГДА** получен AgentResponse от шины
- **ТОГДА** строится TaskResult: text→output, stop_reason→success, + child_session_id

### Требование: Task Permissions

Система ДОЛЖНА проверять может ли caller вызывать target agent:

- Конфигурация в agent permission: `task: {"*": "deny", "tester": "allow", "reviewer": "ask"}`
- При "allow" → выполнить делегирование
- При "deny" → отклонить с ошибкой
- При "ask" → session/request_permission пользователю

#### Сценарий: Разрешённый вызов
- **КОГДА** primary agent вызывает subagent с permission=allow
- **ТОГДА** делегирование выполняется без запроса пользователя

#### Сценарий: Запрещённый вызов
- **КОГДА** primary agent вызывает subagent с permission=deny
- **ТОГДА** делегирование отклоняется с ошибкой

#### Сценарий: Запрос разрешения
- **КОГДА** primary agent вызывает subagent с permission=ask
- **ТОГДА** отправляется session/request_permission пользователю
- **И** agent_name передаётся через _meta

### Требование: HierarchicalStrategy

Система ДОЛЖНА предоставлять `HierarchicalStrategy` — стратегию иерархического делегирования:

1. Primary Agent получает пользовательский запрос
2. Primary LLM решает: ответить самому или делегировать через Task tool
3. При делегировании: check permissions → child session → TaskInvocation → AgentRequest
4. Subagent выполняет в child session: свой prompt, свои инструменты, свои permissions
5. Subagent возвращает AgentResponse → TaskResult
6. TokenSlicer суммаризирует результат для parent context
7. Primary интегрирует summary, продолжает или завершает

#### Сценарий: Успешное делегирование
- **КОГДА** primary agent решает делегировать задачу
- **ТОГДА** создаётся child session
- **И** TaskInvocation конвертируется в AgentRequest
- **И** subagent выполняет задачу
- **И** TaskResult возвращается primary agent
- **И** TokenSlicer суммаризирует результат

#### Сценарий: Ответ без делегирования
- **КОГДА** primary agent решает ответить сам
- **ТОГДА** выполняется один LLM call без делегирования
- **И** ответ возвращается пользователю

#### Сценарий: Cancellation
- **КОГДА** получен session/cancel
- **ТОГДА** cascade cancellation: primary → child sessions → sub-agents
- **И** child sessions помечаются status="cancelled"
- **И** все pending send_request отменяются

### Требование: Валидация стратегии

HierarchicalStrategy ДОЛЖНА требовать:
- ≥1 агент с mode=primary
- ≥1 агент с mode=subagent

При недоступности → fallback на single mode с уведомлением.

### Требование: MCP в HierarchicalStrategy

MCP Manager ДОЛЖЕН propagating в child sessions:
- MCP tools доступны subagent через AgentRequest.tools
- Живые MCP подключения — shared per-session объект

### Требование: Plan в HierarchicalStrategy

План ДОЛЖЕН работать:
- Primary update_plan → parent session plan
- Sub-agent update_plan → child session plan
- TUI: parent plan по умолчанию, child plan при навигации
