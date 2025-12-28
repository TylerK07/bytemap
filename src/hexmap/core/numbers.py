from __future__ import annotations

import math
import struct
from dataclasses import dataclass

from hexmap.core.io import PagedReader


@dataclass(frozen=True)
class NumCell:
    text: str
    ok: bool  # False when insufficient bytes


def _have(reader: PagedReader, offset: int, width: int) -> bool:
    return offset >= 0 and offset + width <= reader.size


def decode_int(
    reader: PagedReader, offset: int, *, bits: int, signed: bool, endian: str
) -> NumCell:
    width = bits // 8
    if not _have(reader, offset, width):
        return NumCell("—", False)
    data = reader.read(offset, width)
    table = {
        1: ("b" if signed else "B"),
        2: ("h" if signed else "H"),
        4: ("i" if signed else "I"),
        8: ("q" if signed else "Q"),
    }
    fmt = ("<" if endian == "little" else ">") + table[width]
    try:
        val = struct.unpack(fmt, data)[0]
    except Exception:
        return NumCell("—", False)
    return NumCell(str(val), True)


def decode_float(reader: PagedReader, offset: int, *, bits: int, endian: str) -> NumCell:
    width = bits // 8
    if not _have(reader, offset, width):
        return NumCell("—", False)
    data = reader.read(offset, width)
    fmt = ("<" if endian == "little" else ">") + ("f" if bits == 32 else "d")
    try:
        val = struct.unpack(fmt, data)[0]
    except Exception:
        return NumCell("—", False)
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return NumCell(str(val), True)
    # Compact formatting
    if bits == 32:
        return NumCell(f"{val:.6g}", True)
    return NumCell(f"{val:.9g}", True)


def decode_int_array(
    reader: PagedReader,
    offset: int,
    *,
    bits: int,
    signed: bool,
    endian: str,
    count: int,
) -> list[int] | None:
    width = bits // 8
    total = width * count
    if not _have(reader, offset, total):
        return None
    data = reader.read(offset, total)
    table = {1: ("b" if signed else "B"), 2: ("h" if signed else "H"), 4: ("i" if signed else "I")}
    fmt_char = table[width]
    fmt = ("<" if endian == "little" else ">") + fmt_char * count
    try:
        vals = list(struct.unpack(fmt, data))
        return vals
    except Exception:
        return None


def array_summary(vals: list[int]) -> str:
    if not vals:
        return "k=0"
    k = len(vals)
    mn = min(vals)
    mx = max(vals)
    head = ", ".join(str(v) for v in vals[:4])
    tail = ", …" if k > 4 else ""
    return f"k={k}  min={mn}  max={mx}  [{head}{tail}]"
