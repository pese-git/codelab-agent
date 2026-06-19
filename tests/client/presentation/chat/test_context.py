"""Тесты для ChatUpdateContext."""

from __future__ import annotations

from typing import Any

from codelab.client.presentation.chat.chat_session_state import ChatSessionState
from codelab.client.presentation.chat.context import ChatUpdateContext


class MockSink:
    """Mock реализация ChatUpdateSink для тестов."""

    def sync_messages(self, session_id: str, messages: list[dict[str, str]]) -> None:
        pass

    def sync_tool_calls(
        self, session_id: str, tool_calls: list[dict[str, Any]]
    ) -> None:
        pass

    def sync_streaming(
        self, session_id: str, text: str, is_streaming: bool
    ) -> None:
        pass


class TestChatUpdateContext:
    """Тесты для ChatUpdateContext."""

    def test_context_creation_with_required_fields(self) -> None:
        """Context должен создаваться с обязательными полями."""
        state = ChatSessionState()
        sink = MockSink()

        context = ChatUpdateContext(
            session_id="test-session",
            state=state,
            sink=sink,
        )

        assert context.session_id == "test-session"
        assert context.state is state
        assert context.sink is sink
        assert context.plan_vm is None
        assert context.event_bus is None

    def test_context_creation_with_optional_fields(self) -> None:
        """Context должен создаваться с опциональными полями."""
        state = ChatSessionState()
        sink = MockSink()

        context = ChatUpdateContext(
            session_id="test-session",
            state=state,
            sink=sink,
            plan_vm=None,  # Можно передать None явно
            event_bus=None,
        )

        assert context.plan_vm is None
        assert context.event_bus is None

    def test_context_logger_created_automatically(self) -> None:
        """Logger должен создаваться автоматически при первом обращении."""
        state = ChatSessionState()
        sink = MockSink()

        context = ChatUpdateContext(
            session_id="test-session",
            state=state,
            sink=sink,
        )

        # Logger должен создаваться при первом обращении
        logger = context.logger
        assert logger is not None

        # Повторное обращение должно возвращать тот же logger
        assert context.logger is logger

    def test_context_create_child_with_new_session_id(self) -> None:
        """create_child должен создавать контекст с новым session_id."""
        state = ChatSessionState()
        sink = MockSink()

        parent = ChatUpdateContext(
            session_id="parent-session",
            state=state,
            sink=sink,
        )

        child = parent.create_child(session_id="child-session")

        assert child.session_id == "child-session"
        assert child.state is state  # State тот же
        assert child.sink is sink  # Sink тот же

    def test_context_create_child_with_new_state(self) -> None:
        """create_child должен создавать контекст с новым state."""
        parent_state = ChatSessionState()
        child_state = ChatSessionState()
        sink = MockSink()

        parent = ChatUpdateContext(
            session_id="test-session",
            state=parent_state,
            sink=sink,
        )

        child = parent.create_child(state=child_state)

        assert child.session_id == "test-session"  # Session ID тот же
        assert child.state is child_state  # State новый
        assert child.sink is sink  # Sink тот же

    def test_context_create_child_preserves_optional_fields(self) -> None:
        """create_child должен сохранять опциональные поля."""
        state = ChatSessionState()
        sink = MockSink()

        parent = ChatUpdateContext(
            session_id="test-session",
            state=state,
            sink=sink,
            plan_vm=None,
            event_bus=None,
        )

        child = parent.create_child()

        assert child.plan_vm is parent.plan_vm
        assert child.event_bus is parent.event_bus

    def test_context_state_is_mutable(self) -> None:
        """State должен быть изменяемым."""
        state = ChatSessionState()
        sink = MockSink()

        context = ChatUpdateContext(
            session_id="test-session",
            state=state,
            sink=sink,
        )

        # Модифицируем state через context
        context.state.add_message("user", "Hello")
        context.state.streaming_text = "Test"

        assert len(context.state.messages) == 1
        assert context.state.streaming_text == "Test"

    def test_context_repr_does_not_include_logger(self) -> None:
        """repr не должен включать logger."""
        state = ChatSessionState()
        sink = MockSink()

        context = ChatUpdateContext(
            session_id="test-session",
            state=state,
            sink=sink,
        )

        # Обращаемся к logger чтобы он создался
        _ = context.logger

        repr_str = repr(context)
        assert "BoundLogger" not in repr_str
