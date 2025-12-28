from __future__ import annotations

from pathlib import Path

from hexmap.core.diff import compute_diff_spans, diff_stats
from hexmap.core.io import PagedReader


def write_bytes(p: Path, data: bytes) -> Path:
    p.write_bytes(data)
    return p


def test_identical_files_no_spans(tmp_path: Path) -> None:
    a = write_bytes(tmp_path / "a.bin", b"abcdef")
    b = write_bytes(tmp_path / "b.bin", b"abcdef")
    with PagedReader(str(a)) as ra, PagedReader(str(b)) as rb:
        spans = compute_diff_spans(ra, rb, chunk_size=3)
        stats = diff_stats(ra, rb, spans)
    assert spans == []
    assert stats["changed_bytes"] == 0
    assert stats["changed_percent"] == 0.0


def test_single_byte_change_one_span(tmp_path: Path) -> None:
    a = write_bytes(tmp_path / "a.bin", b"abcXef")
    b = write_bytes(tmp_path / "b.bin", b"abcdef")
    with PagedReader(str(a)) as ra, PagedReader(str(b)) as rb:
        spans = compute_diff_spans(ra, rb, chunk_size=4)
        stats = diff_stats(ra, rb, spans)
    assert spans == [(3, 1)]
    assert stats["changed_bytes"] == 1
    assert round(stats["changed_percent"], 2) == round(1 / 6 * 100.0, 2)


def test_multiple_separated_changes(tmp_path: Path) -> None:
    a = write_bytes(tmp_path / "a.bin", b"aXcdeY")
    b = write_bytes(tmp_path / "b.bin", b"abcdef")
    with PagedReader(str(a)) as ra, PagedReader(str(b)) as rb:
        spans = compute_diff_spans(ra, rb, chunk_size=4)
        stats = diff_stats(ra, rb, spans)
    assert spans == [(1, 1), (5, 1)]
    assert stats["changed_bytes"] == 2
    assert round(stats["changed_percent"], 2) == round(2 / 6 * 100.0, 2)


def test_different_sizes_tail_span(tmp_path: Path) -> None:
    a = write_bytes(tmp_path / "a.bin", b"abcd")
    b = write_bytes(tmp_path / "b.bin", b"abcdef")
    with PagedReader(str(a)) as ra, PagedReader(str(b)) as rb:
        spans = compute_diff_spans(ra, rb, chunk_size=4)
        stats = diff_stats(ra, rb, spans)
    # Tail from 4..5 (2 bytes)
    assert spans == [(4, 2)]
    assert stats["changed_bytes"] == 2
    assert round(stats["changed_percent"], 2) == round(2 / 6 * 100.0, 2)


def test_chunk_boundary_change_merging(tmp_path: Path) -> None:
    # Change spanning across chunk boundary (chunk_size = 8)
    base = bytearray(range(32))
    mod = bytearray(base)
    # Flip bytes from 6..10 (crosses boundary between [0..7] and [8..15])
    for i in range(6, 11):
        mod[i] ^= 0xFF
    a = write_bytes(tmp_path / "a.bin", bytes(mod))
    b = write_bytes(tmp_path / "b.bin", bytes(base))
    with PagedReader(str(a)) as ra, PagedReader(str(b)) as rb:
        spans = compute_diff_spans(ra, rb, chunk_size=8)
        stats = diff_stats(ra, rb, spans)
    assert spans == [(6, 5)]
    assert stats["changed_bytes"] == 5
    assert round(stats["changed_percent"], 2) == round(5 / 32 * 100.0, 2)


def test_diff_tab_smoke(tmp_path: Path) -> None:
    import pytest
    pytest.importorskip("textual")
    # Build small files and ensure diff plumbing doesn't crash
    a = write_bytes(tmp_path / "a.bin", b"abcdef")
    b = write_bytes(tmp_path / "b.bin", b"abcxef")
    from hexmap.app import HexmapApp

    app = HexmapApp(str(a))
    # Build diff panes and set diff target without running the event loop
    app._build_diff_panes()
    app.set_diff_target(str(b))
    assert len(app._diff_regions) >= 1
