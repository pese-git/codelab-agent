"""Тесты покрытия для StatusLine компонента.

Проверяют непокрытые строки в:
- StatusMode
- StatusIndicator
- StatusLine
- CompactStatusLine
"""

from __future__ import annotations

from unittest.mock import patch

from textual.app import App

from codelab.client.presentation.observable import Observable
from codelab.client.presentation.ui_view_model import ConnectionStatus
from codelab.client.tui.components.status_line import (
    MODE_ICONS,
    MODE_NAMES,
    CompactStatusLine,
    StatusIndicator,
    StatusLine,
    StatusMode,
)


class FakeUIViewModel:
    """Фейковый UIViewModel для тестов StatusLine."""

    def __init__(self) -> None:
        self.connection_status: Observable[ConnectionStatus] = Observable(
            ConnectionStatus.DISCONNECTED
        )


class TestStatusMode:
    """Тесты для StatusMode."""

    def test_mode_values(self) -> None:
        """Режимы содержат ожидаемые строковые значения."""
        assert StatusMode.NORMAL.value == "normal"
        assert StatusMode.CHAT.value == "chat"
        assert StatusMode.COMMAND.value == "command"
        assert StatusMode.SEARCH.value == "search"

    def test_mode_icons(self) -> None:
        """Каждому режиму соответствует иконка."""
        assert StatusMode.NORMAL in MODE_ICONS
        assert StatusMode.CHAT in MODE_ICONS
        assert StatusMode.COMMAND in MODE_ICONS
        assert StatusMode.SEARCH in MODE_ICONS

    def test_mode_names(self) -> None:
        """Каждому режиму соответствует название."""
        assert MODE_NAMES[StatusMode.NORMAL] == "NORMAL"
        assert MODE_NAMES[StatusMode.CHAT] == "CHAT"
        assert MODE_NAMES[StatusMode.COMMAND] == "CMD"
        assert MODE_NAMES[StatusMode.SEARCH] == "SEARCH"


class TestStatusIndicator:
    """Тесты для StatusIndicator."""

    def test_default_values(self) -> None:
        """Поля индикатора по умолчанию заполнены корректно."""
        indicator = StatusIndicator(name="test", icon="●")

        assert indicator.name == "test"
        assert indicator.icon == "●"
        assert indicator.label == ""
        assert indicator.active is True
        assert indicator.color == ""

    def test_custom_values(self) -> None:
        """Индикатор сохраняет все переданные значения."""
        indicator = StatusIndicator(
            name="conn", icon="●", label="Online", active=False, color="error"
        )

        assert indicator.active is False
        assert indicator.label == "Online"
        assert indicator.color == "error"


class TestStatusLine:
    """Тесты для StatusLine."""

    def test_init_without_view_model(self) -> None:
        """Инициализация без UIViewModel."""
        status = StatusLine()

        assert status._ui_vm is None
        assert status._indicators == []
        assert status._custom_hints == []
        assert status.mode == StatusMode.NORMAL

    def test_init_with_view_model(self) -> None:
        """Инициализация с UIViewModel."""
        ui_vm = FakeUIViewModel()
        status = StatusLine(ui_vm)

        assert status._ui_vm is ui_vm

    async def test_compose_and_mount(self) -> None:
        """Компонент монтируется и содержит три секции."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            status = StatusLine()
            await pilot.app.mount(status)

            children = list(status.query("Horizontal > Static"))
            assert len(children) == 3

    def test_create_mode_indicator_for_each_mode(self) -> None:
        """Индикатор режима содержит иконку, название и CSS-класс."""
        for mode in StatusMode:
            status = StatusLine()
            status.mode = mode
            indicator = status._create_mode_indicator()

            assert f"-{mode.value}" in indicator.classes
            assert MODE_ICONS[mode] in str(indicator.render())
            assert MODE_NAMES[mode] in str(indicator.render())

    def test_create_hints_default(self) -> None:
        """Подсказки по умолчанию соответствуют режиму."""
        status = StatusLine()
        status.mode = StatusMode.CHAT
        hints_widget = status._create_hints()

        text = str(hints_widget.render())
        for key, desc in StatusLine.DEFAULT_HINTS[StatusMode.CHAT]:
            assert key in text
            assert desc in text

    def test_create_hints_custom(self) -> None:
        """Кастомные подсказки используются вместо стандартных."""
        status = StatusLine()
        status.set_hints([("F1", "Помощь")])
        hints_widget = status._create_hints()

        text = str(hints_widget.render())
        assert "F1" in text
        assert "Помощь" in text

    def test_create_default_indicators_without_vm(self) -> None:
        """Без ViewModel индикаторы по умолчанию пусты."""
        status = StatusLine()
        indicators = status._create_indicators()

        assert str(indicators.render()) == ""

    def test_create_default_indicators_connected(self) -> None:
        """Индикатор подключения показывает Online."""
        ui_vm = FakeUIViewModel()
        ui_vm.connection_status.value = ConnectionStatus.CONNECTED
        status = StatusLine(ui_vm)
        indicators = status._create_indicators()

        text = str(indicators.render())
        assert "Online" in text

    def test_create_default_indicators_connecting(self) -> None:
        """Индикатор подключения показывает Connecting."""
        ui_vm = FakeUIViewModel()
        ui_vm.connection_status.value = ConnectionStatus.CONNECTING
        status = StatusLine(ui_vm)
        indicators = status._create_indicators()

        text = str(indicators.render())
        assert "Connecting" in text

    def test_create_default_indicators_disconnected(self) -> None:
        """Индикатор подключения показывает Offline."""
        ui_vm = FakeUIViewModel()
        ui_vm.connection_status.value = ConnectionStatus.DISCONNECTED
        status = StatusLine(ui_vm)
        indicators = status._create_indicators()

        text = str(indicators.render())
        assert "Offline" in text

    def test_create_custom_indicators(self) -> None:
        """Пользовательские индикаторы отображаются с маркировкой активности."""
        status = StatusLine()
        status.add_indicator(StatusIndicator(name="sync", icon="↻", label="Sync"))
        status.add_indicator(
            StatusIndicator(name="err", icon="✕", label="Err", active=False)
        )
        indicators = status._create_indicators()

        text = str(indicators.render())
        assert "Sync" in text
        assert "Err" in text

    def test_watch_mode_refreshes(self) -> None:
        """Изменение режима вызывает refresh."""
        status = StatusLine()
        with patch.object(status, "refresh") as mock_refresh:
            status.watch_mode(StatusMode.COMMAND)

        mock_refresh.assert_called_once()

    def test_set_mode(self) -> None:
        """set_mode устанавливает текущий режим."""
        status = StatusLine()
        status.set_mode(StatusMode.SEARCH)

        assert status.mode == StatusMode.SEARCH

    def test_set_hints(self) -> None:
        """set_hints сохраняет подсказки и обновляет отображение."""
        status = StatusLine()
        with patch.object(status, "refresh") as mock_refresh:
            status.set_hints([("Tab", "Переключить")])

        assert status._custom_hints == [("Tab", "Переключить")]
        mock_refresh.assert_called_once()

    def test_clear_hints(self) -> None:
        """clear_hints сбрасывает подсказки и обновляет отображение."""
        status = StatusLine()
        status.set_hints([("Tab", "Переключить")])
        with patch.object(status, "refresh") as mock_refresh:
            status.clear_hints()

        assert status._custom_hints == []
        mock_refresh.assert_called_once()

    def test_add_indicator(self) -> None:
        """add_indicator добавляет индикатор и обновляет отображение."""
        status = StatusLine()
        indicator = StatusIndicator(name="test", icon="●")
        with patch.object(status, "refresh") as mock_refresh:
            status.add_indicator(indicator)

        assert status._indicators == [indicator]
        mock_refresh.assert_called_once()

    def test_remove_indicator_success(self) -> None:
        """remove_indicator удаляет существующий индикатор."""
        status = StatusLine()
        status.add_indicator(StatusIndicator(name="keep", icon="●"))
        status.add_indicator(StatusIndicator(name="drop", icon="●"))

        with patch.object(status, "refresh") as mock_refresh:
            result = status.remove_indicator("drop")

        assert result is True
        assert len(status._indicators) == 1
        assert status._indicators[0].name == "keep"
        mock_refresh.assert_called_once()

    def test_remove_indicator_not_found(self) -> None:
        """remove_indicator возвращает False для отсутствующего имени."""
        status = StatusLine()
        assert status.remove_indicator("missing") is False

    def test_update_indicator_success(self) -> None:
        """update_indicator изменяет активность и метку."""
        status = StatusLine()
        status.add_indicator(StatusIndicator(name="test", icon="●", label="Old"))

        with patch.object(status, "refresh") as mock_refresh:
            result = status.update_indicator("test", active=False, label="New")

        assert result is True
        indicator = status._indicators[0]
        assert indicator.active is False
        assert indicator.label == "New"
        mock_refresh.assert_called_once()

    def test_update_indicator_not_found(self) -> None:
        """update_indicator возвращает False для отсутствующего имени."""
        status = StatusLine()
        assert status.update_indicator("missing", active=False) is False


class TestCompactStatusLine:
    """Тесты для CompactStatusLine."""

    def test_init_default_message(self) -> None:
        """Инициализация с сообщением по умолчанию."""
        status = CompactStatusLine()

        assert status._message == "Ctrl+K команды • ? справка"
        assert status._ui_vm is None

    def test_init_with_view_model(self) -> None:
        """Инициализация с UIViewModel."""
        ui_vm = FakeUIViewModel()
        status = CompactStatusLine(ui_vm)

        assert status._ui_vm is ui_vm

    async def test_compose_and_mount(self) -> None:
        """Компонент монтируется и отображает сообщение."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            status = CompactStatusLine()
            await pilot.app.mount(status)

            static = status.query_one("Static")
            assert static is not None

    def test_set_message(self) -> None:
        """set_message обновляет текст и вызывает refresh."""
        status = CompactStatusLine()
        with patch.object(status, "refresh") as mock_refresh:
            status.set_message("Новое сообщение")

        assert status._message == "Новое сообщение"
        mock_refresh.assert_called_once()
