# agent-ports Specification

## Purpose

Порты, через которые ядро агента (`server/agent/core/`) взаимодействует с обвязкой. Ядро объявляет
порты в `agent/contracts/ports.py` и не зависит от протокольных моделей; ACP (`server/protocol/`) —
**один из** driving-адаптеров, рядом подключается не-ACP драйвер без изменения ядра.

Создано архивацией change `acp-independent-agent-core` (ADR-005). Незавершённая часть — доменная
эмиссия `UpdateSink` и прод-вход через `AgentRunner` — ведётся в change `agent-domain-emission`;
здесь она отражена как фактическое состояние портов, а не как требование.

## Requirements

### Requirement: Ядро не зависит от протокольных моделей

Ядро агента MUST зависеть только от портов, объявленных в `agent/contracts/ports.py`, и MUST НЕ
импортировать `server.protocol`.

#### Scenario: В ядре нет импортов протокола
- **WHEN** сканируются импорты `server/agent/`
- **THEN** импортов `codelab.server.protocol` нет ни одного

#### Scenario: import-linter подтверждает чистоту слоя
- **WHEN** запускается контракт «Server layers»
- **THEN** `ignore_imports` контракта **пуст**, контракт зелёный

#### Scenario: Новая зависимость от протокола объявляется портом
- **WHEN** ядру требуется новая возможность, которую сегодня даёт `protocol`
- **THEN** объявляется порт в `contracts/ports.py`, а не добавляется строка в `ignore_imports`

### Requirement: Порт SessionView

Ядро MUST читать данные сессии через read-only порт `SessionView`.

#### Scenario: Ядро читает конфигурацию и историю через порт
- **WHEN** `ExecutionEngine.build_context` нуждается в `cwd`, `config_values` или истории
- **THEN** оно получает их из `SessionView`, не из персистентной модели документа

#### Scenario: Порт удовлетворяется структурно, без конверсии
- **WHEN** ядру передаётся носитель состояния (доменный `Session`)
- **THEN** он удовлетворяет `SessionView` структурно — адаптера и конверсии нет, поэтому потери полей невозможны

#### Scenario: Живое чтение без снимка
- **WHEN** turn-loop дописывает сообщение в сессию по ходу turn-а
- **THEN** следующее чтение через `SessionView` в том же turn-е отражает дописанное

### Requirement: Порт ClientCapabilitiesView

Ядро MUST получать возможности клиента как feature-gate через порт `ClientCapabilitiesView`, не
завися от конкретной модели capabilities.

#### Scenario: tool_filter фильтрует инструменты через порт
- **WHEN** `tool_filter` отбирает инструменты по возможностям клиента
- **THEN** он типизирован против `ClientCapabilitiesView` (`fs_read`, `fs_write`, `terminal`)

#### Scenario: Обе модели capabilities удовлетворяют порт
- **WHEN** в ядро приходит персистентный `ClientRuntimeCapabilities` либо доменный `ClientCapabilities`
- **THEN** оба удовлетворяют порт структурно, конверсия не требуется

### Requirement: Порт ContentCodec

Ядро MUST декодировать входной контент через порт `ContentCodec`; протокольная форма контента MUST
находиться в адаптере.

#### Scenario: Декодирование через порт
- **WHEN** `HistoryBuilder` строит сообщение из входного контента
- **THEN** он вызывает `ContentCodec.decode(blocks) -> list[ContentPart]`, не зная про ACP `ContentBlock`

#### Scenario: ACP-форма контента отсутствует в ядре
- **WHEN** сканируется `server/agent/`
- **THEN** ACP-маппинг контента там отсутствует; он живёт в `protocol/content/acp_codec.py` как `ACPContentCodec`

#### Scenario: Без кодека мультимодальность схлопывается в текст
- **WHEN** кодек не инъектирован
- **THEN** мультимодальные блоки схлопываются в текст, а не тянут ACP-специфику в ядро

### Requirement: Порт ToolGateway

Ядро MUST исполнять инструменты через порт `ToolGateway`.

#### Scenario: Исполнение инструмента через порт
- **WHEN** стратегия исполняет tool call
- **THEN** используется `ToolGateway.execute_tool(...)` → `ToolExecutionResult`

### Requirement: Порт LLMPort

Ядро MUST вызывать модель через порт `LLMPort`, фиксирующий границу `LLMAdapter` (ADR-001).

#### Scenario: Вызов модели через порт
- **WHEN** ядру нужен вызов модели
- **THEN** он идёт через `LLMPort`, а не через конкретный провайдер

### Requirement: Порт ChildSessionFactory

Создание дочерних сессий субагентов MUST идти через порт `ChildSessionFactory`.

#### Scenario: Субагентская сессия создаётся через порт
- **WHEN** `ChildSessionManager` создаёт дочернюю сессию
- **THEN** он вызывает `ChildSessionFactory.create_session(...)`, не протокольную фабрику напрямую

### Requirement: Порт UpdateSink

Ядро MUST эмитить текст и стриминговые дельты через порт `UpdateSink`; ядро MUST НЕ конструировать
протокольные сообщения.

**Фактическое состояние:** порт объявлен с `emit_agent_message` и `emit_streaming_delta`. Доменные
`emit_plan` / `emit_tool_call` / `emit_tool_update` не объявлены — план и вызовы инструментов
эмитит turn-loop, который сам является ACP-адаптером. Доведение — change `agent-domain-emission`.

#### Scenario: Ядро не конструирует протокольное сообщение
- **WHEN** ядру нужно сообщить текст или дельту
- **THEN** оно вызывает `UpdateSink`, а `ACPMessage` строит адаптер

#### Scenario: Немедленная доставка
- **WHEN** ядро эмитит текст посреди turn-а
- **THEN** он доставляется немедленно, а не батчится к концу turn-а

### Requirement: Driving-порт AgentRunner

Драйвер MUST иметь возможность входить в turn ядра через порт `AgentRunner`, не завися от ACP.

**Фактическое состояние:** порт объявлен, `CoreAgentRunner` реализован; прод turn-loop входит в
ядро напрямую через `ExecutionEngine`. Перевод прод-пути — change `agent-domain-emission`.

#### Scenario: Не-ACP драйвер запускает turn
- **WHEN** тест-харнесс без `protocol/` вызывает `AgentRunner.run_turn` на фейковых портах
- **THEN** turn проходит корректно — это приёмочный признак драйвер-независимости ядра
