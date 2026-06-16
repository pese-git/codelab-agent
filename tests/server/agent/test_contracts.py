"""Тесты для контрактов мультиагентной шины событий."""

import time
from dataclasses import FrozenInstanceError, is_dataclass

import pytest

from codelab.server.agent.contracts.base import (
    AgentBusError,
    AgentDispatchError,
    AgentListChanged,
    AgentNotFoundError,
    AgentRegistered,
    AgentRequest,
    AgentResponse,
    AgentResult,
    AgentUnregistered,
    BroadcastPartialFailure,
    ChoreographyAnswer,
    ContextBroadcast,
    DomainEvent,
    TokenUsage,
    ToolCall,
)


def _assert_frozen(obj, attr_name, value):
    """Helper: проверяет что присвоение вызывает FrozenInstanceError."""
    with pytest.raises(FrozenInstanceError):
        setattr(obj, attr_name, value)


# ─────────────────────────────────────────────
# DomainEvent tests
# ─────────────────────────────────────────────


class TestDomainEvent:
    def test_is_frozen(self):
        event = DomainEvent(session_id="test")
        _assert_frozen(event, "session_id", "changed")

    def test_has_timestamp(self):
        before = time.time()
        event = DomainEvent(session_id="test")
        after = time.time()
        assert before <= event.timestamp <= after

    def test_has_session_id(self):
        event = DomainEvent(session_id="sess_123")
        assert event.session_id == "sess_123"

    def test_default_session_id(self):
        event = DomainEvent()
        assert event.session_id == ""

    def test_is_dataclass(self):
        assert is_dataclass(DomainEvent)


# ─────────────────────────────────────────────
# TokenUsage tests
# ─────────────────────────────────────────────


class TestTokenUsage:
    def test_is_frozen(self):
        usage = TokenUsage(input_tokens=10, output_tokens=20, total_tokens=30)
        _assert_frozen(usage, "input_tokens", 99)

    def test_fields(self):
        usage = TokenUsage(input_tokens=10, output_tokens=20, total_tokens=30)
        assert usage.input_tokens == 10
        assert usage.output_tokens == 20
        assert usage.total_tokens == 30

    def test_is_dataclass(self):
        assert is_dataclass(TokenUsage)


# ─────────────────────────────────────────────
# ToolCall tests
# ─────────────────────────────────────────────


class TestToolCall:
    def test_is_frozen(self):
        tc = ToolCall(id="tc_1", name="read_file", arguments={"path": "test.py"})
        _assert_frozen(tc, "id", "changed")

    def test_fields(self):
        tc = ToolCall(id="tc_1", name="read_file", arguments={"path": "test.py"})
        assert tc.id == "tc_1"
        assert tc.name == "read_file"
        assert tc.arguments == {"path": "test.py"}

    def test_default_arguments(self):
        tc = ToolCall(id="tc_1", name="read_file")
        assert tc.arguments == {}

    def test_is_dataclass(self):
        assert is_dataclass(ToolCall)


# ─────────────────────────────────────────────
# AgentRequest tests
# ─────────────────────────────────────────────


class TestAgentRequest:
    def test_is_frozen(self):
        req = AgentRequest(
            target_agent="coder",
            session_id="sess_1",
            correlation_id="corr_1",
        )
        _assert_frozen(req, "target_agent", "changed")

    def test_inherits_domain_event(self):
        req = AgentRequest(target_agent="coder", session_id="sess_1")
        assert isinstance(req, DomainEvent)

    def test_fields(self):
        req = AgentRequest(
            target_agent="coder",
            messages=[],
            tools=[],
            correlation_id="corr_1",
            session_id="sess_1",
        )
        assert req.target_agent == "coder"
        assert req.correlation_id == "corr_1"
        assert req.session_id == "sess_1"
        assert req.messages == []
        assert req.tools == []

    def test_has_timestamp_from_domain_event(self):
        req = AgentRequest(target_agent="coder", session_id="sess_1")
        assert hasattr(req, "timestamp")

    def test_is_dataclass(self):
        assert is_dataclass(AgentRequest)


# ─────────────────────────────────────────────
# AgentResult tests
# ─────────────────────────────────────────────


class TestAgentResult:
    def test_is_frozen(self):
        result = AgentResult(text="hello", agent_name="coder")
        _assert_frozen(result, "text", "changed")

    def test_fields(self):
        usage = TokenUsage(10, 20, 30)
        tc = ToolCall(id="tc_1", name="read_file")
        result = AgentResult(
            text="hello",
            tool_calls=[tc],
            usage=usage,
            stop_reason="end_turn",
            agent_name="coder",
        )
        assert result.text == "hello"
        assert result.tool_calls == [tc]
        assert result.usage == usage
        assert result.stop_reason == "end_turn"
        assert result.agent_name == "coder"
        assert result.error is None

    def test_error_field(self):
        result = AgentResult(text="", error="something failed")
        assert result.error == "something failed"

    def test_defaults(self):
        result = AgentResult()
        assert result.text == ""
        assert result.tool_calls == []
        assert result.stop_reason == ""
        assert result.agent_name == ""
        assert result.error is None

    def test_is_dataclass(self):
        assert is_dataclass(AgentResult)


# ─────────────────────────────────────────────
# AgentResponse tests
# ─────────────────────────────────────────────


class TestAgentResponse:
    def test_is_frozen(self):
        resp = AgentResponse(request_id="req_1", agent_name="coder")
        _assert_frozen(resp, "request_id", "changed")

    def test_inherits_domain_event(self):
        resp = AgentResponse(request_id="req_1", session_id="sess_1")
        assert isinstance(resp, DomainEvent)

    def test_fields(self):
        usage = TokenUsage(10, 20, 30)
        tc = ToolCall(id="tc_1", name="read_file")
        resp = AgentResponse(
            request_id="req_1",
            text="hello",
            tool_calls=[tc],
            usage=usage,
            stop_reason="end_turn",
            agent_name="coder",
            session_id="sess_1",
        )
        assert resp.request_id == "req_1"
        assert resp.text == "hello"
        assert resp.tool_calls == [tc]
        assert resp.usage == usage
        assert resp.stop_reason == "end_turn"
        assert resp.agent_name == "coder"

    def test_has_timestamp_from_domain_event(self):
        resp = AgentResponse(request_id="req_1", session_id="sess_1")
        assert hasattr(resp, "timestamp")

    def test_is_dataclass(self):
        assert is_dataclass(AgentResponse)


# ─────────────────────────────────────────────
# ContextBroadcast tests
# ─────────────────────────────────────────────


class TestContextBroadcast:
    def test_is_frozen(self):
        bc = ContextBroadcast(session_id="sess_1", correlation_id="corr_1")
        _assert_frozen(bc, "step", 99)

    def test_inherits_domain_event(self):
        bc = ContextBroadcast(session_id="sess_1")
        assert isinstance(bc, DomainEvent)

    def test_fields(self):
        bc = ContextBroadcast(
            context=[],
            available_agents=["coder", "reviewer"],
            step=1,
            correlation_id="corr_1",
            session_id="sess_1",
        )
        assert bc.context == []
        assert bc.available_agents == ["coder", "reviewer"]
        assert bc.step == 1
        assert bc.correlation_id == "corr_1"

    def test_has_timestamp(self):
        bc = ContextBroadcast(session_id="sess_1")
        assert hasattr(bc, "timestamp")

    def test_is_dataclass(self):
        assert is_dataclass(ContextBroadcast)


# ─────────────────────────────────────────────
# ChoreographyAnswer tests
# ─────────────────────────────────────────────


class TestChoreographyAnswer:
    def test_is_frozen(self):
        ans = ChoreographyAnswer(agent_name="coder")
        _assert_frozen(ans, "action_taken", True)

    def test_inherits_domain_event(self):
        ans = ChoreographyAnswer(agent_name="coder", session_id="sess_1")
        assert isinstance(ans, DomainEvent)

    def test_fields(self):
        usage = TokenUsage(5, 10, 15)
        ans = ChoreographyAnswer(
            agent_name="coder",
            action_taken=True,
            reasoning="I will handle this",
            output="done",
            status_signal="completed",
            usage=usage,
            session_id="sess_1",
        )
        assert ans.agent_name == "coder"
        assert ans.action_taken is True
        assert ans.reasoning == "I will handle this"
        assert ans.output == "done"
        assert ans.status_signal == "completed"
        assert ans.usage == usage

    def test_default_values(self):
        ans = ChoreographyAnswer(agent_name="coder", session_id="sess_1")
        assert ans.action_taken is False
        assert ans.reasoning == ""
        assert ans.output is None
        assert ans.status_signal == "continue"

    def test_is_dataclass(self):
        assert is_dataclass(ChoreographyAnswer)


# ─────────────────────────────────────────────
# Lifecycle events tests
# ─────────────────────────────────────────────


class TestAgentRegistered:
    def test_is_frozen(self):
        ev = AgentRegistered(agent_name="coder", session_id="sess_1")
        _assert_frozen(ev, "agent_name", "changed")

    def test_inherits_domain_event(self):
        ev = AgentRegistered(agent_name="coder", session_id="sess_1")
        assert isinstance(ev, DomainEvent)

    def test_fields(self):
        ev = AgentRegistered(
            agent_name="coder",
            capabilities={"tools": ["read_file", "write_file"]},
            mode="single",
            session_id="sess_1",
        )
        assert ev.agent_name == "coder"
        assert ev.capabilities == {"tools": ["read_file", "write_file"]}
        assert ev.mode == "single"

    def test_is_dataclass(self):
        assert is_dataclass(AgentRegistered)


class TestAgentUnregistered:
    def test_is_frozen(self):
        ev = AgentUnregistered(agent_name="coder", session_id="sess_1")
        _assert_frozen(ev, "agent_name", "changed")

    def test_inherits_domain_event(self):
        ev = AgentUnregistered(agent_name="coder", session_id="sess_1")
        assert isinstance(ev, DomainEvent)

    def test_fields(self):
        ev = AgentUnregistered(agent_name="coder", session_id="sess_1")
        assert ev.agent_name == "coder"

    def test_is_dataclass(self):
        assert is_dataclass(AgentUnregistered)


class TestAgentListChanged:
    def test_is_frozen(self):
        ev = AgentListChanged(session_id="sess_1")
        _assert_frozen(ev, "added", ["new"])

    def test_inherits_domain_event(self):
        ev = AgentListChanged(session_id="sess_1")
        assert isinstance(ev, DomainEvent)

    def test_fields(self):
        ev = AgentListChanged(
            added=["coder"],
            removed=["reviewer"],
            session_id="sess_1",
        )
        assert ev.added == ["coder"]
        assert ev.removed == ["reviewer"]

    def test_defaults(self):
        ev = AgentListChanged(session_id="sess_1")
        assert ev.added == []
        assert ev.removed == []

    def test_is_dataclass(self):
        assert is_dataclass(AgentListChanged)


# ─────────────────────────────────────────────
# Exception tests
# ─────────────────────────────────────────────


class TestAgentBusError:
    def test_is_exception(self):
        assert issubclass(AgentBusError, Exception)

    def test_can_be_raised(self):
        with pytest.raises(AgentBusError):
            raise AgentBusError("test error")

    def test_message(self):
        err = AgentBusError("something went wrong")
        assert str(err) == "something went wrong"


class TestAgentNotFoundError:
    def test_inherits_agent_bus_error(self):
        assert issubclass(AgentNotFoundError, AgentBusError)

    def test_can_be_raised(self):
        with pytest.raises(AgentNotFoundError):
            raise AgentNotFoundError("agent not found")

    def test_message(self):
        err = AgentNotFoundError("agent 'coder' not found")
        assert str(err) == "agent 'coder' not found"


class TestAgentDispatchError:
    def test_inherits_agent_bus_error(self):
        assert issubclass(AgentDispatchError, AgentBusError)

    def test_can_be_raised(self):
        with pytest.raises(AgentDispatchError):
            raise AgentDispatchError("dispatch failed")


class TestBroadcastPartialFailure:
    def test_inherits_agent_bus_error(self):
        assert issubclass(BroadcastPartialFailure, AgentBusError)

    def test_has_failed_agents(self):
        err = BroadcastPartialFailure("partial failure", ["agent_a", "agent_b"])
        assert err.failed_agents == ["agent_a", "agent_b"]

    def test_message(self):
        err = BroadcastPartialFailure("2 agents failed", ["a", "b"])
        assert str(err) == "2 agents failed"

    def test_can_be_raised(self):
        with pytest.raises(BroadcastPartialFailure) as exc_info:
            raise BroadcastPartialFailure("fail", ["x"])
        assert exc_info.value.failed_agents == ["x"]
