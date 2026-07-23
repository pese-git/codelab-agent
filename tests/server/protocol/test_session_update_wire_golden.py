"""Golden-фикстуры wire-формата `session/update` (write-фаза, гейт D0.1).

Фиксирует байт/структуру исходящих notification'ов ДО доменной миграции
(ADR-006). Любой шаг write-фазы (особенно D4 — перевод turn-пути на агрегат)
обязан сохранить эти payload'ы байт-в-байт. Ломается тест → ломается контракт wire.

Покрыты все 4 типа: agent_message_chunk, plan, tool_call, tool_call_update —
и полная, и минимальная (optional-поля опущены) формы.
"""

from codelab.server.protocol.handlers.pipeline.stages.agent_loop.updates import SessionUpdateSink
from codelab.server.protocol.handlers.plan_builder import PlanBuilder
from codelab.server.protocol.handlers.tool_call_handler import ToolCallHandler

SESSION_ID = "sess_golden"


class TestAgentMessageChunkWire:
    def test_agent_message_chunk(self) -> None:
        msg = SessionUpdateSink.build_agent_message_chunk(SESSION_ID, "hello world")
        assert msg.method == "session/update"
        assert msg.params == {
            "sessionId": SESSION_ID,
            "update": {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": "hello world"},
            },
        }


class TestPlanWire:
    def test_plan_entries_passthrough(self) -> None:
        entries = [
            {"content": "step 1", "priority": "high", "status": "pending"},
            {"content": "step 2", "priority": "medium", "status": "in_progress"},
        ]
        msg = PlanBuilder().build_plan_notification(SESSION_ID, entries)
        assert msg.method == "session/update"
        assert msg.params == {
            "sessionId": SESSION_ID,
            "update": {"sessionUpdate": "plan", "entries": entries},
        }


class TestToolCallWire:
    def test_tool_call_minimal(self) -> None:
        """Без optional — locations/rawInput ОПУЩЕНЫ (не null)."""
        msg = ToolCallHandler().build_tool_call_notification(
            session_id=SESSION_ID,
            tool_call_id="call_1",
            title="Read file",
            kind="read",
        )
        assert msg.method == "session/update"
        assert msg.params == {
            "sessionId": SESSION_ID,
            "update": {
                "sessionUpdate": "tool_call",
                "toolCallId": "call_1",
                "title": "Read file",
                "kind": "read",
                "status": "pending",
            },
        }

    def test_tool_call_full(self) -> None:
        locations = [{"path": "/a/b.py"}]
        raw_input = {"path": "/a/b.py"}
        msg = ToolCallHandler().build_tool_call_notification(
            session_id=SESSION_ID,
            tool_call_id="call_1",
            title="Read file",
            kind="read",
            locations=locations,
            raw_input=raw_input,
        )
        assert msg.params == {
            "sessionId": SESSION_ID,
            "update": {
                "sessionUpdate": "tool_call",
                "toolCallId": "call_1",
                "title": "Read file",
                "kind": "read",
                "status": "pending",
                "locations": locations,
                "rawInput": raw_input,
            },
        }


class TestToolCallUpdateWire:
    def test_tool_call_update_minimal(self) -> None:
        msg = ToolCallHandler().build_tool_update_notification(
            session_id=SESSION_ID,
            tool_call_id="call_1",
            status="completed",
        )
        assert msg.method == "session/update"
        assert msg.params == {
            "sessionId": SESSION_ID,
            "update": {
                "sessionUpdate": "tool_call_update",
                "toolCallId": "call_1",
                "status": "completed",
            },
        }

    def test_tool_call_update_full(self) -> None:
        content = [{"type": "content", "content": {"type": "text", "text": "result"}}]
        raw_output = {"exit_code": 0}
        locations = [{"path": "/a/b.py"}]
        msg = ToolCallHandler().build_tool_update_notification(
            session_id=SESSION_ID,
            tool_call_id="call_1",
            status="completed",
            content=content,
            locations=locations,
            raw_output=raw_output,
        )
        assert msg.params == {
            "sessionId": SESSION_ID,
            "update": {
                "sessionUpdate": "tool_call_update",
                "toolCallId": "call_1",
                "status": "completed",
                "content": content,
                "locations": locations,
                "rawOutput": raw_output,
            },
        }
