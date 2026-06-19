## Why

Текущий PromptInput — это простое многострочное поле ввода с кнопками Send/Stop. Все настройки сессии (Model, Session Mode, Agent, Strategy) доступны только через модальные окна по горячим клавишам, без видимых индикаторов текущих значений в основном интерфейсе. Это снижает discoverability и требует от пользователя запоминания комбинаций клавиш.

Необходимо переработать PromptInput в единый блок с inline-селекторами, чтобы пользователь мог видеть и менять настройки сессии непосредственно в области ввода.

## What Changes

- **PromptInput** переработан из `Horizontal` (TextArea + кнопки) в `Vertical` контейнер с двумя зонами:
  - Верхняя: многострочное поле ввода с placeholder "Type your task, use @ to add files or / for commands" и кнопкой expand (↗) в правом верхнем углу
  - Нижняя: горизонтальный тулбар с 4 inline-dropdown селекторами (Model, Session Mode, Agent, Strategy), кнопкой "+" (заглушка) и кнопкой Send/Stop
- **InlineSelector** — новый виджет для отображения label + текущее значение + стрелка dropdown
- **QuickActionsBar** удалён из dock-region (функциональность дублируется горячими клавишами)
- **Expand кнопка** переключает высоту TextArea между обычной (6 строк) и развёрнутой (весь dock-region)
- **Горячие клавиши** сохраняются: `Ctrl+M` (Model), `Ctrl+Shift+M` (Session Mode), `Ctrl+A` (Agent), `Ctrl+Shift+A` (Strategy)

## Capabilities

### New Capabilities
- `inline-prompt-selectors`: Inline-dropdown селекторы Model, Session Mode, Agent, Strategy в PromptInput с отображением текущих значений и возможностью выбора через клик или горячую клавишу

### Modified Capabilities
- (none — существующие specs не меняют требований на уровне поведения)

## Impact

**Файлы:**
- `src/codelab/client/tui/components/prompt_input.py` — полная переработка
- `src/codelab/client/tui/components/inline_selector.py` — новый файл
- `src/codelab/client/tui/app.py` — передача view_model в PromptInput, удаление QuickActionsBar
- `src/codelab/client/tui/styles/app.tcss` — новые стили
- `src/codelab/client/tui/components/quick_actions_bar.py` — удаление из compose (файл сохраняется)

**ViewModels:** без изменений (ModelSelectorViewModel, ConfigOptionSelectorViewModel уже предоставляют нужные Observable)

**Протоколы:** без изменений (ACP/MCP не затрагиваются)

**Тесты:** обновление тестов PromptInput, новые тесты InlineSelector
