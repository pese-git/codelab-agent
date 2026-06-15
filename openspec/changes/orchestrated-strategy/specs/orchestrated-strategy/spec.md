# Spec: OrchestratedStrategy

## ДОБАВЛЕННЫЕ Требования

### Требование: RouteDecision через Structured Outputs

Система ДОЛЖНА предоставлять Pydantic модель `RouteDecision` для маршрутизации субагентов:

```python
class RouteDecision(BaseModel):
    reasoning: str
    target_agent: str | None    # null = задача решена
    task_payload: str | None    # атомарная задача для субагента
```

#### Сценарий: Генерация RouteDecision
- **КОГДА** orchestrator LLM анализирует запрос
- **ТОГДА** возвращается валидный RouteDecision с reasoning, target_agent, task_payload
- **И** target_agent=null означает завершение задачи

#### Сценарий: Prompt template для RouteDecision
- **КОГДА** формируется prompt для orchestrator
- **ТОГДА** включаются описания всех доступных агентов из AgentRegistry
- **И** инструкции: null = задача решена, иначе target_agent + task_payload

### Требование: TokenSlicer

Система ДОЛЖНА предоставлять `TokenSlicer` для суммаризации ответов субагентов:

- Использует дешёвую LLM модель (slicer_model из конфига)
- Skip threshold: если output < slicer_skip_threshold токенов — не сжимать
- Fallback: при ошибке LLM — truncate с сохранением начала и конца
- Создаёт tracer span с метриками: original_tokens, sliced_tokens, compression_ratio

#### Сценарий: Суммаризация большого ответа
- **КОГДА** ответ субагента превышает slicer_skip_threshold токенов
- **ТОГДА** TokenSlicer вызывает LLM для суммаризации
- **И** возвращает SlicedResult с summary, child_session_id, метриками

#### Сценарий: Пропуск суммаризации для малого ответа
- **КОГДА** ответ субагента меньше slicer_skip_threshold токенов
- **ТОГДА** TokenSlicer возвращает ответ без изменений (was_skipped=True)

#### Сценарий: Fallback при ошибке LLM
- **КОГДА** LLM для суммаризации недоступна
- **ТОГДА** TokenSlicer применяет truncate: первые 60% + последние 40% + ellipsis

### Требование: HybridContextManager

Система ДОЛЖНА предоставлять `HybridContextManager` для координации управления контекстом:

- `process_subagent_response()` — создать child session + TokenSlicer
- `ensure_context_fits()` — проверить лимит контекста, выполнить compaction если нужно
- Связывание parent ↔ child sessions в storage

#### Сценарий: Обработка ответа субагента
- **КОГДА** субагент возвращает ответ
- **ТОГДА** создаётся child session с полным контекстом
- **И** TokenSlicer суммаризирует ответ
- **И** parent session получает sliced summary
- **И** child_session_ids обновляется у parent

#### Сценарий: Compaction при длинной сессии
- **КОГДА** контекст достигает (context_window_limit - compaction_reserved_tokens)
- **ТОГДА** выполняется двухфазный compaction: Prune → LLM Summarize

### Требование: OrchestratedStrategy

Система ДОЛЖНА предоставлять `OrchestratedStrategy` — стратегию выполнения с циклом маршрутизации:

1. Orchestrator LLM делает RouteDecision (Structured Outputs)
2. Point-to-point вызов субагента через EventBus.send_request()
3. Создать child session для субагента
4. TokenSlicer суммаризирует ответ
5. max_steps предохранитель (default 7)
6. Race condition guard: проверка available_agents перед каждым шагом

#### Сценарий: Успешное выполнение
- **КОГДА** orchestrator получает запрос
- **ТОГДА** выполняется цикл: RouteDecision → sub-agent → TokenSlicer → next step
- **И** цикл завершается когда target_agent=null или достигнут max_steps

#### Сценарий: Fallback при недоступности стратегии
- **КОГДА** нет агента с mode=orchestrator ИЛИ нет агента с mode=subagent
- **ТОГДА** StrategyDispatcher fallback на single mode
- **И** отправляется уведомление клиенту: "[system] OrchestratedStrategy unavailable"

#### Сценарий: Cancellation
- **КОГДА** получен session/cancel во время выполнения
- **ТОГДА** текущий agent call завершается
- **И** проверка cancellation_event перед следующим шагом
- **И** все pending send_request отменяются

### Требование: Child Sessions

Child sessions ДОЛЖНЫ:
- Создаваться при каждом вызове субагента
- Иметь parent_session_id, is_child_session=True
- Сохраняться в storage для навигации в TUI
- Получать статус "cancelled" при cascade cancellation

#### Сценарий: Создание child session
- **КОГДА** orchestrator вызывает субагента
- **ТОГДА** создаётся child session с уникальным session_id
- **И** parent_session_id указывает на родительскую сессию
- **И** child_session_ids добавляется к parent

#### Сценарий: Навигация в TUI
- **КОГДА** пользователь навигирует в child session
- **ТОГДА** отображается полная история child session
- **И** доступны переходы Leader+Right → следующая child, Leader+Left → parent

### Требование: Child session mode inheritance

При создании child session ДОЛЖНА наследовать mode от parent session:

- Child session.config_values["mode"] = parent.config_values["mode"]
- Субагент НЕ может переключить mode на другое значение
- При попытке установить другой mode → warning в лог, mode остаётся parent.mode

#### Сценарий: Наследование mode в child session
- **КОГДА** parent session имеет mode="plan"
- **И** orchestrator создаёт child session для субагента
- **ТОГДА** child session.config_values["mode"] = "plan"
- **И** субагент НЕ может записать файлы (plan mode блокирует write/execute)

#### Сценарий: Безопасность наследования
- **КОГДА** parent session имеет mode="standard"
- **И** orchestrator пытается создать child session с mode="bypass"
- **ТОГДА** mode принудительно устанавливается в parent.mode ("standard")
- **И** записывается warning в лог

### Требование: MCP Tools в OrchestratedStrategy

MCP инструменты ДОЛЖНЫ быть доступны субагентам:
- MCP tools добавляются к AgentRequest.tools вместе с нативными инструментами
- MCPManager — shared per-session объект, доступный всем агентам
- MCP tools НЕ фильтруются по client capabilities

### Требование: Plan в OrchestratedStrategy

План ДОЛЖЕН работать в мультиагентном режиме:
- Orchestrator update_plan → обновляет plan parent session
- Sub-agent update_plan → обновляет plan своей child session
- TUI показывает план из parent session по умолчанию
- При навигации в child session — показывается plan child session
