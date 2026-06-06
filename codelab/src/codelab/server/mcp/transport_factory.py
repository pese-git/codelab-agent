"""Фабрика MCP транспортов и единый протокол.

Модуль определяет единый интерфейс для всех MCP транспортов
и фабрику для их создания на основе конфигурации.
"""

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from .models import MCPServerConfig
from .transport import HttpTransport, SseTransport, StdioTransport


@runtime_checkable
class MCPTransport(Protocol):
    """Единый протокол для всех MCP транспортов.
    
    Все транспорты (stdio, http, sse) реализуют этот интерфейс,
    что позволяет использовать их единообразно в клиенте.
    """
    
    @property
    def is_connected(self) -> bool:
        """Проверить, установлено ли соединение."""
        ...
    
    async def connect(self) -> None:
        """Установить соединение с MCP сервером."""
        ...
    
    async def send_request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Отправить JSON-RPC запрос и дождаться ответа.
        
        Args:
            method: Имя вызываемого метода.
            params: Параметры запроса.
            timeout: Таймаут ожидания ответа в секундах.
        
        Returns:
            Результат из ответа (поле result).
        """
        ...
    
    async def send_notification(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> None:
        """Отправить JSON-RPC уведомление.
        
        Args:
            method: Имя метода уведомления.
            params: Параметры уведомления.
        """
        ...
    
    async def close(self) -> None:
        """Закрыть соединение с MCP сервером."""
        ...
    
    def register_notification_handler(
        self, method: str, handler: Callable
    ) -> None:
        """Зарегистрировать обработчик notification.
        
        Args:
            method: Имя метода notification (или "*" для всех).
            handler: Функция-обработчик (async или sync).
        """
        ...


class TransportFactory:
    """Фабрика для создания MCP транспортов.
    
    Устраняет if/elif цепочки в клиенте, следуя принципу OCP.
    Клиент использует фабрику для создания нужного транспорта
    на основе конфигурации MCPServerConfig.
    """
    
    @staticmethod
    def create(config: MCPServerConfig) -> MCPTransport:
        """Создать транспорт по конфигурации.
        
        Args:
            config: Конфигурация MCP сервера.
        
        Returns:
            Экземпляр транспорта, реализующий MCPTransport.
        
        Raises:
            ValueError: Если тип транспорта не поддерживается 
                       или отсутствуют обязательные параметры.
        """
        if config.type == "stdio":
            if not config.command:
                raise ValueError("Stdio transport requires 'command'")
            return StdioTransport(
                command=config.command,
                args=config.args,
                env=config.get_env_dict() or None,
            )
        
        if config.type == "http":
            if not config.url:
                raise ValueError("HTTP transport requires 'url'")
            return HttpTransport(
                url=config.url,
                headers=config.headers,
            )
        
        if config.type == "sse":
            if not config.url:
                raise ValueError("SSE transport requires 'url'")
            return SseTransport(
                url=config.url,
                headers=config.headers,
            )
        
        raise ValueError(f"Unsupported transport type: {config.type}")
