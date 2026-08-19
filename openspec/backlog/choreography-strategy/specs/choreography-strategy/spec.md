# Spec: ChoreographyStrategy

## ДОБАВЛЕННЫЕ Требования

### Требование: ContextBroadcast — доменное событие broadcast

Система ДОЛЖНА предоставлять `ContextBroadcast` для рассылки всем агентам:

```python
@dataclass(frozen=True)
class ContextBroadcast(DomainEvent):
    context: list[Message]
    available_agents: list[str]
    step: int
    correlation_id: str
    session_id: str
```

#### Сценарий: Broadcast всем агентам
- **КОГДА** ChoreographyStrategy начинает шаг
- **ТОГДА** ContextBroadcast отправляется всем зарегистрированным агентам параллельно
- **И** каждый агент получает одинаковый context

### Требование: ChoreographyAnswer — ответ агента

Система ДОЛЖНА предоставлять `ChoreographyAnswer` как ответ агента на broadcast:

```python
@dataclass(frozen=True)
class ChoreographyAnswer(DomainEvent):
    agent_name: str
    action_taken: bool
    reasoning: str
    output: str | None
    status_signal: Literal["continue", "completed"]
    usage: TokenUsage
```

#### Сценарий: Агент принимает действие
- **КОГДА** агент решает выполнить действие
- **ТОГДА** возвращается ChoreographyAnswer с action_taken=True, output, reasoning
- **И** status_signal="completed" если задача решена

#### Сценарий: Агент воздерживается
- **КОГДА** агент решает не выполнять действие
- **ТОГДА** возвращается ChoreographyAnswer с action_taken=False, reasoning
- **И** status_signal="continue"

### Требование: Conflict Resolution

Система ДОЛЖНА разрешать конфликты через Priority Queue:

- Priority из agent config (priority, меньше = важнее)
- Winner = агент с наименьшим priority среди action_taken=True
- При равном priority — первый по порядку
- Winner output суммаризируется через TokenSlicer (опционально)

#### Сценарий: Один winner
- **КОГДА** только один агент вернул action_taken=True
- **ТОГДА** он становится winner

#### Сценарий: Несколько агентов — выбор по priority
- **КОГДА** несколько агентов вернули action_taken=True
- **ТОГДА** winner = агент с наименьшим priority
- **И** остальные ответы записываются в EventTimeline для debug mode

#### Сценарий: Нет активных агентов
- **КОГДА** все агенты вернули action_taken=False
- **ТОГДА** шаг повторяется или завершается по max_steps

### Требование: ChoreographyStrategy

Система ДОЛЖНА предоставлять `ChoreographyStrategy` — стратегию параллельного выполнения:

1. FCM.create_scope("_broadcast_context") + hydrate_from_history() — подготовка broadcast контекста
2. Broadcast ContextBroadcast всем агентам параллельно (из FCM payload)
3. Сбор ChoreographyAnswer от каждого агента
4. Conflict Resolution: Priority Queue
5. SubAgentCoordinator.process_subagent_response() — создать child session только для winner + TokenSlicer (опционально)
6. FCM.add_to_scope("_broadcast_context", "winner_summary", ...) — добавить summary в контекст
7. coordination_overhead_tokens: токены холостых опросов
8. max_steps предохранитель

**Управление контекстом:**
- `FCM.create_scope("_broadcast_context")` — общий scope для broadcast (не изолированные per-agent scopes)
- Broadcast context формируется через `FCM.optimize_and_build_payload("_broadcast_context")`
- FCM НЕ создаёт scope для каждого агента-участника — они получают одинаковый broadcast payload
- После Conflict Resolution: `FCM.create_scope(winner_name)` + `share_from("_broadcast_context", winner_name)` — только для winner

#### Сценарий: Успешное выполнение
- **КОГДА** стратегия начинает выполнение
- **ТОГДА** FCM формирует broadcast payload из "_broadcast_context" scope
- **И** выполняется цикл: broadcast → parallel → conflict resolution → SubAgentCoordinator → winner scope → next step
- **И** цикл завершается когда winner status_signal="completed" или достигнут max_steps

#### Сценарий: Fallback при недоступности стратегии
- **КОГДА** нет ≥2 агентов с mode=subagent
- **ТОГДА** StrategyDispatcher fallback на single mode
- **И** отправляется уведомление клиенту: "[system] ChoreographyStrategy unavailable"

#### Сценарий: Cancellation
- **КОГДА** получен session/cancel во время broadcast
- **ТОГДА** asyncio.gather(*tasks, return_exceptions=True) — все параллельные calls
- **И** каждый agent task отменяется через task.cancel()
- **И** Conflict Resolution полностью пропускается
- **И** частичные результаты игнорируются

### Требование: Child Session для Winner

Child session ДОЛЖНА создаваться только для winner-агента через `SubAgentCoordinator`:
- Минимизирует overhead (1 child session вместо N)
- Сохраняет навигацию к деталям выполненной работы
- Проигравшие агенты НЕ получают child sessions
- Ответы проигравших записываются в EventTimeline для debug mode
- `SubAgentCoordinator` НЕ выполняет compaction — это делает FCM автоматически через `DefaultContextCompactor`

### Требование: Child session mode inheritance

Winner child session ДОЛЖНА наследовать mode от parent session:

- Child session.config_values["mode"] = parent.config_values["mode"]
- Winner-агент НЕ может переключить mode на другое значение

### Требование: Валидация стратегии

ChoreographyStrategy ДОЛЖНА требовать ≥2 агентов с mode=subagent.

При недоступности → fallback на single mode с уведомлением.

### Требование: Plan в ChoreographyStrategy

План НЕ используется в ChoreographyStrategy (параллельное выполнение, нет единого плана).
