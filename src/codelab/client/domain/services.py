"""Domain Services интерфейсы - абстракции для бизнес-операций.

Содержит:
- TransportService - низкоуровневая коммуникация с сервером
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any


class TransportService(ABC):
    """Service для низкоуровневой коммуникации с ACP сервером.

    Инкапсулирует детали транспорта (WebSocket, TCP и т.д.)
    и предоставляет единый интерфейс для отправки и получения сообщений.
    """

    @abstractmethod
    async def connect(self) -> None:
        """Устанавливает соединение с сервером.

        Raises:
            TransportError: При ошибке подключения
        """
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Разрывает соединение с сервером."""
        ...

    @abstractmethod
    async def send(self, message: dict[str, Any]) -> None:
        """Отправляет сообщение на сервер.

        Аргументы:
            message: JSON-RPC сообщение

        Raises:
            TransportError: При ошибке отправки
        """
        ...

    @abstractmethod
    async def receive(self, request_id: str | int | None = None) -> dict[str, Any]:
        """Получает одно сообщение с сервера.

        Это блокирующая операция, ожидающая сообщение.

        Аргументы:
            request_id: Опциональный ID запроса для маршрутизации ответа

        Возвращает:
            JSON-RPC сообщение из сервера

        Raises:
            TransportError: При ошибке получения
        """
        ...

    @abstractmethod
    def listen(self) -> AsyncIterator[dict[str, Any]]:
        """Слушает входящие сообщения с сервера.

        Возвращает асинхронный итератор, который выдает
        сообщения по мере их поступления с сервера.

        Yields:
            JSON-RPC сообщения из сервера
        """
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """Проверяет наличие активного соединения.

        Возвращает:
            True если соединение активно
        """
        ...

    @abstractmethod
    def set_server_capabilities(self, capabilities: dict[str, Any]) -> None:
        """Сохраняет capabilities сервера после инициализации.

        Аргументы:
            capabilities: Словарь с возможностями сервера
        """
        ...

    @abstractmethod
    def get_server_capabilities(self) -> dict[str, Any]:
        """Возвращает сохраненные capabilities сервера.

        Возвращает:
            Словарь с возможностями сервера

        Raises:
            RuntimeError: Если сервер не инициализирован
        """
        ...

    @abstractmethod
    def is_initialized(self) -> bool:
        """Проверяет, была ли выполнена инициализация.

        Возвращает:
            True если сервер инициализирован и capabilities сохранены
        """
        ...

    async def cancel_prompt(self, session_id: str) -> None:
        """Cancel current prompt without blocking the callback lock.

        Default falls back to request_with_callbacks for compatibility.
        Concrete transports should override this with a lock-free implementation.
        """
        await self.request_with_callbacks(
            method="session/cancel",
            params={"sessionId": session_id},
        )

    async def set_config_option(
        self,
        session_id: str,
        config_id: str,
        value: str,
    ) -> dict[str, Any]:
        """Установить конфигурационную опцию сессии.

        Args:
            session_id: ID сессии
            config_id: ID конфигурационной опции
            value: Новое значение

        Returns:
            Результат с обновлёнными configOptions
        """
        return await self.request_with_callbacks(
            method="session/set_config_option",
            params={
                "sessionId": session_id,
                "configId": config_id,
                "value": value,
            },
        )

    @abstractmethod
    async def request_with_callbacks(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        on_update: Any = None,
    ) -> dict[str, Any]:
        """Выполняет request с обработкой session/update и входящих server->client RPC.

        Входящие RPC (fs/*, terminal/*) обрабатываются транспортом через
        ClientRpcDispatcher; отдельные callbacks для них не требуются.

        Аргументы:
            method: Метод для вызова
            params: Параметры метода
            on_update: Callback для session/update

        Возвращает:
            Финальный ответ на request

        Raises:
            TransportError: При ошибке выполнения
        """
        ...
