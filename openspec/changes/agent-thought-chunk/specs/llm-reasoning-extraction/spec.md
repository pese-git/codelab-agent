## ADDED Requirements

### Requirement: CompletionResponse reasoning field
Система SHALL расширить `CompletionResponse` полем `reasoning: str | None = None` для хранения internal reasoning LLM.

#### Scenario: Response with reasoning
- **WHEN** LLM провайдер возвращает reasoning контент
- **THEN** `CompletionResponse.reasoning` ДОЛЖЕН содержать текст reasoning

#### Scenario: Response without reasoning
- **WHEN** LLM провайдер не возвращает reasoning контент
- **THEN** `CompletionResponse.reasoning` ДОЛЖЕН быть `None`

### Requirement: Anthropic thinking extraction
Система SHALL извлекать thinking content blocks из ответов Anthropic API.

#### Scenario: Anthropic response with thinking block
- **WHEN** Anthropic API возвращает response с `content[].type == "thinking"`
- **THEN** система ДОЛЖНА извлечь текст из thinking block
- **THEN** `CompletionResponse.reasoning` ДОЛЖЕН содержать этот текст

#### Scenario: Anthropic response without thinking
- **WHEN** Anthropic API возвращает response без thinking blocks
- **THEN** `CompletionResponse.reasoning` ДОЛЖЕН быть `None`

#### Scenario: Anthropic streaming with thinking
- **WHEN** Anthropic streaming response содержит thinking content blocks
- **THEN** система ДОЛЖНА агрегировать thinking chunks
- **THEN** `CompletionResponse.reasoning` ДОЛЖЕН содержать полный агрегированный текст

### Requirement: OpenAI reasoning extraction
Система SHALL извлекать `reasoning_content` из ответов OpenAI API (o1/o3 модели).

#### Scenario: OpenAI response with reasoning_content
- **WHEN** OpenAI API возвращает response с `choices[].message.reasoning_content`
- **THEN** система ДОЛЖНА извлечь reasoning_content
- **THEN** `CompletionResponse.reasoning` ДОЛЖЕН содержать этот текст

#### Scenario: OpenAI response without reasoning_content
- **WHEN** OpenAI API возвращает response без reasoning_content
- **THEN** `CompletionResponse.reasoning` ДОЛЖЕН быть `None`

### Requirement: OpenRouter reasoning extraction
Система SHALL извлекать reasoning из ответов OpenRouter API.

#### Scenario: OpenRouter response with reasoning
- **WHEN** OpenRouter API возвращает response с reasoning field
- **THEN** система ДОЛЖНА извлечь reasoning
- **THEN** `CompletionResponse.reasoning` ДОЛЖЕН содержать этот текст

#### Scenario: OpenRouter response without reasoning
- **WHEN** OpenRouter API возвращает response без reasoning
- **THEN** `CompletionResponse.reasoning` ДОЛЖЕН быть `None`

### Requirement: Provider backward compatibility
Система SHALL обеспечить обратную совместимость при отсутствии reasoning.

#### Scenario: Provider without reasoning support
- **WHEN** LLM провайдер не поддерживает reasoning (или не реализовал extraction)
- **THEN** `CompletionResponse.reasoning` ДОЛЖЕН быть `None`
- **THEN** существующая логика обработки ответа ДОЛЖНА работать без изменений

#### Scenario: Empty reasoning string
- **WHEN** LLM провайдер возвращает пустую строку reasoning
- **THEN** система ДОЛЖНА трактовать это как отсутствие reasoning
- **THEN** `agent_thought_chunk` НЕ ДОЛЖЕН быть эмитирован
