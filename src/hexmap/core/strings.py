from __future__ import annotations
# ruff: noqa: I001  # import-sort formatting handled manually for clarity

from dataclasses import dataclass

from hexmap.core.io import PagedReader


PRINTABLE_MIN = 32
PRINTABLE_MAX = 126


def _to_ascii_glyphs(b: bytes) -> str:
    return "".join(chr(c) if PRINTABLE_MIN <= c <= PRINTABLE_MAX else "·" for c in b)


def ascii_fixed(reader: PagedReader, offset: int, length: int) -> str:
    """Render exactly `length` bytes (truncated at EOF) as ASCII with non-printables as ·.

    Bounds-safe: never reads more than `length` bytes.
    """
    if length <= 0:
        return ""
    data = reader.read(max(0, int(offset)), int(length))
    return _to_ascii_glyphs(data)


@dataclass(frozen=True)
class CStringResult:
    text: str
    terminated: bool  # True if a 0x00 terminator encountered within max_len
    length: int  # number of bytes consumed including terminator if present
    capped: bool  # True if we hit the cap without seeing a terminator


def cstring_scan(reader: PagedReader, offset: int, max_len: int) -> CStringResult:
    """Scan forward up to `max_len` bytes for a null-terminated ASCII string.

    - Returns ASCII with non-printables replaced by · (no decoding errors).
    - `length` counts bytes consumed; includes the terminator when `terminated`.
    - Never reads beyond `max_len` bytes.
    """
    if max_len <= 0:
        return CStringResult("", False, 0, False)
    view = reader.read(max(0, int(offset)), int(max_len))
    if not view:
        return CStringResult("", False, 0, False)
    pos = view.find(b"\x00")
    terminated = pos != -1
    if terminated:
        s = view[:pos]
        text = _to_ascii_glyphs(s)
        return CStringResult(text, True, pos + 1, False)
    # No terminator within max_len
    text = _to_ascii_glyphs(view)
    consumed = len(view)
    return CStringResult(text, False, consumed, consumed >= max_len)


def _printable_ratio(b: bytes) -> float:
    if not b:
        return 0.0
    n = sum(1 for c in b if (PRINTABLE_MIN <= c <= PRINTABLE_MAX) or c == 32)
    return n / len(b)


def stringy_heuristic(reader: PagedReader, offset: int, length_basis: int, *, mode: str) -> bool:
    """Heuristic string-likeness on the first min(32, basis) bytes.

    mode: 'ascii' (fixed window) or 'cstring' (null-terminated with adjustable max)
    """
    window = max(1, min(32, int(length_basis)))
    head = reader.read(max(0, int(offset)), window)
    if not head:
        return False
    ratio = _printable_ratio(head)
    if ratio < 0.70:
        return False
    if mode == "ascii":
        # Many trailing spaces suggests padded string
        trailing_spaces = len(head) - len(head.rstrip(b" "))
        if trailing_spaces >= max(1, window // 4):
            return True
        # Or a long printable run before first non-printable
        run = 0
        for c in head:
            if (PRINTABLE_MIN <= c <= PRINTABLE_MAX) or c == 32:
                run += 1
            else:
                break
        return run >= max(8, window // 2)
    if mode == "cstring":
        # Prefer seeing a terminator within the cap
        tail = reader.read(max(0, int(offset)), max(1, int(length_basis)))
        return b"\x00" in tail
    return False


def any_stringy(readers: list[PagedReader], offset: int, n: int, m: int) -> bool:
    for r in readers:
        if stringy_heuristic(r, offset, m, mode="cstring") or stringy_heuristic(
            r, offset, n, mode="ascii"
        ):
            return True
    return False


def decode_cstring_fixed_slot(slot: bytes) -> tuple[str, bool, int]:
    """Decode a fixed-slot C-string from exactly the provided bytes.

    - Finds first 0x00 in `slot`. If found at i: text=slot[:i], terminated=True, used=i+1.
      If not found: text=slot, terminated=False, used=len(slot).
    - Decodes to display as ASCII with non-printables shown as '·'.
    """
    if not slot:
        return ("", False, 0)
    nul = slot.find(b"\x00")
    if nul != -1:
        text_bytes = slot[:nul]
        terminated = True
        used = nul + 1
    else:
        text_bytes = slot
        terminated = False
        used = len(slot)
    disp = "".join(chr(b) if 32 <= b <= 126 else "·" for b in text_bytes)
    return (disp, terminated, used)
