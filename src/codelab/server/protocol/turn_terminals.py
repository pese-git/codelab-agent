"""Освобождение остатка терминалов turn'а (ADR-008, шаг 5.3, часть 2).

По спецификации освобождает **агент**: «The Agent MUST release the terminal using
`terminal/release` when it's no longer needed» (`10-Terminal.md:109-111`). Модель
стороной протокола не является, поэтому делегирование MUST ей — не исполнение
спецификации, а его вероятностная имитация: за шесть живых прогонов модель
освободила остаток один раз и пять раз не освободила.

Фактический приобретатель ресурса от лица модели — **turn**: не сессия (переживает
turn без потребителя) и не процесс (в stdio умирает вместе с клиентом). Отсюда два
следствия, которые определяют форму этого модуля.

**Множество путей, снимающих turn, и множество путей, освобождающих терминалы, не
совпадают — и это by design.** Turn снимается в восьми местах, но приобретателя
завершают не все: переключение сессии оставляет терминалы прошлой сессии живыми у
клиента (к ней можно вернуться — та же причина, по которой в реестре alias'ов нет
метода «забыть сессию»), а дисконнект вообще не имеет адресата для RPC.

**Границу сузил транспорт, а не вкус (измерено живьём 2026-08-12, `sess_937ff13e9d1b`).**
Первая версия освобождала и на отмене — и повисла: stdio отправляет в фоновую задачу
**только** `session/prompt` (`stdio.py:211`), поэтому agent→client RPC из обработчика
`session/cancel` ждёт ответа, прочитать который может лишь заблокированный этим
ожиданием receive-цикл. `session_cancel_handled` оказалась последней строкой лога.
Остались два шва, оба исполняются в фоновых задачах: штатное завершение и ошибка
пайплайна. Остаток отменённого turn'а не теряется — дренаж накопителен и сцеживает его
на следующем завершении.

**Освобождается только дожданный остаток.** Порядок из спецификации — «Use
`terminal/wait_for_exit` to wait for the command to exit before releasing the
terminal» (`17-Schema.md:1060-1062`), потому что освобождение убивает ещё идущую
команду. Замер дал точную границу риска: `unwaited` возвращался в 0 за 151–483 мс, а
единственное окно живой команды — отмена внутри этого интервала, и оно **наблюдалось
живьём** (`term_96847_1`, отмена через 1.5 с после `create`). Поэтому терминал с
незавершённым ожиданием остаётся висеть: цена — несколько коротких строк на процесс,
альтернатива — убитая команда пользователя.

Бухгалтерии остатку не нужно: реестр уже знает живые alias'ы сессии, а терминалы
Context Manager'а сбалансированы внутри одного вызова (`create` → `wait_for_exit` →
`release` в `finally`), поэтому к границе turn'а их там нет. Освобождение
идемпотентно — повторный `release` разрешается в `None` и ничего не делает.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from codelab.server.client_rpc import ClientRPCCancelledError
from codelab.server.tools.integrations.client_rpc_bridge import ClientRPCBridge

if TYPE_CHECKING:
    from codelab.server.domain.session import Session as DomainSession
    from codelab.server.rpc_holder import ClientRPCServiceHolder
    from codelab.server.tools.executors.terminal_alias_registry import TerminalAliasRegistry

logger = structlog.get_logger()


class TurnTerminalReleaser:
    """Освобождает терминалы, оставшиеся от закончившегося turn'а.

    Объект, а не модуль: у освобождения две зависимости — процессный реестр alias'ов
    (`Scope.APP`) и клиентский RPC. Этим он отличается от снятия turn'а
    (`turn_runtime.finish_turn`), у которого зависимостей нет и который обязан
    оставаться синхронным: пять из восьми его вызывающих исполняются внутри замыкания
    доменной транзакции, где сетевой вызов был бы неверен.
    """

    def __init__(
        self,
        aliases: TerminalAliasRegistry,
        client_rpc_service_holder: ClientRPCServiceHolder,
    ) -> None:
        """Инициализирует освобождение остатка.

        Args:
            aliases: Процессный реестр alias'ов терминалов.
            client_rpc_service_holder: Holder клиентского RPC-сервиса — сервис
                меняется по запросам, поэтому берётся на каждом вызове.
        """
        self._aliases = aliases
        self._holder = client_rpc_service_holder

    async def release_turn_remainder(self, session: DomainSession, *, cause: str) -> int:
        """Освобождает дожданный остаток терминалов сессии.

        Вызывается **вне** доменной транзакции: это клиентский RPC, а не запись
        состояния. Сессия здесь читается только ради идентификатора.

        Args:
            session: Сессия, чей turn закончился.
            cause: Причина завершения turn'а (наблюдаемость — как у `turn_finished`).

        Returns:
            Сколько терминалов освобождено.
        """
        service = self._holder.service
        if service is None:
            return 0

        # Пустой остаток тоже пишет запись, и это не избыточность. Прогон 2026-08-12
        # (`sess_f5f9b789397b`) закончился штатно с `live=0`: модель освободила все три
        # терминала сама, освобождению делать было нечего — и молчание шва оказалось
        # неотличимо от «шов не достигнут». Ровно то слепое пятно, которое шаг 5.1
        # убрал у признака `waited`; повторять его у самого освобождения нельзя,
        # приёмка шага держится на этой записи.
        remainder = self._aliases.waited_aliases(session)
        bridge = ClientRPCBridge(service)
        released = 0
        for alias in remainder:
            client_terminal_id = self._aliases.resolve(session, alias)
            if client_terminal_id is None:
                continue
            try:
                success = await bridge.release_terminal(
                    session=session,
                    terminal_id=client_terminal_id,
                )
            except ClientRPCCancelledError:
                # Отмена приходит по всей сессии: остаток доживёт до следующего
                # завершения turn'а, а «продолжать освобождать» здесь означало бы
                # спорить с уже отменённым транспортом.
                break
            except Exception as error:
                # Горячий путь конца turn'а не должен падать из-за одного терминала:
                # ответ на `session/prompt` уже построен, и исключение здесь стоило бы
                # пользователю turn'а. Строка остаётся, чтобы утечка была видна.
                logger.warning(
                    "turn_terminal_release_failed",
                    session_id=str(session.id),
                    alias=alias,
                    cause=cause,
                    error=str(error),
                )
                continue

            if success:
                self._aliases.release(session, alias)
                released += 1

        unwaited = self._aliases.unwaited_aliases(session)
        logger.info(
            "turn_terminals_released",
            session_id=str(session.id),
            cause=cause,
            released=released,
            live=len(self._aliases.known_aliases(session)),
            unwaited=len(unwaited),
            unwaited_aliases=unwaited,
        )
        return released
