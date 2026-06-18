"""ChatViewModel для управления чатом и prompt-turn.

Отвечает за:
- Управление сообщениями и tool calls в чате
- Отправку prompts и обработку responses
- Обработку разрешений пользователя
- Отслеживание статуса streaming
"""

import asyncio
from dataclasses import dataclass
from typing import Any

from codelab.client.presentation.base_view_model import BaseViewModel
from codelab.client.presentation.chat.chat_session_state import ChatSessionState
from codelab.client.presentation.observable import Observable, ObservableCommand


@dataclass
class PermissionRequest:
    """Запрос разрешения от сервера."""

    request_id: str
    session_id: str
    action: str
    resource: str
    description: str = ""


class ChatViewModel(BaseViewModel):
    """ViewModel для управления чатом в активной сессии.

    Хранит состояние чата:
    - messages: история сообщений
    - tool_calls: список tool calls
    - pending_permissions: запросы разрешений в ожидании
    - is_streaming: флаг активного streaming

    Пример использования:
        >>> coordinator = SessionCoordinator(...)
        >>> vm = ChatViewModel(coordinator, event_bus)
        >>>
        >>> # Подписаться на сообщения
        >>> vm.messages.subscribe(lambda m: print(f"Messages: {m}"))
        >>>
        >>> # Отправить prompt
        >>> await vm.send_prompt_cmd.execute("session_1", "Привет!")
        >>>
        >>> # Обработать разрешение
        >>> await vm.approve_permission_cmd.execute(
        ...     "session_1",
        ...     "permission_123",
        ...     approved=True
        ... )
    """

    def __init__(
        self,
        coordinator: Any,  # SessionCoordinator
        event_bus: Any | None = None,
        logger: Any | None = None,
        plan_vm: Any | None = None,  # PlanViewModel для обработки plan updates
        # Компоненты декомпозиции
        session_update_dispatcher: Any | None = None,  # SessionUpdateDispatcher
        chat_persistence: Any | None = None,  # ChatPersistencePort
        fs_callback_executor: Any | None = None,  # FsCallbackExecutor
        terminal_callback_executor: Any | None = None,  # TerminalCallbackExecutor
    ) -> None:
        """Инициализировать ChatViewModel.

        Args:
            coordinator: SessionCoordinator для работы с prompt-turn
            event_bus: EventBus для публикации/подписки на события
            logger: Logger для логирования
            plan_vm: PlanViewModel для обработки plan updates из session/update
            session_update_dispatcher: SessionUpdateDispatcher для маршрутизации обновлений
            chat_persistence: ChatPersistencePort для сохранения истории
            fs_callback_executor: FsCallbackExecutor для async-safe FS операций
            terminal_callback_executor: TerminalCallbackExecutor для управления терминалами
        """
        super().__init__(event_bus, logger)
        self.coordinator = coordinator
        self._plan_vm = plan_vm

        # Компоненты декомпозиции
        self._session_update_dispatcher = session_update_dispatcher
        self._chat_persistence = chat_persistence
        self._fs_callback_executor = fs_callback_executor
        self._terminal_callback_executor = terminal_callback_executor

        # Observable свойства
        self.messages: Observable[list[Any]] = Observable([])
        self.tool_calls: Observable[list[Any]] = Observable([])
        self.is_streaming: Observable[bool] = Observable(False)
        self.pending_permissions: Observable[list[Any]] = Observable([])
        self.streaming_text: Observable[str] = Observable("")
        self.last_stop_reason: Observable[str | None] = Observable(None)

        # Активная сессия и кэш UI-состояния по session_id.
        self._active_session_id: str | None = None
        self._session_states: dict[str, ChatSessionState] = {}

        # Observable команды
        self.send_prompt_cmd = ObservableCommand(self._send_prompt)
        self.cancel_prompt_cmd = ObservableCommand(self._cancel_prompt)
        self.approve_permission_cmd = ObservableCommand(self._approve_permission)
        self.reject_permission_cmd = ObservableCommand(self._reject_permission)
        self.clear_chat_cmd = ObservableCommand(self._clear_chat)

        # Подписываемся на события (если EventBus доступен)
        try:
            from codelab.client.domain.events import (
                ErrorOccurredEvent,
                PermissionRequestedEvent,
                PromptCompletedEvent,
                PromptStartedEvent,
            )

            self.on_event(PromptStartedEvent, self._handle_prompt_started)
            self.on_event(PromptCompletedEvent, self._handle_prompt_completed)
            self.on_event(PermissionRequestedEvent, self._handle_permission_requested)
            self.on_event(ErrorOccurredEvent, self._handle_error_occurred)
        except ImportError:
            self.logger.debug("DomainEvents not available, skipping event subscriptions")

    async def _send_prompt(self, session_id: str, prompt_text: str, **kwargs: Any) -> None:
        """Отправить prompt в сессию.

        Args:
            session_id: ID сессии
            prompt_text: Текст prompt
            **kwargs: Дополнительные параметры
        """
        if not session_id:
            self.logger.warning("Cannot send prompt: session_id is empty")
            return

        # Гарантируем что prompt отправляется в активную сессию
        # и обновления пишутся в её состояние.
        self.set_active_session(session_id)

        self._set_streaming_state(session_id, is_streaming=True, clear_text=True)
        self._set_last_stop_reason(session_id, None)

        try:
            terminal_callbacks: dict[str, Any] = {}
            if self._terminal_callback_executor is not None:
                _executor = self._terminal_callback_executor

                async def _on_terminal_create(command: str) -> str:
                    terminal_id, error = await _executor.create_terminal(command)
                    if error:
                        raise RuntimeError(f"Terminal creation failed: {error}")
                    return terminal_id

                async def _on_terminal_output(terminal_id: str) -> dict[str, Any]:
                    output_data, error = await _executor.get_output(terminal_id)
                    if error:
                        return {"output": "", "isComplete": True, "exitCode": None}
                    output = ""
                    if isinstance(output_data, dict):
                        output = output_data.get("output", "")
                    elif isinstance(output_data, str):
                        output = output_data
                    return {
                        "output": output,
                        "isComplete": True,
                        "exitCode": None,
                    }

                async def _on_terminal_wait_for_exit(
                    terminal_id: str,
                ) -> tuple[int | None, str | None]:
                    result, error = await _executor.wait_for_exit(terminal_id)
                    if error or result is None:
                        return (None, error or "")
                    return result

                async def _on_terminal_release(terminal_id: str) -> None:
                    await _executor.release_terminal(terminal_id)

                async def _on_terminal_kill(terminal_id: str) -> bool:
                    success, _ = await _executor.kill_terminal(terminal_id)
                    return success

                terminal_callbacks = {
                    "on_terminal_create": _on_terminal_create,
                    "on_terminal_output": _on_terminal_output,
                    "on_terminal_wait_for_exit": _on_terminal_wait_for_exit,
                    "on_terminal_release": _on_terminal_release,
                    "on_terminal_kill": _on_terminal_kill,
                }

            # Отправить prompt через coordinator с callback для обработки обновлений
            # SessionCoordinator должен обработать updates и опубликовать события
            await self.coordinator.send_prompt(
                session_id,
                prompt_text,
                on_update=self._handle_session_update,
                on_fs_read=self._handle_fs_read,
                on_fs_write=self._handle_fs_write,
                **terminal_callbacks,
                **kwargs,
            )

            # Гарантированное добавление streaming текста в историю после завершения
            # (на случай, если PromptCompletedEvent не был опубликован)
            session_state = self._get_or_create_session_state(session_id)
            streaming_text = session_state.streaming_text
            if streaming_text:
                session_state.messages.append({"role": "assistant", "content": streaming_text})
                session_state.streaming_text = ""
                session_state.is_streaming = False
                self._session_states[session_id] = session_state
                self._persist_messages(
                    session_id,
                    session_state.messages,
                    replay_updates=session_state.replay_updates,
                )
                if self._active_session_id == session_id:
                    self.messages.value = list(session_state.messages)
                    self.streaming_text.value = ""
                    self.is_streaming.value = False
                self.logger.info(
                    "Agent response added to message history (fallback)",
                    text_length=len(streaming_text),
                )

        except Exception as e:
            self.logger.exception("Error sending prompt", error=str(e))
            raise
        finally:
            # Очищаем streaming состояние
            self._set_streaming_state(session_id, is_streaming=False, clear_text=True)

    def _handle_session_update(self, update_data: dict[str, Any]) -> None:
        """Обработать session/update от сервера.

        Делегирует обработку SessionUpdateDispatcher.

        Args:
            update_data: Данные обновления сессии от сервера
        """
        self.handle_session_update_dispatched(update_data)

    async def _cancel_prompt(self, session_id: str) -> None:
        """Отменить текущий prompt.

        Args:
            session_id: ID сессии
        """
        if not session_id:
            self.logger.warning("Cannot cancel prompt: session_id is empty")
            return

        try:
            self.logger.info(
                "cancel_prompt_sending_request",
                session_id=session_id,
                is_streaming=self.is_streaming.value,
            )
            await self.coordinator.cancel_prompt(session_id)
            self.logger.info("cancel_prompt_request_sent", session_id=session_id)
            self.is_streaming.value = False
        except Exception as e:
            self.logger.exception("cancel_prompt_error", error=str(e))
            raise

    async def _approve_permission(
        self,
        session_id: str,
        permission_id: str,
        **kwargs: Any,
    ) -> None:
        """Утвердить разрешение.

        Args:
            session_id: ID сессии
            permission_id: ID разрешения
            **kwargs: Дополнительные параметры
        """
        try:
            self.logger.info(
                "Approving permission",
                session_id=session_id,
                permission_id=permission_id,
            )
            await self.coordinator.handle_permission(
                session_id,
                permission_id,
                approved=True,
                **kwargs,
            )
            # Удалить из pending
            self._remove_pending_permission(permission_id)
        except Exception as e:
            self.logger.exception("Error approving permission", error=str(e))
            raise

    async def _reject_permission(
        self,
        session_id: str,
        permission_id: str,
        **kwargs: Any,
    ) -> None:
        """Отклонить разрешение.

        Args:
            session_id: ID сессии
            permission_id: ID разрешения
            **kwargs: Дополнительные параметры
        """
        try:
            self.logger.info(
                "Rejecting permission",
                session_id=session_id,
                permission_id=permission_id,
            )
            await self.coordinator.handle_permission(
                session_id,
                permission_id,
                approved=False,
                **kwargs,
            )
            # Удалить из pending
            self._remove_pending_permission(permission_id)
        except Exception as e:
            self.logger.exception("Error rejecting permission", error=str(e))
            raise

    async def _clear_chat(self) -> None:
        """Очистить чат (все сообщения и tool calls)."""
        self.messages.value = []
        self.tool_calls.value = []
        self.pending_permissions.value = []
        self.streaming_text.value = ""
        self.last_stop_reason.value = None
        self._persist_active_state()
        self.logger.info("Chat cleared")

    async def _handle_fs_read(self, path: str) -> str:
        """Обработать fs/read_text_file от агента (async).

        Args:
            path: Путь к файлу для чтения

        Returns:
            Содержимое файла или пустая строка в случае ошибки
        """
        try:
            session_id = self._active_session_id
            if not session_id:
                self.logger.warning("fs_read_no_active_session", path=path)
                return ""

            if self._fs_callback_executor is None:
                self.logger.warning("fs_callback_executor_not_initialized", path=path)
                return ""

            content, error = await self._fs_callback_executor.read_file(path)
            if error:
                self.logger.warning("fs_read_error", path=path, error=error)
                return ""
            self.logger.debug("fs_read_success", path=path, content_size=len(content or ""))
            return content or ""
        except Exception as e:
            self.logger.error("fs_read_error", path=path, error=str(e))
            return ""

    async def _handle_fs_write(self, path: str, content: str) -> bool:
        """Обработать fs/write_text_file от агента (async).

        Args:
            path: Путь к файлу для записи
            content: Содержимое для записи

        Returns:
            True если запись успешна, False в случае ошибки
        """
        try:
            session_id = self._active_session_id
            if not session_id:
                self.logger.warning("fs_write_no_active_session", path=path)
                return False

            if self._fs_callback_executor is None:
                self.logger.warning("fs_callback_executor_not_initialized", path=path)
                return False

            success, error = await self._fs_callback_executor.write_file(path, content)
            if error:
                self.logger.warning("fs_write_error", path=path, error=error)
                return False
            self.logger.debug("fs_write_success", path=path, content_size=len(content))
            return success
        except Exception as e:
            self.logger.error("fs_write_error", path=path, error=str(e))
            return False

    def add_message(self, role: str, content: str, session_id: str | None = None) -> None:
        """Добавить сообщение в чат.

        Args:
            role: Роль ("user", "assistant", "system")
            content: Содержимое сообщения
            session_id: ID сессии, для которой добавляется сообщение
        """
        if session_id is not None:
            state = self._get_or_create_session_state(session_id)
            state.messages.append({"role": role, "content": content})
            self._session_states[session_id] = state
            self._persist_messages(
                session_id,
                state.messages,
                replay_updates=state.replay_updates,
            )
            if self._active_session_id == session_id:
                self.messages.value = list(state.messages)
        else:
            messages = self.messages.value
            messages.append({"role": role, "content": content})
            self.messages.value = list(messages)
            self._persist_active_state()
        self.logger.debug("Message added", role=role, content_length=len(content))

    def append_streaming_text(self, text: str) -> None:
        """Добавить текст к потоковому выводу.

        Args:
            text: Текст для добавления
        """
        self.streaming_text.value += text
        self._persist_active_state()

    def _remove_pending_permission(self, permission_id: str) -> None:
        """Удалить разрешение из pending.

        Args:
            permission_id: ID разрешения
        """
        perms = self.pending_permissions.value
        self.pending_permissions.value = [p for p in perms if p.request_id != permission_id]
        self._persist_active_state()

    def set_active_session(self, session_id: str | None) -> None:
        """Переключает ChatViewModel на состояние выбранной сессии."""

        # Сохраняем текущее состояние перед переключением.
        self._persist_active_state()
        self._active_session_id = session_id

        if session_id is None:
            self.messages.value = []
            self.tool_calls.value = []
            self.pending_permissions.value = []
            self.streaming_text.value = ""
            self.is_streaming.value = False
            self.last_stop_reason.value = None
            return

        state = self._get_or_create_session_state(session_id)

        self.messages.value = list(state.messages)
        self.tool_calls.value = list(state.tool_calls)
        self.pending_permissions.value = list(state.pending_permissions)
        self.streaming_text.value = state.streaming_text
        self.is_streaming.value = state.is_streaming
        self.last_stop_reason.value = state.last_stop_reason

    def restore_session_from_replay(
        self,
        session_id: str,
        replay_updates: list[dict[str, Any]],
    ) -> None:
        """Восстанавливает состояние чата по replay updates от `session/load`.

        Args:
            session_id: ID сессии, для которой применяем replay
            replay_updates: Список raw-уведомлений `session/update`
        """

        self.logger.info(
            "restore_session_from_replay_started",
            session_id=session_id,
            replay_updates_count=len(replay_updates),
        )

        # Пересобираем сообщения из message chunks для быстрого восстановления UI.
        # Это отдельный проход, чтобы сразу установить messages.value до обработки
        # остальных обновлений через _handle_session_update.
        rebuilt_messages: list[dict[str, str]] = []
        last_role: str | None = None
        current_text_parts: list[str] = []

        for idx, update_data in enumerate(replay_updates):
            params = update_data.get("params", {})
            if params.get("sessionId") != session_id:
                self.logger.debug(
                    "restore_skipping_wrong_session",
                    idx=idx,
                    expected_session=session_id,
                    actual_session=params.get("sessionId"),
                )
                continue

            update = params.get("update", {})
            update_type = update.get("sessionUpdate")
            content = update.get("content")

            self.logger.debug(
                "restore_processing_update",
                idx=idx,
                update_type=update_type,
                has_content=content is not None,
                content_type=type(content).__name__ if content is not None else None,
            )

            # Обрабатываем только message chunks для пересборки истории
            if not isinstance(content, dict):
                self.logger.debug(
                    "restore_skipping_no_content",
                    idx=idx,
                    update_type=update_type,
                )
                continue

            text = content.get("text")
            if not isinstance(text, str) or text == "":
                self.logger.debug(
                    "restore_skipping_no_text",
                    idx=idx,
                    update_type=update_type,
                    has_text=text is not None,
                )
                continue

            # Определяем роль для текущего chunk
            if update_type == "user_message_chunk":
                current_role = "user"
            elif update_type == "agent_message_chunk":
                current_role = "assistant"
            else:
                continue

            # Агрегируем последовательные chunks одного типа в одно сообщение
            if current_role != last_role and last_role is not None:
                # Роль изменилась — сохраняем предыдущее сообщение
                rebuilt_messages.append(
                    {
                        "role": last_role,
                        "content": "".join(current_text_parts),
                    }
                )
                current_text_parts = []

            last_role = current_role
            current_text_parts.append(text)

            self.logger.debug(
                "restore_aggregating_chunk",
                idx=idx,
                role=current_role,
                text_length=len(text),
            )

        # Сохраняем последнее сообщение (если есть)
        if last_role is not None and current_text_parts:
            rebuilt_messages.append(
                {
                    "role": last_role,
                    "content": "".join(current_text_parts),
                }
            )
            self.logger.info(
                "restore_added_final_message",
                role=last_role,
                text_length=len("".join(current_text_parts)),
            )

        # Записываем пересобранное состояние в кэш конкретной сессии.
        # ВАЖНО: НЕ сохраняем replay_updates здесь - это сделает _handle_session_update
        # при обработке каждого update, что исключит дублирование.
        state = self._get_or_create_session_state(session_id)
        state.messages = rebuilt_messages
        state.streaming_text = ""
        state.is_streaming = False
        self._session_states[session_id] = state

        # Если сессия активна в UI, синхронизируем observables сразу.
        if self._active_session_id == session_id:
            self.messages.value = list(rebuilt_messages)
            self.streaming_text.value = ""
            self.is_streaming.value = False

        # ОБРАБАТЫВАЕМ ВСЕ replay updates через единый обработчик.
        # Это восстановит config_options, tool_calls, plans и другие состояния,
        # а также опубликует необходимые события (например, ConfigOptionUpdatedEvent).
        # ВАЖНО: пропускаем message chunks, так как они уже обработаны выше
        # при пересборке rebuilt_messages, и _handle_session_update добавит их повторно.
        for update_data in replay_updates:
            params = update_data.get("params", {})
            if params.get("sessionId") == session_id:
                update = params.get("update", {})
                update_type = update.get("sessionUpdate")
                # Пропускаем message chunks - они уже добавлены в rebuilt_messages
                if update_type not in ("user_message_chunk", "agent_message_chunk"):
                    self._handle_session_update(update_data)

        self.logger.info(
            "restore_session_from_replay_completed",
            session_id=session_id,
            rebuilt_messages_count=len(rebuilt_messages),
            is_active_session=self._active_session_id == session_id,
        )

    def _persist_active_state(self) -> None:
        """Сохраняет текущее состояние чата для активной сессии."""

        if self._active_session_id is None:
            return

        existing_state = self._session_states.get(self._active_session_id)
        replay_updates = [] if existing_state is None else list(existing_state.replay_updates)

        state = ChatSessionState(
            messages=list(self.messages.value),
            tool_calls=list(self.tool_calls.value),
            pending_permissions=list(self.pending_permissions.value),
            streaming_text=self.streaming_text.value,
            is_streaming=self.is_streaming.value,
            last_stop_reason=self.last_stop_reason.value,
            replay_updates=replay_updates,
        )
        self._session_states[self._active_session_id] = state
        self._persist_messages(
            self._active_session_id,
            state.messages,
            replay_updates=state.replay_updates,
        )

    def _get_or_create_session_state(self, session_id: str) -> ChatSessionState:
        """Возвращает состояние сессии или создаёт пустое."""

        state = self._session_states.get(session_id)
        if state is not None:
            return state

        persisted_messages = self._load_messages(session_id)
        persisted_replay_updates = self._load_replay_updates(session_id)
        if persisted_replay_updates:
            persisted_messages = self._rebuild_messages_from_replay(
                session_id,
                persisted_replay_updates,
            )

        state = ChatSessionState(
            messages=persisted_messages,
            tool_calls=[],
            pending_permissions=[],
            streaming_text="",
            is_streaming=False,
            last_stop_reason=None,
            replay_updates=persisted_replay_updates,
        )
        self._session_states[session_id] = state
        return state

    def _persist_messages(
        self,
        session_id: str,
        messages: list[Any],
        replay_updates: list[dict[str, Any]] | None = None,
    ) -> None:
        """Сохраняет сообщения через ChatPersistencePort.

        Использует fire-and-forget pattern для async save.

        Args:
            session_id: ID сессии
            messages: Список сообщений для сохранения
            replay_updates: Опциональные replay updates
        """
        if self._chat_persistence is None:
            return

        serializable_messages = [
            message
            for message in messages
            if isinstance(message, dict)
            and isinstance(message.get("role"), str)
            and isinstance(message.get("content"), str)
        ]
        serializable_updates = (
            [u for u in replay_updates if isinstance(u, dict)]
            if replay_updates is not None
            else None
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                self._chat_persistence.save_messages(
                    session_id,
                    serializable_messages,
                    replay_updates=serializable_updates,
                )
            )
        except RuntimeError:
            # Нет running event loop - пропускаем сохранение
            pass

    def _load_messages(self, session_id: str) -> list[dict[str, str]]:
        """Загружает сообщения через ChatPersistencePort.

        Args:
            session_id: ID сессии

        Returns:
            Список сообщений или пустой список
        """
        if self._chat_persistence is None:
            return []
        return self._chat_persistence.load_messages_sync(session_id)

    def _load_replay_updates(self, session_id: str) -> list[dict[str, Any]]:
        """Загружает replay updates через ChatPersistencePort.

        Args:
            session_id: ID сессии

        Returns:
            Список replay updates или пустой список
        """
        if self._chat_persistence is None:
            return []
        return self._chat_persistence.load_replay_updates_sync(session_id)

    def _rebuild_messages_from_replay(
        self,
        session_id: str,
        replay_updates: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        """Восстанавливает сообщения из кэшированных replay updates одной сессии."""

        rebuilt_messages: list[dict[str, str]] = []

        for update_data in replay_updates:
            params = update_data.get("params", {})
            if params.get("sessionId") != session_id:
                continue

            update = params.get("update", {})
            update_type = update.get("sessionUpdate")
            content = update.get("content")
            if not isinstance(content, dict):
                continue

            text = content.get("text")
            if not isinstance(text, str) or text == "":
                continue

            if update_type == "user_message_chunk":
                rebuilt_messages.append({"role": "user", "content": text})
            elif update_type == "agent_message_chunk":
                rebuilt_messages.append({"role": "assistant", "content": text})

        return rebuilt_messages

    def _set_streaming_state(
        self, session_id: str, *, is_streaming: bool, clear_text: bool
    ) -> None:
        """Обновляет флаг streaming и буфер текста для сессии."""

        state = self._get_or_create_session_state(session_id)
        state.is_streaming = is_streaming
        if clear_text:
            state.streaming_text = ""
        self._session_states[session_id] = state

        if self._active_session_id == session_id:
            self.is_streaming.value = is_streaming
            if clear_text:
                self.streaming_text.value = ""
            return

        # Если завершили поток неактивной сессии, синхронизируем общий UI-флаг,
        # чтобы поле prompt не оставалось disabled после фонового завершения turn.
        if not is_streaming:
            any_streaming = any(
                state_item.is_streaming for state_item in self._session_states.values()
            )
            if not any_streaming:
                self.is_streaming.value = False

    def _set_last_stop_reason(self, session_id: str, stop_reason: str | None) -> None:
        """Сохраняет stop reason для сессии и синхронизирует активный UI."""

        state = self._get_or_create_session_state(session_id)
        state.last_stop_reason = stop_reason
        self._session_states[session_id] = state

        if self._active_session_id == session_id:
            self.last_stop_reason.value = stop_reason

    # Event handlers
    def _handle_prompt_started(self, event: Any) -> None:
        """Обработать начало prompt-turn.

        Args:
            event: PromptStartedEvent из EventBus
        """
        self.logger.debug(
            "Prompt started event received - CLEARING streaming_text",
            session_id=getattr(event, "session_id", "unknown"),
        )
        session_id = getattr(event, "session_id", None)
        if isinstance(session_id, str):
            self._set_streaming_state(session_id, is_streaming=True, clear_text=True)

    def _handle_prompt_completed(self, event: Any) -> None:
        """Обработать завершение prompt-turn.

        После завершения streaming сохраняет накопленный текст агента в историю сообщений.

        Args:
            event: PromptCompletedEvent из EventBus
        """
        self.logger.debug(
            "Prompt completed event received - STOPPING streaming",
            session_id=getattr(event, "session_id", "unknown"),
            stop_reason=getattr(event, "stop_reason", None),
            final_streaming_text_length=len(self.streaming_text.value),
        )

        session_id = getattr(event, "session_id", None)
        if not isinstance(session_id, str):
            return

        state = self._get_or_create_session_state(session_id)
        streaming_text = state.streaming_text
        if streaming_text:
            state.messages.append({"role": "assistant", "content": streaming_text})
            self._session_states[session_id] = state
            self._persist_messages(
                session_id,
                state.messages,
                replay_updates=state.replay_updates,
            )
            if self._active_session_id == session_id:
                self.messages.value = list(state.messages)
            self.logger.debug(
                "Agent response saved to message history",
                text_length=len(streaming_text),
            )

        # Отключаем streaming и очищаем буфер
        self._set_streaming_state(session_id, is_streaming=False, clear_text=True)
        self._set_last_stop_reason(session_id, getattr(event, "stop_reason", None))

    def _handle_permission_requested(self, event: Any) -> None:
        """Обработать запрос разрешения.

        Args:
            event: PermissionRequestedEvent из EventBus
        """
        perm = PermissionRequest(
            request_id=getattr(event, "request_id", "unknown"),
            session_id=getattr(event, "session_id", "unknown"),
            action=getattr(event, "action", "unknown"),
            resource=getattr(event, "resource", "unknown"),
            description=getattr(event, "description", ""),
        )
        perms = self.pending_permissions.value
        self.pending_permissions.value = list(perms) + [perm]
        self._persist_active_state()
        self.logger.debug(
            "Permission requested event received",
            request_id=perm.request_id,
            action=perm.action,
        )

    def _handle_error_occurred(self, event: Any) -> None:
        """Обработать ошибку.

        Args:
            event: ErrorOccurredEvent из EventBus
        """
        session_id = getattr(event, "session_id", None)
        if isinstance(session_id, str):
            self._set_streaming_state(session_id, is_streaming=False, clear_text=False)
        else:
            self.is_streaming.value = False
            self._persist_active_state()
        error_msg = getattr(event, "error_message", "Unknown error")
        self.logger.error(
            "Error occurred event received",
            error_message=error_msg,
            error_type=getattr(event, "error_type", "unknown"),
        )

    # =========================================================================
    # Интеграция с новыми компонентами декомпозиции
    # =========================================================================

    def handle_session_update_dispatched(self, update_data: dict[str, Any]) -> None:
        """Обработать session/update через SessionUpdateDispatcher.

        Делегирует обработку обновлений соответствующим handler'ам.
        Handler'ы синхронизируют Observable через ChatUpdateSink.

        Args:
            update_data: Данные обновления от сервера
        """
        if self._session_update_dispatcher is None:
            self.logger.warning(
                "session_update_dispatcher_not_available",
                update_data=update_data,
            )
            return

        # Извлекаем session_id из update_data
        params = update_data.get("params", {})
        session_id = params.get("sessionId", self._active_session_id)

        if not isinstance(session_id, str):
            self.logger.warning(
                "handle_session_update_dispatched_missing_session_id",
                update_data=update_data,
            )
            return

        # Получаем или создаём состояние сессии
        state = self._get_or_create_session_state(session_id)

        # Добавляем replay update для восстановления состояния
        state.replay_updates.append(update_data)
        self._session_states[session_id] = state

        # Сохраняем в persistence
        self._persist_messages(
            session_id,
            state.messages,
            replay_updates=state.replay_updates,
        )

        # Создаём контекст для dispatcher
        from codelab.client.presentation.chat.context import ChatUpdateContext

        context = ChatUpdateContext(
            session_id=session_id,
            state=state,
            sink=self,  # ChatViewModel реализует ChatUpdateSink
            plan_vm=self._plan_vm,
            event_bus=self.event_bus,
            _logger=self.logger,
        )

        # Диспетчеризация обновления
        # Handler'ы синхронизируют Observable через context.sink
        self._session_update_dispatcher.dispatch_with_context(update_data, context)

    # Реализация ChatUpdateSink для интеграции с handler'ами

    def sync_messages(self, session_id: str, messages: list[dict[str, str]]) -> None:
        """Синхронизировать сообщения с UI (ChatUpdateSink).

        Args:
            session_id: ID сессии
            messages: Обновлённый список сообщений
        """
        if self._active_session_id == session_id:
            self.messages.value = list(messages)

    def sync_tool_calls(self, session_id: str, tool_calls: list[dict[str, Any]]) -> None:
        """Синхронизировать tool calls с UI (ChatUpdateSink).

        Args:
            session_id: ID сессии
            tool_calls: Обновлённый список tool calls
        """
        if self._active_session_id == session_id:
            self.tool_calls.value = list(tool_calls)

    def sync_streaming(self, session_id: str, text: str, is_streaming: bool) -> None:
        """Синхронизировать streaming текст с UI (ChatUpdateSink).

        Args:
            session_id: ID сессии
            text: Текущий streaming текст
            is_streaming: Флаг активной потоковой передачи
        """
        if self._active_session_id == session_id:
            self.streaming_text.value = text
            self.is_streaming.value = is_streaming
