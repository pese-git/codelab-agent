"""Protocol интерфейсы для слабой связанности компонентов.

Содержит контракты для:
- SessionUpdateHandler: Strategy для обработки session/update
- ChatPersistencePort: Абстракция для сохранения истории
- ChatUpdateSink: Абстракция для синхронизации Observable
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from codelab.client.presentation.chat.context import ChatUpdateContext


@runtime_checkable
class SessionUpdateHandler(Protocol):
    """Strategy для обработки конкретного типа session/update.

    Каждый обработчик отвечает за один или несколько типов обновлений.
    Dispatcher находит подходящий обработчик по update_type.
    """

    def can_handle(self, update_type: str) -> bool:
        """Проверяет, может ли handler обработать этот тип update.

        Args:
            update_type: Тип обновления из update.sessionUpdate

        Returns:
            True если handler может обработать этот тип
        """
        ...

    def handle(self, update_data: dict[str, Any], context: ChatUpdateContext) -> None:
        """Обрабатывает update. Может модифицировать context.state.

        Args:
            update_data: Полные данные обновления от сервера
            context: Контекст с состоянием и сервисами
        """
        ...


@runtime_checkable
class ChatPersistencePort(Protocol):
    """Порт для persistence истории чата.

    Абстракция позволяет заменить файловое хранилище на SQLite/Redis
    без изменения ChatViewModel.
    """

    async def save_messages(
        self,
        session_id: str,
        messages: list[dict[str, str]],
        replay_updates: list[dict[str, Any]] | None = None,
    ) -> None:
        """Сохраняет сообщения и replay updates.

        Args:
            session_id: ID сессии
            messages: Список сообщений с role и content
            replay_updates: Опциональные replay updates для восстановления
        """
        ...

    async def load_messages(self, session_id: str) -> list[dict[str, str]]:
        """Загружает сообщения для сессии.

        Args:
            session_id: ID сессии

        Returns:
            Список сообщений или пустой список если не найдено
        """
        ...

    async def load_replay_updates(self, session_id: str) -> list[dict[str, Any]]:
        """Загружает replay updates для сессии.

        Args:
            session_id: ID сессии

        Returns:
            Список replay updates или пустой список если не найдено
        """
        ...


@runtime_checkable
class ChatUpdateSink(Protocol):
    """Абстракция для обновления Observable свойств.

    Handlers не знают про Observable, только про sink.
    Это позволяет тестировать handlers изолированно.
    """

    def sync_messages(self, session_id: str, messages: list[dict[str, str]]) -> None:
        """Синхронизирует сообщения с UI.

        Args:
            session_id: ID сессии
            messages: Обновлённый список сообщений
        """
        ...

    def sync_tool_calls(
        self, session_id: str, tool_calls: list[dict[str, Any]]
    ) -> None:
        """Синхронизирует tool calls с UI.

        Args:
            session_id: ID сессии
            tool_calls: Обновлённый список tool calls
        """
        ...

    def sync_streaming(
        self, session_id: str, text: str, is_streaming: bool
    ) -> None:
        """Синхронизирует streaming текст с UI.

        Args:
            session_id: ID сессии
            text: Текущий streaming текст
            is_streaming: Флаг активной потоковой передачи
        """
        ...


__all__ = [
    "SessionUpdateHandler",
    "ChatPersistencePort",
    "ChatUpdateSink",
]
