"""Integration-тесты mode × strategy matrix.

Покрывает:
- Взаимодействие mode (plan/standard/bypass) с execution strategies
- Как mode влияет на tool execution внутри стратегий
- Mode inheritance при strategy switching
- Strategy dispatcher + mode integration
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from codelab.server.agent.event_bus.bus import AgentEventBus
from codelab.server.agent.strategies.dispatcher import StrategyDispatcher
from codelab.server.agent.strategies.registry import StrategyRegistry
from codelab.server.protocol.handlers.tool_policy import decide_tool_policy
from codelab.server.protocol.mode import MODE_BYPASS, MODE_PLAN, MODE_STANDARD
from codelab.server.protocol.state import SessionState


def _make_session(mode: str = MODE_STANDARD) -> SessionState:
    """Создать сессию с указанным mode."""
    return SessionState(
        session_id="sess_1",
        cwd="/tmp",
        mcp_servers=[],
        config_values={"mode": mode},
    )


class TestModeStrategyMatrix:
    """Тесты матрицы mode × strategy.

    Матрица поведения:
    | Mode    | Strategy | Tool Execution        |
    |---------|----------|-----------------------|
    | plan    | single   | read only             |
    | plan    | orch     | read only (coordinator)|
    | plan    | hier     | read only (primary)   |
    | standard| single   | permission request    |
    | standard| orch     | permission request    |
    | standard| hier     | permission request    |
    | bypass  | single   | auto-execute          |
    | bypass  | orch     | auto-execute          |
    | bypass  | hier     | auto-execute          |
    """

    def test_plan_mode_tool_policy_independent_of_strategy(self) -> None:
        """В plan mode tool policy всегда reject для write, независимо от strategy."""
        session = _make_session(mode=MODE_PLAN)

        # Plan mode блокирует write инструменты
        assert decide_tool_policy(session, "execute") == "reject"
        assert decide_tool_policy(session, "edit") == "reject"
        assert decide_tool_policy(session, "delete") == "reject"

        # Plan mode разрешает read инструменты
        assert decide_tool_policy(session, "read") == "allow"
        assert decide_tool_policy(session, "search") == "allow"

    def test_standard_mode_tool_policy_independent_of_strategy(self) -> None:
        """В standard mode tool policy всегда ask, независимо от strategy."""
        session = _make_session(mode=MODE_STANDARD)

        # Standard mode требует permission для всех инструментов
        assert decide_tool_policy(session, "execute") == "ask"
        assert decide_tool_policy(session, "edit") == "ask"
        assert decide_tool_policy(session, "read") == "ask"

    def test_bypass_mode_tool_policy_independent_of_strategy(self) -> None:
        """В bypass mode tool policy всегда allow, независимо от strategy."""
        session = _make_session(mode=MODE_BYPASS)

        # Bypass mode разрешает всё
        assert decide_tool_policy(session, "execute") == "allow"
        assert decide_tool_policy(session, "edit") == "allow"
        assert decide_tool_policy(session, "read") == "allow"

    def test_mode_with_allow_always_in_standard_mode(self) -> None:
        """В standard mode allow_always policy должен auto-execute."""
        session = _make_session(mode=MODE_STANDARD)
        session.permission_policy["execute"] = "allow_always"

        # С allow_always policy — auto-execute
        assert decide_tool_policy(session, "execute") == "allow"

    def test_mode_with_reject_always_in_standard_mode(self) -> None:
        """В standard mode reject_always policy должен auto-reject."""
        session = _make_session(mode=MODE_STANDARD)
        session.permission_policy["execute"] = "reject_always"

        # С reject_always policy — auto-reject
        assert decide_tool_policy(session, "execute") == "reject"

    def test_plan_mode_overrides_allow_always_policy(self) -> None:
        """В plan mode plan блокировка override allow_always policy."""
        session = _make_session(mode=MODE_PLAN)
        session.permission_policy["execute"] = "allow_always"

        # Plan mode блокирует несмотря на allow_always
        assert decide_tool_policy(session, "execute") == "reject"

    def test_bypass_mode_overrides_reject_always_policy(self) -> None:
        """В bypass mode bypass разрешает несмотря на reject_always policy."""
        session = _make_session(mode=MODE_BYPASS)
        session.permission_policy["execute"] = "reject_always"

        # Bypass mode разрешает несмотря на reject_always
        assert decide_tool_policy(session, "execute") == "allow"


class TestStrategyDispatcherModeIntegration:
    """Integration тесты StrategyDispatcher + mode."""

    @pytest.fixture
    def strategy_registry(self) -> StrategyRegistry:
        """Создать StrategyRegistry с single стратегией."""
        from codelab.server.protocol.handlers.strategies.single_strategy import (
            SINGLE_STRATEGY_DESCRIPTOR,
        )

        registry = StrategyRegistry()
        registry.register(SINGLE_STRATEGY_DESCRIPTOR)
        return registry

    @pytest.fixture
    def agent_registry(self):
        """Создать mock AgentRegistry."""
        mock = MagicMock()
        mock.get_primary_agents.return_value = {}
        mock.get_all.return_value = {}
        return mock

    @pytest.fixture
    def strategy_deps(self):
        """Создать mock StrategyDependencies."""
        from codelab.server.agent.strategies.descriptor import StrategyDependencies

        mock_event_bus = MagicMock(spec=AgentEventBus)
        mock_execution_engine = MagicMock()
        return StrategyDependencies(
            event_bus=mock_event_bus,
            execution_engine=mock_execution_engine,
            tracer=None,
            agent_name="primary",
        )

    def test_dispatcher_selects_strategy_with_plan_mode(
        self,
        strategy_registry: StrategyRegistry,
        agent_registry,
        strategy_deps,
    ) -> None:
        """StrategyDispatcher должен работать с plan mode."""
        dispatcher = StrategyDispatcher(
            strategy_registry=strategy_registry,
            agent_registry=agent_registry,
            strategy_dependencies=strategy_deps,
            default_strategy="single",
            fallback_strategy="single",
        )

        session = _make_session(mode=MODE_PLAN)
        strategy_name, fallback = dispatcher.select_strategy(session)

        assert strategy_name == "single"
        assert fallback is None
        # Mode не влияет на выбор стратегии
        assert session.config_values["mode"] == MODE_PLAN

    def test_dispatcher_selects_strategy_with_bypass_mode(
        self,
        strategy_registry: StrategyRegistry,
        agent_registry,
        strategy_deps,
    ) -> None:
        """StrategyDispatcher должен работать с bypass mode."""
        dispatcher = StrategyDispatcher(
            strategy_registry=strategy_registry,
            agent_registry=agent_registry,
            strategy_dependencies=strategy_deps,
            default_strategy="single",
            fallback_strategy="single",
        )

        session = _make_session(mode=MODE_BYPASS)
        strategy_name, fallback = dispatcher.select_strategy(session)

        assert strategy_name == "single"
        assert fallback is None
        assert session.config_values["mode"] == MODE_BYPASS

    def test_mode_change_does_not_affect_strategy_selection(
        self,
        strategy_registry: StrategyRegistry,
        agent_registry,
        strategy_deps,
    ) -> None:
        """Смена mode не должна влиять на выбор стратегии."""
        dispatcher = StrategyDispatcher(
            strategy_registry=strategy_registry,
            agent_registry=agent_registry,
            strategy_dependencies=strategy_deps,
            default_strategy="single",
            fallback_strategy="single",
        )

        session = _make_session(mode=MODE_STANDARD)
        strategy_name_1, _ = dispatcher.select_strategy(session)

        # Меняем mode
        session.config_values["mode"] = MODE_PLAN
        strategy_name_2, _ = dispatcher.select_strategy(session)

        # Стратегия должна остаться той же
        assert strategy_name_1 == strategy_name_2 == "single"

    def test_strategy_change_does_not_affect_mode(
        self,
        strategy_registry: StrategyRegistry,
        agent_registry,
        strategy_deps,
    ) -> None:
        """Смена стратегии не должна влиять на mode."""
        dispatcher = StrategyDispatcher(
            strategy_registry=strategy_registry,
            agent_registry=agent_registry,
            strategy_dependencies=strategy_deps,
            default_strategy="single",
            fallback_strategy="single",
        )

        session = _make_session(mode=MODE_BYPASS)
        dispatcher.select_strategy(session)

        # Mode должен остаться тем же
        assert session.config_values["mode"] == MODE_BYPASS


class TestModeTransitionWithStrategy:
    """Тесты перехода mode при активной стратегии."""

    def test_plan_to_bypass_transition_tool_policy(self) -> None:
        """Переход plan → bypass должен изменить tool policy."""
        session = _make_session(mode=MODE_PLAN)

        # Plan mode
        assert decide_tool_policy(session, "execute") == "reject"
        assert decide_tool_policy(session, "edit") == "reject"

        # Переход в bypass
        session.config_values["mode"] = MODE_BYPASS

        # Bypass mode
        assert decide_tool_policy(session, "execute") == "allow"
        assert decide_tool_policy(session, "edit") == "allow"

    def test_bypass_to_standard_transition_tool_policy(self) -> None:
        """Переход bypass → standard должен включить permission requests."""
        session = _make_session(mode=MODE_BYPASS)

        # Bypass mode
        assert decide_tool_policy(session, "execute") == "allow"

        # Переход в standard
        session.config_values["mode"] = MODE_STANDARD

        # Standard mode
        assert decide_tool_policy(session, "execute") == "ask"

    def test_standard_to_plan_transition_tool_policy(self) -> None:
        """Переход standard → plan должен заблокировать write."""
        session = _make_session(mode=MODE_STANDARD)

        # Standard mode
        assert decide_tool_policy(session, "execute") == "ask"

        # Переход в plan
        session.config_values["mode"] = MODE_PLAN

        # Plan mode
        assert decide_tool_policy(session, "execute") == "reject"
        assert decide_tool_policy(session, "read") == "allow"

    def test_mode_transition_preserves_permission_policy(self) -> None:
        """При переходе mode permission policy должна сохраняться."""
        session = _make_session(mode=MODE_STANDARD)
        session.permission_policy["execute"] = "allow_always"

        # Переход в plan
        session.config_values["mode"] = MODE_PLAN

        # Plan mode блокирует несмотря на allow_always
        assert decide_tool_policy(session, "execute") == "reject"

        # Возврат в standard — policy должна сохраниться
        session.config_values["mode"] = MODE_STANDARD
        assert decide_tool_policy(session, "execute") == "allow"
        assert session.permission_policy["execute"] == "allow_always"


class TestModeInheritancePreparation:
    """Тесты подготовки к mode inheritance для child sessions.

    Child sessions создаются в OrchestratedStrategy, HierarchicalStrategy,
    ChoreographyStrategy. Mode inheritance будет реализована вместе со
    стратегиями.
    """

    def test_parent_mode_can_be_copied_to_child(self) -> None:
        """Mode parent сессии может быть скопирован в child."""
        parent = _make_session(mode=MODE_PLAN)

        # Создаём child session с наследованным mode
        child = SessionState(
            session_id="child_1",
            cwd="/tmp",
            mcp_servers=[],
            config_values={"mode": parent.config_values.get("mode", MODE_STANDARD)},
        )

        assert child.config_values["mode"] == MODE_PLAN

    def test_child_mode_independent_from_parent(self) -> None:
        """Изменение mode child не должно влиять на parent."""
        parent = _make_session(mode=MODE_STANDARD)
        child = _make_session(mode=MODE_STANDARD)

        # Меняем mode child
        child.config_values["mode"] = MODE_BYPASS

        # Parent mode должен остаться тем же
        assert parent.config_values["mode"] == MODE_STANDARD
        assert child.config_values["mode"] == MODE_BYPASS

    def test_child_tool_policy_independent_from_parent(self) -> None:
        """Tool policy child должна быть независимой от parent."""
        parent = _make_session(mode=MODE_PLAN)
        child = _make_session(mode=MODE_BYPASS)

        # Parent plan mode блокирует
        assert decide_tool_policy(parent, "execute") == "reject"

        # Child bypass mode разрешает
        assert decide_tool_policy(child, "execute") == "allow"
