"""Реестр alias'ов терминалов: короткий id для LLM ↔ настоящий client terminalId."""

from __future__ import annotations

from codelab.server.domain.session import Session


class TerminalAliasRegistry:
    """Реестр между коротким alias, который сервер выдаёт LLM, и настоящим
    client-side ``terminalId`` (порождается клиентом в ACP ``terminal/create``).

    Мотивация (tech-debt #18): LLM теряет символы при дословной ретрансляции
    36-символьного UUID → ``Terminal not found`` → recreate-loop. Короткий
    детерминированный alias (``term_<n>``) устраняет саму поверхность ошибки, а
    клиент по-прежнему адресуется своим родным id — ACP-контракт не нарушается.

    **Носитель связки — процесс, не документ сессии (ADR-007, шаг A).** Связка
    alias → client terminalId осмысленна только внутри процесса, который её создал:
    сами терминалы живут у клиента и рестарт сервера не переживают. Пока связка
    персистилась, следующий процесс принимал мёртвые дескрипторы за живые, и это
    приходилось компенсировать отметкой владельца и чисткой на загрузке (P2-44,
    P2-58). После переноса мёртвых alias'ов не существует по построению: новый
    процесс начинает с пустым реестром.

    **Что осталось в документе и почему — счётчик alias'ов.** ``terminal_counter``
    не состояние процесса, а распределитель идентификаторов сессии (как
    ``tool_call_counter``), и он обязан быть монотонным **через рестарт**: иначе
    ``term_1`` из восстановленной истории разрешился бы в терминал нового процесса —
    вместо внятного «неизвестный терминал» модель получила бы чужой вывод. Поэтому
    alias выдаёт агрегат (``Session.allocate_terminal_alias``), а связывает — реестр.

    Реестр адресуется ``session_id`` и живёт как singleton процесса (``Scope.APP``):
    от числа копий сессии, которые отдаёт хранилище, он не зависит. Тот же приём —
    ``TurnCancellationRegistry`` и ``SessionFileCacheRegistry``.

    **Граница роста названа явно.** Записи снимает ``release``, но сессия, от которой
    ушли не освободив терминалы, оставляет свои связки до конца процесса. Метода
    «забыть сессию» здесь нет намеренно: серверного удаления сессии не существует, а
    единственный кандидат на такой вызов — переключение сессии — был бы неверным
    (терминалы прошлой сессии живы у клиента, к ней можно вернуться). Цена —
    несколько коротких строк на сессию за время жизни процесса.
    """

    def __init__(self) -> None:
        self._by_session: dict[str, dict[str, str]] = {}

    def register(self, session: Session, client_terminal_id: str) -> str:
        """Регистрирует client terminalId и возвращает новый короткий alias.

        Alias выдаёт агрегат: счётчик обязан переживать рестарт, чтобы alias'ы не
        переиспользовались (см. docstring класса). Связку хранит реестр.
        """
        alias = session.allocate_terminal_alias()
        self._by_session.setdefault(str(session.id), {})[alias] = client_terminal_id
        return alias

    def resolve(self, session: Session, alias: str) -> str | None:
        """Возвращает client terminalId по alias или ``None``, если alias неизвестен."""
        return self._by_session.get(str(session.id), {}).get(alias)

    def release(self, session: Session, alias: str) -> str | None:
        """Удаляет alias из реестра, возвращает освобождённый client terminalId (или None)."""
        return self._by_session.get(str(session.id), {}).pop(alias, None)

    def known_aliases(self, session: Session) -> list[str]:
        """Живые alias'ы сессии — для сообщения модели о неизвестном терминале."""
        return sorted(self._by_session.get(str(session.id), {}))
