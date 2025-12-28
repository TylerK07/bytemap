from __future__ import annotations

from hexmap.core.spans import Span, SpanIndex, type_group


def test_span_index_basic() -> None:
    spans = [Span(0, 4, "a", "int"), Span(10, 2, "b", "bytes")]
    idx = SpanIndex(spans)
    assert idx.find(0).path == "a"
    assert idx.find(3).path == "a"
    assert idx.find(9) is None
    assert idx.find(10).path == "b"
    assert idx.find(11).path == "b"
    assert idx.find(12) is None


def test_type_group_mapping() -> None:
    assert type_group("u8") == "int"
    assert type_group("i32") == "int"
    assert type_group("f32") == "float"
    assert type_group("string") == "string"
    assert type_group("bytes") == "bytes"
    assert type_group("weird") == "unknown"

