"""Дополнительные тесты для повышения покрытия ChatViewModel.

Покрывают непротестированные ветки `src/codelab/client/presentation/chat_view_model.py`:
инициализацию, отправку prompt, обработку session/update, команды,
работу с persistence и event-обработчики.
"""

from __future__ import annotations

import asyncio
import builtins
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from codelab.client.domain.events import (
    ConfigOptionUpdatedEvent,
    ErrorOccurredEvent,
    PermissionRequestedEvent,
    PromptCompletedEvent,
    PromptStartedEvent,
)
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
from codelab.client.presentation.chat_view_model import ChatViewModel, PermissionRequest


@pytest.fixture
def coordinator() -> AsyncMock:
    """Создает AsyncMock координатора."""
    return AsyncMock()


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
    coordinator: AsyncMock,
    session_update_dispatcher: SessionUpdateDispatcher,
    chat_persistence: Mock,
) -> ChatViewModel:
    """Создает ChatViewModel с тестовыми зависимостями."""
    return ChatViewModel(
        coordinator=coordinator,
        event_bus=EventBus(),
        logger=None,
        session_update_dispatcher=session_update_dispatcher,
        chat_persistence=chat_persistence,
    )


class TestInitialization:
    """Тесты инициализации ChatViewModel."""

    def test_domain_events_import_error_skips_subscription(self) -> None:
        """При недоступности модуля событий подписки пропускаются."""
        real_import = builtins.__import__

        def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "codelab.client.domain.events":
                raise ImportError("events module not available")
            return real_import(name, *args, **kwargs)

        logger = MagicMock()
        import builtins as _builtins
        original_import = _builtins.__import__
        try:
            _builtins.__import__ = fake_import
            ChatViewModel(
                coordinator=MagicMock(),
                event_bus=MagicMock(),
                logger=logger,
            )
        finally:
            _builtins.__import__ = original_import

        logger.debug.assert_any_call(
            "DomainEvents not available, skipping event subscriptions"
        )


class TestSendPrompt:
    """Тесты команды отправки prompt."""

    async def test_send_prompt_empty_session_id(
        self,
        chat_view_model: ChatViewModel,
        coordinator: AsyncMock,
    ) -> None:
        """При пустом session_id prompt не отправляется."""
        await chat_view_model.send_prompt_cmd.execute("", "hello")
        coordinator.send_prompt.assert_not_called()

    async def test_send_prompt_success(
        self,
        chat_view_model: ChatViewModel,
        coordinator: AsyncMock,
    ) -> None:
        """Успешная отправка prompt передает callback'и и сохраняет ответ."""
        # Создаем mock terminal_callback_executor
        mock_terminal_cb = AsyncMock()
        mock_terminal_cb.create_terminal.return_value = ("term_1", None)
        mock_terminal_cb.get_output.return_value = ({"output": "test output"}, None)
        mock_terminal_cb.wait_for_exit.return_value = ((0, "test output"), None)
        mock_terminal_cb.release_terminal.return_value = None
        mock_terminal_cb.kill_terminal.return_value = (True, None)

        # Устанавливаем terminal_callback_executor
        chat_view_model._terminal_callback_executor = mock_terminal_cb

        async def fake_send(
            session_id: str,
            prompt_text: str,
            **kwargs: Any,
        ) -> None:
            if "on_terminal_create" in kwargs:
                tid = await kwargs["on_terminal_create"]("echo hi")
                await kwargs["on_terminal_output"](tid)
                await kwargs["on_terminal_wait_for_exit"](tid)
                await kwargs["on_terminal_release"](tid)
                await kwargs["on_terminal_kill"](tid)
            kwargs["on_update"](
                {
                    "params": {
                        "sessionId": session_id,
                        "update": {
                            "sessionUpdate": "agent_message_chunk",
                            "content": {"text": " partial"},
                        },
                    }
                }
            )

        coordinator.send_prompt.side_effect = fake_send

        await chat_view_model.send_prompt_cmd.execute("s", "hi")

        coordinator.send_prompt.assert_awaited_once()
        call_kwargs = coordinator.send_prompt.call_args.kwargs
        assert "on_update" in call_kwargs
        assert "on_fs_read" in call_kwargs
        assert "on_fs_write" in call_kwargs
        assert "on_terminal_create" in call_kwargs
        mock_terminal_cb.create_terminal.assert_awaited_once_with("echo hi")
        assert chat_view_model.messages.value == [
            {"role": "assistant", "content": " partial"}
        ]
        assert chat_view_model.is_streaming.value is False

    async def test_send_prompt_without_terminal_executor(
        self,
        coordinator: AsyncMock,
        session_update_dispatcher: SessionUpdateDispatcher,
    ) -> None:
        """Без terminal_callback_executor callback'и терминала не передаются."""
        vm = ChatViewModel(
            coordinator=coordinator,
            event_bus=EventBus(),
            logger=None,
            session_update_dispatcher=session_update_dispatcher,
        )
        coordinator.send_prompt.return_value = None

        await vm.send_prompt_cmd.execute("s", "hi")

        call_kwargs = coordinator.send_prompt.call_args.kwargs
        assert "on_terminal_create" not in call_kwargs

    async def test_send_prompt_exception_reraises(
        self,
        chat_view_model: ChatViewModel,
        coordinator: AsyncMock,
    ) -> None:
        """Исключение при отправке prompt пробрасывается выше."""
        coordinator.send_prompt.side_effect = Exception("send failed")

        with pytest.raises(Exception, match="send failed"):
            await chat_view_model.send_prompt_cmd.execute("s", "hi")

        assert chat_view_model.is_streaming.value is False


class TestSessionUpdate:
    """Тесты обработки session/update."""

    def test_tool_call_result_logs(self, chat_view_model: ChatViewModel) -> None:
        """tool_call_result логирует получение результата."""
        chat_view_model.set_active_session("s")
        chat_view_model._handle_session_update(
            {
                "params": {
                    "sessionId": "s",
                    "update": {
                        "sessionUpdate": "tool_call_result",
                        "toolCallId": "tc_1",
                        "result": {"data": 1},
                    },
                }
            }
        )
        # Метод не падает и не изменяет observable'ы.
        assert chat_view_model.tool_calls.value == []

    def test_tool_call_update_modifies_existing(self, chat_view_model: ChatViewModel) -> None:
        """tool_call_update обновляет существующий tool call."""
        chat_view_model.set_active_session("s")
        chat_view_model._handle_session_update(
            {
                "params": {
                    "sessionId": "s",
                    "update": {
                        "sessionUpdate": "tool_call",
                        "toolCallId": "tc_1",
                        "title": "Read",
                        "kind": "read",
                        "status": "running",
                    },
                }
            }
        )
        chat_view_model._handle_session_update(
            {
                "params": {
                    "sessionId": "s",
                    "update": {
                        "sessionUpdate": "tool_call_update",
                        "toolCallId": "tc_1",
                        "status": "completed",
                        "title": "Read file",
                    },
                }
            }
        )

        assert len(chat_view_model.tool_calls.value) == 1
        assert chat_view_model.tool_calls.value[0]["status"] == "completed"
        assert chat_view_model.tool_calls.value[0]["title"] == "Read file"

    def test_tool_call_update_missing_id_leaves_list_unchanged(
        self,
        chat_view_model: ChatViewModel,
    ) -> None:
        """tool_call_update для отсутствующего id не изменяет список."""
        chat_view_model.set_active_session("s")
        chat_view_model._handle_session_update(
            {
                "params": {
                    "sessionId": "s",
                    "update": {
                        "sessionUpdate": "tool_call_update",
                        "toolCallId": "missing",
                        "status": "completed",
                    },
                }
            }
        )
        assert chat_view_model.tool_calls.value == []

    def test_tool_call_update_keeps_other_calls(
        self,
        chat_view_model: ChatViewModel,
    ) -> None:
        """tool_call_update не изменяет tool calls с другими id."""
        chat_view_model.set_active_session("s")
        chat_view_model._handle_session_update(
            {
                "params": {
                    "sessionId": "s",
                    "update": {
                        "sessionUpdate": "tool_call",
                        "toolCallId": "tc_1",
                        "title": "Read",
                        "status": "running",
                    },
                }
            }
        )
        chat_view_model._handle_session_update(
            {
                "params": {
                    "sessionId": "s",
                    "update": {
                        "sessionUpdate": "tool_call",
                        "toolCallId": "tc_2",
                        "title": "Write",
                        "status": "running",
                    },
                }
            }
        )
        chat_view_model._handle_session_update(
            {
                "params": {
                    "sessionId": "s",
                    "update": {
                        "sessionUpdate": "tool_call_update",
                        "toolCallId": "tc_2",
                        "status": "completed",
                    },
                }
            }
        )

        assert len(chat_view_model.tool_calls.value) == 2
        statuses = {tc["toolCallId"]: tc["status"] for tc in chat_view_model.tool_calls.value}
        assert statuses["tc_1"] == "running"
        assert statuses["tc_2"] == "completed"

    def test_plan_update_with_plan_vm(
        self,
        session_update_dispatcher: SessionUpdateDispatcher,
    ) -> None:
        """plan update форматирует план и передает PlanViewModel."""
        plan_vm = MagicMock()
        vm = ChatViewModel(
            coordinator=MagicMock(),
            event_bus=EventBus(),
            logger=None,
            plan_vm=plan_vm,
            session_update_dispatcher=session_update_dispatcher,
        )
        vm.set_active_session("s")
        vm._handle_session_update(
            {
                "params": {
                    "sessionId": "s",
                    "update": {
                        "sessionUpdate": "plan",
                        "entries": [
                            {
                                "content": "step 1",
                                "priority": "high",
                                "status": "done",
                            }
                        ],
                    },
                }
            }
        )

        plan_vm.set_plan.assert_called_once()
        plan_text = plan_vm.set_plan.call_args[0][0]
        assert "План:" in plan_text
        assert "[done] (high) step 1" in plan_text

    def test_plan_update_without_plan_vm(
        self,
        chat_view_model: ChatViewModel,
    ) -> None:
        """plan update без PlanViewModel только логирует."""
        chat_view_model.set_active_session("s")
        chat_view_model._handle_session_update(
            {
                "params": {
                    "sessionId": "s",
                    "update": {
                        "sessionUpdate": "plan",
                        "entries": [{"content": "step"}],
                    },
                }
            }
        )
        assert chat_view_model.messages.value == []

    async def test_config_option_update_publishes_event(
        self,
        chat_view_model: ChatViewModel,
    ) -> None:
        """config_option_update публикует ConfigOptionUpdatedEvent."""
        events: list[ConfigOptionUpdatedEvent] = []
        chat_view_model.on_event(ConfigOptionUpdatedEvent, events.append)
        chat_view_model.set_active_session("s")

        chat_view_model._handle_session_update(
            {
                "params": {
                    "sessionId": "s",
                    "update": {
                        "sessionUpdate": "config_option_update",
                        "configOptions": [{"id": "model", "category": "model"}],
                    },
                }
            }
        )
        await asyncio.sleep(0)

        assert len(events) == 1
        assert events[0].session_id == "s"

    def test_session_update_with_invalid_data(
        self,
        chat_view_model: ChatViewModel,
    ) -> None:
        """_handle_session_update с невалидными данными не вызывает crash."""
        # Dispatcher обрабатывает исключения внутри себя
        chat_view_model._handle_session_update(
            {"params": {"sessionId": "s", "update": {}}}
        )


class TestCommands:
    """Тесты ObservableCommand оберток ChatViewModel."""

    async def test_cancel_prompt_empty_session_id(
        self,
        chat_view_model: ChatViewModel,
        coordinator: AsyncMock,
    ) -> None:
        """При пустом session_id отмена не отправляется."""
        await chat_view_model.cancel_prompt_cmd.execute("")
        coordinator.cancel_prompt.assert_not_called()

    async def test_cancel_prompt_success(
        self,
        chat_view_model: ChatViewModel,
        coordinator: AsyncMock,
    ) -> None:
        """Успешная отмена сбрасывает флаг streaming."""
        chat_view_model.set_active_session("s")
        chat_view_model.is_streaming.value = True
        coordinator.cancel_prompt.return_value = None

        await chat_view_model.cancel_prompt_cmd.execute("s")

        coordinator.cancel_prompt.assert_awaited_once_with("s")
        assert chat_view_model.is_streaming.value is False

    async def test_cancel_prompt_exception_reraises(
        self,
        chat_view_model: ChatViewModel,
        coordinator: AsyncMock,
    ) -> None:
        """Исключение при отмене пробрасывается выше."""
        coordinator.cancel_prompt.side_effect = Exception("cancel failed")

        with pytest.raises(Exception, match="cancel failed"):
            await chat_view_model.cancel_prompt_cmd.execute("s")

    async def test_approve_permission_success(
        self,
        chat_view_model: ChatViewModel,
        coordinator: AsyncMock,
    ) -> None:
        """Утверждение разрешения вызывает координатор и удаляет запрос."""
        chat_view_model.set_active_session("s")
        perm = PermissionRequest(
            request_id="p1",
            session_id="s",
            action="read",
            resource="/file",
        )
        chat_view_model.pending_permissions.value = [perm]
        coordinator.handle_permission.return_value = None

        await chat_view_model.approve_permission_cmd.execute("s", "p1")

        coordinator.handle_permission.assert_awaited_once_with(
            "s", "p1", approved=True
        )
        assert chat_view_model.pending_permissions.value == []

    async def test_approve_permission_exception_reraises(
        self,
        chat_view_model: ChatViewModel,
        coordinator: AsyncMock,
    ) -> None:
        """Исключение при утверждении пробрасывается, запрос не удаляется."""
        chat_view_model.set_active_session("s")
        perm = PermissionRequest(
            request_id="p1",
            session_id="s",
            action="read",
            resource="/file",
        )
        chat_view_model.pending_permissions.value = [perm]
        coordinator.handle_permission.side_effect = Exception("approve failed")

        with pytest.raises(Exception, match="approve failed"):
            await chat_view_model.approve_permission_cmd.execute("s", "p1")

        assert len(chat_view_model.pending_permissions.value) == 1

    async def test_reject_permission_success(
        self,
        chat_view_model: ChatViewModel,
        coordinator: AsyncMock,
    ) -> None:
        """Отклонение разрешения вызывает координатор и удаляет запрос."""
        chat_view_model.set_active_session("s")
        perm = PermissionRequest(
            request_id="p1",
            session_id="s",
            action="read",
            resource="/file",
        )
        chat_view_model.pending_permissions.value = [perm]
        coordinator.handle_permission.return_value = None

        await chat_view_model.reject_permission_cmd.execute("s", "p1")

        coordinator.handle_permission.assert_awaited_once_with(
            "s", "p1", approved=False
        )
        assert chat_view_model.pending_permissions.value == []

    async def test_clear_chat_resets_observables(
        self,
        chat_view_model: ChatViewModel,
    ) -> None:
        """Очистка чата сбрасывает все observable'ы и сохраняет состояние."""
        chat_view_model.set_active_session("s")
        chat_view_model.messages.value = [{"role": "user", "content": "hi"}]
        chat_view_model.tool_calls.value = [{"toolCallId": "t1"}]
        chat_view_model.pending_permissions.value = [
            PermissionRequest("p1", "s", "read", "/file")
        ]
        chat_view_model.streaming_text.value = "stream"
        chat_view_model.last_stop_reason.value = "end"

        await chat_view_model.clear_chat_cmd.execute()

        assert chat_view_model.messages.value == []
        assert chat_view_model.tool_calls.value == []
        assert chat_view_model.pending_permissions.value == []
        assert chat_view_model.streaming_text.value == ""
        assert chat_view_model.last_stop_reason.value is None


class TestHelpers:
    """Тесты вспомогательных методов."""

    def test_append_streaming_text(self, chat_view_model: ChatViewModel) -> None:
        """append_streaming_text добавляет текст к streaming_text."""
        chat_view_model.set_active_session("s")
        chat_view_model.append_streaming_text("hello")
        chat_view_model.append_streaming_text(" world")

        assert chat_view_model.streaming_text.value == "hello world"

    def test_remove_pending_permission(self, chat_view_model: ChatViewModel) -> None:
        """_remove_pending_permission удаляет запрос по id."""
        chat_view_model.set_active_session("s")
        perm1 = PermissionRequest("p1", "s", "read", "/a")
        perm2 = PermissionRequest("p2", "s", "write", "/b")
        chat_view_model.pending_permissions.value = [perm1, perm2]

        chat_view_model._remove_pending_permission("p1")

        assert chat_view_model.pending_permissions.value == [perm2]


class TestRestoreSession:
    """Тесты восстановления сессии из replay."""

    def test_restore_skips_wrong_session(self, chat_view_model: ChatViewModel) -> None:
        """Replay updates для другой сессии игнорируются."""
        chat_view_model.set_active_session("target")
        chat_view_model.restore_session_from_replay(
            "target",
            [
                {
                    "params": {
                        "sessionId": "other",
                        "update": {
                            "sessionUpdate": "user_message_chunk",
                            "content": {"text": "hello"},
                        },
                    }
                }
            ],
        )
        assert chat_view_model.messages.value == []

    def test_restore_skips_non_text_content(self, chat_view_model: ChatViewModel) -> None:
        """Replay updates без текстового контента игнорируются."""
        chat_view_model.set_active_session("s")
        chat_view_model.restore_session_from_replay(
            "s",
            [
                {
                    "params": {
                        "sessionId": "s",
                        "update": {
                            "sessionUpdate": "user_message_chunk",
                            "content": None,
                        },
                    }
                },
                {
                    "params": {
                        "sessionId": "s",
                        "update": {
                            "sessionUpdate": "user_message_chunk",
                            "content": {"text": ""},
                        },
                    }
                },
                {
                    "params": {
                        "sessionId": "s",
                        "update": {
                            "sessionUpdate": "user_message_chunk",
                            "content": {"text": 123},
                        },
                    }
                },
            ],
        )
        assert chat_view_model.messages.value == []

    def test_restore_skips_unknown_update_type(self, chat_view_model: ChatViewModel) -> None:
        """Replay updates неизвестного типа не попадают в messages."""
        chat_view_model.set_active_session("s")
        chat_view_model.restore_session_from_replay(
            "s",
            [
                {
                    "params": {
                        "sessionId": "s",
                        "update": {
                            "sessionUpdate": "unknown",
                            "content": {"text": "ignored"},
                        },
                    }
                }
            ],
        )
        assert chat_view_model.messages.value == []


class TestRebuildMessages:
    """Тесты восстановления сообщений из replay updates."""

    def test_rebuild_messages_skips_wrong_session(self, chat_view_model: ChatViewModel) -> None:
        """_rebuild_messages_from_replay игнорирует updates другой сессии."""
        result = chat_view_model._rebuild_messages_from_replay(
            "target",
            [
                {
                    "params": {
                        "sessionId": "other",
                        "update": {
                            "sessionUpdate": "user_message_chunk",
                            "content": {"text": "hello"},
                        },
                    }
                }
            ],
        )
        assert result == []

    def test_rebuild_messages_skips_non_dict_content(
        self,
        chat_view_model: ChatViewModel,
    ) -> None:
        """_rebuild_messages_from_replay игнорирует content не dict."""
        result = chat_view_model._rebuild_messages_from_replay(
            "s",
            [
                {
                    "params": {
                        "sessionId": "s",
                        "update": {
                            "sessionUpdate": "user_message_chunk",
                            "content": "not-dict",
                        },
                    }
                }
            ],
        )
        assert result == []

    def test_rebuild_messages_skips_empty_text(self, chat_view_model: ChatViewModel) -> None:
        """_rebuild_messages_from_replay игнорирует пустой или невалидный text."""
        result = chat_view_model._rebuild_messages_from_replay(
            "s",
            [
                {
                    "params": {
                        "sessionId": "s",
                        "update": {
                            "sessionUpdate": "user_message_chunk",
                            "content": {"text": ""},
                        },
                    }
                },
                {
                    "params": {
                        "sessionId": "s",
                        "update": {
                            "sessionUpdate": "user_message_chunk",
                            "content": {"text": None},
                        },
                    }
                },
            ],
        )
        assert result == []


class TestStreamingState:
    """Тесты управления streaming-состоянием."""

    def test_set_streaming_state_active_clears_text(
        self,
        chat_view_model: ChatViewModel,
    ) -> None:
        """Установка streaming для активной сессии очищает текст при clear_text."""
        chat_view_model.set_active_session("s")
        chat_view_model.streaming_text.value = "old"

        chat_view_model._set_streaming_state("s", is_streaming=True, clear_text=True)

        assert chat_view_model.streaming_text.value == ""
        assert chat_view_model.is_streaming.value is True

    def test_set_streaming_state_inactive_resets_global(
        self,
        chat_view_model: ChatViewModel,
    ) -> None:
        """Завершение streaming неактивной сессии сбрасывает глобальный флаг."""
        chat_view_model.set_active_session("active")
        chat_view_model.is_streaming.value = True
        chat_view_model._set_streaming_state("background", is_streaming=True, clear_text=False)

        chat_view_model._set_streaming_state("background", is_streaming=False, clear_text=True)

        assert chat_view_model.is_streaming.value is False

    def test_set_last_stop_reason_active(self, chat_view_model: ChatViewModel) -> None:
        """stop reason для активной сессии синхронизируется с UI."""
        chat_view_model.set_active_session("s")
        chat_view_model._set_last_stop_reason("s", "tool_use")

        assert chat_view_model.last_stop_reason.value == "tool_use"


class TestEventHandlers:
    """Тесты обработчиков доменных событий."""

    def test_handle_prompt_started(self, chat_view_model: ChatViewModel) -> None:
        """PromptStartedEvent включает streaming и очищает текст."""
        chat_view_model.set_active_session("s")
        chat_view_model.streaming_text.value = "old"
        event = PromptStartedEvent(
            aggregate_id="s",
            occurred_at=datetime.now(),
            session_id="s",
            prompt_text="hi",
        )

        chat_view_model._handle_prompt_started(event)

        assert chat_view_model.is_streaming.value is True
        assert chat_view_model.streaming_text.value == ""

    def test_handle_prompt_completed(self, chat_view_model: ChatViewModel) -> None:
        """PromptCompletedEvent сохраняет ответ и сбрасывает streaming."""
        chat_view_model.set_active_session("s")
        # Устанавливаем streaming_text через state
        state = chat_view_model._get_or_create_session_state("s")
        state.streaming_text = "response"
        state.is_streaming = True
        chat_view_model._session_states["s"] = state
        chat_view_model.streaming_text.value = "response"
        chat_view_model.is_streaming.value = True
        event = PromptCompletedEvent(
            aggregate_id="s",
            occurred_at=datetime.now(),
            session_id="s",
            stop_reason="end_turn",
        )

        chat_view_model._handle_prompt_completed(event)

        assert chat_view_model.messages.value == [
            {"role": "assistant", "content": "response"}
        ]
        assert chat_view_model.is_streaming.value is False
        assert chat_view_model.last_stop_reason.value == "end_turn"

    def test_handle_permission_requested(self, chat_view_model: ChatViewModel) -> None:
        """PermissionRequestedEvent добавляет запрос в pending."""
        event = MagicMock()
        event.request_id = "p1"
        event.session_id = "s"
        event.action = "read"
        event.resource = "/file"
        event.description = "read file"

        chat_view_model._handle_permission_requested(event)

        assert len(chat_view_model.pending_permissions.value) == 1
        perm = chat_view_model.pending_permissions.value[0]
        assert isinstance(perm, PermissionRequest)
        assert perm.request_id == "p1"

    async def test_handle_permission_requested_via_event_bus(
        self,
        chat_view_model: ChatViewModel,
    ) -> None:
        """PermissionRequestedEvent через шину добавляет запрос в pending."""
        event = PermissionRequestedEvent(
            aggregate_id="s",
            occurred_at=datetime.now(),
            session_id="s",
            action="read",
            resource="/file",
            permission_id="p2",
        )
        await chat_view_model.event_bus.publish(event)

        assert len(chat_view_model.pending_permissions.value) == 1
        assert chat_view_model.pending_permissions.value[0].request_id == "unknown"

    def test_handle_error_occurred_with_session_id(
        self,
        chat_view_model: ChatViewModel,
    ) -> None:
        """ErrorOccurredEvent с session_id сбрасывает streaming сессии."""
        chat_view_model.set_active_session("s")
        chat_view_model.is_streaming.value = True
        event = ErrorOccurredEvent(
            aggregate_id="s",
            occurred_at=datetime.now(),
            error_message="boom",
            error_type="TransportError",
            session_id="s",
        )

        chat_view_model._handle_error_occurred(event)

        assert chat_view_model.is_streaming.value is False

    def test_handle_error_occurred_without_session_id(
        self,
        chat_view_model: ChatViewModel,
    ) -> None:
        """ErrorOccurredEvent без session_id сбрасывает глобальный флаг."""
        chat_view_model.set_active_session("s")
        chat_view_model.is_streaming.value = True
        event = ErrorOccurredEvent(
            aggregate_id="global",
            occurred_at=datetime.now(),
            error_message="boom",
            error_type="TransportError",
        )

        chat_view_model._handle_error_occurred(event)

        assert chat_view_model.is_streaming.value is False
