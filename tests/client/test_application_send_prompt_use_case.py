"""Тесты для SendPromptUseCase."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from codelab.client.application.dto import PromptCallbacks, SendPromptRequest
from codelab.client.application.use_cases import SendPromptUseCase
from codelab.client.domain import (
    AudioContent,
    ImageContent,
    ResourceContent,
    ResourceLinkContent,
    Session,
)


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


class TestSendPromptUseCaseMultimodal:
    """Проверки отправки мультимодального контента."""

    @pytest.mark.asyncio
    async def test_execute_sends_image_when_supported(self) -> None:
        """UseCase отправляет изображение когда агент поддерживает image."""
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
            server_capabilities={
                "promptCapabilities": {"image": True},
            },
            session_id="sess_123",
        )
        session_repo = AsyncMock()
        session_repo.load = AsyncMock(return_value=session)
        session_repo.save = AsyncMock()

        use_case = SendPromptUseCase(transport=transport, session_repo=session_repo)

        request = SendPromptRequest(
            session_id="sess_123",
            prompt_text="What is in this image?",
            images=[
                ImageContent(
                    data="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
                    mime_type="image/png",
                ),
            ],
        )
        await use_case.execute(request)

        # Проверяем что prompt содержит image content block
        call_args = transport.request_with_callbacks.call_args
        prompt_content = call_args.kwargs["params"]["prompt"]
        assert len(prompt_content) == 2
        assert prompt_content[0]["type"] == "text"
        assert prompt_content[1]["type"] == "image"
        assert prompt_content[1]["mimeType"] == "image/png"

    @pytest.mark.asyncio
    async def test_execute_raises_when_image_not_supported(self) -> None:
        """UseCase поднимает ошибку когда агент не поддерживает image."""
        transport = AsyncMock()

        session = Session.create(
            server_host="127.0.0.1",
            server_port=8765,
            client_capabilities={},
            server_capabilities={
                "promptCapabilities": {"image": False},
            },
            session_id="sess_123",
        )
        session_repo = AsyncMock()
        session_repo.load = AsyncMock(return_value=session)

        use_case = SendPromptUseCase(transport=transport, session_repo=session_repo)

        request = SendPromptRequest(
            session_id="sess_123",
            prompt_text="What is in this image?",
            images=[
                ImageContent(data="base64data", mime_type="image/png"),
            ],
        )

        with pytest.raises(ValueError, match="does not support image"):
            await use_case.execute(request)

    @pytest.mark.asyncio
    async def test_execute_sends_audio_when_supported(self) -> None:
        """UseCase отправляет аудио когда агент поддерживает audio."""
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
            server_capabilities={
                "promptCapabilities": {"audio": True},
            },
            session_id="sess_123",
        )
        session_repo = AsyncMock()
        session_repo.load = AsyncMock(return_value=session)
        session_repo.save = AsyncMock()

        use_case = SendPromptUseCase(transport=transport, session_repo=session_repo)

        request = SendPromptRequest(
            session_id="sess_123",
            prompt_text="Transcribe this audio",
            audio=[
                AudioContent(data="base64audiodata", mime_type="audio/wav"),
            ],
        )
        await use_case.execute(request)

        call_args = transport.request_with_callbacks.call_args
        prompt_content = call_args.kwargs["params"]["prompt"]
        assert len(prompt_content) == 2
        assert prompt_content[1]["type"] == "audio"
        assert prompt_content[1]["mimeType"] == "audio/wav"

    @pytest.mark.asyncio
    async def test_execute_raises_when_audio_not_supported(self) -> None:
        """UseCase поднимает ошибку когда агент не поддерживает audio."""
        transport = AsyncMock()

        session = Session.create(
            server_host="127.0.0.1",
            server_port=8765,
            client_capabilities={},
            server_capabilities={
                "promptCapabilities": {"audio": False},
            },
            session_id="sess_123",
        )
        session_repo = AsyncMock()
        session_repo.load = AsyncMock(return_value=session)

        use_case = SendPromptUseCase(transport=transport, session_repo=session_repo)

        request = SendPromptRequest(
            session_id="sess_123",
            prompt_text="Transcribe this",
            audio=[AudioContent(data="data", mime_type="audio/wav")],
        )

        with pytest.raises(ValueError, match="does not support audio"):
            await use_case.execute(request)

    @pytest.mark.asyncio
    async def test_execute_sends_resource_when_supported(self) -> None:
        """UseCase отправляет embedded resource когда агент поддерживает embeddedContext."""
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
            server_capabilities={
                "promptCapabilities": {"embeddedContext": True},
            },
            session_id="sess_123",
        )
        session_repo = AsyncMock()
        session_repo.load = AsyncMock(return_value=session)
        session_repo.save = AsyncMock()

        use_case = SendPromptUseCase(transport=transport, session_repo=session_repo)

        request = SendPromptRequest(
            session_id="sess_123",
            prompt_text="Analyze this code",
            resources=[
                ResourceContent(
                    uri="file:///path/to/code.py",
                    text="def hello(): print('Hello')",
                    mime_type="text/x-python",
                ),
            ],
        )
        await use_case.execute(request)

        call_args = transport.request_with_callbacks.call_args
        prompt_content = call_args.kwargs["params"]["prompt"]
        assert len(prompt_content) == 2
        assert prompt_content[1]["type"] == "resource"
        assert prompt_content[1]["resource"]["uri"] == "file:///path/to/code.py"
        assert prompt_content[1]["resource"]["text"] == "def hello(): print('Hello')"

    @pytest.mark.asyncio
    async def test_execute_raises_when_resource_not_supported(self) -> None:
        """UseCase поднимает ошибку когда агент не поддерживает embeddedContext."""
        transport = AsyncMock()

        session = Session.create(
            server_host="127.0.0.1",
            server_port=8765,
            client_capabilities={},
            server_capabilities={
                "promptCapabilities": {"embeddedContext": False},
            },
            session_id="sess_123",
        )
        session_repo = AsyncMock()
        session_repo.load = AsyncMock(return_value=session)

        use_case = SendPromptUseCase(transport=transport, session_repo=session_repo)

        request = SendPromptRequest(
            session_id="sess_123",
            prompt_text="Analyze this",
            resources=[
                ResourceContent(uri="file:///path/to/file", text="content"),
            ],
        )

        with pytest.raises(ValueError, match="does not support resource"):
            await use_case.execute(request)

    @pytest.mark.asyncio
    async def test_execute_sends_resource_link_always(self) -> None:
        """UseCase отправляет resource_link без проверки capabilities (baseline)."""
        transport = AsyncMock()
        transport.request_with_callbacks = AsyncMock(return_value={
            "jsonrpc": "2.0",
            "id": "prompt_req",
            "result": {"stopReason": "end_turn"},
        })

        # Нет promptCapabilities - resource_link всё равно должен работать
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
            prompt_text="Look at this file",
            resource_links=[
                ResourceLinkContent(
                    uri="file:///path/to/document.pdf",
                    name="document.pdf",
                    mime_type="application/pdf",
                    size=1024,
                ),
            ],
        )
        await use_case.execute(request)

        call_args = transport.request_with_callbacks.call_args
        prompt_content = call_args.kwargs["params"]["prompt"]
        assert len(prompt_content) == 2
        assert prompt_content[1]["type"] == "resource_link"
        assert prompt_content[1]["uri"] == "file:///path/to/document.pdf"
        assert prompt_content[1]["name"] == "document.pdf"

    @pytest.mark.asyncio
    async def test_execute_sends_multimodal_prompt(self) -> None:
        """UseCase отправляет промпт с несколькими типами контента."""
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
            server_capabilities={
                "promptCapabilities": {
                    "image": True,
                    "audio": True,
                    "embeddedContext": True,
                },
            },
            session_id="sess_123",
        )
        session_repo = AsyncMock()
        session_repo.load = AsyncMock(return_value=session)
        session_repo.save = AsyncMock()

        use_case = SendPromptUseCase(transport=transport, session_repo=session_repo)

        request = SendPromptRequest(
            session_id="sess_123",
            prompt_text="Analyze all of this",
            images=[ImageContent(data="img_data", mime_type="image/png")],
            audio=[AudioContent(data="audio_data", mime_type="audio/wav")],
            resources=[ResourceContent(uri="file:///code.py", text="code")],
            resource_links=[ResourceLinkContent(uri="file:///doc.pdf", name="doc.pdf")],
        )
        await use_case.execute(request)

        call_args = transport.request_with_callbacks.call_args
        prompt_content = call_args.kwargs["params"]["prompt"]
        # text + image + audio + resource + resource_link
        assert len(prompt_content) == 5
        types = [item["type"] for item in prompt_content]
        assert "text" in types
        assert "image" in types
        assert "audio" in types
        assert "resource" in types
        assert "resource_link" in types

    @pytest.mark.asyncio
    async def test_execute_handles_missing_capabilities_gracefully(self) -> None:
        """UseCase работает когда server_capabilities отсутствует."""
        transport = AsyncMock()
        transport.request_with_callbacks = AsyncMock(return_value={
            "jsonrpc": "2.0",
            "id": "prompt_req",
            "result": {"stopReason": "end_turn"},
        })

        # session без server_capabilities
        session = Session.create(
            server_host="127.0.0.1",
            server_port=8765,
            client_capabilities={},
            server_capabilities=None,
            session_id="sess_123",
        )
        session_repo = AsyncMock()
        session_repo.load = AsyncMock(return_value=session)
        session_repo.save = AsyncMock()

        use_case = SendPromptUseCase(transport=transport, session_repo=session_repo)

        # Только текст - должно работать
        request = SendPromptRequest(
            session_id="sess_123",
            prompt_text="Hello",
        )
        response = await use_case.execute(request)
        assert response.session_id == "sess_123"
