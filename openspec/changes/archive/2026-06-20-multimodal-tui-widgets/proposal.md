## Почему

После реализации multimodal контента (image/audio) в ACP протоколе, TUI клиент не имел возможности отображать этот контент. Пользователи видели только текстовые сообщения, что снижало UX при работе с multimodal агентами. Необходимо добавить placeholder виджеты для отображения информации об изображениях и аудио в терминале.

## Что изменяется

- Создан `ImageContentWidget` — placeholder для отображения информации об изображении (MIME type, размер, URI)
- Создан `AudioContentWidget` — placeholder для отображения информации об аудио (MIME type, размер)
- Обновлён `MessageBubble` для поддержки `content_blocks` с multimodal контентом
- Добавлен метод `_render_content_blocks()` для рендеринга различных типов контента

## Возможности

### Новые возможности

- `tui-image-content-widget`: Placeholder виджет для отображения информации об изображении в терминале
- `tui-audio-content-widget`: Placeholder виджет для отображения информации об аудио в терминале
- `tui-message-bubble-multimodal`: Поддержка multimodal content_blocks в MessageBubble

### Изменённые возможности

- `client-chat-persistence`: MessageBubble теперь поддерживает content_blocks

## Влияние

**Client TUI Layer:**
- `client/tui/components/image_content.py` — новый виджет ImageContentWidget
- `client/tui/components/audio_content.py` — новый виджет AudioContentWidget
- `client/tui/components/message_bubble.py` — поддержка content_blocks

**Tests:**
- `tests/client/tui/components/test_image_content.py` — 4 теста
- `tests/client/tui/components/test_audio_content.py` — 3 теста
- `tests/client/tui/components/test_message_bubble_multimodal.py` — 5 тестов

**Dependencies:** Нет новых зависимостей. Используются существующие Textual виджеты.

**Backward Compatibility:** Полная. Обычный текстовый контент работает как раньше.
