from __future__ import annotations

from pathlib import Path

import pytest

textual = pytest.importorskip("textual")
from hexmap.app import HexmapApp  # noqa: E402
from hexmap.widgets.hex_view import HexView  # noqa: E402


def test_explore_panes_construct(tmp_path: Path) -> None:
    # Prepare a small file
    p = tmp_path / "small.bin"
    p.write_bytes(bytes(range(128)))
    app = HexmapApp(str(p))

    # Build panes without running the app
    app._reader = None  # ensure compose opens it
    # Access helper to build explore panes
    # First, we need a reader; let compose set it up
    # Simulate compose by calling it to set _reader and hex_view
    gen = app.compose()
    list(gen)  # exhaust yields to construct widgets

    app._build_explore_panes()
    # Ensure widgets exist
    assert isinstance(app.hex_view, HexView)
    assert app._schema is not None
    assert app._output is not None


def test_schema_apply_smoke(tmp_path: Path) -> None:
    _ = textual  # ensure dependency present
    p = tmp_path / "small.bin"
    p.write_bytes(bytes(range(64)))
    app = HexmapApp(str(p))
    gen = app.compose()
    list(gen)
    app._build_explore_panes()
    assert app._schema is not None
    app._schema.load_text(
        """
endian: little
fields:
  - name: head
    offset: 0
    type: bytes
    length: 4
"""
    )
    # Should not crash
    app.action_apply_schema()
