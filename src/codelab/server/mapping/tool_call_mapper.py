"""Mapper между domain ToolCall и ACP Protocol ToolCallState."""

from __future__ import annotations

from codelab.server.domain.tool_call import ToolCall, ToolResult
from codelab.server.domain.value_objects import FileLocation, ToolCallStatus
from codelab.server.protocol.state import ToolCallState


class ToolCallMapper:
    """Конвертер между domain ToolCall и protocol ToolCallState."""

    @staticmethod
    def to_protocol(domain: ToolCall) -> ToolCallState:
        """Конвертировать domain ToolCall в protocol ToolCallState."""
        locations = [
            {"path": loc.path, "line": loc.line} for loc in domain.locations
        ]
        return ToolCallState(
            tool_call_id=domain.id,
            title=domain.tool_name,
            kind="other",
            status=domain.status.value,
            raw_input=domain.arguments,
            raw_output=domain.result.raw_output if domain.result else domain.raw_output,
            locations=locations,
            tool_name=domain.tool_name,
            tool_arguments=domain.arguments,
        )

    @staticmethod
    def to_domain(protocol: ToolCallState) -> ToolCall:
        """Конвертировать protocol ToolCallState в domain ToolCall."""
        locations = [
            FileLocation(path=loc["path"], line=loc.get("line"))
            for loc in protocol.locations
            if isinstance(loc, dict) and "path" in loc
        ]
        status = _parse_status(protocol.status)
        result = None
        if protocol.raw_output or locations:
            result = ToolResult(
                locations=locations,
                raw_output=dict(protocol.raw_output),
            )
        return ToolCall(
            id=protocol.tool_call_id,
            tool_name=protocol.title,
            arguments=(
                dict(protocol.raw_input)
                if protocol.raw_input
                else dict(protocol.tool_arguments)
            ),
            status=status,
            result=result,
            locations=locations,
            raw_output=dict(protocol.raw_output),
        )


def _parse_status(value: str) -> ToolCallStatus:
    try:
        return ToolCallStatus(value)
    except ValueError:
        return ToolCallStatus.PENDING
