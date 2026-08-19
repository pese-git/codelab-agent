# Delta-спецификация agent-ports

Доведение двух портов до доменной формы: эмиссия прогресса и прод-вход turn-а.
Продолжение change `acp-independent-agent-core`, где оба порта объявлены минимально-честно.

## MODIFIED Requirements

### Requirement: Порт UpdateSink
Ядро MUST эмитить прогресс turn-а через порт `UpdateSink` в доменных терминах; ACP wire
`session/update` MUST собираться внутри адаптера.

**Текущее состояние (после `acp-independent-agent-core`):** порт объявлен с
`emit_agent_message` / `emit_streaming_delta`; доменных `emit_plan` / `emit_tool_call` /
`emit_tool_update` нет, точки эмиссии строят ACP-обновления в turn-loop'е. Turn-loop —
ACP-адаптер, поэтому граница гексагона этим не нарушается, но ядро не может эмитить план и
вызовы инструментов, не зная про ACP.

#### Scenario: Эмиссия обновления в доменных терминах
- **WHEN** ядро сообщает о tool call, обновлении вызова или плане
- **THEN** оно вызывает `UpdateSink.emit_tool_call` / `emit_tool_update` / `emit_plan` с доменными объектами, не с `ACPMessage`

#### Scenario: ACP wire-формат сохранён байт-в-байт
- **WHEN** ACP-адаптер `UpdateSink` мапит доменное событие в `session/update`
- **THEN** wire-формат нотификации байт-идентичен прежнему (golden-тест, снятый **до** правки)

#### Scenario: Немедленная доставка сохранена
- **WHEN** ядро эмитит обновление посреди turn-а
- **THEN** оно доставляется немедленно, а не батчится к концу turn-а

#### Scenario: Ветки success и exception эмитят одинаково
- **WHEN** исполнение инструмента завершилось успехом либо исключением
- **THEN** обновление эмитится одним и тем же путём (снимает асимметрию буферизации, tech-debt P1-4)

### Requirement: Driving-порт AgentRunner
ACP-обвязка MUST входить в turn ядра через driving-порт `AgentRunner`, что позволяет подключать
не-ACP драйверы без изменения ядра.

**Текущее состояние (после `acp-independent-agent-core`):** порт объявлен, `CoreAgentRunner`
реализован и доказан не-ACP fake-драйвером в тесте, но прод turn-loop зовёт `ExecutionEngine`
напрямую — вне тестов `CoreAgentRunner` не используется.

#### Scenario: ACP-адаптер запускает turn через порт
- **WHEN** приходит `session/prompt`
- **THEN** прод turn-loop вызывает `AgentRunner.run_turn(SessionView, TurnRequest)`, а не `ExecutionEngine` напрямую

#### Scenario: Пауза и возобновление не протекают в порт
- **WHEN** turn встаёт на паузу (запрос разрешения либо клиентский RPC) и затем возобновляется
- **THEN** порт `AgentRunner` не получает ACP-специфики паузы; автомат `ActiveTurn` остаётся в адаптере

#### Scenario: Не-ACP драйвер запускает тот же turn
- **WHEN** тест-харнесс без `protocol/` вызывает `AgentRunner.run_turn`
- **THEN** turn проходит корректно, включая доменную эмиссию через `FakeUpdateSink`
