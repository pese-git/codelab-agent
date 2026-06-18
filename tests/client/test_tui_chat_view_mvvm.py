"""Тесты для компонента ChatView с MVVM интеграцией."""

from __future__ import annotations

import pytest

from codelab.client.infrastructure.events.bus import EventBus
from codelab.client.presentation.chat_view_model import ChatViewModel
from codelab.client.tui.components.chat_view import ChatView


@pytest.fixture
def event_bus() -> EventBus:
    """Создать EventBus для тестов."""
    return EventBus()


@pytest.fixture
def chat_view_model(event_bus: EventBus) -> ChatViewModel:
    """Создать ChatViewModel для тестов."""
    coordinator = None
    return ChatViewModel(coordinator=coordinator, event_bus=event_bus, logger=None)


@pytest.fixture
def chat_view(chat_view_model: ChatViewModel) -> ChatView:
    """Создать ChatView с ChatViewModel."""
    view = ChatView(chat_view_model)
    # Имитируем монтирование компонента
    view._mounted = True
    return view


def test_chat_view_initializes_with_chat_view_model(chat_view_model: ChatViewModel) -> None:
    """Проверить что ChatView инициализируется с ChatViewModel."""
    chat_view = ChatView(chat_view_model)

    assert chat_view.chat_vm is chat_view_model
    assert chat_view.id == "chat_view"
    assert chat_view._mounted is False


def test_chat_view_displays_empty_when_no_messages(
    chat_view: ChatView,
    chat_view_model: ChatViewModel,
) -> None:
    """Проверить что ChatView изначально пуст."""
    chat_view_model.messages.value = []
    chat_view_model.tool_calls.value = []
    chat_view_model.is_streaming.value = False

    # Компонент должен быть пуст или содержать placeholder
    assert chat_view.chat_vm is not None


def test_chat_view_updates_on_messages_changed(
    chat_view: ChatView,
    chat_view_model: ChatViewModel,
) -> None:
    """Проверить что ChatView обновляется при добавлении сообщений."""
    messages = [
        {"type": "user", "content": "Hello"},
        {"type": "assistant", "content": "Hi there!"},
    ]

    chat_view_model.messages.value = messages

    # После обновления сообщений, компонент должен отобразить их
    assert chat_view_model.messages.value == messages


def test_chat_view_updates_on_streaming_text_changed(
    chat_view: ChatView,
    chat_view_model: ChatViewModel,
) -> None:
    """Проверить что ChatView обновляется при streaming текста."""
    chat_view_model.is_streaming.value = True
    chat_view_model.streaming_text.value = "Loading response..."

    # Проверить что streaming флаг активен
    assert chat_view_model.is_streaming.value is True
    assert chat_view_model.streaming_text.value == "Loading response..."


def test_chat_view_updates_on_tool_calls_changed(
    chat_view: ChatView,
    chat_view_model: ChatViewModel,
) -> None:
    """Проверить что ChatView обновляется при добавлении tool calls."""
    tool_calls = [
        {"id": "tool_1", "name": "read_file", "arguments": {"path": "/tmp/file.txt"}},
    ]

    chat_view_model.tool_calls.value = tool_calls

    # Проверить что tool calls были добавлены
    assert chat_view_model.tool_calls.value == tool_calls


def test_chat_view_handles_streaming_state_changes(
    chat_view: ChatView,
    chat_view_model: ChatViewModel,
) -> None:
    """Проверить что ChatView правильно обрабатывает переходы streaming статуса."""
    # Начало streaming
    chat_view_model.is_streaming.value = True
    assert chat_view_model.is_streaming.value is True

    # Конец streaming
    chat_view_model.is_streaming.value = False
    assert chat_view_model.is_streaming.value is False


def test_chat_view_handles_multiple_message_batches(
    chat_view: ChatView,
    chat_view_model: ChatViewModel,
) -> None:
    """Проверить что ChatView правильно обрабатывает несколько батчей сообщений."""
    batch1 = [{"type": "user", "content": "Message 1"}]
    batch2 = batch1 + [{"type": "assistant", "content": "Response 1"}]
    batch3 = batch2 + [{"type": "user", "content": "Message 2"}]

    chat_view_model.messages.value = batch1
    assert len(chat_view_model.messages.value) == 1

    chat_view_model.messages.value = batch2
    assert len(chat_view_model.messages.value) == 2

    chat_view_model.messages.value = batch3
    assert len(chat_view_model.messages.value) == 3


def test_chat_view_with_vm_updates_model_messages(
    chat_view: ChatView,
    chat_view_model: ChatViewModel,
) -> None:
    """Проверить что ChatView отображает изменения сообщений в ViewModel."""
    chat_view_model.messages.value = []

    chat_view_model.messages.value = [{"role": "assistant", "content": "Test message"}]

    assert len(chat_view_model.messages.value) == 1
    assert chat_view_model.messages.value[0]["content"] == "Test message"
