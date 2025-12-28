from __future__ import annotations

from pathlib import Path

import pytest


def test_file_browser_lists_siblings(tmp_path: Path) -> None:
    pytest.importorskip("textual")
    from hexmap.widgets.file_browser import FileBrowser

    # Create files
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    c = tmp_path / "c.txt"
    a.write_bytes(b"a")
    b.write_bytes(b"b")
    c.write_text("c")
    files = FileBrowser.list_files(tmp_path)
    names = [p.name for p in files]
    assert names == sorted(["a.bin", "b.bin", "c.txt"])  # directories filtered; names sorted


def test_diff_target_recompute(tmp_path: Path) -> None:
    pytest.importorskip("textual")
    from hexmap.app import HexmapApp

    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    a.write_bytes(b"abcdef")
    b.write_bytes(b"abcxef")
    app = HexmapApp(str(a))
    app._build_diff_panes()
    app.set_diff_target(str(b))
    # setting same target again should not change spans length
    first = list(app._diff_regions)
    app.set_diff_target(str(b))
    assert app._diff_regions == first


def test_diff_empty_state_no_primary(tmp_path: Path) -> None:
    pytest.importorskip("textual")
    from hexmap.app import HexmapApp

    # Create fake app and clear reader
    a = tmp_path / "a.bin"
    a.write_bytes(b"x")
    app = HexmapApp(str(a))
    app._reader = None  # simulate no primary open
    cont = app._build_diff_panes()
    # The container id should be diff-empty in empty state
    assert getattr(cont, "id", None) == "diff-empty"
