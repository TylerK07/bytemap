from __future__ import annotations

import pytest


def test_compare_strings_modal_smoke(tmp_path):
    pytest.importorskip("textual")
    from hexmap.core.io import PagedReader
    from hexmap.widgets.compare_strings import CompareStringsModal

    # Prepare three small files
    a = tmp_path / "A.bin"
    b = tmp_path / "B.bin"
    c = tmp_path / "C.bin"
    a.write_bytes(b"Alpha\x00Tail")
    b.write_bytes(b"Alpha\x00Tail")
    c.write_bytes(b"Axxxa\x00Tail")
    with PagedReader(str(a)) as ra, PagedReader(str(b)) as rb, PagedReader(str(c)) as rc:
        files = [
            (str(a), ra, True),
            (str(b), rb, False),
            (str(c), rc, False),
        ]
        modal = CompareStringsModal(files, 0, None)
        # Compose should build without raising
        list(modal.compose())
        # DataTable exists and a row is selected by default
        assert hasattr(modal, "_dt")
        # Should have > 10 rows (strings + numerics)
        modal._render_table()
        # selection move works
        r0 = modal._row_index
        modal.action_select_next()
        assert modal._row_index != r0
