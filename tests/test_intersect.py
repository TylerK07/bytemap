from __future__ import annotations

from hexmap.core.intersect import intersect_spans
from hexmap.core.spans import Span


def mkspan(off: int, ln: int, path: str = "f", group: str = "int") -> Span:
    return Span(off, ln, path, group)


def test_no_intersections() -> None:
    fields = [mkspan(0, 4, "a"), mkspan(10, 2, "b")]
    diffs: list[tuple[int, int]] = []
    res = intersect_spans(fields, diffs)
    assert res["a"]["changed"] is False
    assert res["b"]["changed"] is False


def test_exact_overlap() -> None:
    fields = [mkspan(0, 4, "a")]
    diffs = [(0, 4)]
    res = intersect_spans(fields, diffs)
    assert res["a"]["changed"] is True
    assert res["a"]["changed_bytes"] == 4


def test_partial_overlap() -> None:
    fields = [mkspan(10, 10, "a")]
    diffs = [(5, 10)]  # overlaps 10..15 -> 5 bytes
    res = intersect_spans(fields, diffs)
    assert res["a"]["changed"] is True
    assert res["a"]["changed_bytes"] == 5


def test_multiple_fields_and_diffs() -> None:
    fields = [mkspan(0, 4, "a"), mkspan(8, 4, "b"), mkspan(16, 4, "c")]
    diffs = [(1, 2), (9, 2), (18, 1)]
    res = intersect_spans(fields, diffs)
    assert res["a"]["changed_bytes"] == 2
    assert res["b"]["changed_bytes"] == 2
    assert res["c"]["changed_bytes"] == 1

