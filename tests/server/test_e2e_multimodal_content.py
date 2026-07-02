"""E2E тесты multimodal content через stdio transport.

Проверяет:
- Отправка image content в session/prompt
- Отправка audio content в session/prompt
- Отправка resource content в session/prompt
- Отправка resource_link content в session/prompt
- Смешанный контент (text + image)
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import agent_flow_harness as h
import pytest

_PROJECT_ROOT = Path(__file__).parent.parent.parent


class StdioTransport:
    """Transport поверх stdin/stdout subprocess-сервера."""

    def __init__(self, proc: asyncio.subprocess.Process) -> None:
        self._proc = proc

    async def send(self, obj: dict) -> None:
        assert self._proc.stdin is not None
        self._proc.stdin.write((json.dumps(obj) + "\n").encode())
        await self._proc.stdin.drain()

    async def recv(self, timeout: float = 15.0) -> dict:
        assert self._proc.stdout is not None
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise TimeoutError("No JSON message from server")
            line = await asyncio.wait_for(
                self._proc.stdout.readline(), timeout=remaining
            )
            if not line:
                raise TimeoutError("Server stdout closed")
            text = line.decode().strip()
            if not text:
                continue
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                continue


async def _start_server(
    tmp_cwd: Path, scenario_path: Path
) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        "uv", "run", "--directory", str(_PROJECT_ROOT),
        "codelab", "serve", "--stdio",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(tmp_cwd),
        env=h.server_env(tmp_cwd, scenario_path),
    )


async def _stop_server(proc: asyncio.subprocess.Process) -> None:
    if proc.stdin is not None:
        proc.stdin.close()
    try:
        await asyncio.wait_for(proc.wait(), timeout=5.0)
    except TimeoutError:
        proc.terminate()
        await proc.wait()


class _server:
    """Async context manager: поднять stdio-сервер и отдать (transport)."""

    def __init__(self, tmp_cwd: Path, scenario: dict) -> None:
        self._tmp_cwd = tmp_cwd
        self._scenario = scenario
        self._proc: asyncio.subprocess.Process | None = None

    async def __aenter__(self) -> StdioTransport:
        h.default_primary_agent(self._tmp_cwd)
        scenario_path = h.write_scenario(self._tmp_cwd, self._scenario)
        self._proc = await _start_server(self._tmp_cwd, scenario_path)
        await asyncio.sleep(0.5)
        return StdioTransport(self._proc)

    async def __aexit__(self, *exc) -> None:
        if self._proc is not None:
            await _stop_server(self._proc)


@pytest.fixture
def tmp_cwd(tmp_path: Path) -> Path:
    return tmp_path


async def _handshake(transport: StdioTransport, tmp_cwd: Path) -> str:
    """initialize + session/new → возвращает session_id."""
    await transport.send(
        h.request(
            "initialize",
            {
                "protocolVersion": 1,
                "clientCapabilities": {
                    "fs": {"readTextFile": True, "writeTextFile": True},
                    "terminal": True,
                },
            },
            1,
        )
    )
    init = await transport.recv()
    assert init["id"] == 1

    await transport.send(
        h.request("session/new", {"cwd": str(tmp_cwd), "mcpServers": []}, 2)
    )
    new = await transport.recv()
    assert new["id"] == 2
    return new["result"]["sessionId"]


async def _run_multimodal_prompt(
    transport: StdioTransport,
    session_id: str,
    prompt_content: list[dict],
    request_id: int,
    timeout: float = 20.0,
) -> tuple[dict, list[dict]]:
    """Отправить session/prompt с multimodal content и собрать notifications."""
    await transport.send(
        h.request(
            "session/prompt",
            {"sessionId": session_id, "prompt": prompt_content},
            request_id,
        )
    )

    notifications: list[dict] = []
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise TimeoutError(f"prompt {request_id} did not finish")
        msg = await transport.recv(timeout=remaining)

        if msg.get("id") == request_id and ("result" in msg or "error" in msg):
            return msg, notifications

        method = msg.get("method")
        if method is not None and "id" in msg:
            await transport.send(h.result(msg["id"], {}))
        elif method is not None:
            notifications.append(msg)


@pytest.mark.asyncio
async def test_prompt_with_image_content(tmp_cwd: Path) -> None:
    """session/prompt принимает image content."""
    scenario = h.chat_scenario()

    async with _server(tmp_cwd, scenario) as transport:
        session_id = await _handshake(transport, tmp_cwd)

        prompt_content = [
            {"type": "text", "text": "What is in this image?"},
            {
                "type": "image",
                "data": (
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
                    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
                ),
                "mimeType": "image/png",
            },
        ]

        resp, notifications = await _run_multimodal_prompt(
            transport, session_id, prompt_content, 3
        )

        assert "result" in resp
        assert resp.get("result", {}).get("stopReason") == "end_turn"


@pytest.mark.asyncio
async def test_prompt_with_audio_content(tmp_cwd: Path) -> None:
    """session/prompt принимает audio content."""
    scenario = h.chat_scenario()

    async with _server(tmp_cwd, scenario) as transport:
        session_id = await _handshake(transport, tmp_cwd)

        prompt_content = [
            {"type": "text", "text": "Transcribe this audio"},
            {
                "type": "audio",
                "data": (
                    "SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjU4Ljc2LjEwMAAAAAAAAAAAAAAA"
                    "//tQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWGluZwAAAA8A"
                    "AAACAAABhgC7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7"
                    "u7u7u7u7u7u7u7u7u7u7u7v////////////////////////////8AAAAATGF2"
                    "YzU4LjEzAAAAAAAAAAAAAAAAJAAAAAAAAAAAAYYoRwAAAAAAAAAAAAAAAAAA"
                    "AA=="
                ),
                "mimeType": "audio/mp3",
            },
        ]

        resp, notifications = await _run_multimodal_prompt(
            transport, session_id, prompt_content, 3
        )

        assert "result" in resp
        assert resp.get("result", {}).get("stopReason") == "end_turn"


@pytest.mark.asyncio
async def test_prompt_with_resource_content(tmp_cwd: Path) -> None:
    """session/prompt принимает resource content (embedded resource)."""
    scenario = h.chat_scenario()

    async with _server(tmp_cwd, scenario) as transport:
        session_id = await _handshake(transport, tmp_cwd)

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

        resp, notifications = await _run_multimodal_prompt(
            transport, session_id, prompt_content, 3
        )

        assert "result" in resp
        assert resp.get("result", {}).get("stopReason") == "end_turn"


@pytest.mark.asyncio
async def test_prompt_with_resource_link_content(tmp_cwd: Path) -> None:
    """session/prompt принимает resource_link content."""
    scenario = h.chat_scenario()

    async with _server(tmp_cwd, scenario) as transport:
        session_id = await _handshake(transport, tmp_cwd)

        prompt_content = [
            {"type": "text", "text": "Check this link"},
            {
                "type": "resource_link",
                "uri": "https://example.com",
                "name": "Example Website",
                "description": "A test website",
            },
        ]

        resp, notifications = await _run_multimodal_prompt(
            transport, session_id, prompt_content, 3
        )

        assert "result" in resp
        assert resp.get("result", {}).get("stopReason") == "end_turn"


@pytest.mark.asyncio
async def test_prompt_with_mixed_content(tmp_cwd: Path) -> None:
    """session/prompt принимает смешанный контент (text + image + resource_link)."""
    scenario = h.chat_scenario()

    async with _server(tmp_cwd, scenario) as transport:
        session_id = await _handshake(transport, tmp_cwd)

        prompt_content = [
            {"type": "text", "text": "Compare this image with the link"},
            {
                "type": "image",
                "data": (
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
                    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
                ),
                "mimeType": "image/png",
            },
            {
                "type": "resource_link",
                "uri": "https://example.com/reference",
                "name": "Reference",
            },
        ]

        resp, notifications = await _run_multimodal_prompt(
            transport, session_id, prompt_content, 3
        )

        assert "result" in resp
        assert resp.get("result", {}).get("stopReason") == "end_turn"
