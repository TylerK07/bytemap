from __future__ import annotations

from pathlib import Path

import pytest

from hexmap.core.io import InvalidOffset, PagedReader


def make_fixture_file(tmp_path: Path, size: int = 5000) -> Path:
    # Deterministic content: 0..255 repeating
    data = bytes(i % 256 for i in range(size))
    p = tmp_path / "fixture.bin"
    p.write_bytes(data)
    return p


@pytest.mark.parametrize("use_mmap", [True, False])
def test_read_exact_ranges(tmp_path: Path, use_mmap: bool) -> None:
    path = make_fixture_file(tmp_path, size=5000)
    with PagedReader(str(path), use_mmap=use_mmap) as r:
        # start of file
        b0 = r.read(0, 16)
        assert b0 == bytes(range(16))

        # mid-file range
        off = 1234
        ln = 77
        expected = bytes(i % 256 for i in range(off, off + ln))
        assert r.read(off, ln) == expected

        # large chunk
        off2 = 100
        ln2 = 1024
        expected2 = bytes(i % 256 for i in range(off2, off2 + ln2))
        assert r.read(off2, ln2) == expected2


@pytest.mark.parametrize("use_mmap", [True, False])
def test_read_past_eof_truncated(tmp_path: Path, use_mmap: bool) -> None:
    path = make_fixture_file(tmp_path, size=4097)
    with PagedReader(str(path), use_mmap=use_mmap) as r:
        # Request more than available from near EOF
        start = r.size - 10
        out = r.read(start, 100)
        assert len(out) == 10
        expected = bytes(i % 256 for i in range(start, r.size))
        assert out == expected

        # Offset exactly at EOF returns empty
        assert r.read(r.size, 10) == b""


@pytest.mark.parametrize("use_mmap", [True, False])
def test_invalid_negative_offset_raises(tmp_path: Path, use_mmap: bool) -> None:
    path = make_fixture_file(tmp_path, size=100)
    with PagedReader(str(path), use_mmap=use_mmap) as r:
        with pytest.raises(InvalidOffset):
            r.read(-1, 1)
        with pytest.raises(InvalidOffset):
            r.byte_at(-5)
        with pytest.raises(InvalidOffset):
            r.slice(-1, 10)
        with pytest.raises(InvalidOffset):
            r.read(0, -1)


@pytest.mark.parametrize("use_mmap", [True, False])
def test_byte_at_behavior(tmp_path: Path, use_mmap: bool) -> None:
    path = make_fixture_file(tmp_path, size=1024)
    with PagedReader(str(path), use_mmap=use_mmap) as r:
        # Valid byte
        assert r.byte_at(0) == 0
        assert r.byte_at(255) == 255
        assert r.byte_at(256) == 0

        # At EOF returns None
        assert r.byte_at(r.size) is None


def test_file_not_found(tmp_path: Path) -> None:
    missing = tmp_path / "missing.bin"
    with pytest.raises(FileNotFoundError):
        PagedReader(str(missing))
