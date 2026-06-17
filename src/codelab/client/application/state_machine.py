"""State Machine для управления состоянием UI приложения.

Реализует паттерн State Machine для строго контролируемых переходов
между состояниями приложения. Предотвращает некорректные переходы
и уведомляет об изменениях состояния.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

import structlog


class UIState(Enum):
    """Состояния UI приложения.
    
    Определяет все возможные состояния, в которых может находиться
    приложение во время взаимодействия с пользователем.
    """
    
    INITIALIZING = "initializing"
    """Инициализация соединения с сервером."""
    
    READY = "ready"
    """Готово к работе, ожидание ввода пользователя."""
    
    PROCESSING_PROMPT = "processing_prompt"
    """Обработка prompt от пользователя."""
    
    WAITING_PERMISSION = "waiting_permission"
    """Ожидание разрешения пользователя на действие."""
    
    CANCELLING = "cancelling"
    """Отмена текущей операции."""
    
    RECONNECTING = "reconnecting"
    """Переподключение к серверу."""
    
    ERROR = "error"
    """Состояние ошибки."""


class StateTransitionError(Exception):
    """Ошибка при попытке недопустимого перехода состояния."""
    
    pass


@dataclass
class StateChange:
    """Изменение состояния приложения.
    
    Содержит информацию о переходе из одного состояния в другое.
    """
    
    from_state: UIState
    """Исходное состояние."""
    
    to_state: UIState
    """Новое состояние."""
    
    reason: str | None = None
    """Причина изменения состояния."""
    
    metadata: dict[str, Any] | None = None
    """Дополнительные данные, связанные с изменением."""


class UIStateMachine:
    """State Machine для управления состоянием UI.
    
    Контролирует допустимые переходы между состояниями и уведомляет
    слушателей об изменениях состояния.
    """
    
    # Карта допустимых переходов из каждого состояния
    _TRANSITIONS: dict[UIState, set[UIState]] = {
        UIState.INITIALIZING: {UIState.READY, UIState.ERROR, UIState.RECONNECTING},
        UIState.READY: {
            UIState.PROCESSING_PROMPT,
            UIState.WAITING_PERMISSION,
            UIState.CANCELLING,
            UIState.RECONNECTING,
            UIState.ERROR,
        },
        UIState.PROCESSING_PROMPT: {
            UIState.READY,
            UIState.WAITING_PERMISSION,
            UIState.CANCELLING,
            UIState.RECONNECTING,
            UIState.ERROR,
        },
        UIState.WAITING_PERMISSION: {
            UIState.PROCESSING_PROMPT,
            UIState.READY,
            UIState.ERROR,
            UIState.RECONNECTING,
            UIState.CANCELLING,
        },
        UIState.CANCELLING: {UIState.READY, UIState.RECONNECTING, UIState.ERROR},
        UIState.RECONNECTING: {UIState.READY, UIState.ERROR},
        UIState.ERROR: {UIState.RECONNECTING, UIState.READY},
    }
    
    def __init__(self, initial_state: UIState = UIState.INITIALIZING) -> None:
        """Инициализирует State Machine.
        
        Аргументы:
            initial_state: Начальное состояние (по умолчанию INITIALIZING)
        """
        self._current_state = initial_state
        self._listeners: list[Callable[[StateChange], None]] = []
        self._logger = structlog.get_logger("ui_state_machine")
    
    @property
    def current_state(self) -> UIState:
        """Возвращает текущее состояние.
        
        Возвращает:
            Текущее состояние UI
        """
        return self._current_state
    
    def can_transition(self, target_state: UIState) -> bool:
        """Проверяет возможность перехода в новое состояние.
        
        Аргументы:
            target_state: Целевое состояние
        
        Возвращает:
            True если переход допустим, False иначе
        """
        if self._current_state == target_state:
            return False  # Не переходим в то же состояние
        
        allowed_transitions = self._TRANSITIONS.get(self._current_state, set())
        return target_state in allowed_transitions
    
    def transition(
        self,
        target_state: UIState,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> StateChange:
        """Переводит State Machine в новое состояние.
        
        Аргументы:
            target_state: Целевое состояние
            reason: Причина изменения (опционально)
            metadata: Дополнительные данные (опционально)
        
        Возвращает:
            Объект StateChange с информацией о переходе
        
        Raises:
            StateTransitionError: Если переход не допустим
        """
        if not self.can_transition(target_state):
            msg = (
                f"Invalid transition: {self._current_state.value} -> "
                f"{target_state.value}"
            )
            self._logger.error("invalid_transition", error=msg)
            raise StateTransitionError(msg)
        
        # Создаем объект изменения состояния
        state_change = StateChange(
            from_state=self._current_state,
            to_state=target_state,
            reason=reason,
            metadata=metadata,
        )
        
        # Обновляем текущее состояние
        self._current_state = target_state
        
        self._logger.info(
            "state_changed",
            from_state=state_change.from_state.value,
            to_state=state_change.to_state.value,
            reason=reason,
        )
        
        # Уведомляем слушателей
        self._notify_listeners(state_change)
        
        return state_change
    
    def on_state_change(self, listener: Callable[[StateChange], None]) -> None:
        """Регистрирует слушателя на изменение состояния.
        
        Аргументы:
            listener: Функция, вызываемая при изменении состояния
        """
        self._listeners.append(listener)
    
    def remove_listener(self, listener: Callable[[StateChange], None]) -> None:
        """Удаляет слушателя.
        
        Аргументы:
            listener: Функция слушателя для удаления
        """
        if listener in self._listeners:
            self._listeners.remove(listener)
    
    def _notify_listeners(self, state_change: StateChange) -> None:
        """Уведомляет всех слушателей об изменении состояния.
        
        Аргументы:
            state_change: Объект изменения состояния
        """
        for listener in self._listeners:
            try:
                listener(state_change)
            except Exception as e:
                self._logger.error(
                    "listener_error",
                    error=str(e),
                    listener=getattr(listener, "__name__", "<unknown>"),
                )
    
    def reset(self, initial_state: UIState = UIState.INITIALIZING) -> None:
        """Сбрасывает State Machine в начальное состояние.
        
        Аргументы:
            initial_state: Состояние для сброса (по умолчанию INITIALIZING)
        """
        self._current_state = initial_state
        self._logger.info("state_machine_reset", initial_state=initial_state.value)
