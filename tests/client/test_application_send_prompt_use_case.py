"""Тесты для SendPromptUseCase."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from codelab.client.application.dto import PromptCallbacks, SendPromptRequest
from codelab.client.application.use_cases import SendPromptUseCase
from codelab.client.domain import Session


class TestSendPromptUseCase:
    """Проверки сценария отправки prompt через `session/prompt`."""

    @pytest.mark.asyncio
    async def test_execute_sends_prompt_and_returns_result(self) -> None:
        """UseCase отправляет prompt и возвращает результат."""
        transport = AsyncMock()
        transport.request_with_callbacks = AsyncMock(return_value={
            "jsonrpc": "2.0",
            "id": "prompt_req",
            "result": {
                "stopReason": "end_turn",
                "content": [{"type": "text", "text": "Response"}],
            },
        })

        session = Session.create(
            server_host="127.0.0.1",
            server_port=8765,
            client_capabilities={},
            server_capabilities={},
            session_id="sess_123",
        )
        session_repo = AsyncMock()
        session_repo.load = AsyncMock(return_value=session)
        session_repo.save = AsyncMock()

        use_case = SendPromptUseCase(transport=transport, session_repo=session_repo)

        request = SendPromptRequest(
            session_id="sess_123",
            prompt_text="Hello, world!",
        )
        response = await use_case.execute(request)

        assert response.session_id == "sess_123"
        assert response.prompt_result["stopReason"] == "end_turn"
        transport.request_with_callbacks.assert_awaited_once()
        session_repo.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_raises_when_session_not_found(self) -> None:
        """UseCase поднимает ошибку если сессия не найдена."""
        transport = AsyncMock()
        session_repo = AsyncMock()
        session_repo.load = AsyncMock(return_value=None)

        use_case = SendPromptUseCase(transport=transport, session_repo=session_repo)

        request = SendPromptRequest(
            session_id="nonexistent",
            prompt_text="Hello",
        )

        with pytest.raises(ValueError, match="not found"):
            await use_case.execute(request)

    @pytest.mark.asyncio
    async def test_execute_raises_on_prompt_error(self) -> None:
        """UseCase поднимает ошибку при ошибке prompt."""
        transport = AsyncMock()
        transport.request_with_callbacks = AsyncMock(return_value={
            "jsonrpc": "2.0",
            "id": "prompt_req",
            "error": {
                "code": -32600,
                "message": "Invalid Request",
            },
        })

        session = Session.create(
            server_host="127.0.0.1",
            server_port=8765,
            client_capabilities={},
            server_capabilities={},
            session_id="sess_123",
        )
        session_repo = AsyncMock()
        session_repo.load = AsyncMock(return_value=session)

        use_case = SendPromptUseCase(transport=transport, session_repo=session_repo)

        request = SendPromptRequest(
            session_id="sess_123",
            prompt_text="Hello",
        )

        with pytest.raises(RuntimeError, match="Prompt failed"):
            await use_case.execute(request)

    @pytest.mark.asyncio
    async def test_execute_collects_updates(self) -> None:
        """UseCase собирает updates во время выполнения prompt."""
        transport = AsyncMock()

        async def request_with_callbacks_side_effect(
            *,
            method: str,
            params: dict,
            on_update,
            **kwargs,
        ) -> dict:
            # Имитируем получение updates
            on_update({
                "jsonrpc": "2.0",
                "method": "session/update",
                "params": {"sessionId": "sess_123", "update": {"type": "chunk"}},
            })
            on_update({
                "jsonrpc": "2.0",
                "method": "session/update",
                "params": {"sessionId": "sess_123", "update": {"type": "chunk"}},
            })
            return {
                "jsonrpc": "2.0",
                "id": "prompt_req",
                "result": {"stopReason": "end_turn"},
            }

        transport.request_with_callbacks.side_effect = request_with_callbacks_side_effect

        session = Session.create(
            server_host="127.0.0.1",
            server_port=8765,
            client_capabilities={},
            server_capabilities={},
            session_id="sess_123",
        )
        session_repo = AsyncMock()
        session_repo.load = AsyncMock(return_value=session)
        session_repo.save = AsyncMock()

        use_case = SendPromptUseCase(transport=transport, session_repo=session_repo)

        request = SendPromptRequest(
            session_id="sess_123",
            prompt_text="Hello",
        )
        response = await use_case.execute(request)

        assert len(response.updates) == 2

    @pytest.mark.asyncio
    async def test_execute_calls_user_on_update_callback(self) -> None:
        """UseCase вызывает пользовательский on_update callback."""
        transport = AsyncMock()

        async def request_with_callbacks_side_effect(
            *,
            method: str,
            params: dict,
            on_update,
            **kwargs,
        ) -> dict:
            on_update({
                "jsonrpc": "2.0",
                "method": "session/update",
                "params": {"sessionId": "sess_123", "update": {"type": "chunk"}},
            })
            return {
                "jsonrpc": "2.0",
                "id": "prompt_req",
                "result": {"stopReason": "end_turn"},
            }

        transport.request_with_callbacks.side_effect = request_with_callbacks_side_effect

        session = Session.create(
            server_host="127.0.0.1",
            server_port=8765,
            client_capabilities={},
            server_capabilities={},
            session_id="sess_123",
        )
        session_repo = AsyncMock()
        session_repo.load = AsyncMock(return_value=session)
        session_repo.save = AsyncMock()

        user_callback = Mock()
        callbacks = PromptCallbacks(on_update=user_callback)

        use_case = SendPromptUseCase(transport=transport, session_repo=session_repo)

        request = SendPromptRequest(
            session_id="sess_123",
            prompt_text="Hello",
            callbacks=callbacks,
        )
        await use_case.execute(request)

        user_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_handles_callback_exception(self) -> None:
        """UseCase обрабатывает исключения в пользовательском callback."""
        transport = AsyncMock()

        async def request_with_callbacks_side_effect(
            *,
            method: str,
            params: dict,
            on_update,
            **kwargs,
        ) -> dict:
            on_update({
                "jsonrpc": "2.0",
                "method": "session/update",
                "params": {"sessionId": "sess_123", "update": {"type": "chunk"}},
            })
            return {
                "jsonrpc": "2.0",
                "id": "prompt_req",
                "result": {"stopReason": "end_turn"},
            }

        transport.request_with_callbacks.side_effect = request_with_callbacks_side_effect

        session = Session.create(
            server_host="127.0.0.1",
            server_port=8765,
            client_capabilities={},
            server_capabilities={},
            session_id="sess_123",
        )
        session_repo = AsyncMock()
        session_repo.load = AsyncMock(return_value=session)
        session_repo.save = AsyncMock()

        # Callback с исключением
        user_callback = Mock(side_effect=RuntimeError("Callback error"))
        callbacks = PromptCallbacks(on_update=user_callback)

        use_case = SendPromptUseCase(transport=transport, session_repo=session_repo)

        request = SendPromptRequest(
            session_id="sess_123",
            prompt_text="Hello",
            callbacks=callbacks,
        )
        # Не должно поднять исключение
        response = await use_case.execute(request)
        assert response.session_id == "sess_123"

    @pytest.mark.asyncio
    async def test_execute_passes_terminal_callbacks(self) -> None:
        """UseCase передаёт terminal callbacks в transport."""
        transport = AsyncMock()
        transport.request_with_callbacks = AsyncMock(return_value={
            "jsonrpc": "2.0",
            "id": "prompt_req",
            "result": {"stopReason": "end_turn"},
        })

        session = Session.create(
            server_host="127.0.0.1",
            server_port=8765,
            client_capabilities={},
            server_capabilities={},
            session_id="sess_123",
        )
        session_repo = AsyncMock()
        session_repo.load = AsyncMock(return_value=session)
        session_repo.save = AsyncMock()

        on_terminal_create = AsyncMock()
        on_terminal_output = AsyncMock()
        callbacks = PromptCallbacks(
            on_terminal_create=on_terminal_create,
            on_terminal_output=on_terminal_output,
        )

        use_case = SendPromptUseCase(transport=transport, session_repo=session_repo)

        request = SendPromptRequest(
            session_id="sess_123",
            prompt_text="Hello",
            callbacks=callbacks,
        )
        await use_case.execute(request)

        # Проверяем что callbacks были переданы
        call_kwargs = transport.request_with_callbacks.call_args.kwargs
        assert "on_terminal_create" in call_kwargs
        assert "on_terminal_output" in call_kwargs

    @pytest.mark.asyncio
    async def test_execute_marks_session_authenticated(self) -> None:
        """UseCase помечает сессию как аутентифицированную после успешного prompt."""
        transport = AsyncMock()
        transport.request_with_callbacks = AsyncMock(return_value={
            "jsonrpc": "2.0",
            "id": "prompt_req",
            "result": {"stopReason": "end_turn"},
        })

        session = Session.create(
            server_host="127.0.0.1",
            server_port=8765,
            client_capabilities={},
            server_capabilities={},
            session_id="sess_123",
        )
        assert session.is_authenticated is False

        session_repo = AsyncMock()
        session_repo.load = AsyncMock(return_value=session)
        session_repo.save = AsyncMock()

        use_case = SendPromptUseCase(transport=transport, session_repo=session_repo)

        request = SendPromptRequest(
            session_id="sess_123",
            prompt_text="Hello",
        )
        await use_case.execute(request)

        assert session.is_authenticated is True
        session_repo.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_handles_cancelled_error(self) -> None:
        """UseCase обрабатывает CancelledError."""
        import asyncio

        transport = AsyncMock()
        transport.request_with_callbacks = AsyncMock(side_effect=asyncio.CancelledError())

        session = Session.create(
            server_host="127.0.0.1",
            server_port=8765,
            client_capabilities={},
            server_capabilities={},
            session_id="sess_123",
        )
        session_repo = AsyncMock()
        session_repo.load = AsyncMock(return_value=session)

        use_case = SendPromptUseCase(transport=transport, session_repo=session_repo)

        request = SendPromptRequest(
            session_id="sess_123",
            prompt_text="Hello",
        )

        with pytest.raises(asyncio.CancelledError):
            await use_case.execute(request)

    @pytest.mark.asyncio
    async def test_execute_handles_timeout_error(self) -> None:
        """UseCase обрабатывает TimeoutError."""
        transport = AsyncMock()
        transport.request_with_callbacks = AsyncMock(side_effect=TimeoutError("Timeout"))

        session = Session.create(
            server_host="127.0.0.1",
            server_port=8765,
            client_capabilities={},
            server_capabilities={},
            session_id="sess_123",
        )
        session_repo = AsyncMock()
        session_repo.load = AsyncMock(return_value=session)

        use_case = SendPromptUseCase(transport=transport, session_repo=session_repo)

        request = SendPromptRequest(
            session_id="sess_123",
            prompt_text="Hello",
        )

        with pytest.raises(TimeoutError):
            await use_case.execute(request)
