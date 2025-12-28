from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass


@dataclass(frozen=True)
class Span:
    offset: int
    length: int
    path: str
    group: str  # int|string|bytes|float|unknown
    effective_endian: str | None = None  # "little" or "big"
    endian_source: str | None = None  # "field"|"type"|"parent"|"root"|"default"
    color_override: str | None = None  # normalized color (named or #rrggbb)

    @property
    def end(self) -> int:
        return self.offset + self.length


class SpanIndex:
    def __init__(self, spans: list[Span]) -> None:
        # assumes non-overlapping sorted spans; overlapping still works by picking the first match
        self._spans = sorted((s for s in spans if s.length > 0), key=lambda s: s.offset)
        self._starts = [s.offset for s in self._spans]

    def find(self, offset: int) -> Span | None:
        i = bisect_right(self._starts, offset) - 1
        if i >= 0:
            s = self._spans[i]
            if s.offset <= offset < s.end:
                return s
        return None


def type_group(pf_type: str) -> str:
    t = pf_type.lower()
    if t.startswith("u") or t.startswith("i"):
        return "int"
    if t.startswith("f"):
        return "float"
    if t == "string":
        return "string"
    if t == "bytes":
        return "bytes"
    return "unknown"
