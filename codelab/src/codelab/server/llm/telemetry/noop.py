"""NoOp telemetry sink.

Заглушка для MVP — все методы проходят silently.
"""

from __future__ import annotations

from codelab.server.llm.telemetry.base import TelemetrySink


class NoOpTelemetry(TelemetrySink):
    """Заглушка telemetry sink.

    Все методы проходят без действий.
    Используется по умолчанию в MVP.
    """

    async def record_request(
        self,
        provider_id: str,  # noqa: ARG002
        model_id: str,  # noqa: ARG002
        latency_ms: float,  # noqa: ARG002
        success: bool,  # noqa: ARG002
    ) -> None:
        """No-op."""
        pass

    async def record_cost(
        self,
        provider_id: str,  # noqa: ARG002
        model_id: str,  # noqa: ARG002
        cost_usd: float,  # noqa: ARG002
    ) -> None:
        """No-op."""
        pass
