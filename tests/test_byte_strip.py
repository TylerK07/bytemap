from __future__ import annotations

from pathlib import Path

import pytest

from hexmap.core.io import PagedReader


def test_hex_ascii_width_and_mapping(tmp_path: Path) -> None:
    pytest.importorskip("rich")
    from hexmap.widgets.byte_strip import ByteStrip
    p = tmp_path / "d.bin"
    p.write_bytes(bytes([0x41, 0x00, 0x20, 0x7F, 0x42, 0x43, 0x44, 0x45]))
    with PagedReader(str(p)) as r:
        strip = ByteStrip()
        # Simulate some width
        strip.size = type("S", (), {"width": 40, "height": 4})()  # type: ignore
        strip.update_state([("★ file", r)], 0, None)
        # Ensure computed window reasonable
        w = strip._compute_window()
        assert w >= 8


def test_selection_highlight_does_not_crash(tmp_path: Path) -> None:
    pytest.importorskip("rich")
    p = tmp_path / "e.bin"
    p.write_bytes(b"\x00" * 64)
    with PagedReader(str(p)) as r:
        from hexmap.widgets.byte_strip import ByteStrip
        strip = ByteStrip()
        strip.size = type("S", (), {"width": 40, "height": 4})()  # type: ignore
        strip.update_state([("★ file", r)], 10, (12, 8))
        # No exceptions; render returns a Group
        _ = strip.render()


def test_modal_with_strip_smoke(tmp_path: Path) -> None:
    pytest.importorskip("textual")
    from hexmap.widgets.compare_strings import CompareStringsModal

    p = tmp_path / "f.bin"
    p.write_bytes(b"ABCDEFGHIJKLMNOPQRSTUVWXYZ012345")
    with PagedReader(str(p)) as r:
        files = [(str(p), r, True), (str(p), r, False), (str(p), r, False)]
        modal = CompareStringsModal(files, 0, (0, 16))
        list(modal.compose())
        assert hasattr(modal, "_strip")
