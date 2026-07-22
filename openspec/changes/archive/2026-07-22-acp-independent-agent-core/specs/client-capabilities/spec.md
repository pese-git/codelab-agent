# Delta-спецификация client-capabilities

## MODIFIED Requirements

### Requirement: Типизированная Session.capabilities
Ядро агента MUST оперировать client capabilities через доменный VO
`shared.capabilities.ClientCapabilities`, а НЕ через протокольную
`protocol.state.ClientRuntimeCapabilities`. Протокольная модель остаётся только
на границе сериализации (адаптер).

#### Scenario: tool_filter использует доменный VO
- **WHEN** `tool_filter` фильтрует инструменты по возможностям клиента
- **THEN** он получает `ClientCapabilities` через `SessionView.config.runtime_capabilities`, не `ClientRuntimeCapabilities`

#### Scenario: Round-trip без потери полей
- **WHEN** capabilities конвертируются protocol ↔ shared VO через `SessionMapper`
- **THEN** поля `image_prompts` и `embedded_context` сохраняются (не теряются при маппинге)

#### Scenario: Снятие дублирования концепции
- **WHEN** добавляется новая client capability
- **THEN** доменный VO `ClientCapabilities` — единственный источник для ядра; протокольная модель мапится на границе (устраняет расхождение, tech-debt P2-32)
