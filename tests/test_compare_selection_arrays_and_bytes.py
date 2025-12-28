from __future__ import annotations

from pathlib import Path

import pytest

from hexmap.core.io import PagedReader
from hexmap.core.numbers import array_summary, decode_int_array
from hexmap.core.schema_edit import upsert_array_field, upsert_bytes_field


def test_selection_first_span_basis_and_divisibility(tmp_path: Path) -> None:
    p = tmp_path / "s.bin"
    # 8 bytes: two u32le values [1,2]
    p.write_bytes((1).to_bytes(4, "little") + (2).to_bytes(4, "little"))
    with PagedReader(str(p)) as r:
        vals = decode_int_array(r, 0, bits=32, signed=False, endian="little", count=2)
        assert vals == [1, 2]
        summary = array_summary(vals or [])
        assert "k=2" in summary and "[1, 2]" in summary


def test_bytes_digest_eof(tmp_path: Path) -> None:
    p = tmp_path / "b.bin"
    p.write_bytes(b"\x01\x02\x03")
    with PagedReader(str(p)) as r:
        data = r.read(0, 8)
        # emulate first 8 digest
        hexes = " ".join(f"{b:02X}" for b in data[:8])
        assert hexes == "01 02 03"


def test_commit_bytes_and_array_yaml() -> None:
    base = "fields:\n  - name: header\n    type: bytes\n    length: 4\n"
    new, spec = upsert_bytes_field(base, offset=0x10, length=12, name="blob")
    assert "type: bytes" in new and "length: 12" in new
    new2, spec2 = upsert_array_field(new, offset=0x20, elem_type="u16", length=3, name="arr")
    assert "type: array of u16" in new2 and "length: 3" in new2


def test_commit_and_jump_len_calculation(tmp_path: Path) -> None:
    pytest.importorskip("textual")
    from hexmap.widgets.compare_strings import CompareStringsModal

    p = tmp_path / "x.bin"
    p.write_bytes(b"A" * 32)
    with PagedReader(str(p)) as r:
        files = [(str(p), r, True)]
        # selection 16 bytes
        modal = CompareStringsModal(files, 0, (0, 16))
        # array u16 rows should exist; pick the first array row and compute len
        rows = modal._row_defs()
        arr_row = next(rd for rd in rows if rd.get("kind") == "array" and rd.get("bits") == 16)
        jump = modal._committed_span_len(arr_row)
        assert jump == 16

