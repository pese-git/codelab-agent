## ADDED Requirements

### Requirement: InlineSelector виджет
Система SHALL предоставлять виджет `InlineSelector`, который отображает label и текущее значение config option с визуальным индикатором dropdown (▾).

#### Scenario: Отображение текущего значения
- **WHEN** InlineSelector инициализирован с view_model, имеющим текущее значение
- **THEN** виджет SHALL отображать текст в формате `Label: Value ▾`

#### Scenario: Обновление при изменении значения
- **WHEN** view_model публикует новое значение через Observable
- **THEN** InlineSelector SHALL обновить отображаемый текст без перезагрузки

#### Scenario: Открытие модала по клику
- **WHEN** пользователь кликает на InlineSelector
- **THEN** система SHALL вызвать callback открытия соответствующего модала выбора

#### Scenario: Открытие модала по горячей клавише
- **WHEN** пользователь нажимает назначенную горячую клавишу (Ctrl+M, Ctrl+Shift+M, Ctrl+A, Ctrl+Shift+A)
- **THEN** система SHALL открыть соответствующий модал выбора

### Requirement: Переработанный PromptInput
PromptInput SHALL быть Vertical контейнером с двумя зонами: полем ввода сверху и тулбаром снизу.

#### Scenario: Отображение поля ввода с placeholder
- **WHEN** PromptInput смонтирован
- **THEN** TextArea SHALL отображать placeholder "Type your task, use @ to add files or / for commands"

#### Scenario: Отображение тулбара с 4 селекторами
- **WHEN** PromptInput смонтирован
- **THEN** тулбар SHALL содержать InlineSelector для Model, Session Mode, Agent, Strategy

#### Scenario: Кнопка Send отображается когда агент не streaming
- **WHEN** `is_streaming` в ChatViewModel равен False
- **THEN** кнопка Send SHALL быть видима, кнопка Stop SHALL быть скрыта

#### Scenario: Кнопка Stop отображается во время streaming
- **WHEN** `is_streaming` в ChatViewModel равен True
- **THEN** кнопка Stop SHALL быть видима, кнопка Send SHALL быть скрыта, TextArea SHALL быть disabled

#### Scenario: Expand toggle
- **WHEN** пользователь нажимает кнопку expand (↗)
- **THEN** высота TextArea SHALL переключаться между обычной (6 строк) и развёрнутой (весь dock-region)

### Requirement: Удаление QuickActionsBar из dock-region
QuickActionsBar SHALL быть удалён из dock-region в main layout.

#### Scenario: QuickActionsBar не монтируется
- **WHEN** приложение запускается
- **THEN** QuickActionsBar SHALL НЕ присутствовать в dock-region

### Requirement: Горячие клавиши селекторов
Горячие клавиши для выбора Model, Session Mode, Agent, Strategy SHALL оставаться функциональными.

#### Scenario: Ctrl+M открывает выбор модели
- **WHEN** пользователь нажимает Ctrl+M
- **THEN** система SHALL открыть ModelSelectorModal

#### Scenario: Ctrl+Shift+M открывает выбор режима
- **WHEN** пользователь нажимает Ctrl+Shift+M
- **THEN** система SHALL открыть ConfigOptionSelectorModal для Session Mode

#### Scenario: Ctrl+A открывает выбор агента
- **WHEN** пользователь нажимает Ctrl+A
- **THEN** система SHALL открыть ConfigOptionSelectorModal для Agent

#### Scenario: Ctrl+Shift+A открывает выбор стратегии
- **WHEN** пользователь нажимает Ctrl+Shift+A
- **THEN** система SHALL открыть ConfigOptionSelectorModal для Strategy
