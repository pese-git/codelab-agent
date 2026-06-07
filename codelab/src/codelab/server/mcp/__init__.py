"""MCP (Model Context Protocol) интеграция для ACP сервера.

Этот модуль реализует клиентскую часть MCP протокола для подключения
к внешним MCP серверам и использования их инструментов.

Основные компоненты:
- MCPClient: Клиент для взаимодействия с MCP сервером
- Транспорты: StdioTransport, HttpTransport, SseTransport
- Модели данных для MCP протокола

Example:
    >>> from codelab.server.mcp import MCPClient, MCPServerConfig
    >>> 
    >>> config = MCPServerConfig(
    ...     name="filesystem",
    ...     command="mcp-server-filesystem",
    ...     args=["--stdio"]
    ... )
    >>> 
    >>> async with MCPClient(config) as client:
    ...     tools = await client.list_tools()
    ...     result = await client.call_tool("read_file", {"path": "/tmp/test.txt"})
"""

from .client import (
    MCPClient,
    MCPClientError,
    MCPClientState,
    MCPInitializeError,
    MCPToolCallError,
)
from .content_mapper import (
    ContentMapperError,
    extract_text_from_acp_content,
    mcp_content_item_to_acp,
    mcp_content_to_acp_list,
    mcp_embedded_to_acp,
    mcp_image_to_acp,
    mcp_text_to_acp,
)
from .manager import (
    MCPManager,
    MCPManagerError,
    MCPServerAlreadyExistsError,
    MCPServerNotFoundError,
)
from .models import (
    MCPAnnotations,
    MCPCallToolParams,
    MCPCallToolResult,
    MCPCapabilities,
    MCPClientCapabilities,
    MCPClientInfo,
    MCPContent,
    MCPEmbeddedResource,
    MCPError,
    MCPGetPromptParams,
    MCPGetPromptResult,
    MCPImageContent,
    MCPInitializeParams,
    MCPInitializeResult,
    MCPListPromptsParams,
    MCPListPromptsResult,
    MCPListResourcesParams,
    MCPListResourcesResult,
    MCPListResourceTemplatesParams,
    MCPListResourceTemplatesResult,
    MCPListToolsResult,
    MCPNotification,
    MCPProgressNotification,
    MCPPrompt,
    MCPPromptArgument,
    MCPPromptMessage,
    MCPReadResourceParams,
    MCPReadResourceResult,
    MCPRequest,
    MCPResource,
    MCPResourceContent,
    MCPResourceIcon,
    MCPResourceTemplate,
    MCPResponse,
    MCPRoot,
    MCPServerConfig,
    MCPServerInfo,
    MCPTextContent,
    MCPTool,
    MCPToolInputSchema,
)
from .prompt_mapper import (
    mcp_prompt_to_available_command,
    mcp_prompts_to_available_commands,
)
from .resource_mapper import (
    mcp_resource_to_resource_link,
    mcp_resources_to_resource_links,
)
from .tool_adapter import MCPToolAdapter
from .transport import (
    HttpConnectionError,
    HttpTimeoutError,
    HttpTransport,
    HttpTransportError,
    ProcessExitedError,
    ProcessNotStartedError,
    SseTransport,
    SseTransportError,
    StdioTransport,
    StdioTransportError,
)
from .transport_factory import MCPTransport, TransportFactory

__all__ = [
    # Client
    "MCPClient",
    "MCPClientError",
    "MCPClientState",
    "MCPInitializeError",
    "MCPToolCallError",
    # Manager
    "MCPManager",
    "MCPManagerError",
    "MCPServerAlreadyExistsError",
    "MCPServerNotFoundError",
    # Tool Adapter
    "MCPToolAdapter",
    # Content Mapper
    "ContentMapperError",
    "mcp_text_to_acp",
    "mcp_image_to_acp",
    "mcp_embedded_to_acp",
    "mcp_content_item_to_acp",
    "mcp_content_to_acp_list",
    "extract_text_from_acp_content",
    # Resource Mapper
    "mcp_resource_to_resource_link",
    "mcp_resources_to_resource_links",
    # Prompt Mapper
    "mcp_prompt_to_available_command",
    "mcp_prompts_to_available_commands",
    # Transport
    "MCPTransport",
    "TransportFactory",
    "StdioTransport",
    "StdioTransportError",
    "ProcessNotStartedError",
    "ProcessExitedError",
    "HttpTransport",
    "HttpTransportError",
    "HttpConnectionError",
    "HttpTimeoutError",
    "SseTransport",
    "SseTransportError",
    # Models - core JSON-RPC
    "MCPRequest",
    "MCPResponse",
    "MCPNotification",
    "MCPError",
    # Models - Server Info
    "MCPServerConfig",
    "MCPServerInfo",
    "MCPClientInfo",
    "MCPCapabilities",
    "MCPInitializeParams",
    "MCPInitializeResult",
    # Models - Tools
    "MCPTool",
    "MCPToolInputSchema",
    "MCPListToolsResult",
    "MCPCallToolParams",
    "MCPCallToolResult",
    # Models - Content
    "MCPContent",
    "MCPTextContent",
    "MCPImageContent",
    "MCPEmbeddedResource",
    # Models - Resources
    "MCPAnnotations",
    "MCPResourceIcon",
    "MCPResource",
    "MCPResourceTemplate",
    "MCPListResourcesParams",
    "MCPListResourcesResult",
    "MCPListResourceTemplatesParams",
    "MCPListResourceTemplatesResult",
    "MCPReadResourceParams",
    "MCPReadResourceResult",
    "MCPResourceContent",
    # Models - Prompts
    "MCPPrompt",
    "MCPPromptArgument",
    "MCPPromptMessage",
    "MCPListPromptsParams",
    "MCPListPromptsResult",
    "MCPGetPromptParams",
    "MCPGetPromptResult",
    # Models - Progress
    "MCPProgressNotification",
    # Models - Roots
    "MCPRoot",
    "MCPClientCapabilities",
]
