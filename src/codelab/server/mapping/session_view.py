"""Проекция доменного агрегата на read-порт ядра (`SessionView`).

Зачем. Ядро агента читает сессию через порт `agent.contracts.ports.SessionView`,
и живой `protocol.state.SessionDocument` удовлетворяет его структурно. Доменный
`Session` — **нет**: имена и вложенность другие (`id` против `session_id`,
`config.cwd`, `config.config_values`, `ConversationHistory` вместо
последовательности wire-записей). Без проекции перевод turn'а на агрегат (шаг 3
фазы D, ADR-006) обязан был бы задеть и ядро, и всю цепочку `tools/` — около
двадцати файлов, типизированных против `SessionDocument`.

Проекция read-only намеренно. Мутации по решению шага 1 фазы D — команды в своих
коротких транзакциях; проксировать записи в долгоживущий агрегат значило бы
вернуть тот самый инвариант, который шаг 1 запретил («turn не записывает
документ, который держал через `await`»).

Чтение идёт **сквозь** агрегат, а не снимком: `history` пересобирается на каждое
обращение, поэтому дописанная по ходу turn'а запись видна сразу — того же
поведения требует docstring порта.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from codelab.server.mapping.history_mapper import HistoryMapper

if TYPE_CHECKING:
    from collections.abc import Sequence

    from codelab.server.domain.session import Session
    from codelab.server.models import HistoryMessage
    from codelab.shared.capabilities import ClientCapabilities


class DomainSessionView:
    """`SessionView` поверх доменного агрегата (read-only).

    Пример использования:
        view = DomainSessionView(domain_session)
        response = await strategy.execute(view, prompt, mcp_manager)
    """

    __slots__ = ("_session",)

    def __init__(self, session: Session) -> None:
        """Инициализирует проекцию.

        Args:
            session: Доменный агрегат сессии. Хранится по ссылке — проекция
                читает его текущее состояние, а не копию.
        """
        self._session = session

    @property
    def aggregate(self) -> Session:
        """Носитель, поверх которого построена проекция.

        Единственный законный потребитель — граница `tools/`: инструменты меняют
        состояние сессии (реестр терминалов, `set_config_value`), поэтому им нужен
        агрегат, а не read-проекция. Разворачивает ровно одно место —
        `SimpleToolRegistry.execute_tool`, чтобы знание о проекции не расползлось
        по исполнителям. Ядру это свойство не нужно: оно читает через порт.
        """
        return self._session

    @property
    def session_id(self) -> str:
        return self._session.id

    @property
    def cwd(self) -> str:
        return self._session.config.cwd

    @property
    def config_values(self) -> dict[str, str]:
        return self._session.config.config_values

    @property
    def runtime_capabilities(self) -> ClientCapabilities | None:
        """Возможности клиента как есть, без конверсии в wire-DTO.

        Порт `ClientCapabilitiesView` структурный, и доменный `ClientCapabilities`
        удовлетворяет его теми же тремя полями, что и `ClientRuntimeCapabilities`.
        """
        return self._session.config.runtime_capabilities

    @property
    def history(self) -> Sequence[HistoryMessage]:
        """История в wire-форме, которую ожидает `HistoryBuilder`.

        Выражение то же, которым историю собирает `SessionMapper.to_protocol`, —
        иначе ядро читало бы одно, а на диск уезжало другое.
        """
        messages = self._session.history.get_messages()
        return [HistoryMapper.to_protocol(message) for message in messages]

    def __repr__(self) -> str:
        return f"DomainSessionView(session_id={self._session.id!r})"
