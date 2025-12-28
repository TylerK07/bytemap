from __future__ import annotations

from pathlib import Path

import pytest

textual = pytest.importorskip("textual")


def test_app_constructs(tmp_path: Path) -> None:
    # Create a tiny fixture file
    p = tmp_path / "tiny.bin"
    p.write_bytes(bytes(range(64)))

    # Import here to avoid E402 when textual is absent
    from hexmap.app import HexmapApp

    app = HexmapApp(str(p))
    # Do not run the app; just ensure construction doesn't crash
    assert app is not None
