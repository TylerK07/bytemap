from __future__ import annotations

from pathlib import Path

from hexmap.core.io import PagedReader
from hexmap.core.search import find_ascii, find_bytes


def test_find_bytes_basic(tmp_path: Path) -> None:
    data = bytearray(b"hello world\x00\x01\x02DEADBEEFtrail")
    p = tmp_path / "data.bin"
    p.write_bytes(data)
    with PagedReader(str(p)) as r:
        off = find_bytes(r, b"DEADBEEF", 0)
        assert off == data.index(b"DEADBEEF")
        not_found = find_bytes(r, b"NOPE", 0)
        assert not_found is None


def test_find_bytes_boundary(tmp_path: Path) -> None:
    # Create a file where the needle crosses a 64k boundary
    chunk = 64 * 1024
    size = chunk + 10
    buf = bytearray(b"A" * size)
    needle = b"XYZW"
    start = chunk - 2  # cross boundary by 2 bytes
    buf[start : start + len(needle)] = needle
    p = tmp_path / "boundary.bin"
    p.write_bytes(buf)
    with PagedReader(str(p)) as r:
        off = find_bytes(r, needle, 0)
        assert off == start


def test_find_ascii(tmp_path: Path) -> None:
    p = tmp_path / "ascii.bin"
    p.write_bytes(b"abc123 abcXYZ")
    with PagedReader(str(p)) as r:
        off = find_ascii(r, "abcXYZ", 0)
        assert off == 7
        none = find_ascii(r, "missing", 0)
        assert none is None
