"""SessionListCommandHandler - обработчик метода session/list.

Возвращает список существующих сессий с поддержкой пагинации.
"""

from __future__ import annotations

import structlog

from ...messages import ACPMessage
from ...storage import SessionStorage
from ..handlers import session
from ..state import ProtocolOutcome

logger = structlog.get_logger()


class SessionListCommandHandler:
    """Обработчик метода session/list.

    Отвечает за:
    - Возврат списка сессий с поддержкой cursor-based пагинации
    - Фильтрацию по working directory (опционально)

    Attributes:
        method_name: Имя обрабатываемого метода.
    """

    method_name = "session/list"

    def __init__(
        self,
        storage: SessionStorage,
        page_size: int = 50,
    ) -> None:
        """Инициализирует обработчик.

        Args:
            storage: Хранилище сессий.
            page_size: Размер страницы для пагинации.
        """
        self._storage = storage
        self._page_size = page_size

    async def handle(self, message: ACPMessage) -> ProtocolOutcome:
        """Обрабатывает метод session/list.

        Args:
            message: Входящее JSON-RPC сообщение.

        Returns:
            ProtocolOutcome со списком сессий.
        """
        params = message.params or {}
        response = await session.session_list(
            message.id,
            params,
            self._storage,
            self._page_size,
        )
        return ProtocolOutcome(response=response)
