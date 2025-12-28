from __future__ import annotations

from hexmap.core.parse import ParsedField


def compute_coverage(
    leaves: list[ParsedField], file_size: int
) -> tuple[list[tuple[int, int, str]], list[tuple[int, int]]]:
    """Compute covered and unmapped spans.

    Returns (covered_spans, unmapped_spans), where:
    - covered_spans: list of (offset, length, field_path) for each leaf with non-zero length,
      clipped to file_size and sorted by offset.
    - unmapped_spans: list of (offset, length) gaps between covered spans within [0, file_size).
    """
    cov: list[tuple[int, int, str]] = []
    for pf in leaves:
        if pf.length <= 0:
            continue
        start = max(0, pf.offset)
        end = min(file_size, pf.offset + pf.length)
        if end <= start:
            continue
        cov.append((start, end - start, pf.name))
    cov.sort(key=lambda x: x[0])

    # Merge overlapping covered spans (ignore path for merging)
    merged: list[tuple[int, int]] = []
    for s, ln, _ in cov:
        e = s + ln
        if not merged:
            merged.append((s, e))
            continue
        ps, pe = merged[-1]
        if s <= pe:
            merged[-1] = (ps, max(pe, e))
        else:
            merged.append((s, e))

    # Unmapped as gaps between merged covered, within file size
    unmapped: list[tuple[int, int]] = []
    cursor = 0
    for s, e in merged:
        if s > cursor:
            gap_end = min(file_size, s)
            if gap_end > cursor:
                unmapped.append((cursor, gap_end - cursor))
        cursor = max(cursor, e)
    if cursor < file_size:
        unmapped.append((cursor, file_size - cursor))

    return cov, unmapped
