from __future__ import annotations

from pathlib import Path

from hexmap.core.io import PagedReader
from hexmap.core.strings import ascii_fixed, cstring_scan, stringy_heuristic


def test_cstring_scan_terminator_vs_cap(tmp_path: Path) -> None:
    p = tmp_path / "a.bin"
    p.write_bytes(b"Babylonians\x00Fren")
    with PagedReader(str(p)) as r:
        res = cstring_scan(r, 0, 64)
        assert res.terminated and not res.capped
        assert res.text == "Babylonians"
        assert res.length == len("Babylonians") + 1
        # Cap without terminator
        res2 = cstring_scan(r, 0, 5)
        assert not res2.terminated and res2.capped


def test_ascii_fixed_non_printables(tmp_path: Path) -> None:
    p = tmp_path / "b.bin"
    p.write_bytes(b"A\x01B\x00C\x7FZ")
    with PagedReader(str(p)) as r:
        s = ascii_fixed(r, 0, 8)
        # Non-printables become middle dot
        assert s.startswith("A·B·C·Z"[: len(s)])


def test_stringy_heuristic_triggers(tmp_path: Path) -> None:
    p = tmp_path / "c.bin"
    p.write_bytes(b"LeaderName    \x00rest")
    with PagedReader(str(p)) as r:
        assert stringy_heuristic(r, 0, 32, mode="cstring")
        assert stringy_heuristic(r, 0, 16, mode="ascii")

