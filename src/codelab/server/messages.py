"""Реэкспорт модуля сообщений из shared для server."""

from codelab.shared.messages import (
    ACPMessage,
    JsonRpcError,
    JsonRpcId,
)

__all__ = ["ACPMessage", "JsonRpcError", "JsonRpcId"]
