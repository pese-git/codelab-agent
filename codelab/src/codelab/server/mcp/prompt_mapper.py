"""Маппинг MCP Prompt моделей в ACP AvailableCommand.

Обеспечивает конвертацию MCP prompt моделей в ACP slash command определения
для интеграции MCP prompts с ACP протоколом.

Согласовано с:
- MCP spec: https://modelcontextprotocol.io/specification/ (prompts)
- ACP spec: 14-Slash Commands
"""

from ..models import AvailableCommand, AvailableCommandInput
from .models import MCPPrompt


def mcp_prompt_to_available_command(prompt: MCPPrompt) -> AvailableCommand:
    """Конвертировать MCPPrompt в ACP AvailableCommand.

    Маппинг полей:
    - name → name (имя команды без слеша)
    - title или description → description
    - arguments → input.hint (строка с форматом аргументов)

    Args:
        prompt: MCP prompt для конвертации.

    Returns:
        AvailableCommand для ACP протокола.
    """
    # Описание: предпочитаем title, fallback на description
    description = prompt.title or prompt.description or f"MCP prompt: {prompt.name}"

    # Формируем hint из аргументов
    input_spec = None
    if prompt.arguments:
        arg_parts = []
        for arg in prompt.arguments:
            # Обязательные аргументы в <>, опциональные в []
            if arg.required:
                arg_parts.append(f"<{arg.name}>")
            else:
                arg_parts.append(f"[{arg.name}]")
        hint = " ".join(arg_parts)
        input_spec = AvailableCommandInput(hint=hint)

    return AvailableCommand(
        name=prompt.name,
        description=description,
        input=input_spec,
    )


def mcp_prompts_to_available_commands(
    prompts: list[MCPPrompt],
) -> list[AvailableCommand]:
    """Конвертировать список MCP prompts в список ACP AvailableCommand.

    Args:
        prompts: Список MCP prompts.

    Returns:
        Список AvailableCommand для ACP протокола.
    """
    return [mcp_prompt_to_available_command(p) for p in prompts]
