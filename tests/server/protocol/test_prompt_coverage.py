"""Тесты для непокрытых функций prompt-обработчика.

Покрывают извлечение slash-команд, _meta overrides, нормализацию
plan/tool-kind/path, разрешение заголовков tool-call и проверки
runtime-возможностей клиента.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codelab.server.protocol.handlers.prompt import (
    can_run_tool_runtime,
    can_use_fs_client_rpc,
    can_use_terminal_client_rpc,
    extract_prompt_directives,
    normalize_plan_entries,
    normalize_session_path,
    normalize_tool_kind,
    resolve_prompt_directives,
    resolve_tool_title,
)
from codelab.server.protocol.state import ClientRuntimeCapabilities, SessionState


class TestExtractPromptDirectivesSlashCommands:
    """Тесты извлечения slash-команд в extract_prompt_directives."""

    _DEFAULT_TOOL_KINDS = {
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

    def test_plan_directive_sets_publish_plan(self) -> None:
        """Slash-команда /plan устанавливает publish_plan=True."""
        directives = extract_prompt_directives("/plan", self._DEFAULT_TOOL_KINDS)

        assert directives.publish_plan is True
        assert directives.request_tool is False
        assert directives.tool_kind == "other"

    def test_tool_execute_sets_request_tool_and_kind(self) -> None:
        """Slash-команда /tool execute устанавливает request_tool и tool_kind."""
        directives = extract_prompt_directives(
            "/tool execute", self._DEFAULT_TOOL_KINDS
        )

        assert directives.request_tool is True
        assert directives.keep_tool_pending is False
        assert directives.tool_kind == "execute"

    def test_tool_pending_read_sets_request_and_keep_pending(self) -> None:
        """Slash-команда /tool-pending read устанавливает pending-флаги."""
        directives = extract_prompt_directives(
            "/tool-pending read", self._DEFAULT_TOOL_KINDS
        )

        assert directives.request_tool is True
        assert directives.keep_tool_pending is True
        assert directives.tool_kind == "read"

    def test_fs_read_sets_path(self) -> None:
        """Slash-команда /fs-read устанавливает fs_read_path."""
        directives = extract_prompt_directives(
            "/fs-read /tmp/file.txt", self._DEFAULT_TOOL_KINDS
        )

        assert directives.fs_read_path == "/tmp/file.txt"
        assert directives.fs_write_path is None
        assert directives.terminal_command is None

    def test_fs_write_sets_path_and_content(self) -> None:
        """Slash-команда /fs-write устанавливает путь и содержимое."""
        directives = extract_prompt_directives(
            "/fs-write /tmp/file.txt hello world", self._DEFAULT_TOOL_KINDS
        )

        assert directives.fs_write_path == "/tmp/file.txt"
        assert directives.fs_write_content == "hello world"

    def test_term_run_sets_terminal_command(self) -> None:
        """Slash-команда /term-run устанавливает terminal_command."""
        directives = extract_prompt_directives(
            "/term-run ls -la", self._DEFAULT_TOOL_KINDS
        )

        assert directives.terminal_command == "ls -la"

    def test_unknown_tool_kind_falls_back_to_other(self) -> None:
        """Неизвестный tool kind нормализуется к 'other'."""
        directives = extract_prompt_directives(
            "/tool unknown", self._DEFAULT_TOOL_KINDS
        )

        assert directives.request_tool is True
        assert directives.tool_kind == "other"


class TestResolvePromptDirectivesMetaOverrides:
    """Тесты _meta.promptDirectives overrides в resolve_prompt_directives."""

    def _resolve(
        self,
        text_preview: str,
        overrides: dict[str, Any],
    ) -> Any:
        """Хелпер для вызова resolve_prompt_directives с _meta overrides."""
        return resolve_prompt_directives(
            params={"_meta": {"promptDirectives": overrides}},
            text_preview=text_preview,
        )

    def test_request_tool_override(self) -> None:
        """requestTool override принудительно включает tool-flow."""
        directives = self._resolve("plain text", {"requestTool": True})

        assert directives.request_tool is True

    def test_publish_plan_override(self) -> None:
        """publishPlan override принудительно публикует план."""
        directives = self._resolve("plain text", {"publishPlan": True})

        assert directives.publish_plan is True

    def test_plan_entries_override_sets_entries_and_forces_publish(self) -> None:
        """planEntries override нормализует записи и включает publish_plan."""
        entries = [{"content": "step 1"}, {"content": "step 2"}]
        directives = self._resolve("plain text", {"planEntries": entries})

        assert directives.plan_entries is not None
        assert len(directives.plan_entries) == 2
        assert directives.publish_plan is True

    def test_tool_kind_override_with_normalization(self) -> None:
        """toolKind override нормализуется через normalize_tool_kind."""
        directives = self._resolve("plain text", {"toolKind": "WRITE"})

        assert directives.tool_kind == "edit"

    def test_fs_read_path_override(self) -> None:
        """fsReadPath override устанавливает путь чтения."""
        directives = self._resolve(
            "plain text", {"fsReadPath": "  /tmp/read.txt  "}
        )

        assert directives.fs_read_path == "/tmp/read.txt"

    def test_fs_write_path_and_content_override(self) -> None:
        """fsWritePath и fsWriteContent overrides устанавливают write-поля."""
        directives = self._resolve(
            "plain text",
            {
                "fsWritePath": "/tmp/write.txt",
                "fsWriteContent": "content",
            },
        )

        assert directives.fs_write_path == "/tmp/write.txt"
        assert directives.fs_write_content == "content"

    def test_terminal_command_override(self) -> None:
        """terminalCommand override устанавливает команду терминала."""
        directives = self._resolve(
            "plain text", {"terminalCommand": "  echo hi  "}
        )

        assert directives.terminal_command == "echo hi"

    def test_keep_tool_pending_auto_sets_request_tool(self) -> None:
        """keepToolPending без requestTool всё равно включает tool-flow."""
        directives = self._resolve("plain text", {"keepToolPending": True})

        assert directives.keep_tool_pending is True
        assert directives.request_tool is True

    def test_meta_override_overrides_slash_command(self) -> None:
        """_meta override имеет приоритет над slash-командой."""
        directives = self._resolve("/tool execute", {"toolKind": "read"})

        assert directives.tool_kind == "read"


class TestNormalizeToolKind:
    """Тесты нормализации tool kind."""

    _DEFAULT_TOOL_KINDS = {
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

    def test_known_kind_returns_unchanged(self) -> None:
        """Известный kind 'read' возвращается без изменений."""
        assert normalize_tool_kind("read", self._DEFAULT_TOOL_KINDS) == "read"

    def test_write_alias_returns_edit(self) -> None:
        """Алиас 'write' нормализуется в 'edit'."""
        assert normalize_tool_kind("write", self._DEFAULT_TOOL_KINDS) == "edit"

    def test_unknown_kind_returns_none(self) -> None:
        """Неизвестный kind возвращает None."""
        assert normalize_tool_kind("unknown", self._DEFAULT_TOOL_KINDS) is None

    def test_default_supported_kinds_used(self) -> None:
        """При отсутствии набора используются встроенные supported kinds."""
        assert normalize_tool_kind("execute") == "execute"


class TestNormalizePlanEntries:
    """Тесты нормализации structured planEntries."""

    def test_valid_entries_normalized(self) -> None:
        """Валидные entries нормализуются с дефолтными priority/status."""
        raw = [{"content": "step 1"}, {"content": "step 2"}]
        normalized = normalize_plan_entries(raw)

        assert normalized is not None
        assert len(normalized) == 2
        assert normalized[0] == {
            "content": "step 1",
            "priority": "medium",
            "status": "pending",
        }

    def test_missing_content_skipped(self) -> None:
        """Entries без content пропускаются."""
        raw = [{"content": "valid"}, {"priority": "high"}, {"content": "  "}]
        normalized = normalize_plan_entries(raw)

        assert normalized is not None
        assert len(normalized) == 1
        assert normalized[0]["content"] == "valid"

    def test_invalid_priority_defaults_to_medium(self) -> None:
        """Некорректный priority заменяется на 'medium'."""
        raw = [{"content": "step", "priority": "urgent"}]
        normalized = normalize_plan_entries(raw)

        assert normalized is not None
        assert normalized[0]["priority"] == "medium"

    def test_invalid_status_defaults_to_pending(self) -> None:
        """Некорректный status заменяется на 'pending'."""
        raw = [{"content": "step", "status": "running"}]
        normalized = normalize_plan_entries(raw)

        assert normalized is not None
        assert normalized[0]["status"] == "pending"

    def test_non_list_input_returns_none(self) -> None:
        """Не-список на входе возвращает None."""
        assert normalize_plan_entries("not a list") is None
        assert normalize_plan_entries({"content": "step"}) is None

    def test_empty_list_returns_none(self) -> None:
        """Пустой список на входе возвращает None."""
        assert normalize_plan_entries([]) is None

    def test_all_valid_priorities_and_statuses(self) -> None:
        """Все допустимые priority и status проходят без изменений."""
        raw = [
            {"content": "low", "priority": "low", "status": "completed"},
            {"content": "high", "priority": "high", "status": "in_progress"},
            {"content": "cancelled", "status": "cancelled"},
        ]
        normalized = normalize_plan_entries(raw)

        assert normalized is not None
        assert normalized[0]["priority"] == "low"
        assert normalized[0]["status"] == "completed"
        assert normalized[1]["priority"] == "high"
        assert normalized[1]["status"] == "in_progress"
        assert normalized[2]["status"] == "cancelled"


class TestNormalizeSessionPath:
    """Тесты нормализации пути сессии."""

    def test_absolute_path_unchanged(self) -> None:
        """Абсолютный путь возвращается без изменений."""
        assert normalize_session_path("/tmp", "/etc/hosts") == "/etc/hosts"

    def test_relative_path_resolved_against_cwd(self) -> None:
        """Относительный путь разрешается относительно cwd."""
        assert normalize_session_path("/tmp", "file.txt") == str(
            Path("/tmp") / "file.txt"
        )

    def test_empty_or_whitespace_returns_none(self) -> None:
        """Пустая строка или whitespace возвращает None."""
        assert normalize_session_path("/tmp", "") is None
        assert normalize_session_path("/tmp", "   ") is None


class TestResolveToolTitle:
    """Тесты разрешения заголовка tool-call по kind."""

    def test_known_kinds_return_correct_titles(self) -> None:
        """Каждый известный kind возвращает корректный title."""
        expected = {
            "read": "Tool read operation",
            "edit": "Tool edit operation",
            "delete": "Tool delete operation",
            "move": "Tool move operation",
            "execute": "Tool execution",
            "search": "Tool search operation",
            "think": "Tool reasoning step",
            "fetch": "Tool fetch operation",
            "switch_mode": "Tool mode switch",
            "other": "Tool operation",
        }
        for kind, title in expected.items():
            assert resolve_tool_title(kind) == title, f"Failed for: {kind}"

    def test_unknown_kind_returns_default(self) -> None:
        """Неизвестный kind возвращает дефолтный title."""
        assert resolve_tool_title("unknown_kind") == "Tool operation"


class TestRuntimeCapabilityChecks:
    """Тесты проверок runtime-возможностей клиента."""

    def _make_session(self, caps: ClientRuntimeCapabilities | None) -> SessionState:
        """Хелпер для создания SessionState с заданными capabilities."""
        return SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
            runtime_capabilities=caps,
        )

    def test_can_run_tool_runtime_no_caps(self) -> None:
        """Отсутствие capabilities запрещает tool-runtime ветки."""
        session = self._make_session(None)

        assert can_run_tool_runtime(session) is False

    def test_can_run_tool_runtime_various_combinations(self) -> None:
        """tool-runtime доступен при любой из fs_read/fs_write/terminal."""
        assert can_run_tool_runtime(
            self._make_session(ClientRuntimeCapabilities(fs_read=True))
        ) is True
        assert can_run_tool_runtime(
            self._make_session(ClientRuntimeCapabilities(fs_write=True))
        ) is True
        assert can_run_tool_runtime(
            self._make_session(ClientRuntimeCapabilities(terminal=True))
        ) is True
        assert can_run_tool_runtime(
            self._make_session(ClientRuntimeCapabilities())
        ) is False

    def test_can_use_fs_client_rpc_no_caps(self) -> None:
        """Отсутствие capabilities запрещает fs client RPC."""
        session = self._make_session(None)

        assert can_use_fs_client_rpc(session, "fs_read") is False
        assert can_use_fs_client_rpc(session, "fs_write") is False

    def test_can_use_fs_client_rpc_various_combinations(self) -> None:
        """fs RPC доступен только при соответствующей capability."""
        assert can_use_fs_client_rpc(
            self._make_session(ClientRuntimeCapabilities(fs_read=True)), "fs_read"
        ) is True
        assert can_use_fs_client_rpc(
            self._make_session(ClientRuntimeCapabilities(fs_write=True)), "fs_read"
        ) is False
        assert can_use_fs_client_rpc(
            self._make_session(ClientRuntimeCapabilities(fs_write=True)), "fs_write"
        ) is True
        assert can_use_fs_client_rpc(
            self._make_session(ClientRuntimeCapabilities()), "fs_read"
        ) is False
        assert can_use_fs_client_rpc(
            self._make_session(ClientRuntimeCapabilities(fs_read=True)), "unknown"
        ) is False

    def test_can_use_terminal_client_rpc_no_caps(self) -> None:
        """Отсутствие capabilities запрещает terminal client RPC."""
        session = self._make_session(None)

        assert can_use_terminal_client_rpc(session) is False

    def test_can_use_terminal_client_rpc_various_combinations(self) -> None:
        """terminal RPC доступен только при terminal capability."""
        assert can_use_terminal_client_rpc(
            self._make_session(ClientRuntimeCapabilities(terminal=True))
        ) is True
        assert can_use_terminal_client_rpc(
            self._make_session(ClientRuntimeCapabilities(fs_read=True))
        ) is False
        assert can_use_terminal_client_rpc(
            self._make_session(ClientRuntimeCapabilities())
        ) is False
