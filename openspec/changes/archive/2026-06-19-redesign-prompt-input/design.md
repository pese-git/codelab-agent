## Context

Текущий `PromptInput` — это `Horizontal` контейнер с `PromptTextArea` (TextArea) и двумя кнопками (Send/Stop). Все настройки сессии (Model, Session Mode, Agent, Strategy) управляются через модальные окна, вызываемые горячими клавишами. Текущие значения не отображаются в основном интерфейсе (кроме модели в HeaderBar).

`QuickActionsBar` дублирует функциональность горячих клавиш и занимает место в dock-region.

Архитектура: Textual TUI, Clean Architecture (TUI layer → Presentation ViewModels). ViewModels уже предоставляют Observable-свойства с текущими значениями.

## Goals / Non-Goals

**Goals:**
- Пользователь видит текущие значения Model, Session Mode, Agent, Strategy прямо в области ввода
- Клик по селектору или горячая клавиша открывает модал выбора
- Expand-кнопка разворачивает TextArea на весь dock-region
- Убрать дублирующий QuickActionsBar

**Non-Goals:**
- Изменение протоколов ACP/MCP
- Изменение ViewModels (они уже предоставляют нужные данные)
- Реализация действия для кнопки "+" (заглушка)
- Изменение горячих клавиш

## Decisions

### D1: InlineSelector как отдельный виджет

**Решение:** Создать `InlineSelector(Static)` — компактный виджет, отображающий `label: value ▾`.

**Альтернативы:**
- Использовать `textual.widgets.Select` — не подходит, т.к. не поддерживает открытие произвольного модала
- Встроить логику в PromptInput — нарушает SRP, усложняет тестирование

**Рationale:** Отдельный виджет проще тестировать, переиспользовать, и он инкапсулирует подписку на Observable.

### D2: Vertical layout для PromptInput

**Решение:** Заменить `Horizontal` на `Vertical` с двумя дочерними контейнерами:
- `#prompt-textarea-container` (TextArea + expand button)
- `#prompt-toolbar` (InlineSelector × 4 + Send/Stop)

**Альтернативы:**
- Оставить Horizontal и добавить toolbar сбоку — не соответствует макету (toolbar должен быть снизу)
- Использовать Grid layout — избыточно для двух строк

### D3: QuickActionsBar — удаление из compose

**Решение:** Убрать `QuickActionsBar` из `_mount_main_layout_children()`. Файл компонента сохраняется для обратной совместимости.

**Rationale:** Все действия QuickActionsBar доступны через горячие клавиши. Компонент не удаляется полностью, чтобы не нарушать обратную совместимость.

### D4: Expand через CSS class toggle

**Решение:** Кнопка expand переключает CSS-класс `.expanded` на `#prompt-textarea-container`, который меняет `height: 6` → `height: 1fr`.

**Альтернативы:**
- Динамически менять `self.styles.height` — менее декларативно
- Использовать `set_timer` для анимации — избыточно для TUI

## Risks / Trade-offs

- **[Риск] InlineSelector клики в Textual** — Textual лучше работает с клавиатурой, чем с мышью. → **Митигация:** горячие клавиши остаются основным способом, клики — дополнительным.
- **[Риск] Ширина toolbar** — 4 селектора + кнопки могут не поместиться на узких экранах. → **Митигация:** использовать `overflow-x: auto` и сокращённые label при необходимости.
- **[Риск] Подписки на Observable** — каждый InlineSelector создаёт подписку. → **Митигация:** отписка в `on_unmount`, стандартный паттерн проекта.
