"""Реестр alias'ов терминалов: короткий id для LLM ↔ настоящий client terminalId."""

from __future__ import annotations

from codelab.server.domain.session import Session
from codelab.server.process_identity import PROCESS_TOKEN


class TerminalAliasRegistry:
    """Реестр между коротким alias, который сервер выдаёт LLM, и настоящим
    client-side ``terminalId`` (порождается клиентом в ACP ``terminal/create``).

    Мотивация (tech-debt #18): LLM теряет символы при дословной ретрансляции
    36-символьного UUID → ``Terminal not found`` → recreate-loop. Короткий
    детерминированный alias (``term_<n>``) устраняет саму поверхность ошибки, а
    клиент по-прежнему адресуется своим родным id — ACP-контракт не нарушается.

    Состояние живёт в доменном агрегате сессии (``runtime.terminals`` +
    ``runtime.terminal_counter``), чтобы переживать tool-call'ы turn'а и
    персиститься вместе с сессией. Поведение над этим состоянием принадлежит
    агрегату (сеймы ``register_terminal``/``resolve_terminal``/
    ``release_terminal``, шаг 2 фазы D ADR-006); класс остаётся адаптером
    executor'а и сам состояния не хранит — потокобезопасно переиспользуется
    как singleton.
    """

    def register(self, session: Session, client_terminal_id: str) -> str:
        """Регистрирует client terminalId и возвращает новый короткий alias.

        Владелец передаётся отсюда: домен не знает про процесс, в котором
        исполняется, а отметка обязательна — терминалы живут у клиента и рестарт
        не переживают, тогда как реестр персистится (P2-44).
        """
        return session.register_terminal(client_terminal_id, owner=PROCESS_TOKEN)

    def resolve(self, session: Session, alias: str) -> str | None:
        """Возвращает client terminalId по alias или ``None``, если alias неизвестен."""
        return session.resolve_terminal(alias)

    def release(self, session: Session, alias: str) -> str | None:
        """Удаляет alias из реестра, возвращает освобождённый client terminalId (или None)."""
        return session.release_terminal(alias)
