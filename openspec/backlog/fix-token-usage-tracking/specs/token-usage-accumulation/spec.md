## ADDED Requirements

### Requirement: Token usage accumulation in SessionState
Система SHALL аккумулировать token usage метрики в `SessionState.session_metrics` после каждого LLM call в AgentLoop.

#### Scenario: First LLM call initializes SessionMetrics
- **WHEN** AgentLoop.run() завершает LLM call
- **WHEN** `session.session_metrics is None`
- **THEN** система ДОЛЖНА инициализировать `session.session_metrics = SessionMetrics()`
- **THEN** система ДОЛЖНА аккумулировать `input_tokens`, `output_tokens`, `total_tokens` из response.usage

#### Scenario: Subsequent LLM calls accumulate tokens
- **WHEN** AgentLoop.run() завершает LLM call
- **WHEN** `session.session_metrics` уже инициализирован
- **THEN** система ДОЛЖНА инкрементировать `input_tokens`, `output_tokens`, `total_tokens`
- **THEN** система ДОЛЖНА инкрементировать `total_llm_calls`

#### Scenario: Token usage from multiple iterations
- **WHEN** AgentLoop выполняет несколько итераций (tool calling loop)
- **THEN** система ДОЛЖНА аккумулировать токены из каждой итерации
- **THEN** `session.session_metrics.total_llm_calls` ДОЛЖЕН отражать количество итераций

### Requirement: Token usage from AgentResponse
Система SHALL извлекать token usage из `AgentResponse.usage` и аккумулировать в SessionMetrics.

#### Scenario: Extract usage from AgentResponse
- **WHEN** AgentLoop получает AgentResponse от стратегии
- **WHEN** `response.usage` не None
- **THEN** система ДОЛЖНА извлечь `input_tokens`, `output_tokens`, `total_tokens`
- **THEN** система ДОЛЖНА аккумулировать их в `session.session_metrics`

#### Scenario: Handle missing usage gracefully
- **WHEN** AgentLoop получает AgentResponse
- **WHEN** `response.usage is None`
- **THEN** система НЕ ДОЛЖНА обновлять session_metrics
- **THEN** система НЕ ДОЛЖНА вызывать исключения

### Requirement: SessionMetrics persistence
Система SHALL сохранять session_metrics при сериализации SessionState.

#### Scenario: SessionMetrics included in serialization
- **WHEN** SessionState сериализуется для хранения
- **WHEN** `session.session_metrics` не None
- **THEN** session_metrics ДОЛЖЕН быть включён в сериализованные данные

#### Scenario: SessionMetrics restored on load
- **WHEN** SessionState загружается из хранилища
- **WHEN** сериализованные данные содержат session_metrics
- **THEN** `session.session_metrics` ДОЛЖЕН быть восстановлен
