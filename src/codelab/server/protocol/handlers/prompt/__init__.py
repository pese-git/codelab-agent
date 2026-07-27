"""Обработчики методов работы с prompt-turn.

Логика session/prompt, session/cancel и related. Разнесена по осям изменения
(P1-4) на подмодули; публичный API сохранён через re-export.
"""

from __future__ import annotations

# Re-export ACPMessage: прежний модуль prompt.py импортировал его на верхнем уровне,
# поэтому `handlers.prompt.ACPMessage` — часть публичного контракта (используется в
# тестах для patch `ACPMessage.request`).
from ....messages import ACPMessage as ACPMessage
from ..client_rpc_response import (
    finalize_failed_client_rpc_request as finalize_failed_client_rpc_request,
)
from ..client_rpc_response import (
    find_session_by_pending_client_request_id as find_session_by_pending_client_request_id,
)
from ..client_rpc_response import (
    resolve_pending_client_rpc_response_impl as resolve_pending_client_rpc_response_impl,
)
from .client_requests import (
    build_fs_client_request,
    build_terminal_client_request,
    can_use_fs_client_rpc,
    can_use_terminal_client_rpc,
    normalize_session_path,
)
from .directives import (
    extract_prompt_directives,
    resolve_prompt_directives,
    resolve_prompt_stop_reason,
)
from .normalization import (
    normalize_plan_entries,
    normalize_stop_reason,
    normalize_tool_kind,
    resolve_tool_title,
)
from .permission_response import resolve_permission_response_impl
from .tool_calls import (
    build_executor_tool_execution_updates,
    build_plan_entries,
    build_policy_tool_execution_updates,
    complete_active_turn,
    create_tool_call,
    finalize_active_turn,
    should_auto_complete_active_turn,
    update_tool_call_status,
)
from .validation import (
    MAX_AUDIO_DATA_SIZE,
    MAX_IMAGE_DATA_SIZE,
    MAX_PROMPT_TEXT_LENGTH,
    validate_prompt_content,
)

__all__ = [
    "MAX_AUDIO_DATA_SIZE",
    "MAX_IMAGE_DATA_SIZE",
    "MAX_PROMPT_TEXT_LENGTH",
    "build_executor_tool_execution_updates",
    "build_fs_client_request",
    "build_plan_entries",
    "build_policy_tool_execution_updates",
    "build_terminal_client_request",
    "can_use_fs_client_rpc",
    "can_use_terminal_client_rpc",
    "complete_active_turn",
    "create_tool_call",
    "extract_prompt_directives",
    "finalize_active_turn",
    "finalize_failed_client_rpc_request",
    "find_session_by_pending_client_request_id",
    "normalize_plan_entries",
    "normalize_session_path",
    "normalize_stop_reason",
    "normalize_tool_kind",
    "resolve_pending_client_rpc_response_impl",
    "resolve_permission_response_impl",
    "resolve_prompt_directives",
    "resolve_prompt_stop_reason",
    "resolve_tool_title",
    "should_auto_complete_active_turn",
    "update_tool_call_status",
    "validate_prompt_content",
]
