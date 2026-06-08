"""Тесты для AgentRegistry."""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codelab.server.agent.config.models import (
    AgentMarkdownConfig,
    AgentMode,
    AgentsGlobalConfig,
    ResolvedAgent,
)
from codelab.server.agent.event_bus.bus import AgentEventBus, RetryConfig
from codelab.server.agent.registry import AgentRegistry


@pytest.fixture
def event_bus():
    return AgentEventBus(retry_config=RetryConfig(max_attempts=1, base_delay=0.0))


@pytest.fixture
def global_config():
    return AgentsGlobalConfig(default_model="openai/gpt-4o", max_steps=10)


@pytest.fixture
def registry(event_bus, global_config):
    return AgentRegistry(
        event_bus=event_bus,
        global_config=global_config,
    )


class TestInitialize:
    """4.10 — initialize → агенты загружены."""

    @pytest.mark.asyncio
    async def test_initialize_loads_agents(self, registry):
        # Mock resolver
        with patch.object(
            registry._resolver,
            "resolve_all",
            return_value={
                "coder": ResolvedAgent(name="coder", mode=AgentMode.PRIMARY),
                "reviewer": ResolvedAgent(name="reviewer", mode=AgentMode.SUBAGENT),
            },
        ):
            await registry.initialize()

        assert registry.is_initialized
        assert len(registry.get_all()) == 2
        assert "coder" in registry.get_all()
        assert "reviewer" in registry.get_all()


class TestReload:
    """4.11 — reload → события added/removed опубликованы."""

    @pytest.mark.asyncio
    async def test_reload_adds_and_removes(self, registry):
        # Сначала инициализируем с одним агентом
        with patch.object(
            registry._resolver,
            "resolve_all",
            return_value={
                "coder": ResolvedAgent(name="coder"),
            },
        ):
            await registry.initialize()

        # Reload — добавляем reviewer, удаляем coder
        with patch.object(
            registry._resolver,
            "resolve_all",
            return_value={
                "reviewer": ResolvedAgent(name="reviewer"),
            },
        ):
            result = await registry.reload()

        assert "reviewer" in result["added"]
        assert "coder" in result["removed"]
        assert "reviewer" in registry.get_all()
        assert "coder" not in registry.get_all()


class TestGetMethods:
    """4.12 — get_primary_agents, get_subagents, get_orchestrator."""

    @pytest.mark.asyncio
    async def test_get_primary_agents(self, registry):
        with patch.object(
            registry._resolver,
            "resolve_all",
            return_value={
                "coder": ResolvedAgent(name="coder", mode=AgentMode.PRIMARY),
                "helper": ResolvedAgent(name="helper", mode=AgentMode.SUBAGENT),
            },
        ):
            await registry.initialize()

        primary = registry.get_primary_agents()
        assert len(primary) == 1
        assert "coder" in primary

    @pytest.mark.asyncio
    async def test_get_subagents(self, registry):
        with patch.object(
            registry._resolver,
            "resolve_all",
            return_value={
                "coder": ResolvedAgent(name="coder", mode=AgentMode.PRIMARY),
                "helper": ResolvedAgent(name="helper", mode=AgentMode.SUBAGENT),
                "assistant": ResolvedAgent(name="assistant", mode=AgentMode.SUBAGENT),
            },
        ):
            await registry.initialize()

        subagents = registry.get_subagents()
        assert len(subagents) == 2
        assert "helper" in subagents
        assert "assistant" in subagents

    @pytest.mark.asyncio
    async def test_get_orchestrator(self, registry):
        with patch.object(
            registry._resolver,
            "resolve_all",
            return_value={
                "coder": ResolvedAgent(name="coder", mode=AgentMode.PRIMARY),
                "orchestrator": ResolvedAgent(
                    name="orchestrator", mode=AgentMode.ORCHESTRATOR
                ),
            },
        ):
            await registry.initialize()

        orch = registry.get_orchestrator()
        assert orch is not None
        assert orch.name == "orchestrator"

    @pytest.mark.asyncio
    async def test_get_orchestrator_none(self, registry):
        with patch.object(
            registry._resolver,
            "resolve_all",
            return_value={
                "coder": ResolvedAgent(name="coder", mode=AgentMode.PRIMARY),
            },
        ):
            await registry.initialize()

        assert registry.get_orchestrator() is None

    @pytest.mark.asyncio
    async def test_get_single_agent(self, registry):
        with patch.object(
            registry._resolver,
            "resolve_all",
            return_value={
                "coder": ResolvedAgent(name="coder", model="openai/gpt-4o"),
            },
        ):
            await registry.initialize()

        agent = registry.get("coder")
        assert agent is not None
        assert agent.model == "openai/gpt-4o"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, registry):
        with patch.object(
            registry._resolver,
            "resolve_all",
            return_value={},
        ):
            await registry.initialize()

        assert registry.get("nonexistent") is None
