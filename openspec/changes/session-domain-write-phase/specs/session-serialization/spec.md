# Delta-спецификация session-serialization

## MODIFIED Requirements

### Requirement: Рабочая модель — доменный агрегат, SessionState — сериализационный DTO
Сервер MUST оперировать `domain.Session` как рабочим агрегатом turn-пути. `protocol.state.SessionState`
MUST использоваться только как сериализационный DTO на границе wire/storage, через единственную точку
конвертации `SessionMapper`. `storage` и `tools`-executor'ы MUST НЕ зависеть от `SessionState`.

#### Scenario: Домен — рабочая модель
- **WHEN** хендлеры turn-а изменяют состояние сессии (`active_turn`/`history`/`tool_calls`/`plan`)
- **THEN** мутируется `domain.Session` (доменные операции), а не Pydantic `SessionState`

#### Scenario: SessionState только на границе
- **WHEN** сессия уходит в wire или в storage
- **THEN** `domain.Session` конвертируется в `SessionState` через `SessionMapper`; вне границы `SessionState` не используется

#### Scenario: Round-trip без потерь
- **WHEN** `domain.Session → SessionState → domain.Session`
- **THEN** сохраняются tool_calls, роль `tool`/tool_call_id, plan, multimodal content, permissions, multi-agent state

#### Scenario: Server layers без исключений для agent
- **WHEN** запускается `import-linter` контракт «Server layers»
- **THEN** `ignore_imports` не содержит рёбер `agent`/`storage`/`tools` → `protocol.state` (ADR-003 закрыт)

### Requirement: Изменение формата хранения — с миграцией
Формат сериализации сессий MAY измениться (versioned schema). Change MUST сохранить обратно-совместимое
**чтение** ранее сохранённых сессий (upgrade на чтении). Запись MAY идти в новом формате.

#### Scenario: Чтение старой сессии
- **WHEN** загружается сессия в старом формате (`SessionState`-JSON текущей schema_version)
- **THEN** она распознаётся и апгрейдится в `domain.Session` без потери данных

#### Scenario: Запись в новом формате
- **WHEN** сессия сохраняется после миграции
- **THEN** используется новый versioned формат; повторное чтение эквивалентно

### Requirement: Wire session/update байт-в-байт
Изменение рабочей модели MUST НЕ менять wire-формат `session/update` (`agent_message_chunk`, `plan`,
`tool_call`, `tool_call_update`).

#### Scenario: Golden wire
- **WHEN** turn эмитит `session/update` любого типа
- **THEN** байтовый вывод идентичен зафиксированным golden-фикстурам
