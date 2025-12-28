from __future__ import annotations

from pathlib import Path

from hexmap.core.io import PagedReader
from hexmap.core.numbers import decode_float, decode_int


def test_numeric_decoding_u16_endianness(tmp_path: Path) -> None:
    p = tmp_path / "n.bin"
    # bytes: 0x34 0x12 => u16le=0x1234=4660, u16be=0x3412=13330
    p.write_bytes(bytes([0x34, 0x12, 0x00, 0x00]))
    with PagedReader(str(p)) as r:
        le = decode_int(r, 0, bits=16, signed=False, endian="little")
        be = decode_int(r, 0, bits=16, signed=False, endian="big")
        assert le.ok and le.text == "4660"
        assert be.ok and be.text == "13330"


def test_numeric_eof(tmp_path: Path) -> None:
    p = tmp_path / "e.bin"
    p.write_bytes(b"\x01")  # only 1 byte available
    with PagedReader(str(p)) as r:
        v16 = decode_int(r, 0, bits=16, signed=False, endian="little")
        assert not v16.ok and v16.text == "—"


def test_float_formatting(tmp_path: Path) -> None:
    import struct

    p = tmp_path / "f.bin"
    p.write_bytes(struct.pack("<f", 1.2345) + struct.pack("<d", 2.5))
    with PagedReader(str(p)) as r:
        f32 = decode_float(r, 0, bits=32, endian="little")
        f64 = decode_float(r, 4, bits=64, endian="little")
        assert f32.ok and "1.2345"[:5] in f32.text
        assert f64.ok and "2.5" in f64.text

