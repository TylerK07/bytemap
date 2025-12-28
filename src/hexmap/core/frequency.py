from __future__ import annotations

from array import array

from hexmap.core.io import PagedReader


def compute_frequency_map(
    baseline: PagedReader, snapshots: list[PagedReader], *, chunk_size: int = 64 * 1024
) -> tuple[array, dict[str, float | int]]:
    """Compute per-byte change frequency counts across snapshots vs. baseline.

    Returns (counts, stats) where counts is an array('H') of length max_size and
    each entry is the number of snapshots where the byte differs from baseline.
    Stats include: N, max_size, union_changed, mean_diff_rate.
    """
    n = len(snapshots)
    size_a = baseline.size
    max_size = max([size_a] + [b.size for b in snapshots]) if snapshots else size_a
    counts = array("H", [0] * max_size)
    if n == 0 or max_size == 0:
        return counts, {"N": n, "max_size": max_size, "union_changed": 0, "mean_diff_rate": 0.0}

    union_changed = 0

    offset = 0
    while offset < max_size:
        to_read = min(chunk_size, max_size - offset)
        a_chunk = baseline.read(offset, to_read) if offset < size_a else b""
        # Pre-read snapshot chunks
        b_chunks = [b.read(offset, to_read) if offset < b.size else b"" for b in snapshots]
        # Iterate within chunk
        for i in range(to_read):
            a_has = offset + i < size_a
            a_val = a_chunk[i] if a_has and i < len(a_chunk) else None
            diff_count = 0
            for b_idx, b in enumerate(snapshots):
                b_has = offset + i < b.size
                if not b_has:
                    diff_count += 1
                    continue
                b_chunk = b_chunks[b_idx]
                b_val = b_chunk[i] if i < len(b_chunk) else None
                if a_val is None or b_val is None or a_val != b_val:
                    diff_count += 1
            if diff_count:
                counts[offset + i] = diff_count
                union_changed += 1
        offset += to_read

    mean_rate = (union_changed / max_size) if max_size else 0.0
    stats = {
        "N": n,
        "max_size": max_size,
        "union_changed": union_changed,
        "mean_diff_rate": mean_rate,
    }
    return counts, stats


def freq_at(counts: array, offset: int) -> int:
    if offset < 0 or offset >= len(counts):
        return 0
    return int(counts[offset])
