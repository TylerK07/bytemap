from __future__ import annotations

from bisect import bisect_right

from hexmap.core.io import PagedReader


def compute_diff_spans(
    reader_a: PagedReader,
    reader_b: PagedReader,
    *,
    chunk_size: int = 64 * 1024,
) -> list[tuple[int, int]]:
    """Compute merged contiguous changed ranges between two files.

    Returns a list of (offset, length) spans. Bytes beyond the shorter file
    are treated as changed.
    """
    size_a = int(reader_a.size)
    size_b = int(reader_b.size)
    total = max(size_a, size_b)
    if total == 0:
        return []

    spans: list[tuple[int, int]] = []
    open_start: int | None = None

    offset = 0
    while offset < total:
        to_read = min(chunk_size, total - offset)
        chunk_a = reader_a.read(offset, to_read) if offset < size_a else b""
        chunk_b = reader_b.read(offset, to_read) if offset < size_b else b""

        la = len(chunk_a)
        lb = len(chunk_b)
        same_len = min(la, lb)

        # Compare common prefix
        for i in range(same_len):
            if chunk_a[i] != chunk_b[i]:
                if open_start is None:
                    open_start = offset + i
            else:
                if open_start is not None:
                    spans.append((open_start, offset + i - open_start))
                    open_start = None

        # Tail beyond shorter file counts as changed
        if la != lb:
            tail_start = offset + same_len
            if open_start is None:
                open_start = tail_start
            # keep span open across chunks; length will be resolved at EOF or on match

        offset += to_read

    if open_start is not None:
        spans.append((open_start, total - open_start))

    # Merge adjacent spans if any were split across chunk boundaries
    merged: list[tuple[int, int]] = []
    for s, ln in spans:
        if ln <= 0:
            continue
        if not merged:
            merged.append((s, ln))
            continue
        ps, pln = merged[-1]
        pe = ps + pln
        if s <= pe:  # overlapping or adjacent (since we never create gaps of 0)
            new_e = max(pe, s + ln)
            merged[-1] = (ps, new_e - ps)
        else:
            merged.append((s, ln))
    return merged


def diff_stats(
    reader_a: PagedReader, reader_b: PagedReader, spans: list[tuple[int, int]]
) -> dict[str, float | int]:
    size_a = int(reader_a.size)
    size_b = int(reader_b.size)
    max_size = max(size_a, size_b)
    changed_bytes = sum(ln for (_s, ln) in spans)
    changed_percent = (changed_bytes / max_size * 100.0) if max_size > 0 else 0.0
    return {
        "size_a": size_a,
        "size_b": size_b,
        "max_size": max_size,
        "changed_bytes": changed_bytes,
        "changed_percent": changed_percent,
    }


class DiffIndex:
    """Index for fast membership checks within diff spans."""

    def __init__(self, spans: list[tuple[int, int]]) -> None:
        # store as [start,end) merged non-overlapping spans
        merged: list[tuple[int, int]] = []
        for s, ln in sorted(((s, ln) for (s, ln) in spans if ln > 0), key=lambda t: t[0]):
            e = s + ln
            if merged and s <= merged[-1][1]:
                ps, pe = merged[-1]
                merged[-1] = (ps, max(pe, e))
            else:
                merged.append((s, e))
        self._spans = merged
        self._starts = [s for (s, _e) in merged]

    def contains(self, offset: int) -> bool:
        if not self._spans:
            return False
        i = bisect_right(self._starts, offset) - 1
        if i >= 0:
            s, e = self._spans[i]
            return s <= offset < e
        return False


class SearchSpanIndex:
    """Index for fast lookup of search span roles (hit, length, payload)."""

    def __init__(self, spans: list[tuple[int, int, str]]) -> None:
        # Store spans as (start, end, role) sorted by start offset
        # Don't merge spans since they can have different roles
        self._spans: list[tuple[int, int, str]] = []
        for s, ln, role in sorted(((s, ln, r) for (s, ln, r) in spans if ln > 0), key=lambda t: t[0]):
            e = s + ln
            self._spans.append((s, e, role))
        self._starts = [s for (s, _e, _r) in self._spans]

    def get_role(self, offset: int) -> str | None:
        """Get the role of the search span at this offset, or None if not in a span."""
        if not self._spans:
            return None
        # Binary search to find the rightmost span that starts at or before offset
        i = bisect_right(self._starts, offset) - 1
        if i >= 0:
            s, e, role = self._spans[i]
            if s <= offset < e:
                return role
        return None
