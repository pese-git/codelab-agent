"""Дополнительные тесты для покрытия use_cases.

Покрывает:
- CreateSessionUseCase: непредвиденное исключение
- LoadSessionUseCase: transport not initialized
- SendPromptUseCase: все callback-ветки и непредвиденное исключение
- ListSessionsUseCase: transport not connected
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from codelab.client.application.dto import (
    CreateSessionRequest,
    LoadSessionRequest,
    PromptCallbacks,
    SendPromptRequest,
)
from codelab.client.application.use_cases import (
    CreateSessionUseCase,
    ListSessionsUseCase,
    LoadSessionUseCase,
    SendPromptUseCase,
)
from codelab.client.domain import Session


class TestCreateSessionUseCaseCoverage:
    """Тесты для покрытия CreateSessionUseCase."""

    @pytest.mark.asyncio
    async def test_execute_unexpected_exception_wrapped(self) -> None:
        """Неожиданное исключение оборачивается в RuntimeError."""
        transport = AsyncMock()
        transport.is_initialized = Mock(return_value=True)
        transport.is_connected = Mock(return_value=True)
        transport.get_server_capabilities = Mock(return_value={})
        transport.send = AsyncMock(side_effect=ValueError("boom"))

        session_repo = AsyncMock()
        use_case = CreateSessionUseCase(transport=transport, session_repo=session_repo)

        request = CreateSessionRequest(
            server_host="127.0.0.1",
            server_port=8765,
            cwd="/tmp",
        )

        with pytest.raises(RuntimeError, match="Failed to create session"):
            await use_case.execute(request)


class TestLoadSessionUseCaseCoverage:
    """Тесты для покрытия LoadSessionUseCase."""

    @pytest.mark.asyncio
    async def test_execute_raises_when_transport_not_initialized(self) -> None:
        """UseCase поднимает ошибку если транспорт не инициализирован."""
        transport = AsyncMock()
        transport.is_initialized = Mock(return_value=False)
        session_repo = AsyncMock()

        use_case = LoadSessionUseCase(transport=transport, session_repo=session_repo)

        with pytest.raises(RuntimeError, match="Transport not initialized"):
            await use_case.execute(
                LoadSessionRequest(
                    session_id="sess_1",
                    server_host="127.0.0.1",
                    server_port=8765,
                )
            )


class TestSendPromptUseCaseCoverage:
    """Тесты для покрытия SendPromptUseCase callback-веток."""

    @pytest.fixture
    def base_setup(self):
        """Базовый setup для тестов SendPromptUseCase."""
        transport = AsyncMock()
        transport.request_with_callbacks = AsyncMock(
            return_value={
                "jsonrpc": "2.0",
                "id": "prompt_req",
                "result": {"stopReason": "end_turn"},
            }
        )

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
        return use_case, transport, session_repo

    @pytest.mark.asyncio
    async def test_execute_passes_on_terminal_create_callback(self, base_setup) -> None:
        """UseCase передаёт on_terminal_create callback."""
        use_case, transport, _ = base_setup
        callback = Mock()
        callbacks = PromptCallbacks(on_terminal_create=callback)

        await use_case.execute(
            SendPromptRequest(
                session_id="sess_123",
                prompt_text="Hello",
                callbacks=callbacks,
            )
        )

        call_kwargs = transport.request_with_callbacks.call_args.kwargs
        assert "on_terminal_create" in call_kwargs
        assert call_kwargs["on_terminal_create"] is callback

    @pytest.mark.asyncio
    async def test_execute_passes_on_terminal_output_callback(self, base_setup) -> None:
        """UseCase передаёт on_terminal_output callback."""
        use_case, transport, _ = base_setup
        callback = Mock()
        callbacks = PromptCallbacks(on_terminal_output=callback)

        await use_case.execute(
            SendPromptRequest(
                session_id="sess_123",
                prompt_text="Hello",
                callbacks=callbacks,
            )
        )

        call_kwargs = transport.request_with_callbacks.call_args.kwargs
        assert "on_terminal_output" in call_kwargs
        assert call_kwargs["on_terminal_output"] is callback

    @pytest.mark.asyncio
    async def test_execute_passes_on_terminal_wait_callback(self, base_setup) -> None:
        """UseCase передаёт on_terminal_wait callback."""
        use_case, transport, _ = base_setup
        callback = Mock()
        callbacks = PromptCallbacks(on_terminal_wait_for_exit=callback)

        await use_case.execute(
            SendPromptRequest(
                session_id="sess_123",
                prompt_text="Hello",
                callbacks=callbacks,
            )
        )

        call_kwargs = transport.request_with_callbacks.call_args.kwargs
        assert "on_terminal_wait" in call_kwargs
        assert call_kwargs["on_terminal_wait"] is callback

    @pytest.mark.asyncio
    async def test_execute_passes_on_terminal_release_callback(self, base_setup) -> None:
        """UseCase передаёт on_terminal_release callback."""
        use_case, transport, _ = base_setup
        callback = Mock()
        callbacks = PromptCallbacks(on_terminal_release=callback)

        await use_case.execute(
            SendPromptRequest(
                session_id="sess_123",
                prompt_text="Hello",
                callbacks=callbacks,
            )
        )

        call_kwargs = transport.request_with_callbacks.call_args.kwargs
        assert "on_terminal_release" in call_kwargs
        assert call_kwargs["on_terminal_release"] is callback

    @pytest.mark.asyncio
    async def test_execute_passes_on_terminal_kill_callback(self, base_setup) -> None:
        """UseCase передаёт on_terminal_kill callback."""
        use_case, transport, _ = base_setup
        callback = Mock()
        callbacks = PromptCallbacks(on_terminal_kill=callback)

        await use_case.execute(
            SendPromptRequest(
                session_id="sess_123",
                prompt_text="Hello",
                callbacks=callbacks,
            )
        )

        call_kwargs = transport.request_with_callbacks.call_args.kwargs
        assert "on_terminal_kill" in call_kwargs
        assert call_kwargs["on_terminal_kill"] is callback

    @pytest.mark.asyncio
    async def test_execute_unexpected_exception_wrapped(self, base_setup) -> None:
        """Неожиданное исключение оборачивается в RuntimeError."""
        use_case, transport, _ = base_setup
        new_mock = AsyncMock(side_effect=ValueError("boom"))
        transport.request_with_callbacks = new_mock
        print(f"transport id: {id(transport)}, use_case._transport id: {id(use_case._transport)}")
        print(
            f"new mock id: {id(new_mock)}, "
            f"transport.request_with_callbacks id: {id(transport.request_with_callbacks)}"
        )

        with pytest.raises(RuntimeError, match="Failed to send prompt"):
            await use_case.execute(
                SendPromptRequest(
                    session_id="sess_123",
                    prompt_text="Hello",
                )
            )


class TestListSessionsUseCaseCoverage:
    """Тесты для покрытия ListSessionsUseCase."""

    @pytest.mark.asyncio
    async def test_execute_raises_when_transport_not_connected(self) -> None:
        """UseCase поднимает ошибку если транспорт не подключён."""
        transport = AsyncMock()
        transport.is_initialized = Mock(return_value=True)
        transport.is_connected = Mock(return_value=False)
        session_repo = AsyncMock()

        use_case = ListSessionsUseCase(transport=transport, session_repo=session_repo)

        with pytest.raises(RuntimeError, match="Transport not connected"):
            await use_case.execute()
