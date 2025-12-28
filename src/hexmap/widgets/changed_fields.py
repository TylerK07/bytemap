from __future__ import annotations

from contextlib import suppress

from rich.text import Text
from textual.widgets import Tree

from hexmap.ui.palette import PALETTE


class ChangedFieldsPanel(Tree[tuple[str, int, int] | None]):
    """List of changed fields; selecting jumps to field and highlights it.

    Node data: (path, offset, length)
    """

    def __init__(self) -> None:
        super().__init__("Changed fields")
        self._items: list[tuple[str, int, int, int]] = []  # (path, offset, length, changed_bytes)

    def set_items(self, items: list[tuple[str, int, int, int]]) -> None:
        # items should be sorted by offset
        self._items = items
        for ch in list(self.root.children):
            ch.remove()
        self.root.set_label("Changed fields")
        for (path, off, ln, cbytes) in self._items:
            label = Text()
            label.append(path, style=PALETTE.parsed_name)
            label.append(" ", style=PALETTE.parsed_punct)
            label.append(f"@0x{off:08X}", style=PALETTE.parsed_offset)
            label.append(" ", style=PALETTE.parsed_punct)
            label.append(f"({cbytes} bytes)", style=PALETTE.parsed_type)
            self.root.add_leaf(label, (path, off, ln))
        with suppress(Exception):
            self.root.expand()
        self.refresh(layout=True)

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:  # type: ignore[override]
        data = event.node.data
        if not data:
            return
        path, off, ln = data
        # Ask app to navigate to field path
        if hasattr(self.app, "diff_goto_field"):
            self.app.diff_goto_field(path, off, ln)  # type: ignore[attr-defined]

