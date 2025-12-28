from __future__ import annotations

import os
from pathlib import Path

from rich.text import Text
from textual.widgets import Tree

from hexmap.ui.palette import PALETTE


class FileBrowser(Tree[Path | None]):
    """Simple single-select file browser for Diff tab.

    Lists sibling files of the primary file's directory. Directories are
    filtered out. Selecting a file triggers a diff against the primary.
    """

    def __init__(self, primary_path: str | None) -> None:
        super().__init__("Files")
        self._primary_path = Path(primary_path) if primary_path else None
        self._dir = self._primary_path.parent if self._primary_path else None
        self._paths: list[Path] = []
        self._selected: set[Path] = set()

    @staticmethod
    def list_files(dir_path: Path) -> list[Path]:
        try:
            entries = [dir_path / name for name in os.listdir(dir_path)]
        except Exception:
            return []
        files = [p for p in entries if p.is_file()]
        files.sort(key=lambda p: p.name.lower())
        return files

    def rebuild(self) -> None:
        for ch in list(self.root.children):
            ch.remove()
        if not self._dir:
            self.root.set_label("Files (no primary)")
            return
        self._paths = self.list_files(self._dir)
        self.root.set_label(Text(f"{self._dir}", style=PALETTE.parsed_offset))
        for p in self._paths:
            label = Text()
            if self._primary_path and p == self._primary_path:
                label.append("★ ", style=PALETTE.accent_dim)
            if p in self._selected:
                label.append("✓ ", style=PALETTE.accent)
            label.append(p.name, style=PALETTE.parsed_name)
            self.root.add_leaf(label, p)
        from contextlib import suppress
        with suppress(Exception):
            self.root.expand()
        # Trigger layout/render
        from contextlib import suppress
        with suppress(Exception):
            super().refresh(layout=True)

    def on_mount(self) -> None:  # type: ignore[override]
        self.rebuild()

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:  # type: ignore[override]
        data = event.node.data
        if data and isinstance(data, Path) and hasattr(self.app, "set_diff_target"):
            # Enter selects a single target (convenience)
            self._selected = {data}
            # Remember last node
            self._last_node = event.node  # type: ignore[attr-defined]
            self.rebuild()
            if hasattr(self.app, "set_diff_targets"):
                self.app.set_diff_targets([str(p) for p in self._selected])  # type: ignore[attr-defined]
            else:
                self.app.set_diff_target(str(data))  # type: ignore[attr-defined]

    def on_key(self, event) -> None:  # type: ignore[override]
        key = getattr(event, "key", "") or ""
        # Normalize space key across Textual versions
        is_space = (
            key.lower() == "space"
            or (getattr(event, "character", None) == " ")
            or (key == " ")
        )
        if is_space:
            node = (
                getattr(self, "cursor_node", None)
                or getattr(self, "highlighted_node", None)
                or getattr(self, "_last_node", None)
            )
            if node is not None and isinstance(getattr(node, "data", None), Path):
                p = node.data
                if self._primary_path and p == self._primary_path:
                    event.prevent_default()
                    return
                if p in self._selected:
                    self._selected.remove(p)
                else:
                    self._selected.add(p)
                self.rebuild()
                if hasattr(self.app, "set_diff_targets"):
                    self.app.set_diff_targets([str(x) for x in self._selected])  # type: ignore[attr-defined]
                from contextlib import suppress
                with suppress(Exception):
                    event.stop()
                event.prevent_default()
                return
        if key == "escape" and self._selected:
            self._selected.clear()
            self.rebuild()
            if hasattr(self.app, "set_diff_targets"):
                self.app.set_diff_targets([])  # type: ignore[attr-defined]
            event.prevent_default()
            return

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:  # type: ignore[override]
        # Track last highlighted node for robust toggling
        self._last_node = event.node  # type: ignore[attr-defined]
