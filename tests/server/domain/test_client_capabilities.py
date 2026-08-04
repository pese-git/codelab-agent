"""Unit тесты для ClientCapabilities."""

import pytest

from codelab.client.domain.entities import ClientCapabilities, Session


class TestClientCapabilities:
    def test_defaults(self) -> None:
        caps = ClientCapabilities()
        assert caps.fs_read is False
        assert caps.fs_write is False
        assert caps.terminal is False

    def test_supports_fs_false(self) -> None:
        caps = ClientCapabilities()
        assert caps.supports_fs is False

    def test_supports_fs_read(self) -> None:
        caps = ClientCapabilities(fs_read=True)
        assert caps.supports_fs is True

    def test_supports_fs_write(self) -> None:
        caps = ClientCapabilities(fs_write=True)
        assert caps.supports_fs is True

    def test_multimodal_not_a_client_capability(self) -> None:
        """Мультимодальность здесь отсутствует намеренно.

        По ACP `image`/`audio`/`embeddedContext` входят в
        `agentCapabilities.promptCapabilities` — их носитель `PromptCapabilities`
        (tech-debt P2-32: здесь они лежали дублем без потребителей).
        """
        caps = ClientCapabilities()
        assert not hasattr(caps, "image_prompts")
        assert not hasattr(caps, "embedded_context")
        assert not hasattr(caps, "supports_multimodal")

    def test_can_read_files(self) -> None:
        caps = ClientCapabilities(fs_read=True)
        assert caps.can_read_files() is True

    def test_can_read_files_false(self) -> None:
        caps = ClientCapabilities()
        assert caps.can_read_files() is False

    def test_can_write_files(self) -> None:
        caps = ClientCapabilities(fs_write=True)
        assert caps.can_write_files() is True

    def test_can_write_files_false(self) -> None:
        caps = ClientCapabilities()
        assert caps.can_write_files() is False

    def test_frozen(self) -> None:
        caps = ClientCapabilities(fs_read=True)
        with pytest.raises(AttributeError):
            caps.fs_read = False  # type: ignore[misc]

    def test_from_dict_empty(self) -> None:
        caps = ClientCapabilities.from_dict({})
        assert caps.fs_read is False
        assert caps.fs_write is False
        assert caps.terminal is False

    def test_from_dict_full(self) -> None:
        caps = ClientCapabilities.from_dict(
            {
                "fs_read": True,
                "fs_write": True,
                "terminal": True,
            }
        )
        assert caps.fs_read is True
        assert caps.fs_write is True
        assert caps.terminal is True

    def test_from_dict_ignores_unknown_keys(self) -> None:
        """Незнакомые ключи не роняют разбор: словари приходят из внешнего обмена."""
        caps = ClientCapabilities.from_dict(
            {"fs_read": True, "image_prompts": True, "whatever": 1}
        )
        assert caps.fs_read is True
        assert caps == ClientCapabilities(fs_read=True)

    def test_from_dict_partial(self) -> None:
        caps = ClientCapabilities.from_dict({"fs_read": True})
        assert caps.fs_read is True
        assert caps.fs_write is False

    def test_equality(self) -> None:
        a = ClientCapabilities(fs_read=True)
        b = ClientCapabilities(fs_read=True)
        assert a == b


class TestSessionWithCapabilities:
    def test_create_with_dict(self) -> None:
        session = Session.create(
            server_host="localhost",
            server_port=8080,
            client_capabilities={"fs_read": True},
            server_capabilities={},
        )
        assert isinstance(session.client_capabilities, ClientCapabilities)
        assert session.client_capabilities.fs_read is True

    def test_create_with_capabilities(self) -> None:
        caps = ClientCapabilities(fs_read=True, terminal=True)
        session = Session.create(
            server_host="localhost",
            server_port=8080,
            client_capabilities=caps,
            server_capabilities={},
        )
        assert session.client_capabilities is caps
        assert session.client_capabilities.fs_read is True
        assert session.client_capabilities.terminal is True

    def test_create_with_empty_dict(self) -> None:
        session = Session.create(
            server_host="localhost",
            server_port=8080,
            client_capabilities={},
            server_capabilities={},
        )
        assert isinstance(session.client_capabilities, ClientCapabilities)
        assert session.client_capabilities.supports_fs is False
