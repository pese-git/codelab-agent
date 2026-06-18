"""Адаптер для PermissionManager, проверяющий разрешения для tool execution."""

from __future__ import annotations

import structlog

from codelab.server.protocol.handlers.permission_manager import PermissionManager
from codelab.server.protocol.state import SessionState

logger = structlog.get_logger()


class PermissionChecker:
    """Адаптер для проверки разрешений через PermissionManager.
    
    Задачи:
    - Определять, нужно ли запрашивать разрешение перед execution
    - Получать remembered permissions
    - Логирование всех проверок
    """

    def __init__(self, permission_manager: PermissionManager) -> None:
        """Инициализировать checker с PermissionManager.
        
        Args:
            permission_manager: Экземпляр PermissionManager для проверки разрешений.
        """
        self._manager = permission_manager

    def should_request_permission(
        self,
        session: SessionState,
        tool_kind: str,
    ) -> bool:
        """Определить, нужно ли запрашивать разрешение для tool kind.
        
        Args:
            session: Состояние сессии.
            tool_kind: Категория инструмента (read, write, execute, delete).
            
        Returns:
            True если нужно запросить разрешение, False если разрешение запомнено.
        """
        should_ask = self._manager.should_request_permission(session, tool_kind)
        
        logger.debug(
            "Проверка разрешения для tool kind",
            extra={
                "session_id": session.session_id,
                "tool_kind": tool_kind,
                "should_request": should_ask,
            },
        )
        
        return should_ask

    def get_remembered_permission(
        self,
        session: SessionState,
        tool_kind: str,
    ) -> str:
        """Получить запомненное разрешение для tool kind.
        
        Args:
            session: Состояние сессии.
            tool_kind: Категория инструмента.
            
        Returns:
            'allow' если permission_policy['tool_kind'] == 'allow_always',
            'reject' если permission_policy['tool_kind'] == 'reject_always',
            'ask' если разрешение не установлено.
        """
        decision = self._manager.get_remembered_permission(session, tool_kind)
        
        logger.debug(
            "Получение запомненного разрешения",
            extra={
                "session_id": session.session_id,
                "tool_kind": tool_kind,
                "decision": decision,
            },
        )
        
        return decision
