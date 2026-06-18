"""Состояние чата для одной сессии.

ChatSessionState хранит все данные чата для конкретной сессии:
- messages: история сообщений
- tool_calls: список вызовов инструментов
- streaming_text: текущий текст потоковой передачи
- replay_updates: обновления для восстановления состояния
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatSessionState:
    """Состояние чата, привязанное к конкретной сессии.

    Содержит все данные необходимые для отображения чата
    и восстановления состояния после перезапуска.

    Attributes:
        messages: История сообщений с role и content
        tool_calls: Список вызовов инструментов с их статусами
        pending_permissions: Ожидающие разрешения (для обратной совместимости)
        streaming_text: Текущий текст потоковой передачи
        is_streaming: Флаг активной потоковой передачи
        last_stop_reason: Причина остановки последнего prompt
        replay_updates: Обновления для восстановления состояния
    """

    messages: list[dict[str, str]] = field(default_factory=list)
    """История сообщений. Каждое сообщение имеет 'role' и 'content'."""

    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    """Список вызовов инструментов. Каждый tool call имеет:
    - toolCallId: уникальный ID
    - title: название инструмента
    - status: статус (pending, in_progress, completed, failed)
    - kind: тип инструмента (read, edit, execute, etc.)
    """

    pending_permissions: list[Any] = field(default_factory=list)
    """Ожидающие разрешения. Для обратной совместимости."""

    streaming_text: str = ""
    """Текущий текст потоковой передачи от агента."""

    is_streaming: bool = False
    """Флаг активной потоковой передачи."""

    last_stop_reason: str | None = None
    """Причина остановки последнего prompt (end_turn, tool_use, etc.)."""

    replay_updates: list[dict[str, Any]] = field(default_factory=list)
    """Сырые обновления session/update для восстановления состояния.
    Используются при загрузке сессии для воспроизведения истории.
    """

    def clear(self) -> None:
        """Очищает все данные состояния."""
        self.messages.clear()
        self.tool_calls.clear()
        self.pending_permissions.clear()
        self.streaming_text = ""
        self.is_streaming = False
        self.last_stop_reason = None
        # replay_updates не очищаем - они нужны для восстановления

    def add_message(self, role: str, content: str) -> None:
        """Добавляет сообщение в историю.

        Args:
            role: Роль отправителя (user, assistant, system)
            content: Текст сообщения
        """
        self.messages.append({"role": role, "content": content})

    def append_streaming_text(self, text: str) -> None:
        """Добавляет текст к потоковому выводу.

        Args:
            text: Текст для добавления
        """
        self.streaming_text += text
        self.is_streaming = True

    def finalize_streaming(self) -> None:
        """Завершает потоковую передачу и сохраняет текст в историю.

        Если есть накопленный streaming_text, добавляет его как сообщение
        от ассистента и очищает буфер.
        """
        if self.streaming_text:
            self.add_message("assistant", self.streaming_text)
            self.streaming_text = ""
        self.is_streaming = False

    def update_tool_call(self, tool_call_id: str, **updates: Any) -> None:
        """Обновляет существующий tool call.

        Args:
            tool_call_id: ID tool call для обновления
            **updates: Поля для обновления (status, title, etc.)
        """
        for tc in self.tool_calls:
            if tc.get("toolCallId") == tool_call_id:
                tc.update(updates)
                return

    def add_tool_call(self, tool_call: dict[str, Any]) -> None:
        """Добавляет новый tool call.

        Args:
            tool_call: Данные tool call с toolCallId, title, status, kind
        """
        self.tool_calls.append(tool_call)
