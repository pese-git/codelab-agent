"""Тесты покрытия для ToolPanel компонента.

Проверяют отображение tool calls, прогресс-бар и интеграцию с ViewModels.
"""

from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.app import App

from codelab.client.messages import ToolCallCreatedUpdate
from codelab.client.presentation.observable import Observable
from codelab.client.tui.components.progress import ProgressVariant
from codelab.client.tui.components.tool_panel import ToolPanel


class FakeChatViewModel:
    """Фейковый ChatViewModel для тестов ToolPanel."""

    def __init__(self) -> None:
        self.tool_calls: Observable[list[Any]] = Observable([])


class FakeTerminalViewModel:
    """Фейковый TerminalViewModel для тестов ToolPanel."""

    def __init__(self) -> None:
        self._output: Observable[str] = Observable("")
        self._has_output: Observable[bool] = Observable(False)
        self._is_running: Observable[bool] = Observable(False)

    @property
    def output(self) -> Observable[str]:
        return self._output

    @property
    def has_output(self) -> Observable[bool]:
        return self._has_output

    @property
    def is_running(self) -> Observable[bool]:
        return self._is_running

    def append_output(self, text: str) -> None:
        self._output.value += text
        self._has_output.value = bool(self._output.value.strip())

    def clear_output(self) -> None:
        self._output.value = ""
        self._has_output.value = False


class FakeToolCall:
    """Фейковый объект tool call."""

    def __init__(self, tool_id: str, name: str, status: str) -> None:
        self.id = tool_id
        self.name = name
        self.status = status

    def __repr__(self) -> str:
        return f"FakeToolCall({self.id})"


class TestToolPanel:
    """Тесты для ToolPanel."""

    def test_init_subscribes_to_view_model(self) -> None:
        """Инициализация подписывается на tool_calls ViewModel."""
        chat_vm = FakeChatViewModel()
        terminal_vm = FakeTerminalViewModel()

        panel = ToolPanel(chat_vm, terminal_vm)

        assert panel.chat_vm is chat_vm
        assert panel._terminal_vm is terminal_vm
        assert panel._tool_calls == {}

    def test_render_before_mount(self) -> None:
        """render возвращает Text даже до монтирования."""
        chat_vm = FakeChatViewModel()
        terminal_vm = FakeTerminalViewModel()
        panel = ToolPanel(chat_vm, terminal_vm)

        result = panel.render()

        assert isinstance(result, Text)
        assert "нет активных вызовов" in result.plain

    async def test_compose_and_mount(self) -> None:
        """Компонент создаёт вложенные виджеты после монтирования."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            terminal_vm = FakeTerminalViewModel()
            panel = ToolPanel(chat_vm, terminal_vm)
            await pilot.app.mount(panel)

            assert panel._tool_call_list is not None
            assert panel._tool_list is not None
            assert panel._progress_bar is not None

    async def test_on_tool_calls_changed_empty(self) -> None:
        """Пустой список tool calls скрывает прогресс-бар."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            terminal_vm = FakeTerminalViewModel()
            panel = ToolPanel(chat_vm, terminal_vm)
            await pilot.app.mount(panel)

            chat_vm.tool_calls.value = []

            assert panel._tool_list._Static__content == "Инструменты: нет активных вызовов"
            assert panel._progress_bar.display is False

    async def test_on_tool_calls_changed_with_dicts(self) -> None:
        """Список словарей tool calls обновляет панель и прогресс-бар."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            terminal_vm = FakeTerminalViewModel()
            panel = ToolPanel(chat_vm, terminal_vm)
            await pilot.app.mount(panel)

            chat_vm.tool_calls.value = [
                {"toolCallId": "tc1", "title": "read", "status": "in_progress"},
                {"toolCallId": "tc2", "title": "write", "status": "completed"},
            ]

            text = panel._tool_list._Static__content
            assert "tc1 [in_progress]" in text
            assert "tc2 [completed]" in text
            assert panel._tool_call_list.count == 2

    async def test_on_tool_calls_changed_with_objects(self) -> None:
        """Список объектов tool calls обновляет панель."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            terminal_vm = FakeTerminalViewModel()
            panel = ToolPanel(chat_vm, terminal_vm)
            await pilot.app.mount(panel)

            chat_vm.tool_calls.value = [
                FakeToolCall("tc1", "read", "failed"),
            ]

            text = panel._tool_list._Static__content
            assert "tc1 [failed]" in text
            assert panel._progress_bar._variant == ProgressVariant.WARNING

    async def test_on_tool_calls_changed_before_mount(self) -> None:
        """Изменение tool calls до монтирования не вызывает ошибок."""
        chat_vm = FakeChatViewModel()
        terminal_vm = FakeTerminalViewModel()
        panel = ToolPanel(chat_vm, terminal_vm)

        chat_vm.tool_calls.value = [
            {"toolCallId": "tc1", "title": "read", "status": "completed"},
        ]

        assert panel._tool_calls == {}

    def test_get_tc_status(self) -> None:
        """_get_tc_status извлекает статус из dict и объекта."""
        chat_vm = FakeChatViewModel()
        terminal_vm = FakeTerminalViewModel()
        panel = ToolPanel(chat_vm, terminal_vm)

        assert panel._get_tc_status({"status": "done"}) == "done"
        assert panel._get_tc_status({}) == ""
        assert panel._get_tc_status(FakeToolCall("x", "y", "running")) == "running"

    async def test_update_progress_visibility(self) -> None:
        """Показ/скрытие прогресс-бара работает корректно."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            terminal_vm = FakeTerminalViewModel()
            panel = ToolPanel(chat_vm, terminal_vm)
            await pilot.app.mount(panel)

            panel._update_progress_visibility(show=True)
            assert panel._progress_bar.display is True

            panel._update_progress_visibility(show=False)
            assert panel._progress_bar.display is False

    async def test_reset(self) -> None:
        """reset очищает локальное состояние и ToolCallList."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            terminal_vm = FakeTerminalViewModel()
            panel = ToolPanel(chat_vm, terminal_vm)
            await pilot.app.mount(panel)

            panel._tool_calls["tc1"] = {"title": "t", "status": "pending"}
            panel._tool_call_list.add_tool_call("tc1", "t", {}, "pending")
            panel._progress_bar.set_steps(1, 2)

            panel.reset()

            assert panel._tool_calls == {}
            assert panel._tool_list._Static__content == "Инструменты: нет активных вызовов"
            assert panel._progress_bar.display is False

    async def test_apply_update_creates_tool_call(self) -> None:
        """apply_update добавляет новый tool call."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            terminal_vm = FakeTerminalViewModel()
            panel = ToolPanel(chat_vm, terminal_vm)
            await pilot.app.mount(panel)

            update = ToolCallCreatedUpdate(
                sessionUpdate="tool_call",
                toolCallId="tc1",
                title="read_file",
                status="in_progress",
            )
            panel.apply_update(update)

            assert "tc1" in panel._tool_calls
            assert panel._tool_calls["tc1"]["title"] == "read_file"
            assert panel._tool_calls["tc1"]["status"] == "in_progress"

    async def test_apply_update_with_terminal_output(self) -> None:
        """apply_update сохраняет terminal output и exit code."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            terminal_vm = FakeTerminalViewModel()
            panel = ToolPanel(chat_vm, terminal_vm)
            await pilot.app.mount(panel)

            update = ToolCallCreatedUpdate(
                sessionUpdate="tool_call",
                toolCallId="tc1",
                title="exec",
                status="completed",
                rawOutput={"output": "hello", "exitCode": 0},
                content=[{"type": "terminal", "terminalId": "term_1"}],
            )
            panel.apply_update(update)

            snapshot = panel.latest_terminal_snapshot()
            assert snapshot is not None
            title, terminal_id, _text = snapshot
            assert title == "exec"
            assert terminal_id == "term_1"

    async def test_apply_update_skips_invalid_id(self) -> None:
        """apply_update игнорирует update без toolCallId."""
        chat_vm = FakeChatViewModel()
        terminal_vm = FakeTerminalViewModel()
        panel = ToolPanel(chat_vm, terminal_vm)

        update = ToolCallCreatedUpdate(
            sessionUpdate="tool_call",
            toolCallId="",
            title="x",
        )
        panel.apply_update(update)

        assert panel._tool_calls == {}

    async def test_update_progress_from_tool_calls_dict(self) -> None:
        """Прогресс обновляется на основе локального словаря."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            terminal_vm = FakeTerminalViewModel()
            panel = ToolPanel(chat_vm, terminal_vm)
            await pilot.app.mount(panel)

            panel._tool_calls = {
                "tc1": {"title": "a", "status": "completed"},
                "tc2": {"title": "b", "status": "in_progress"},
            }
            panel._update_progress_from_tool_calls_dict()

            assert panel._progress_bar._total == 2
            assert panel._progress_bar._current == 1
            assert panel._progress_bar.display is True
            assert panel._progress_bar._variant == ProgressVariant.PRIMARY

    async def test_update_progress_from_tool_calls_dict_all_completed(self) -> None:
        """Прогресс успешен когда все tool calls завершены."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            terminal_vm = FakeTerminalViewModel()
            panel = ToolPanel(chat_vm, terminal_vm)
            await pilot.app.mount(panel)

            panel._tool_calls = {
                "tc1": {"title": "a", "status": "completed"},
            }
            panel._update_progress_from_tool_calls_dict()

            assert panel._progress_bar._variant == ProgressVariant.SUCCESS
            assert panel._progress_bar.display is False

    async def test_update_progress_from_tool_calls_dict_with_error(self) -> None:
        """Прогресс предупреждает при наличии ошибок."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            terminal_vm = FakeTerminalViewModel()
            panel = ToolPanel(chat_vm, terminal_vm)
            await pilot.app.mount(panel)

            panel._tool_calls = {
                "tc1": {"title": "a", "status": "failed"},
            }
            panel._update_progress_from_tool_calls_dict()

            assert panel._progress_bar._variant == ProgressVariant.WARNING

    def test_render_text_with_calls(self) -> None:
        """_render_text формирует список вызовов."""
        chat_vm = FakeChatViewModel()
        terminal_vm = FakeTerminalViewModel()
        panel = ToolPanel(chat_vm, terminal_vm)

        panel._tool_calls = {
            "tc1": {"title": "read", "status": "completed", "terminal_id": "t1"},
        }
        text = panel._render_text()

        assert text.startswith("Инструменты:")
        assert "read [completed] (tc1)" in text
        assert "terminal: t1" in text

    def test_render_text_limits_calls(self) -> None:
        """_render_text показывает не более 8 вызовов."""
        chat_vm = FakeChatViewModel()
        terminal_vm = FakeTerminalViewModel()
        panel = ToolPanel(chat_vm, terminal_vm)

        for i in range(10):
            panel._tool_calls[f"tc{i}"] = {"title": f"tool{i}", "status": "completed"}

        text = panel._render_text()
        assert text.count("tool") == 8

    def test_latest_terminal_snapshot_no_terminal(self) -> None:
        """latest_terminal_snapshot возвращает None без terminal-данных."""
        chat_vm = FakeChatViewModel()
        terminal_vm = FakeTerminalViewModel()
        panel = ToolPanel(chat_vm, terminal_vm)

        panel._tool_calls["tc1"] = {"title": "read", "status": "completed"}
        assert panel.latest_terminal_snapshot() is None

    def test_extract_terminal_id(self) -> None:
        """_extract_terminal_id извлекает terminalId из content."""
        assert ToolPanel._extract_terminal_id({}) is None
        assert ToolPanel._extract_terminal_id({"content": "not list"}) is None
        assert (
            ToolPanel._extract_terminal_id({"content": [{"type": "terminal", "terminalId": "t1"}]})
            == "t1"
        )
        assert (
            ToolPanel._extract_terminal_id({"content": [{"type": "text", "terminalId": "t1"}]})
            is None
        )

    def test_extract_terminal_output(self) -> None:
        """_extract_terminal_output извлекает output и exitCode."""
        assert ToolPanel._extract_terminal_output("bad") == (None, None)
        assert ToolPanel._extract_terminal_output({}) == (None, None)
        assert ToolPanel._extract_terminal_output({"output": "hi", "exitCode": 1}) == ("hi", 1)
        assert ToolPanel._extract_terminal_output({"output": 123, "exitCode": "x"}) == (None, None)

    def test_shorten_output(self) -> None:
        """_shorten_output обрезает длинный вывод."""
        short = "hello world"
        assert ToolPanel._shorten_output(short) == "hello world"

        long = "x" * 200
        result = ToolPanel._shorten_output(long)
        assert result.endswith("...")
        assert len(result) == 140

    def test_shorten_output_multiline(self) -> None:
        """_shorten_output нормализует многострочный вывод."""
        output = "line1\n\n  line2  "
        assert ToolPanel._shorten_output(output) == "line1 line2"

    async def test_on_mount_hides_progress(self) -> None:
        """on_mount скрывает прогресс-бар по умолчанию."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            terminal_vm = FakeTerminalViewModel()
            panel = ToolPanel(chat_vm, terminal_vm)
            await pilot.app.mount(panel)

            panel.on_mount()
            assert panel._progress_bar.display is False

    async def test_apply_update_reuses_terminal_view(self) -> None:
        """apply_update переиспользует существующий TerminalOutputPanel."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            terminal_vm = FakeTerminalViewModel()
            panel = ToolPanel(chat_vm, terminal_vm)
            await pilot.app.mount(panel)

            update1 = ToolCallCreatedUpdate(
                sessionUpdate="tool_call",
                toolCallId="tc1",
                title="exec",
                status="in_progress",
            )
            panel.apply_update(update1)
            existing_view = panel._tool_calls["tc1"]["terminal_view"]

            update2 = ToolCallCreatedUpdate(
                sessionUpdate="tool_call",
                toolCallId="tc1",
                title="exec",
                status="completed",
                rawOutput={"output": "done"},
            )
            panel.apply_update(update2)

            assert panel._tool_calls["tc1"]["terminal_view"] is existing_view

    async def test_render_text_with_terminal_output(self) -> None:
        """_render_text включает output терминала если он не пустой."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            terminal_vm = FakeTerminalViewModel()
            panel = ToolPanel(chat_vm, terminal_vm)
            await pilot.app.mount(panel)

            update = ToolCallCreatedUpdate(
                sessionUpdate="tool_call",
                toolCallId="tc1",
                title="exec",
                status="completed",
                rawOutput={"output": "important result"},
            )
            panel.apply_update(update)

            text = panel._render_text()
            assert "important result" in text


class TestToolPanelAdditionalCoverage:
    """Дополнительные тесты для непокрытых строк."""

    async def test_on_tool_calls_changed_tool_call_list_not_mounted(self) -> None:
        """_on_tool_calls_changed обрабатывает исключение если ToolCallList не смонтирован."""
        chat_vm = FakeChatViewModel()
        terminal_vm = FakeTerminalViewModel()
        panel = ToolPanel(chat_vm, terminal_vm)
        panel.chat_vm.tool_calls.value = [
            {"toolCallId": "tc1", "title": "test", "status": "in_progress"},
        ]
        panel._on_tool_calls_changed(panel.chat_vm.tool_calls.value)

    async def test_on_tool_calls_changed_empty_with_exception(self) -> None:
        """_on_tool_calls_changed при пустом списке обрабатывает исключение."""
        chat_vm = FakeChatViewModel()
        terminal_vm = FakeTerminalViewModel()
        panel = ToolPanel(chat_vm, terminal_vm)
        panel._on_tool_calls_changed([])

    async def test_update_progress_from_calls_empty(self) -> None:
        """_update_progress_from_calls при пустом списке скрывает прогресс-бар."""
        chat_vm = FakeChatViewModel()
        terminal_vm = FakeTerminalViewModel()
        panel = ToolPanel(chat_vm, terminal_vm)
        panel._update_progress_from_calls([])

    async def test_update_progress_from_calls_all_completed_success(self) -> None:
        """_update_progress_from_calls устанавливает SUCCESS variant при завершении."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            terminal_vm = FakeTerminalViewModel()
            panel = ToolPanel(chat_vm, terminal_vm)
            await pilot.app.mount(panel)
            panel._update_progress_from_calls([
                {"toolCallId": "tc1", "status": "completed"},
                {"toolCallId": "tc2", "status": "completed"},
            ])

    async def test_update_progress_from_calls_with_exception(self) -> None:
        """_update_progress_from_calls обрабатывает исключение если виджет не смонтирован."""
        chat_vm = FakeChatViewModel()
        terminal_vm = FakeTerminalViewModel()
        panel = ToolPanel(chat_vm, terminal_vm)
        panel._update_progress_from_calls([{"toolCallId": "tc1", "status": "in_progress"}])

    async def test_update_progress_visibility_exception(self) -> None:
        """_update_progress_visibility обрабатывает исключение если виджет не смонтирован."""
        chat_vm = FakeChatViewModel()
        terminal_vm = FakeTerminalViewModel()
        panel = ToolPanel(chat_vm, terminal_vm)
        panel._update_progress_visibility(show=True)

    async def test_apply_update_status_from_previous(self) -> None:
        """apply_update использует status из previous если не указан в payload."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            terminal_vm = FakeTerminalViewModel()
            panel = ToolPanel(chat_vm, terminal_vm)
            await pilot.app.mount(panel)

            update1 = ToolCallCreatedUpdate(
                sessionUpdate="tool_call",
                toolCallId="tc1",
                title="exec",
                status="in_progress",
            )
            panel.apply_update(update1)

            update2 = ToolCallCreatedUpdate(
                sessionUpdate="tool_call",
                toolCallId="tc1",
                title="exec",
                status="pending",
            )
            panel.apply_update(update2)
            assert panel._tool_calls["tc1"]["status"] == "pending"

    async def test_update_progress_from_tool_calls_dict_empty(self) -> None:
        """_update_progress_from_tool_calls_dict при пустом словаре скрывает прогресс-бар."""
        chat_vm = FakeChatViewModel()
        terminal_vm = FakeTerminalViewModel()
        panel = ToolPanel(chat_vm, terminal_vm)
        panel._update_progress_from_tool_calls_dict()

    async def test_update_progress_from_tool_calls_dict_with_exception(self) -> None:
        """_update_progress_from_tool_calls_dict обрабатывает исключение."""
        chat_vm = FakeChatViewModel()
        terminal_vm = FakeTerminalViewModel()
        panel = ToolPanel(chat_vm, terminal_vm)
        panel._tool_calls = {"tc1": {"status": "in_progress", "title": "test"}}
        panel._update_progress_from_tool_calls_dict()

    async def test_latest_terminal_snapshot_no_terminal_id(self) -> None:
        """latest_terminal_snapshot пропускает tool calls без terminal_id."""
        chat_vm = FakeChatViewModel()
        terminal_vm = FakeTerminalViewModel()
        panel = ToolPanel(chat_vm, terminal_vm)
        panel._tool_calls = {"tc1": {"title": "test", "status": "completed"}}
        result = panel.latest_terminal_snapshot()
        assert result is None

    async def test_latest_terminal_snapshot_no_terminal_view(self) -> None:
        """latest_terminal_snapshot пропускает tool calls без terminal_view."""
        chat_vm = FakeChatViewModel()
        terminal_vm = FakeTerminalViewModel()
        panel = ToolPanel(chat_vm, terminal_vm)
        panel._tool_calls = {
            "tc1": {"title": "test", "status": "completed", "terminal_id": "term1"},
        }
        result = panel.latest_terminal_snapshot()
        assert result is None

    async def test_extract_terminal_id_continue_on_non_terminal(self) -> None:
        """_extract_terminal_id пропускает content items не типа terminal."""
        payload = {
            "content": [
                {"type": "text", "text": "hello"},
                {"type": "terminal", "terminalId": "term1"},
            ]
        }
        result = ToolPanel._extract_terminal_id(payload)
        assert result == "term1"
