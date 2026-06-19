"""Mapper между domain Session и protocol SessionState.

Обеспечивает конвертацию между domain моделью Session (aggregate root)
и protocol моделью SessionState (Pydantic BaseModel для сериализации).
"""

from codelab.client.domain.entities import ClientCapabilities
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

        # Конвертируем историю сообщений
        history = []
        for msg in session.history.get_messages():
            # MessageRole.TOOL не поддерживается в HistoryMessage, используем assistant
            role_value = msg.role.value
            if role_value == "tool":
                role_value = "assistant"
            history.append(HistoryMessage(
                role=role_value,  # type: ignore[arg-type]
                content=msg.content.text,
                timestamp=msg.timestamp.isoformat() if msg.timestamp else None,
            ))

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
            latest_plan.append({
                "content": step.content,
                "priority": step.priority.value,
                "status": step.status.value,
            })

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

        # Создаем ConversationHistory
        history = ConversationHistory()
        for msg_data in state.history:
            # msg_data может быть HistoryMessage или dict
            if hasattr(msg_data, "role"):
                # Это HistoryMessage объект
                role_str = msg_data.role
                content_text = msg_data.content if isinstance(msg_data.content, str) else ""
            elif isinstance(msg_data, dict):
                # Это dict
                role_str = msg_data.get("role", "user")
                content_text = msg_data.get("content", "")
                if not isinstance(content_text, str):
                    content_text = ""
            else:
                continue

            try:
                role = MessageRole(role_str)
            except ValueError:
                role = MessageRole.USER

            content = MessageContent(text=content_text)
            msg = ConversationMessage(role=role, content=content)
            history.add(msg)

        # Создаем ToolCallRegistry
        tool_calls = ToolCallRegistry()
        tool_calls.counter = state.tool_call_counter
        for tc_id, tc_state in state.tool_calls.items():
            try:
                status = ToolCallStatus(tc_state.status)
            except ValueError:
                status = ToolCallStatus.PENDING
            tc = ToolCall(
                id=tc_state.tool_call_id,
                tool_name=tc_state.tool_name or tc_state.title,
                arguments=tc_state.tool_arguments,
                status=status,
            )
            tool_calls.calls[tc_id] = tc

        # Создаем PermissionState
        permissions = PermissionState(
            policy=state.permission_policy,
            cancelled_requests={str(r) for r in state.cancelled_permission_requests},
        )

        # Создаем AgentPlan
        plan = AgentPlan()
        for step_data in state.latest_plan:
            if isinstance(step_data, dict):
                content = step_data.get("content", "")
                priority_str = step_data.get("priority", "medium")
                status_str = step_data.get("status", "pending")
                try:
                    priority = PlanPriority(priority_str)
                except ValueError:
                    priority = PlanPriority.MEDIUM
                try:
                    status = PlanStatus(status_str)
                except ValueError:
                    status = PlanStatus.PENDING
                step = PlanEntry(content=content, priority=priority, status=status)
                plan.add_step(step)

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
