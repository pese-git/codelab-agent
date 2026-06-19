"""Тесты для ChatSessionState."""

from __future__ import annotations

from codelab.client.presentation.chat.chat_session_state import ChatSessionState


class TestChatSessionState:
    """Тесты для ChatSessionState."""

    def test_state_creation_with_defaults(self) -> None:
        """State должен создаваться с пустыми значениями по умолчанию."""
        state = ChatSessionState()

        assert state.messages == []
        assert state.tool_calls == []
        assert state.pending_permissions == []
        assert state.streaming_text == ""
        assert state.is_streaming is False
        assert state.last_stop_reason is None
        assert state.replay_updates == []

    def test_state_creation_with_initial_values(self) -> None:
        """State должен принимать начальные значения."""
        messages = [{"role": "user", "content": "Hello"}]
        tool_calls = [{"toolCallId": "tc-1", "title": "Read"}]

        state = ChatSessionState(
            messages=messages,
            tool_calls=tool_calls,
            streaming_text="Test",
            is_streaming=True,
        )

        assert state.messages == messages
        assert state.tool_calls == tool_calls
        assert state.streaming_text == "Test"
        assert state.is_streaming is True

    def test_add_message(self) -> None:
        """add_message должен добавлять сообщение в историю."""
        state = ChatSessionState()

        state.add_message("user", "Hello")
        state.add_message("assistant", "Hi there!")

        assert len(state.messages) == 2
        assert state.messages[0] == {"role": "user", "content": "Hello"}
        assert state.messages[1] == {"role": "assistant", "content": "Hi there!"}

    def test_append_streaming_text(self) -> None:
        """append_streaming_text должен добавлять текст и устанавливать флаг."""
        state = ChatSessionState()

        state.append_streaming_text("Hello")
        assert state.streaming_text == "Hello"
        assert state.is_streaming is True

        state.append_streaming_text(" World")
        assert state.streaming_text == "Hello World"
        assert state.is_streaming is True

    def test_finalize_streaming_with_text(self) -> None:
        """finalize_streaming должен сохранять текст в историю."""
        state = ChatSessionState()
        state.streaming_text = "Hello World"
        state.is_streaming = True

        state.finalize_streaming()

        assert len(state.messages) == 1
        assert state.messages[0] == {"role": "assistant", "content": "Hello World"}
        assert state.streaming_text == ""
        assert state.is_streaming is False

    def test_finalize_streaming_without_text(self) -> None:
        """finalize_streaming не должен добавлять пустое сообщение."""
        state = ChatSessionState()
        state.is_streaming = True

        state.finalize_streaming()

        assert len(state.messages) == 0
        assert state.streaming_text == ""
        assert state.is_streaming is False

    def test_add_tool_call(self) -> None:
        """add_tool_call должен добавлять tool call в список."""
        state = ChatSessionState()

        tool_call = {
            "toolCallId": "tc-1",
            "title": "Read file",
            "status": "pending",
            "kind": "read",
        }
        state.add_tool_call(tool_call)

        assert len(state.tool_calls) == 1
        assert state.tool_calls[0] == tool_call

    def test_update_tool_call(self) -> None:
        """update_tool_call должен обновлять существующий tool call."""
        state = ChatSessionState()
        state.add_tool_call({
            "toolCallId": "tc-1",
            "title": "Read file",
            "status": "pending",
        })

        state.update_tool_call("tc-1", status="completed", title="Read file.py")

        assert state.tool_calls[0]["status"] == "completed"
        assert state.tool_calls[0]["title"] == "Read file.py"

    def test_update_tool_call_nonexistent(self) -> None:
        """update_tool_call не должен делать ничего для несуществующего ID."""
        state = ChatSessionState()
        state.add_tool_call({
            "toolCallId": "tc-1",
            "title": "Read file",
            "status": "pending",
        })

        state.update_tool_call("tc-999", status="completed")

        # Существующий tool call не должен измениться
        assert state.tool_calls[0]["status"] == "pending"

    def test_clear(self) -> None:
        """clear должен очищать все данные кроме replay_updates."""
        state = ChatSessionState(
            messages=[{"role": "user", "content": "Hello"}],
            tool_calls=[{"toolCallId": "tc-1"}],
            pending_permissions=["perm-1"],
            streaming_text="Test",
            is_streaming=True,
            last_stop_reason="end_turn",
            replay_updates=[{"update": "data"}],
        )

        state.clear()

        assert state.messages == []
        assert state.tool_calls == []
        assert state.pending_permissions == []
        assert state.streaming_text == ""
        assert state.is_streaming is False
        assert state.last_stop_reason is None
        # replay_updates не очищаются
        assert state.replay_updates == [{"update": "data"}]

    def test_state_equality(self) -> None:
        """Два state с одинаковыми данными должны быть равны."""
        state1 = ChatSessionState(
            messages=[{"role": "user", "content": "Hello"}],
            streaming_text="Test",
        )
        state2 = ChatSessionState(
            messages=[{"role": "user", "content": "Hello"}],
            streaming_text="Test",
        )

        assert state1 == state2

    def test_state_inequality(self) -> None:
        """Два state с разными данными не должны быть равны."""
        state1 = ChatSessionState(streaming_text="Test1")
        state2 = ChatSessionState(streaming_text="Test2")

        assert state1 != state2
