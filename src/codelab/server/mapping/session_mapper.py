"""Mapper между domain Session и protocol SessionState.

Обеспечивает конвертацию между domain моделью Session (aggregate root)
и protocol моделью SessionState (Pydantic BaseModel для сериализации).
"""

from datetime import datetime
from typing import Any

from codelab.server.agent.config.models import SessionMetrics
from codelab.server.domain.conversation import ConversationMessage, MessageContent
from codelab.server.domain.plan import PlanEntry
from codelab.server.domain.session import (
    AgentPlan,
    ConversationHistory,
    MultiAgentState,
    PermissionState,
    Session,
    SessionConfig,
    SessionRuntime,
    ToolCallRegistry,
    TurnState,
)
from codelab.server.domain.value_objects import (
    MessageRole,
    PlanPriority,
    PlanStatus,
    SessionId,
)
from codelab.server.mapping.tool_call_mapper import ToolCallMapper
from codelab.server.protocol.state import (
    ActiveTurnState,
    PendingClientRequestState,
    SessionState,
)
from codelab.shared.capabilities import ClientCapabilities


class SessionMapper:
    """Конвертер между domain Session и protocol SessionState."""

    @staticmethod
    def to_protocol(session: Session) -> SessionState:
        """Конвертировать domain Session в protocol SessionState.

        Args:
            session: Domain Session aggregate

        Returns:
            Protocol SessionState для сериализации
        """
        from codelab.server.models import HistoryMessage

        # Конвертируем историю сообщений (round-trip без потерь: роль и tool_call_id
        # сохраняются; HistoryMessage теперь поддерживает role="tool" — write-фаза D1).
        history = []
        for msg in session.history.get_messages():
            history.append(
                HistoryMessage(
                    role=msg.role.value,  # type: ignore[arg-type]
                    content=msg.content.text,
                    timestamp=msg.timestamp.isoformat() if msg.timestamp else None,
                    tool_call_id=msg.tool_call_id,
                )
            )

        # Конвертируем tool calls (делегируем ToolCallMapper — round-trip без потерь, D4-b/b3)
        tool_calls = {tc.id: ToolCallMapper.to_protocol(tc) for tc in session.tool_calls.get_all()}

        # Конвертируем plan
        latest_plan = []
        for step in session.plan.get_steps():
            latest_plan.append(
                {
                    "content": step.content,
                    "priority": step.priority.value,
                    "status": step.status.value,
                }
            )

        # Создаем SessionState
        state = SessionState(
            session_id=session.id,
            schema_version=session.schema_version,
            cwd=session.config.cwd,
            mcp_servers=list(session.config.mcp_servers),
            title=session.title,
            config_values=session.config.config_values,
            history=history,
            tool_calls=tool_calls,
            tool_call_counter=session.tool_calls.counter,
            permission_policy=session.permissions.policy,
            cancelled_permission_requests=set(session.permissions.cancelled_requests),  # type: ignore[arg-type]
            available_commands=list(session.available_commands),
            latest_plan=latest_plan,
            active_strategy=session.multi_agent.active_strategy,
            active_agents=session.multi_agent.active_agents,
            parent_session_id=session.multi_agent.parent_session_id,
            child_session_ids=session.multi_agent.child_session_ids,
            is_child_session=session.multi_agent.is_child_session,
            task_result=session.multi_agent.task_result,
            sliced_summary=session.multi_agent.sliced_summary,
        )
        # `updated_at` несём как есть; регенерацию (default_factory=now) допускаем
        # только для доменных сессий без метки (свежесозданных, не из round-trip).
        if session.updated_at is not None:
            state.updated_at = session.updated_at

        # Runtime capabilities
        if session.config.runtime_capabilities:
            from codelab.server.protocol.state import ClientRuntimeCapabilities

            state.runtime_capabilities = ClientRuntimeCapabilities(
                fs_read=session.config.runtime_capabilities.fs_read,
                fs_write=session.config.runtime_capabilities.fs_write,
                terminal=session.config.runtime_capabilities.terminal,
            )

        # Turn-состояние (доменный TurnState VO → wire-DTO ActiveTurnState, ADR-006)
        if session.active_turn is not None:
            state.active_turn = SessionMapper._turn_to_protocol(
                session.active_turn, str(session.id)
            )

        # Рантайм-состояние (доменный SessionRuntime VO → плоские поля SessionState)
        runtime = session.runtime
        state.terminals = dict(runtime.terminals)
        state.terminal_counter = runtime.terminal_counter
        state.events_history = [dict(e) for e in runtime.events_history]
        state.cancelled_client_rpc_requests = set(runtime.cancelled_client_rpc_requests)  # type: ignore[arg-type]
        state.pending_prompt_response = (
            dict(runtime.pending_prompt_response)
            if runtime.pending_prompt_response is not None
            else None
        )
        state.correlation_id = runtime.correlation_id
        if runtime.session_metrics is not None:
            state.session_metrics = SessionMetrics.model_validate(runtime.session_metrics)

        return state

    @staticmethod
    def _turn_to_protocol(turn: TurnState, session_id: str) -> ActiveTurnState:
        """TurnState VO → wire-DTO ActiveTurnState (round-trip без потерь)."""
        pending = None
        if turn.pending_external_request is not None:
            pending = PendingClientRequestState.model_validate(turn.pending_external_request)
        return ActiveTurnState(
            prompt_request_id=turn.prompt_request_id,
            session_id=session_id,
            cancel_requested=turn.cancel_requested,
            permission_request_id=turn.permission_request_id,
            permission_tool_call_id=turn.permission_tool_call_id,
            phase=turn.phase,
            pending_client_request=pending,
        )

    @staticmethod
    def to_domain(state: SessionState) -> Session:
        """Конвертировать protocol SessionState в domain Session.

        Args:
            state: Protocol SessionState из хранилища

        Returns:
            Domain Session aggregate
        """
        # Создаем SessionConfig
        runtime_caps = None
        if state.runtime_capabilities:
            runtime_caps = ClientCapabilities(
                fs_read=state.runtime_capabilities.fs_read,
                fs_write=state.runtime_capabilities.fs_write,
                terminal=state.runtime_capabilities.terminal,
            )

        config = SessionConfig(
            cwd=state.cwd,
            config_values=state.config_values,
            active_strategy=state.active_strategy,
            runtime_capabilities=runtime_caps,
            mcp_servers=[dict(s) for s in state.mcp_servers],
        )

        history = SessionMapper._build_history(state)
        tool_calls = SessionMapper._build_tool_calls(state)

        # Создаем PermissionState
        permissions = PermissionState(
            policy=state.permission_policy,
            cancelled_requests={str(r) for r in state.cancelled_permission_requests},
        )

        plan = SessionMapper._build_plan(state)

        # Создаем MultiAgentState
        multi_agent = MultiAgentState(
            active_strategy=state.active_strategy,
            active_agents=state.active_agents,
            parent_session_id=state.parent_session_id,
            child_session_ids=state.child_session_ids,
            is_child_session=state.is_child_session,
            task_result=state.task_result,
            sliced_summary=state.sliced_summary,
        )

        active_turn = SessionMapper._build_turn(state)
        runtime = SessionMapper._build_runtime(state)

        # Создаем Session
        return Session(
            id=SessionId(state.session_id),
            config=config,
            history=history,
            tool_calls=tool_calls,
            permissions=permissions,
            plan=plan,
            multi_agent=multi_agent,
            active_turn=active_turn,
            runtime=runtime,
            title=state.title,
            updated_at=state.updated_at,
            schema_version=state.schema_version,
            available_commands=SessionMapper._normalize_commands(state.available_commands),
        )

    @staticmethod
    def _normalize_commands(commands: list[Any]) -> list[dict[str, Any]]:
        """available_commands → list[dict]: AvailableCommand (pydantic) или dict."""
        result: list[dict[str, Any]] = []
        for cmd in commands:
            if isinstance(cmd, dict):
                result.append(dict(cmd))
            elif hasattr(cmd, "model_dump"):
                result.append(cmd.model_dump())
        return result

    @staticmethod
    def _build_turn(state: SessionState) -> TurnState | None:
        """Собирает доменный TurnState VO из wire-DTO ActiveTurnState."""
        at = state.active_turn
        if at is None:
            return None
        pending = (
            at.pending_client_request.model_dump()
            if at.pending_client_request is not None
            else None
        )
        return TurnState(
            prompt_request_id=at.prompt_request_id,
            cancel_requested=at.cancel_requested,
            permission_request_id=at.permission_request_id,
            permission_tool_call_id=at.permission_tool_call_id,
            phase=at.phase,
            pending_external_request=pending,
        )

    @staticmethod
    def _build_runtime(state: SessionState) -> SessionRuntime:
        """Собирает доменный SessionRuntime VO из плоских runtime-полей SessionState."""
        return SessionRuntime(
            terminals=dict(state.terminals),
            terminal_counter=state.terminal_counter,
            events_history=[dict(e) for e in state.events_history],
            cancelled_client_rpc_requests=set(state.cancelled_client_rpc_requests),
            pending_prompt_response=(
                dict(state.pending_prompt_response)
                if state.pending_prompt_response is not None
                else None
            ),
            session_metrics=(
                state.session_metrics.model_dump() if state.session_metrics is not None else None
            ),
            correlation_id=state.correlation_id,
        )

    @staticmethod
    def _build_history(state: SessionState) -> ConversationHistory:
        """Собирает ConversationHistory из protocol-history (HistoryMessage или dict)."""
        history = ConversationHistory()
        for msg_data in state.history:
            tool_call_id: str | None = None
            timestamp_raw: str | None = None
            if hasattr(msg_data, "role"):
                role_str = msg_data.role
                content_text = msg_data.content if isinstance(msg_data.content, str) else ""
                tool_call_id = getattr(msg_data, "tool_call_id", None)
                timestamp_raw = getattr(msg_data, "timestamp", None)
            elif isinstance(msg_data, dict):
                role_str = msg_data.get("role", "user")
                content_text = msg_data.get("content", "")
                if not isinstance(content_text, str):
                    content_text = ""
                tool_call_id = msg_data.get("tool_call_id")
                timestamp_raw = msg_data.get("timestamp")
            else:
                continue

            try:
                role = MessageRole(role_str)
            except ValueError:
                role = MessageRole.USER

            # null остаётся null — время не синтезируется при пересборке (ACP updatedAt).
            timestamp = datetime.fromisoformat(timestamp_raw) if timestamp_raw else None

            history.add(
                ConversationMessage(
                    role=role,
                    content=MessageContent(text=content_text),
                    timestamp=timestamp,
                    tool_call_id=tool_call_id,
                )
            )
        return history

    @staticmethod
    def _build_tool_calls(state: SessionState) -> ToolCallRegistry:
        """Собирает ToolCallRegistry из protocol tool_calls (делегируя ToolCallMapper)."""
        tool_calls = ToolCallRegistry()
        tool_calls.counter = state.tool_call_counter
        for tc_id, tc_state in state.tool_calls.items():
            tool_calls.calls[tc_id] = ToolCallMapper.to_domain(tc_state)
        return tool_calls

    @staticmethod
    def _build_plan(state: SessionState) -> AgentPlan:
        """Собирает AgentPlan из protocol latest_plan (только dict-записи)."""
        plan = AgentPlan()
        for step_data in state.latest_plan:
            if not isinstance(step_data, dict):
                continue
            try:
                priority = PlanPriority(step_data.get("priority", "medium"))
            except ValueError:
                priority = PlanPriority.MEDIUM
            try:
                status = PlanStatus(step_data.get("status", "pending"))
            except ValueError:
                status = PlanStatus.PENDING
            plan.add_step(
                PlanEntry(content=step_data.get("content", ""), priority=priority, status=status)
            )
        return plan
