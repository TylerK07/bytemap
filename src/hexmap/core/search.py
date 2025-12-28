from __future__ import annotations

from hexmap.core.io import PagedReader


def find_bytes(reader: PagedReader, needle: bytes, start: int) -> int | None:
    """Find `needle` bytes at or after `start`. Returns offset or None.

    Efficient chunked scan without loading the entire file. Overlaps chunks by
    len(needle)-1 to catch boundary matches.
    """
    if start < 0:
        start = 0
    if not needle:
        return start if start <= reader.size else None
    if start >= reader.size:
        return None

    chunk_size = 64 * 1024
    overlap = max(0, len(needle) - 1)
    pos = start
    while pos < reader.size:
        end = min(reader.size, pos + chunk_size)
        data = reader.read(pos, end - pos)
        idx = data.find(needle)
        if idx != -1:
            return pos + idx
        if end >= reader.size:
            break
        # Advance with overlap to catch cross-boundary matches
        pos = end - overlap
    return None


def find_ascii(reader: PagedReader, text: str, start: int, encoding: str = "utf-8") -> int | None:
    """Find ASCII/UTF-8 text forward from `start`. Returns offset or None."""
    try:
        needle = text.encode(encoding)
    except Exception:
        return None
    return find_bytes(reader, needle, start)
