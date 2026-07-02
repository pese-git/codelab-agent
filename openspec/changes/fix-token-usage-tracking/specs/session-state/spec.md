## ADDED Requirements

### Requirement: SessionMetrics token usage tracking
Система SHALL обновлять `SessionState.session_metrics` для отслеживания token usage после каждого LLM call.

#### Scenario: SessionMetrics lazy initialization
- **WHEN** AgentLoop завершает LLM call с response.usage
- **WHEN** `session.session_metrics is None`
- **THEN** система ДОЛЖНА инициализировать `session.session_metrics = SessionMetrics()`
- **THEN** система ДОЛЖНА установить начальные значения из response.usage

#### Scenario: SessionMetrics accumulation
- **WHEN** AgentLoop завершает LLM call с response.usage
- **WHEN** `session.session_metrics` уже инициализирован
- **THEN** система ДОЛЖНА инкрементировать `input_tokens`, `output_tokens`, `total_tokens`
- **THEN** система ДОЛЖНА инкрементировать `total_llm_calls`

#### Scenario: SessionMetrics preservation across turns
- **WHEN** сессия имеет накопленные session_metrics
- **WHEN** начинается новый prompt turn
- **THEN** session_metrics ДОЛЖЕН сохраняться между turns
- **THEN** новые токены ДОЛЖНЫ аккумулироваться к существующим значениям
