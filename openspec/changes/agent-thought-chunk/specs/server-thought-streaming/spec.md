## ADDED Requirements

### Requirement: ReplayManager save_thought_chunk
Система SHALL предоставлять метод `save_thought_chunk(session, content)` в `ReplayManager` для сохранения thought chunks в events_history.

#### Scenario: Save thought chunk
- **WHEN** вызван `save_thought_chunk(session, {"type": "text", "text": "reasoning..."})`
- **THEN** в `events_history` сессии ДОЛЖЕН быть добавлен элемент с `sessionUpdate: "agent_thought_chunk"`
- **THEN** элемент ДОЛЖЕН содержать переданный content

#### Scenario: Thought chunk in replayable types
- **WHEN** `agent_thought_chunk` добавлен в events_history
- **THEN** он ДОЛЖЕН быть включён в `_REPLAYABLE_UPDATE_TYPES`
- **THEN** при replay он ДОЛЖЕН быть воспроизведён

### Requirement: AgentLoop thought notification emission
Система SHALL эмитить `agent_thought_chunk` notification при наличии reasoning в ответе LLM.

#### Scenario: Emit thought before message
- **WHEN** `CompletionResponse` содержит непустой `reasoning`
- **WHEN** `CompletionResponse` содержит `text`
- **THEN** система ДОЛЖНА эмитить `agent_thought_chunk` ПЕРЕД `agent_message_chunk`

#### Scenario: Emit thought without message
- **WHEN** `CompletionResponse` содержит непустой `reasoning`
- **WHEN** `CompletionResponse` НЕ содержит `text` (или пустой)
- **THEN** система ДОЛЖНА эмитить `agent_thought_chunk`

#### Scenario: No thought when reasoning is None
- **WHEN** `CompletionResponse.reasoning` равен `None`
- **THEN** система НЕ ДОЛЖНА эмитить `agent_thought_chunk`

#### Scenario: No thought when reasoning is empty
- **WHEN** `CompletionResponse.reasoning` равен пустой строке
- **THEN** система НЕ ДОЛЖНА эмитить `agent_thought_chunk`

### Requirement: Thought notification format
Система SHALL формировать `agent_thought_chunk` notification согласно ACP спецификации.

#### Scenario: Notification structure
- **WHEN** система эмитит `agent_thought_chunk`
- **THEN** notification ДОЛЖЕН иметь структуру:
  ```json
  {
    "jsonrpc": "2.0",
    "method": "session/update",
    "params": {
      "sessionId": "<session_id>",
      "update": {
        "sessionUpdate": "agent_thought_chunk",
        "content": {"type": "text", "text": "<reasoning_text>"}
      }
    }
  }
  ```

#### Scenario: Notification via immediate delivery
- **WHEN** `notification_callback` установлен в AgentLoop
- **THEN** `agent_thought_chunk` ДОЛЖЕН быть отправлен через callback немедленно

#### Scenario: Notification via list accumulation
- **WHEN** `notification_callback` НЕ установлен
- **THEN** `agent_thought_chunk` ДОЛЖЕН быть добавлен в список `notifications`

### Requirement: StrategyDispatcher thought emission
Система SHALL эмитить `agent_thought_chunk` в `StrategyDispatcher` при наличии reasoning.

#### Scenario: Dispatcher with reasoning response
- **WHEN** `StrategyDispatcher` получает ответ с reasoning
- **THEN** dispatcher ДОЛЖЕН эмитить `agent_thought_chunk` notification
- **THEN** notification ДОЛЖЕН быть отправлен через `notification_callback`

### Requirement: Thought chunk in events_history order
Система SHALL сохранять thought chunks в events_history в порядке их появления.

#### Scenario: Order preservation
- **WHEN** в одном turn эмитируются thought chunk и message chunk
- **THEN** thought chunk ДОЛЖЕН быть сохранён в events_history ПЕРЕД message chunk
- **THEN** при replay порядок ДОЛЖЕН быть сохранён

#### Scenario: Multiple thought chunks
- **WHEN** в одном turn эмитируются несколько thought chunks
- **THEN** все chunks ДОЛЖНЫ быть сохранены в порядке появления
