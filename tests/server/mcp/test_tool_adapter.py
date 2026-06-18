"""Тесты для MCPToolAdapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.mcp.client import MCPClient, MCPToolCallError
from codelab.server.mcp.models import MCPTool, MCPToolAnnotations, MCPToolInputSchema
from codelab.server.mcp.tool_adapter import _NAME_PREFIX_TO_KIND, MCPToolAdapter


@pytest.fixture
def mock_client() -> MagicMock:
    """Создать мок MCPClient."""
    return MagicMock(spec=MCPClient)


@pytest.fixture
def adapter(mock_client: MagicMock) -> MCPToolAdapter:
    """Создать MCPToolAdapter с мок клиентом."""
    return MCPToolAdapter(server_id="test_server", client=mock_client)


def _make_mcp_tool(
    name: str = "test_tool",
    description: str = "Test tool description",
    annotations: MCPToolAnnotations | None = None,
) -> MCPTool:
    """Создать MCPTool для тестов."""
    return MCPTool(
        name=name,
        description=description,
        input_schema=MCPToolInputSchema(
            type="object",
            properties={"arg1": {"type": "string"}},
            required=["arg1"],
        ),
        annotations=annotations,
    )


class TestMCPToolAdapterInit:
    """Тесты инициализации."""

    def test_init_stores_server_id(self, adapter: MCPToolAdapter) -> None:
        """Инициализация сохраняет server_id."""
        assert adapter.server_id == "test_server"

    def test_init_stores_client(self, adapter: MCPToolAdapter, mock_client: MagicMock) -> None:
        """Инициализация сохраняет client."""
        assert adapter.client is mock_client


class TestGetNamespacedName:
    """Тесты get_namespaced_name."""

    def test_returns_namespaced_name(self, adapter: MCPToolAdapter) -> None:
        """Возвращает имя в формате mcp:server_id:tool_name."""
        result = adapter.get_namespaced_name("read_file")
        assert result == "mcp:test_server:read_file"

    def test_handles_special_characters(self, adapter: MCPToolAdapter) -> None:
        """Обрабатывает специальные символы в имени инструмента."""
        result = adapter.get_namespaced_name("tool-with-dashes")
        assert result == "mcp:test_server:tool-with-dashes"


class TestParseNamespacedName:
    """Тесты parse_namespaced_name."""

    def test_parses_valid_name(self) -> None:
        """Разбирает валидное namespaced имя."""
        result = MCPToolAdapter.parse_namespaced_name("mcp:server:tool")
        assert result == ("mcp", "server", "tool")

    def test_returns_none_for_invalid_name(self) -> None:
        """Возвращает None для невалидного имени."""
        result = MCPToolAdapter.parse_namespaced_name("invalid")
        assert result is None

    def test_returns_none_for_two_parts(self) -> None:
        """Возвращает None для имени с двумя частями."""
        result = MCPToolAdapter.parse_namespaced_name("mcp:server")
        assert result is None

    def test_handles_tool_name_with_colons(self) -> None:
        """Обрабатывает имя инструмента с двоеточиями."""
        result = MCPToolAdapter.parse_namespaced_name("mcp:server:tool:with:colons")
        assert result == ("mcp", "server", "tool:with:colons")


class TestIsMCPTool:
    """Тесты is_mcp_tool."""

    def test_returns_true_for_mcp_tool(self) -> None:
        """Возвращает True для MCP инструмента."""
        assert MCPToolAdapter.is_mcp_tool("mcp:server:tool") is True

    def test_returns_false_for_non_mcp_tool(self) -> None:
        """Возвращает False для не-MCP инструмента."""
        assert MCPToolAdapter.is_mcp_tool("regular_tool") is False

    def test_returns_false_for_partial_match(self) -> None:
        """Возвращает False для частичного совпадения."""
        assert MCPToolAdapter.is_mcp_tool("mcp_tool") is False


class TestInferKind:
    """Тесты _infer_kind."""

    def test_read_only_hint_returns_read(self, adapter: MCPToolAdapter) -> None:
        """readOnlyHint=True возвращает 'read'."""
        tool = _make_mcp_tool(
            name="any_tool",
            annotations=MCPToolAnnotations(read_only_hint=True),
        )
        assert adapter._infer_kind(tool) == "read"

    def test_destructive_hint_with_delete_name_returns_delete(
        self, adapter: MCPToolAdapter
    ) -> None:
        """destructiveHint=True + delete в имени возвращает 'delete'."""
        tool = _make_mcp_tool(
            name="delete_file",
            annotations=MCPToolAnnotations(destructive_hint=True),
        )
        assert adapter._infer_kind(tool) == "delete"

    def test_destructive_hint_with_remove_name_returns_delete(
        self, adapter: MCPToolAdapter
    ) -> None:
        """destructiveHint=True + remove в имени возвращает 'delete'."""
        tool = _make_mcp_tool(
            name="remove_item",
            annotations=MCPToolAnnotations(destructive_hint=True),
        )
        assert adapter._infer_kind(tool) == "delete"

    def test_destructive_hint_with_rm_name_returns_delete(self, adapter: MCPToolAdapter) -> None:
        """destructiveHint=True + rm в имени возвращает 'delete'."""
        tool = _make_mcp_tool(
            name="rm_file",
            annotations=MCPToolAnnotations(destructive_hint=True),
        )
        assert adapter._infer_kind(tool) == "delete"

    def test_destructive_hint_without_delete_name_returns_edit(
        self, adapter: MCPToolAdapter
    ) -> None:
        """destructiveHint=True без delete в имени возвращает 'edit'."""
        tool = _make_mcp_tool(
            name="modify_file",
            annotations=MCPToolAnnotations(destructive_hint=True),
        )
        assert adapter._infer_kind(tool) == "edit"

    def test_read_prefix_returns_read(self, adapter: MCPToolAdapter) -> None:
        """Инструмент с префиксом 'read' возвращает 'read'."""
        tool = _make_mcp_tool(name="read_file")
        assert adapter._infer_kind(tool) == "read"

    def test_get_prefix_returns_read(self, adapter: MCPToolAdapter) -> None:
        """Инструмент с префиксом 'get' возвращает 'read'."""
        tool = _make_mcp_tool(name="get_config")
        assert adapter._infer_kind(tool) == "read"

    def test_list_prefix_returns_read(self, adapter: MCPToolAdapter) -> None:
        """Инструмент с префиксом 'list' возвращает 'read'."""
        tool = _make_mcp_tool(name="list_files")
        assert adapter._infer_kind(tool) == "read"

    def test_write_prefix_returns_edit(self, adapter: MCPToolAdapter) -> None:
        """Инструмент с префиксом 'write' возвращает 'edit'."""
        tool = _make_mcp_tool(name="write_file")
        assert adapter._infer_kind(tool) == "edit"

    def test_create_prefix_returns_edit(self, adapter: MCPToolAdapter) -> None:
        """Инструмент с префиксом 'create' возвращает 'edit'."""
        tool = _make_mcp_tool(name="create_file")
        assert adapter._infer_kind(tool) == "edit"

    def test_delete_prefix_returns_delete(self, adapter: MCPToolAdapter) -> None:
        """Инструмент с префиксом 'delete' возвращает 'delete'."""
        tool = _make_mcp_tool(name="delete_file")
        assert adapter._infer_kind(tool) == "delete"

    def test_exec_prefix_returns_execute(self, adapter: MCPToolAdapter) -> None:
        """Инструмент с префиксом 'exec' возвращает 'execute'."""
        tool = _make_mcp_tool(name="exec_command")
        assert adapter._infer_kind(tool) == "execute"

    def test_run_prefix_returns_execute(self, adapter: MCPToolAdapter) -> None:
        """Инструмент с префиксом 'run' возвращает 'execute'."""
        tool = _make_mcp_tool(name="run_script")
        assert adapter._infer_kind(tool) == "execute"

    def test_search_prefix_returns_search(self, adapter: MCPToolAdapter) -> None:
        """Инструмент с префиксом 'search' возвращает 'search'."""
        tool = _make_mcp_tool(name="search_files")
        assert adapter._infer_kind(tool) == "search"

    def test_fetch_prefix_returns_fetch(self, adapter: MCPToolAdapter) -> None:
        """Инструмент с префиксом 'fetch' возвращает 'fetch'."""
        tool = _make_mcp_tool(name="fetch_url")
        assert adapter._infer_kind(tool) == "fetch"

    def test_move_prefix_returns_move(self, adapter: MCPToolAdapter) -> None:
        """Инструмент с префиксом 'move' возвращает 'move'."""
        tool = _make_mcp_tool(name="move_file")
        assert adapter._infer_kind(tool) == "move"

    def test_unknown_prefix_returns_other(self, adapter: MCPToolAdapter) -> None:
        """Неизвестный префикс возвращает 'other'."""
        tool = _make_mcp_tool(name="unknown_tool")
        assert adapter._infer_kind(tool) == "other"

    def test_annotations_take_priority_over_name(self, adapter: MCPToolAdapter) -> None:
        """Аннотации имеют приоритет над эвристикой имени."""
        tool = _make_mcp_tool(
            name="write_file",
            annotations=MCPToolAnnotations(read_only_hint=True),
        )
        assert adapter._infer_kind(tool) == "read"


class TestMCPToolToDefinition:
    """Тесты mcp_tool_to_definition."""

    def test_creates_namespaced_name(self, adapter: MCPToolAdapter) -> None:
        """Создаёт ToolDefinition с namespaced именем."""
        tool = _make_mcp_tool(name="read_file")
        definition = adapter.mcp_tool_to_definition(tool)
        assert definition.name == "mcp:test_server:read_file"

    def test_includes_server_tag_in_description(self, adapter: MCPToolAdapter) -> None:
        """Добавляет тег MCP сервера в описание."""
        tool = _make_mcp_tool(name="read_file", description="Read a file")
        definition = adapter.mcp_tool_to_definition(tool)
        assert "[MCP:test_server]" in definition.description
        assert "Read a file" in definition.description

    def test_uses_tool_name_as_description_fallback(self, adapter: MCPToolAdapter) -> None:
        """Использует имя инструмента как fallback для описания."""
        tool = _make_mcp_tool(name="read_file", description="")
        definition = adapter.mcp_tool_to_definition(tool)
        assert "read_file" in definition.description

    def test_converts_input_schema_to_parameters(self, adapter: MCPToolAdapter) -> None:
        """Конвертирует input_schema в parameters."""
        tool = _make_mcp_tool(name="test")
        definition = adapter.mcp_tool_to_definition(tool)
        assert definition.parameters["type"] == "object"
        assert "arg1" in definition.parameters["properties"]
        assert "arg1" in definition.parameters["required"]

    def test_infers_kind_from_tool(self, adapter: MCPToolAdapter) -> None:
        """Выводит kind из инструмента."""
        tool = _make_mcp_tool(name="read_file")
        definition = adapter.mcp_tool_to_definition(tool)
        assert definition.kind == "read"

    def test_requires_permission(self, adapter: MCPToolAdapter) -> None:
        """MCP инструменты требуют разрешения."""
        tool = _make_mcp_tool(name="test")
        definition = adapter.mcp_tool_to_definition(tool)
        assert definition.requires_permission is True


class TestAdaptTools:
    """Тесты adapt_tools."""

    def test_adapts_empty_list(self, adapter: MCPToolAdapter) -> None:
        """Адаптирует пустой список инструментов."""
        result = adapter.adapt_tools([])
        assert result == []

    def test_adapts_single_tool(self, adapter: MCPToolAdapter) -> None:
        """Адаптирует один инструмент."""
        tools = [_make_mcp_tool(name="read_file")]
        result = adapter.adapt_tools(tools)
        assert len(result) == 1
        assert result[0].name == "mcp:test_server:read_file"

    def test_adapts_multiple_tools(self, adapter: MCPToolAdapter) -> None:
        """Адаптирует несколько инструментов."""
        tools = [
            _make_mcp_tool(name="read_file"),
            _make_mcp_tool(name="write_file"),
            _make_mcp_tool(name="delete_file"),
        ]
        result = adapter.adapt_tools(tools)
        assert len(result) == 3
        names = [t.name for t in result]
        assert "mcp:test_server:read_file" in names
        assert "mcp:test_server:write_file" in names
        assert "mcp:test_server:delete_file" in names


class TestCreateExecutor:
    """Тесты create_executor."""

    @pytest.mark.asyncio
    async def test_executor_calls_client_tool(
        self,
        adapter: MCPToolAdapter,
        mock_client: MagicMock,
    ) -> None:
        """Executor вызывает client.call_tool."""
        from codelab.server.mcp.models import MCPCallToolResult

        mock_result = MCPCallToolResult(
            content=[{"type": "text", "text": "Result"}],
            is_error=False,
        )
        mock_client.call_tool = AsyncMock(return_value=mock_result)

        executor = await adapter.create_executor("read_file")
        result = await executor(arg1="value1")

        mock_client.call_tool.assert_awaited_once_with("read_file", {"arg1": "value1"})
        assert result.success is True
        assert result.output == "Result"

    @pytest.mark.asyncio
    async def test_executor_returns_error_on_mcp_error(
        self,
        adapter: MCPToolAdapter,
        mock_client: MagicMock,
    ) -> None:
        """Executor возвращает ошибку при MCP ошибке."""
        from codelab.server.mcp.models import MCPCallToolResult

        mock_result = MCPCallToolResult(
            content=[{"type": "text", "text": "Error message"}],
            is_error=True,
        )
        mock_client.call_tool = AsyncMock(return_value=mock_result)

        executor = await adapter.create_executor("read_file")
        result = await executor(arg1="value1")

        assert result.success is False
        assert "Error message" in result.error

    @pytest.mark.asyncio
    async def test_executor_handles_tool_call_error(
        self,
        adapter: MCPToolAdapter,
        mock_client: MagicMock,
    ) -> None:
        """Executor обрабатывает MCPToolCallError."""
        mock_client.call_tool = AsyncMock(
            side_effect=MCPToolCallError("Tool not found")
        )

        executor = await adapter.create_executor("nonexistent")
        result = await executor()

        assert result.success is False
        assert "MCP tool call failed" in result.error

    @pytest.mark.asyncio
    async def test_executor_handles_unexpected_error(
        self,
        adapter: MCPToolAdapter,
        mock_client: MagicMock,
    ) -> None:
        """Executor обрабатывает непредвиденные ошибки."""
        mock_client.call_tool = AsyncMock(side_effect=RuntimeError("Unexpected"))

        executor = await adapter.create_executor("test")
        result = await executor()

        assert result.success is False
        assert "Unexpected error" in result.error


class TestCallTool:
    """Тесты call_tool."""

    @pytest.mark.asyncio
    async def test_call_tool_delegates_to_executor(
        self,
        adapter: MCPToolAdapter,
        mock_client: MagicMock,
    ) -> None:
        """call_tool делегирует executor."""
        from codelab.server.mcp.models import MCPCallToolResult

        mock_result = MCPCallToolResult(
            content=[{"type": "text", "text": "OK"}],
            is_error=False,
        )
        mock_client.call_tool = AsyncMock(return_value=mock_result)

        result = await adapter.call_tool("read_file", {"arg1": "value1"})

        assert result.success is True
        mock_client.call_tool.assert_awaited_once_with("read_file", {"arg1": "value1"})


class TestNamePrefixToKind:
    """Тесты маппинга префиксов."""

    def test_all_prefixes_have_valid_kinds(self) -> None:
        """Все префиксы имеют валидные kind."""
        valid_kinds = {"read", "fetch", "search", "edit", "delete", "move", "execute", "other"}
        for prefix, kind in _NAME_PREFIX_TO_KIND:
            assert kind in valid_kinds, f"Invalid kind '{kind}' for prefix '{prefix}'"

    def test_prefixes_are_lowercase(self) -> None:
        """Все префиксы в нижнем регистре."""
        for prefix, _ in _NAME_PREFIX_TO_KIND:
            assert prefix == prefix.lower(), f"Prefix '{prefix}' is not lowercase"
