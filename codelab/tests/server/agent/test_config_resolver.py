"""Тесты для AgentConfigResolver."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from codelab.server.agent.config.loader import AgentConfigLoader
from codelab.server.agent.config.models import (
    AgentMarkdownConfig,
    AgentMode,
    AgentsGlobalConfig,
)
from codelab.server.agent.config.resolver import AgentConfigResolver


@pytest.fixture
def loader():
    return AgentConfigLoader()


@pytest.fixture
def global_config():
    return AgentsGlobalConfig(
        default_model="openai/gpt-4o",
        max_steps=20,
        debug=True,
    )


@pytest.fixture
def resolver(loader, global_config):
    return AgentConfigResolver(loader=loader, global_config=global_config)


class TestResolveDefaults:
    """3.9 — разрешение с defaults."""

    def test_model_from_global(self, loader, global_config):
        resolver = AgentConfigResolver(
            loader=loader, global_config=global_config
        )
        md = AgentMarkdownConfig(name="coder", model=None)
        resolved = resolver._resolve("coder", md)
        assert resolved.model == "openai/gpt-4o"

    def test_model_from_agent(self, loader, global_config):
        resolver = AgentConfigResolver(
            loader=loader, global_config=global_config
        )
        md = AgentMarkdownConfig(name="coder", model="anthropic/claude-3")
        resolved = resolver._resolve("coder", md)
        assert resolved.model == "anthropic/claude-3"

    def test_temperature_default(self, loader, global_config):
        resolver = AgentConfigResolver(
            loader=loader, global_config=global_config
        )
        md = AgentMarkdownConfig(name="coder", temperature=None)
        resolved = resolver._resolve("coder", md)
        assert resolved.temperature == 0.0

    def test_temperature_from_agent(self, loader, global_config):
        resolver = AgentConfigResolver(
            loader=loader, global_config=global_config
        )
        md = AgentMarkdownConfig(name="coder", temperature=0.7)
        resolved = resolver._resolve("coder", md)
        assert resolved.temperature == 0.7

    def test_max_steps_from_global(self, loader, global_config):
        resolver = AgentConfigResolver(
            loader=loader, global_config=global_config
        )
        md = AgentMarkdownConfig(name="coder", max_steps=None)
        resolved = resolver._resolve("coder", md)
        assert resolved.max_steps == 20

    def test_max_steps_from_agent(self, loader, global_config):
        resolver = AgentConfigResolver(
            loader=loader, global_config=global_config
        )
        md = AgentMarkdownConfig(name="coder", max_steps=50)
        resolved = resolver._resolve("coder", md)
        assert resolved.max_steps == 50

    def test_prompt_from_markdown(self, loader, global_config):
        resolver = AgentConfigResolver(
            loader=loader, global_config=global_config
        )
        md = AgentMarkdownConfig(name="coder", prompt="You are a coder.")
        resolved = resolver._resolve("coder", md)
        assert resolved.prompt == "You are a coder."

    def test_additional_params(self, loader, global_config):
        resolver = AgentConfigResolver(
            loader=loader, global_config=global_config
        )
        md = AgentMarkdownConfig(
            name="coder", custom_param="value", another=42
        )
        resolved = resolver._resolve("coder", md)
        assert resolved.additional_params.get("custom_param") == "value"
        assert resolved.additional_params.get("another") == 42


class TestDisabledAgents:
    """3.10 — отключённые агенты исключены."""

    def test_disabled_agent_excluded(self, loader, global_config):
        resolver = AgentConfigResolver(
            loader=loader, global_config=global_config
        )

        # Mock load_all
        loader.load_all = MagicMock(
            return_value={
                "coder": AgentMarkdownConfig(name="coder", enabled=True),
                "disabled": AgentMarkdownConfig(name="disabled", enabled=False),
            }
        )

        result = resolver.resolve_all()
        assert "coder" in result
        assert "disabled" not in result

    def test_all_enabled(self, loader, global_config):
        resolver = AgentConfigResolver(
            loader=loader, global_config=global_config
        )

        loader.load_all = MagicMock(
            return_value={
                "coder": AgentMarkdownConfig(name="coder", enabled=True),
                "reviewer": AgentMarkdownConfig(name="reviewer", enabled=True),
            }
        )

        result = resolver.resolve_all()
        assert len(result) == 2
        assert "coder" in result
        assert "reviewer" in result
