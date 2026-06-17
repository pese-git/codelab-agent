"""Тесты для непокрытых участков MCPManager.

Покрывают методы управления серверами, вызова инструментов, ресурсов,
промптов, уведомлений, shutdown и health check.
"""

from __future__ import annotations

import asyncio
import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codelab.server.mcp.client import MCPClient, MCPClientError, MCPClientState
from codelab.server.mcp.manager import (
    MCPManager,
    MCPManagerError,
    MCPManagerState,
    MCPServerAlreadyExistsError,
    MCPServerNotFoundError,
)
from codelab.server.mcp.models import (
    MCPCapabilities,
    MCPGetPromptResult,
    MCPPrompt,
    MCPResource,
    MCPResourceTemplate,
    MCPServerConfig,
    MCPTool,
    MCPToolInputSchema,
)
from codelab.server.mcp.tool_adapter import MCPToolAdapter
from codelab.server.tools.base import ToolDefinition, ToolExecutionResult


@pytest.fixture
def mcp_server_config() -> MCPServerConfig:
    """Создаёт тестовую конфигурацию MCP сервера."""
    return MCPServerConfig(
        name="test-server",
        command="test-mcp-server",
        args=["--stdio"],
    )


@pytest.fixture
def sample_mcp_tools() -> list[MCPTool]:
    """Создаёт список тестовых MCP инструментов."""
    return [
        MCPTool(
            name="read_file",
            description="Читает содержимое файла",
            input_schema=MCPToolInputSchema(
                type="object",
                properties={"path": {"type": "string"}},
                required=["path"],
            ),
        ),
    ]


class TestMCPManagerClientAccess:
    """Тесты доступа к клиентам через get_client и has_server."""

    def test_get_client_returns_client(self) -> None:
        """get_client возвращает клиент по ID сервера."""
        manager = MCPManager("session_123")
        client = MagicMock(spec=MCPClient)
        manager._clients["server"] = client

        assert manager.get_client("server") is client

    def test_get_client_returns_none_for_missing(self) -> None:
        """get_client возвращает None для несуществующего сервера."""
        manager = MCPManager("session_123")

        assert manager.get_client("missing") is None


class TestMCPManagerRemoveServer:
    """Тесты удаления сервера."""

    @pytest.mark.asyncio
    async def test_remove_server_logs_disconnect_error(
        self,
        mcp_server_config: MCPServerConfig,
        sample_mcp_tools: list[MCPTool],
    ) -> None:
        """Ошибка отключения логируется, но сервер удаляется."""
        manager = MCPManager("session_123")

        mock_client = AsyncMock(spec=MCPClient)
        mock_client.state = MCPClientState.READY
        mock_client.disconnect = AsyncMock(side_effect=RuntimeError("disconnect failed"))
        mock_client.list_tools = AsyncMock(return_value=sample_mcp_tools)

        with patch(
            "codelab.server.mcp.manager.MCPClient",
            return_value=mock_client,
        ):
            await manager.add_server(mcp_server_config)
            await manager.remove_server("test-server")

        assert manager.server_count == 0
        assert manager.has_server("test-server") is False
        mock_client.disconnect.assert_called_once()


class TestMCPManagerGetTools:
    """Тесты получения инструментов конкретного сервера."""

    def test_get_tools_for_server_not_found(self) -> None:
        """get_tools_for_server выбрасывает ошибку для несуществующего сервера."""
        manager = MCPManager("session_123")

        with pytest.raises(MCPServerNotFoundError):
            manager.get_tools_for_server("missing")

    @pytest.mark.asyncio
    async def test_get_tools_for_server_success(
        self,
        mcp_server_config: MCPServerConfig,
        sample_mcp_tools: list[MCPTool],
    ) -> None:
        """get_tools_for_server возвращает инструменты сервера."""
        manager = MCPManager("session_123")

        mock_client = AsyncMock(spec=MCPClient)
        mock_client.state = MCPClientState.READY
        mock_client.list_tools = AsyncMock(return_value=sample_mcp_tools)

        with patch(
            "codelab.server.mcp.manager.MCPClient",
            return_value=mock_client,
        ):
            await manager.add_server(mcp_server_config)
            tools = manager.get_tools_for_server("test-server")

        assert len(tools) == 1
        assert isinstance(tools[0], ToolDefinition)


class TestMCPManagerCallTool:
    """Тесты вызова инструмента через namespaced имя."""

    def _create_ready_manager(self, server_id: str = "test-server") -> MCPManager:
        """Создаёт менеджер с готовым сервером и адаптером."""
        manager = MCPManager("session_123")

        client = MagicMock(spec=MCPClient)
        client.state = MCPClientState.READY
        client.config = MCPServerConfig(name=server_id, command="cmd")

        adapter = MagicMock(spec=MCPToolAdapter)
        adapter.call_tool = AsyncMock(
            return_value=ToolExecutionResult(success=True, output="ok")
        )

        manager._clients[server_id] = client
        manager._adapters[server_id] = adapter
        manager._tools_cache[server_id] = []

        return manager

    @pytest.mark.asyncio
    async def test_call_tool_invalid_format(self) -> None:
        """call_tool возвращает ошибку при неверном формате имени."""
        manager = self._create_ready_manager()

        result = await manager.call_tool("bad_name", {})

        assert result.success is False
        assert "Invalid MCP tool name format" in (result.error or "")

    @pytest.mark.asyncio
    async def test_call_tool_invalid_prefix(self) -> None:
        """call_tool возвращает ошибку при неверном префиксе namespace."""
        manager = self._create_ready_manager()

        result = await manager.call_tool("other:test-server:tool", {})

        assert result.success is False
        assert "Invalid namespace prefix" in (result.error or "")

    @pytest.mark.asyncio
    async def test_call_tool_server_not_found(self) -> None:
        """call_tool возвращает ошибку если сервер не найден."""
        manager = self._create_ready_manager()

        result = await manager.call_tool("mcp:missing:tool", {})

        assert result.success is False
        assert "MCP server 'missing' not found" in (result.error or "")

    @pytest.mark.asyncio
    async def test_call_tool_server_not_ready(self) -> None:
        """call_tool возвращает ошибку если сервер не в состоянии READY."""
        manager = self._create_ready_manager()
        manager._clients["test-server"].state = MCPClientState.FAILED

        result = await manager.call_tool("mcp:test-server:tool", {})

        assert result.success is False
        assert "MCP server 'test-server' is not ready" in (result.error or "")

    @pytest.mark.asyncio
    async def test_call_tool_client_missing(self) -> None:
        """call_tool возвращает ошибку если клиент отсутствует в менеджере."""
        manager = self._create_ready_manager()
        del manager._clients["test-server"]

        result = await manager.call_tool("mcp:test-server:tool", {})

        assert result.success is False
        assert "MCP server 'test-server' is not ready" in (result.error or "")

    @pytest.mark.asyncio
    async def test_call_tool_success(self) -> None:
        """call_tool перенаправляет вызов адаптеру."""
        manager = self._create_ready_manager()

        result = await manager.call_tool("mcp:test-server:read_file", {"path": "/tmp"})

        assert result.success is True
        assert result.output == "ok"
        manager._adapters["test-server"].call_tool.assert_called_once_with(
            "read_file", {"path": "/tmp"}
        )


class TestMCPManagerServerInfo:
    """Тесты получения информации о серверах."""

    def test_get_servers_info_with_capabilities(self) -> None:
        """get_servers_info включает capabilities сервера."""
        manager = MCPManager("session_123")

        client = MagicMock(spec=MCPClient)
        client.config = MCPServerConfig(name="server", command="cmd")
        client.state = MCPClientState.READY
        client.capabilities = MCPCapabilities(tools={"listChanged": True})

        manager._clients["server"] = client
        manager._tools_cache["server"] = []

        info = manager.get_servers_info()

        assert len(info) == 1
        assert info[0]["id"] == "server"
        assert "capabilities" in info[0]
        assert info[0]["capabilities"]["tools"] == {"listChanged": True}

    def test_get_servers_info_without_capabilities(self) -> None:
        """get_servers_info не добавляет capabilities если их нет."""
        manager = MCPManager("session_123")

        client = MagicMock(spec=MCPClient)
        client.config = MCPServerConfig(name="server", command="cmd")
        client.state = MCPClientState.READY
        client.capabilities = None

        manager._clients["server"] = client
        manager._tools_cache["server"] = []

        info = manager.get_servers_info()

        assert len(info) == 1
        assert "capabilities" not in info[0]


class TestMCPManagerRefreshTools:
    """Тесты обновления списка инструментов."""

    @pytest.mark.asyncio
    async def test_refresh_tools_success(self) -> None:
        """refresh_tools обновляет кэш и возвращает инструменты."""
        manager = MCPManager("session_123")

        new_tools = [
            MCPTool(
                name="new_tool",
                description="Новый инструмент",
                input_schema=MCPToolInputSchema(),
            ),
        ]

        client = MagicMock(spec=MCPClient)
        client.config = MCPServerConfig(name="server", command="cmd")
        client.state = MCPClientState.READY
        client.list_tools = AsyncMock(return_value=new_tools)

        adapter = MagicMock(spec=MCPToolAdapter)
        adapter.adapt_tools.return_value = [MagicMock(spec=ToolDefinition)]

        manager._clients["server"] = client
        manager._adapters["server"] = adapter
        manager._tools_cache["server"] = []

        result = await manager.refresh_tools("server")

        assert manager._tools_cache["server"] == new_tools
        assert len(result) == 1
        adapter.adapt_tools.assert_called_once_with(new_tools)

    @pytest.mark.asyncio
    async def test_refresh_tools_not_found(self) -> None:
        """refresh_tools выбрасывает ошибку для несуществующего сервера."""
        manager = MCPManager("session_123")

        with pytest.raises(MCPServerNotFoundError):
            await manager.refresh_tools("missing")

    @pytest.mark.asyncio
    async def test_refresh_tools_client_error(self) -> None:
        """refresh_tools оборачивает MCPClientError в MCPManagerError."""
        manager = MCPManager("session_123")

        client = MagicMock(spec=MCPClient)
        client.config = MCPServerConfig(name="server", command="cmd")
        client.state = MCPClientState.READY
        client.list_tools = AsyncMock(side_effect=MCPClientError("boom"))

        manager._clients["server"] = client
        manager._adapters["server"] = MagicMock(spec=MCPToolAdapter)
        manager._tools_cache["server"] = []

        with pytest.raises(MCPManagerError):
            await manager.refresh_tools("server")


class TestMCPManagerNotificationErrors:
    """Тесты обработки ошибок в notification callbacks."""

    @pytest.mark.asyncio
    async def test_on_resources_changed_callback_error(self) -> None:
        """Ошибка в resource callback не ломает остальные callbacks."""
        manager = MCPManager("session_123")
        good_calls: list[int] = []

        async def bad_callback() -> None:
            raise RuntimeError("resource error")

        async def good_callback() -> None:
            good_calls.append(1)

        manager.register_resource_change_callback(bad_callback)
        manager.register_resource_change_callback(good_callback)

        await manager._on_resources_changed("server")

        assert len(good_calls) == 1

    @pytest.mark.asyncio
    async def test_on_prompts_changed_callback_error(self) -> None:
        """Ошибка в prompt callback не ломает остальные callbacks."""
        manager = MCPManager("session_123")
        good_calls: list[int] = []

        async def bad_callback() -> None:
            raise RuntimeError("prompt error")

        async def good_callback() -> None:
            good_calls.append(1)

        manager.register_prompt_change_callback(bad_callback)
        manager.register_prompt_change_callback(good_callback)

        await manager._on_prompts_changed("server")

        assert len(good_calls) == 1

    @pytest.mark.asyncio
    async def test_notify_server_status_changed_callback_error(self) -> None:
        """Ошибка в server status callback не ломает остальные callbacks."""
        manager = MCPManager("session_123")
        good_calls: list[int] = []

        async def bad_callback() -> None:
            raise RuntimeError("status error")

        async def good_callback() -> None:
            good_calls.append(1)

        manager.register_server_status_callback(bad_callback)
        manager.register_server_status_callback(good_callback)

        await manager._notify_server_status_changed()

        assert len(good_calls) == 1


class TestMCPManagerResources:
    """Тесты работы с ресурсами MCP серверов."""

    def _create_resource_client(
        self,
        state: MCPClientState = MCPClientState.READY,
        resources_cap: dict[str, object] | None = None,
        list_resources_result: list[MCPResource] | None = None,
        list_resources_error: Exception | None = None,
    ) -> MagicMock:
        """Создаёт mock клиента с заданными настройками ресурсов."""
        effective_resources_cap = resources_cap

        client = MagicMock(spec=MCPClient)
        client.config = MCPServerConfig(name="server", command="cmd")
        client.state = state
        client.capabilities = MCPCapabilities(resources=effective_resources_cap)

        if list_resources_error is not None:
            client.list_resources = AsyncMock(side_effect=list_resources_error)
        else:
            client.list_resources = AsyncMock(return_value=list_resources_result or [])

        client.list_resource_templates = AsyncMock(return_value=[])

        return client

    @pytest.mark.asyncio
    async def test_get_all_resources_with_capability(self) -> None:
        """get_all_resources возвращает ресурсы от готового сервера."""
        manager = MCPManager("session_123")
        resource = MCPResource(uri="file:///tmp", name="tmp")
        client = self._create_resource_client(
            resources_cap={"listChanged": True},
            list_resources_result=[resource],
        )
        manager._clients["server"] = client

        result = await manager.get_all_resources()

        assert result == {"server": [resource]}

    @pytest.mark.asyncio
    async def test_get_all_resources_skips_not_ready(self) -> None:
        """get_all_resources пропускает серверы не в состоянии READY."""
        manager = MCPManager("session_123")
        client = self._create_resource_client(
            state=MCPClientState.CONNECTING,
            resources_cap={"listChanged": True},
        )
        manager._clients["server"] = client

        result = await manager.get_all_resources()

        assert result == {}
        client.list_resources.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_all_resources_skips_no_capability(self) -> None:
        """get_all_resources пропускает серверы без поддержки ресурсов."""
        manager = MCPManager("session_123")
        client = self._create_resource_client(resources_cap=None)
        manager._clients["server"] = client

        result = await manager.get_all_resources()

        assert result == {}
        client.list_resources.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_all_resources_handles_client_error(self) -> None:
        """get_all_resources обрабатывает ошибки клиента."""
        manager = MCPManager("session_123")
        client = self._create_resource_client(
            resources_cap={"listChanged": True},
            list_resources_error=MCPClientError("list failed"),
        )
        manager._clients["server"] = client

        result = await manager.get_all_resources()

        assert result == {}

    @pytest.mark.asyncio
    async def test_get_all_resource_templates_with_capability(self) -> None:
        """get_all_resource_templates возвращает шаблоны от готового сервера."""
        manager = MCPManager("session_123")
        template = MCPResourceTemplate(uri_template="file:///{path}", name="files")
        client = self._create_resource_client(resources_cap={"listChanged": True})
        client.list_resource_templates = AsyncMock(return_value=[template])
        manager._clients["server"] = client

        result = await manager.get_all_resource_templates()

        assert result == {"server": [template]}

    @pytest.mark.asyncio
    async def test_get_all_resource_templates_skips_not_ready(self) -> None:
        """get_all_resource_templates пропускает неготовые серверы."""
        manager = MCPManager("session_123")
        client = self._create_resource_client(
            state=MCPClientState.CONNECTING,
            resources_cap={"listChanged": True},
        )
        manager._clients["server"] = client

        result = await manager.get_all_resource_templates()

        assert result == {}
        client.list_resource_templates.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_all_resource_templates_skips_no_capability(self) -> None:
        """get_all_resource_templates пропускает серверы без поддержки ресурсов."""
        manager = MCPManager("session_123")
        client = self._create_resource_client(resources_cap=None)
        manager._clients["server"] = client

        result = await manager.get_all_resource_templates()

        assert result == {}
        client.list_resource_templates.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_all_resource_templates_handles_client_error(self) -> None:
        """get_all_resource_templates обрабатывает ошибки клиента."""
        manager = MCPManager("session_123")
        client = self._create_resource_client(resources_cap={"listChanged": True})
        client.list_resource_templates = AsyncMock(
            side_effect=MCPClientError("templates failed")
        )
        manager._clients["server"] = client

        result = await manager.get_all_resource_templates()

        assert result == {}

    @pytest.mark.asyncio
    async def test_read_resource_not_found(self) -> None:
        """read_resource выбрасывает ошибку для несуществующего сервера."""
        manager = MCPManager("session_123")

        with pytest.raises(MCPServerNotFoundError):
            await manager.read_resource("missing", "file:///tmp")

    @pytest.mark.asyncio
    async def test_read_resource_not_ready(self) -> None:
        """read_resource выбрасывает ошибку если сервер не готов."""
        manager = MCPManager("session_123")
        client = MagicMock(spec=MCPClient)
        client.config = MCPServerConfig(name="server", command="cmd")
        client.state = MCPClientState.CONNECTING
        manager._clients["server"] = client

        with pytest.raises(MCPManagerError):
            await manager.read_resource("server", "file:///tmp")

    @pytest.mark.asyncio
    async def test_read_resource_success(self) -> None:
        """read_resource возвращает результат от клиента."""
        manager = MCPManager("session_123")
        expected = {"contents": [{"text": "data"}]}

        client = MagicMock(spec=MCPClient)
        client.config = MCPServerConfig(name="server", command="cmd")
        client.state = MCPClientState.READY
        client.read_resource = AsyncMock(return_value=expected)
        manager._clients["server"] = client

        result = await manager.read_resource("server", "file:///tmp")

        assert result == expected
        client.read_resource.assert_called_once_with("file:///tmp")

    @pytest.mark.asyncio
    async def test_read_resource_client_error(self) -> None:
        """read_resource оборачивает MCPClientError в MCPManagerError."""
        manager = MCPManager("session_123")
        client = MagicMock(spec=MCPClient)
        client.config = MCPServerConfig(name="server", command="cmd")
        client.state = MCPClientState.READY
        client.read_resource = AsyncMock(side_effect=MCPClientError("read failed"))
        manager._clients["server"] = client

        with pytest.raises(MCPManagerError):
            await manager.read_resource("server", "file:///tmp")


class TestMCPManagerPrompts:
    """Тесты работы с промптами MCP серверов."""

    def _create_prompt_client(
        self,
        state: MCPClientState = MCPClientState.READY,
        prompts_cap: dict[str, object] | None = None,
        list_prompts_result: list[MCPPrompt] | None = None,
        list_prompts_error: Exception | None = None,
    ) -> MagicMock:
        """Создаёт mock клиента с заданными настройками промптов."""
        effective_prompts_cap = prompts_cap

        client = MagicMock(spec=MCPClient)
        client.config = MCPServerConfig(name="server", command="cmd")
        client.state = state
        client.capabilities = MCPCapabilities(prompts=effective_prompts_cap)

        if list_prompts_error is not None:
            client.list_prompts = AsyncMock(side_effect=list_prompts_error)
        else:
            client.list_prompts = AsyncMock(return_value=list_prompts_result or [])

        return client

    @pytest.mark.asyncio
    async def test_get_all_prompts_with_capability(self) -> None:
        """get_all_prompts возвращает промпты от готового сервера."""
        manager = MCPManager("session_123")
        prompt = MCPPrompt(name="greeting", description="Hello prompt")
        client = self._create_prompt_client(
            prompts_cap={"listChanged": True},
            list_prompts_result=[prompt],
        )
        manager._clients["server"] = client

        result = await manager.get_all_prompts()

        assert result == {"server": [prompt]}

    @pytest.mark.asyncio
    async def test_get_all_prompts_skips_not_ready(self) -> None:
        """get_all_prompts пропускает серверы не в состоянии READY."""
        manager = MCPManager("session_123")
        client = self._create_prompt_client(
            state=MCPClientState.CONNECTING,
            prompts_cap={"listChanged": True},
        )
        manager._clients["server"] = client

        result = await manager.get_all_prompts()

        assert result == {}
        client.list_prompts.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_all_prompts_skips_no_capability(self) -> None:
        """get_all_prompts пропускает серверы без поддержки промптов."""
        manager = MCPManager("session_123")
        client = self._create_prompt_client(prompts_cap=None)
        manager._clients["server"] = client

        result = await manager.get_all_prompts()

        assert result == {}
        client.list_prompts.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_all_prompts_handles_client_error(self) -> None:
        """get_all_prompts обрабатывает ошибки клиента."""
        manager = MCPManager("session_123")
        client = self._create_prompt_client(
            prompts_cap={"listChanged": True},
            list_prompts_error=MCPClientError("list failed"),
        )
        manager._clients["server"] = client

        result = await manager.get_all_prompts()

        assert result == {}

    @pytest.mark.asyncio
    async def test_get_prompt_not_found(self) -> None:
        """get_prompt выбрасывает ошибку для несуществующего сервера."""
        manager = MCPManager("session_123")

        with pytest.raises(MCPServerNotFoundError):
            await manager.get_prompt("missing", "greeting")

    @pytest.mark.asyncio
    async def test_get_prompt_not_ready(self) -> None:
        """get_prompt выбрасывает ошибку если сервер не готов."""
        manager = MCPManager("session_123")
        client = MagicMock(spec=MCPClient)
        client.config = MCPServerConfig(name="server", command="cmd")
        client.state = MCPClientState.CONNECTING
        manager._clients["server"] = client

        with pytest.raises(MCPManagerError):
            await manager.get_prompt("server", "greeting")

    @pytest.mark.asyncio
    async def test_get_prompt_success(self) -> None:
        """get_prompt возвращает результат от клиента."""
        manager = MCPManager("session_123")
        expected = MCPGetPromptResult(
            description="Hello",
            messages=[{"role": "user", "content": {"type": "text", "text": "Hi"}}],
        )

        client = MagicMock(spec=MCPClient)
        client.config = MCPServerConfig(name="server", command="cmd")
        client.state = MCPClientState.READY
        client.get_prompt = AsyncMock(return_value=expected)
        manager._clients["server"] = client

        result = await manager.get_prompt("server", "greeting", {"name": "Ada"})

        assert result == expected
        client.get_prompt.assert_called_once_with("greeting", {"name": "Ada"})

    @pytest.mark.asyncio
    async def test_get_prompt_default_arguments(self) -> None:
        """get_prompt передаёт пустой словарь если arguments не указаны."""
        manager = MCPManager("session_123")
        expected = MCPGetPromptResult(description="Hello", messages=[])

        client = MagicMock(spec=MCPClient)
        client.config = MCPServerConfig(name="server", command="cmd")
        client.state = MCPClientState.READY
        client.get_prompt = AsyncMock(return_value=expected)
        manager._clients["server"] = client

        await manager.get_prompt("server", "greeting")

        client.get_prompt.assert_called_once_with("greeting", {})

    @pytest.mark.asyncio
    async def test_get_prompt_client_error(self) -> None:
        """get_prompt оборачивает MCPClientError в MCPManagerError."""
        manager = MCPManager("session_123")
        client = MagicMock(spec=MCPClient)
        client.config = MCPServerConfig(name="server", command="cmd")
        client.state = MCPClientState.READY
        client.get_prompt = AsyncMock(side_effect=MCPClientError("get failed"))
        manager._clients["server"] = client

        with pytest.raises(MCPManagerError):
            await manager.get_prompt("server", "greeting")


class TestMCPManagerShutdown:
    """Тесты завершения работы менеджера."""

    @pytest.mark.asyncio
    async def test_shutdown_logs_remove_error(
        self,
        mcp_server_config: MCPServerConfig,
        sample_mcp_tools: list[MCPTool],
    ) -> None:
        """shutdown логирует ошибки при удалении серверов."""
        manager = MCPManager("session_123")

        mock_client = AsyncMock(spec=MCPClient)
        mock_client.state = MCPClientState.READY
        mock_client.list_tools = AsyncMock(return_value=sample_mcp_tools)

        with patch(
            "codelab.server.mcp.manager.MCPClient",
            return_value=mock_client,
        ):
            await manager.add_server(mcp_server_config)

        # Имитируем ошибку в remove_server
        manager.remove_server = AsyncMock(side_effect=RuntimeError("remove failed"))

        # Не должно выбрасывать исключение
        await manager.shutdown()

        manager.remove_server.assert_called_once_with("test-server")


class TestMCPManagerHealthCheck:
    """Тесты периодической проверки здоровья серверов."""

    @pytest.mark.asyncio
    async def test_start_health_check_already_running(self) -> None:
        """Повторный запуск health check не создаёт вторую задачу."""
        manager = MCPManager("session_123")
        client = MagicMock(spec=MCPClient)
        client.config = MCPServerConfig(name="server", command="cmd")
        client.state = MCPClientState.READY
        manager._clients["server"] = client

        await manager.start_health_check("server", interval=60.0)
        first_task = manager._health_check_tasks["server"]

        # Повторный запуск должен вернуться раньше
        await manager.start_health_check("server", interval=60.0)

        assert manager._health_check_tasks["server"] is first_task

        await manager.stop_health_check("server")

    @pytest.mark.asyncio
    async def test_health_check_loop_client_not_found(self) -> None:
        """Цикл health check завершается если клиент удалён."""
        manager = MCPManager("session_123")

        task = asyncio.create_task(
            manager._health_check_loop("server", interval=0.01)
        )
        result = await asyncio.wait_for(task, timeout=1.0)

        assert result is None

    @pytest.mark.asyncio
    async def test_health_check_loop_exception_handled(self) -> None:
        """Цикл health check обрабатывает неожиданные исключения."""
        manager = MCPManager("session_123")

        class RaisingClient:
            """Клиент, чьё состояние выбрасывает исключение."""

            config = MCPServerConfig(name="server", command="cmd")

            @property
            def state(self) -> MCPClientState:
                """Всегда выбрасывает RuntimeError."""
                raise RuntimeError("state boom")

        manager._clients["server"] = RaisingClient()  # type: ignore[assignment]

        task = asyncio.create_task(
            manager._health_check_loop("server", interval=0.01)
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        assert manager.state != MCPManagerState.FAILED


class TestMCPManagerAddServerErrors:
    """Тесты ошибок при добавлении сервера."""

    @pytest.mark.asyncio
    async def test_add_server_client_error_disconnects(
        self,
        mcp_server_config: MCPServerConfig,
    ) -> None:
        """При ошибке добавления клиент отключается и выбрасывается MCPManagerError."""
        manager = MCPManager("session_123")

        mock_client = AsyncMock(spec=MCPClient)
        mock_client.connect = AsyncMock()
        mock_client.initialize = AsyncMock(side_effect=MCPClientError("init failed"))
        mock_client.disconnect = AsyncMock()

        with patch(
            "codelab.server.mcp.manager.MCPClient",
            return_value=mock_client,
        ):
            with pytest.raises(MCPManagerError):
                await manager.add_server(mcp_server_config)

        mock_client.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_server_already_exists(
        self,
        mcp_server_config: MCPServerConfig,
        sample_mcp_tools: list[MCPTool],
    ) -> None:
        """Повторное добавление сервера выбрасывает MCPServerAlreadyExistsError."""
        manager = MCPManager("session_123")

        mock_client = AsyncMock(spec=MCPClient)
        mock_client.state = MCPClientState.READY
        mock_client.list_tools = AsyncMock(return_value=sample_mcp_tools)

        with patch(
            "codelab.server.mcp.manager.MCPClient",
            return_value=mock_client,
        ):
            await manager.add_server(mcp_server_config)

            with pytest.raises(MCPServerAlreadyExistsError):
                await manager.add_server(mcp_server_config)
