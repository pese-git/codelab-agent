"""Фейки для тестов ядра агента (без Pydantic, без SessionState).

ADR-005: ядро ``core/`` принимает ``SessionView``/``ContentCodec``/
``UpdateSink`` Protocols. Тесты должны иметь возможность конструировать
эти порты без Pydantic-фикстур и без ``SessionState``.

Доступные фейки:
- ``FakeSessionView`` — in-memory реализация ``SessionView`` (Фаза 1).
- ``FakeContentCodec`` — предсказуемый ``ContentCodec`` (Фаза 2).
- ``FakeUpdateSink`` — собирает вызовы ``UpdateSink`` (Фаза 3).
"""

from tests.server.agent.fakes.content_codec import FakeContentCodec
from tests.server.agent.fakes.session_view import FakeSessionView
from tests.server.agent.fakes.update_sink import FakeUpdateSink, UpdateCalls

__all__ = [
    "FakeSessionView",
    "FakeContentCodec",
    "FakeUpdateSink",
    "UpdateCalls",
]
