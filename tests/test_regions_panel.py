from __future__ import annotations

import pytest

pytest.importorskip("textual")
pytest.importorskip("rich")

from hexmap.widgets.diff_regions import DiffRegionsPanel


def test_topn_sorting_and_limits() -> None:
    pytest.importorskip("textual")
    panel = DiffRegionsPanel()
    # lengths: 50, 10, 30
    regs = [(0x10, 10), (0x20, 50), (0x30, 30)]
    panel.set_regions(regs)
    # By default top N=25, but we only have 3; ensure sort largest first
    vis = panel._visible_regions
    assert vis[0] == (0x20, 50)
    assert vis[1] == (0x30, 30)


def test_grouping_behavior_and_density() -> None:
    pytest.importorskip("textual")
    panel = DiffRegionsPanel()
    # Regions close enough to cluster (gap 16)
    regs = [(0x00, 8), (0x10, 8), (0x21, 8)]  # 0x00..0x17 and 0x21..0x28
    panel.set_regions(regs)
    panel.action_toggle_grouped()
    clusters = panel._clusters
    assert len(clusters) >= 1
    (start, span, changed, count, density) = clusters[0]
    assert start == 0x00
    assert count >= 2
    assert changed > 0 and span >= changed
    assert 0.0 <= density <= 1.0
