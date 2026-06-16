"""Обработчики методов аутентификации.

Содержит логику обработки методов authenticate и related.
"""

from __future__ import annotations

from typing import Any

from ...messages import ACPMessage, JsonRpcId
from ..state import ClientRuntimeCapabilities


def initialize(
    request_id: JsonRpcId | None,
    params: dict[str, Any],
    supported_protocol_versions: tuple[int, ...],
    require_auth: bool,
    auth_methods: list[dict[str, Any]],
    mcp_http_enabled: bool = True,
    mcp_sse_enabled: bool = True,
) -> ACPMessage:
    """Формирует ответ на `initialize` с перечнем возможностей агента.

    Пример использования:
        response = initialize("req_1", {"protocolVersion": 1}, (1,), False, [])
    """

    # Для ACP handshake поле `protocolVersion` является обязательным.
    if "protocolVersion" not in params:
        return ACPMessage.error_response(
            request_id,
            code=-32602,
            message="Invalid params: protocolVersion is required",
        )

    requested_version = params.get("protocolVersion")
    if not isinstance(requested_version, int):
        return ACPMessage.error_response(
            request_id,
            code=-32602,
            message="Invalid params: protocolVersion must be an integer",
        )

    # По спецификации клиент обязан передать объект capabilities.
    client_capabilities = params.get("clientCapabilities")
    if not isinstance(client_capabilities, dict):
        return ACPMessage.error_response(
            request_id,
            code=-32602,
            message="Invalid params: clientCapabilities must be an object",
        )

    client_info = params.get("clientInfo")
    if client_info is not None and not isinstance(client_info, dict):
        return ACPMessage.error_response(
            request_id,
            code=-32602,
            message="Invalid params: clientInfo must be an object",
        )

    negotiated_version = supported_protocol_versions[-1]
    if isinstance(requested_version, int) and requested_version in supported_protocol_versions:
        negotiated_version = requested_version

    # Инициализация capability negotiation для ACP v1.
    result = {
        "protocolVersion": negotiated_version,
        "agentCapabilities": {
            "loadSession": True,
            "mcpCapabilities": {"http": mcp_http_enabled, "sse": mcp_sse_enabled},
            "promptCapabilities": {
                "image": False,
                "audio": False,
                "embeddedContext": False,
            },
            "sessionCapabilities": {},
        },
        "agentInfo": {
            "name": "codelab-server",
            "title": "ACP Server",
            "version": "0.1.0",
        },
        "authMethods": auth_methods if require_auth else [],
    }
    result["agentCapabilities"]["sessionCapabilities"] = {
        "list": {},
    }
    return ACPMessage.response(request_id, result)


def authenticate(
    request_id: JsonRpcId | None,
    params: dict[str, Any],
    require_auth: bool,
    auth_api_key: str | None,
    auth_methods: list[dict[str, Any]],
) -> tuple[ACPMessage, bool]:
    """Обрабатывает `authenticate` и отмечает протокольный инстанс как auth-ok.

    Возвращает (response_message, is_authenticated).

    Пример использования:
        response, authenticated = authenticate("req_1", {"methodId": "local"}, True, "key", [])
    """

    if not require_auth:
        return ACPMessage.response(request_id, {}), True

    method_id = params.get("methodId")
    if not isinstance(method_id, str):
        return (
            ACPMessage.error_response(
                request_id,
                code=-32602,
                message="Invalid params: methodId is required",
            ),
            False,
        )

    known_method_ids = {
        method.get("id")
        for method in auth_methods
        if isinstance(method, dict) and isinstance(method.get("id"), str)
    }
    if method_id not in known_method_ids:
        return (
            ACPMessage.error_response(
                request_id,
                code=-32602,
                message="Invalid params: unknown authentication method",
            ),
            False,
        )

    if auth_api_key is not None:
        api_key = params.get("apiKey")
        if not isinstance(api_key, str) or not api_key:
            return (
                ACPMessage.error_response(
                    request_id,
                    code=-32602,
                    message="Invalid params: apiKey is required",
                ),
                False,
            )
        if api_key != auth_api_key:
            return (
                ACPMessage.error_response(
                    request_id,
                    code=-32011,
                    message="auth_failed",
                ),
                False,
            )

    return ACPMessage.response(request_id, {}), True


def auth_required_error(
    request_id: JsonRpcId | None,
    auth_methods: list[dict[str, Any]],
) -> ACPMessage:
    """Строит унифицированную ошибку `auth_required` для session setup методов.

    Пример использования:
        return auth_required_error("req_1", [])
    """

    return ACPMessage.error_response(
        request_id,
        code=-32010,
        message="auth_required",
        data={"authMethods": auth_methods},
    )


def parse_client_runtime_capabilities(
    capabilities: dict[str, Any],
) -> ClientRuntimeCapabilities:
    """Преобразует payload `clientCapabilities` в внутреннюю модель.

    Пример использования:
        caps = parse_client_runtime_capabilities(
            {"fs": {"readTextFile": True}, "terminal": False},
        )
    """

    fs_payload = capabilities.get("fs") if isinstance(capabilities, dict) else None
    read_text = False
    write_text = False
    if isinstance(fs_payload, dict):
        read_text = bool(fs_payload.get("readTextFile") is True)
        write_text = bool(fs_payload.get("writeTextFile") is True)

    terminal_enabled = bool(capabilities.get("terminal") is True)
    return ClientRuntimeCapabilities(
        fs_read=read_text,
        fs_write=write_text,
        terminal=terminal_enabled,
    )
