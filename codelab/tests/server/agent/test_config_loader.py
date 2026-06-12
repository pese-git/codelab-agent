"""Тесты для AgentConfigLoader."""

import tempfile
from pathlib import Path

import pytest

from codelab.server.agent.config.loader import AgentConfigLoader
from codelab.server.agent.config.models import AgentRole


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


class TestParseMarkdown:
    """2.6 — парсинг Markdown с frontmatter."""

    def test_with_frontmatter(self, temp_dir):
        md_file = temp_dir / "coder.md"
        md_file.write_text(
            "---\nname: coder\nrole: primary\nmodel: openai/gpt-4o\n---\nYou are a coder."
        )

        loader = AgentConfigLoader(project_config_dir=temp_dir)
        cfg = loader._parse_markdown(md_file)

        assert cfg.name == "coder"
        assert cfg.role == AgentRole.PRIMARY
        assert cfg.model == "openai/gpt-4o"
        assert cfg.prompt == "You are a coder."

    def test_without_frontmatter(self, temp_dir):
        md_file = temp_dir / "coder.md"
        md_file.write_text("Just a prompt without frontmatter.")

        loader = AgentConfigLoader()
        cfg = loader._parse_markdown(md_file)

        assert cfg.name == "coder"
        assert cfg.prompt == "Just a prompt without frontmatter."

    def test_frontmatter_with_permissions(self, temp_dir):
        md_file = temp_dir / "coder.md"
        md_file.write_text(
            "---\nname: coder\npermissions:\n  edit: true\n  bash: false\n---\nPrompt."
        )

        loader = AgentConfigLoader()
        cfg = loader._parse_markdown(md_file)

        assert cfg.permissions == {"edit": True, "bash": False}


class TestTomlToMarkdown:
    """2.7 — конвертация TOML в Markdown."""

    def test_basic_conversion(self):
        from codelab.server.agent.config.models import AgentTOMLConfig

        loader = AgentConfigLoader()
        toml_cfg = AgentTOMLConfig(
            enabled=True,
            role=AgentRole.SUBAGENT,
            model="openai/gpt-4o-mini",
            temperature=0.5,
            tools=["read_file"],
        )

        md_cfg = loader._toml_to_markdown("reviewer", toml_cfg)

        assert md_cfg.name == "reviewer"
        assert md_cfg.role == AgentRole.SUBAGENT
        assert md_cfg.model == "openai/gpt-4o-mini"
        assert md_cfg.temperature == 0.5
        assert md_cfg.tools == ["read_file"]

    def test_extra_fields_preserved(self):
        from codelab.server.agent.config.models import AgentTOMLConfig

        loader = AgentConfigLoader()
        toml_cfg = AgentTOMLConfig(custom="value")
        md_cfg = loader._toml_to_markdown("test", toml_cfg)

        assert md_cfg.model_extra.get("custom") == "value"


class TestLoadAll:
    """2.8 — логика override."""

    def test_empty_load(self, temp_dir):
        loader = AgentConfigLoader(
            global_config_dir=temp_dir,
            project_config_dir=temp_dir,
        )
        result = loader.load_all()
        assert result == {}

    def test_project_toml_definitions(self, temp_dir):
        loader = AgentConfigLoader(
            project_config_dir=temp_dir,
        )
        project_toml = {
            "agents": {
                "definitions": {
                    "coder": {
                        "role": "primary",
                        "model": "openai/gpt-4o",
                    }
                }
            }
        }

        result = loader.load_all(project_toml=project_toml)
        assert "coder" in result
        assert result["coder"].model == "openai/gpt-4o"

    def test_override_project_md_over_project_toml(self, temp_dir):
        loader = AgentConfigLoader(
            project_config_dir=temp_dir,
        )

        # Project TOML
        project_toml = {
            "agents": {
                "definitions": {
                    "coder": {
                        "role": "primary",
                        "model": "openai/gpt-3.5",
                    }
                }
            }
        }

        # Project MD (высший приоритет)
        agents_dir = temp_dir / "agents"
        agents_dir.mkdir()
        (agents_dir / "coder.md").write_text(
            "---\nname: coder\nrole: subagent\n---\nCoder prompt."
        )

        result = loader.load_all(project_toml=project_toml)
        assert result["coder"].role == AgentRole.SUBAGENT  # Из MD, не TOML

    def test_override_chain(self, temp_dir):
        """global TOML < global MD < project TOML < project MD."""
        global_dir = temp_dir / "global"
        global_dir.mkdir()
        project_dir = temp_dir / "project"
        project_dir.mkdir()

        # Global TOML
        global_toml = {
            "agents": {
                "definitions": {
                    "coder": {"role": "primary", "model": "global-toml-model"},
                }
            }
        }

        # Global MD
        global_agents = global_dir / "agents"
        global_agents.mkdir()
        (global_agents / "coder.md").write_text(
            "---\nname: coder\nmodel: global-md-model\n---\nPrompt."
        )

        # Project TOML
        project_toml = {
            "agents": {
                "definitions": {
                    "coder": {"role": "primary", "model": "project-toml-model"},
                }
            }
        }

        # Project MD
        project_agents = project_dir / "agents"
        project_agents.mkdir()
        (project_agents / "coder.md").write_text(
            "---\nname: coder\nmodel: project-md-model\n---\nPrompt."
        )

        loader = AgentConfigLoader(
            global_config_dir=global_dir,
            project_config_dir=project_dir,
        )
        result = loader.load_all(
            global_toml=global_toml,
            project_toml=project_toml,
        )

        # Project MD — высший приоритет
        assert result["coder"].model == "project-md-model"
