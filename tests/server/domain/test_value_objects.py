"""Unit тесты для domain value objects."""

import pytest

from codelab.server.domain.value_objects import (
    AwaitingClientRpc,
    AwaitingPermission,
    Completing,
    FileLocation,
    MessageRole,
    PermissionWait,
    PlanPriority,
    PlanStatus,
    Running,
    SessionId,
    ToolCallStatus,
    TurnCancelled,
    turn_phase_from_wire,
)


class TestSessionId:
    def test_create(self) -> None:
        sid = SessionId("sess_123")
        assert sid == "sess_123"

    def test_is_str(self) -> None:
        sid = SessionId("sess_123")
        assert isinstance(sid, str)


class TestFileLocation:
    def test_create_with_path_only(self) -> None:
        loc = FileLocation(path="/tmp/test.py")
        assert loc.path == "/tmp/test.py"
        assert loc.line is None

    def test_create_with_path_and_line(self) -> None:
        loc = FileLocation(path="/tmp/test.py", line=42)
        assert loc.path == "/tmp/test.py"
        assert loc.line == 42

    def test_frozen(self) -> None:
        loc = FileLocation(path="/tmp/test.py")
        with pytest.raises(AttributeError):
            loc.path = "/other"  # type: ignore[misc]

    def test_empty_path_raises(self) -> None:
        with pytest.raises(ValueError, match="path must not be empty"):
            FileLocation(path="")

    def test_equality(self) -> None:
        a = FileLocation(path="/tmp/test.py", line=10)
        b = FileLocation(path="/tmp/test.py", line=10)
        assert a == b

    def test_inequality(self) -> None:
        a = FileLocation(path="/tmp/test.py", line=10)
        b = FileLocation(path="/tmp/test.py", line=20)
        assert a != b


class TestToolCallStatus:
    def test_values(self) -> None:
        assert ToolCallStatus.PENDING == "pending"
        assert ToolCallStatus.IN_PROGRESS == "in_progress"
        assert ToolCallStatus.COMPLETED == "completed"
        assert ToolCallStatus.CANCELLED == "cancelled"
        assert ToolCallStatus.FAILED == "failed"

    def test_values_match_acp_wire(self) -> None:
        """Набор совпадает с ACP ToolCallStatus: маппер отдаёт .value напрямую."""
        assert {s.value for s in ToolCallStatus} == {
            "pending",
            "in_progress",
            "completed",
            "cancelled",
            "failed",
        }

    def test_from_string(self) -> None:
        assert ToolCallStatus("pending") is ToolCallStatus.PENDING

    def test_is_str(self) -> None:
        assert isinstance(ToolCallStatus.PENDING, str)


class TestMessageRole:
    def test_values(self) -> None:
        assert MessageRole.USER == "user"
        assert MessageRole.ASSISTANT == "assistant"
        assert MessageRole.SYSTEM == "system"
        assert MessageRole.TOOL == "tool"

    def test_from_string(self) -> None:
        assert MessageRole("user") is MessageRole.USER


class TestPlanPriority:
    def test_values(self) -> None:
        assert PlanPriority.HIGH == "high"
        assert PlanPriority.MEDIUM == "medium"
        assert PlanPriority.LOW == "low"


class TestPlanStatus:
    def test_values(self) -> None:
        assert PlanStatus.PENDING == "pending"
        assert PlanStatus.IN_PROGRESS == "in_progress"
        assert PlanStatus.COMPLETED == "completed"


class TestTurnPhaseFromWire:
    """Чтение фазы из документа: терпимость к прежним значениям.

    Здесь нашлись две настоящие регрессии при вводе типа (ADR-008, шаг 2), поэтому
    гейты стоят на каждом наблюдавшемся сочетании полей, а не только на «нормальном».
    """

    def test_legacy_waiting_permission_name_is_read(self) -> None:
        """`waiting_permission` — прежнее имя того же состояния (его писал `directives`)."""
        phase = turn_phase_from_wire(
            "waiting_permission",
            waits=[PermissionWait("perm_1", "call_1")],
        )
        assert phase == AwaitingPermission.of(request_id="perm_1", tool_call_id="call_1")
        assert phase.wire_name == "awaiting_permission"

    def test_keep_tool_pending_is_a_property_of_the_wait(self) -> None:
        """`waiting_tool_completion` — та же фаза с признаком, а не третье состояние.

        Признак пришёл из имени фазы и с v12 хранится у самого ожидания: их может
        быть несколько, и ветка у каждого своя. Восстановление имени из документа
        проверяется на уровне документа (`test_permission_waits_migration_v12`).
        """
        phase = turn_phase_from_wire(
            "waiting_tool_completion",
            waits=[PermissionWait("perm_1", "call_1", keep_tool_pending=True)],
        )
        assert phase == AwaitingPermission.of(
            request_id="perm_1", tool_call_id="call_1", keep_tool_pending=True
        )
        assert phase.wire_name == "waiting_tool_completion"

    def test_every_wait_is_restored(self) -> None:
        """Незакрытых ожиданий может быть несколько — все обязаны пережить чтение (P1-61)."""
        phase = turn_phase_from_wire(
            "awaiting_permission",
            waits=[PermissionWait("perm_1", "call_1"), PermissionWait("perm_2", "call_2")],
        )

        assert isinstance(phase, AwaitingPermission)
        assert [w.request_id for w in phase.waits] == ["perm_1", "perm_2"]

    def test_ids_win_over_phase_name(self) -> None:
        """`phase = running` при заполненном идентификаторе — ожидание, а не running.

        Регрессия, найденная тестами: такие документы лежат на диске (идентификаторы
        писал `permission_manager`, фазу — отдельно `tool_processor`). Потеря
        идентификатора делала бы разрешение необрабатываемым — ответ клиента ищет
        сессию именно по нему.
        """
        phase = turn_phase_from_wire("running", waits=[PermissionWait("perm_1", "call_1")])
        assert phase == AwaitingPermission.of(request_id="perm_1", tool_call_id="call_1")

    def test_request_id_without_tool_call_id_survives(self) -> None:
        """Вторая найденная регрессия: без `tool_call_id` идентификатор всё равно нужен.

        Без него нельзя возобновить конкретный вызов, но отмена обязана записать
        tombstone по `request_id`, иначе поздний ответ даёт -32603.
        """
        phase = turn_phase_from_wire("running", waits=[PermissionWait("perm_1", None)])
        assert phase == AwaitingPermission.of(request_id="perm_1", tool_call_id=None)

    def test_awaiting_without_ids_degrades_to_running(self) -> None:
        """Наблюдавшееся живьём несогласованное состояние не восстанавливается как пауза."""
        assert turn_phase_from_wire("awaiting_permission", waits=[]) == Running()

    def test_terminal_names(self) -> None:
        for name, expected in (("cancelled", TurnCancelled()), ("completing", Completing())):
            assert turn_phase_from_wire(name, waits=[]) == expected

    def test_client_rpc_both_spellings(self) -> None:
        """`awaiting_client_rpc` числился в матрице, но не писался никем; `waiting_` — писался."""
        for name in ("waiting_client_rpc", "awaiting_client_rpc"):
            assert turn_phase_from_wire(name, waits=[]) == AwaitingClientRpc()

    def test_unknown_name_degrades_to_running(self) -> None:
        assert turn_phase_from_wire("who_knows", waits=[]) == Running()
