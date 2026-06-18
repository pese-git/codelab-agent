"""Модуль декомпозиции ChatViewModel.

Содержит специализированные компоненты для обработки обновлений сессии,
сохранения истории и выполнения callback'ов.

Архитектура:
- contracts: Protocol интерфейсы для слабой связанности
- dispatcher: SessionUpdateDispatcher для маршрутизации обновлений
- handlers: Strategy handlers для каждого типа обновления
- persistence: FileChatPersistence для async-safe сохранения
- executors: FsCallbackExecutor и TerminalCallbackExecutor
"""

from codelab.client.presentation.chat.chat_session_state import ChatSessionState
from codelab.client.presentation.chat.context import ChatUpdateContext
from codelab.client.presentation.chat.contracts import (
    ChatPersistencePort,
    ChatUpdateSink,
    SessionUpdateHandler,
)

__all__ = [
    "ChatSessionState",
    "ChatUpdateContext",
    "ChatPersistencePort",
    "ChatUpdateSink",
    "SessionUpdateHandler",
]
