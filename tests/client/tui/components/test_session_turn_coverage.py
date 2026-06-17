"""Тесты покрытия для SessionTurn компонента.

Проверяют индикатор статуса, виджет tool call и жизненный цикл turn.
"""

from __future__ import annotations

from datetime import datetime

from textual.app import App

from codelab.client.tui.components.session_turn import (
    SessionTurn,
    ToolCallWidget,
    TurnData,
    TurnStatus,
    TurnStatusIndicator,
)


class TestTurnStatusIndicator:
    """Тесты для TurnStatusIndicator."""

    def test_init_pending(self) -> None:
        """Инициализация с статусом pending."""
        indicator = TurnStatusIndicator(TurnStatus.PENDING)
        assert indicator._status == TurnStatus.PENDING
        assert "pending" in indicator.classes

    def test_init_complete(self) -> None:
        """Инициализация с статусом complete не показывает метку."""
        indicator = TurnStatusIndicator(TurnStatus.COMPLETE)
        assert "✅" in indicator._Static__content

    def test_update_status(self) -> None:
        """update_status меняет класс и текст."""
        indicator = TurnStatusIndicator(TurnStatus.PENDING)
        indicator.update_status(TurnStatus.ERROR)

        assert indicator._status == TurnStatus.ERROR
        assert "error" in indicator.classes
        assert "pending" not in indicator.classes
        assert "❌" in indicator._Static__content


class TestToolCallWidget:
    """Тесты для ToolCallWidget."""

    def test_init_with_arguments(self) -> None:
        """Инициализация с аргументами форматирует их в текст."""
        widget = ToolCallWidget(
            "read_file",
            arguments={"path": "/tmp", "limit": 10},
            result="done",
        )
        text = widget._Static__content
        assert "read_file" in text
        assert "path=" in text
        assert "done" in text

    def test_init_trims_arguments(self) -> None:
        """Более 3 аргументов обрезаются."""
        widget = ToolCallWidget(
            "tool",
            arguments={"a": 1, "b": 2, "c": 3, "d": 4},
        )
        text = widget._Static__content
        assert "..." in text

    def test_init_trims_result(self) -> None:
        """Длинный результат обрезается."""
        widget = ToolCallWidget("tool", result="x" * 200)
        text = widget._Static__content
        assert text.count("...") >= 1


class TestSessionTurn:
    """Тесты для SessionTurn."""

    async def test_init_defaults(self) -> None:
        """Инициализация с значениями по умолчанию."""
        turn = SessionTurn(turn_id="t1", user_content="hello")

        assert turn.turn_id == "t1"
        assert turn.user_content == "hello"
        assert turn.status == TurnStatus.PENDING
        assert turn._collapsible is True

    async def test_compose_and_mount(self) -> None:
        """Компонент создаёт секции после монтирования."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            turn = SessionTurn(turn_id="t1", user_content="hello")
            await pilot.app.mount(turn)

            assert turn._status_indicator is not None
            assert turn._assistant_section is not None
            assert turn._tool_calls_section is not None

    async def test_mount_with_assistant_content(self) -> None:
        """on_mount показывает сообщение ассистента если оно задано."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            turn = SessionTurn(
                turn_id="t1",
                user_content="hello",
                assistant_content="hi",
                status=TurnStatus.COMPLETE,
            )
            await pilot.app.mount(turn)

            assert turn._assistant_bubble is not None
            assert turn.has_class("complete")

    async def test_mount_pending_shows_thinking(self) -> None:
        """on_mount показывает индикатор thinking для pending статуса."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            turn = SessionTurn(turn_id="t1", user_content="hello")
            await pilot.app.mount(turn)

            assert turn._thinking_indicator is not None

    async def test_watch_status(self) -> None:
        """Изменение статуса обновляет индикатор и классы."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            turn = SessionTurn(turn_id="t1", user_content="hello")
            await pilot.app.mount(turn)

            turn.status = TurnStatus.STREAMING

            assert turn._status_indicator._status == TurnStatus.STREAMING
            assert turn.has_class("streaming")
            assert not turn.has_class("pending")

    async def test_start_streaming(self) -> None:
        """start_streaming переводит turn в streaming и показывает виджет."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            turn = SessionTurn(turn_id="t1", user_content="hello")
            await pilot.app.mount(turn)

            turn.start_streaming()

            assert turn.status == TurnStatus.STREAMING
            assert turn._streaming_widget is not None
            assert turn._thinking_indicator is None

    async def test_update_streaming(self) -> None:
        """update_streaming обновляет текст виджета."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            turn = SessionTurn(turn_id="t1", user_content="hello")
            await pilot.app.mount(turn)
            turn.start_streaming()

            turn.update_streaming("hello world")

            assert turn._streaming_widget.text == "hello world"

    async def test_append_streaming(self) -> None:
        """append_streaming добавляет текст к виджету."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            turn = SessionTurn(turn_id="t1", user_content="hello")
            await pilot.app.mount(turn)
            turn.start_streaming()
            turn.update_streaming("hello")

            turn.append_streaming(" world")

            assert turn._streaming_widget.text == "hello world"

    async def test_complete(self) -> None:
        """complete завершает turn и показывает ответ ассистента."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            turn = SessionTurn(turn_id="t1", user_content="hello")
            await pilot.app.mount(turn)
            turn.start_streaming()

            turn.complete("Final answer")

            assert turn.status == TurnStatus.COMPLETE
            assert turn.assistant_content == "Final answer"
            assert turn._assistant_bubble is not None
            assert turn._streaming_widget is None

    async def test_fail(self) -> None:
        """fail завершает turn с ошибкой."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            turn = SessionTurn(turn_id="t1", user_content="hello")
            await pilot.app.mount(turn)

            turn.fail("something wrong")

            assert turn.status == TurnStatus.ERROR
            assert "something wrong" in turn.assistant_content
            assert turn.has_class("error")

    async def test_cancel(self) -> None:
        """cancel отменяет turn."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            turn = SessionTurn(turn_id="t1", user_content="hello")
            await pilot.app.mount(turn)

            turn.cancel()

            assert turn.status == TurnStatus.CANCELLED
            assert "отменен" in turn.assistant_content
            assert turn.has_class("cancelled")

    async def test_add_tool_call(self) -> None:
        """add_tool_call добавляет виджет tool call."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            turn = SessionTurn(turn_id="t1", user_content="hello")
            await pilot.app.mount(turn)

            turn.add_tool_call({"name": "read", "arguments": {"path": "/tmp"}})

            assert len(turn.tool_calls) == 1
            assert len(turn._tool_calls_section.query("*")) == 1

    async def test_add_tool_call_with_result(self) -> None:
        """add_tool_call с результатом отображает его."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            turn = SessionTurn(turn_id="t1", user_content="hello")
            await pilot.app.mount(turn)

            turn.add_tool_call({"name": "read", "arguments": {}, "result": "data"})

            assert turn.tool_calls[0]["result"] == "data"

    def test_properties(self) -> None:
        """Свойства user_content, assistant_content и tool_calls."""
        turn = SessionTurn(
            turn_id="t1",
            user_content="hello",
            assistant_content="hi",
            tool_calls=[{"name": "x"}],
        )

        assert turn.user_content == "hello"
        assert turn.assistant_content == "hi"
        assert turn.tool_calls == [{"name": "x"}]

        # tool_calls возвращает копию
        turn.tool_calls.append({"name": "y"})
        assert len(turn._tool_calls) == 1

    def test_from_data(self) -> None:
        """from_data создаёт SessionTurn из TurnData."""
        data = TurnData(
            turn_id="t1",
            user_content="hello",
            assistant_content="hi",
            status=TurnStatus.COMPLETE,
        )
        turn = SessionTurn.from_data(data)

        assert turn.turn_id == "t1"
        assert turn.status == TurnStatus.COMPLETE

    async def test_initial_status_complete(self) -> None:
        """Инициализация с COMPLETE статусом работает корректно."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            turn = SessionTurn(
                turn_id="t1",
                user_content="hello",
                status=TurnStatus.COMPLETE,
            )
            await pilot.app.mount(turn)

            assert turn._status_indicator._status == TurnStatus.COMPLETE

    async def test_render_tool_calls(self) -> None:
        """_render_tool_calls рендерит tool calls."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            turn = SessionTurn(
                turn_id="t1",
                user_content="hello",
            )
            await pilot.app.mount(turn)

            turn._tool_calls = [{"name": "a"}]
            turn._render_tool_calls()

            assert len(turn._tool_calls_section.children) == 1

    async def test_hide_thinking_when_none(self) -> None:
        """_hide_thinking не падает если индикатора нет."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            turn = SessionTurn(turn_id="t1", user_content="hello")
            await pilot.app.mount(turn)

            turn._thinking_indicator = None
            turn._hide_thinking()
            assert turn._thinking_indicator is None

    async def test_hide_streaming_when_none(self) -> None:
        """_hide_streaming не падает если виджета нет."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            turn = SessionTurn(turn_id="t1", user_content="hello")
            await pilot.app.mount(turn)

            turn._streaming_widget = None
            turn._hide_streaming()
            assert turn._streaming_widget is None

    async def test_show_assistant_message_replaces_old(self) -> None:
        """_show_assistant_message заменяет старый bubble."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            turn = SessionTurn(turn_id="t1", user_content="hello")
            await pilot.app.mount(turn)

            turn.complete("first")
            old_bubble = turn._assistant_bubble
            turn.complete("second")

            assert turn._assistant_bubble is not old_bubble
