from __future__ import annotations

import pytest


def test_instances_suggestion_numeric(tmp_path):
    pytest.importorskip("textual")
    from hexmap.core.io import PagedReader
    from hexmap.widgets.compare_strings import CompareStringsModal

    p = tmp_path / "g.bin"
    # 16 bytes selection; if u16 selected, expect instances suggested = 8
    p.write_bytes(b"\x00" * 64)
    with PagedReader(str(p)) as r:
        modal = CompareStringsModal([(str(p), r, True)], 0, (0, 16))
        list(modal.compose())
        # Select a u16 row: rows are generated; find first int 16 row
        rows = modal._row_defs()
        idx = next(
            i
            for i, rd in enumerate(rows)
            if rd.get("kind") == "int"
            and rd.get("bits") == 16
            and rd.get("endian") == "little"
        )
        modal._select_row(idx)
        modal._refresh_len_dependent_ui()
        assert int(modal._instances) == 8


def test_array_rows_removed(tmp_path):
    pytest.importorskip("textual")
    from hexmap.core.io import PagedReader
    from hexmap.widgets.compare_strings import CompareStringsModal

    p = tmp_path / "h.bin"
    p.write_bytes(b"\x00" * 64)
    with PagedReader(str(p)) as r:
        modal = CompareStringsModal([(str(p), r, True)], 0, (0, 16))
        list(modal.compose())
        rows = modal._row_defs()
        assert all(
            "×" not in (
                rd.get("label")() if callable(rd.get("label")) else str(rd.get("label"))
            )
            for rd in rows
        )
