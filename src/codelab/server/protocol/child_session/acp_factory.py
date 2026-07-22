"""ACPChildSessionFactory — ACP-адаптер для ChildSessionFactory (ADR-005, Фаза 4).

Реализует driven-порт ``codelab.server.agent.contracts.ports.ChildSessionFactory``
через обёртку над ``protocol.session_factory.SessionFactory``
(ACP-уровень).

Используется в ``core/context/child_session.py`` (DefaultChildSessionManager)
для создания изолированных child-сессий в мультиагентных стратегиях.

До Фазы 4 ``DefaultChildSessionManager`` напрямую зависел от
``SessionFactory`` (protocol). Это нарушало шестигранник. Фаза 4
разворачивает направление: ядро объявляет ``ChildSessionFactory``,
ACP предоставляет ``ACPChildSessionFactory``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codelab.server.agent.contracts.ports import SessionView
    from codelab.server.protocol.session_factory import SessionFactory


class ACPChildSessionFactory:
    """ACP-реализация ``ChildSessionFactory``: создаёт child-сессии
    через ``SessionFactory`` + сразу прокидывает ``parent_session_id``
    (first-class поле SessionState, schema_version 7).
    """

    __slots__ = ("_session_factory",)

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    async def create_child(
        self,
        parent: SessionView,
        subagent_scope: str,
    ) -> SessionView:
        """Создать изолированную child-сессию с ``parent_session_id``.

        Args:
            parent: Read-only представление родительской сессии.
            subagent_scope: Идентификатор скоупа субагента.

        Returns:
            Read-only представление созданной child-сессии.
        """
        from codelab.server.protocol.session_view import SessionStateView

        parent_session_id = str(parent.id)
        child_session_id = f"{parent_session_id}_child_{subagent_scope}"
        cwd = parent.config.cwd

        # Создаём child через SessionFactory (ACP-уровень).
        child_state = self._session_factory.create_session(
            cwd=cwd,
            session_id=child_session_id,
        )

        # Проставляем parent_session_id (first-class поле, schema_version 7).
        child_state.parent_session_id = parent_session_id

        return SessionStateView(child_state)

    async def collect_summary(
        self,
        child: SessionView,
    ) -> object:  # SubagentResult из agent.context.models (избегаем цикл)
        """Собрать summary результата child-сессии.

        Реализация по умолчанию отсутствует — child_session.py
        подмешивает свой ConversationSummarizer в DefaultChildSessionManager,
        поэтому ACPChildSessionFactory предоставляет только create_child,
        а collect_summary делегируется на уровне ядра (DefaultChildSessionManager
        непосредственно использует свой summarizer, а не этот адаптер).

        Это упрощение, но не нарушает контракт: ``ChildSessionFactory.collect_summary``
        может делегироваться на уровень ядра через DefaultChildSessionManager,
        который имеет доступ к обоим: ACP-фабрике и summarizer'у.
        """
        # Делегирование на уровне ядра (DefaultChildSessionManager) —
        # см. core/context/child_session.py:_collect_summary.
        msg = (
            "ACPChildSessionFactory.collect_summary должен вызываться "
            "через DefaultChildSessionManager с явным summarizer"
        )
        raise NotImplementedError(msg)


__all__ = ["ACPChildSessionFactory"]
