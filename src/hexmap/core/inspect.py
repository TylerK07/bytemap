from __future__ import annotations

import struct

from hexmap.core.io import PagedReader


def read_bytes(reader: PagedReader, offset: int, n: int) -> bytes:
    if n <= 0:
        return b""
    if offset < 0:
        return b""
    return reader.read(offset, n)


def decode_ints(b: bytes) -> dict[str, int]:
    out: dict[str, int] = {}
    if len(b) >= 1:
        v = b[0]
        out["u8"] = v
        out["i8"] = struct.unpack("b", bytes([v]))[0]
    if len(b) >= 2:
        out["u16le"] = struct.unpack("<H", b[:2])[0]
        out["i16le"] = struct.unpack("<h", b[:2])[0]
        out["u16be"] = struct.unpack(">H", b[:2])[0]
        out["i16be"] = struct.unpack(">h", b[:2])[0]
    if len(b) >= 4:
        out["u32le"] = struct.unpack("<I", b[:4])[0]
        out["i32le"] = struct.unpack("<i", b[:4])[0]
        out["u32be"] = struct.unpack(">I", b[:4])[0]
        out["i32be"] = struct.unpack(">i", b[:4])[0]
    if len(b) >= 8:
        out["u64le"] = struct.unpack("<Q", b[:8])[0]
        out["i64le"] = struct.unpack("<q", b[:8])[0]
        out["u64be"] = struct.unpack(">Q", b[:8])[0]
        out["i64be"] = struct.unpack(">q", b[:8])[0]
    return out


def decode_floats(b: bytes) -> dict[str, float]:
    out: dict[str, float] = {}
    if len(b) >= 4:
        out["f32le"] = struct.unpack("<f", b[:4])[0]
        out["f32be"] = struct.unpack(">f", b[:4])[0]
    if len(b) >= 8:
        out["f64le"] = struct.unpack("<d", b[:8])[0]
        out["f64be"] = struct.unpack(">d", b[:8])[0]
    return out


def ascii_preview(b: bytes, *, limit: int = 16) -> str:
    view = b[:limit]
    return "".join(chr(c) if 32 <= c <= 126 else "·" for c in view)


def c_string_guess(b: bytes, *, limit: int = 32) -> tuple[str, int] | None:
    if not b:
        return None
    view = b[:limit]
    nul = view.find(b"\x00")
    if nul == -1:
        return None
    s = view[:nul]
    if not s:
        return None
    if all(32 <= c <= 126 for c in s):
        try:
            return (s.decode("ascii", errors="ignore"), len(s) + 1)
        except Exception:
            return None
    return None
