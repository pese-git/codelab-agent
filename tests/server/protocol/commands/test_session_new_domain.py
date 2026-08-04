"""`session/new` персистит сессию доменным портом (фаза D ADR-006).

Гейт шага — байт-идентичность: `SessionFactory` остаётся на постоянной
wire-границе, поэтому свежая сессия проходит конверсию `to_domain` → `to_protocol`
при сохранении. Если маппер потеряет поле, новая сессия ляжет на диск иной, чем
раньше, — этот тест фиксирует, что не теряет.
"""

from __future__ import annotations

from typing import Any

import pytest

from codelab.server.mapping.session_mapper import SessionMapper
from codelab.server.messages import ACPMessage
from codelab.server.protocol.commands.session_new import SessionNewCommandHandler
from codelab.server.protocol.session_factory import SessionFactory
from codelab.server.storage import InMemoryStorage, SessionRepository
from codelab.server.storage.document import ClientRuntimeCapabilities


def _config_specs() -> dict[str, dict[str, Any]]:
    return {
        "mode": {
            "name": "Mode",
            "category": "behaviour",
            "default": "standard",
            "options": [{"value": "standard", "name": "Standard"}],
        },
        "model": {
            "name": "Model",
            "category": "llm",
            "default": "openai/gpt",
            "options": [{"value": "openai/gpt", "name": "GPT"}],
        },
    }


@pytest.fixture
def repository() -> SessionRepository:
    return SessionRepository(backend=InMemoryStorage())


class TestSessionNewPersistsViaRepository:
    @pytest.mark.asyncio
    async def test_created_session_is_loadable_as_domain(
        self, repository: SessionRepository
    ) -> None:
        handler = SessionNewCommandHandler(
            repository=repository,
            config_specs=_config_specs(),
            auth_methods=[],
            require_auth=False,
            authenticated=True,
            runtime_capabilities=ClientRuntimeCapabilities(
                fs_read=True, fs_write=True, terminal=True
            ),
        )

        outcome = await handler.handle(
            ACPMessage(
                id="req_1",
                method="session/new",
                params={"cwd": "/tmp/work", "mcpServers": []},
            )
        )

        assert outcome.response is not None
        assert outcome.response.result is not None
        session_id = outcome.response.result["sessionId"]
        stored = await repository.load_session(session_id)
        assert stored is not None
        assert stored.config.cwd == "/tmp/work"
        # Дефолты config-опций доезжают до диска через доменный агрегат
        assert stored.get_config_value("mode") == "standard"
        assert stored.get_config_value("model") == "openai/gpt"
        assert stored.config.runtime_capabilities is not None
        assert stored.config.runtime_capabilities.terminal is True

    def test_fresh_session_survives_domain_roundtrip_byte_identical(self) -> None:
        """Конверсия свежей сессии не меняет ни одного поля wire-формы."""
        state = SessionFactory.create_session(
            cwd="/tmp/x",
            mcp_servers=[{"name": "m", "command": "c", "args": [], "env": []}],
            config_values={"mode": "standard", "model": "openai/gpt"},
            available_commands=[{"name": "cmd", "description": "d"}],
            runtime_capabilities=ClientRuntimeCapabilities(
                fs_read=True, fs_write=False, terminal=True
            ),
            session_id="sess_x",
        )

        restored = SessionMapper.to_protocol(SessionMapper.to_domain(state))

        assert restored.model_dump(mode="json") == state.model_dump(mode="json")
