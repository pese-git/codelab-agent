# Spec: agent-context-models

## ADDED Requirements

### Требование: Domain UserPrompt

Система ДОЛЖНА предоставлять `UserPrompt` как frozen dataclass:
- `text: str` — текстовое содержимое
- `resources: list[Resource]` — встроенные ресурсы
- `images: list[Image]` — изображения

### Требование: UserPrompt Business Logic

`UserPrompt` ДОЛЖЕН предоставлять:
- `has_multimodal` property — проверка наличия мультимодального контента
- `get_text_preview(max_length: int)` — получение текстового превью

### Требование: Domain AgentContext с UserPrompt

Система ДОЛЖНА обновить `AgentContext` для использования `UserPrompt`:
- `prompt: UserPrompt` — domain model вместо `list[dict]`

### Требование: PromptMapper

Система ДОЛЖНА предоставлять `PromptMapper` с методами:
- `from_acp_blocks(blocks: list[dict]) -> UserPrompt` — конвертировать ACP в domain
- `to_acp_blocks(prompt: UserPrompt) -> list[dict]` — конвертировать domain в ACP

### Требование: Миграция AgentContext

Система ДОЛЖНА мигрировать все использования `AgentContext.prompt` на `UserPrompt`.
