"""Дополнительные тесты для оставшихся непокрытых функций prompt-обработчика.

Покрывают жизненный цикл prompt-turn, валидацию контента, управление
tool calls, client RPC lifecycle и permission resolution.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from codelab.server.protocol.handlers.prompt import (
    build_executor_tool_execution_updates,
    build_fs_client_request,
    build_plan_entries,
    build_policy_tool_execution_updates,
    build_terminal_client_request,
    cancel_active_tool_calls,
    complete_active_turn,
    create_tool_call,
    extract_prompt_directives,
    finalize_failed_client_rpc_request,
    find_session_by_pending_client_request_id,
    normalize_stop_reason,
    resolve_pending_client_rpc_response_impl,
    resolve_permission_response_impl,
    resolve_prompt_directives,
    resolve_prompt_stop_reason,
    should_auto_complete_active_turn,
    update_tool_call_status,
    validate_prompt_content,
)
from codelab.server.protocol.state import (
    ActiveTurnState,
    ClientRuntimeCapabilities,
    PendingClientRequestState,
    PromptDirectives,
    SessionState,
)


class TestCompleteActiveTurn:
    """Тесты завершения активного prompt-turn."""

    def test_complete_active_turn_returns_response(self) -> None:
        """complete_active_turn возвращает response с нормализованным stopReason."""
        session = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
            active_turn=ActiveTurnState(
                prompt_request_id="req_1",
                session_id="sess_1",
            ),
        )

        response = complete_active_turn(session, stop_reason="max_tokens")

        assert response is not None
        assert response.id == "req_1"
        assert response.result == {"stopReason": "max_tokens"}
        assert session.active_turn is None

    def test_complete_active_turn_without_active_turn_returns_none(self) -> None:
        """complete_active_turn возвращает None если нет активного turn."""
        session = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
        )

        assert complete_active_turn(session) is None


class TestShouldAutoCompleteActiveTurn:
    """Тесты проверки возможности автозавершения turn."""

    def test_no_active_turn_returns_false(self) -> None:
        """Без активного turn автозавершение невозможно."""
        session = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
        )

        assert should_auto_complete_active_turn(session) is False

    def test_waiting_tool_completion_returns_true(self) -> None:
        """Фаза waiting_tool_completion разрешает автозавершение."""
        session = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
            active_turn=ActiveTurnState(
                prompt_request_id="req_1",
                session_id="sess_1",
                phase="waiting_tool_completion",
            ),
        )

        assert should_auto_complete_active_turn(session) is True

    def test_other_phase_returns_false(self) -> None:
        """Другие фазы не разрешают автозавершение."""
        session = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
            active_turn=ActiveTurnState(
                prompt_request_id="req_1",
                session_id="sess_1",
                phase="running",
            ),
        )

        assert should_auto_complete_active_turn(session) is False


class TestValidatePromptContent:
    """Тесты валидации prompt-контента."""

    def test_valid_text_block_returns_none(self) -> None:
        """Валидный text-block проходит валидацию."""
        assert validate_prompt_content("req_1", [{"type": "text", "text": "hi"}]) is None

    def test_non_dict_block_returns_error(self) -> None:
        """Элемент не являющийся dict вызывает ошибку валидации."""
        error = validate_prompt_content("req_1", ["not a dict"])

        assert error is not None
        assert error.error is not None
        assert error.error.code == -32602

    def test_text_block_without_string_text_returns_error(self) -> None:
        """text-block без строкового content вызывает ошибку."""
        error = validate_prompt_content("req_1", [{"type": "text", "text": 123}])

        assert error is not None
        assert error.error is not None
        assert "text content requires text string" in error.error.message

    def test_text_block_too_long_returns_error(self) -> None:
        """Слишком длинный текст вызывает ошибку."""
        long_text = "x" * 100_001
        error = validate_prompt_content("req_1", [{"type": "text", "text": long_text}])

        assert error is not None
        assert "prompt text too long" in error.error.message

    def test_valid_resource_link_returns_none(self) -> None:
        """Валидный resource_link проходит валидацию."""
        block = {"type": "resource_link", "uri": "file:///tmp/a.txt", "name": "a"}
        assert validate_prompt_content("req_1", [block]) is None

    def test_resource_link_missing_uri_or_name_returns_error(self) -> None:
        """resource_link без uri или name вызывает ошибку."""
        error = validate_prompt_content(
            "req_1",
            [{"type": "resource_link", "uri": "file:///tmp/a.txt"}],
        )

        assert error is not None
        assert "resource_link requires uri and name" in error.error.message

    def test_unsupported_content_type_returns_error(self) -> None:
        """Неподдерживаемый тип контента вызывает ошибку."""
        error = validate_prompt_content("req_1", [{"type": "image"}])

        assert error is not None
        assert "unsupported content type image" in error.error.message


class TestExtractPromptDirectivesStopReasons:
    """Тесты slash-команд, управляющих stopReason."""

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

    def test_stop_max_tokens(self) -> None:
        """/stop-max-tokens устанавливает forced_stop_reason=max_tokens."""
        directives = extract_prompt_directives(
            "/stop-max-tokens", self._DEFAULT_TOOL_KINDS
        )

        assert directives.forced_stop_reason == "max_tokens"

    def test_stop_max_turn_requests(self) -> None:
        """/stop-max-turn-requests устанавливает forced_stop_reason=max_turn_requests."""
        directives = extract_prompt_directives(
            "/stop-max-turn-requests", self._DEFAULT_TOOL_KINDS
        )

        assert directives.forced_stop_reason == "max_turn_requests"

    def test_stop_refuse(self) -> None:
        """/refuse устанавливает forced_stop_reason=refusal."""
        directives = extract_prompt_directives("/refuse", self._DEFAULT_TOOL_KINDS)

        assert directives.forced_stop_reason == "refusal"


class TestResolvePromptDirectivesDefaultsAndOverrides:
    """Тесты resolve_prompt_directives: defaults и оставшиеся overrides."""

    def test_default_supported_tool_kinds_used(self) -> None:
        """При отсутствии supported_tool_kinds используется встроенный набор."""
        directives = resolve_prompt_directives(
            params={"_meta": {"promptDirectives": {"toolKind": "execute"}}},
            text_preview="hello",
        )

        assert directives.tool_kind == "execute"

    def test_forced_stop_reason_override(self) -> None:
        """forcedStopReason override нормализуется через normalize_stop_reason."""
        directives = resolve_prompt_directives(
            params={"_meta": {"promptDirectives": {"forcedStopReason": "max_tokens"}}},
            text_preview="hello",
        )

        assert directives.forced_stop_reason == "max_tokens"

    def test_forced_stop_reason_unknown_normalized_to_end_turn(self) -> None:
        """Неизвестный forcedStopReason нормализуется к end_turn."""
        directives = resolve_prompt_directives(
            params={"_meta": {"promptDirectives": {"forcedStopReason": "unknown"}}},
            text_preview="hello",
        )

        assert directives.forced_stop_reason == "end_turn"

    def test_non_dict_meta_returns_directives(self) -> None:
        """Невалидный _meta игнорируется и возвращаются slash-directives."""
        directives = resolve_prompt_directives(
            params={"_meta": "not a dict"},
            text_preview="/plan",
        )

        assert directives.publish_plan is True

    def test_non_dict_prompt_directives_returns_directives(self) -> None:
        """Невалидный promptDirectives игнорируется."""
        directives = resolve_prompt_directives(
            params={"_meta": {"promptDirectives": "not a dict"}},
            text_preview="/tool execute",
        )

        assert directives.request_tool is True


class TestResolvePromptStopReason:
    """Тесты resolve_prompt_stop_reason."""

    def test_forced_stop_reason_used(self) -> None:
        """Возвращает forced_stop_reason если он задан."""
        directives = PromptDirectives(forced_stop_reason="max_tokens")

        assert resolve_prompt_stop_reason(directives) == "max_tokens"

    def test_default_end_turn(self) -> None:
        """Возвращает end_turn по умолчанию."""
        directives = PromptDirectives()

        assert resolve_prompt_stop_reason(directives) == "end_turn"


class TestNormalizeStopReason:
    """Тесты normalize_stop_reason."""

    def test_known_reason_returned(self) -> None:
        """Известная причина возвращается без изменений."""
        assert normalize_stop_reason("max_tokens") == "max_tokens"

    def test_unknown_reason_defaults_to_end_turn(self) -> None:
        """Неизвестная причина нормализуется к end_turn."""
        assert normalize_stop_reason("unknown") == "end_turn"

    def test_custom_supported_reasons(self) -> None:
        """Поддерживает кастомный набор supported_stop_reasons."""
        assert normalize_stop_reason("custom", {"custom"}) == "custom"
        assert normalize_stop_reason("other", {"custom"}) == "end_turn"


class TestBuildExecutorToolExecutionUpdates:
    """Тесты build_executor_tool_execution_updates."""

    def _make_session_with_tool(self) -> SessionState:
        """Создает сессию с одним pending tool call."""
        session = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
        )
        create_tool_call(session, title="Demo", kind="other")
        return session

    def test_leave_running_returns_single_in_progress(self) -> None:
        """leave_running=True возвращает только in_progress update."""
        session = self._make_session_with_tool()
        updates = build_executor_tool_execution_updates(
            session=session,
            session_id="sess_1",
            tool_call_id="call_001",
            leave_running=True,
        )

        assert len(updates) == 1
        assert updates[0].params["update"]["status"] == "in_progress"
        assert session.tool_calls["call_001"].status == "in_progress"

    def test_full_lifecycle_returns_in_progress_and_completed(self) -> None:
        """leave_running=False возвращает in_progress и completed updates."""
        session = self._make_session_with_tool()
        updates = build_executor_tool_execution_updates(
            session=session,
            session_id="sess_1",
            tool_call_id="call_001",
            leave_running=False,
        )

        assert len(updates) == 2
        assert updates[0].params["update"]["status"] == "in_progress"
        assert updates[1].params["update"]["status"] == "completed"
        assert session.tool_calls["call_001"].status == "completed"


class TestBuildPolicyToolExecutionUpdates:
    """Тесты build_policy_tool_execution_updates."""

    def _make_session_with_tool(self) -> SessionState:
        """Создает сессию с одним pending tool call."""
        session = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
        )
        create_tool_call(session, title="Demo", kind="other")
        return session

    def test_allowed_true_returns_in_progress(self) -> None:
        """allowed=True отмечает tool_call как in_progress."""
        session = self._make_session_with_tool()
        updates = build_policy_tool_execution_updates(
            session=session,
            session_id="sess_1",
            tool_call_id="call_001",
            allowed=True,
        )

        assert len(updates) == 1
        assert updates[0].params["update"]["status"] == "in_progress"
        assert session.tool_calls["call_001"].status == "in_progress"

    def test_allowed_false_returns_cancelled(self) -> None:
        """allowed=False отменяет tool_call."""
        session = self._make_session_with_tool()
        updates = build_policy_tool_execution_updates(
            session=session,
            session_id="sess_1",
            tool_call_id="call_001",
            allowed=False,
        )

        assert len(updates) == 1
        assert updates[0].params["update"]["status"] == "cancelled"
        assert session.tool_calls["call_001"].status == "cancelled"


class TestBuildPlanEntries:
    """Тесты build_plan_entries."""

    def test_uses_directive_plan_entries(self) -> None:
        """Если заданы plan_entries, возвращает их."""
        entries = [{"content": "step", "priority": "high", "status": "pending"}]
        directives = PromptDirectives(plan_entries=entries)

        assert build_plan_entries(directives=directives, text_preview="text") == entries

    def test_generates_default_entries(self) -> None:
        """Без plan_entries генерирует дефолтный план по preview."""
        directives = PromptDirectives()
        result = build_plan_entries(directives=directives, text_preview="  do thing  ")

        assert len(result) == 3
        assert "Уточнить задачу: do thing" in result[0]["content"]
        assert result[0]["status"] == "completed"
        assert result[1]["status"] == "in_progress"
        assert result[2]["status"] == "pending"

    def test_empty_preview_defaults_to_placeholder(self) -> None:
        """Пустой preview заменяется на placeholder."""
        directives = PromptDirectives()
        result = build_plan_entries(directives=directives, text_preview="   ")

        assert "выполнение запроса" in result[0]["content"]


class TestBuildFsClientRequest:
    """Тесты build_fs_client_request."""

    def _make_session(self) -> SessionState:
        """Создает сессию с fs-возможностями."""
        return SessionState(
            session_id="sess_1",
            cwd="/work",
            mcp_servers=[],
            runtime_capabilities=ClientRuntimeCapabilities(fs_read=True, fs_write=True),
        )

    def test_fs_read_request(self) -> None:
        """Подготавливает fs/read_text_file request."""
        session = self._make_session()
        directives = PromptDirectives(fs_read_path="file.txt")
        prepared = build_fs_client_request(
            session=session,
            session_id="sess_1",
            directives=directives,
        )

        assert prepared is not None
        assert prepared.kind == "fs_read"
        assert len(prepared.messages) == 2
        assert prepared.pending_request.kind == "fs_read"
        assert prepared.pending_request.path == "/work/file.txt"
        assert session.tool_calls["call_001"].kind == "read"

    def test_fs_read_invalid_path_returns_none(self) -> None:
        """Невалидный путь чтения возвращает None."""
        session = self._make_session()
        directives = PromptDirectives(fs_read_path="   ")

        assert (
            build_fs_client_request(
                session=session,
                session_id="sess_1",
                directives=directives,
            )
            is None
        )

    def test_fs_write_request(self) -> None:
        """Подготавливает fs/write_text_file request."""
        session = self._make_session()
        directives = PromptDirectives(
            fs_write_path="file.txt",
            fs_write_content="hello",
        )
        prepared = build_fs_client_request(
            session=session,
            session_id="sess_1",
            directives=directives,
        )

        assert prepared is not None
        assert prepared.kind == "fs_write"
        assert prepared.pending_request.kind == "fs_write"
        assert prepared.pending_request.expected_new_text == "hello"
        assert session.tool_calls["call_001"].kind == "edit"

    def test_no_fs_directive_returns_none(self) -> None:
        """Без fs-directives возвращает None."""
        session = self._make_session()
        directives = PromptDirectives()

        assert (
            build_fs_client_request(
                session=session,
                session_id="sess_1",
                directives=directives,
            )
            is None
        )


class TestBuildTerminalClientRequest:
    """Тесты build_terminal_client_request."""

    def _make_session(self) -> SessionState:
        """Создает сессию с terminal-возможностью."""
        return SessionState(
            session_id="sess_1",
            cwd="/work",
            mcp_servers=[],
            runtime_capabilities=ClientRuntimeCapabilities(terminal=True),
        )

    def test_terminal_create_request(self) -> None:
        """Подготавливает terminal/create request."""
        session = self._make_session()
        directives = PromptDirectives(terminal_command="echo hi")
        prepared = build_terminal_client_request(
            session=session,
            session_id="sess_1",
            directives=directives,
        )

        assert prepared is not None
        assert prepared.kind == "terminal_create"
        assert len(prepared.messages) == 2
        assert prepared.pending_request.kind == "terminal_create"
        assert prepared.pending_request.path == "echo hi"
        assert session.tool_calls["call_001"].kind == "execute"

    def test_no_terminal_command_returns_none(self) -> None:
        """Без terminal_command возвращает None."""
        session = self._make_session()
        directives = PromptDirectives()

        assert (
            build_terminal_client_request(
                session=session,
                session_id="sess_1",
                directives=directives,
            )
            is None
        )


class TestCreateToolCall:
    """Тесты create_tool_call."""

    def test_creates_monotonic_ids(self) -> None:
        """create_tool_call генерирует монотонные call_xxx id."""
        session = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
        )

        first = create_tool_call(session, title="First", kind="read")
        second = create_tool_call(session, title="Second", kind="execute")

        assert first == "call_001"
        assert second == "call_002"
        assert session.tool_calls["call_001"].title == "First"
        assert session.tool_calls["call_002"].kind == "execute"


class TestUpdateToolCallStatus:
    """Тесты update_tool_call_status."""

    def test_valid_transition_updates_status(self) -> None:
        """Допустимый переход обновляет статус."""
        session = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
        )
        create_tool_call(session, title="Demo", kind="other")
        update_tool_call_status(session, "call_001", "in_progress")

        assert session.tool_calls["call_001"].status == "in_progress"

    def test_invalid_transition_ignored(self) -> None:
        """Недопустимый переход игнорируется."""
        session = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
        )
        create_tool_call(session, title="Demo", kind="other")
        update_tool_call_status(session, "call_001", "completed")

        assert session.tool_calls["call_001"].status == "pending"

    def test_same_status_allowed(self) -> None:
        """Переход в тот же статус разрешен."""
        session = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
        )
        create_tool_call(session, title="Demo", kind="other")
        update_tool_call_status(session, "call_001", "pending")

        assert session.tool_calls["call_001"].status == "pending"

    def test_updates_content(self) -> None:
        """Обновление статуса может сохранить content."""
        session = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
        )
        create_tool_call(session, title="Demo", kind="other")
        content = [{"type": "content", "content": {"type": "text", "text": "ok"}}]
        update_tool_call_status(session, "call_001", "in_progress", content=content)

        assert session.tool_calls["call_001"].content == content

    def test_missing_tool_call_ignored(self) -> None:
        """Обновление несуществующего tool call не падает."""
        session = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
        )
        update_tool_call_status(session, "nonexistent", "in_progress")

        assert "nonexistent" not in session.tool_calls


class TestCancelActiveToolCalls:
    """Тесты cancel_active_tool_calls."""

    def test_cancels_pending_and_in_progress(self) -> None:
        """Отменяет pending и in_progress tool calls."""
        session = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
        )
        create_tool_call(session, title="One", kind="other")
        create_tool_call(session, title="Two", kind="other")
        create_tool_call(session, title="Three", kind="other")
        update_tool_call_status(session, "call_002", "in_progress")
        update_tool_call_status(session, "call_003", "in_progress")
        update_tool_call_status(session, "call_003", "completed")

        notifications = cancel_active_tool_calls(session, "sess_1")

        assert len(notifications) == 2
        assert session.tool_calls["call_001"].status == "cancelled"
        assert session.tool_calls["call_002"].status == "cancelled"
        assert session.tool_calls["call_003"].status == "completed"


class TestFindSessionByPendingClientRequestId:
    """Тесты find_session_by_pending_client_request_id."""

    async def test_finds_matching_session(self) -> None:
        """Находит сессию с совпадающим pending client request id."""
        session = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
            active_turn=ActiveTurnState(
                prompt_request_id="req_1",
                session_id="sess_1",
                pending_client_request=PendingClientRequestState(
                    request_id="rpc_1",
                    kind="fs_read",
                    tool_call_id="call_001",
                    path="file.txt",
                ),
            ),
        )
        storage = AsyncMock()
        storage.list_sessions = AsyncMock(return_value=([session], None))

        found = await find_session_by_pending_client_request_id("rpc_1", storage)

        assert found is not None
        assert found.session_id == "sess_1"
        storage.list_sessions.assert_awaited_once_with(limit=500)

    async def test_returns_none_when_not_found(self) -> None:
        """Возвращает None если совпадения не найдено."""
        session = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
        )
        storage = AsyncMock()
        storage.list_sessions = AsyncMock(return_value=([session], None))

        found = await find_session_by_pending_client_request_id("rpc_1", storage)

        assert found is None


class TestResolvePendingClientRpcResponseImpl:
    """Тесты resolve_pending_client_rpc_response_impl."""

    def _make_session(self, pending: PendingClientRequestState) -> SessionState:
        """Создает сессию с активным turn и pending client request."""
        return SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
            active_turn=ActiveTurnState(
                prompt_request_id="req_1",
                session_id="sess_1",
                pending_client_request=pending,
            ),
        )

    def test_no_active_turn_returns_none(self) -> None:
        """Без active_turn возвращает None."""
        session = SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[])

        assert (
            resolve_pending_client_rpc_response_impl(
                session=session,
                request_id="rpc_1",
                result={},
                error=None,
            )
            is None
        )

    def test_no_pending_request_returns_none(self) -> None:
        """Без pending_client_request возвращает None."""
        session = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
            active_turn=ActiveTurnState(
                prompt_request_id="req_1",
                session_id="sess_1",
            ),
        )

        assert (
            resolve_pending_client_rpc_response_impl(
                session=session,
                request_id="rpc_1",
                result={},
                error=None,
            )
            is None
        )

    def test_error_response_finalizes_failed(self) -> None:
        """error в ответе финализирует failed client rpc."""
        pending = PendingClientRequestState(
            request_id="rpc_1",
            kind="fs_read",
            tool_call_id="call_001",
            path="file.txt",
        )
        session = self._make_session(pending)
        create_tool_call(session, title="Read", kind="read")

        outcome = resolve_pending_client_rpc_response_impl(
            session=session,
            request_id="rpc_1",
            result=None,
            error={"message": "not found"},
        )

        assert outcome is not None
        assert session.tool_calls["call_001"].status == "failed"
        assert session.active_turn is None

    def test_fs_read_invalid_result_finalizes_failed(self) -> None:
        """Невалидный результат fs/read_text_file финализирует failed."""
        pending = PendingClientRequestState(
            request_id="rpc_1",
            kind="fs_read",
            tool_call_id="call_001",
            path="file.txt",
        )
        session = self._make_session(pending)
        create_tool_call(session, title="Read", kind="read")

        outcome = resolve_pending_client_rpc_response_impl(
            session=session,
            request_id="rpc_1",
            result={"wrong": "shape"},
            error=None,
        )

        assert outcome is not None
        assert session.tool_calls["call_001"].status == "failed"

    def test_fs_read_success_completes_turn(self) -> None:
        """Успешный fs/read_text_file завершает tool call и turn."""
        pending = PendingClientRequestState(
            request_id="rpc_1",
            kind="fs_read",
            tool_call_id="call_001",
            path="file.txt",
        )
        session = self._make_session(pending)
        create_tool_call(session, title="Read", kind="read")
        update_tool_call_status(session, "call_001", "in_progress")

        outcome = resolve_pending_client_rpc_response_impl(
            session=session,
            request_id="rpc_1",
            result={"content": "file body"},
            error=None,
        )

        assert outcome is not None
        assert session.tool_calls["call_001"].status == "completed"
        assert session.active_turn is None
        assert len(outcome.followup_responses) == 1

    def test_fs_write_success_completes_turn(self) -> None:
        """Успешный fs/write_text_file завершает tool call и turn."""
        pending = PendingClientRequestState(
            request_id="rpc_1",
            kind="fs_write",
            tool_call_id="call_001",
            path="file.txt",
            expected_new_text="new",
        )
        session = self._make_session(pending)
        create_tool_call(session, title="Write", kind="edit")
        update_tool_call_status(session, "call_001", "in_progress")

        outcome = resolve_pending_client_rpc_response_impl(
            session=session,
            request_id="rpc_1",
            result={"oldText": "old", "newText": "new"},
            error=None,
        )

        assert outcome is not None
        assert session.tool_calls["call_001"].status == "completed"
        assert session.active_turn is None

    def test_terminal_create_missing_terminal_id_fails(self) -> None:
        """terminal/create без terminalId переводит tool call в failed."""
        pending = PendingClientRequestState(
            request_id="rpc_1",
            kind="terminal_create",
            tool_call_id="call_001",
            path="echo hi",
        )
        session = self._make_session(pending)
        create_tool_call(session, title="Run", kind="execute")

        outcome = resolve_pending_client_rpc_response_impl(
            session=session,
            request_id="rpc_1",
            result={},
            error=None,
        )

        assert outcome is not None
        assert session.tool_calls["call_001"].status == "failed"
        assert session.active_turn is None

    def test_terminal_create_success_starts_output_request(self) -> None:
        """terminal/create с terminalId создает terminal/output request."""
        pending = PendingClientRequestState(
            request_id="rpc_1",
            kind="terminal_create",
            tool_call_id="call_001",
            path="echo hi",
        )
        session = self._make_session(pending)
        create_tool_call(session, title="Run", kind="execute")

        outcome = resolve_pending_client_rpc_response_impl(
            session=session,
            request_id="rpc_1",
            result={"terminalId": "term_1"},
            error=None,
        )

        assert outcome is not None
        assert session.tool_calls["call_001"].status == "in_progress"
        assert session.active_turn is not None
        assert session.active_turn.pending_client_request.kind == "terminal_output"

    def test_terminal_output_with_exit_status_sends_release(self) -> None:
        """terminal/output с exitStatus отправляет terminal/release."""
        pending = PendingClientRequestState(
            request_id="rpc_1",
            kind="terminal_output",
            tool_call_id="call_001",
            path="echo hi",
            terminal_id="term_1",
        )
        session = self._make_session(pending)
        create_tool_call(session, title="Run", kind="execute")

        outcome = resolve_pending_client_rpc_response_impl(
            session=session,
            request_id="rpc_1",
            result={"output": "hi", "exitStatus": {"exitCode": 0}},
            error=None,
        )

        assert outcome is not None
        assert session.active_turn is not None
        assert session.active_turn.pending_client_request.kind == "terminal_release"

    def test_terminal_output_without_exit_status_sends_wait(self) -> None:
        """terminal/output без exitStatus отправляет terminal/wait_for_exit."""
        pending = PendingClientRequestState(
            request_id="rpc_1",
            kind="terminal_output",
            tool_call_id="call_001",
            path="echo hi",
            terminal_id="term_1",
        )
        session = self._make_session(pending)
        create_tool_call(session, title="Run", kind="execute")

        outcome = resolve_pending_client_rpc_response_impl(
            session=session,
            request_id="rpc_1",
            result={"output": "hi"},
            error=None,
        )

        assert outcome is not None
        assert session.active_turn.pending_client_request.kind == "terminal_wait_for_exit"

    def test_terminal_output_invalid_exit_status_fails(self) -> None:
        """Невалидный exitStatus в terminal/output финализирует failed."""
        pending = PendingClientRequestState(
            request_id="rpc_1",
            kind="terminal_output",
            tool_call_id="call_001",
            path="echo hi",
            terminal_id="term_1",
        )
        session = self._make_session(pending)
        create_tool_call(session, title="Run", kind="execute")

        outcome = resolve_pending_client_rpc_response_impl(
            session=session,
            request_id="rpc_1",
            result={"output": "hi", "exitStatus": "bad"},
            error=None,
        )

        assert outcome is not None
        assert session.tool_calls["call_001"].status == "failed"

    def test_terminal_wait_for_exit_success_releases(self) -> None:
        """terminal/wait_for_exit успешно переходит к terminal/release."""
        pending = PendingClientRequestState(
            request_id="rpc_1",
            kind="terminal_wait_for_exit",
            tool_call_id="call_001",
            path="echo hi",
            terminal_id="term_1",
            terminal_output="hi",
            terminal_truncated=False,
        )
        session = self._make_session(pending)
        create_tool_call(session, title="Run", kind="execute")

        outcome = resolve_pending_client_rpc_response_impl(
            session=session,
            request_id="rpc_1",
            result={"exitCode": 0},
            error=None,
        )

        assert outcome is not None
        assert session.active_turn.pending_client_request.kind == "terminal_release"

    def test_terminal_release_success_completes_turn(self) -> None:
        """terminal/release завершает tool call и turn."""
        pending = PendingClientRequestState(
            request_id="rpc_1",
            kind="terminal_release",
            tool_call_id="call_001",
            path="echo hi",
            terminal_id="term_1",
            terminal_output="hi",
            terminal_exit_code=0,
            terminal_truncated=False,
        )
        session = self._make_session(pending)
        create_tool_call(session, title="Run", kind="execute")
        update_tool_call_status(session, "call_001", "in_progress")

        outcome = resolve_pending_client_rpc_response_impl(
            session=session,
            request_id="rpc_1",
            result={},
            error=None,
        )

        assert outcome is not None
        assert session.tool_calls["call_001"].status == "completed"
        assert session.active_turn is None

    def test_unknown_pending_kind_returns_none(self) -> None:
        """Неизвестный pending.kind возвращает None."""
        pending = PendingClientRequestState(
            request_id="rpc_1",
            kind="unknown",
            tool_call_id="call_001",
            path="x",
        )
        session = self._make_session(pending)

        assert (
            resolve_pending_client_rpc_response_impl(
                session=session,
                request_id="rpc_1",
                result={},
                error=None,
            )
            is None
        )


class TestFinalizeFailedClientRpcRequest:
    """Тесты finalize_failed_client_rpc_request."""

    def test_finalizes_failed_tool_call_and_turn(self) -> None:
        """Финализирует failed tool call и активный turn."""
        session = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
            active_turn=ActiveTurnState(
                prompt_request_id="req_1",
                session_id="sess_1",
            ),
        )
        create_tool_call(session, title="Demo", kind="other")

        outcome = finalize_failed_client_rpc_request(
            session=session,
            session_id="sess_1",
            tool_call_id="call_001",
            failure_text="Failed",
        )

        assert outcome is not None
        assert session.tool_calls["call_001"].status == "failed"
        assert session.active_turn is None
        assert len(outcome.notifications) == 2
        assert len(outcome.followup_responses) == 1


class TestResolvePermissionResponseImpl:
    """Тесты resolve_permission_response_impl."""

    def _make_session(self) -> SessionState:
        """Создает сессию с активным permission turn."""
        return SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
            active_turn=ActiveTurnState(
                prompt_request_id="req_1",
                session_id="sess_1",
                permission_request_id="perm_1",
                permission_tool_call_id="call_001",
            ),
        )

    def test_no_active_turn_returns_none(self) -> None:
        """Без active_turn возвращает None."""
        session = SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[])

        assert (
            resolve_permission_response_impl(
                session=session,
                permission_request_id="perm_1",
                result={"outcome": {"outcome": "selected", "optionId": "allow_once"}},
            )
            is None
        )

    def test_no_permission_tool_call_id_returns_none(self) -> None:
        """Без permission_tool_call_id возвращает None."""
        session = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
            active_turn=ActiveTurnState(
                prompt_request_id="req_1",
                session_id="sess_1",
            ),
        )

        assert (
            resolve_permission_response_impl(
                session=session,
                permission_request_id="perm_1",
                result={"outcome": {"outcome": "selected", "optionId": "allow_once"}},
            )
            is None
        )

    def test_reject_cancels_turn(self) -> None:
        """Reject option отменяет tool call и завершает turn."""
        session = self._make_session()
        create_tool_call(session, title="Demo", kind="execute")

        outcome = resolve_permission_response_impl(
            session=session,
            permission_request_id="perm_1",
            result={"outcome": {"outcome": "selected", "optionId": "reject_once"}},
        )

        assert outcome is not None
        assert session.tool_calls["call_001"].status == "cancelled"
        assert session.active_turn is None
        assert len(outcome.followup_responses) == 1

    def test_allow_once_schedules_pending_execution(self) -> None:
        """Allow once сбрасывает permission state и планирует execution."""
        session = self._make_session()
        create_tool_call(session, title="Demo", kind="execute")

        outcome = resolve_permission_response_impl(
            session=session,
            permission_request_id="perm_1",
            result={"outcome": {"outcome": "selected", "optionId": "allow_once"}},
        )

        assert outcome is not None
        assert session.active_turn.permission_request_id is None
        assert session.active_turn.permission_tool_call_id is None
        assert outcome.pending_tool_execution is not None
        assert outcome.pending_tool_execution.tool_call_id == "call_001"

    def test_allow_always_stores_session_policy(self) -> None:
        """Allow always сохраняет решение в session.permission_policy."""
        session = self._make_session()
        create_tool_call(session, title="Demo", kind="execute")

        resolve_permission_response_impl(
            session=session,
            permission_request_id="perm_1",
            result={"outcome": {"outcome": "selected", "optionId": "allow_always"}},
        )

        assert session.permission_policy.get("execute") == "allow_always"

    def test_reject_always_stores_session_policy(self) -> None:
        """Reject always сохраняет решение в session.permission_policy."""
        session = self._make_session()
        create_tool_call(session, title="Demo", kind="execute")

        resolve_permission_response_impl(
            session=session,
            permission_request_id="perm_1",
            result={"outcome": {"outcome": "selected", "optionId": "reject_always"}},
        )

        assert session.permission_policy.get("execute") == "reject_always"
