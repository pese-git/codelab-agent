# Delta-спецификация agent-ports

Новая capability: driven/driving порты, через которые ядро агента (`server/agent/`)
взаимодействует с обвязкой. Порты выражены в доменном словаре; ACP — один из адаптеров.

## ADDED Requirements

### Requirement: Порт SessionView
Ядро MUST зависеть от read-only порта `SessionView` (доменный словарь), а НЕ от
`protocol.state.SessionState`, для доступа к данным сессии.

#### Scenario: Ядро читает конфигурацию через порт
- **WHEN** `ExecutionEngine.build_context` нуждается в `cwd`/`config_values`
- **THEN** оно получает их из `SessionView.config` (`SessionConfig`), не из `SessionState`

#### Scenario: Ядро читает историю в доменных VO
- **WHEN** ядру нужна история сообщений
- **THEN** `SessionView.messages()` возвращает `Sequence[ConversationMessage]` (доменные VO), не плоский protocol-history

#### Scenario: Живое чтение без снимка
- **WHEN** turn-loop дописывает сообщение в сессию по ходу turn-а
- **THEN** следующее чтение `SessionView.messages()` в том же turn-е отражает дописанное (адаптер читает сквозь живую `SessionState`, а не снимок)

#### Scenario: import-linter не видит ребра agent → protocol.state
- **WHEN** запускается контракт «Server layers»
- **THEN** `ignore_imports` контракта **пуст целиком** (не только для переведённых модулей), контракт зелёный, а импортов `protocol` внутри `server/agent/` нет
- **Примечание:** ослабленная формулировка «для модулей, переведённых на `SessionView`» была нужна, пока остаток (`storage`, цепочка `tools/`, `file_cache_decorator`) ждал write-фазы. Write-фаза выполнена фазой D ADR-006, поэтому признак усилен до пустого списка исключений

### Requirement: Порт ContentCodec
Ядро MUST декодировать входной контент через порт `ContentCodec`, а ACP-специфичный
маппинг MUST находиться в адаптере (`protocol/`), не в ядре.

#### Scenario: Декодирование контента через порт
- **WHEN** `HistoryBuilder` строит сообщение из входного контента
- **THEN** оно вызывает `ContentCodec.decode(blocks) -> list[ContentPart]`, не зная про ACP `ContentBlock`

#### Scenario: ACP-форма контента отсутствует в ядре
- **WHEN** сканируются импорты `server/agent/`
- **THEN** `agent/acp_content_mapper.py` отсутствует, ACP-специфика контента живёт в `protocol/` как `ACPContentCodec`

### Requirement: Порт ToolGateway
Ядро MUST исполнять инструменты через порт `ToolGateway` (сужение `ToolRegistry`).

#### Scenario: Исполнение инструмента через порт
- **WHEN** стратегии исполняют tool call
- **THEN** используется `ToolGateway.execute_tool(...)` → `ToolExecutionResult`

### Requirement: Порт UpdateSink
Ядро MUST эмитить прогресс turn-а через порт `UpdateSink` в доменных терминах; ACP wire
`session/update` MUST собираться внутри адаптера.

#### Scenario: Эмиссия обновления в доменных терминах
- **WHEN** ядро сообщает о tool call / плане / тексте
- **THEN** оно вызывает `UpdateSink.emit_tool_call/emit_plan/emit_agent_message` с доменными объектами, не с `ACPMessage`

#### Scenario: ACP wire-формат сохранён байт-в-байт
- **WHEN** ACP-адаптер `UpdateSink` мапит доменное событие в `session/update`
- **THEN** wire-формат нотификации байт-идентичен прежнему (golden-тест)

### Requirement: Driving-порт AgentRunner
ACP-обвязка MUST входить в turn ядра через driving-порт `AgentRunner`, что позволяет
подключать не-ACP драйверы без изменения ядра.

#### Scenario: ACP-адаптер запускает turn через порт
- **WHEN** приходит `session/prompt`
- **THEN** turn-loop (ACP-адаптер) вызывает `AgentRunner.run_turn(SessionView, TurnRequest)`

#### Scenario: Не-ACP драйвер запускает тот же turn
- **WHEN** тест-харнесс (без `protocol/`) вызывает `AgentRunner.run_turn`
- **THEN** turn проходит корректно, ядро не импортирует `protocol/`
