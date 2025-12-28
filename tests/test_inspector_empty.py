from __future__ import annotations

import pytest


def test_inspector_empty_render_returns_renderable() -> None:
    pytest.importorskip("textual")
    from hexmap.widgets.inspector import Inspector

    insp = Inspector()
    # Calling render should yield a Rich Text (not None)
    r = insp.render()
    assert r is not None
