## 1. InlineSelector виджет

- [ ] 1.1 Создать файл `src/codelab/client/tui/components/inline_selector.py` с классом `InlineSelector(Static)`
- [ ] 1.2 Реализовать подписку на Observable view_model для обновления отображаемого значения
- [ ] 1.3 Реализовать обработку клика → вызов open_callback
- [ ] 1.4 Добавить DEFAULT_CSS для стилизации (compact, clickable, hover, selected state)
- [ ] 1.5 Написать unit-тесты для InlineSelector

## 2. Переработка PromptInput

- [ ] 2.1 Изменить PromptInput с `Horizontal` на `Vertical` контейнер
- [ ] 2.2 Добавить placeholder "Type your task, use @ to add files or / for commands" в TextArea
- [ ] 2.3 Добавить кнопку expand (↗) в правый верхний угол TextArea
- [ ] 2.4 Реализовать expand toggle (CSS class переключение высоты)
- [ ] 2.5 Создать toolbar с 4 InlineSelector виджетами (Model, Session Mode, Agent, Strategy)
- [ ] 2.6 Переместить кнопки Send/Stop в правую часть toolbar
- [ ] 2.7 Обновить конструктор: принять 4 view_model + app callback для открытия модалов
- [ ] 2.8 Обновить DEFAULT_CSS для нового layout
- [ ] 2.9 Написать/обновить тесты для PromptInput

## 3. Интеграция в app.py

- [ ] 3.1 Обновить `_mount_main_layout_children()`: передать view_model в PromptInput
- [ ] 3.2 Удалить монтирование QuickActionsBar из dock-region
- [ ] 3.3 Убедиться что горячие клавиши (Ctrl+M, Ctrl+Shift+M, Ctrl+A, Ctrl+Shift+A) работают

## 4. CSS стили

- [ ] 4.1 Добавить стили для `#prompt-input` (vertical layout, border)
- [ ] 4.2 Добавить стили для `#prompt-toolbar` (horizontal, compact)
- [ ] 4.3 Добавить стили для `InlineSelector` (hover, focus, dropdown indicator)
- [ ] 4.4 Добавить стили для `.expanded` состояния TextArea
- [ ] 4.5 Обновить `#dock-region` min-height для размещения toolbar

## 5. Проверки

- [ ] 5.1 Запустить `make check` (ruff + ty + pytest)
- [ ] 5.2 Визуальная проверка в TUI
