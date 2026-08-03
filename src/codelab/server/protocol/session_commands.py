"""Команды turn'а: одна мутация — одна короткая транзакция (ADR-006, фаза D шаг 4).

Turn не вправе записывать документ, который держал через `await`: копия,
пережившая ожидание, устаревает, и её запись либо отклоняется CAS, либо
примиряется слиянием — тот самый класс, что стоил проекту P2-42, P1-49 и
`session_merge`. Здесь этот инвариант становится конструктивным: каждое
изменение состояния применяется к агрегату, загруженному **в момент
применения**, под блокировкой сессии, и коммитится тут же.

Рабочая копия turn'а при этом остаётся тем же объектом: `apply` переносит
состояние закоммиченного агрегата в неё поэлементно. Держатели ссылки
(`PromptContext.session`, `DomainSessionView`, цепочка `tools/`) продолжают
читать актуальное состояние, не зная о транзакциях.

Правила слияния переехали в guard'ы применения и не воспроизводятся здесь:
«отмена главнее» — это отказ `ToolCallRegistry.update_status` от перехода из
`cancelled`; «`active_turn` из свежей копии» — это `require_active_turn`;
«журналы по общему префиксу» — сливать нечего, запись добавляется в свежий
журнал.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import fields
from typing import TypeVar

import structlog

from ..domain.session import Session
from ..storage.session_repository import SessionRepository

logger = structlog.get_logger()

T = TypeVar("T")


class SessionCommands:
    """Применение команд к сессии короткими транзакциями.

    Пример использования:
        commands = SessionCommands(repository, session)
        await commands.apply(lambda s: s.add_assistant_message(text), name="assistant_message")
    """

    __slots__ = ("_repository", "_session", "_session_id")

    def __init__(self, repository: SessionRepository, session: Session) -> None:
        """Инициализирует шов команд.

        Args:
            repository: Доменный порт хранилища.
            session: Рабочая копия turn'а — объект, в который переносится
                состояние после каждого коммита.
        """
        self._repository = repository
        self._session = session
        self._session_id = str(session.id)

    @property
    def session(self) -> Session:
        """Рабочая копия turn'а."""
        return self._session

    async def apply(self, command: Callable[[Session], T], *, name: str) -> T | None:
        """Применить команду к свежему агрегату и закоммитить.

        Команда обязана быть синхронной: `await` внутри неё удерживал бы
        блокировку сессии и вернул бы ровно ту проблему, ради которой команды и
        вводились.

        Вложенный вызов по той же сессии — взаимная блокировка
        (`SessionRepository.transaction`); команда одна, вложенных не бывает.

        Returns:
            Результат команды, либо `None`, если сессии больше нет: удалённую
            сессию не воскрешают записью turn'а.
        """
        committed: Session | None = None
        async with self._repository.transaction(self._session_id) as fresh:
            if fresh is None:
                logger.warning(
                    "session_command_skipped_session_gone",
                    session_id=self._session_id,
                    command=name,
                )
                return None
            committed = fresh
            result = command(fresh)

        # Перенос — ПОСЛЕ выхода из области, а не внутри: `updated_at` и ревизию
        # хранилище штампует на записи, то есть на коммите области. Перенос
        # изнутри оставил бы рабочую копию на значениях загрузки — тот же класс,
        # что дал зависший turn на шаге 3 («проекция теряет то, что писало
        # хранилище»), и вдобавок отдал бы клиенту устаревший `updatedAt`.
        self._adopt(committed)
        return result

    async def require_active_turn(self, command: Callable[[Session], T], *, name: str) -> T | None:
        """Применить команду, только если turn ещё активен.

        Turn, который успели отменить, не вправе дописывать состояние: именно
        это правило `session_merge` выражал как «`active_turn` берётся из свежей
        копии», и именно его нарушение было дефектом P0-39.
        """

        def guarded(session: Session) -> T | None:
            if session.active_turn is None:
                logger.debug(
                    "session_command_skipped_turn_closed",
                    session_id=self._session_id,
                    command=name,
                )
                return None
            return command(session)

        return await self.apply(guarded, name=name)

    async def carry_working_changes(
        self, transfer: Callable[[Session, Session], None], *, name: str
    ) -> None:
        """Перенести в команду изменения, сделанные прямо в рабочей копии.

        ВРЕМЕННЫЙ ШОВ (ADR-006, фаза D шаг 4). Часть путей пишет состояние в
        рабочую копию по ходу собственного `await`: исполнители инструментов
        (реестр терминалов, `set_config_value`) и slash-команды. Своего шва
        команд у них пока нет — у обоих цепочка вызовов шире turn'а, и перевод
        задел бы вызывающих вне этого шага.

        Пока их решения переносятся явно: `transfer(рабочая копия, свежая)`
        перечисляет, что именно переносится, — перечень конечный и виден
        целиком. Уходит, когда эти пути получат собственные команды; до тех пор
        изменение, не перечисленное в `transfer`, до диска не доедет.
        """
        await self.apply(lambda fresh: transfer(self._session, fresh), name=name)

    def _adopt(self, committed: Session) -> None:
        """Перенести состояние закоммиченного агрегата в рабочую копию.

        Поэлементно, а не подменой ссылки: рабочую копию держат `PromptContext`,
        проекция ядра и цепочка `tools/`, и подмена оставила бы их на объекте,
        который больше никто не пишет.
        """
        if committed is self._session:
            return
        for attribute in fields(Session):
            setattr(self._session, attribute.name, getattr(committed, attribute.name))
