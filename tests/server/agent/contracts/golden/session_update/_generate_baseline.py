"""Генерация golden-снимков wire-формата session/update.

Запускается вручную при создании/обновлении baseline:
    uv run python tests/server/agent/contracts/golden/session_update/_generate_baseline.py

Каждый сценарий вызывает текущий production-код
(`SessionUpdateSink.build_*`, `ToolCallHandler.build_*_notification`,
`StrategyDispatcher.build_fallback_notification`, `PlanBuilder.build_plan_notification`)
и сохраняет результат `to_dict() -> json.dumps(sort_keys=True)` в
соответствующий файл `*.json`.

После генерации ручной review diff + commit. CI проверяет байт-идентичность.
"""

from __future__ import annotations

import json
from pathlib import Path

from codelab.server.agent.strategies.dispatcher import StrategyDispatcher
from codelab.server.protocol.handlers.pipeline.stages.agent_loop.updates import (
    SessionUpdateSink,
)
from codelab.server.protocol.handlers.plan_builder import PlanBuilder
from codelab.server.protocol.handlers.tool_call_handler import ToolCallHandler

OUT_DIR = Path(__file__).parent


def _dump(name: str, msg) -> None:
    """Сериализовать ACPMessage в стабильный JSON (sort_keys, ensure_ascii=False)."""
    payload = msg.to_dict()
    path = OUT_DIR / f"{name}.json"
    path.write_text(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def generate() -> None:
    """Сгенерировать все golden-снимки текущим кодом."""
    # 1. agent_message_chunk (текст ответа)
    _dump(
        "agent_message_chunk",
        SessionUpdateSink.build_agent_message_chunk(
            session_id="sess_001",
            text="I'll read the file first.",
        ),
    )

    # 2. plan (multi-step)
    plan_builder = PlanBuilder()
    _dump(
        "plan",
        plan_builder.build_plan_notification(
            session_id="sess_001",
            plan_entries=[
                {"content": "Read README.md", "priority": "high", "status": "in_progress"},
                {"content": "Summarize architecture", "priority": "medium", "status": "pending"},
            ],
        ),
    )

    # 3. tool_call (create)
    tool_call_handler = ToolCallHandler()
    _dump(
        "tool_call_create",
        tool_call_handler.build_tool_call_notification(
            session_id="sess_001",
            tool_call_id="call_001",
            title="Read file",
            kind="read",
            locations=[{"path": "/tmp/README.md"}],
            raw_input={"path": "/tmp/README.md"},
        ),
    )

    # 4. tool_call_update (in_progress)
    _dump(
        "tool_call_update_in_progress",
        tool_call_handler.build_tool_update_notification(
            session_id="sess_001",
            tool_call_id="call_001",
            status="in_progress",
        ),
    )

    # 5. tool_call_update (completed, with content)
    _dump(
        "tool_call_update_completed",
        tool_call_handler.build_tool_update_notification(
            session_id="sess_001",
            tool_call_id="call_001",
            status="completed",
            content=[{"type": "content", "content": {"type": "text", "text": "file body"}}],
        ),
    )

    # 6. fallback notification (стратегия недоступна)
    _dump(
        "fallback_notification",
        StrategyDispatcher.build_fallback_notification(
            session_id="sess_001",
            requested="hierarchical",
            actual="single",
            reason="agent not registered",
        ),
    )


if __name__ == "__main__":
    generate()
    print(f"Generated {len(list(OUT_DIR.glob('*.json')))} golden snapshots in {OUT_DIR}")
