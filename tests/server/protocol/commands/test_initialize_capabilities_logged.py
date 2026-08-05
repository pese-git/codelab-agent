"""Согласованные client capabilities наблюдаемы в логе (побочная находка A.3, P2-32).

Замер живого прогона 2026-08-05 (`codelab-70220.log`, 801 строка, stdio через Zed): про
capabilities — **ни одной записи**. При этом `ToolFilter` решает по ним, существуют ли для
модели `fs/*` и `terminal/*` вообще. То есть смена набора у клиента выглядела бы в разборе
как «модель перестала пользоваться инструментами», и отличить одно от другого было нечем.

Событие структурное (`structlog`, конвенция проекта), поэтому проверяется по имени события
и полям, а не по тексту сообщения.
"""

from __future__ import annotations

import pytest
import structlog

from codelab.server.messages import ACPMessage
from codelab.server.protocol.commands.initialize import InitializeCommandHandler


def _handler() -> InitializeCommandHandler:
    return InitializeCommandHandler(
        supported_protocol_versions=(1,),
        require_auth=False,
        auth_methods=[],
    )


def _message(params: dict) -> ACPMessage:
    return ACPMessage(id="req_1", method="initialize", params=params)


class TestCapabilitiesAreLogged:
    @pytest.mark.asyncio
    async def test_negotiated_capabilities_are_logged(self) -> None:
        with structlog.testing.capture_logs() as logs:
            await _handler().handle(
                _message(
                    {
                        "protocolVersion": 1,
                        "clientCapabilities": {
                            "fs": {"readTextFile": True, "writeTextFile": False},
                            "terminal": True,
                        },
                    }
                )
            )

        negotiated = [log for log in logs if log["event"] == "client_capabilities_negotiated"]
        assert len(negotiated) == 1
        assert negotiated[0]["fs_read"] is True
        assert negotiated[0]["fs_write"] is False
        assert negotiated[0]["terminal"] is True

    @pytest.mark.asyncio
    async def test_absent_capabilities_are_a_warning(self) -> None:
        """Отсутствие `clientCapabilities` — tool-runtime недоступен целиком.

        Уровень `warning`, а не `info`: наружу это выглядит как «инструменты не работают»,
        и в логе это должно быть видно без сопоставления с чем-либо ещё.
        """
        with structlog.testing.capture_logs() as logs:
            await _handler().handle(_message({"protocolVersion": 1}))

        absent = [log for log in logs if log["event"] == "client_capabilities_absent"]
        assert len(absent) == 1
        assert absent[0]["log_level"] == "warning"

    @pytest.mark.asyncio
    async def test_all_disabled_is_logged_not_treated_as_absent(self) -> None:
        """Пустой набор — согласованное решение клиента, а не отсутствие ответа.

        Различие важно для разбора: «клиент не умеет» и «клиент не сказал» — разные
        причины одного наблюдаемого следствия.
        """
        with structlog.testing.capture_logs() as logs:
            await _handler().handle(
                _message({"protocolVersion": 1, "clientCapabilities": {}}),
            )

        assert [log for log in logs if log["event"] == "client_capabilities_negotiated"]
        assert not [log for log in logs if log["event"] == "client_capabilities_absent"]
