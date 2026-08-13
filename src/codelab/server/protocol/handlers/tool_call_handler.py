"""Обработчик управления жизненным циклом tool calls.

Содержит логику создания, обновления статуса и финализации tool calls
в контексте обработки prompt-turn.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import structlog

from ...domain.session import Session as DomainSession
from ...domain.value_objects import (
    FileLocation,
    ToolCallStatus,
)
from ...messages import ACPMessage
from .event_history_writer import EventHistoryWriter

logger = structlog.get_logger()


class ToolCallHandler:
    """Управляет жизненным циклом tool calls в prompt-turn.

    Инкапсулирует логику создания tool calls, обновления их статуса,
    построения notifications и отмены активных tool calls.
    """

    # Поддерживаемые tool kinds для нормализации
    _SUPPORTED_TOOL_KINDS: set[str] = {
        "read",
        "edit",
        "delete",
        "move",
        "search",
        "execute",
        "think",
        "fetch",
        "switch_mode",
        "other",
    }

    # Человекочитаемые titles для каждого kind
    _TOOL_TITLES: dict[str, str] = {
        "read": "Tool read operation",
        "edit": "Tool edit operation",
        "delete": "Tool delete operation",
        "move": "Tool move operation",
        "execute": "Tool execution",
        "search": "Tool search operation",
        "think": "Tool reasoning step",
        "fetch": "Tool fetch operation",
        "switch_mode": "Tool mode switch",
        "other": "Tool operation",
    }

    def __init__(self) -> None:
        # Писатель журнала без состояния, поэтому создаётся здесь, а не
        # прокидывается: ответ модели на невыполненный вызов и запись этого факта
        # неразделимы (см. `answer_unexecuted_tool_calls`).
        self._history_writer = EventHistoryWriter()

    def create_tool_call(
        self,
        session: DomainSession,
        *,
        title: str,
        kind: str,
        tool_name: str | None = None,
        tool_arguments: dict[str, Any] | None = None,
        tool_call_id_from_llm: str | None = None,
        locations: list[FileLocation] | None = None,
    ) -> str:
        """Создает новый tool call, возвращает его ID.

        Мутация делегируется доменному `ToolCallRegistry.create`: счётчик и форма
        записи принадлежат агрегату (фаза D ADR-006). Здесь остаётся только
        поверхность turn-пути.

        Args:
            session: Доменный агрегат сессии
            title: Название для UI (e.g., "Tool execution")
            kind: Категория tool (read, edit, delete, move, search, execute,
                think, fetch, switch_mode, other)
            tool_name: Имя инструмента в реестре для отложенного выполнения
            tool_arguments: Аргументы для выполнения инструмента
            tool_call_id_from_llm: ID tool call из ответа LLM (для связки в истории)
            locations: Опциональные file locations

        Returns:
            ID вида "call_NNN" (e.g., "call_001", "call_002")
        """
        tool_call = session.tool_calls.create(
            tool_name or "",
            tool_arguments or {},
            title=title,
            kind=kind,
            tool_call_id_from_llm=tool_call_id_from_llm,
            locations=locations,
        )
        return tool_call.id

    def update_tool_call_status(
        self,
        session: DomainSession,
        tool_call_id: str,
        status: str,
        *,
        content: list[dict[str, Any]] | None = None,
    ) -> None:
        """Обновляет статус tool call с проверкой допустимых переходов.

        Матрица допустимых переходов:
        - pending → in_progress, cancelled, failed
        - in_progress → completed, cancelled, failed
        - completed, cancelled, failed → (терминальные состояния)

        Если переход невалиден, игнорирует обновление (отказ логирует домен).

        Args:
            session: Доменный агрегат сессии
            tool_call_id: ID tool call'а для обновления
            status: Новый статус (wire-строка; `ToolCallStatus` — StrEnum)
            content: Опциональный контент (результат tool call)
        """
        session.tool_calls.update_status(
            tool_call_id,
            ToolCallStatus(status),
            content=content,
        )

    def build_tool_call_notification(
        self,
        session_id: str,
        tool_call_id: str,
        title: str,
        kind: str,
        locations: list[dict[str, str]] | None = None,
        raw_input: dict[str, Any] | None = None,
    ) -> ACPMessage:
        """Строит tool_call notification для отправки клиенту.

        Создает сообщение с информацией о новом tool call, включающее
        его идентификатор, title, kind и опциональные locations.

        Args:
            session_id: ID сессии
            tool_call_id: ID tool call'а
            title: Название для UI
            kind: Категория tool
            locations: Опциональные locations (e.g., file paths)
            raw_input: Опциональные исходные аргументы (ACP rawInput)

        Returns:
            ACPMessage типа notification с sessionUpdate="tool_call"
        """
        update_dict: dict[str, Any] = {
            "sessionUpdate": "tool_call",
            "toolCallId": tool_call_id,
            "title": title,
            "kind": kind,
            "status": "pending",
        }
        if locations is not None:
            update_dict["locations"] = locations
        if raw_input is not None:
            update_dict["rawInput"] = raw_input

        return ACPMessage.notification(
            "session/update",
            {
                "sessionId": session_id,
                "update": update_dict,
            },
        )

    def build_tool_update_notification(
        self,
        session_id: str,
        tool_call_id: str,
        status: str,
        content: list[dict[str, Any]] | None = None,
        locations: list[dict[str, Any]] | None = None,
        raw_output: dict[str, Any] | None = None,
    ) -> ACPMessage:
        """Строит tool_call_update notification для отправки клиенту.

        Создает сообщение об изменении статуса существующего tool call,
        опционально включая контент результата.

        Args:
            session_id: ID сессии
            tool_call_id: ID tool call'а
            status: Новый статус (in_progress, completed, cancelled, failed)
            content: Опциональный контент (результаты tool call)
            locations: Опциональные file locations
            raw_output: Опциональный исходный результат (ACP rawOutput)

        Returns:
            ACPMessage типа notification с sessionUpdate="tool_call_update"
        """
        # Форма события — в одном месте (`tool_call_status_notification`), иначе
        # копии расходятся: этот же рендер зовут пути отмены и ответов client-RPC.
        from .prompt.tool_call_updates import tool_call_status_notification

        return tool_call_status_notification(
            session_id=session_id,
            tool_call_id=tool_call_id,
            status=status,
            content=content,
            locations=locations,
            raw_output=raw_output,
        )

    def answer_tool_call(
        self,
        session: DomainSession,
        tool_call_id: str,
        text: str,
    ) -> bool:
        """Ответить модели на вызов и записать этот ответ в журнал.

        Единственная дверь для записи `role: tool`, откуда бы ответ ни шёл:
        результат исполнения, ошибка, отмена, остаток прерванного батча, вызов без
        имени инструмента. Ответ и событие журнала — одно решение, поэтому они
        неразделимы: событие пишется ровно там, где `add_tool_result` подтвердил
        запись, и подавленный дубль в журнал не попадает.

        Дверь существует потому, что текст ответа **не выводится** из ACP-контента
        вызова (замер — в докстринге `ToolCallAnswered`), а проекция `history`
        обязана его выдать. До шага 4 в журнал попадали только ответы
        невыполненным вызовам, и выводимость держалась на совпадении текстов.

        Args:
            session: Доменный агрегат сессии
            tool_call_id: Адресат ответа (`answer_id` из ответа модели)
            text: Текст, который увидит модель

        Returns:
            True, если ответ записан; False — ответ этому адресату уже был, и
            второй отклонён (побеждает первый, см. `Session.add_tool_result`).
        """
        if not session.add_tool_result(tool_call_id, text):
            return False
        self._history_writer.save_tool_call_answer(session, tool_call_id, text)
        return True

    def answer_unexecuted_tool_calls(
        self,
        session: DomainSession,
        tool_call_ids: Sequence[str],
        *,
        reason: str,
        retry_hint: bool = True,
    ) -> int:
        """Ответить модели на вызовы, которые выполнены не будут, и записать это.

        Единственная дверь для ответов вызовам, которых нет в `tool_calls`:
        остаток прерванного батча, отложенный после permission хвост и вызов без
        имени инструмента. Их id уже лежат в assistant-сообщении истории, а
        контракт LLM-API требует `role: tool` на каждый (P2-38).

        Текст ответа принадлежит этой двери — она единственная его знает, — а
        неразделимость ответа и записи обеспечивает `answer_tool_call`. Разложить
        пару по трём вызывающим значило бы снова договариваться дисциплиной — так
        уже разошлись шесть писателей ответа (P2-63).

        Args:
            session: Доменный агрегат сессии
            tool_call_ids: Адресаты ответов (`answer_id` из ответа модели)
            reason: Причина в терминах пользователя — уезжает модели в тексте
            retry_hint: Приглашать ли модель повторить вызов. `False` — когда
                повтор в прежнем виде заведомо не поможет: вызову без имени
                инструмента подсказка «запроси снова» была бы вредным советом.

        Returns:
            Число записанных ответов (дубли не считаются: побеждает первый ответ).
        """
        text = f"Вызов не выполнялся: {reason}."
        if retry_hint:
            text += " Запроси его снова, если он всё ещё нужен."

        answered = 0
        for tool_call_id in tool_call_ids:
            if self.answer_tool_call(session, tool_call_id, text):
                answered += 1

        if answered:
            logger.info(
                "unexecuted_tool_calls_answered",
                session_id=str(session.id),
                count=answered,
                reason=reason,
            )
        return answered

    def cancel_active_tools(
        self,
        session: DomainSession,
        session_id: str,
    ) -> list[ACPMessage]:
        """Отменяет все активные (pending, in_progress) tool calls.

        Используется при отмене prompt-turn или других событиях,
        требующих отмены всех незавершенных tool calls.
        Игнорирует tool calls в терминальных состояниях.

        Мутации — доменные (`ToolCallRegistry.update_status`, `add_tool_result`);
        wire остаётся только в построении нотификаций (транзакция `session/cancel`,
        фаза D ADR-006).

        Args:
            session: Доменный агрегат сессии (будет обновлён)
            session_id: ID сессии

        Returns:
            Список ACPMessage notifications об отмене tool calls
        """
        notifications: list[ACPMessage] = []

        for tool_call in session.tool_calls.get_all():
            if tool_call.is_terminal:
                continue

            # Признак снимается ДО перехода: `update_status` мутирует этот же объект,
            # и после него вызов уже `cancelled`, а не `in_progress`. Порядок значим —
            # тот же случай, что чтение идентификатора разрешения до перехода фазы в
            # `_cleanup_session_state`.
            was_in_flight = tool_call.is_in_flight

            session.tool_calls.update_status(tool_call.id, ToolCallStatus.CANCELLED)
            notifications.append(
                self.build_tool_update_notification(
                    session_id=session_id,
                    tool_call_id=tool_call.id,
                    status=ToolCallStatus.CANCELLED.value,
                )
            )

            # Ответ вызова в полёте принадлежит его исполнителю: отмена клиентского
            # RPC кооперативная, поэтому исполнитель разворачивается штатно и пишет
            # правдивый текст («ожидание терминала отменено», P2-50) вместо
            # обобщённого «не выполнялся», которое про исполняющийся вызов неверно.
            # Побеждает первый ответ, поэтому пропустить его вперёд можно только
            # промолчав здесь.
            #
            # Пропускается **только ответ**: статус и нотификация выше остаются, иначе
            # клиент не узнал бы об отмене из ответа на `session/cancel` — это
            # ACP-поведение, и P2-63 его менять не просит.
            #
            # Это выбор текста, а не гарантия отсутствия дубля: гарантию несёт
            # идемпотентность `add_tool_result`. Здесь остаётся окно между созданием
            # вызова и выставлением `in_progress`, куда отмена тоже может попасть
            # (P2-63).
            if was_in_flight:
                continue

            # Отменённый вызов тоже обязан получить ответ модели: его id лежит в
            # assistant-сообщении истории, а контракт LLM-API требует `role: tool`
            # на каждый `tool_call_id`. Без этого вызов оставался без ответа
            # навсегда — и модель повторяла его (tech-debt P2-38, источник 2).
            #
            # Через дверь, а не напрямую: статус эта метёлка выставляет **без
            # контента**, поэтому текст ответа journal'ом не описан и проекция
            # `history` его не выведет. Измерено на `sess_8fa73fe08f55`
            # (2026-08-13): 2 ответа из 25 оставались невыводимыми — `call_003` и
            # `call_009`, оба отменены здесь. Текст совпадает дословно с прежним.
            self.answer_unexecuted_tool_calls(
                session, [tool_call.answer_id], reason="turn отменён пользователем"
            )

        logger.debug(
            "active tool calls cancelled",
            session_id=session_id,
            cancelled_count=len(notifications),
        )
        return notifications
