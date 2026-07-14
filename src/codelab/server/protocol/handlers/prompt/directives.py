"""Извлечение и разрешение prompt-directives (slash-команды + _meta overrides)."""
from __future__ import annotations

from typing import Any

from ...state import PromptDirectives
from .normalization import (
    normalize_plan_entries,
    normalize_stop_reason,
    normalize_tool_kind,
)


def extract_prompt_directives(
    text_preview: str,
    supported_tool_kinds: set[str],
) -> PromptDirectives:
    """Извлекает служебные флаги turn из текстового preview prompt.

    Поддерживаются только slash-команды (`/plan`, `/tool`, `/tool-pending`
    и RPC-команды `/fs-read`, `/fs-write`, `/term-run`).

    Пример использования:
        directives = extract_prompt_directives("/tool /plan", {"other"})
    """

    normalized_tokens = {
        token.strip().lower()
        for token in text_preview.replace("\n", " ").split(" ")
        if token.strip()
    }

    has_plan_directive = "/plan" in normalized_tokens
    has_tool_directive = "/tool" in normalized_tokens
    has_pending_directive = "/tool-pending" in normalized_tokens
    tool_kind = "other"
    fs_read_path: str | None = None
    fs_write_path: str | None = None
    fs_write_content: str | None = None
    terminal_command: str | None = None
    forced_stop_reason: str | None = None

    stripped_preview = text_preview.strip()
    if stripped_preview.startswith("/fs-read "):
        maybe_path = stripped_preview[len("/fs-read ") :].strip()
        if maybe_path:
            fs_read_path = maybe_path
    if stripped_preview.startswith("/fs-write "):
        raw_write_payload = stripped_preview[len("/fs-write ") :].strip()
        path_and_content = raw_write_payload.split(" ", 1)
        if len(path_and_content) == 2:
            candidate_path = path_and_content[0].strip()
            candidate_content = path_and_content[1]
            if candidate_path:
                fs_write_path = candidate_path
                fs_write_content = candidate_content
    if stripped_preview.startswith("/term-run "):
        raw_command = stripped_preview[len("/term-run ") :].strip()
        if raw_command:
            terminal_command = raw_command
    if stripped_preview.startswith("/stop-max-tokens"):
        forced_stop_reason = "max_tokens"
    if stripped_preview.startswith("/stop-max-turn-requests"):
        forced_stop_reason = "max_turn_requests"
    if stripped_preview.startswith("/refuse"):
        forced_stop_reason = "refusal"

    # Поддерживаем опциональный kind в `/tool <kind> ...` и
    # `/tool-pending <kind> ...` для policy-scope beyond `other`.
    if stripped_preview.startswith("/tool "):
        candidate = stripped_preview[len("/tool ") :].split(" ", 1)[0].strip().lower()
        normalized_candidate = normalize_tool_kind(candidate, supported_tool_kinds)
        if normalized_candidate is not None:
            tool_kind = normalized_candidate
    if stripped_preview.startswith("/tool-pending "):
        candidate = stripped_preview[len("/tool-pending ") :].split(" ", 1)[0].strip().lower()
        normalized_candidate = normalize_tool_kind(candidate, supported_tool_kinds)
        if normalized_candidate is not None:
            tool_kind = normalized_candidate

    return PromptDirectives(
        request_tool=has_tool_directive or has_pending_directive,
        keep_tool_pending=has_pending_directive,
        publish_plan=has_plan_directive,
        plan_entries=None,
        tool_kind=tool_kind,
        fs_read_path=fs_read_path,
        fs_write_path=fs_write_path,
        fs_write_content=fs_write_content,
        terminal_command=terminal_command,
        forced_stop_reason=forced_stop_reason,
    )


def resolve_prompt_directives(
    *,
    params: dict[str, Any],
    text_preview: str,
    supported_tool_kinds: set[str] | None = None,
) -> PromptDirectives:
    """Формирует итоговые prompt-directives из текста и structured `_meta`.

    Structured overrides позволяют управлять prompt-оркестрацией без
    специальных slash-триггеров внутри пользовательского текста.

    Пример использования:
        directives = resolve_prompt_directives(params=params, text_preview="hello")
    """

    if supported_tool_kinds is None:
        supported_tool_kinds = {
            "read",
            "edit",
            "delete",
            "move",
            "search",
            "execute",
            "think",
            "fetch",
            "switch_mode",
            "other",
        }

    directives = extract_prompt_directives(text_preview, supported_tool_kinds)
    raw_meta = params.get("_meta")
    if not isinstance(raw_meta, dict):
        return directives
    raw_overrides = raw_meta.get("promptDirectives")
    if not isinstance(raw_overrides, dict):
        return directives

    request_tool = raw_overrides.get("requestTool")
    if isinstance(request_tool, bool):
        directives.request_tool = request_tool

    keep_tool_pending = raw_overrides.get("keepToolPending")
    if isinstance(keep_tool_pending, bool):
        directives.keep_tool_pending = keep_tool_pending

    publish_plan = raw_overrides.get("publishPlan")
    if isinstance(publish_plan, bool):
        directives.publish_plan = publish_plan

    raw_plan_entries = raw_overrides.get("planEntries")
    normalized_plan_entries = normalize_plan_entries(raw_plan_entries)
    if normalized_plan_entries is not None:
        directives.plan_entries = normalized_plan_entries
        directives.publish_plan = True

    raw_tool_kind = raw_overrides.get("toolKind")
    if isinstance(raw_tool_kind, str):
        normalized_kind = normalize_tool_kind(raw_tool_kind.strip().lower(), supported_tool_kinds)
        if normalized_kind is not None:
            directives.tool_kind = normalized_kind

    fs_read_path = raw_overrides.get("fsReadPath")
    if isinstance(fs_read_path, str) and fs_read_path.strip():
        directives.fs_read_path = fs_read_path.strip()

    fs_write_path = raw_overrides.get("fsWritePath")
    if isinstance(fs_write_path, str) and fs_write_path.strip():
        directives.fs_write_path = fs_write_path.strip()

    fs_write_content = raw_overrides.get("fsWriteContent")
    if isinstance(fs_write_content, str):
        directives.fs_write_content = fs_write_content

    terminal_command = raw_overrides.get("terminalCommand")
    if isinstance(terminal_command, str) and terminal_command.strip():
        directives.terminal_command = terminal_command.strip()

    forced_stop_reason = raw_overrides.get("forcedStopReason")
    if isinstance(forced_stop_reason, str):
        normalized_reason = normalize_stop_reason(forced_stop_reason)
        directives.forced_stop_reason = normalized_reason

    if directives.keep_tool_pending:
        # Pending-tool сценарий не имеет смысла без явного tool-flow.
        directives.request_tool = True

    return directives


def resolve_prompt_stop_reason(directives: PromptDirectives) -> str:
    """Возвращает stopReason для текущего prompt-turn.

    Пример использования:
        reason = resolve_prompt_stop_reason(directives)
    """

    if directives.forced_stop_reason is not None:
        return normalize_stop_reason(directives.forced_stop_reason)
    return "end_turn"
