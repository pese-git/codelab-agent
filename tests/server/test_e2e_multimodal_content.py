"""E2E тесты multimodal content через stdio transport.

Проверяет:
- Отправка image content в session/prompt
- Отправка audio content в session/prompt
- Отправка resource content в session/prompt
- Отправка resource_link content в session/prompt
- Смешанный контент (text + image)

Согласованность с ACP: перед отправкой image/audio/embeddedContext клиент
обязан убедиться, что агент объявил соответствующую prompt capability
(02-Initialization.md). Поэтому тесты сперва читают promptCapabilities из
initialize response и пропускают проверку, если capability не объявлена.
"""

from __future__ import annotations

from pathlib import Path

import agent_flow_harness as h
import pytest

_IMAGE_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
_AUDIO_MP3 = (
    "SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjU4Ljc2LjEwMAAAAAAAAAAAAAAA"
    "//tQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWGluZwAAAA8A"
    "AAACAAABhgC7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7"
    "u7u7u7u7u7u7u7u7u7u7u7v////////////////////////////8AAAAATGF2"
    "YzU4LjEzAAAAAAAAAAAAAAAAJAAAAAAAAAAAAYYoRwAAAAAAAAAAAAAAAAAA"
    "AA=="
)


@pytest.fixture
def tmp_cwd(tmp_path: Path) -> Path:
    return tmp_path


async def _handshake_require(
    transport: h.StdioTransport, tmp_cwd: Path, capability: str | None
) -> str:
    """initialize + session/new; пропустить тест, если capability не объявлена.

    capability — ключ в promptCapabilities (image/audio/embeddedContext) либо
    None, если контент не требует опциональной capability (resource_link/text).
    """
    init = await h.initialize(transport)
    prompt_caps = (
        init["result"].get("agentCapabilities", {}).get("promptCapabilities", {})
    )
    if capability is not None and not prompt_caps.get(capability):
        pytest.skip(f"агент не объявил promptCapabilities.{capability}")
    return await h.session_new(transport, tmp_cwd)


@pytest.mark.asyncio
async def test_prompt_with_image_content(tmp_cwd: Path) -> None:
    """session/prompt принимает image content."""
    async with h.StdioServer(tmp_cwd, h.chat_scenario()) as transport:
        session_id = await _handshake_require(transport, tmp_cwd, "image")
        prompt_content = [
            {"type": "text", "text": "What is in this image?"},
            {"type": "image", "data": _IMAGE_PNG, "mimeType": "image/png"},
        ]
        resp, _, _ = await h.run_prompt(
            transport, session_id, "", 3, prompt_blocks=prompt_content
        )
        assert resp.get("result", {}).get("stopReason") == "end_turn"


@pytest.mark.asyncio
async def test_prompt_with_audio_content(tmp_cwd: Path) -> None:
    """session/prompt принимает audio content."""
    async with h.StdioServer(tmp_cwd, h.chat_scenario()) as transport:
        session_id = await _handshake_require(transport, tmp_cwd, "audio")
        prompt_content = [
            {"type": "text", "text": "Transcribe this audio"},
            {"type": "audio", "data": _AUDIO_MP3, "mimeType": "audio/mp3"},
        ]
        resp, _, _ = await h.run_prompt(
            transport, session_id, "", 3, prompt_blocks=prompt_content
        )
        assert resp.get("result", {}).get("stopReason") == "end_turn"


@pytest.mark.asyncio
async def test_prompt_with_resource_content(tmp_cwd: Path) -> None:
    """session/prompt принимает resource content (embedded resource)."""
    async with h.StdioServer(tmp_cwd, h.chat_scenario()) as transport:
        session_id = await _handshake_require(transport, tmp_cwd, "embeddedContext")
        prompt_content = [
            {"type": "text", "text": "Summarize this document"},
            {
                "type": "resource",
                "resource": {
                    "uri": "file:///tmp/document.txt",
                    "text": "This is a test document with some content.",
                    "mimeType": "text/plain",
                },
            },
        ]
        resp, _, _ = await h.run_prompt(
            transport, session_id, "", 3, prompt_blocks=prompt_content
        )
        assert resp.get("result", {}).get("stopReason") == "end_turn"


@pytest.mark.asyncio
async def test_prompt_with_resource_link_content(tmp_cwd: Path) -> None:
    """session/prompt принимает resource_link content.

    resource_link — часть baseline ContentBlock, отдельной capability не требует.
    """
    async with h.StdioServer(tmp_cwd, h.chat_scenario()) as transport:
        session_id = await _handshake_require(transport, tmp_cwd, None)
        prompt_content = [
            {"type": "text", "text": "Check this link"},
            {
                "type": "resource_link",
                "uri": "https://example.com",
                "name": "Example Website",
                "description": "A test website",
            },
        ]
        resp, _, _ = await h.run_prompt(
            transport, session_id, "", 3, prompt_blocks=prompt_content
        )
        assert resp.get("result", {}).get("stopReason") == "end_turn"


@pytest.mark.asyncio
async def test_prompt_with_mixed_content(tmp_cwd: Path) -> None:
    """session/prompt принимает смешанный контент (text + image + resource_link)."""
    async with h.StdioServer(tmp_cwd, h.chat_scenario()) as transport:
        session_id = await _handshake_require(transport, tmp_cwd, "image")
        prompt_content = [
            {"type": "text", "text": "Compare this image with the link"},
            {"type": "image", "data": _IMAGE_PNG, "mimeType": "image/png"},
            {
                "type": "resource_link",
                "uri": "https://example.com/reference",
                "name": "Reference",
            },
        ]
        resp, _, _ = await h.run_prompt(
            transport, session_id, "", 3, prompt_blocks=prompt_content
        )
        assert resp.get("result", {}).get("stopReason") == "end_turn"
