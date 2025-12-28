from __future__ import annotations

import pytest


def _build_modal(tmp_path, offset=0):
    pytest.importorskip("textual")
    pytest.importorskip("rich")
    from hexmap.core.io import PagedReader
    from hexmap.widgets.compare_strings import CompareStringsModal

    a = tmp_path / "A.bin"
    b = tmp_path / "B.bin"
    a.write_bytes(b"Hello\x00World")
    b.write_bytes(b"Hello\x00World")
    ra = PagedReader(str(a))
    rb = PagedReader(str(b))
    files = [(str(a), ra, True), (str(b), rb, False)]
    return CompareStringsModal(files, offset, None), (ra, rb)


def test_default_name_formatting(tmp_path):
    modal, readers = _build_modal(tmp_path, offset=0x98)
    list(modal.compose())
    assert modal._name_input.value == "string_0x00000098"
    # cleanup
    for r in readers:
        r.close()


def test_adjust_n_and_m_by_1_and_4_with_clamp(tmp_path):
    modal, readers = _build_modal(tmp_path)
    list(modal.compose())
    # Start on ascii row (index 0). Adjust N by 1 and 4
    n0 = modal._n
    modal.action_adjust_small_inc()
    assert modal._n == min(modal.MAX_N, n0 + 1)
    modal.action_adjust_big_inc()
    assert modal._n == min(modal.MAX_N, n0 + 5)
    # Move to cstring row and adjust M
    modal.action_select_next()
    m0 = modal._m
    modal.action_adjust_small_dec()
    assert modal._m == max(modal.MIN_M, m0 - 1)
    modal.action_adjust_big_dec()
    assert modal._m == max(modal.MIN_M, m0 - 5)
    # Clamp extremes
    modal._n = modal.MAX_N
    modal.action_adjust_big_inc()
    assert modal._n == modal.MAX_N
    modal._row_index = 1
    modal._m = modal.MIN_M
    modal.action_adjust_small_dec()
    assert modal._m == modal.MIN_M
    # cleanup
    for r in readers:
        r.close()


def test_arrow_input_smoke(tmp_path):
    pytest.importorskip("textual")
    modal, readers = _build_modal(tmp_path)
    # Compose should work and arrow actions should not raise
    list(modal.compose())
    # DataTable present
    assert hasattr(modal, "_dt")
    # Default selected row present
    r0 = modal._row_index
    modal.action_select_next()
    assert modal._row_index in {0, 1} and modal._row_index != r0
    modal.action_select_prev()
    modal.action_adjust_small_inc()
    modal.action_adjust_small_dec()
    modal.action_adjust_big_inc()
    modal.action_adjust_big_dec()
    for r in readers:
        r.close()
