# Спецификация: TUI Multimodal Widgets

## ДОБАВЛЕННЫЕ Требования

### Требование: ImageContentWidget

Система ДОЛЖНА предоставлять `ImageContentWidget` для отображения информации об изображении в терминале.

#### Сценарий: Создание виджета с данными изображения
- **КОГДА** создаётся `ImageContentWidget` с `data`, `mime_type`, `uri`
- **ТОГДА** виджет отображает иконку 🖼️, MIME type, размер данных в KB/MB

#### Сценарий: Создание из content block
- **КОГДА** вызван `ImageContentWidget.from_content_block({"type": "image", "data": "...", "mimeType": "image/png"})`
- **ТОГДА** возвращён виджет с корректными данными

### Требование: AudioContentWidget

Система ДОЛЖНА предоставлять `AudioContentWidget` для отображения информации об аудио в терминале.

#### Сценарий: Создание виджета с данными аудио
- **КОГДА** создаётся `AudioContentWidget` с `data`, `mime_type`
- **ТОГДА** виджет отображает иконку 🔊, MIME type, размер данных в KB/MB

#### Сценарий: Создание из content block
- **КОГДА** вызван `AudioContentWidget.from_content_block({"type": "audio", "data": "...", "mimeType": "audio/wav"})`
- **ТОГДА** возвращён виджет с корректными данными

### Требование: MessageBubble поддержка content_blocks

`MessageBubble` ДОЛЖНА поддерживать параметр `content_blocks` для рендеринга multimodal контента.

#### Сценарий: Рендеринг text content block
- **КОГДА** `content_blocks` содержит `{"type": "text", "text": "Hello"}`
- **ТОГДА** отображается текст через `MessageContent`

#### Сценарий: Рендеринг image content block
- **КОГДА** `content_blocks` содержит `{"type": "image", ...}`
- **ТОГДА** отображается `ImageContentWidget`

#### Сценарий: Рендеринг audio content block
- **КОГДА** `content_blocks` содержит `{"type": "audio", ...}`
- **ТОГДА** отображается `AudioContentWidget`

#### Сценарий: Рендеринг resource content block
- **КОГДА** `content_blocks` содержит `{"type": "resource", ...}`
- **ТОГДА** отображается как текст с URI и содержимым

### Требование: Метод update_content_blocks

`MessageBubble` ДОЛЖНА предоставлять метод `update_content_blocks()` для динамического обновления контента.

#### Сценарий: Обновление content blocks
- **КОГДА** вызван `update_content_blocks(new_blocks)`
- **ТОГДА** виджет перерисовывается с новым контентом
