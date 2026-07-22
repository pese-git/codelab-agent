"""Golden-тест wire-формата session/update notifications.

Фиксирует байт-идентичность JSON-RPC payload для каждого типа
``session/update``, который эмитится из ядра/протокола. Снимки лежат
рядом как ``*.json`` и сгенерированы скриптом ``_generate_baseline.py``.

Зачем: Фаза 3 change ``acp-independent-agent-core`` (``ADR-005``) вводит
``UpdateSink(Protocol)`` и ACP-адаптер над ``SessionUpdateSink``. Любое
изменение wire-формата = breaking change для клиентов ACP → должно быть
явно зафиксировано через обновление снимка (review + bump).

Тест НЕ использует сторонние snapshot-библиотеки — только ``json.dumps``
с детерминированным форматированием (``sort_keys=True``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codelab.server.agent.core.strategies.dispatcher import StrategyDispatcher
from codelab.server.protocol.handlers.pipeline.stages.agent_loop.updates import (
    SessionUpdateSink,
)
from codelab.server.protocol.handlers.plan_builder import PlanBuilder
from codelab.server.protocol.handlers.tool_call_handler import ToolCallHandler

GOLDEN_DIR = Path(__file__).parent


def _load(name: str) -> dict:
    """Загрузить golden-снимок как dict."""
    return json.loads((GOLDEN_DIR / f"{name}.json").read_text(encoding="utf-8"))


def _actual(msg) -> dict:
    """Сериализовать ACPMessage в стабильный dict для сравнения."""
    return json.loads(json.dumps(msg.to_dict(), sort_keys=True, ensure_ascii=False))


def test_agent_message_chunk_wire_format() -> None:
    """`agent_message_chunk` с текстом ответа — байт-в-байт прежний."""
    expected = _load("agent_message_chunk")
    actual = _actual(
        SessionUpdateSink.build_agent_message_chunk(
            session_id="sess_001",
            text="I'll read the file first.",
        ),
    )
    assert actual == expected


def test_plan_wire_format() -> None:
    """`plan` с multi-step entries — байт-в-байт прежний."""
    expected = _load("plan")
    plan_builder = PlanBuilder()
    actual = _actual(
        plan_builder.build_plan_notification(
            session_id="sess_001",
            plan_entries=[
                {"content": "Read README.md", "priority": "high", "status": "in_progress"},
                {"content": "Summarize architecture", "priority": "medium", "status": "pending"},
            ],
        ),
    )
    assert actual == expected


def test_tool_call_create_wire_format() -> None:
    """`tool_call` (create) с locations + rawInput — байт-в-байт прежний."""
    expected = _load("tool_call_create")
    tool_call_handler = ToolCallHandler()
    actual = _actual(
        tool_call_handler.build_tool_call_notification(
            session_id="sess_001",
            tool_call_id="call_001",
            title="Read file",
            kind="read",
            locations=[{"path": "/tmp/README.md"}],
            raw_input={"path": "/tmp/README.md"},
        ),
    )
    assert actual == expected


def test_tool_call_update_in_progress_wire_format() -> None:
    """`tool_call_update` со статусом in_progress — байт-в-байт прежний."""
    expected = _load("tool_call_update_in_progress")
    tool_call_handler = ToolCallHandler()
    actual = _actual(
        tool_call_handler.build_tool_update_notification(
            session_id="sess_001",
            tool_call_id="call_001",
            status="in_progress",
        ),
    )
    assert actual == expected


def test_tool_call_update_completed_wire_format() -> None:
    """`tool_call_update` со статусом completed + content — байт-в-байт прежний."""
    expected = _load("tool_call_update_completed")
    tool_call_handler = ToolCallHandler()
    actual = _actual(
        tool_call_handler.build_tool_update_notification(
            session_id="sess_001",
            tool_call_id="call_001",
            status="completed",
            content=[
                {"type": "content", "content": {"type": "text", "text": "file body"}},
            ],
        ),
    )
    assert actual == expected


def test_fallback_notification_wire_format() -> None:
    """Fallback notification при недоступной стратегии — байт-в-байт прежний."""
    expected = _load("fallback_notification")
    actual = _actual(
        StrategyDispatcher.build_fallback_notification(
            session_id="sess_001",
            requested="hierarchical",
            actual="single",
            reason="agent not registered",
        ),
    )
    assert actual == expected


@pytest.mark.parametrize(
    "name",
    [
        "agent_message_chunk",
        "plan",
        "tool_call_create",
        "tool_call_update_in_progress",
        "tool_call_update_completed",
        "fallback_notification",
    ],
)
def test_golden_snapshot_is_well_formed_jsonrpc(name: str) -> None:
    """Каждый снимок — валидный JSON-RPC 2.0 notification session/update."""
    payload = _load(name)
    assert payload["jsonrpc"] == "2.0", f"{name}: must be JSON-RPC 2.0"
    assert payload.get("id") is None, f"{name}: notifications have no id"
    assert payload["method"] == "session/update", f"{name}: method must be session/update"
    assert "sessionId" in payload["params"], f"{name}: missing sessionId"
    assert "update" in payload["params"], f"{name}: missing update"
    assert "sessionUpdate" in payload["params"]["update"], (
        f"{name}: missing sessionUpdate discriminator"
    )
