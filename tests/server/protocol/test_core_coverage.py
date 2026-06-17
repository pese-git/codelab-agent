"""Тесты для непокрытых edge cases в ACPProtocol.

Фокус на мелких ветках core.py: отправка сообщений, флаги MCP transport,
построение config specs и fallback-пути для _agent.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from codelab.server.messages import ACPMessage
from codelab.server.protocol.core import ACPProtocol


class TestSendMessage:
    """Тесты для _send_message."""

    async def test_send_message_invokes_callback_when_set(self) -> None:
        """Callback вызывается, если он задан."""
        message = ACPMessage.notification("session/update", {"update": {}})
        callback = AsyncMock()
        protocol = ACPProtocol(send_callback=callback)

        await protocol._send_message(message)

        callback.assert_awaited_once_with(message)

    async def test_send_message_logs_warning_when_callback_is_none(self) -> None:
        """Логируется предупреждение, если callback не настроен."""
        message = ACPMessage.notification("session/update", {"update": {}})
        protocol = ACPProtocol()

        with patch("codelab.server.protocol.core.logger") as mock_logger:
            await protocol._send_message(message)

        mock_logger.warning.assert_called_once()


class TestInitializeMcpFlags:
    """Тесты для флагов MCP transport в ответе initialize."""

    async def test_initialize_mcp_http_disabled(self) -> None:
        """mcp_http_enabled=False пробрасывается в результат initialize."""
        protocol = ACPProtocol(mcp_http_enabled=False)
        request = ACPMessage.request(
            "initialize",
            {"protocolVersion": 1, "clientCapabilities": {}},
        )

        outcome = await protocol.handle(request)

        assert outcome.response is not None
        assert outcome.response.error is None
        result = outcome.response.result
        assert result is not None
        assert result["agentCapabilities"]["mcpCapabilities"]["http"] is False
        assert result["agentCapabilities"]["mcpCapabilities"]["sse"] is True

    async def test_initialize_mcp_sse_disabled(self) -> None:
        """mcp_sse_enabled=False пробрасывается в результат initialize."""
        protocol = ACPProtocol(mcp_sse_enabled=False)
        request = ACPMessage.request(
            "initialize",
            {"protocolVersion": 1, "clientCapabilities": {}},
        )

        outcome = await protocol.handle(request)

        assert outcome.response is not None
        assert outcome.response.error is None
        result = outcome.response.result
        assert result is not None
        assert result["agentCapabilities"]["mcpCapabilities"]["http"] is True
        assert result["agentCapabilities"]["mcpCapabilities"]["sse"] is False


class TestBuildConfigSpecs:
    """Тесты для _build_config_specs."""

    def test_build_config_specs_calls_config_option_builder(self) -> None:
        """config_option_builder вызывается с default_model и additional_specs."""
        builder = MagicMock()
        builder.get_model_list.return_value = []
        builder.build_config_specs.return_value = {"model": {"default": "openai/gpt-4o"}}
        protocol = ACPProtocol(config_option_builder=builder)
        builder.build_config_specs.reset_mock()

        specs = protocol._build_config_specs()

        builder.build_config_specs.assert_called_once()
        call_kwargs = builder.build_config_specs.call_args.kwargs
        assert call_kwargs["default_model"] == "openai/gpt-4o"
        assert "mode" in call_kwargs["additional_specs"]
        assert "_agent" in call_kwargs["additional_specs"]
        assert "_active_strategy" in call_kwargs["additional_specs"]
        assert specs == {"model": {"default": "openai/gpt-4o"}}


class TestBuildAgentConfigSpec:
    """Тесты для _build_agent_config_spec и fallback-путей."""

    def _assert_fallback_spec(self, spec: dict) -> None:
        """Проверить структуру fallback spec."""
        assert spec["id"] == "_agent"
        assert spec["name"] == "Agent"
        assert spec["category"] == "_agent"
        assert spec["type"] == "select"
        assert spec["default"] == "primary"
        assert len(spec["options"]) == 1
        assert spec["options"][0]["value"] == "primary"

    def test_build_agent_config_spec_no_registry(self) -> None:
        """Без agent_registry возвращается fallback spec."""
        protocol = ACPProtocol()

        spec = protocol._build_agent_config_spec()

        self._assert_fallback_spec(spec)

    def test_build_agent_config_spec_not_initialized(self) -> None:
        """Registry с is_initialized=False даёт fallback spec."""
        agent_registry = MagicMock()
        agent_registry.is_initialized = False
        protocol = ACPProtocol(agent_registry=agent_registry)

        spec = protocol._build_agent_config_spec()

        self._assert_fallback_spec(spec)

    def test_build_agent_config_spec_without_get_primary_agents(self) -> None:
        """Registry без get_primary_agents даёт fallback spec."""
        agent_registry = MagicMock(spec=["is_initialized"])
        agent_registry.is_initialized = True
        protocol = ACPProtocol(agent_registry=agent_registry)

        spec = protocol._build_agent_config_spec()

        self._assert_fallback_spec(spec)

    def test_build_agent_config_spec_empty_primary_agents(self) -> None:
        """Пустой словарь primary агентов даёт fallback spec."""
        agent_registry = MagicMock()
        agent_registry.is_initialized = True
        agent_registry.get_primary_agents.return_value = {}
        protocol = ACPProtocol(agent_registry=agent_registry)

        spec = protocol._build_agent_config_spec()

        self._assert_fallback_spec(spec)

    def test_build_agent_config_spec_full_path_sorted_by_priority(self) -> None:
        """Агенты сортируются по priority и превращаются в options."""
        class Agent:
            def __init__(self, name: str, model: str, priority: int) -> None:
                self.name = name
                self.model = model
                self.priority = priority

        agent_registry = MagicMock()
        agent_registry.is_initialized = True
        agent_registry.get_primary_agents.return_value = {
            "beta": Agent("beta", "openai/gpt-4o", 20),
            "alpha": Agent("alpha", "anthropic/claude", 10),
        }
        protocol = ACPProtocol(agent_registry=agent_registry)

        spec = protocol._build_agent_config_spec()

        assert spec["id"] == "_agent"
        assert spec["default"] == "alpha"
        option_values = [opt["value"] for opt in spec["options"]]
        assert option_values == ["alpha", "beta"]
        alpha_option = spec["options"][0]
        assert alpha_option["name"] == "Alpha"
        assert "anthropic/claude" in alpha_option["description"]
        assert "priority: 10" in alpha_option["description"]


class TestSupportedToolKinds:
    """Тесты для _supported_tool_kinds."""

    def test_supported_tool_kinds_contains_expected_values(self) -> None:
        """Множество поддерживаемых tool kinds содержит ожидаемые значения."""
        expected = {
            "read",
            "edit",
            "delete",
            "move",
            "search",
            "execute",
            "think",
            "fetch",
            "switch_mode",
            "other",
        }

        assert expected <= ACPProtocol._supported_tool_kinds


class TestDefaultConfigSpecs:
    """Тесты для _default_config_specs."""

    def test_default_config_specs_mode_structure(self) -> None:
        """mode spec имеет корректный default и набор options."""
        mode_spec = ACPProtocol._default_config_specs["mode"]

        assert mode_spec["name"] == "Session Mode"
        assert mode_spec["category"] == "mode"
        assert mode_spec["default"] == "standard"
        option_values = {opt["value"] for opt in mode_spec["options"]}
        assert option_values == {"plan", "standard", "bypass"}

    def test_default_config_specs_model_structure(self) -> None:
        """model spec имеет корректный default."""
        model_spec = ACPProtocol._default_config_specs["model"]

        assert model_spec["name"] == "Model"
        assert model_spec["category"] == "model"
        assert model_spec["default"] == "openai/gpt-4o"
        assert any(
            opt["value"] == "openai/gpt-4o" for opt in model_spec["options"]
        )
