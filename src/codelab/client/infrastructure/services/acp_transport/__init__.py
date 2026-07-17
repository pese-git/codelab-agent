"""Infrastructure для ACP транспорта.

Модуль содержит компоненты для обработки входящих RPC запросов от сервера:
- ClientRpcDispatcher - диспетчер RPC запросов
- RpcHandler - Protocol для обработчиков
- Обработчики для fs/* и terminal/* методов
"""

from codelab.client.infrastructure.services.acp_transport.client_rpc_dispatcher import (
    ClientRpcDispatcher,
)
from codelab.client.infrastructure.services.acp_transport.contracts import RpcHandler
from codelab.client.infrastructure.services.acp_transport.handlers import (
    FsReadHandler,
    FsWriteHandler,
    TerminalCreateHandler,
    TerminalKillHandler,
    TerminalOutputHandler,
    TerminalReleaseHandler,
    TerminalWaitHandler,
)
from codelab.client.infrastructure.services.acp_transport.permission_responder import (
    PermissionResponder,
)
from codelab.client.infrastructure.services.acp_transport.request_callback_coordinator import (
    RequestCallbackCoordinator,
)

__all__ = [
    "ClientRpcDispatcher",
    "RpcHandler",
    "PermissionResponder",
    "RequestCallbackCoordinator",
    "FsReadHandler",
    "FsWriteHandler",
    "TerminalCreateHandler",
    "TerminalOutputHandler",
    "TerminalWaitHandler",
    "TerminalReleaseHandler",
    "TerminalKillHandler",
]
