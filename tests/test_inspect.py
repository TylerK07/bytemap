from __future__ import annotations

from pathlib import Path

from hexmap.core.inspect import (
    ascii_preview,
    c_string_guess,
    decode_floats,
    decode_ints,
    read_bytes,
)
from hexmap.core.io import PagedReader


def test_decode_ints_basic() -> None:
    b = bytes([0x01, 0x00, 0x02, 0x00, 0xFF, 0xFF, 0x00, 0x00])
    ints = decode_ints(b)
    assert ints["u8"] == 1 and ints["i8"] == 1
    assert ints["u16le"] == 1 and ints["u16be"] == 256
    assert ints["u32le"] == 131073 and ints["u32be"] == 16777728


def test_decode_floats_basic() -> None:
    import struct

    b = struct.pack("<f", 1.5) + b"\x00\x00\x00\x00"
    floats = decode_floats(b)
    assert abs(floats["f32le"] - 1.5) < 1e-6


def test_ascii_preview_and_cstring(tmp_path: Path) -> None:
    s = b"Hello\x00World"
    prev = ascii_preview(s, limit=16)
    assert prev.startswith("Hello")
    guess = c_string_guess(s, limit=32)
    assert guess is not None and guess[0] == "Hello"


def test_read_bytes_bounds(tmp_path: Path) -> None:
    p = tmp_path / "t.bin"
    p.write_bytes(b"ABCD")
    with PagedReader(str(p)) as r:
        assert read_bytes(r, 2, 4) == b"CD"
        assert read_bytes(r, 4, 4) == b""
        assert read_bytes(r, -1, 1) == b""


def test_ascii_preview_len() -> None:
    b = b"ABCDEFGHIJKLmnopq"
    s = ascii_preview(b, limit=16)
    assert len(s) == 16


def test_inspector_compact_full_smoke(tmp_path: Path) -> None:
    import pytest
    pytest.importorskip("textual")
    from hexmap.core.spans import SpanIndex
    from hexmap.widgets.inspector import Inspector

    p = tmp_path / "d.bin"
    p.write_bytes(b"Babylonians\x00Fren")
    with PagedReader(str(p)) as r:
        insp = Inspector()
        spans = SpanIndex([])
        # Full
        insp.update_for(r, 0, spans, [], endian="little")
        # Toggle mode (compact)
        insp.toggle_mode()
        insp.update_for(r, 0, spans, [], endian="little")
