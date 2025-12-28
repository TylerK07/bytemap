from __future__ import annotations

from contextlib import suppress

from rich.text import Text
from textual.widgets import Tree

from hexmap.core.parse import ParsedField, ParsedNode
from hexmap.ui.palette import PALETTE


class OutputPanel(Tree[ParsedNode | None]):
    """Displays parsed fields as a collapsible tree and errors when present."""

    def __init__(self) -> None:
        super().__init__("Output")
        self._errors: list[str] = []
        self._unmapped: list[tuple[int, int]] = []
        self._show_metadata: bool = True
        self._last_nodes: list[ParsedNode] | None = None
        # Diff markers support
        self._diff_markers: bool = False
        self._changed_map: dict[str, dict] = {}
        self._changed_paths: set[str] = set()
        self._last_selected_node = None  # track current node for key handling

    BINDINGS = [("m", "toggle_metadata", "Toggle metadata")]
    ALIGN_COL = 48  # wider to reduce horizontal scrolling; metadata starts here

    def set_errors(self, errors: list[str]) -> None:
        self._errors = errors
        self.root.set_label(Text("Schema errors", style="bold red"))
        # Clear children (TreeNode may not have clear() in this Textual version)
        for child in list(self.root.children):
            child.remove()
        for e in errors:
            self.root.add_leaf(Text(e, style="red"), None)
        # Show errors immediately; open root by default
        with suppress(Exception):
            self.root.expand()
        self.refresh(layout=True)

    def set_fields(self, fields: list[ParsedField]) -> None:
        # Back-compat flattened list view
        self._errors = []
        self.root.set_label("Parsed fields")
        for child in list(self.root.children):
            child.remove()
        for pf in fields:
            label = (
                f"{pf.name} @0x{pf.offset:08X} {pf.type}[{pf.length}] — {pf.error}"
                if pf.error
                else f"{pf.name} @0x{pf.offset:08X} {pf.type}[{pf.length}] = {pf.value}"
            )
            self.root.add_leaf(label, None)
        with suppress(Exception):
            self.root.expand()
        self.refresh(layout=True)

    def set_tree(self, nodes: list[ParsedNode]) -> None:
        self._errors = []
        self.root.set_label("Parsed structure")
        expanded = self._collect_expanded()
        for child in list(self.root.children):
            child.remove()
        # Add Unmapped Regions section first if present
        if self._unmapped:
            self._add_unmapped_section(self.root)
        # Build a mapping of path -> node while creating nodes
        self._node_by_path: dict[str, any] = {}
        for n in nodes:
            self._add_node_rec(self.root, n, expanded)
        # Open root by default
        with suppress(Exception):
            self.root.expand()
        self.refresh(layout=True)
        self._last_nodes = nodes

    def _add_node_rec(self, parent, n: ParsedNode, expanded: set[str] | None = None) -> None:  # type: ignore[no-untyped-def]
        label = self._format_label(n, self._show_metadata)
        if n.children:
            node = parent.add(label, n)
            self._node_by_path[n.path] = node
            for c in n.children:
                self._add_node_rec(node, c, expanded)
            # Restore expansion state if previously expanded
            if expanded and n.path in expanded:
                with suppress(Exception):
                    node.expand()
        else:
            ln = parent.add_leaf(label, n)
            self._node_by_path[n.path] = ln

    def _collect_expanded(self) -> set[str]:
        paths: set[str] = set()

        def visit(node) -> None:  # type: ignore[no-untyped-def]
            try:
                is_expanded = bool(getattr(node, "expanded", False))
            except Exception:
                is_expanded = False
            data = getattr(node, "data", None)
            if is_expanded and isinstance(data, ParsedNode) and data.path:
                paths.add(data.path)
            for ch in list(getattr(node, "children", [])):
                visit(ch)

        try:
            visit(self.root)
        except Exception:
            return set()
        return paths

    def set_unmapped(self, regions: list[tuple[int, int]]) -> None:
        self._unmapped = [(s, ln) for s, ln in regions if ln > 0]
        # If tree already shown, rebuild label list quickly
        # Let set_tree handle the heavy lifting on next apply

    def _add_unmapped_section(self, parent) -> None:  # type: ignore[no-untyped-def]
        if not self._unmapped:
            return
        sect = parent.add(Text("Unmapped Regions", style=PALETTE.parsed_name), None)
        for s, ln in self._unmapped:
            label = Text()
            label.append(f"[0x{s:08X} – 0x{s+ln-1:08X}]", style=PALETTE.parsed_value)
            label.append(" ", style=PALETTE.parsed_punct)
            label.append(f"({ln} bytes)", style=PALETTE.parsed_type)
            # Tag nodes so selection moves cursor
            sect.add_leaf(label, ("unmapped", s, ln))

    def _format_label(self, n: ParsedNode, show_meta: bool) -> Text:
        name = self._display_name(n)
        t = Text()
        # Diff marker: ● if node (or any descendant) changed
        if self._diff_markers and (
            (n.children and n.path in self._changed_paths)
            or (
                not n.children
                and n.path in self._changed_map
                and self._changed_map[n.path].get("changed")
            )
        ):
            t.append("● ", style=PALETTE.accent)
        name_style = PALETTE.parsed_index if name.startswith("[") else PALETTE.parsed_name
        t.append(name, style=name_style)
        if n.children:
            t.append(": ", style=PALETTE.parsed_punct)
            if n.type == "struct":
                preview = self._struct_summary(n)
                t.append(preview if preview else "{ … }", style=PALETTE.parsed_value)
            elif n.type == "array":
                cnt = len(n.children or [])
                t.append(f"[ {cnt} items ]", style=PALETTE.parsed_value)
            else:
                t.append("{ … }", style=PALETTE.parsed_value)
            if show_meta:
                meta = self._meta_suffix(n)
                if meta:
                    # pad to alignment column before metadata
                    pad = max(1, self.ALIGN_COL - t.cell_len)
                    t.append(" " * pad, style=PALETTE.parsed_punct)
                    t.append(meta, style=PALETTE.parsed_offset)
            return t
        # leaf
        t.append(": ", style=PALETTE.parsed_punct)
        if n.error:
            t.append(n.error, style=PALETTE.parsed_error)
        else:
            # Use formatted_value if available (e.g., date strings), otherwise raw value
            if n.formatted_value:
                t.append(n.formatted_value, style=PALETTE.parsed_value)
            else:
                val = n.value
                vs = val.hex(" ").upper() if isinstance(val, bytes) else str(val)
                t.append(vs, style=PALETTE.parsed_value)
        if show_meta:
            meta = self._meta_suffix(n)
            if meta:
                pad = max(1, self.ALIGN_COL - t.cell_len)
                t.append(" " * pad, style=PALETTE.parsed_punct)
                t.append(meta, style=PALETTE.parsed_offset)
        return t

    def _display_name(self, n: ParsedNode) -> str:
        path = n.path
        if path.endswith("]"):
            lb = path.rfind("[")
            if lb != -1:
                return path[lb:]
        if "." in path:
            return path.split(".")[-1]
        return path

    def _meta_suffix(self, n: ParsedNode) -> str:
        parts: list[str] = [f"@0x{n.offset:08X}"]
        if n.type == "bytes" and n.length is not None:
            parts.append(f"bytes[{n.length}]")
        elif n.type not in ("struct", "array"):
            parts.append(n.type)
        elif n.length is not None:
            parts.append(f"({n.length} bytes)")

        # Show endian indicator for overrides (field, type, parent)
        # Don't show for root or default to reduce clutter
        if n.effective_endian and n.endian_source in ("field", "type", "parent"):
            endian_short = "LE" if n.effective_endian == "little" else "BE"
            source_indicator = {
                "field": "↓",  # Field override
                "type": "T",   # Type definition
                "parent": "↑", # Parent container
            }.get(n.endian_source, "")
            parts.append(f"{endian_short}{source_indicator}")

        return " ".join(parts)

    def _struct_summary(self, n: ParsedNode, limit: int = 3) -> str:
        res: list[str] = []
        def visit(node: ParsedNode) -> None:
            nonlocal res
            if len(res) >= limit:
                return
            if node.children:
                for ch in node.children:
                    visit(ch)
                    if len(res) >= limit:
                        return
            else:
                if node.error:
                    return
                val = node.value
                vs = val.hex(" ").upper() if isinstance(val, bytes) else str(val)
                name = self._display_name(node)
                res.append(f"{name}: {vs}")
        visit(n)
        return "{ " + ", ".join(res) + " }" if res else "{ … }"

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:  # type: ignore[override]
        # Remember last selected node for Enter key toggling
        self._last_selected_node = event.node
        node_data = event.node.data
        if (
            node_data
            and isinstance(node_data, ParsedNode)
            and node_data.offset is not None
            and hasattr(self.app, "hex_view")
            and self.app.hex_view is not None  # type: ignore[attr-defined]
        ):
            # Only broadcast to HexView when OutputPanel has focus (user-driven)
            if self.has_focus:
                # Avoid redundant cursor moves that can trigger feedback loops
                if getattr(self.app.hex_view, "cursor_offset", None) != node_data.offset:  # type: ignore[attr-defined]
                    self.app.hex_view.set_cursor(node_data.offset)  # type: ignore[attr-defined]
                hint = (
                    f"{node_data.path} = {node_data.value} "
                    f"@0x{node_data.offset:08X} {node_data.type}"
                )
                if hasattr(self.app, "set_status_hint"):
                    self.app.set_status_hint(hint)  # type: ignore[attr-defined]
            # Set selection spans (aggregate spans for any node)
            spans = self._node_spans(node_data)
            if hasattr(self.app, "set_selected_spans"):
                self.app.set_selected_spans(spans, node_data.path)  # type: ignore[attr-defined]
        elif (
            isinstance(node_data, tuple)
            and node_data
            and node_data[0] == "unmapped"
            and self.has_focus
            and hasattr(self.app, "hex_view")
            and self.app.hex_view is not None  # type: ignore[attr-defined]
        ):
            start = int(node_data[1])
            ln = int(node_data[2]) if len(node_data) > 2 else 0
            self.app.hex_view.set_cursor(start)  # type: ignore[attr-defined]
            if hasattr(self.app, "set_status_hint"):
                self.app.set_status_hint(f"unmapped @0x{start:08X}")  # type: ignore[attr-defined]
                if hasattr(self.app, "set_selected_spans"):
                    self.app.set_selected_spans([(start, ln)], "unmapped")  # type: ignore[attr-defined]

    # Allow Textual's default key handling (Enter toggles expansion) and rely
    # on focus-gated broadcasting in on_tree_node_selected to avoid feedback loops.

    def action_toggle_metadata(self) -> None:
        self._show_metadata = not self._show_metadata
        if self._last_nodes is not None:
            self.set_tree(self._last_nodes)

    # Diff markers API
    def set_change_map(self, changes: dict[str, dict]) -> None:
        self._changed_map = changes or {}
        # Precompute changed paths and their ancestors for quick lookup
        paths: set[str] = set()
        for p, info in self._changed_map.items():
            if info.get("changed"):
                paths.add(p)
                # include ancestors like a.b.c -> a.b, a
                cur = p
                while "." in cur:
                    cur = cur.rsplit(".", 1)[0]
                    paths.add(cur)
        self._changed_paths = paths
        if self._last_nodes is not None:
            self.set_tree(self._last_nodes)

    def show_diff_markers(self, flag: bool) -> None:
        self._diff_markers = bool(flag)
        if self._last_nodes is not None:
            self.set_tree(self._last_nodes)

    # External API: select a node by path
    def select_path(self, path: str) -> None:
        node = getattr(self, "_node_by_path", {}).get(path)
        if node is not None:
            from contextlib import suppress
            # Expand ancestors top-down to expose the node in the tree
            try:
                chain = []
                cur = node
                while cur is not None:
                    chain.append(cur)
                    cur = getattr(cur, "parent", None)
                for anc in reversed(chain):
                    with suppress(Exception):
                        anc.expand()
            except Exception:
                pass
            # Select the node; defer slightly so expansion renders first
            def _do_select(n=node) -> None:
                with suppress(Exception):
                    self.select_node(n)
            try:
                self.set_timer(0.01, _do_select)
            except Exception:
                _do_select()

    # Compute aggregate spans for a node (collect leaf spans)
    def _node_spans(self, n: ParsedNode) -> list[tuple[int, int]]:
        if not n.children:
            return [(n.offset, n.length or 0)]
        spans: list[tuple[int, int]] = []
        stack = list(n.children or [])
        while stack:
            cur = stack.pop(0)
            if cur.children:
                stack.extend(cur.children)
            else:
                if cur.length and cur.length > 0:
                    spans.append((cur.offset, cur.length))
        return spans
