"""Mapper между domain Session и protocol SessionState.

Обеспечивает конвертацию между domain моделью Session (aggregate root)
и protocol моделью SessionState (Pydantic BaseModel для сериализации).
"""

from codelab.server.domain.conversation import ConversationMessage, MessageContent
from codelab.server.domain.plan import PlanEntry
from codelab.server.domain.session import (
    AgentPlan,
    ConversationHistory,
    MultiAgentState,
    PermissionState,
    Session,
    SessionConfig,
    ToolCallRegistry,
)
from codelab.server.domain.tool_call import ToolCall
from codelab.server.domain.value_objects import (
    MessageRole,
    PlanPriority,
    PlanStatus,
    SessionId,
    ToolCallStatus,
)
from codelab.server.protocol.state import SessionState, ToolCallState
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

        # Конвертируем tool calls
        tool_calls = {}
        for tc in session.tool_calls.get_all():
            tool_calls[tc.id] = ToolCallState(
                tool_call_id=tc.id,
                title=tc.tool_name,
                kind="other",
                status=tc.status.value,
                tool_name=tc.tool_name,
                tool_arguments=tc.arguments,
            )

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
            cwd=session.config.cwd,
            config_values=session.config.config_values,
            history=history,
            tool_calls=tool_calls,
            tool_call_counter=session.tool_calls.counter,
            permission_policy=session.permissions.policy,
            cancelled_permission_requests=set(session.permissions.cancelled_requests),  # type: ignore[arg-type]
            latest_plan=latest_plan,
            active_strategy=session.multi_agent.active_strategy,
            active_agents=session.multi_agent.active_agents,
            parent_session_id=session.multi_agent.parent_session_id,
            child_session_ids=session.multi_agent.child_session_ids,
            is_child_session=session.multi_agent.is_child_session,
        )

        # Runtime capabilities
        if session.config.runtime_capabilities:
            from codelab.server.protocol.state import ClientRuntimeCapabilities

            state.runtime_capabilities = ClientRuntimeCapabilities(
                fs_read=session.config.runtime_capabilities.fs_read,
                fs_write=session.config.runtime_capabilities.fs_write,
                terminal=session.config.runtime_capabilities.terminal,
            )

        return state

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
        )

        # Создаем Session
        return Session(
            id=SessionId(state.session_id),
            config=config,
            history=history,
            tool_calls=tool_calls,
            permissions=permissions,
            plan=plan,
            multi_agent=multi_agent,
        )

    @staticmethod
    def _build_history(state: SessionState) -> ConversationHistory:
        """Собирает ConversationHistory из protocol-history (HistoryMessage или dict)."""
        history = ConversationHistory()
        for msg_data in state.history:
            tool_call_id: str | None = None
            if hasattr(msg_data, "role"):
                role_str = msg_data.role
                content_text = msg_data.content if isinstance(msg_data.content, str) else ""
                tool_call_id = getattr(msg_data, "tool_call_id", None)
            elif isinstance(msg_data, dict):
                role_str = msg_data.get("role", "user")
                content_text = msg_data.get("content", "")
                if not isinstance(content_text, str):
                    content_text = ""
                tool_call_id = msg_data.get("tool_call_id")
            else:
                continue

            try:
                role = MessageRole(role_str)
            except ValueError:
                role = MessageRole.USER

            history.add(
                ConversationMessage(
                    role=role,
                    content=MessageContent(text=content_text),
                    tool_call_id=tool_call_id,
                )
            )
        return history

    @staticmethod
    def _build_tool_calls(state: SessionState) -> ToolCallRegistry:
        """Собирает ToolCallRegistry из protocol tool_calls."""
        tool_calls = ToolCallRegistry()
        tool_calls.counter = state.tool_call_counter
        for tc_id, tc_state in state.tool_calls.items():
            try:
                status = ToolCallStatus(tc_state.status)
            except ValueError:
                status = ToolCallStatus.PENDING
            tool_calls.calls[tc_id] = ToolCall(
                id=tc_state.tool_call_id,
                tool_name=tc_state.tool_name or tc_state.title,
                arguments=tc_state.tool_arguments,
                status=status,
            )
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
