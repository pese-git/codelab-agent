"""TabBar и TabPanel - компоненты табов.

Горизонтальные табы для переключения между панелями:
- Активный/неактивный стиль
- Close button на табе
- Навигация клавиатурой
"""

from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Label, Static


@dataclass
class TabData:
    """Данные таба.

    Атрибуты:
        id: Уникальный идентификатор таба
        label: Отображаемый текст
        closable: Можно ли закрыть таб
        icon: Опциональная иконка
    """

    id: str
    label: str
    closable: bool = True
    icon: str | None = None


class Tab(Static):
    """Отдельный таб в TabBar.

    Поддерживает активное/неактивное состояние и кнопку закрытия.
    """

    DEFAULT_CSS = """
    Tab {
        width: auto;
        height: 3;
        padding: 0 2;
        border: solid $border;
        border-bottom: none;
        margin-right: 1;
        background: $background-secondary;
    }

    Tab:hover {
        background: $background-tertiary;
    }

    Tab.-active {
        background: $background;
        border-bottom: solid $background;
        text-style: bold;
    }

    Tab .tab-content {
        width: auto;
        height: auto;
        layout: horizontal;
    }

    Tab .tab-icon {
        width: auto;
        margin-right: 1;
    }

    Tab .tab-label {
        width: auto;
    }

    Tab .tab-close {
        width: 3;
        height: 1;
        margin-left: 1;
        min-width: 0;
        border: none;
        background: transparent;
    }

    Tab .tab-close:hover {
        background: $error 30%;
        color: $error;
    }

    Tab.-closable .tab-close {
        display: block;
    }

    Tab:not(.-closable) .tab-close {
        display: none;
    }
    """

    class Clicked(Message):
        """Сообщение о клике на таб."""

        def __init__(self, tab_id: str) -> None:
            self.tab_id = tab_id
            super().__init__()

    class CloseRequested(Message):
        """Сообщение о запросе закрытия таба."""

        def __init__(self, tab_id: str) -> None:
            self.tab_id = tab_id
            super().__init__()

    is_active: reactive[bool] = reactive(False)

    def __init__(
        self,
        data: TabData,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует таб.

        Args:
            data: Данные таба
            name: Имя виджета
            id: ID виджета
            classes: CSS классы
        """
        super().__init__(name=name, id=id or f"tab-{data.id}", classes=classes)
        self._data = data
        if data.closable:
            self.add_class("-closable")

    @property
    def tab_id(self) -> str:
        """ID таба из данных."""
        return self._data.id

    def compose(self) -> ComposeResult:
        """Создаёт содержимое таба."""
        with Horizontal(classes="tab-content"):
            if self._data.icon:
                yield Label(self._data.icon, classes="tab-icon")
            yield Label(self._data.label, classes="tab-label")
            yield Button("×", classes="tab-close", variant="default")

    def watch_is_active(self, active: bool) -> None:
        """Обновляет стиль при изменении активности."""
        self.set_class(active, "-active")

    async def on_click(self) -> None:
        """Обрабатывает клик на таб."""
        self.post_message(self.Clicked(self._data.id))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Обрабатывает клик на кнопку закрытия."""
        if "tab-close" in event.button.classes:
            event.stop()
            self.post_message(self.CloseRequested(self._data.id))


class TabBar(Horizontal):
    """Горизонтальная панель табов.

    Управляет коллекцией табов с возможностью:
    - Добавления/удаления табов
    - Переключения активного таба
    - Навигации клавиатурой
    """

    DEFAULT_CSS = """
    TabBar {
        width: 100%;
        height: 3;
        background: $background-secondary;
        border-bottom: solid $border;
        padding: 0 1;
    }

    TabBar:focus {
        border-bottom: solid $primary;
    }
    """

    BINDINGS = [
        ("left", "previous_tab", "Previous Tab"),
        ("right", "next_tab", "Next Tab"),
        ("escape", "blur", "Blur"),
    ]

    class TabActivated(Message):
        """Сообщение об активации таба."""

        def __init__(self, tab_id: str) -> None:
            self.tab_id = tab_id
            super().__init__()

    class TabClosed(Message):
        """Сообщение о закрытии таба."""

        def __init__(self, tab_id: str) -> None:
            self.tab_id = tab_id
            super().__init__()

    active_tab: reactive[str | None] = reactive(None)

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует TabBar."""
        super().__init__(name=name, id=id or "tab-bar", classes=classes)
        self._tabs: dict[str, Tab] = {}
        self._tab_order: list[str] = []

    @property
    def tabs(self) -> list[str]:
        """Список ID табов в порядке отображения."""
        return self._tab_order.copy()

    def add_tab(
        self,
        tab_id: str,
        label: str,
        *,
        closable: bool = True,
        icon: str | None = None,
        activate: bool = True,
    ) -> Tab:
        """Добавляет новый таб.

        Args:
            tab_id: Уникальный ID таба
            label: Отображаемый текст
            closable: Можно ли закрыть таб
            icon: Опциональная иконка
            activate: Активировать таб после добавления

        Returns:
            Созданный виджет таба
        """
        data = TabData(id=tab_id, label=label, closable=closable, icon=icon)
        tab = Tab(data)
        self._tabs[tab_id] = tab
        self._tab_order.append(tab_id)
        self.mount(tab)

        if activate or len(self._tabs) == 1:
            self.activate_tab(tab_id)

        return tab

    def remove_tab(self, tab_id: str) -> bool:
        """Удаляет таб по ID.

        Args:
            tab_id: ID таба для удаления

        Returns:
            True если таб был удалён
        """
        if tab_id not in self._tabs:
            return False

        tab = self._tabs.pop(tab_id)
        self._tab_order.remove(tab_id)
        tab.remove()

        # Активируем соседний таб если удалённый был активным
        if self.active_tab == tab_id and self._tab_order:
            self.activate_tab(self._tab_order[-1])
        elif not self._tab_order:
            self.active_tab = None

        self.post_message(self.TabClosed(tab_id))
        return True

    def activate_tab(self, tab_id: str) -> bool:
        """Активирует таб по ID.

        Args:
            tab_id: ID таба для активации

        Returns:
            True если таб был активирован
        """
        if tab_id not in self._tabs:
            return False

        # Деактивируем текущий активный таб
        if self.active_tab and self.active_tab in self._tabs:
            self._tabs[self.active_tab].is_active = False

        # Активируем новый таб
        self._tabs[tab_id].is_active = True
        self.active_tab = tab_id
        self.post_message(self.TabActivated(tab_id))
        return True

    def on_tab_clicked(self, event: Tab.Clicked) -> None:
        """Обрабатывает клик на таб."""
        self.activate_tab(event.tab_id)

    def on_tab_close_requested(self, event: Tab.CloseRequested) -> None:
        """Обрабатывает запрос закрытия таба."""
        self.remove_tab(event.tab_id)

    def action_previous_tab(self) -> None:
        """Переключает на предыдущий таб."""
        if not self._tab_order or not self.active_tab:
            return
        idx = self._tab_order.index(self.active_tab)
        new_idx = (idx - 1) % len(self._tab_order)
        self.activate_tab(self._tab_order[new_idx])

    def action_next_tab(self) -> None:
        """Переключает на следующий таб."""
        if not self._tab_order or not self.active_tab:
            return
        idx = self._tab_order.index(self.active_tab)
        new_idx = (idx + 1) % len(self._tab_order)
        self.activate_tab(self._tab_order[new_idx])


class TabPanel(Container):
    """Панель контента для TabBar.

    Показывает контент активного таба и скрывает остальные.
    """

    DEFAULT_CSS = """
    TabPanel {
        width: 100%;
        height: 1fr;
    }

    TabPanel > .tab-content-panel {
        width: 100%;
        height: 100%;
        display: none;
    }

    TabPanel > .tab-content-panel.-active {
        display: block;
    }
    """

    active_tab: reactive[str | None] = reactive(None)

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует TabPanel."""
        super().__init__(name=name, id=id or "tab-panel", classes=classes)
        self._panels: dict[str, Container] = {}

    def add_panel(self, tab_id: str, *widgets: Widget) -> Container:
        """Добавляет панель контента для таба.

        Args:
            tab_id: ID связанного таба
            *widgets: Виджеты для размещения в панели

        Returns:
            Созданный контейнер панели
        """
        panel = Container(*widgets, classes="tab-content-panel", id=f"panel-{tab_id}")
        self._panels[tab_id] = panel
        self.mount(panel)

        if self.active_tab == tab_id:
            panel.add_class("-active")

        return panel

    def remove_panel(self, tab_id: str) -> bool:
        """Удаляет панель контента.

        Args:
            tab_id: ID связанного таба

        Returns:
            True если панель была удалена
        """
        if tab_id not in self._panels:
            return False

        panel = self._panels.pop(tab_id)
        panel.remove()
        return True

    def watch_active_tab(self, tab_id: str | None) -> None:
        """Обновляет видимость панелей при смене активного таба."""
        for pid, panel in self._panels.items():
            panel.set_class(pid == tab_id, "-active")

    def get_panel(self, tab_id: str) -> Container | None:
        """Получает панель по ID таба."""
        return self._panels.get(tab_id)


class TabbedContainer(Container):
    """Контейнер с TabBar и TabPanel.

    Объединяет TabBar и TabPanel для удобного использования.
    Автоматически синхронизирует активный таб между ними.
    """

    DEFAULT_CSS = """
    TabbedContainer {
        width: 100%;
        height: 100%;
        layout: vertical;
    }
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует TabbedContainer."""
        super().__init__(name=name, id=id, classes=classes)
        self._tab_bar = TabBar()
        self._tab_panel = TabPanel()

    def compose(self) -> ComposeResult:
        """Создаёт TabBar и TabPanel."""
        yield self._tab_bar
        yield self._tab_panel

    @property
    def tab_bar(self) -> TabBar:
        """TabBar контейнера."""
        return self._tab_bar

    @property
    def tab_panel(self) -> TabPanel:
        """TabPanel контейнера."""
        return self._tab_panel

    def add_tab(
        self,
        tab_id: str,
        label: str,
        *widgets: Widget,
        closable: bool = True,
        icon: str | None = None,
        activate: bool = True,
    ) -> None:
        """Добавляет таб с контентом.

        Args:
            tab_id: Уникальный ID таба
            label: Отображаемый текст
            *widgets: Виджеты для панели контента
            closable: Можно ли закрыть таб
            icon: Опциональная иконка
            activate: Активировать таб после добавления
        """
        self._tab_bar.add_tab(tab_id, label, closable=closable, icon=icon, activate=activate)
        self._tab_panel.add_panel(tab_id, *widgets)
        if activate:
            self._tab_panel.active_tab = tab_id

    def remove_tab(self, tab_id: str) -> bool:
        """Удаляет таб и его контент.

        Args:
            tab_id: ID таба для удаления

        Returns:
            True если таб был удалён
        """
        bar_removed = self._tab_bar.remove_tab(tab_id)
        panel_removed = self._tab_panel.remove_panel(tab_id)
        return bar_removed or panel_removed

    def on_tab_bar_tab_activated(self, event: TabBar.TabActivated) -> None:
        """Синхронизирует активный таб с TabPanel."""
        self._tab_panel.active_tab = event.tab_id

    def on_tab_bar_tab_closed(self, event: TabBar.TabClosed) -> None:
        """Удаляет панель при закрытии таба."""
        self._tab_panel.remove_panel(event.tab_id)
