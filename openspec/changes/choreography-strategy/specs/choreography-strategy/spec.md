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

1. Broadcast ContextBroadcast всем агентам параллельно
2. Сбор ChoreographyAnswer от каждого агента
3. Conflict Resolution: Priority Queue
4. Создать child session для winner-агента
5. TokenSlicer: суммаризация winner output (опционально)
6. coordination_overhead_tokens: токены холостых опросов
7. max_steps предохранитель

#### Сценарий: Успешное выполнение
- **КОГДА** стратегия начинает выполнение
- **ТОГДА** выполняется цикл: broadcast → parallel → conflict resolution → winner → next step
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

Child session ДОЛЖНА создаваться только для winner-агента:
- Минимизирует overhead (1 child session вместо N)
- Сохраняет навигацию к деталям выполненной работы
- Проигравшие агенты НЕ получают child sessions
- Ответы проигравших записываются в EventTimeline для debug mode

### Требование: Child session mode inheritance

Winner child session ДОЛЖНА наследовать mode от parent session:

- Child session.config_values["mode"] = parent.config_values["mode"]
- Winner-агент НЕ может переключить mode на другое значение

### Требование: Валидация стратегии

ChoreographyStrategy ДОЛЖНА требовать ≥2 агентов с mode=subagent.

При недоступности → fallback на single mode с уведомлением.

### Требование: Plan в ChoreographyStrategy

План НЕ используется в ChoreographyStrategy (параллельное выполнение, нет единого плана).
