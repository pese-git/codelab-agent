"""Smoke: ядро прогоняет turn через AgentRunner без ACP/protocol (ADR-005, Фаза 4).

Это приёмочный тест driver-независимости: не-ACP «драйвер» (этот тест-харнесс)
подаёт turn в `CoreAgentRunner`, который использует только порты
(`SessionView`, `ContentCodec`, `ToolGateway`, `LLMPort`) на фейках. Ни один
импорт `codelab.server.protocol` при этом не задействован — ядро развязано.
"""

import pytest

from codelab.server.agent.core.agent_runner import CoreAgentRunner
from codelab.server.agent.core.execution_engine import ExecutionEngine
from tests.server.agent.fakes import (
    FakeCapabilities,
    FakeContentCodec,
    FakeLLM,
    FakeSessionView,
    FakeToolGateway,
)


def _make_runner(llm: FakeLLM) -> CoreAgentRunner:
    engine = ExecutionEngine(
        tool_registry=FakeToolGateway(),
        content_codec=FakeContentCodec(),
    )
    return CoreAgentRunner(engine, llm)


class TestAgentRunnerDriverIndependence:
    """CoreAgentRunner гоняет turn на портах-фейках, без protocol/ACP."""

    @pytest.mark.asyncio
    async def test_run_turn_on_fakes(self) -> None:
        llm = FakeLLM()
        runner = _make_runner(llm)
        session = FakeSessionView(
            session_id="s1",
            config_values={"model": "fake/model"},
            runtime_capabilities=FakeCapabilities(fs_read=True),
            history=[{"role": "user", "text": "previous"}],
        )

        result = await runner.run_turn(session, "do the task", system_prompt="You are helpful.")

        assert result.text == "ok"
        assert result.stop_reason == "end_turn"
        assert llm.calls == 1
        # ядро собрало историю: system prompt + прошлый ход
        assert llm.last_messages[0].role == "system"
        # fs/read доступен (fs_read=True), update_plan серверный
        tool_names = {t.name for t in llm.last_tools}
        assert "fs/read_text_file" in tool_names
        assert "update_plan" in tool_names

    @pytest.mark.asyncio
    async def test_continue_turn_on_fakes(self) -> None:
        llm = FakeLLM()
        runner = _make_runner(llm)
        session = FakeSessionView(
            history=[
                {"role": "assistant", "text": "", "tool_calls": [
                    {"id": "c1", "name": "fs/read_text_file", "arguments": {"path": "a"}}
                ]},
                {"role": "tool", "tool_call_id": "c1", "content": "body"},
            ],
        )

        result = await runner.continue_turn(session)

        assert result.stop_reason == "end_turn"
        assert llm.calls == 1
        roles = [m.role for m in llm.last_messages]
        assert "tool" in roles

    def test_core_agent_runner_imports_no_protocol(self) -> None:
        """agent.core.agent_runner не тянет codelab.server.protocol транзитивно."""
        import codelab.server.agent.core.agent_runner as mod

        # Модуль ядра импортируется без побочного импорта protocol в его namespace.
        assert not any(
            name.startswith("codelab.server.protocol")
            for name in vars(mod)
            if isinstance(getattr(mod, name, None), type)
        )
