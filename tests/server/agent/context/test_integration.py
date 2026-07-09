"""Интеграционный тест: PayloadEnvelope проходит через ExecutionEngine."""

from unittest.mock import MagicMock

import pytest

from codelab.server.agent.context.models import ContextConfig, PayloadEnvelope
from codelab.server.agent.execution_engine import ExecutionEngine
from codelab.server.llm.models import LLMMessage


def _make_session(session_id="test-session"):
    session = MagicMock()
    session.session_id = session_id
    session.history = [
        {"role": "system", "text": "You are a helpful assistant."},
        {"role": "user", "text": "Hello"},
        {"role": "assistant", "text": "Hi there!"},
    ]
    session.runtime_capabilities = MagicMock()
    session.config_values = {"model": "test-model"}
    return session


def _make_tool_registry():
    registry = MagicMock()
    registry.get_available_tools.return_value = []
    return registry


class TestPayloadEnvelopeIntegration:
    """PayloadEnvelope интегрирован в ExecutionEngine."""

    @pytest.mark.asyncio
    async def test_build_context_uses_payload_envelope_internally(self):
        """build_context() внутренне использует PayloadEnvelope."""
        engine = ExecutionEngine(
            tool_registry=_make_tool_registry(),
        )
        session = _make_session()

        context = await engine.build_context(
            session=session,
            prompt="Test prompt",
            system_prompt="System",
        )

        assert context.conversation_history is not None
        assert len(context.conversation_history) > 0

    @pytest.mark.asyncio
    async def test_build_envelope_separates_system_to_baseline(self):
        """_build_envelope() помещает system в baseline."""
        history = [
            LLMMessage(role="system", content="System prompt"),
            LLMMessage(role="user", content="Question"),
            LLMMessage(role="assistant", content="Answer"),
        ]

        envelope = ExecutionEngine._build_envelope(history)

        assert len(envelope.baseline) == 1
        assert envelope.baseline[0].role == "system"
        assert len(envelope.tail) == 2
        assert envelope.tail[0].role == "user"

    @pytest.mark.asyncio
    async def test_build_envelope_no_system_all_tail(self):
        """_build_envelope() без system — всё в tail."""
        history = [
            LLMMessage(role="user", content="Question"),
            LLMMessage(role="assistant", content="Answer"),
        ]

        envelope = ExecutionEngine._build_envelope(history)

        assert len(envelope.baseline) == 0
        assert len(envelope.tail) == 2

    @pytest.mark.asyncio
    async def test_build_envelope_system_after_tail_goes_to_tail(self):
        """_build_envelope() system после non-system → в tail."""
        history = [
            LLMMessage(role="user", content="Question"),
            LLMMessage(role="system", content="Late system"),
        ]

        envelope = ExecutionEngine._build_envelope(history)

        assert len(envelope.baseline) == 0
        assert len(envelope.tail) == 2

    @pytest.mark.asyncio
    async def test_to_messages_roundtrip(self):
        """to_messages() восстанавливает плоский список из envelope."""
        history = [
            LLMMessage(role="system", content="System"),
            LLMMessage(role="user", content="Q1"),
            LLMMessage(role="assistant", content="A1"),
            LLMMessage(role="user", content="Q2"),
        ]

        envelope = ExecutionEngine._build_envelope(history)
        restored = envelope.to_messages()

        assert len(restored) == 4
        assert restored[0].role == "system"
        assert restored[1].role == "user"
        assert restored[1].content == "Q1"
        assert restored[2].role == "assistant"
        assert restored[3].content == "Q2"

    @pytest.mark.asyncio
    async def test_context_config_passed_to_engine(self):
        """ContextConfig передаётся в ExecutionEngine."""
        config = ContextConfig(enabled=True, max_context_tokens=64000)
        engine = ExecutionEngine(
            tool_registry=_make_tool_registry(),
            context_config=config,
        )

        assert engine.context_config.enabled is True
        assert engine.context_config.max_context_tokens == 64000

    @pytest.mark.asyncio
    async def test_default_context_config(self):
        """ExecutionEngine создаёт дефолтный ContextConfig."""
        engine = ExecutionEngine(
            tool_registry=_make_tool_registry(),
        )

        assert engine.context_config.enabled is False
        assert engine.context_config.max_context_tokens == 128000

    @pytest.mark.asyncio
    async def test_ensure_envelope_fits_no_compactor(self):
        """_ensure_envelope_fits() без compactor возвращает envelope."""
        engine = ExecutionEngine(
            tool_registry=_make_tool_registry(),
            compactor=None,
        )
        envelope = PayloadEnvelope(
            baseline=[LLMMessage(role="system", content="Sys")],
            tail=[LLMMessage(role="user", content="Hi")],
        )

        result = await engine._ensure_envelope_fits(envelope)

        assert result is envelope
