## MODIFIED Requirements

### Requirement: SessionState как ACP Protocol Model
Система SHALL обновить `SessionState` как ACP Protocol Model:
- Обновить структуру с использованием value objects
- Делегировать бизнес-логику domain агрегатам
- Поддерживать миграцию schema_version: 3 → 4

#### Scenario: SessionState как ACP Protocol Model
- **WHEN** используется SessionState
- **THEN** он соответствует ACP спецификации для session state

#### Scenario: Делегирование бизнес-логики
- **WHEN** SessionState используется для хранения состояния
- **THEN** бизнес-логика делегирована domain Session агрегату

### Requirement: ChatSessionState thinking support
Система SHALL расширить `ChatSessionState` (клиентский state) полями для хранения thinking state.

#### Scenario: thinking_text field
- **WHEN** `ChatSessionState` инициализирован
- **THEN** поле `thinking_text: str` ДОЛЖНО быть инициализировано пустой строкой

#### Scenario: is_thinking_streaming field
- **WHEN** `ChatSessionState` инициализирован
- **THEN** поле `is_thinking_streaming: bool` ДОЛЖНО быть инициализировано `False`

#### Scenario: append_streaming_thought method
- **WHEN** вызван `append_streaming_thought(text)`
- **THEN** `thinking_text` ДОЛЖЕН быть дополнен переданным текстом
- **THEN** `is_thinking_streaming` ДОЛЖЕН быть установлен в `True`

#### Scenario: finalize_thinking method
- **WHEN** вызван `finalize_thinking()`
- **THEN** `thinking_text` ДОЛЖЕН быть сброшен в пустую строку
- **THEN** `is_thinking_streaming` ДОЛЖЕН быть установлен в `False`

#### Scenario: clear resets thinking
- **WHEN** вызван `ChatSessionState.clear()`
- **THEN** `thinking_text` ДОЛЖЕН быть сброшен в пустую строку
- **THEN** `is_thinking_streaming` ДОЛЖЕН быть сброшен в `False`
