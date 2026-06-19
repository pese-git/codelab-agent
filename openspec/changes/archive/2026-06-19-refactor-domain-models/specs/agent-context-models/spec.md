# Spec: agent-context-models

## ADDED Requirements

### Requirement: Domain UserPrompt

Система SHALL предоставлять `UserPrompt` как frozen dataclass:
- `text: str` — текстовое содержимое
- `resources: list[Resource]` — встроенные ресурсы
- `images: list[Image]` — изображения

#### Scenario: Создание UserPrompt с текстом
- **WHEN** система создает UserPrompt с текстом
- **THEN** UserPrompt содержит поле `text` с указанным содержимым

#### Scenario: Создание UserPrompt с мультимодальным контентом
- **WHEN** система создает UserPrompt с ресурсами и изображениями
- **THEN** UserPrompt содержит поля `resources` и `images` с указанными данными

### Requirement: UserPrompt Business Logic

`UserPrompt` SHALL предоставлять:
- `has_multimodal` property — проверка наличия мультимодального контента
- `get_text_preview(max_length: int)` — получение текстового превью

#### Scenario: Проверка наличия мультимодального контента
- **WHEN** UserPrompt содержит ресурсы или изображения
- **THEN** property `has_multimodal` возвращает `true`

#### Scenario: Получение текстового превью
- **WHEN** вызывается `get_text_preview(max_length)`
- **THEN** возвращается текст, ограниченный указанной длиной

### Requirement: Domain AgentContext с UserPrompt

Система SHALL обновить `AgentContext` для использования `UserPrompt`:
- `prompt: UserPrompt` — domain model вместо `list[dict]`

#### Scenario: Использование UserPrompt в AgentContext
- **WHEN** создается AgentContext
- **THEN** поле `prompt` имеет тип `UserPrompt` вместо `list[dict]`

### Requirement: PromptMapper

Система SHALL предоставлять `PromptMapper` с методами:
- `from_acp_blocks(blocks: list[dict]) -> UserPrompt` — конвертировать ACP в domain
- `to_acp_blocks(prompt: UserPrompt) -> list[dict]` — конвертировать domain в ACP

#### Scenario: Конвертация ACP блоков в UserPrompt
- **WHEN** вызывается `from_acp_blocks` с ACP content blocks
- **THEN** возвращается UserPrompt с соответствующими текстом, ресурсами и изображениями

#### Scenario: Конвертация UserPrompt в ACP блоки
- **WHEN** вызывается `to_acp_blocks` с UserPrompt
- **THEN** возвращается список ACP content blocks

### Requirement: Миграция AgentContext

Система SHALL мигрировать все использования `AgentContext.prompt` на `UserPrompt`.

#### Scenario: Миграция кодовой базы
- **WHEN** код использует `AgentContext.prompt`
- **THEN** используется тип `UserPrompt` вместо `list[dict]`
