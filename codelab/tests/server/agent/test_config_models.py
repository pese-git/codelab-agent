"""Тесты для Pydantic моделей конфигурации агентов."""

import pytest

from codelab.server.agent.config.models import (
    AgentMarkdownConfig,
    AgentMode,
    AgentPermission,
    AgentsGlobalConfig,
    AgentTOMLConfig,
    ResolvedAgent,
    SessionMetrics,
)


class TestAgentMode:
    def test_primary(self):
        assert AgentMode.PRIMARY == "primary"

    def test_subagent(self):
        assert AgentMode.SUBAGENT == "subagent"

    def test_orchestrator(self):
        assert AgentMode.ORCHESTRATOR == "orchestrator"

    def test_from_string(self):
        assert AgentMode("primary") == AgentMode.PRIMARY


class TestAgentPermission:
    def test_defaults(self):
        p = AgentPermission()
        assert p.edit is False
        assert p.bash is False
        assert p.webfetch is False
        assert p.task is False

    def test_custom(self):
        p = AgentPermission(edit=True, bash=True)
        assert p.edit is True
        assert p.bash is True
        assert p.webfetch is False

    def test_frozen(self):
        p = AgentPermission()
        with pytest.raises(Exception):
            p.edit = True


class TestAgentTOMLConfig:
    def test_defaults(self):
        cfg = AgentTOMLConfig()
        assert cfg.enabled is True
        assert cfg.mode == AgentMode.PRIMARY
        assert cfg.priority == 99
        assert cfg.model is None
        assert cfg.tools == []

    def test_custom(self):
        cfg = AgentTOMLConfig(
            enabled=False,
            mode=AgentMode.SUBAGENT,
            model="openai/gpt-4o-mini",
            tools=["read_file"],
        )
        assert cfg.enabled is False
        assert cfg.mode == AgentMode.SUBAGENT
        assert cfg.model == "openai/gpt-4o-mini"

    def test_extra_fields(self):
        cfg = AgentTOMLConfig(custom_param="value")
        assert cfg.model_extra.get("custom_param") == "value"


class TestAgentsGlobalConfig:
    def test_defaults(self):
        cfg = AgentsGlobalConfig()
        assert cfg.mode == AgentMode.PRIMARY
        assert cfg.default_model == "openai/gpt-4o"
        assert cfg.max_steps == 10
        assert cfg.slicer_model == "openai/gpt-4o-mini"
        assert cfg.max_sliced_tokens == 120
        assert cfg.slicer_skip_threshold == 300
        assert cfg.debug is False
        assert cfg.definitions == {}

    def test_custom(self):
        cfg = AgentsGlobalConfig(
            default_model="anthropic/claude-3.5",
            max_steps=20,
            debug=True,
        )
        assert cfg.default_model == "anthropic/claude-3.5"
        assert cfg.max_steps == 20
        assert cfg.debug is True


class TestAgentMarkdownConfig:
    def test_defaults(self):
        cfg = AgentMarkdownConfig()
        assert cfg.name == ""
        assert cfg.enabled is True
        assert cfg.mode == AgentMode.PRIMARY
        assert cfg.priority == 99
        assert cfg.prompt == ""

    def test_custom(self):
        cfg = AgentMarkdownConfig(
            name="coder",
            mode=AgentMode.PRIMARY,
            prompt="You are a coding assistant.",
        )
        assert cfg.name == "coder"
        assert cfg.prompt == "You are a coding assistant."

    def test_extra_fields(self):
        cfg = AgentMarkdownConfig(custom_key="value")
        assert cfg.model_extra.get("custom_key") == "value"


class TestResolvedAgent:
    def test_defaults(self):
        agent = ResolvedAgent(name="test")
        assert agent.name == "test"
        assert agent.enabled is True
        assert agent.mode == AgentMode.PRIMARY
        assert agent.priority == 99
        assert agent.model == ""
        assert agent.temperature == 0.0
        assert agent.tools == []
        assert agent.additional_params == {}

    def test_full_config(self):
        agent = ResolvedAgent(
            name="coder",
            mode=AgentMode.PRIMARY,
            model="openai/gpt-4o",
            temperature=0.7,
            max_steps=15,
            tools=["read_file", "write_file"],
            prompt="You are a coder.",
            additional_params={"custom": "value"},
        )
        assert agent.name == "coder"
        assert agent.model == "openai/gpt-4o"
        assert agent.temperature == 0.7
        assert agent.max_steps == 15
        assert len(agent.tools) == 2
        assert agent.additional_params["custom"] == "value"


class TestSessionMetrics:
    def test_defaults(self):
        m = SessionMetrics()
        assert m.total_time_sec == 0.0
        assert m.total_llm_calls == 0
        assert m.input_tokens == 0
        assert m.output_tokens == 0
        assert m.estimated_cost_usd == 0.0
        assert m.task_success is None
        assert m.agent_breakdown == {}

    def test_custom(self):
        m = SessionMetrics(
            total_time_sec=120.5,
            total_llm_calls=10,
            input_tokens=5000,
            output_tokens=2000,
            task_success=True,
            agent_breakdown={"coder": {"calls": 5}},
        )
        assert m.total_time_sec == 120.5
        assert m.total_llm_calls == 10
        assert m.task_success is True
