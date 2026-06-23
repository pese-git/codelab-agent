## ADDED Requirements

### Requirement: ThoughtPanel widget
Система SHALL предоставлять TUI виджет `ThoughtPanel` для отображения reasoning агента.

#### Scenario: ThoughtPanel creation
- **WHEN** `ThoughtPanel` создан
- **THEN** виджет ДОЛЖЕН быть свёрнут по умолчанию (`is_collapsed = True`)
- **THEN** заголовок ДОЛЖЕН быть "Reasoning"

#### Scenario: ThoughtPanel inherits CollapsiblePanel
- **WHEN** `ThoughtPanel` создан
- **THEN** виджет ДОЛЖЕН наследовать `CollapsiblePanel`
- **THEN** виджет ДОЛЖЕН поддерживать expand/collapse операции

### Requirement: ThoughtPanel content update
Система SHALL предоставлять метод `update_content(text)` для обновления содержимого reasoning.

#### Scenario: Update with text
- **WHEN** вызван `update_content("reasoning text...")`
- **THEN** содержимое Markdown виджета ДОЛЖНО быть обновлено
- **THEN** если panel была свёрнута, она ДОЛЖНА развернуться

#### Scenario: Update with empty text
- **WHEN** вызван `update_content("")`
- **THEN** содержимое ДОЛЖНО быть очищено
- **THEN** panel ДОЛЖНА остаться в текущем состоянии (не менять collapsed/expanded)

### Requirement: ThoughtPanel collapse after answer
Система SHALL предоставлять метод `collapse_after_answer()` для сворачивания после начала ответа.

#### Scenario: Collapse after answer starts
- **WHEN** вызван `collapse_after_answer()`
- **THEN** panel ДОЛЖНА быть свёрнута
- **THEN** `is_collapsed` ДОЛЖЕН быть установлен в `True`

### Requirement: ChatView ThoughtPanel integration
Система SHALL интегрировать `ThoughtPanel` в `ChatView`.

#### Scenario: ThoughtPanel mounted in ChatView
- **WHEN** `ChatView` инициализирован
- **THEN** `ThoughtPanel` ДОЛЖЕН быть смонтирован перед областью сообщений
- **THEN** panel ДОЛЖНА быть свёрнута по умолчанию

#### Scenario: ThoughtPanel receives thinking updates
- **WHEN** `ChatViewModel` получает `sync_thinking()` с непустым текстом
- **THEN** `ThoughtPanel.update_content()` ДОЛЖЕН быть вызван

#### Scenario: ThoughtPanel collapses on answer
- **WHEN** `ChatViewModel` получает `sync_streaming()` после `sync_thinking()`
- **THEN** `ThoughtPanel.collapse_after_answer()` ДОЛЖЕН быть вызван

### Requirement: ThoughtPanel visibility control
Система SHALL позволять пользователю контролировать видимость `ThoughtPanel`.

#### Scenario: User expands panel
- **WHEN** пользователь нажимает на заголовок panel
- **THEN** panel ДОЛЖНА развернуться
- **THEN** содержимое reasoning ДОЛЖНО быть видно

#### Scenario: User collapses panel
- **WHEN** пользователь нажимает на заголовок развёрнутой panel
- **THEN** panel ДОЛЖНА быть свёрнута

### Requirement: ThoughtPanel styling
Система SHALL применять distinct styling для `ThoughtPanel`.

#### Scenario: Visual distinction
- **WHEN** `ThoughtPanel` отображается
- **THEN** panel ДОЛЖНА визуально отличаться от обычных message bubbles
- **THEN** styling ДОЛЖЕН соответствовать теме (light/dark)
