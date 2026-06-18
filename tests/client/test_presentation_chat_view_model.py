"""Тесты session-aware поведения ChatViewModel."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from codelab.client.infrastructure.events.bus import EventBus
from codelab.client.presentation.chat.dispatcher.session_update_dispatcher import (
    SessionUpdateDispatcher,
)
from codelab.client.presentation.chat.handlers.config_option_handler import (
    ConfigOptionHandler,
)
from codelab.client.presentation.chat.handlers.message_chunk_handler import (
    MessageChunkHandler,
)
from codelab.client.presentation.chat.handlers.plan_update_handler import (
    PlanUpdateHandler,
)
from codelab.client.presentation.chat.handlers.tool_call_handler import ToolCallHandler
from codelab.client.presentation.chat_view_model import ChatViewModel


@pytest.fixture
def session_update_dispatcher() -> SessionUpdateDispatcher:
    """Создает SessionUpdateDispatcher с тестовыми handlers."""
    return SessionUpdateDispatcher(
        message_chunk_handler=MessageChunkHandler(),
        tool_call_handler=ToolCallHandler(),
        plan_update_handler=PlanUpdateHandler(),
        config_option_handler=ConfigOptionHandler(),
    )


@pytest.fixture
def chat_persistence() -> Mock:
    """Создает mock ChatPersistencePort."""
    persistence = Mock()
    persistence.save_messages = AsyncMock()
    persistence.load_messages_sync = Mock(return_value=[])
    persistence.load_replay_updates_sync = Mock(return_value=[])
    return persistence


@pytest.fixture
def chat_view_model(
    session_update_dispatcher: SessionUpdateDispatcher,
    chat_persistence: Mock,
) -> ChatViewModel:
    """Создает ChatViewModel для тестов."""

    return ChatViewModel(
        coordinator=None,
        event_bus=EventBus(),
        logger=None,
        session_update_dispatcher=session_update_dispatcher,
        chat_persistence=chat_persistence,
    )


def test_chat_state_isolated_between_sessions(chat_view_model: ChatViewModel) -> None:
    """История сообщений хранится отдельно для каждой сессии."""

    chat_view_model.set_active_session("sess_1")
    chat_view_model.add_message("user", "hello from s1")

    chat_view_model.set_active_session("sess_2")
    assert chat_view_model.messages.value == []
    chat_view_model.add_message("user", "hello from s2")

    chat_view_model.set_active_session("sess_1")
    assert len(chat_view_model.messages.value) == 1
    assert chat_view_model.messages.value[0]["content"] == "hello from s1"

    chat_view_model.set_active_session("sess_2")
    assert len(chat_view_model.messages.value) == 1
    assert chat_view_model.messages.value[0]["content"] == "hello from s2"


def test_chat_resets_when_no_active_session(chat_view_model: ChatViewModel) -> None:
    """При отсутствии активной сессии отображается пустой чат."""

    chat_view_model.set_active_session("sess_1")
    chat_view_model.add_message("assistant", "saved message")

    chat_view_model.set_active_session(None)
    assert chat_view_model.messages.value == []

    chat_view_model.set_active_session("sess_1")
    assert len(chat_view_model.messages.value) == 1
    assert chat_view_model.messages.value[0]["content"] == "saved message"


def test_session_update_chunk_written_to_original_session(chat_view_model: ChatViewModel) -> None:
    """Chunk ответа сохраняется в сессию из params.sessionId, а не в активную."""

    chat_view_model.set_active_session("sess_1")
    chat_view_model.add_message("user", "question s1", session_id="sess_1")

    chat_view_model.set_active_session("sess_2")
    chat_view_model._handle_session_update(
        {
            "params": {
                "sessionId": "sess_1",
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"text": "answer s1"},
                },
            }
        }
    )

    # В активной сессии chunk не должен появиться.
    assert chat_view_model.streaming_text.value == ""

    # После возврата в исходную сессию chunk доступен.
    chat_view_model.set_active_session("sess_1")
    assert chat_view_model.streaming_text.value == "answer s1"


def test_restore_session_from_replay_rebuilds_messages(chat_view_model: ChatViewModel) -> None:
    """Replay updates из `session/load` восстанавливают историю сообщений."""

    chat_view_model.set_active_session("sess_replay")
    chat_view_model.restore_session_from_replay(
        "sess_replay",
        [
            {
                "params": {
                    "sessionId": "sess_replay",
                    "update": {
                        "sessionUpdate": "user_message_chunk",
                        "content": {"type": "text", "text": "hello"},
                    },
                }
            },
            {
                "params": {
                    "sessionId": "sess_replay",
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"type": "text", "text": "world"},
                    },
                }
            },
        ],
    )

    assert chat_view_model.messages.value == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]


def test_user_message_chunk_added_to_history(chat_view_model: ChatViewModel) -> None:
    """user_message_chunk обрабатывается и добавляется в историю сообщений."""

    chat_view_model.set_active_session("sess_user_chunk")

    # Обработаем user_message_chunk
    chat_view_model._handle_session_update(
        {
            "params": {
                "sessionId": "sess_user_chunk",
                "update": {
                    "sessionUpdate": "user_message_chunk",
                    "content": {"text": "user question"},
                },
            }
        }
    )

    # Сообщение должно быть добавлено в историю
    assert len(chat_view_model.messages.value) == 1
    assert chat_view_model.messages.value[0]["role"] == "user"
    assert chat_view_model.messages.value[0]["content"] == "user question"


def test_streaming_flag_resets_after_background_session_completion(
    chat_view_model: ChatViewModel,
) -> None:
    """Глобальный is_streaming сбрасывается после завершения неактивной сессии."""

    # Имитируем ситуацию, когда prompt-input уже отключен в UI.
    chat_view_model.is_streaming.value = True

    # Завершаем поток в неактивной для UI сессии.
    chat_view_model.set_active_session("sess_active")
    chat_view_model._set_streaming_state("sess_background", is_streaming=True, clear_text=False)
    chat_view_model._set_streaming_state("sess_background", is_streaming=False, clear_text=True)

    assert chat_view_model.is_streaming.value is False


async def test_restore_session_populates_model_list(chat_view_model: ChatViewModel) -> None:
    """Replay updates восстанавливают список моделей из config_option_update."""
    config_updated_events = []

    def on_config_updated(event):
        config_updated_events.append(event)

    try:
        from codelab.client.domain.events import ConfigOptionUpdatedEvent

        chat_view_model.on_event(ConfigOptionUpdatedEvent, on_config_updated)
    except ImportError:
        pytest.skip("ConfigOptionUpdatedEvent not available")

    chat_view_model.set_active_session("sess_with_models")

    replay_updates = [
        {
            "params": {
                "sessionId": "sess_with_models",
                "update": {
                    "sessionUpdate": "config_option_update",
                    "configOptions": [
                        {
                            "id": "model",
                            "category": "model",
                            "currentValue": "openai/gpt-4o",
                            "options": [
                                {
                                    "value": "openai/gpt-4o",
                                    "name": "gpt-4o",
                                    "description": "128K context",
                                },
                                {"value": "anthropic/claude-sonnet-4", "name": "claude-sonnet-4"},
                            ],
                        }
                    ],
                },
            }
        },
    ]

    chat_view_model.restore_session_from_replay("sess_with_models", replay_updates)

    # Ждём обработки asyncio.ensure_future
    await asyncio.sleep(0)

    assert len(config_updated_events) == 1
    assert config_updated_events[0].session_id == "sess_with_models"
    assert len(config_updated_events[0].config_options) == 1


def test_restore_session_restores_tool_calls(chat_view_model: ChatViewModel) -> None:
    """Replay updates восстанавливают tool calls."""

    chat_view_model.set_active_session("sess_with_tools")

    replay_updates = [
        {
            "params": {
                "sessionId": "sess_with_tools",
                "update": {
                    "sessionUpdate": "tool_call",
                    "toolCallId": "tool_123",
                    "title": "Read file",
                    "kind": "read",
                    "status": "completed",
                },
            }
        },
    ]

    chat_view_model.restore_session_from_replay("sess_with_tools", replay_updates)

    assert len(chat_view_model.tool_calls.value) == 1
    assert chat_view_model.tool_calls.value[0]["toolCallId"] == "tool_123"
    assert chat_view_model.tool_calls.value[0]["title"] == "Read file"
