# Спецификация: Multi-Provider LLM (Дельта)

## ИЗМЕНЁННЫЕ Требования

### Требование: Возможности LLMProvider

Система ДОЛЖНА включать `supports_vision: bool` в `LLMCapabilities` для указания, может ли провайдер обрабатывать содержимое изображений в мультимодальных сообщениях.

#### Сценарий: OpenAI-совместимый провайдер поддерживает vision
- **КОГДА** обращён `OpenAICompatibleProvider.capabilities`
- **ТОГДА** возвращён `LLMCapabilities(supports_vision=True, ...)`

#### Сценарий: Провайдер Anthropic поддерживает vision
- **КОГДА** обращён `AnthropicProvider.capabilities`
- **ТОГДА** возвращён `LLMCapabilities(supports_vision=True, ...)`

#### Сценарий: Провайдер без поддержки vision
- **КОГДА** провайдер не поддерживает обработку изображений
- **ТОГДА** `LLMCapabilities.supports_vision` равен `False` и части содержимого image пропускаются с предупреждением в логе
