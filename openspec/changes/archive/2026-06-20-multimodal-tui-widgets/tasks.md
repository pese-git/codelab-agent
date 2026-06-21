## 1. ImageContentWidget

- [x] 1.1 Создать `src/codelab/client/tui/components/image_content.py`
- [x] 1.2 Реализовать отображение иконки 🖼️ и заголовка "Изображение"
- [x] 1.3 Реализовать отображение MIME type и размера данных
- [x] 1.4 Реализовать factory метод `from_content_block()`
- [x] 1.5 Написать unit тесты (4 теста)

## 2. AudioContentWidget

- [x] 2.1 Создать `src/codelab/client/tui/components/audio_content.py`
- [x] 2.2 Реализовать отображение иконки 🔊 и заголовка "Аудио"
- [x] 2.3 Реализовать отображение MIME type и размера данных
- [x] 2.4 Реализовать factory метод `from_content_block()`
- [x] 2.5 Написать unit тесты (3 теста)

## 3. MessageBubble multimodal поддержка

- [x] 3.1 Добавить параметр `content_blocks` в `__init__`
- [x] 3.2 Реализовать метод `_render_content_blocks()`
- [x] 3.3 Добавить обработку типов: text, image, audio, resource, resource_link
- [x] 3.4 Реализовать метод `update_content_blocks()`
- [x] 3.5 Обновить `from_dict()` для поддержки content_blocks
- [x] 3.6 Написать unit тесты (5 тестов)

## 4. Интеграция

- [x] 4.1 Все 6688 тестов проходят
- [x] 4.2 Ruff check проходит
- [x] 4.3 Type check проходит
