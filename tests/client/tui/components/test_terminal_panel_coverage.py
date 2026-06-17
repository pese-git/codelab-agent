"""Тесты для покрытия terminal_panel.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from textual.app import App
from textual.widgets import Button, Label

from codelab.client.tui.components.tabs import TabBar
from codelab.client.tui.components.terminal_panel import (
    TerminalOutput,
    TerminalPanel,
    TerminalSession,
    TerminalToolbar,
)


class TestTerminalSession:
    """Тесты для TerminalSession."""

    def test_add_output(self) -> None:
        """add_output добавляет текст в буфер."""
        session = TerminalSession(id="t1", name="Test")
        session.add_output("hello")
        session.add_output("world")
        assert session.output == ["hello", "world"]


class TestTerminalOutput:
    """Тесты для TerminalOutput."""

    def test_session_id_property(self) -> None:
        """session_id возвращает связанный ID."""
        output = TerminalOutput("sess-1")
        assert output.session_id == "sess-1"
        assert output.id == "terminal-output-sess-1"

    def test_custom_id(self) -> None:
        """Можно задать собственный ID."""
        output = TerminalOutput("sess", id="custom-id")
        assert output.id == "custom-id"

    def test_append_calls_write(self) -> None:
        """append делегирует в write."""
        output = TerminalOutput("sess")
        with patch.object(output, "write") as write_mock:
            output.append("text")
        write_mock.assert_called_once_with("text")

    def test_clear_output_calls_clear(self) -> None:
        """clear_output делегирует в clear."""
        output = TerminalOutput("sess")
        with patch.object(output, "clear") as clear_mock:
            output.clear_output()
        clear_mock.assert_called_once()


class TestTerminalToolbar:
    """Тесты для TerminalToolbar."""

    def test_init_default_title(self) -> None:
        """Заголовок по умолчанию — Terminal."""
        toolbar = TerminalToolbar()
        assert toolbar._title == "Terminal"
        assert toolbar.id == "terminal-toolbar"

    def test_compose(self) -> None:
        """Toolbar содержит заголовок и три кнопки."""
        toolbar = TerminalToolbar(title="My")
        children = list(toolbar.compose())
        labels = [c for c in children if isinstance(c, Label)]
        buttons = [c for c in children if isinstance(c, Button)]
        assert len(labels) == 1
        assert len(buttons) == 3

    def test_button_pressed_new_session(self) -> None:
        """Кнопка '+' отправляет NewSessionRequested."""
        toolbar = TerminalToolbar()
        posted: list[object] = []
        toolbar.post_message = posted.append
        button = Button("+")
        toolbar.on_button_pressed(Button.Pressed(button))
        assert len(posted) == 1
        assert isinstance(posted[0], TerminalToolbar.NewSessionRequested)

    def test_button_pressed_clear(self) -> None:
        """Кнопка '🗑' отправляет ClearRequested."""
        toolbar = TerminalToolbar()
        posted: list[object] = []
        toolbar.post_message = posted.append
        button = Button("🗑")
        toolbar.on_button_pressed(Button.Pressed(button))
        assert isinstance(posted[0], TerminalToolbar.ClearRequested)

    def test_button_pressed_copy(self) -> None:
        """Кнопка '📋' отправляет CopyRequested."""
        toolbar = TerminalToolbar()
        posted: list[object] = []
        toolbar.post_message = posted.append
        button = Button("📋")
        toolbar.on_button_pressed(Button.Pressed(button))
        assert isinstance(posted[0], TerminalToolbar.CopyRequested)

    def test_button_pressed_unknown(self) -> None:
        """Неизвестная кнопка не отправляет сообщения."""
        toolbar = TerminalToolbar()
        posted: list[object] = []
        toolbar.post_message = posted.append
        button = Button("?")
        toolbar.on_button_pressed(Button.Pressed(button))
        assert len(posted) == 0

    def test_set_title(self) -> None:
        """set_title обновляет внутреннее состояние."""
        toolbar = TerminalToolbar()
        toolbar.set_title("New")
        assert toolbar._title == "New"

    def test_set_title_updates_label(self) -> None:
        """set_title обновляет виджет заголовка если он есть."""
        toolbar = TerminalToolbar()
        label_mock = MagicMock()
        with patch.object(toolbar, "query_one", return_value=label_mock):
            toolbar.set_title("New")
        label_mock.update.assert_called_once_with("New")


class TestTerminalPanel:
    """Тесты для TerminalPanel."""

    def setup_method(self) -> None:
        """Сбрасываем счётчик сессий перед каждым тестом."""
        TerminalPanel._session_counter = 0

    def test_init(self) -> None:
        """Инициализация панели."""
        panel = TerminalPanel()
        assert panel.id == "terminal-panel"
        assert panel._sessions == {}
        assert panel._outputs == {}
        assert panel._tab_bar is None
        assert panel._content is None

    def test_compose(self) -> None:
        """Панель создаёт toolbar, tab bar и content."""
        from textual._context import active_app

        panel = TerminalPanel()
        app = App()
        token = active_app.set(app)
        try:
            children = list(panel.compose())
        finally:
            active_app.reset(token)
        assert panel._tab_bar is not None
        assert panel._content is not None
        assert len(children) >= 3

    def test_on_mount_creates_first_session(self) -> None:
        """При монтировании создаётся первая сессия."""
        panel = TerminalPanel()
        with patch.object(panel, "create_session") as create_mock:
            panel.on_mount()
        create_mock.assert_called_once_with("Terminal 1")

    def test_on_mount_skips_if_sessions_exist(self) -> None:
        """Если сессии уже есть, on_mount не создаёт новую."""
        panel = TerminalPanel()
        panel._sessions["existing"] = TerminalSession(id="existing", name="Existing")
        with patch.object(panel, "create_session") as create_mock:
            panel.on_mount()
        create_mock.assert_not_called()

    def test_create_session(self) -> None:
        """Создание сессии добавляет её в панель."""
        panel = TerminalPanel()
        panel._content = MagicMock()
        panel._tab_bar = MagicMock()
        sid = panel.create_session("My Session")
        assert sid in panel._sessions
        assert sid in panel._outputs
        assert panel._sessions[sid].name == "My Session"
        panel._content.mount.assert_called_once()
        panel._tab_bar.add_tab.assert_called_once()

    def test_create_session_auto_name(self) -> None:
        """Имя сессии генерируется автоматически."""
        panel = TerminalPanel()
        panel._content = MagicMock()
        panel._tab_bar = MagicMock()
        sid = panel.create_session()
        assert panel._sessions[sid].name == "Terminal 1"

    def test_create_session_posts_message(self) -> None:
        """Создание сессии отправляет SessionCreated."""
        panel = TerminalPanel()
        panel._content = MagicMock()
        panel._tab_bar = MagicMock()
        posted: list[object] = []
        panel.post_message = posted.append
        sid = panel.create_session()
        assert any(
            isinstance(m, TerminalPanel.SessionCreated) and m.session_id == sid
            for m in posted
        )

    def test_close_session(self) -> None:
        """Закрытие сессии удаляет её данные."""
        panel = TerminalPanel()
        panel._content = MagicMock()
        panel._tab_bar = MagicMock()
        sid = panel.create_session("S1")
        with patch.object(panel._outputs[sid], "remove"):
            result = panel.close_session(sid)
        assert result is True
        assert sid not in panel._sessions
        assert sid not in panel._outputs

    def test_close_session_unknown(self) -> None:
        """Закрытие неизвестной сессии возвращает False."""
        panel = TerminalPanel()
        assert panel.close_session("missing") is False

    def test_write_to_session(self) -> None:
        """Запись в сессию обновляет буфер и вывод."""
        panel = TerminalPanel()
        panel._content = MagicMock()
        panel._tab_bar = MagicMock()
        sid = panel.create_session("S1")
        output_widget = panel._outputs[sid]
        posted: list[object] = []
        panel.post_message = posted.append
        with patch.object(output_widget, "append") as append_mock:
            panel.write_to_session(sid, "hello")
        append_mock.assert_called_once_with("hello")
        assert "hello" in panel._sessions[sid].output
        assert any(
            isinstance(m, TerminalPanel.OutputReceived)
            and m.session_id == sid
            and m.text == "hello"
            for m in posted
        )

    def test_write_to_unknown_session(self) -> None:
        """Запись в несуществующую сессию не падает."""
        panel = TerminalPanel()
        panel.write_to_session("missing", "hello")

    def test_write_active_session(self) -> None:
        """write делегирует в активную сессию."""
        panel = TerminalPanel()
        panel._content = MagicMock()
        panel._tab_bar = MagicMock()
        sid = panel.create_session("S1")
        panel.active_session = sid
        with patch.object(panel, "write_to_session") as write_mock:
            panel.write("text")
        write_mock.assert_called_once_with(sid, "text")

    def test_write_no_active_session(self) -> None:
        """write без активной сессии ничего не делает."""
        panel = TerminalPanel()
        with patch.object(panel, "write_to_session") as write_mock:
            panel.write("text")
        write_mock.assert_not_called()

    def test_clear_session(self) -> None:
        """clear_session очищает буфер и виджет."""
        panel = TerminalPanel()
        panel._content = MagicMock()
        panel._tab_bar = MagicMock()
        sid = panel.create_session("S1")
        panel.write_to_session(sid, "hello")
        output_widget = panel._outputs[sid]
        with patch.object(output_widget, "clear_output") as clear_mock:
            panel.clear_session(sid)
        clear_mock.assert_called_once()
        assert panel._sessions[sid].output == []

    def test_clear_active(self) -> None:
        """clear_active очищает активную сессию."""
        panel = TerminalPanel()
        panel._content = MagicMock()
        panel._tab_bar = MagicMock()
        sid = panel.create_session("S1")
        panel.active_session = sid
        with patch.object(panel, "clear_session") as clear_mock:
            panel.clear_active()
        clear_mock.assert_called_once_with(sid)

    def test_watch_active_session(self) -> None:
        """watch_active_session переключает класс -active."""
        panel = TerminalPanel()
        panel._content = MagicMock()
        panel._tab_bar = MagicMock()
        sid1 = panel.create_session("S1")
        sid2 = panel.create_session("S2")
        panel.watch_active_session(sid1)
        assert panel._outputs[sid1].has_class("-active")
        assert not panel._outputs[sid2].has_class("-active")

    def test_on_tab_bar_tab_activated(self) -> None:
        """Активация таба меняет active_session."""
        panel = TerminalPanel()
        panel.on_tab_bar_tab_activated(TabBar.TabActivated("t1"))
        assert panel.active_session == "t1"

    def test_on_tab_bar_tab_closed(self) -> None:
        """Закрытие таба закрывает сессию."""
        panel = TerminalPanel()
        panel._content = MagicMock()
        panel._tab_bar = MagicMock()
        sid = panel.create_session("S1")
        with patch.object(panel, "close_session") as close_mock:
            panel.on_tab_bar_tab_closed(TabBar.TabClosed(sid))
        close_mock.assert_called_once_with(sid)

    def test_on_toolbar_new_session(self) -> None:
        """Запрос toolbar на новую сессию создаёт её."""
        panel = TerminalPanel()
        panel._content = MagicMock()
        panel._tab_bar = MagicMock()
        with patch.object(panel, "create_session") as create_mock:
            panel.on_terminal_toolbar_new_session_requested(
                TerminalToolbar.NewSessionRequested()
            )
        create_mock.assert_called_once_with()

    def test_on_toolbar_clear(self) -> None:
        """Запрос toolbar на очистку вызывает clear_active."""
        panel = TerminalPanel()
        with patch.object(panel, "clear_active") as clear_mock:
            panel.on_terminal_toolbar_clear_requested(
                TerminalToolbar.ClearRequested()
            )
        clear_mock.assert_called_once()

    def test_on_toolbar_copy(self) -> None:
        """Запрос toolbar на копирование не падает."""
        panel = TerminalPanel()
        panel.on_terminal_toolbar_copy_requested(TerminalToolbar.CopyRequested())

    def test_sessions_property(self) -> None:
        """sessions возвращает список ID сессий."""
        panel = TerminalPanel()
        panel._content = MagicMock()
        panel._tab_bar = MagicMock()
        sid1 = panel.create_session("S1")
        sid2 = panel.create_session("S2")
        assert set(panel.sessions) == {sid1, sid2}

    def test_get_session(self) -> None:
        """get_session возвращает сессию или None."""
        panel = TerminalPanel()
        panel._content = MagicMock()
        panel._tab_bar = MagicMock()
        sid = panel.create_session("S1")
        assert panel.get_session(sid) is panel._sessions[sid]
        assert panel.get_session("missing") is None
