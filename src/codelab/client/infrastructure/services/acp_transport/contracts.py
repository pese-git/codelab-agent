"""Protocol интерфейсы для RPC обработчиков."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class RpcHandler(Protocol):
    """Protocol для обработки входящих RPC запросов от сервера.

    Каждый обработчик отвечает за один или несколько методов RPC.
    Диспетчер находит подходящий обработчик по method name.
    """

    def can_handle(self, method: str) -> bool:
        """Проверяет, может ли handler обработать этот метод RPC.

        Args:
            method: Имя метода RPC (например, "fs/read_text_file")

        Returns:
            True если handler может обработать этот метод
        """
        ...

    async def handle(
        self, rpc_id: str | int, params: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Обрабатывает RPC запрос.

        Args:
            rpc_id: Идентификатор запроса
            params: Параметры запроса

        Returns:
            Dict с результатом при успехе,
            или {"error": {"code": N, "message": "..."}} при ошибке,
            или None для пустого ответа
        """
        ...


__all__ = ["RpcHandler"]
