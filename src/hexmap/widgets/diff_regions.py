from __future__ import annotations

from contextlib import suppress

from rich.text import Text
from textual.widgets import Tree

from hexmap.ui.palette import PALETTE


class DiffRegionsPanel(Tree[tuple[int, int] | None]):
    """List of changed regions; selecting jumps cursor in HexView.

    Node data is (start, length) or None for headers.
    """

    DEFAULT_TOP_N = 25
    GAP_THRESHOLD = 16

    BINDINGS = [
        ("a", "toggle_all", "All/Top"),
        ("g", "toggle_grouped", "Group"),
    ]

    def __init__(self) -> None:
        super().__init__("Changed regions")
        self._all_regions: list[tuple[int, int]] = []
        self._visible_regions: list[tuple[int, int]] = []
        # (start, span, changed, count, density)
        self._clusters: list[tuple[int, int, int, int, float]] = []
        self._index_by_node: dict[any, int] = {}
        self._show_all = False
        self._grouped = False
        self._top_n = self.DEFAULT_TOP_N

    def set_regions(self, regions: list[tuple[int, int]]) -> None:
        self._all_regions = [(s, ln) for (s, ln) in regions if ln > 0]
        self._rebuild()

    def action_toggle_all(self) -> None:  # type: ignore[override]
        self._show_all = not self._show_all
        self._rebuild()

    def action_toggle_grouped(self) -> None:  # type: ignore[override]
        self._grouped = not self._grouped
        self._rebuild()

    # Helpers
    def _sort_regions(self, regs: list[tuple[int, int]]) -> list[tuple[int, int]]:
        return sorted(regs, key=lambda t: (-t[1], t[0]))

    def _cluster(self, regs: list[tuple[int, int]]) -> list[tuple[int, int, int, int, float]]:
        if not regs:
            return []
        regs = sorted(regs, key=lambda t: t[0])
        clusters: list[tuple[int, int, int, int, float]] = []
        cur_start = regs[0][0]
        cur_end = regs[0][0] + regs[0][1]
        cur_changed = regs[0][1]
        cur_count = 1
        for (s, ln) in regs[1:]:
            if s <= cur_end + self.GAP_THRESHOLD:
                cur_end = max(cur_end, s + ln)
                cur_changed += ln
                cur_count += 1
            else:
                span = cur_end - cur_start
                density = (cur_changed / span) if span > 0 else 0.0
                clusters.append((cur_start, span, cur_changed, cur_count, density))
                cur_start = s
                cur_end = s + ln
                cur_changed = ln
                cur_count = 1
        span = cur_end - cur_start
        density = (cur_changed / span) if span > 0 else 0.0
        clusters.append((cur_start, span, cur_changed, cur_count, density))
        # Sort clusters by changed desc, then start
        clusters.sort(key=lambda c: (-c[2], c[0]))
        return clusters

    def _header_text(self, total: int, mode: str) -> str:
        if self._show_all:
            return f"{mode} (showing all {total}) — press a to show top {self._top_n}"
        else:
            shown = min(self._top_n, total)
            return f"{mode} (showing top {shown} of {total}) — press a to show all"

    def _rebuild(self) -> None:
        # Clear
        for ch in list(self.root.children):
            ch.remove()
        self._index_by_node.clear()
        if not self._grouped:
            regs = self._sort_regions(self._all_regions)
            total = len(regs)
            if not self._show_all:
                regs = regs[: self._top_n]
            self._visible_regions = regs
            self.root.set_label(self._header_text(total, "Changed regions"))
            for i, (s, ln) in enumerate(regs):
                label = Text()
                label.append(f"[0x{s:08X}–0x{s+ln-1:08X}] ", style=PALETTE.parsed_value)
                label.append(f"{ln} ", style=PALETTE.parsed_value)
                label.append("byte" if ln == 1 else "bytes", style=PALETTE.parsed_punct)
                node = self.root.add_leaf(label, (s, ln))
                self._index_by_node[node] = i
            # Notify app of visible regions
            if hasattr(self.app, "diff_regions_updated"):
                self.app.diff_regions_updated(self._visible_regions)  # type: ignore[attr-defined]
        else:
            clusters = self._cluster(self._all_regions)
            total = len(clusters)
            if not self._show_all:
                clusters = clusters[: self._top_n]
            self._clusters = clusters
            self.root.set_label(self._header_text(total, "Clusters"))
            for i, (start, span, changed, count, density) in enumerate(clusters):
                label = Text()
                label.append(f"[0x{start:08X}–0x{start+span-1:08X}] ", style=PALETTE.parsed_value)
                label.append(f"regions={count} ", style=PALETTE.parsed_type)
                label.append(f"changed={changed} ", style=PALETTE.parsed_value)
                label.append(f"span={span} ", style=PALETTE.parsed_type)
                label.append(f"density={density:.0%}", style=PALETTE.parsed_type)
                node = self.root.add_leaf(label, (start, span))
                self._index_by_node[node] = i
            # Notify app with cluster spans
            if hasattr(self.app, "diff_regions_updated"):
                self.app.diff_regions_updated([(s, ln) for (s, ln, _c, _n, _d) in clusters])  # type: ignore[attr-defined]
        with suppress(Exception):
            self.root.expand()
        self.refresh(layout=True)

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:  # type: ignore[override]
        data = event.node.data
        if (
            data
            and isinstance(data, tuple)
            and len(data) >= 2
            and hasattr(self.app, "diff_goto_region")
        ):
            start = int(data[0])
            ln = int(data[1])
            try:
                idx = self._index_by_node.get(event.node, 0)
            except Exception:
                idx = 0
            self.app.diff_goto_region(idx, start, ln)  # type: ignore[attr-defined]
