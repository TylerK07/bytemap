from __future__ import annotations

import pytest

pytest.importorskip("rich")
from hexmap.widgets.byte_strip import ByteStrip


def test_style_roles_selection_and_continuation() -> None:
    bs = ByteStrip()
    # Pretend selection length L=3
    L = 3
    roles = [bs._style_role_for_index(i, L) for i in range(10)]
    # First L are selected
    assert roles[:3].count(roles[0]) == 3  # same selected style
    # Next blocks alternate pattern_a / pattern_b in size L
    blk_a = roles[3:6]
    blk_b = roles[6:9]
    assert len(set(blk_a)) == 1 and len(set(blk_b)) == 1 and blk_a[0] != blk_b[0]


def test_ascii_window_larger_than_hex() -> None:
    bs = ByteStrip()
    # Fake widget width large enough
    bs.size = type("S", (), {"width": 120, "height": 6})()  # type: ignore
    W_hex, W_ascii = bs._compute_windows()
    assert W_ascii >= W_hex * 2 or W_ascii == 128
