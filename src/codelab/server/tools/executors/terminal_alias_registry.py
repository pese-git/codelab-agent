"""Реестр alias'ов терминалов: короткий id для LLM ↔ настоящий client terminalId."""

from __future__ import annotations

from codelab.server.process_identity import PROCESS_TOKEN
from codelab.server.protocol.state import SessionState


class TerminalAliasRegistry:
    """Реестр между коротким alias, который сервер выдаёт LLM, и настоящим
    client-side ``terminalId`` (порождается клиентом в ACP ``terminal/create``).

    Мотивация (tech-debt #18): LLM теряет символы при дословной ретрансляции
    36-символьного UUID → ``Terminal not found`` → recreate-loop. Короткий
    детерминированный alias (``term_<n>``) устраняет саму поверхность ошибки, а
    клиент по-прежнему адресуется своим родным id — ACP-контракт не нарушается.

    Состояние живёт в :class:`SessionState` (``terminals`` + ``terminal_counter``),
    чтобы переживать tool-call'ы turn'а и персиститься вместе с сессией. Класс
    инкапсулирует только поведение над этим состоянием (регистрация, разрешение,
    освобождение) и сам состояния не хранит — потокобезопасно переиспользуется
    как singleton executor'а.
    """

    _PREFIX = "term_"

    def register(self, session: SessionState, client_terminal_id: str) -> str:
        """Регистрирует client terminalId и возвращает новый короткий alias."""
        session.terminal_counter += 1
        alias = f"{self._PREFIX}{session.terminal_counter}"
        session.terminals[alias] = client_terminal_id
        # Отметка владельца: терминалы живут у клиента и рестарт не переживают, а
        # реестр персистится. Без отметки следующий процесс принял бы мёртвые
        # дескрипторы за живые (P2-44).
        session.terminals_owner = PROCESS_TOKEN
        return alias

    def resolve(self, session: SessionState, alias: str) -> str | None:
        """Возвращает client terminalId по alias или ``None``, если alias неизвестен."""
        return session.terminals.get(alias)

    def release(self, session: SessionState, alias: str) -> str | None:
        """Удаляет alias из реестра, возвращает освобождённый client terminalId (или None)."""
        return session.terminals.pop(alias, None)
