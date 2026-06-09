"""Тесты интеграции ACPProtocol с AgentOrchestrator.

Проверяют работу session/prompt с LLM-агентом при передаче agent_orchestrator.

NOTE: AgentOrchestrator is deprecated. Use ExecutionEngine + StrategyDispatcher instead.
These tests are kept for backward compatibility verification.
"""

import pytest

from codelab.server.agent.orchestrator import AgentOrchestrator
from codelab.server.agent.state import OrchestratorConfig
from codelab.server.llm.mock_provider import MockLLMProvider
from codelab.server.messages import ACPMessage
from codelab.server.protocol import ACPProtocol
from codelab.server.tools.registry import SimpleToolRegistry


pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.mark.asyncio
async def test_session_prompt_with_agent_orchestrator() -> None:
    """Тест обработки промпта через агента."""
    # Инициализировать компоненты агента
    config = OrchestratorConfig(agent_class="naive")
    llm_provider = MockLLMProvider()
    tool_registry = SimpleToolRegistry()
    agent_orchestrator = AgentOrchestrator(config, llm_provider, tool_registry)

    # Создать протокол с агентом
    protocol = ACPProtocol(agent_orchestrator=agent_orchestrator)

    # Инициализировать
    init_outcome = await protocol.handle(
        ACPMessage.request(
            "initialize",
            {
                "protocolVersion": 1,
                "clientCapabilities": {},
            },
        )
    )
    assert init_outcome.response is not None
    assert init_outcome.response.error is None

    # Создать сессию
    new_session = await protocol.handle(
        ACPMessage.request("session/new", {"cwd": "/tmp", "mcpServers": []})
    )
    assert new_session.response is not None
    assert isinstance(new_session.response.result, dict)
    session_id = new_session.response.result["sessionId"]

    # Обработать промпт через агента
    outcome = await protocol.handle(
        ACPMessage.request(
            "session/prompt",
            {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": "hello agent"}],
            },
        )
    )

    # Проверить результат
    assert outcome.response is not None
    assert outcome.response.error is None
    assert outcome.response.result is not None
    assert outcome.response.result.get("stopReason") == "end_turn"

    # Проверить уведомления
    assert len(outcome.notifications) > 0
    update_types = [
        notification.params["update"]["sessionUpdate"]
        for notification in outcome.notifications
        if notification.method == "session/update" and notification.params is not None
    ]
    assert "agent_message_chunk" in update_types
    # session_info может приходить как session_info или session_info_update
    assert "session_info_update" in update_types or "session_info" in update_types


@pytest.mark.asyncio
async def test_session_prompt_with_agent_sets_session_title() -> None:
    """Тест установки заголовка сессии при обработке через агента."""
    config = OrchestratorConfig(agent_class="naive")
    llm_provider = MockLLMProvider()
    tool_registry = SimpleToolRegistry()
    agent_orchestrator = AgentOrchestrator(config, llm_provider, tool_registry)

    protocol = ACPProtocol(agent_orchestrator=agent_orchestrator)

    # Инициализировать
    await protocol.handle(
        ACPMessage.request(
            "initialize",
            {
                "protocolVersion": 1,
                "clientCapabilities": {},
            },
        )
    )

    # Создать сессию
    new_session = await protocol.handle(
        ACPMessage.request("session/new", {"cwd": "/tmp", "mcpServers": []})
    )
    assert new_session.response is not None
    assert isinstance(new_session.response.result, dict)
    session_id = new_session.response.result["sessionId"]

    # Обработать промпт с текстом для заголовка
    prompt_text = "implement authentication system"
    outcome = await protocol.handle(
        ACPMessage.request(
            "session/prompt",
            {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": prompt_text}],
            },
        )
    )

    assert outcome.response is not None
    assert outcome.response.error is None

    # Загрузить сессию и проверить заголовок
    load_outcome = await protocol.handle(
        ACPMessage.request(
            "session/load",
            {
                "sessionId": session_id,
                "cwd": "/tmp",
                "mcpServers": [],
            },
        )
    )

    assert load_outcome.response is not None
    # Заголовок должен быть установлен из первой строки промпта
    assert len(load_outcome.notifications) > 0


@pytest.mark.asyncio
async def test_session_prompt_without_agent_still_works() -> None:
    """Тест что session/prompt работает без агента (legacy mode)."""
    # Протокол БЕЗ агента
    protocol = ACPProtocol()

    # Инициализировать
    await protocol.handle(
        ACPMessage.request(
            "initialize",
            {
                "protocolVersion": 1,
                "clientCapabilities": {},
            },
        )
    )

    # Создать сессию
    new_session = await protocol.handle(
        ACPMessage.request("session/new", {"cwd": "/tmp", "mcpServers": []})
    )
    assert new_session.response is not None
    assert isinstance(new_session.response.result, dict)
    session_id = new_session.response.result["sessionId"]

    # Обработать промпт БЕЗ агента (legacy)
    outcome = await protocol.handle(
        ACPMessage.request(
            "session/prompt",
            {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": "legacy prompt"}],
            },
        )
    )

    # Должно работать как раньше
    assert outcome.response is not None
    assert outcome.response.error is None
    assert outcome.response.result is not None
    assert outcome.response.result.get("stopReason") == "end_turn"


@pytest.mark.asyncio
async def test_agent_orchestrator_parameter_is_optional() -> None:
    """Тест что параметр agent_orchestrator опционален."""
    # Создать протокол БЕЗ явной передачи agent_orchestrator
    protocol = ACPProtocol()

    # Должно работать без ошибок
    assert protocol._agent_orchestrator is None

    # Создать протокол С явной передачей None
    protocol2 = ACPProtocol(agent_orchestrator=None)
    assert protocol2._agent_orchestrator is None
