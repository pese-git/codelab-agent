"""Mapper между domain Session и protocol SessionDocument.

Обеспечивает конвертацию между domain моделью Session (aggregate root)
и protocol моделью SessionDocument (Pydantic BaseModel для сериализации).
"""

from dataclasses import asdict
from typing import Any, cast

from codelab.server.agent.config.models import SessionMetrics
from codelab.server.domain.history_projection import project_history
from codelab.server.domain.session import (
    AgentPlan,
    ConversationHistory,
    MultiAgentState,
    PendingExternalRequest,
    PermissionState,
    Session,
    SessionConfig,
    SessionRuntime,
    ToolCallRegistry,
    TurnState,
)
from codelab.server.domain.value_objects import PermissionWait, SessionId, turn_phase_from_wire
from codelab.server.mapping.history_mapper import HistoryMapper
from codelab.server.mapping.journal_mapper import JournalMapper
from codelab.server.mapping.plan_mapper import PlanMapper
from codelab.server.mapping.tool_call_mapper import ToolCallMapper
from codelab.server.models import HistoryMessage, PlanStep
from codelab.server.storage.document import (
    ActiveTurnState,
    ClientRuntimeCapabilities,
    PendingClientRequestState,
    PermissionWaitState,
    SessionDocument,
)
from codelab.shared.capabilities import ClientCapabilities


class SessionMapper:
    """Конвертер между domain Session и protocol SessionDocument."""

    @staticmethod
    def to_protocol(session: Session) -> SessionDocument:
        """Конвертировать domain Session в protocol SessionDocument.

        Args:
            session: Domain Session aggregate

        Returns:
            Protocol SessionDocument для сериализации
        """
        # История на диск не уезжает: она проекция журнала (шаг 4f ADR-008), и
        # хранить её значило бы держать вторую копию тех же данных — ровно тот
        # рассинхрон, ради устранения которого шаг делался.
        #
        # Исключение — легаси-документы, которые уже несут историю: их журнал
        # диалог целиком не описывает, поэтому коллекция остаётся источником и
        # продолжает писаться. Признак несёт сам документ, а не версия схемы.
        history: list[HistoryMessage] = (
            [HistoryMapper.to_protocol(msg) for msg in session.history.get_messages()]
            if session.history_is_source
            else []
        )

        # Конвертируем tool calls (делегируем ToolCallMapper — round-trip без потерь, D4-b/b3)
        tool_calls = {tc.id: ToolCallMapper.to_protocol(tc) for tc in session.tool_calls.get_all()}

        # Конвертируем plan (делегируем PlanMapper — единственный шов Plan↔ACP).
        # `to_acp` всегда отдаёт dict-записи; поле `latest_plan` шире (PlanStep | dict) —
        # сужение через cast, без расширения контракта поля (ср. `updates._apply_plan`).
        latest_plan = cast(
            "list[PlanStep | dict[str, Any]]", PlanMapper.to_acp(session.plan.get_steps())
        )

        # Создаем SessionDocument
        state = SessionDocument(
            session_id=session.id,
            schema_version=session.schema_version,
            revision=session.revision,
            cwd=session.config.cwd,
            mcp_servers=list(session.config.mcp_servers),
            title=session.title,
            config_values=session.config.config_values,
            history=history,
            tool_calls=tool_calls,
            tool_call_counter=session.tool_calls.counter,
            permission_policy=session.permissions.policy,
            cancelled_permission_requests=set(session.permissions.cancelled_requests),
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
            state.runtime_capabilities = ClientRuntimeCapabilities(
                fs_read=session.config.runtime_capabilities.fs_read,
                fs_write=session.config.runtime_capabilities.fs_write,
                terminal=session.config.runtime_capabilities.terminal,
            )

        # Turn-состояние (доменный TurnState VO → wire-DTO ActiveTurnState, ADR-006)
        if session.active_turn is not None:
            state.active_turn = SessionMapper._turn_to_protocol(session.active_turn)

        # Рантайм-состояние (доменный SessionRuntime VO → плоские поля SessionDocument)
        runtime = session.runtime
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
    def _turn_to_protocol(turn: TurnState) -> ActiveTurnState:
        """TurnState VO → wire-DTO ActiveTurnState (round-trip без потерь)."""
        pending = None
        if turn.pending_external_request is not None:
            pending = PendingClientRequestState.model_validate(
                asdict(turn.pending_external_request)
            )
        return ActiveTurnState(
            prompt_request_id=turn.prompt_request_id,
            session_id=turn.session_id,
            cancel_requested=turn.cancel_requested,
            # Фаза несёт свои ожидания (ADR-008, шаги 2 и 5), документ хранит их
            # списком (v12). Пока хранилась пара плоских полей, запись переживало
            # только последнее ожидание, и ответ на любой другой был неприменим.
            permission_waits=[
                PermissionWaitState(
                    request_id=wait.request_id,
                    tool_call_id=wait.tool_call_id,
                    keep_tool_pending=wait.keep_tool_pending,
                )
                for wait in turn.outstanding_permissions
            ],
            phase=turn.phase.wire_name,
            pending_client_request=pending,
            pending_batch=[dict(call) for call in turn.pending_batch],
        )

    @staticmethod
    def to_domain(state: SessionDocument) -> Session:
        """Конвертировать protocol SessionDocument в domain Session.

        Args:
            state: Protocol SessionDocument из хранилища

        Returns:
            Domain Session aggregate
        """
        # Создаем SessionConfig
        runtime_caps = SessionMapper.capabilities_to_domain(state.runtime_capabilities)

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
            # Тип id сохраняется (str|int): коэрция в str ломала round-trip числовых
            # JSON-RPC id и корреляцию tombstone'ов (write-фаза D4-d1, ADR-006).
            cancelled_requests=set(state.cancelled_permission_requests),
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
            revision=state.revision,
            available_commands=SessionMapper.normalize_commands(state.available_commands),
            history_is_source=bool(state.history),
        )

    @staticmethod
    def normalize_commands(commands: list[Any]) -> list[dict[str, Any]]:
        """available_commands → list[dict]: AvailableCommand (pydantic) или dict."""
        result: list[dict[str, Any]] = []
        for cmd in commands:
            if isinstance(cmd, dict):
                result.append(dict(cmd))
            elif hasattr(cmd, "model_dump"):
                result.append(cmd.model_dump())
        return result

    @staticmethod
    def _build_turn(state: SessionDocument) -> TurnState | None:
        """Собирает доменный TurnState VO из wire-DTO ActiveTurnState."""
        at = state.active_turn
        if at is None:
            return None
        pending = (
            PendingExternalRequest(**at.pending_client_request.model_dump())
            if at.pending_client_request is not None
            else None
        )
        return TurnState(
            session_id=at.session_id,
            prompt_request_id=at.prompt_request_id,
            cancel_requested=at.cancel_requested,
            phase=turn_phase_from_wire(
                at.phase,
                waits=[
                    PermissionWait(
                        request_id=wait.request_id,
                        tool_call_id=wait.tool_call_id,
                        keep_tool_pending=wait.keep_tool_pending,
                    )
                    for wait in at.permission_waits
                ],
            ),
            pending_external_request=pending,
            pending_batch=[dict(call) for call in at.pending_batch],
        )

    @staticmethod
    def _build_runtime(state: SessionDocument) -> SessionRuntime:
        """Собирает доменный SessionRuntime VO из плоских runtime-полей SessionDocument."""
        return SessionRuntime(
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
    def capabilities_to_domain(
        wire: ClientRuntimeCapabilities | None,
    ) -> ClientCapabilities | None:
        """Согласованные возможности клиента: wire-DTO → доменный VO.

        Отдельный шов, потому что возможности приходят не только из документа
        сессии: `initialize` согласует их за пределами хранилища, а применяет
        `session/load` (ADR-006, фаза D шаг 5).
        """
        if wire is None:
            return None
        return ClientCapabilities(
            fs_read=wire.fs_read,
            fs_write=wire.fs_write,
            terminal=wire.terminal,
        )

    @staticmethod
    def _build_history(state: SessionDocument) -> ConversationHistory:
        """История сессии: проекция журнала, а для легаси-документов — их коллекция.

        Шаг 4f ADR-008: `history` перестала быть источником и стала видом. Новые
        документы её не несут вовсе, поэтому признак легаси — **само наличие
        коллекции**, а не версия схемы: замер показал документ v14, чей журнал
        дописан кодом до 4e, то есть версия о полноте журнала не говорит.

        Такие документы читаются как раньше и остаются со своей историей до конца:
        события до 4e не несут ни границ сообщения, ни вызовов модели, и проекция
        восстановила бы из них 5 сообщений вместо 14 (замер на `sess_cfa80d9edd84`).

        Проекция сверена с сохранённой историей на сессии, записанной после 4e:
        10 записей против 10, роли, содержимое, вызовы и адресаты ответов совпали;
        разошлись только метки времени — на микросекунды, потому что история
        ставила свою в момент вызова сейма, а журнал — в момент записи события. В
        payload модели метка не попадает (`HistoryBuilder` её не читает).
        """
        if state.history:
            history = ConversationHistory()
            for msg_data in state.history:
                history.add(HistoryMapper.to_domain(msg_data))
            return history

        entries = [
            entry
            for entry in (JournalMapper.from_wire(dict(record)) for record in state.events_history)
            if entry is not None
        ]
        history = ConversationHistory()
        for message in project_history(entries):
            history.add(message)
        return history

    @staticmethod
    def _build_tool_calls(state: SessionDocument) -> ToolCallRegistry:
        """Собирает ToolCallRegistry из protocol tool_calls (делегируя ToolCallMapper)."""
        tool_calls = ToolCallRegistry()
        tool_calls.counter = state.tool_call_counter
        for tc_id, tc_state in state.tool_calls.items():
            tool_calls.calls[tc_id] = ToolCallMapper.to_domain(tc_state)
        return tool_calls

    @staticmethod
    def _build_plan(state: SessionDocument) -> AgentPlan:
        """Собирает AgentPlan из protocol latest_plan (делегируя PlanMapper).

        `entries_to_acp` покрывает и pre-P2-26 записи (`PlanStep`), которые
        прежний inline-разбор молча отбрасывал как не-dict.
        """
        return AgentPlan(steps=PlanMapper.from_acp(PlanMapper.entries_to_acp(state.latest_plan)))
