"""Реестр alias'ов терминалов выдаётся DI в `Scope.APP` (ADR-008, шаг 5.3).

Пока реестр создавался внутри `TerminalToolExecutor`, единственность держалась на
том, что точка создания executor'а одна, — на дисциплине того же рода, что однажды
не сработала у персистируемого `terminal_counter` (P2-58). Гейт проверяет свойство,
а не проводку: alias, выданный зарегистрированным инструментом, разрешается
реестром, который отдаёт контейнер.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.client_rpc.service import ClientRPCService
from codelab.server.config import AppConfig
from codelab.server.di import make_container
from codelab.server.protocol.handlers.prompt_orchestrator import PromptOrchestrator
from codelab.server.storage.memory import InMemoryStorage
from codelab.server.tools.executors.terminal_alias_registry import TerminalAliasRegistry
from tests.server._domain_sessions import make_domain_session


@pytest.fixture
def config() -> AppConfig:
    return AppConfig()


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


class TestTerminalAliasRegistryWiring:
    async def test_container_resolves_registry(
        self, config: AppConfig, storage: InMemoryStorage
    ) -> None:
        container = make_container(config, storage)
        async with container() as request_container:
            registry = await request_container.get(TerminalAliasRegistry)
            assert isinstance(registry, TerminalAliasRegistry)

    async def test_registry_is_single_per_process(
        self, config: AppConfig, storage: InMemoryStorage
    ) -> None:
        """APP-scope: два запроса получают один экземпляр.

        Связка alias → client terminalId не персистится, поэтому второй реестр
        означал бы alias, выданный одним и неразрешимый другим.
        """
        container = make_container(config, storage)
        async with container() as first:
            registry = await first.get(TerminalAliasRegistry)
        async with container() as second:
            assert await second.get(TerminalAliasRegistry) is registry

    async def test_registered_tool_issues_alias_into_container_registry(
        self, config: AppConfig, storage: InMemoryStorage
    ) -> None:
        """Alias, выданный инструментом, разрешается реестром из контейнера.

        Возврат дефекта (executor создаёт собственный реестр) валит именно это:
        alias уходит модели, а разрешить его снаружи executor'а становится нечем.
        """
        container = make_container(config, storage)
        async with container() as request_container:
            registry = await request_container.get(TerminalAliasRegistry)
            orchestrator = await request_container.get(PromptOrchestrator)

        rpc_service = MagicMock(spec=ClientRPCService)
        rpc_service.create_terminal = AsyncMock(return_value="client-terminal-uuid")
        assert orchestrator.client_rpc_service_holder is not None
        orchestrator.client_rpc_service_holder.service = rpc_service
        orchestrator._ensure_tools_registered()

        session = make_domain_session(session_id="sess_aliases", cwd="/tmp", mcp_servers=[])
        handler = orchestrator.tool_registry._handlers["terminal/create"]
        result = await handler(session, command="echo hi")

        alias = result.metadata["terminal_id"]
        assert registry.resolve(session, alias) == "client-terminal-uuid"
