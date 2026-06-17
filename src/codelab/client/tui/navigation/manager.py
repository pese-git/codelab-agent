"""Централизованный менеджер навигации для TUI приложения."""

import asyncio
from collections.abc import Callable
from typing import Any

import structlog
from textual.app import App
from textual.screen import ModalScreen, Screen

from .operations import NavigationOperation, OperationType
from .queue import OperationQueue, OperationQueueError
from .tracker import ModalWindowTracker

logger = structlog.get_logger(__name__)


class NavigationError(Exception):
    """Базовое исключение для навигационных ошибок."""

    pass


class ScreenStackError(NavigationError):
    """Ошибка при работе со стеком экранов."""

    pass


class ModalNotFoundError(NavigationError):
    """Модальное окно не найдено."""

    pass


class OperationTimeoutError(NavigationError):
    """Операция превысила таймаут."""

    pass


class NavigationManager:
    """Централизованный менеджер навигации для TUI приложения.

    Управляет показом и скрытием экранов, модальных окон и синхронизацией
    с ViewModels. Все операции выполняются последовательно через очередь
    с поддержкой приоритетов.
    """

    def __init__(self, app: App) -> None:
        """Инициализировать менеджер навигации.

        Args:
            app: Главное Textual приложение
        """
        self._app = app
        self._queue = OperationQueue()
        self._tracker = ModalWindowTracker()

        # Установить функцию выполнения операций
        self._queue.set_executor(self._execute_operation)

        # Подписки ViewModel для синхронизации
        self._subscriptions: dict[str, Callable[[], None]] = {}

        logger.debug("navigation_manager_initialized")

    async def show_screen(
        self,
        screen: Screen,
        modal: bool = False,
        priority: int = 1,
        callback: Callable[[Screen], None] | None = None,
    ) -> None:
        """Показать экран (screen или modal).

        Args:
            screen: Экран для отображения
            modal: True если это модальное окно (ModalScreen)
            priority: Приоритет операции (выше = выполнится раньше)
            callback: Callback после успешного показа

        Raises:
            NavigationError: Если операция невозможна
        """
        operation = NavigationOperation(
            operation_type=OperationType.SHOW_SCREEN,
            screen=screen,
            modal=modal,
            priority=priority,
            on_success=lambda: callback(screen) if callback else None,
            metadata={
                "screen_class": type(screen).__name__,
                "is_modal": modal,
            },
        )

        try:
            await self._queue.enqueue(operation)
        except OperationQueueError as e:
            logger.error(
                "show_screen_failed",
                screen_class=type(screen).__name__,
                error=str(e),
            )
            raise NavigationError(f"Failed to show screen: {e}") from e

    async def hide_screen(
        self,
        screen_or_id: Screen | str,
        result: Any = None,
        callback: Callable[[], None] | None = None,
    ) -> Any:
        """Скрыть экран (pop или dismiss в зависимости от типа).

        Args:
            screen_or_id: Экран или его ID для скрытия
            result: Результат для передачи (для ModalScreen)
            callback: Callback после успешного скрытия

        Returns:
            Результат операции

        Raises:
            NavigationError: Если операция невозможна
        """
        # Определить ID экрана
        screen_id: str | None = None
        if isinstance(screen_or_id, str):
            screen_id = screen_or_id
        else:
            # Попытаться найти ID в трекере
            screen_id = self._tracker.unregister_by_screen(screen_or_id)

        operation = NavigationOperation(
            operation_type=OperationType.HIDE_SCREEN,
            screen_id=screen_id,
            result=result,
            priority=1,
            on_success=callback,
            metadata={
                "screen_class": (
                    type(screen_or_id).__name__
                    if not isinstance(screen_or_id, str)
                    else screen_id
                ),
            },
        )

        try:
            return await self._queue.enqueue(operation)
        except OperationQueueError as e:
            logger.error(
                "hide_screen_failed",
                screen_id=screen_id,
                error=str(e),
            )
            raise NavigationError(f"Failed to hide screen: {e}") from e

    async def hide_top_screen(
        self,
        result: Any = None,
    ) -> Any:
        """Скрыть верхний экран в стеке.

        Args:
            result: Результат для передачи

        Returns:
            Результат операции
        """
        operation = NavigationOperation(
            operation_type=OperationType.HIDE_SCREEN,
            result=result,
            priority=1,
            metadata={"action": "hide_top_screen"},
        )

        try:
            return await self._queue.enqueue(operation)
        except OperationQueueError as e:
            logger.error("hide_top_screen_failed", error=str(e))
            raise NavigationError(f"Failed to hide top screen: {e}") from e

    def get_modal_by_type(self, modal_type: str) -> Screen | None:
        """Найти модальное окно по типу.

        Args:
            modal_type: Тип модального окна

        Returns:
            Найденное модальное окно или None
        """
        return self._tracker.get_modal_by_type(modal_type)

    def is_modal_visible(self, modal_type: str) -> bool:
        """Проверить видимо ли модальное окно.

        Args:
            modal_type: Тип модального окна

        Returns:
            True если модаль открыта
        """
        return self._tracker.is_modal_visible(modal_type)

    def get_screen_stack_depth(self) -> int:
        """Получить глубину стека экранов (для диагностики).

        Returns:
            Количество экранов в стеке
        """
        return len(self._app.screen_stack)

    def subscribe_to_view_model(
        self,
        view_model: Any,
        modal_type: str,
        on_show: Callable[[], None] | None = None,
        on_hide: Callable[[], None] | None = None,
    ) -> Callable[[], None]:
        """Подписать ViewModel на изменения навигации.

        Автоматически синхронизирует is_visible в ViewModel с реальным состоянием.

        Args:
            view_model: ViewModel для синхронизации (должен иметь is_visible)
            modal_type: Тип модального окна
            on_show: Callback при открытии окна
            on_hide: Callback при закрытии окна

        Returns:
            Функция для отписки
        """
        # Сохранить subscription
        subscription_key = f"view_model_{modal_type}_{id(view_model)}"

        # Флаг для предотвращения циклических обновлений
        sync_in_progress = False

        def on_visibility_changed(is_visible: bool) -> None:
            """Обработать изменение видимости в ViewModel."""
            nonlocal sync_in_progress

            # Предотвратить циклические обновления
            if sync_in_progress:
                return

            sync_in_progress = True

            try:
                if is_visible:
                    # Показать модаль
                    logger.debug(
                        "view_model_show_requested",
                        modal_type=modal_type,
                    )
                    if on_show:
                        on_show()
                else:
                    # Скрыть модаль
                    logger.debug(
                        "view_model_hide_requested",
                        modal_type=modal_type,
                    )

                    # Найти и скрыть модаль
                    modal = self.get_modal_by_type(modal_type)
                    if modal:
                        # Асинхронная операция в фоне
                        asyncio.create_task(self.hide_screen(modal))

                    if on_hide:
                        on_hide()

            finally:
                sync_in_progress = False

        # Подписаться на изменения (если есть Observable)
        if hasattr(view_model, "is_visible") and hasattr(
            view_model.is_visible, "subscribe"
        ):
            view_model.is_visible.subscribe(on_visibility_changed)

            # Вернуть функцию отписки
            def unsubscribe() -> None:
                """Отписаться от изменений ViewModel."""
                if hasattr(view_model.is_visible, "unsubscribe"):
                    view_model.is_visible.unsubscribe(on_visibility_changed)
                if subscription_key in self._subscriptions:
                    del self._subscriptions[subscription_key]
                logger.debug(
                    "view_model_unsubscribed",
                    modal_type=modal_type,
                )

            self._subscriptions[subscription_key] = unsubscribe
            return unsubscribe

        logger.warning(
            "view_model_not_observable",
            modal_type=modal_type,
            view_model_type=type(view_model).__name__,
        )
        return lambda: None

    async def reset(self) -> None:
        """Закрыть все модальные окна и вернуться в normal state.

        Выполняет reset операцию с высоким приоритетом.
        """
        operation = NavigationOperation(
            operation_type=OperationType.RESET,
            priority=2,  # Высокий приоритет для reset
            metadata={"action": "reset_all"},
        )

        try:
            await self._queue.enqueue(operation)
        except OperationQueueError as e:
            logger.error("reset_failed", error=str(e))
            raise NavigationError(f"Failed to reset: {e}") from e

    def dispose(self) -> None:
        """Очистить ресурсы менеджера (вызвать при завершении приложения)."""
        # Отписать все ViewModels (копируем для избежания RuntimeError при изменении)
        for unsubscribe in list(self._subscriptions.values()):
            unsubscribe()
        self._subscriptions.clear()

        # Очистить трекер
        self._tracker.clear()

        # Очистить очередь
        self._queue.clear()

        logger.debug("navigation_manager_disposed")

    async def _execute_operation(self, operation: NavigationOperation) -> Any:
        """Выполнить операцию навигации.

        Args:
            operation: Операция для выполнения

        Returns:
            Результат операции

        Raises:
            NavigationError: Если операция невозможна
        """
        try:
            # Выполнить операцию в зависимости от типа
            if operation.operation_type == OperationType.SHOW_SCREEN:
                await self._handle_show_screen(operation)
            elif operation.operation_type == OperationType.HIDE_SCREEN:
                await self._handle_hide_screen(operation)
            elif operation.operation_type == OperationType.RESET:
                await self._handle_reset(operation)
            else:
                raise NavigationError(
                    f"Unknown operation type: {operation.operation_type}"
                )

            return None

        except Exception as e:
            logger.error(
                "operation_execution_failed",
                operation_type=operation.operation_type.value,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            raise

    async def _handle_show_screen(self, operation: NavigationOperation) -> None:
        """Показать экран.

        Args:
            operation: Операция show_screen

        Raises:
            ScreenStackError: Если невозможно показать экран
        """
        if operation.screen is None:
            raise ScreenStackError("Screen is None for SHOW_SCREEN operation")

        try:
            # Зарегистрировать модаль если нужно
            if operation.modal and isinstance(operation.screen, ModalScreen):
                modal_type = operation.metadata.get(
                    "screen_class", type(operation.screen).__name__
                )
                self._tracker.register_modal(operation.screen, modal_type)

            # Показать экран
            self._app.push_screen(operation.screen)

            logger.debug(
                "screen_shown",
                screen_class=type(operation.screen).__name__,
                is_modal=operation.modal,
                stack_depth=len(self._app.screen_stack),
            )

            # Небольшая задержка для синхронизации
            await asyncio.sleep(0.01)

        except Exception as e:
            # Отменить регистрацию если что-то пошло не так
            if operation.modal:
                self._tracker.unregister_by_screen(operation.screen)

            raise ScreenStackError(f"Failed to show screen: {e}") from e

    async def _handle_hide_screen(self, operation: NavigationOperation) -> Any:
        """Скрыть экран.

        Args:
            operation: Операция hide_screen

        Returns:
            Результат (для ModalScreen)

        Raises:
            ScreenStackError: Если невозможно скрыть экран
        """
        try:
            # Получить верхний экран со стека
            if not self._app.screen_stack:
                raise ScreenStackError("Screen stack is empty")

            top_screen = self._app.screen_stack[-1]

            # Отменить регистрацию из трекера
            self._tracker.unregister_by_screen(top_screen)

            # Закрыть экран
            if isinstance(top_screen, ModalScreen):
                # Для ModalScreen используем dismiss
                result = operation.result
                top_screen.dismiss(result)
            else:
                # Для обычного Screen используем pop_screen
                self._app.pop_screen()

            logger.debug(
                "screen_hidden",
                screen_class=type(top_screen).__name__,
                stack_depth=len(self._app.screen_stack),
            )

            # Небольшая задержка для синхронизации
            await asyncio.sleep(0.01)

            return operation.result

        except ScreenStackError:
            raise
        except Exception as e:
            raise ScreenStackError(f"Failed to hide screen: {e}") from e

    async def _handle_reset(self, operation: NavigationOperation) -> None:
        """Выполнить reset (закрыть все модальные окна).

        Args:
            operation: Операция reset
        """
        try:
            # Получить все открытые модали
            all_modals = self._tracker.get_all_modals()

            # Закрыть все модали
            for modal_id, modal_type, screen in reversed(all_modals):
                try:
                    self._tracker.unregister_modal(modal_id)
                    if isinstance(screen, ModalScreen):
                        screen.dismiss(None)
                    else:
                        self._app.pop_screen()
                except Exception as e:
                    logger.warning(
                        "reset_close_modal_failed",
                        modal_id=modal_id,
                        modal_type=modal_type,
                        error=str(e),
                    )

            # Очистить трекер
            self._tracker.clear()

            logger.debug(
                "reset_completed",
                modals_closed=len(all_modals),
            )

            await asyncio.sleep(0.01)

        except Exception as e:
            raise NavigationError(f"Failed to reset navigation: {e}") from e
