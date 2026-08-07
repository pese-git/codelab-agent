"""Незакрытые разрешения переживают запись (v12, шаг 5 ADR-008).

Документ — носитель состояния turn'а между запросом и ответом: разрешение
приходит следующим запросом, а тот получает свою копию сессии с диска (та же
причина, по которой в `active_turn` живёт `pending_batch`). Пока ожидание
описывалось парой плоских полей, запись переживало только последнее — и ответ на
любой другой применить было не к чему, даже если сессия нашлась (P1-61).

Это и есть та часть, без которой доменная модель и реестр не закрывают дефект:
проверено замером — до v12 из двух заведённых ожиданий после загрузки
оставалось одно.
"""

from __future__ import annotations

from typing import Any

import pytest

from codelab.server.domain.session import TurnState
from codelab.server.domain.value_objects import AwaitingPermission, PermissionWait
from codelab.server.mapping.session_mapper import SessionMapper
from codelab.server.storage.document import (
    CURRENT_SCHEMA_VERSION,
    ActiveTurnState,
    SessionDocument,
)


def _v11_document(turn: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 11,
        "session_id": "sess_waits",
        "cwd": "/tmp",
        "active_turn": turn,
    }


class TestMigrationFromFlatFields:
    def test_pair_becomes_a_single_wait(self) -> None:
        document = SessionDocument.model_validate(
            _v11_document(
                {
                    "prompt_request_id": "req_1",
                    "session_id": "sess_waits",
                    "permission_request_id": "perm_1",
                    "permission_tool_call_id": "call_1",
                    "phase": "awaiting_permission",
                }
            )
        )

        assert document.schema_version == CURRENT_SCHEMA_VERSION
        assert document.active_turn is not None
        assert [w.request_id for w in document.active_turn.permission_waits] == ["perm_1"]
        assert document.active_turn.permission_waits[0].tool_call_id == "call_1"

    def test_keep_tool_pending_comes_from_the_phase_name(self) -> None:
        """Ветку хранило имя фазы — до v12 это было единственное место, где она жила."""
        document = SessionDocument.model_validate(
            _v11_document(
                {
                    "prompt_request_id": "req_1",
                    "session_id": "sess_waits",
                    "permission_request_id": "perm_1",
                    "permission_tool_call_id": "call_1",
                    "phase": "waiting_tool_completion",
                }
            )
        )

        assert document.active_turn is not None
        assert document.active_turn.permission_waits[0].keep_tool_pending is True

    def test_flat_fields_are_dropped_from_storage(self) -> None:
        """Отбрасывание явное, как в v9 и v10: удаление данных видно в цепочке."""
        document = SessionDocument.model_validate(
            _v11_document(
                {
                    "prompt_request_id": "req_1",
                    "session_id": "sess_waits",
                    "permission_request_id": "perm_1",
                    "permission_tool_call_id": "call_1",
                    "phase": "awaiting_permission",
                }
            )
        )

        dumped = document.model_dump(mode="json")["active_turn"]

        assert "permission_request_id" not in dumped
        assert "permission_tool_call_id" not in dumped

    def test_turn_without_permission_gets_empty_list(self) -> None:
        document = SessionDocument.model_validate(
            _v11_document(
                {"prompt_request_id": "req_1", "session_id": "sess_waits", "phase": "running"}
            )
        )

        assert document.active_turn is not None
        assert document.active_turn.permission_waits == []

    def test_second_pass_changes_nothing(self) -> None:
        """Миграция срабатывает на каждой загрузке — повтор обязан быть тождеством."""
        once = SessionDocument.model_validate(
            _v11_document(
                {
                    "prompt_request_id": "req_1",
                    "session_id": "sess_waits",
                    "permission_request_id": "perm_1",
                    "permission_tool_call_id": "call_1",
                    "phase": "awaiting_permission",
                }
            )
        ).model_dump(mode="json")

        twice = SessionDocument.model_validate(once).model_dump(mode="json")

        assert twice["active_turn"] == once["active_turn"]


class TestLegacyConstruction:
    """Прежняя форма записи ожидания остаётся допустимым **входом**."""

    def test_legacy_kwargs_fold_into_the_list(self) -> None:
        turn = ActiveTurnState(
            prompt_request_id="req_1",
            session_id="sess_waits",
            permission_request_id="perm_1",
            permission_tool_call_id="call_1",
        )

        assert [w.request_id for w in turn.permission_waits] == ["perm_1"]
        assert turn.permission_request_id == "perm_1"
        assert turn.permission_tool_call_id == "call_1"

    def test_derived_fields_describe_the_latest_wait(self) -> None:
        turn = ActiveTurnState(
            prompt_request_id="req_1",
            session_id="sess_waits",
            permission_waits=[
                {"request_id": "perm_1", "tool_call_id": "call_1"},
                {"request_id": "perm_2", "tool_call_id": "call_2"},
            ],
        )

        assert turn.permission_request_id == "perm_2"
        assert turn.awaits_permission_request("perm_1") is True
        assert turn.awaits_permission_request("perm_2") is True
        assert turn.awaits_permission_request("посторонний") is False


class TestRoundTripThroughDocument:
    """Главный замер: до v12 из двух ожиданий круг переживало одно."""

    @pytest.mark.parametrize("count", [1, 2, 3])
    def test_every_wait_survives_domain_to_document_and_back(self, count: int) -> None:
        session = SessionMapper.to_domain(
            SessionDocument(session_id="sess_waits", cwd="/tmp", mcp_servers=[])
        )
        session.active_turn = TurnState(session_id="sess_waits")
        for index in range(count):
            session.active_turn.await_permission(
                PermissionWait(f"perm_{index}", f"call_{index}", keep_tool_pending=index == 0)
            )

        restored = SessionMapper.to_domain(SessionMapper.to_protocol(session))

        assert restored.active_turn is not None
        assert isinstance(restored.active_turn.phase, AwaitingPermission)
        assert [w.request_id for w in restored.active_turn.outstanding_permissions] == [
            f"perm_{index}" for index in range(count)
        ]
        assert restored.active_turn.permission_wait_for("perm_0") is not None
        assert restored.active_turn.permission_wait_for("perm_0").keep_tool_pending is True

    def test_answering_the_older_request_is_applicable_after_reload(self) -> None:
        """Ровно потерянный случай: ответ пришёл на первый из двух запросов."""
        session = SessionMapper.to_domain(
            SessionDocument(session_id="sess_waits", cwd="/tmp", mcp_servers=[])
        )
        session.active_turn = TurnState(session_id="sess_waits")
        session.active_turn.await_permission(PermissionWait("f5614636", "call_007"))
        session.active_turn.await_permission(PermissionWait("aaaa1111", "call_008"))

        restored = SessionMapper.to_domain(SessionMapper.to_protocol(session))
        wait = restored.active_turn.permission_wait_for("f5614636")

        assert wait is not None
        assert wait.tool_call_id == "call_007"
