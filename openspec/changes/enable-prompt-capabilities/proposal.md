## Почему

ACP сервер объявляет `promptCapabilities: {image: false, audio: false, embeddedContext: false}` в ответе на `initialize`, хотя спецификация ACP требует поддержки `text` и `resource_link` как baseline, а `image` и `resource` (embedded context) — как опциональные capabilities. Это блокирует клиентов от отправки multimodal контента (изображения, embedded resources), ограничивая взаимодействие только текстом. Включение `image` и `embeddedContext` позволит клиентам отправлять изображения для анализа и встраивать ресурсы (файлы, контекст) напрямую в промпт.

## Что изменяется

- Сервер объявляет `promptCapabilities.image: true` и `promptCapabilities.embeddedContext: true` в handshake
- Валидация `session/prompt` принимает content types `image` и `resource` согласно ACP 06-Content.md
- Введён domain model `ContentPart` для представления multimodal content в pipeline
- HistoryBuilder конвертирует multimodal content blocks в формат, понятный LLM providers
- OpenAI и Anthropic providers форматируют image content для соответствующих API (image_url / image block)
- Runtime capability check: если LLM provider не поддерживает vision, image блоки gracefully fallback-ят в text description
- **Audio остаётся отложенным** — требует отдельной поддержки (транскрипция или audio-capable модели)

## Возможности

### Новые возможности

- `prompt-multimodal-content`: Поддержка image и embedded resource content blocks в session/prompt. Включает: валидацию, domain model (ContentPart), маппинг ACP → domain, форматирование для LLM providers, capability-aware validation.

### Изменённые возможности

- `multi-provider-llm`: Добавляется требование поддержки vision capabilities (`supports_vision`) для OpenAI-compatible providers. Anthropic уже имеет `supports_vision=True`.
- `agent-lifecycle-events`: ExecutionEngine передаёт multimodal content через AgentContext (prompt field расширяется).

## Влияние

**Protocol Layer:**
- `server/protocol/handlers/auth.py` — capabilities: true
- `server/protocol/handlers/prompt.py` — validate_prompt_content: +image, +resource
- `server/protocol/content/validator.py` — REQUIRED_FIELDS sync с ACP spec

**Pipeline Layer:**
- `server/protocol/handlers/pipeline/context.py` — +content_parts field
- `server/protocol/handlers/prompt_orchestrator.py` — маппинг blocks → content_parts
- `server/protocol/handlers/pipeline/stages/validation.py` — multimodal empty check

**Agent Layer:**
- `server/llm/models.py` — LLMMessage.content: str | list[ContentPart]
- `server/agent/history_builder.py` — multimodal conversion
- `server/agent/execution_engine.py` — передаёт content_parts

**LLM Provider Layer:**
- `server/llm/providers/openai_compatible.py` — ContentPart → OpenAI format + supports_vision=True
- `server/llm/providers/anthropic.py` — ContentPart → Anthropic format

**New Files:**
- `server/llm/content_parts.py` — ContentPart domain model
- `server/protocol/content/acp_mapper.py` — ACP ContentBlock → ContentPart mapper

**Tests:**
- Unit tests для ContentPart, ACPContentMapper, валидации, providers
- Integration test: session/prompt с image → LLM

**Dependencies:** Нет новых зависимостей. Используются существующие Pydantic, dataclasses.

**Backward Compatibility:** Полная. Text-only путь не меняется. `LLMMessage.content: str` остаётся валидным.
