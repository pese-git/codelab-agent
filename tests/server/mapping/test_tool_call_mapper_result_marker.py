"""Признак «у вызова есть результат» после удаления `result_content` (ADR-007, шаг B1).

`ToolCallMapper.to_domain` создаёт `ToolResult` только если в документе есть хоть один
признак результата. Раньше в дизъюнкцию входил и `result_content`; поле удалено как
не имеющее читателей, поэтому дизъюнкция сузилась до `raw_output`/`locations`/`content`.

Здесь проверяется, что сужение не потеряло вызовы: документ старой версии, у которого
единственным признаком был `result_content`, после миграции читается, а наблюдаемое
поведение (реплей смотрит `result.content`) не меняется.
"""

from __future__ import annotations

from codelab.server.mapping.tool_call_mapper import ToolCallMapper
from codelab.server.storage.document import SessionDocument, ToolCallState


def _call(**fields) -> ToolCallState:
    base = {"tool_call_id": "call_001", "title": "Read", "kind": "read", "status": "completed"}
    return ToolCallState(**{**base, **fields})


class TestResultMarker:
    def test_content_still_marks_result(self) -> None:
        domain = ToolCallMapper.to_domain(_call(content=[{"type": "text", "text": "тело"}]))

        assert domain.result is not None
        assert domain.result.content == [{"type": "text", "text": "тело"}]

    def test_raw_output_still_marks_result(self) -> None:
        domain = ToolCallMapper.to_domain(_call(raw_output={"bytes": 42}))

        assert domain.result is not None
        assert domain.result.raw_output == {"bytes": 42}

    def test_locations_still_mark_result(self) -> None:
        domain = ToolCallMapper.to_domain(_call(locations=[{"path": "/a.py", "line": 3}]))

        assert domain.result is not None
        assert [loc.path for loc in domain.result.locations] == ["/a.py"]

    def test_no_markers_means_no_result(self) -> None:
        assert ToolCallMapper.to_domain(_call()).result is None


class TestLegacyDocumentWithOnlyResultContent:
    def test_document_reads_and_call_survives(self) -> None:
        """Вызов, у которого единственным признаком результата был `result_content`.

        Миграция v9→v10 отбрасывает поле, поэтому признаков не остаётся и `result` будет
        `None`. Потери наблюдаемого поведения нет: единственный читатель результата в
        реплее смотрит `result.content`, который и раньше был пуст у таких вызовов.
        """
        document = SessionDocument.model_validate(
            {
                "schema_version": 9,
                "session_id": "sess_legacy",
                "cwd": "/tmp",
                "mcp_servers": [],
                "tool_calls": {
                    "call_001": {
                        "tool_call_id": "call_001",
                        "title": "Read",
                        "kind": "read",
                        "status": "completed",
                        "result_content": [{"type": "text", "text": "только тут"}],
                    }
                },
            }
        )

        call = document.tool_calls["call_001"]
        domain = ToolCallMapper.to_domain(call)

        assert domain.id == "call_001"
        assert domain.status.value == "completed"
        assert domain.result is None
