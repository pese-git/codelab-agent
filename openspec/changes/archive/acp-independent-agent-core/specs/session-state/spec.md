# Delta-спецификация session-state

## MODIFIED Requirements

### Requirement: Развязка ядра агента от SessionState
Ядро агента (`server/agent/`) MUST НЕ зависеть от `protocol.state.SessionState`. Доступ к
данным сессии из ядра идёт через порт `SessionView` (см. capability `agent-ports`).
`SessionState` остаётся протокольно-персистентной моделью и мутируется только в `protocol/`.

#### Scenario: Ядро не импортирует SessionState
- **WHEN** сканируются импорты модулей `server/agent/` (после выполнения фаз)
- **THEN** `protocol.state.SessionState` не импортируется; используется порт `SessionView`

#### Scenario: SessionState продолжает быть моделью сериализации
- **WHEN** сессия сохраняется/загружается через storage
- **THEN** используется `SessionState` (Pydantic); поведение сериализации не меняется

#### Scenario: Мутации сессии остаются в protocol
- **WHEN** turn-loop дописывает `history`/`latest_plan`
- **THEN** мутируется `SessionState` в `protocol/`; ядро видит изменения через живой `SessionView` (read-only)

#### Scenario: Обратная совместимость формата сессии
- **WHEN** загружается ранее сохранённая сессия
- **THEN** формат `SessionState` и schema_version не изменяются этим change (только развязка чтения в ядре)
