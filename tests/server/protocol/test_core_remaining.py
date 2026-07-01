"""Дополнительные тесты для оставшихся веток декомпозированного ACPProtocol.

После декомпозиции God Object'а ACPProtocol логика вынесена в компоненты:
- BackgroundExecutor — фоновое выполнение tools, завершение turns.
- ResponseRouter — маршрутизация client responses / permission responses.
- Command handlers (session_prompt / session_cancel / permission_response).
- MCPSessionManager — инициализация MCP серверов и восстановление prompts.

Тесты сохраняют исходный behavioral intent, но нацелены на новые компоненты
напрямую (или через сохранённые публичные фасадные методы ACPProtocol).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from _protocol_factory import build_protocol
from codelab.server.mcp import MCPManager
from codelab.server.messages import ACPMessage
from codelab.server.protocol.background_executor import BackgroundExecutor
from codelab.server.protocol.commands.permission_response import (
    PermissionResponseCommandHandler,
)
from codelab.server.protocol.commands.session_cancel import SessionCancelCommandHandler
from codelab.server.protocol.commands.session_prompt import SessionPromptCommandHandler
from codelab.server.protocol.mcp_session_manager import MCPSessionManager
from codelab.server.protocol.response_router import ResponseRouter
from codelab.server.protocol.session_factory import SessionFactory
from codelab.server.protocol.session_runtime import SessionRuntimeRegistry
from codelab.server.protocol.state import (
    ActiveTurnState,
    LLMLoopResult,
    PendingToolExecution,
    ProtocolOutcome,
    SessionState,
    ToolCallState,
)
from codelab.server.storage import InMemoryStorage


def _make_background_executor(
    storage: InMemoryStorage,
    *,
    orchestrator: Any | None = None,
    mcp_manager: Any | None = None,
    runtime_registry: SessionRuntimeRegistry | None = None,
) -> BackgroundExecutor:
    """Создаёт BackgroundExecutor с провайдерами-заглушками."""

    async def orchestrator_provider() -> Any:
        return orchestrator

    async def mcp_provider(_session: SessionState) -> Any:
        return mcp_manager

    return BackgroundExecutor(
        storage=storage,
        orchestrator_provider=orchestrator_provider,
        mcp_provider=mcp_provider,
        runtime_registry=runtime_registry or SessionRuntimeRegistry(),
    )


def _make_response_router(
    storage: InMemoryStorage,
    *,
    client_rpc_service: Any | None = None,
) -> ResponseRouter:
    """Создаёт ResponseRouter."""
    from codelab.server.protocol.pending_registry import PendingRequestRegistry

    return ResponseRouter(
        storage=storage,
        pending_registry=PendingRequestRegistry(),
        client_rpc_service=client_rpc_service,
    )


class TestHandleAndProcess:
    """Тесты для handle_and_process и планирования фоновой задачи (фасад)."""

    async def test_schedules_background_task_when_pending_tool_exists(self) -> None:
        """При pending_tool_execution запускается фоновая задача."""
        protocol = build_protocol()
        pending = PendingToolExecution(session_id="sess_1", tool_call_id="call_1")
        outcome = ProtocolOutcome(pending_tool_execution=pending)

        with patch.object(protocol, "handle", return_value=outcome):
            with patch("asyncio.create_task") as mock_create_task:
                result = await protocol.handle_and_process(
                    ACPMessage.request("session/prompt", {})
                )

        assert result is outcome
        mock_create_task.assert_called_once()

    async def test_returns_outcome_without_background_task(self) -> None:
        """Без pending_tool_execution просто возвращается outcome."""
        protocol = build_protocol()
        outcome = ProtocolOutcome()

        with patch.object(protocol, "handle", return_value=outcome):
            result = await protocol.handle_and_process(
                ACPMessage.request("session/prompt", {})
            )

        assert result is outcome


class TestExecuteToolInBackground:
    """Тесты для BackgroundExecutor.execute_tool_in_background."""

    async def test_sends_notifications_and_turn_completion(self) -> None:
        """Успешный фоновый запуск отправляет turn completion.

        Notifications доставляются через immediate delivery callback в AgentLoop,
        поэтому _send_message вызывается только для completion.
        """
        executor = _make_background_executor(InMemoryStorage())
        notification = ACPMessage.notification("session/update", {})
        completion = ACPMessage.response("req_1", {"stopReason": "end_turn"})
        llm_result = LLMLoopResult(
            notifications=[notification],
            stop_reason="end_turn",
        )

        with patch.object(executor, "execute_pending_tool", return_value=llm_result):
            with patch.object(executor, "complete_active_turn", return_value=completion):
                with patch.object(executor, "_send_message", new=AsyncMock()) as send:
                    await executor.execute_tool_in_background(
                        session_id="sess_1",
                        tool_call_id="call_1",
                    )

        assert send.await_count == 1
        send.assert_any_await(completion, "sess_1")

    async def test_returns_early_when_pending_permission(self) -> None:
        """Если снова ожидается permission, turn не завершается (только notif)."""
        executor = _make_background_executor(InMemoryStorage())
        llm_result = LLMLoopResult(pending_permission=True)

        with patch.object(executor, "execute_pending_tool", return_value=llm_result):
            with patch.object(executor, "complete_active_turn", new=AsyncMock()) as complete:
                with patch.object(executor, "_send_message", new=AsyncMock()):
                    await executor.execute_tool_in_background(
                        session_id="sess_1",
                        tool_call_id="call_1",
                    )

        complete.assert_not_awaited()

    async def test_logs_error_on_exception(self) -> None:
        """Исключение в фоновой задаче логируется."""
        executor = _make_background_executor(InMemoryStorage())

        with patch.object(
            executor,
            "execute_pending_tool",
            side_effect=RuntimeError("boom"),
        ):
            with patch(
                "codelab.server.protocol.background_executor.logger"
            ) as mock_logger:
                await executor.execute_tool_in_background(
                    session_id="sess_1",
                    tool_call_id="call_1",
                )

        mock_logger.error.assert_called_once()


class TestCompleteActiveTurn:
    """Тесты для BackgroundExecutor.complete_active_turn."""

    async def test_returns_none_when_session_missing(self) -> None:
        """Возвращает None, если сессия не найдена."""
        executor = _make_background_executor(InMemoryStorage())

        result = await executor.complete_active_turn("missing")

        assert result is None

    async def test_returns_prompt_completion(self) -> None:
        """Возвращает результат prompt.complete_active_turn."""
        storage = InMemoryStorage()
        session = SessionFactory.create_session(cwd="/tmp")
        await storage.save_session(session)
        completion = ACPMessage.response("req_1", {"stopReason": "end_turn"})
        executor = _make_background_executor(storage)

        with patch(
            "codelab.server.protocol.background_executor.prompt.complete_active_turn",
            return_value=completion,
        ):
            result = await executor.complete_active_turn(session.session_id)

        assert result is completion


class TestShouldAutoCompleteActiveTurn:
    """Тесты для BackgroundExecutor.should_auto_complete_active_turn."""

    async def test_returns_false_when_session_missing(self) -> None:
        """False, если сессия не найдена."""
        executor = _make_background_executor(InMemoryStorage())

        result = await executor.should_auto_complete_active_turn("missing")

        assert result is False

    async def test_returns_false_when_active_turn_missing(self) -> None:
        """False, если active_turn отсутствует."""
        storage = InMemoryStorage()
        session = SessionFactory.create_session(cwd="/tmp")
        await storage.save_session(session)
        executor = _make_background_executor(storage)

        result = await executor.should_auto_complete_active_turn(session.session_id)

        assert result is False

    async def test_returns_prompt_decision(self) -> None:
        """Пробрасывает результат prompt.should_auto_complete_active_turn."""
        storage = InMemoryStorage()
        session = SessionFactory.create_session(cwd="/tmp")
        session.active_turn = ActiveTurnState(
            prompt_request_id="req_1",
            session_id=session.session_id,
        )
        await storage.save_session(session)
        executor = _make_background_executor(storage)

        with patch(
            "codelab.server.protocol.background_executor.prompt.should_auto_complete_active_turn",
            return_value=True,
        ):
            result = await executor.should_auto_complete_active_turn(session.session_id)

        assert result is True


class TestHandleClientResponse:
    """Тесты для ResponseRouter.handle_client_response."""

    async def test_ignores_message_without_id(self) -> None:
        """Сообщение без id игнорируется пустым outcome."""
        router = _make_response_router(InMemoryStorage())
        message = ACPMessage.response(None, {"ok": True})

        with patch("codelab.server.protocol.response_router.logger") as mock_logger:
            result = await router.handle_client_response(message)

        assert result == ProtocolOutcome()
        mock_logger.debug.assert_called_once()

    async def test_resolves_pending_client_rpc(self) -> None:
        """Response распознаётся как ожидаемый client RPC."""
        router = _make_response_router(InMemoryStorage())
        expected = ProtocolOutcome(response=ACPMessage.response("rpc_1", {"ok": True}))

        with patch.object(
            router,
            "_resolve_pending_client_rpc_response",
            return_value=expected,
        ):
            result = await router.handle_client_response(
                ACPMessage.response("rpc_1", {"content": "ok"})
            )

        assert result is expected

    async def test_forwards_to_client_rpc_service(self) -> None:
        """Response передаётся в ClientRPCService."""
        service = MagicMock()
        service.has_pending_request.return_value = True
        router = _make_response_router(InMemoryStorage(), client_rpc_service=service)
        message = ACPMessage.response("rpc_1", {"content": "ok"})

        result = await router.handle_client_response(message)

        assert result == ProtocolOutcome()
        service.handle_response.assert_called_once_with(message.to_dict())

    async def test_consumes_cancelled_client_rpc(self) -> None:
        """Поглощается late response на отменённый client RPC."""
        storage = InMemoryStorage()
        session = SessionFactory.create_session(cwd="/tmp")
        session.cancelled_client_rpc_requests.add("rpc_1")
        await storage.save_session(session)
        router = _make_response_router(storage)

        result = await router.handle_client_response(
            ACPMessage.response("rpc_1", {"content": "ok"})
        )

        assert result == ProtocolOutcome()
        assert "rpc_1" not in session.cancelled_client_rpc_requests

    async def test_consumes_cancelled_permission_response(self) -> None:
        """Поглощается late response на отменённый permission request."""
        storage = InMemoryStorage()
        session = SessionFactory.create_session(cwd="/tmp")
        session.cancelled_permission_requests.add("perm_1")
        await storage.save_session(session)
        router = _make_response_router(storage)

        result = await router.handle_client_response(
            ACPMessage.response("perm_1", {"outcome": "selected"})
        )

        assert result == ProtocolOutcome()
        assert "perm_1" not in session.cancelled_permission_requests

    async def test_returns_empty_when_permission_resolution_none(self) -> None:
        """Если _resolve_permission_response вернул None — пустой outcome."""
        router = _make_response_router(InMemoryStorage())

        with patch.object(
            router,
            "_resolve_permission_response",
            return_value=None,
        ):
            result = await router.handle_client_response(
                ACPMessage.response("perm_1", {"outcome": {"outcome": "selected"}})
            )

        assert result == ProtocolOutcome()

    async def test_returns_resolved_permission_response(self) -> None:
        """Успешное разрешение permission пробрасывается наружу."""
        router = _make_response_router(InMemoryStorage())
        expected = ProtocolOutcome(response=ACPMessage.response("perm_1", {}))

        with patch.object(
            router,
            "_resolve_permission_response",
            return_value=expected,
        ):
            result = await router.handle_client_response(
                ACPMessage.response("perm_1", {"outcome": {"outcome": "selected"}})
            )

        assert result is expected


class TestResolvePermissionResponse:
    """Тесты для ResponseRouter._resolve_permission_response."""

    async def test_returns_none_when_session_not_found(self) -> None:
        """None, если сессия по permission_request_id не найдена."""
        router = _make_response_router(InMemoryStorage())

        result = await router._resolve_permission_response("perm_1", {})

        assert result is None

    async def test_returns_prompt_resolution(self) -> None:
        """Пробрасывает результат prompt.resolve_permission_response_impl."""
        storage = InMemoryStorage()
        session = SessionFactory.create_session(cwd="/tmp")
        session.active_turn = ActiveTurnState(
            prompt_request_id="req_1",
            session_id=session.session_id,
            permission_request_id="perm_1",
        )
        await storage.save_session(session)
        router = _make_response_router(storage)
        expected = ProtocolOutcome(response=ACPMessage.response("perm_1", {}))

        with patch(
            "codelab.server.protocol.response_router.prompt.resolve_permission_response_impl",
            return_value=expected,
        ):
            result = await router._resolve_permission_response("perm_1", {})

        assert result is expected


class TestCancelActiveTurnsOnDisconnect:
    """Тесты для ACPProtocol.cancel_active_turns_on_disconnect (фасад)."""

    async def test_continues_on_save_exception(self) -> None:
        """Ошибка save_session не прерывает цикл отмены."""
        storage = InMemoryStorage()
        session_ok = SessionFactory.create_session(cwd="/tmp")
        session_ok.active_turn = ActiveTurnState(
            prompt_request_id="req_1",
            session_id=session_ok.session_id,
        )
        session_bad = SessionFactory.create_session(cwd="/tmp")
        session_bad.active_turn = ActiveTurnState(
            prompt_request_id="req_2",
            session_id=session_bad.session_id,
        )
        await storage.save_session(session_ok)
        await storage.save_session(session_bad)

        original_save = storage.save_session

        async def flaky_save(session: SessionState) -> None:
            if session.session_id == session_bad.session_id:
                raise RuntimeError("save failed")
            await original_save(session)

        storage.save_session = flaky_save  # type: ignore

        orchestrator = MagicMock()
        protocol = build_protocol(
            storage=storage,
            prompt_orchestrator=orchestrator,
        )

        count = await protocol.cancel_active_turns_on_disconnect()

        assert count == 2
        orchestrator.handle_cancel.assert_called()

    async def test_returns_cancelled_count(self) -> None:
        """Возвращает количество отменённых сессий."""
        storage = InMemoryStorage()
        session = SessionFactory.create_session(cwd="/tmp")
        session.active_turn = ActiveTurnState(
            prompt_request_id="req_1",
            session_id=session.session_id,
        )
        await storage.save_session(session)
        orchestrator = MagicMock()
        protocol = build_protocol(
            storage=storage,
            prompt_orchestrator=orchestrator,
        )

        count = await protocol.cancel_active_turns_on_disconnect()

        assert count == 1


def _make_prompt_handler(
    storage: InMemoryStorage,
    *,
    orchestrator: Any | None = None,
    runtime_registry: SessionRuntimeRegistry | None = None,
) -> SessionPromptCommandHandler:
    """Создаёт SessionPromptCommandHandler."""

    async def orchestrator_provider() -> Any:
        return orchestrator

    async def mcp_provider(_session: Any) -> Any:
        return None

    return SessionPromptCommandHandler(
        storage=storage,
        orchestrator_provider=orchestrator_provider,
        runtime_registry=runtime_registry or SessionRuntimeRegistry(),
        mcp_provider=mcp_provider,
        notification_callback=AsyncMock(),
    )


class TestHandleSessionPrompt:
    """Тесты для SessionPromptCommandHandler.handle."""

    async def test_returns_error_when_session_id_invalid(self) -> None:
        """Ошибка, если sessionId не строка."""
        handler = _make_prompt_handler(InMemoryStorage(), orchestrator=AsyncMock())
        message = ACPMessage.request(
            "session/prompt",
            {"sessionId": 123},
            request_id="req_1",
        )

        outcome = await handler.handle(message)

        assert outcome.response is not None
        assert outcome.response.error is not None
        assert outcome.response.error.code == -32602

    async def test_returns_error_when_session_not_found(self) -> None:
        """Ошибка, если сессия не найдена."""
        handler = _make_prompt_handler(InMemoryStorage(), orchestrator=AsyncMock())
        message = ACPMessage.request(
            "session/prompt",
            {"sessionId": "missing"},
            request_id="req_1",
        )

        outcome = await handler.handle(message)

        assert outcome.response is not None
        assert outcome.response.error is not None
        assert outcome.response.error.code == -32001

    async def test_logs_error_on_save_exception(self) -> None:
        """Исключение save_session логируется, но не ломает обработку."""
        storage = InMemoryStorage()
        session = SessionFactory.create_session(cwd="/tmp")
        await storage.save_session(session)
        orchestrator = AsyncMock()
        orchestrator.handle_prompt.return_value = ProtocolOutcome()
        handler = _make_prompt_handler(storage, orchestrator=orchestrator)

        with patch.object(
            storage,
            "save_session",
            side_effect=RuntimeError("save failed"),
        ):
            with patch(
                "codelab.server.protocol.commands.session_prompt.logger"
            ) as mock_logger:
                message = ACPMessage.request(
                    "session/prompt",
                    {
                        "sessionId": session.session_id,
                        "prompt": [{"type": "text", "text": "hi"}],
                    },
                    request_id="req_1",
                )
                outcome = await handler.handle(message)

        mock_logger.error.assert_called_once()
        assert outcome == ProtocolOutcome()


def _make_cancel_handler(
    storage: InMemoryStorage,
    *,
    orchestrator: Any | None = None,
    llm_adapter: Any | None = None,
) -> SessionCancelCommandHandler:
    """Создаёт SessionCancelCommandHandler."""

    async def orchestrator_provider() -> Any:
        return orchestrator

    return SessionCancelCommandHandler(
        storage=storage,
        orchestrator_provider=orchestrator_provider,
        llm_adapter=llm_adapter,
    )


class TestHandleSessionCancel:
    """Тесты для SessionCancelCommandHandler.handle."""

    async def test_returns_empty_when_session_id_missing(self) -> None:
        """Пустой outcome, если sessionId отсутствует."""
        handler = _make_cancel_handler(InMemoryStorage(), orchestrator=MagicMock())
        message = ACPMessage.request("session/cancel", {}, request_id="req_1")

        outcome = await handler.handle(message)

        assert outcome == ProtocolOutcome(response=None, notifications=[])

    async def test_returns_response_when_session_not_found(self) -> None:
        """Возвращает response, если сессия не найдена."""
        handler = _make_cancel_handler(InMemoryStorage(), orchestrator=MagicMock())
        message = ACPMessage.request(
            "session/cancel",
            {"sessionId": "missing"},
            request_id="req_1",
        )

        outcome = await handler.handle(message)

        assert outcome.response is not None
        assert outcome.response.result is None

    async def test_cancels_llm_adapter(self) -> None:
        """Вызывается llm_adapter.cancel_prompt при наличии адаптера."""
        storage = InMemoryStorage()
        session = SessionFactory.create_session(cwd="/tmp")
        await storage.save_session(session)
        llm_adapter = AsyncMock()
        orchestrator = MagicMock()
        orchestrator.handle_cancel.return_value = ProtocolOutcome()
        handler = _make_cancel_handler(
            storage,
            orchestrator=orchestrator,
            llm_adapter=llm_adapter,
        )

        message = ACPMessage.request(
            "session/cancel",
            {"sessionId": session.session_id},
            request_id="req_1",
        )
        await handler.handle(message)

        llm_adapter.cancel_prompt.assert_awaited_once_with(session.session_id)

    async def test_includes_followup_response(self) -> None:
        """Pending prompt response добавляется в followup_responses."""
        storage = InMemoryStorage()
        session = SessionFactory.create_session(cwd="/tmp")
        session.pending_prompt_response = {
            "request_id": "prompt_req",
            "stop_reason": "cancelled",
        }
        await storage.save_session(session)
        orchestrator = MagicMock()
        orchestrator.handle_cancel.return_value = ProtocolOutcome()
        handler = _make_cancel_handler(storage, orchestrator=orchestrator)

        message = ACPMessage.request(
            "session/cancel",
            {"sessionId": session.session_id},
            request_id="req_1",
        )
        outcome = await handler.handle(message)

        assert len(outcome.followup_responses) == 1
        assert outcome.followup_responses[0].id == "prompt_req"


class TestHandlePermissionResponseMethod:
    """Тесты для PermissionResponseCommandHandler.handle."""

    async def test_returns_error_when_id_is_none(self) -> None:
        """Notification без id отклоняется ошибкой."""
        handler = PermissionResponseCommandHandler(storage=InMemoryStorage())
        message = ACPMessage.notification(
            "session/request_permission_response",
            {"sessionId": "sess_1"},
        )

        outcome = await handler.handle(message)

        assert outcome.response is not None
        assert outcome.response.error is not None
        assert outcome.response.error.code == -32600

    async def test_delegates_to_handle_permission_response(self) -> None:
        """Request с id делегируется _handle_permission_response."""
        handler = PermissionResponseCommandHandler(storage=InMemoryStorage())
        expected = ProtocolOutcome(response=ACPMessage.response("perm_1", {}))

        with patch.object(
            handler,
            "_handle_permission_response",
            return_value=expected,
        ):
            message = ACPMessage.request(
                "session/request_permission_response",
                {"sessionId": "sess_1"},
                request_id="perm_1",
            )
            outcome = await handler.handle(message)

        assert outcome is expected


class TestRestoreMcpPrompts:
    """Тесты для MCPSessionManager._restore_mcp_prompts."""

    async def test_warns_when_runtime_not_found(self) -> None:
        """Предупреждение, если runtime state отсутствует."""
        session = SessionFactory.create_session(cwd="/tmp")
        mcp_manager = MagicMock(spec=MCPManager)
        manager = MCPSessionManager(runtime_registry=SessionRuntimeRegistry())

        with patch("codelab.server.protocol.mcp_session_manager.logger") as mock_logger:
            await manager._restore_mcp_prompts(session, mcp_manager)

        mock_logger.warning.assert_called_once()

    async def test_returns_when_get_all_prompts_fails(self) -> None:
        """При ошибке get_all_prompts метод возвращается без исключения."""
        session = SessionFactory.create_session(cwd="/tmp")
        registry = SessionRuntimeRegistry()
        await registry.set_mcp_manager(session.session_id, MagicMock(spec=MCPManager))
        mcp_manager = AsyncMock()
        mcp_manager.get_all_prompts.side_effect = RuntimeError("prompts failed")
        manager = MCPSessionManager(runtime_registry=registry)

        with patch("codelab.server.protocol.mcp_session_manager.logger") as mock_logger:
            await manager._restore_mcp_prompts(session, mcp_manager)

        mock_logger.warning.assert_called_once()

    async def test_skips_server_without_prompts(self) -> None:
        """Сервер без prompts пропускается."""
        session = SessionFactory.create_session(
            cwd="/tmp",
            mcp_servers=[{"name": "srv"}],
        )
        registry = SessionRuntimeRegistry()
        await registry.set_mcp_manager(session.session_id, MagicMock(spec=MCPManager))
        mcp_manager = AsyncMock()
        mcp_manager.get_all_prompts.return_value = {"srv": []}
        manager = MCPSessionManager(runtime_registry=registry)

        with patch.object(manager, "_register_mcp_prompts_from_list") as register:
            await manager._restore_mcp_prompts(session, mcp_manager)

        register.assert_not_called()


class TestSendAvailableCommandsUpdate:
    """Тесты для MCPSessionManager.send_available_commands_update."""

    async def test_appends_non_dict_command_without_model_dump(self) -> None:
        """Команда без model_dump и не dict добавляется как есть."""
        session = SessionFactory.create_session(cwd="/tmp")
        session.available_commands = ["raw_command"]  # type: ignore
        mcp_manager = MagicMock()
        mcp_manager.get_all_tools.return_value = []
        registry = SessionRuntimeRegistry()
        tool_registry = MagicMock()
        manager = MCPSessionManager(
            runtime_registry=registry,
            tool_registry=tool_registry,
        )

        with patch.object(manager, "_send_message", new=AsyncMock()):
            await manager.send_available_commands_update(session, mcp_manager)

        mcp_manager.get_all_tools.assert_called_once()


class TestSetupMcpIfNeeded:
    """Тесты для MCPSessionManager.setup_if_needed."""

    async def test_returns_when_already_initialized(self) -> None:
        """Если MCP manager уже есть в runtime — инициализация пропускается."""
        session = SessionFactory.create_session(
            cwd="/tmp",
            mcp_servers=[{"name": "srv", "command": "cmd"}],
        )
        registry = SessionRuntimeRegistry()
        await registry.set_mcp_manager(session.session_id, MagicMock(spec=MCPManager))
        manager = MCPSessionManager(runtime_registry=registry)

        with patch.object(manager, "_initialize_mcp_servers") as init:
            await manager.setup_if_needed(
                session,
                {"mcpServers": [{"name": "srv", "command": "cmd"}]},
            )

        init.assert_not_called()


class TestHandlePermissionResponse:
    """Тесты для PermissionResponseCommandHandler._handle_permission_response."""

    async def test_returns_error_for_unknown_request(self) -> None:
        """Ошибка для неизвестного permission request."""
        handler = PermissionResponseCommandHandler(storage=InMemoryStorage())

        outcome = await handler._handle_permission_response(
            "perm_unknown",
            {"sessionId": "sess_1"},
        )

        assert outcome.response is not None
        assert outcome.response.error is not None
        assert outcome.response.error.code == -32603

    async def test_handles_cancelled_late_response(self) -> None:
        """Late response на отменённый request возвращает пустой response."""
        storage = InMemoryStorage()
        session = SessionFactory.create_session(cwd="/tmp")
        session.cancelled_permission_requests.add("perm_1")
        await storage.save_session(session)
        handler = PermissionResponseCommandHandler(storage=storage)

        outcome = await handler._handle_permission_response(
            "perm_1",
            {"sessionId": session.session_id},
        )

        assert outcome.response is not None
        assert outcome.response.result == {}
        assert "perm_1" not in session.cancelled_permission_requests

    async def test_returns_error_for_invalid_format(self) -> None:
        """Ошибка, если response не содержит outcome/optionId."""
        storage = InMemoryStorage()
        session = SessionFactory.create_session(cwd="/tmp")
        session.active_turn = ActiveTurnState(
            prompt_request_id="req_1",
            session_id=session.session_id,
            permission_request_id="perm_1",
            permission_tool_call_id="call_1",
        )
        await storage.save_session(session)
        handler = PermissionResponseCommandHandler(storage=storage)

        outcome = await handler._handle_permission_response(
            "perm_1",
            {"sessionId": session.session_id, "result": {}},
        )

        assert outcome.response is not None
        assert outcome.response.error is not None
        assert outcome.response.error.code == -32603

    async def test_returns_error_when_no_pending_tool_call(self) -> None:
        """Ошибка, если active_turn не содержит permission_tool_call_id."""
        storage = InMemoryStorage()
        session = SessionFactory.create_session(cwd="/tmp")
        session.active_turn = ActiveTurnState(
            prompt_request_id="req_1",
            session_id=session.session_id,
            permission_request_id="perm_1",
        )
        await storage.save_session(session)
        handler = PermissionResponseCommandHandler(storage=storage)

        outcome = await handler._handle_permission_response(
            "perm_1",
            {
                "sessionId": session.session_id,
                "result": {"outcome": {"outcome": "selected", "optionId": "allow_once"}},
            },
        )

        assert outcome.response is not None
        assert outcome.response.error is not None
        assert outcome.response.error.message == "No pending tool call"

    async def test_returns_success_response(self) -> None:
        """Успешный permission response возвращает response и notifications."""
        storage = InMemoryStorage()
        session = SessionFactory.create_session(cwd="/tmp")
        session.active_turn = ActiveTurnState(
            prompt_request_id="req_1",
            session_id=session.session_id,
            permission_request_id="perm_1",
            permission_tool_call_id="call_1",
        )
        session.tool_calls["call_1"] = ToolCallState(
            tool_call_id="call_1",
            title="Run",
            kind="execute",
            status="pending",
        )
        await storage.save_session(session)
        handler = PermissionResponseCommandHandler(storage=storage)

        outcome = await handler._handle_permission_response(
            "perm_1",
            {
                "sessionId": session.session_id,
                "result": {"outcome": {"outcome": "selected", "optionId": "allow_once"}},
            },
        )

        assert outcome.response is not None
        assert outcome.response.result == {}


class TestExecutePendingTool:
    """Тесты для BackgroundExecutor.execute_pending_tool."""

    async def test_returns_empty_when_session_missing(self) -> None:
        """Пустой LLMLoopResult, если сессия не найдена."""
        executor = _make_background_executor(InMemoryStorage())

        result = await executor.execute_pending_tool("missing", "call_1")

        assert result == LLMLoopResult(notifications=[], stop_reason="end_turn")

    async def test_returns_empty_when_orchestrator_none(self) -> None:
        """Пустой LLMLoopResult, если orchestrator не настроен."""
        storage = InMemoryStorage()
        session = SessionFactory.create_session(cwd="/tmp")
        await storage.save_session(session)
        executor = _make_background_executor(storage, orchestrator=None)

        result = await executor.execute_pending_tool(session.session_id, "call_1")

        assert result == LLMLoopResult(notifications=[], stop_reason="end_turn")

    async def test_logs_error_on_save_exception(self) -> None:
        """Исключение save_session логируется."""
        storage = InMemoryStorage()
        session = SessionFactory.create_session(cwd="/tmp")
        await storage.save_session(session)
        orchestrator = AsyncMock()
        orchestrator.execute_pending_tool.return_value = LLMLoopResult()
        executor = _make_background_executor(storage, orchestrator=orchestrator)

        with patch.object(
            storage,
            "save_session",
            side_effect=RuntimeError("save failed"),
        ):
            with patch(
                "codelab.server.protocol.background_executor.logger"
            ) as mock_logger:
                result = await executor.execute_pending_tool(
                    session.session_id,
                    "call_1",
                )

        mock_logger.error.assert_called_once()
        assert result == LLMLoopResult()

    async def test_returns_llm_result(self) -> None:
        """Возвращает результат orchestrator.execute_pending_tool."""
        storage = InMemoryStorage()
        session = SessionFactory.create_session(cwd="/tmp")
        await storage.save_session(session)
        expected = LLMLoopResult(
            notifications=[ACPMessage.notification("session/update", {})]
        )
        orchestrator = AsyncMock()
        orchestrator.execute_pending_tool.return_value = expected
        executor = _make_background_executor(storage, orchestrator=orchestrator)

        result = await executor.execute_pending_tool(session.session_id, "call_1")

        assert result is expected


async def _init_with_mock_manager(
    session: SessionState,
    mcp_servers: list[dict[str, Any]],
) -> tuple[MCPSessionManager, MagicMock, SessionRuntimeRegistry]:
    """Инициализирует MCP с замоканным менеджером, возвращает manager/mcp/registry."""
    registry = SessionRuntimeRegistry()
    mcp_manager = MagicMock(spec=MCPManager)
    mcp_manager.add_server = AsyncMock(return_value=[])
    mcp_manager.get_all_prompts = AsyncMock(return_value={})
    await registry.set_mcp_manager(session.session_id, mcp_manager)
    manager = MCPSessionManager(
        runtime_registry=registry,
        tool_registry=MagicMock(),
    )

    with patch(
        "codelab.server.protocol.mcp_session_manager.MCPManager",
        return_value=mcp_manager,
    ):
        with patch.object(manager, "_send_message", new=AsyncMock()):
            await manager._initialize_mcp_servers(session, mcp_servers)

    return manager, mcp_manager, registry


class TestInitializeMcpServersCallbacks:
    """Тесты для callback'ов инициализации MCP серверов (MCPSessionManager)."""

    async def test_server_status_callback_sends_notifications(self) -> None:
        """Callback статуса сервера отправляет notifications."""
        session = SessionFactory.create_session(cwd="/tmp")
        manager, mcp_manager, _registry = await _init_with_mock_manager(
            session,
            [{"name": "srv", "command": "cmd"}],
        )

        callbacks = mcp_manager.register_server_status_callback.call_args_list
        assert len(callbacks) == 1
        status_callback = callbacks[0][0][0]
        mcp_manager.get_servers_info.return_value = [
            {"name": "srv", "state": "connected"},
        ]

        with patch.object(manager, "_send_message", new=AsyncMock()) as send:
            await status_callback()

        send.assert_awaited_once()

    async def test_server_status_callback_logs_error_on_exception(self) -> None:
        """Callback статуса сервера логирует ошибку при исключении."""
        session = SessionFactory.create_session(cwd="/tmp")
        manager, mcp_manager, _registry = await _init_with_mock_manager(
            session,
            [{"name": "srv", "command": "cmd"}],
        )

        callbacks = mcp_manager.register_server_status_callback.call_args_list
        status_callback = callbacks[0][0][0]
        mcp_manager.get_servers_info.side_effect = RuntimeError("info failed")

        with patch(
            "codelab.server.protocol.mcp_session_manager.logger"
        ) as mock_logger:
            with patch.object(manager, "_send_message", new=AsyncMock()) as send:
                await status_callback()

        mock_logger.error.assert_called_once()
        send.assert_not_awaited()

    async def test_prompts_changed_runtime_not_found(self) -> None:
        """Callback prompts_change логирует предупреждение при отсутствии runtime."""
        session = SessionFactory.create_session(cwd="/tmp")
        manager, mcp_manager, registry = await _init_with_mock_manager(
            session,
            [{"name": "srv", "command": "cmd"}],
        )

        callbacks = mcp_manager.register_prompt_change_callback.call_args_list
        prompts_callback = callbacks[0][0][0]

        # Удаляем runtime, чтобы callback не нашёл состояние
        await registry.remove(session.session_id)

        with patch(
            "codelab.server.protocol.mcp_session_manager.logger"
        ) as mock_logger:
            await prompts_callback()

        mock_logger.warning.assert_called_once()

    async def test_prompts_changed_skips_invalid_config(self) -> None:
        """Callback prompts_change пропускает невалидные конфиги серверов."""
        session = SessionFactory.create_session(
            cwd="/tmp",
            mcp_servers=[{"name": "srv", "command": "cmd"}],
        )
        manager, mcp_manager, _registry = await _init_with_mock_manager(
            session,
            [{"name": "srv", "command": "cmd"}],
        )

        callbacks = mcp_manager.register_prompt_change_callback.call_args_list
        prompts_callback = callbacks[0][0][0]
        session.mcp_servers = ["not_a_dict", {"name": "srv", "command": "cmd"}]  # type: ignore
        session.available_commands = [{"name": "status"}]
        mcp_manager.get_all_prompts.reset_mock()
        mcp_manager.get_all_prompts.return_value = {"srv": []}

        with patch.object(manager, "_send_message", new=AsyncMock()):
            await prompts_callback()

        mcp_manager.get_all_prompts.assert_called_once()

    async def test_prompts_changed_skips_server_without_name(self) -> None:
        """Callback prompts_change пропускает сервер без имени."""
        session = SessionFactory.create_session(
            cwd="/tmp",
            mcp_servers=[{"name": "srv", "command": "cmd"}],
        )
        manager, mcp_manager, _registry = await _init_with_mock_manager(
            session,
            [{"name": "srv", "command": "cmd"}],
        )

        callbacks = mcp_manager.register_prompt_change_callback.call_args_list
        prompts_callback = callbacks[0][0][0]
        session.mcp_servers = [{"command": "cmd"}, {"name": "srv", "command": "cmd"}]
        session.available_commands = [{"name": "status"}]
        mcp_manager.get_all_prompts.reset_mock()
        mcp_manager.get_all_prompts.return_value = {}

        with patch.object(manager, "_send_message", new=AsyncMock()):
            await prompts_callback()

        mcp_manager.get_all_prompts.assert_called_once()

    async def test_skips_invalid_server_config(self) -> None:
        """_initialize_mcp_servers пропускает невалидные конфигурации серверов."""
        session = SessionFactory.create_session(cwd="/tmp")
        registry = SessionRuntimeRegistry()
        mcp_manager = AsyncMock(spec=MCPManager)
        await registry.set_mcp_manager(session.session_id, mcp_manager)
        manager = MCPSessionManager(runtime_registry=registry)

        raw_configs: list[Any] = [
            "not_a_dict",
            {"name": "srv"},
            {"command": "cmd"},
        ]

        with patch(
            "codelab.server.protocol.mcp_session_manager.MCPManager",
            return_value=mcp_manager,
        ):
            with patch(
                "codelab.server.protocol.mcp_session_manager.logger"
            ) as mock_logger:
                await manager._initialize_mcp_servers(session, raw_configs)

        assert mock_logger.warning.call_count == 3
        mcp_manager.add_server.assert_not_awaited()


class TestRegisterMcpPromptsFromList:
    """Тесты для MCPSessionManager._register_mcp_prompts_from_list."""

    def test_optional_arguments_hint(self) -> None:
        """Формируется arguments_hint с обязательными и опциональными аргументами."""
        session = SessionFactory.create_session(cwd="/tmp")
        mcp_manager = MagicMock(spec=MCPManager)
        manager = MCPSessionManager(runtime_registry=SessionRuntimeRegistry())

        class PromptArg:
            def __init__(self, name: str, required: bool) -> None:
                self.name = name
                self.required = required

        class PromptDef:
            def __init__(self) -> None:
                self.name = "greet"
                self.title = "Greet"
                self.description = "Say hello"
                self.arguments = [
                    PromptArg("name", True),
                    PromptArg("tone", False),
                ]

        prompt_def = PromptDef()

        with patch(
            "codelab.server.protocol.mcp_session_manager.mcp_prompts_to_available_commands",
            return_value=[{"name": "greet"}],
        ):
            manager._register_mcp_prompts_from_list(
                session,
                mcp_manager,
                "srv",
                [prompt_def],
            )

        handler = session.mcp_prompt_handlers["greet"]
        assert handler._arguments_hint == "<name> [tone]"
        assert len(session.available_commands) == 1
