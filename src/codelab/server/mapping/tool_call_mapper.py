"""Mapper между domain ToolCall и ACP Protocol ToolCallState."""

from __future__ import annotations

from codelab.server.domain.tool_call import ToolCall, ToolResult
from codelab.server.domain.value_objects import FileLocation, ToolCallStatus
from codelab.server.protocol.state import ToolCallState


class ToolCallMapper:
    """Конвертер между domain ToolCall и protocol ToolCallState."""

    @staticmethod
    def to_protocol(domain: ToolCall) -> ToolCallState:
        """Конвертировать domain ToolCall в protocol ToolCallState (round-trip без потерь)."""
        result = domain.result
        locations_src = result.locations if result else domain.locations
        locations = [{"path": loc.path, "line": loc.line} for loc in locations_src]
        return ToolCallState(
            tool_call_id=domain.id,
            # title — доменный display; для domain-origin объектов без title fallback на tool_name.
            title=domain.title if domain.title is not None else domain.tool_name,
            kind=domain.kind,
            status=domain.status.value,
            raw_input=domain.arguments,
            raw_output=result.raw_output if result else domain.raw_output,
            locations=locations,
            tool_name=domain.tool_name,
            tool_arguments=domain.arguments,
            tool_call_id_from_llm=domain.tool_call_id_from_llm,
            content=result.content if result else [],
            result_content=result.result_content if result else [],
        )

    @staticmethod
    def to_domain(protocol: ToolCallState) -> ToolCall:
        """Конвертировать protocol ToolCallState в domain ToolCall (round-trip без потерь)."""
        locations = [
            FileLocation(path=loc["path"], line=loc.get("line"))
            for loc in protocol.locations
            if isinstance(loc, dict) and "path" in loc
        ]
        status = _parse_status(protocol.status)
        result = None
        if protocol.raw_output or locations or protocol.content or protocol.result_content:
            result = ToolResult(
                locations=locations,
                raw_output=dict(protocol.raw_output),
                content=[dict(c) for c in protocol.content],
                result_content=[dict(c) for c in protocol.result_content],
            )
        return ToolCall(
            id=protocol.tool_call_id,
            tool_name=protocol.tool_name or protocol.title,
            arguments=(
                dict(protocol.raw_input) if protocol.raw_input else dict(protocol.tool_arguments)
            ),
            status=status,
            result=result,
            locations=locations,
            raw_output=dict(protocol.raw_output),
            kind=protocol.kind,
            title=protocol.title,
            tool_call_id_from_llm=protocol.tool_call_id_from_llm,
        )


def _parse_status(value: str) -> ToolCallStatus:
    try:
        return ToolCallStatus(value)
    except ValueError:
        return ToolCallStatus.PENDING
