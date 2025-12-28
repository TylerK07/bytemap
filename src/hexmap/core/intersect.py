from __future__ import annotations

from hexmap.core.spans import Span


def intersect_spans(
    fields: list[Span], diffs: list[tuple[int, int]]
) -> dict[str, dict]:
    """Compute intersection between field spans and diff spans.

    Returns a mapping of field path -> {
        'offset': int,
        'length': int,
        'group': str,
        'changed': bool,
        'changed_bytes': int,
    }

    Assumes inputs may be unsorted; sorts them, then uses a two-pointer sweep
    to compute linear-time intersections.
    """
    if not fields:
        return {}

    # Normalize and sort
    fspans = sorted(
        ((f.offset, f.offset + f.length, f) for f in fields if f.length > 0),
        key=lambda t: t[0],
    )
    dspans = sorted(((s, s + ln) for (s, ln) in diffs if ln > 0), key=lambda t: t[0])

    res: dict[str, dict] = {
        f.path: {
            "offset": f.offset,
            "length": f.length,
            "group": f.group,
            "changed": False,
            "changed_bytes": 0,
        }
        for (_s, _e, f) in fspans
    }

    i = 0
    j = 0
    while i < len(fspans) and j < len(dspans):
        fs, fe, f = fspans[i]
        ds, de = dspans[j]

        if fe <= ds:
            i += 1
            continue
        if de <= fs:
            j += 1
            continue
        # Overlap exists
        inter = min(fe, de) - max(fs, ds)
        if inter > 0:
            entry = res[f.path]
            entry["changed"] = True
            entry["changed_bytes"] += inter
        # Advance the one that ends first
        if fe <= de:
            i += 1
        else:
            j += 1

    return res
