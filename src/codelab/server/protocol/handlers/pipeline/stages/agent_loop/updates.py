"""SessionUpdateSink — единая точка исходящих ACP ``session/update``.

Инкапсулирует один транспортный concern: доставить notification клиенту и
записать её для replay при ``session/load``. Порядок side-effects —
``emit`` (immediate delivery → буфер) ПЕРЕД ``replay.save`` — сохранён
байт-идентично прежнему поведению ``AgentLoop`` (детерминизм replay/prompt
cache).

Согласно ACP (05-Prompt Turn.md:169, 08-Tool Calls.md:11) tool calls и их
статусы репортятся "immediately"; sink реализует это через callback, с
fallback на накопление в буфере (backward compatibility).

Sink создаётся пер-turn: связан со свежим буфером notifications и callback'ом,
никакого разделяемого мутабельного состояния между вызовами.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from codelab.server.messages import ACPMessage

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from codelab.server.domain.session import Session as DomainSession
    from codelab.server.protocol.handlers.event_history_writer import EventHistoryWriter

logger = structlog.get_logger()


class SessionUpdateSink:
    """Исходящий канал ``session/update``: immediate delivery → buffer → replay.

    ACP driving-адаптер порта ``agent.contracts.ports.UpdateSink`` (ADR-005, шов №3):
    доменные ``emit_agent_message``/``emit_streaming_delta`` уже реализованы;
    plan/tool_call/tool_update пока принимают готовый ``ACPMessage`` (доменные
    сигнатуры добавит их потребитель ``AgentRunner`` в Фазе 4). Доставка —
    немедленная через callback; буфер только как fallback при отсутствии callback.
    """

    def __init__(
        self,
        history_writer: EventHistoryWriter,
        callback: Callable[[ACPMessage], Awaitable[None]] | None,
        buffer: list[ACPMessage],
    ) -> None:
        """Инициализация sink.

        Args:
            history_writer: Писатель events_history.
            callback: Callback для немедленной отправки notifications (или None).
            buffer: Список notifications для накопления (fallback / permission).
                Sink хранит ссылку — вызывающий читает его после turn'а.
        """
        self._history_writer = history_writer
        self._callback = callback
        self._buffer = buffer

    @property
    def notifications(self) -> list[ACPMessage]:
        """Накопленный буфер notifications (тот же объект, что передан в ctor)."""
        return self._buffer

    # ── Примитивы доставки ──────────────────────────────────────────────────

    async def emit(self, notification: ACPMessage) -> None:
        """Отправить notification немедленно через callback, иначе в буфер."""
        if not await self._send_immediately(notification):
            self._buffer.append(notification)

    def buffer_only(self, notification: ACPMessage) -> None:
        """Положить notification только в буфер (без immediate delivery).

        Используется для permission-request: доставляется через
        ``outcome.notifications``, чтобы избежать дублирования.
        """
        self._buffer.append(notification)

    async def _send_immediately(self, notification: ACPMessage) -> bool:
        """Отправить notification немедленно через callback если он задан.

        Returns:
            True если notification успешно отправлен через callback.
            False если callback не задан или упал с ошибкой.
        """
        if self._callback is not None:
            try:
                logger.debug(
                    "sending_notification_via_callback",
                    method=notification.method,
                    is_notification=notification.is_notification,
                    has_callback=True,
                )
                await self._callback(notification)
                logger.debug(
                    "notification_sent_via_callback",
                    method=notification.method,
                )
                return True
            except Exception as e:
                logger.warning(
                    "notification_callback_failed",
                    notification_method=notification.method,
                    error=str(e),
                    exc_info=True,
                )
                return False
        else:
            logger.debug(
                "notification_not_sent_no_callback",
                method=notification.method,
                has_callback=False,
            )
            return False

    # ── Построение и эмит agent_message_chunk ──────────────────────────────

    @staticmethod
    def build_agent_message_chunk(session_id: str, text: str) -> ACPMessage:
        """Построить notification agent_message_chunk с текстом."""
        return ACPMessage.notification(
            "session/update",
            {
                "sessionId": session_id,
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": text},
                },
            },
        )

    async def emit_agent_message(self, session_id: str, text: str) -> None:
        """Отправить agent_message_chunk (для текста ответа и ошибок LLM)."""
        await self.emit(self.build_agent_message_chunk(session_id, text))

    async def emit_streaming_delta(self, session_id: str, text: str) -> None:
        """Отправить текстовую дельту стриминга (только immediate, без буфера).

        Дельты, не доставленные callback'ом, НЕ накапливаются в буфере (иначе
        при отсутствии стрим-делты полный текст эмитится отдельно, см. AgentLoop).
        """
        await self._send_immediately(self.build_agent_message_chunk(session_id, text))

    def save_agent_message_chunk(self, session: DomainSession, content: dict[str, Any]) -> None:
        """Сохранить agent_message_chunk в events_history для replay."""
        self._history_writer.save_agent_message_chunk(session, content)

    # ── Комбинированные emit + replay ──────────────────────────────────────

    async def emit_and_save_plan(
        self,
        notification: ACPMessage,
        *,
        session: DomainSession,
        entries: list[dict[str, str]],
    ) -> None:
        """Отправить plan-notification, обновить план и сохранить в replay.

        Единственный писатель плана в turn-пути: план — доменная операция агрегата,
        а ACP-форма `latest_plan` собирается маппером на границе сохранения.
        """
        self._apply_plan(session, entries)
        await self.emit(notification)
        self._history_writer.save_plan(session, entries)

    def _apply_plan(self, session: DomainSession, entries: list[dict[str, str]]) -> None:
        """Единая запись плана — доменная операция агрегата."""
        from codelab.server.domain.session import AgentPlan
        from codelab.server.mapping.plan_mapper import PlanMapper

        session.plan = AgentPlan(steps=PlanMapper.from_acp(list(entries)))

    async def emit_and_save_tool_call(
        self,
        notification: ACPMessage,
        *,
        session: DomainSession,
        tool_call_id: str,
        title: str,
        kind: str,
        status: str,
    ) -> None:
        """Отправить tool_call-notification и сохранить создание tool call в replay."""
        await self.emit(notification)
        self._history_writer.save_tool_call(
            session=session,
            tool_call_id=tool_call_id,
            title=title,
            kind=kind,
            status=status,
        )

    async def emit_and_save_tool_update(
        self,
        notification: ACPMessage,
        *,
        session: DomainSession,
        tool_call_id: str,
        status: str,
        content: list[dict[str, Any]] | None = None,
    ) -> None:
        """Отправить tool_call_update-notification и сохранить статус в replay."""
        await self.emit(notification)
        self._history_writer.save_tool_call_update(
            session=session,
            tool_call_id=tool_call_id,
            status=status,
            content=content,
        )
