from __future__ import annotations

import pytest

textual = pytest.importorskip("textual")
from hexmap.core.parse import ParsedNode  # noqa: E402
from hexmap.widgets.output_panel import OutputPanel  # noqa: E402


def make_leaf(path: str, offset: int, typ: str, value, length: int = 1) -> ParsedNode:
    return ParsedNode(
        path=path,
        offset=offset,
        length=length,
        type=typ,
        value=value,
        error=None,
        children=None,
    )


def test_struct_summary_basic() -> None:
    # Build a simple struct node with two primitive children
    leaf1 = make_leaf("player.hp", 0x20, "u16", 12, 2)
    leaf2 = make_leaf("player.mp", 0x22, "u16", 7, 2)
    struct = ParsedNode(
        path="player",
        offset=0x20,
        length=4,
        type="struct",
        value=None,
        error=None,
        children=[leaf1, leaf2],
    )
    panel = OutputPanel()
    summary = panel._struct_summary(struct)
    assert "hp: 12" in summary and "mp: 7" in summary


def test_array_item_summary_uses_first_leaves() -> None:
    leaf1 = make_leaf("items[0].id", 0x10, "u8", 84, 1)
    leaf2 = make_leaf("items[0].qty", 0x11, "u8", 101, 1)
    item = ParsedNode(
        path="items[0]",
        offset=0x10,
        length=2,
        type="struct",
        value=None,
        error=None,
        children=[leaf1, leaf2],
    )
    panel = OutputPanel()
    summary = panel._struct_summary(item)
    assert "id: 84" in summary and "qty: 101" in summary
