"""Извлечение и разрешение prompt-directives (slash-команды + _meta overrides)."""
from __future__ import annotations

from typing import Any

from ...state import PromptDirectives
from .normalization import (
    normalize_plan_entries,
    normalize_stop_reason,
    normalize_tool_kind,
)


def _parse_rpc_directives(
    stripped_preview: str,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Парсит RPC slash-команды (`/fs-read`, `/fs-write`, `/term-run`).

    Возвращает `(fs_read_path, fs_write_path, fs_write_content, terminal_command)`.
    """
    fs_read_path: str | None = None
    fs_write_path: str | None = None
    fs_write_content: str | None = None
    terminal_command: str | None = None

    if stripped_preview.startswith("/fs-read "):
        maybe_path = stripped_preview[len("/fs-read ") :].strip()
        if maybe_path:
            fs_read_path = maybe_path
    if stripped_preview.startswith("/fs-write "):
        raw_write_payload = stripped_preview[len("/fs-write ") :].strip()
        path_and_content = raw_write_payload.split(" ", 1)
        if len(path_and_content) == 2 and path_and_content[0].strip():
            fs_write_path = path_and_content[0].strip()
            fs_write_content = path_and_content[1]
    if stripped_preview.startswith("/term-run "):
        raw_command = stripped_preview[len("/term-run ") :].strip()
        if raw_command:
            terminal_command = raw_command

    return fs_read_path, fs_write_path, fs_write_content, terminal_command


def _parse_forced_stop(stripped_preview: str) -> str | None:
    """Определяет forced stopReason по slash-команде `/stop-*` / `/refuse`."""
    if stripped_preview.startswith("/stop-max-tokens"):
        return "max_tokens"
    if stripped_preview.startswith("/stop-max-turn-requests"):
        return "max_turn_requests"
    if stripped_preview.startswith("/refuse"):
        return "refusal"
    return None


def _parse_directive_tool_kind(stripped_preview: str, supported_tool_kinds: set[str]) -> str:
    """Извлекает опциональный kind из `/tool <kind>` / `/tool-pending <kind>`."""
    for prefix in ("/tool ", "/tool-pending "):
        if stripped_preview.startswith(prefix):
            candidate = stripped_preview[len(prefix) :].split(" ", 1)[0].strip().lower()
            normalized_candidate = normalize_tool_kind(candidate, supported_tool_kinds)
            if normalized_candidate is not None:
                return normalized_candidate
    return "other"


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

    has_tool_directive = "/tool" in normalized_tokens
    has_pending_directive = "/tool-pending" in normalized_tokens

    stripped_preview = text_preview.strip()
    fs_read_path, fs_write_path, fs_write_content, terminal_command = _parse_rpc_directives(
        stripped_preview
    )

    return PromptDirectives(
        request_tool=has_tool_directive or has_pending_directive,
        keep_tool_pending=has_pending_directive,
        publish_plan="/plan" in normalized_tokens,
        plan_entries=None,
        tool_kind=_parse_directive_tool_kind(stripped_preview, supported_tool_kinds),
        fs_read_path=fs_read_path,
        fs_write_path=fs_write_path,
        fs_write_content=fs_write_content,
        terminal_command=terminal_command,
        forced_stop_reason=_parse_forced_stop(stripped_preview),
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

    _apply_meta_flag_overrides(directives, raw_overrides, supported_tool_kinds)
    _apply_meta_rpc_overrides(directives, raw_overrides)

    if directives.keep_tool_pending:
        # Pending-tool сценарий не имеет смысла без явного tool-flow.
        directives.request_tool = True

    return directives


def _apply_meta_flag_overrides(
    directives: PromptDirectives,
    raw_overrides: dict[str, Any],
    supported_tool_kinds: set[str],
) -> None:
    """Применяет bool-флаги, plan и tool_kind из structured `_meta`."""
    request_tool = raw_overrides.get("requestTool")
    if isinstance(request_tool, bool):
        directives.request_tool = request_tool

    keep_tool_pending = raw_overrides.get("keepToolPending")
    if isinstance(keep_tool_pending, bool):
        directives.keep_tool_pending = keep_tool_pending

    publish_plan = raw_overrides.get("publishPlan")
    if isinstance(publish_plan, bool):
        directives.publish_plan = publish_plan

    normalized_plan_entries = normalize_plan_entries(raw_overrides.get("planEntries"))
    if normalized_plan_entries is not None:
        directives.plan_entries = normalized_plan_entries
        directives.publish_plan = True

    raw_tool_kind = raw_overrides.get("toolKind")
    if isinstance(raw_tool_kind, str):
        normalized_kind = normalize_tool_kind(raw_tool_kind.strip().lower(), supported_tool_kinds)
        if normalized_kind is not None:
            directives.tool_kind = normalized_kind


def _apply_meta_rpc_overrides(
    directives: PromptDirectives,
    raw_overrides: dict[str, Any],
) -> None:
    """Применяет fs/terminal/stop-reason overrides из structured `_meta`."""
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
        directives.forced_stop_reason = normalize_stop_reason(forced_stop_reason)


def resolve_prompt_stop_reason(directives: PromptDirectives) -> str:
    """Возвращает stopReason для текущего prompt-turn.

    Пример использования:
        reason = resolve_prompt_stop_reason(directives)
    """

    if directives.forced_stop_reason is not None:
        return normalize_stop_reason(directives.forced_stop_reason)
    return "end_turn"
