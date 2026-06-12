## Decision 1: TaskInvocation/TaskResult — доменные события, не контракты шины

**Контекст:** HierarchicalStrategy делегирует задачи субагентам.

**Решение:** TaskInvocation и TaskResult — доменные события стратегии. Перед вызовом EventBus.send_request() TaskInvocation конвертируется в AgentRequest (единый контракт шины). После получения AgentResponse стратегия строит TaskResult.

**Tradeoffs:**
- ✅ Чистое разделение домена и транспорта
- ✅ Шина не знает о task permissions, prompt vs messages
- ⚠️ Дополнительная конвертация

## Decision 2: Cascade Cancellation

**Контекст:** При отмене нужно отменить primary, все child sessions и sub-agents.

**Решение:** Каскадная отмена: primary → child sessions → sub-agents. Child sessions помечаются status="cancelled", все pending send_request отменяются.

**Tradeoffs:**
- ✅ Гарантированная очистка ресурсов
- ✅ Child sessions сохраняются для навигации в TUI
- ⚠️ Сложнее чем простая отмена

## Decision 3: Task Permissions через agent config

**Контекст:** Нужно контролировать каких субагентов может вызывать primary agent.

**Решение:** Permissions в agent config: `task: {"*": "deny", "tester": "allow", "reviewer": "ask"}`. Проверка ДО вызова шины.

**Tradeoffs:**
- ✅ Гибкая настройка per-agent
- ✅ "ask" интегрируется с существующим permission flow
- ⚠️ Дополнительная проверка перед каждым делегированием
