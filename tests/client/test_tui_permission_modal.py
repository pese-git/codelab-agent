from __future__ import annotations

from unittest.mock import MagicMock

from codelab.client.messages import PermissionOption
from codelab.client.presentation.permission_view_model import PermissionViewModel
from codelab.client.tui.components.permission_modal import PermissionModal


def test_permission_modal_prefers_reject_once_for_default_focus() -> None:
    mock_vm = MagicMock(spec=PermissionViewModel)
    modal = PermissionModal(
        permission_vm=mock_vm,
        title="Permission",
        options=[
            PermissionOption(optionId="allow_1", name="Allow", kind="allow_once"),
            PermissionOption(optionId="reject_1", name="Reject", kind="reject_once"),
        ],
    )

    button_id = modal._default_focus_button_id()  # noqa: SLF001

    assert button_id == "permission-reject_1"


def test_permission_modal_allow_action_uses_allow_fallback() -> None:
    mock_vm = MagicMock(spec=PermissionViewModel)
    modal = PermissionModal(
        permission_vm=mock_vm,
        title="Permission",
        options=[PermissionOption(optionId="allow_always_1", name="Allow", kind="allow_always")],
    )
    option_id = modal._resolve_option_id_by_kinds(["allow_once", "allow_always"])  # noqa: SLF001

    assert option_id == "allow_always_1"


def test_permission_modal_reject_action_uses_reject_fallback() -> None:
    mock_vm = MagicMock(spec=PermissionViewModel)
    modal = PermissionModal(
        permission_vm=mock_vm,
        title="Permission",
        options=[PermissionOption(optionId="reject_always_1", name="Reject", kind="reject_always")],
    )
    option_id = modal._resolve_option_id_by_kinds(["reject_once", "reject_always"])  # noqa: SLF001

    assert option_id == "reject_always_1"
