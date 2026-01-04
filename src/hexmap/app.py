from __future__ import annotations

import os

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    OptionList,
    Static,
    TabbedContent,
    TabPane,
)

from hexmap.core.coverage import compute_coverage
from hexmap.core.diff import compute_diff_spans, diff_stats
from hexmap.core.frequency import compute_frequency_map
from hexmap.core.intersect import intersect_spans
from hexmap.core.io import PagedReader
from hexmap.core.parse import apply_schema_tree
from hexmap.core.schema import SchemaError, load_schema
from hexmap.core.schema_edit import (
    upsert_array_field,
    upsert_ascii_type_and_field,
    upsert_bytes_field,
    upsert_bytes_type_and_field,
    upsert_chunk_field,
    upsert_cstring_type_and_field,
    upsert_date_field,
    upsert_numeric_field,
    upsert_string_field,
)
from hexmap.core.schema_library import (
    SchemaEntry,
    create_new_schema,
    delete_user_schema,
    discover_schemas,
    duplicate_to_user,
    search_schemas,
)
from hexmap.core.search import find_bytes
from hexmap.core.search_lens import (
    SearchHit,
    SearchState,
    search_date_ascii_text,
    search_date_days_since_1970,
    search_date_days_since_1980,
    search_date_dos_date,
    search_date_dos_datetime,
    search_date_filetime,
    search_date_ftm_packed,
    search_date_ole_date,
    search_date_unix_ms,
    search_date_unix_s,
)
from hexmap.core.spans import Span, SpanIndex, type_group
from hexmap.widgets.changed_fields import ChangedFieldsPanel
from hexmap.widgets.chunking import ChunkingWidget
from hexmap.widgets.yaml_chunking import YAMLChunkingWidget
from hexmap.widgets.compare_strings import CompareStringsModal
from hexmap.widgets.diff_regions import DiffRegionsPanel
from hexmap.widgets.file_browser import FileBrowser
from hexmap.widgets.file_overview import FileOverview
from hexmap.widgets.hex_view import HexView
from hexmap.widgets.inspector import Inspector
from hexmap.widgets.output_panel import OutputPanel
from hexmap.widgets.schema_editor import SchemaEditor
from hexmap.widgets.search_banner import SearchBanner
from hexmap.widgets.search_panel import SearchPanel


class HexmapApp(App):
    """Textual application shell for Hexmap."""

    CSS_PATH = "ui/theme.tcss"

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("?", "open_help", "Help"),
        ("ctrl+tab", "switch_next_tab", "Next Tab"),
        ("ctrl+shift+tab", "switch_previous_tab", "Prev Tab"),
        ("1", "tab_1", "Explore"),
        ("2", "tab_2", "Diff"),
        ("d", "tab_2", "Diff"),
        ("3", "tab_3", "Chunking"),
        ("tab", "focus_next", "Next Focus"),
        ("shift+tab", "focus_previous", "Prev Focus"),
        ("i", "toggle_inspector", "Inspector"),
        ("a", "add_chunk_to_schema", "Add Chunk"),
        ("I", "toggle_inspector_mode", "Inspector Mode"),
        ("ctrl+o", "open_schema_path", "Open Schema"),
        ("ctrl+l", "open_schema_library", "Schema Library"),
        ("ctrl+s", "save_schema", "Save"),
        ("ctrl+S", "save_schema_as", "Save As"),
        ("ctrl+y", "copy_schema", "Copy Schema"),
        ("ctrl+enter", "apply_schema", "Apply Schema"),
        ("ctrl+r", "apply_schema", "Re-apply Schema"),
        ("ctrl+d", "open_diff_paths", "Open Diff"),
        ("]", "next_diff_region", "Next Change"),
        ("[", "prev_diff_region", "Prev Change"),
        ("c", "diff_toggle_panel", "Toggle Changes"),
        ("n", "search_next_hit", "Next Search Hit"),
        ("p", "search_prev_hit", "Prev Search Hit"),
        ("escape", "cancel_search", "Cancel Search"),
    ]

    def __init__(self, path: str) -> None:
        super().__init__()
        self._path = path
        self._reader: PagedReader | None = None
        self.hex_view: HexView | None = None
        self.title = f"hexmap — {os.path.basename(path)}"
        self.status = Static(id="status")
        self._pending_g = False
        self._last_search: tuple[str, bytes] | None = None  # (mode, needle)
        self._status_hint: str = ""
        self._schema: SchemaEditor | None = None
        self._output: OutputPanel | None = None
        self._pane_viz: Container | None = None
        self._pane_schema: Container | None = None
        self._pane_output: Container | None = None
        self._schema_apply_timer = None
        self._last_schema_text: str | None = None
        self._mapped_percent: float = 0.0
        self._schema_path: str | None = None  # Track current schema file path
        # Diff state
        # Primary (already open in Explore)
        self._primary_file: str | None = path
        # Diff targets state (snapshot set)
        self._diff_targets: list[str] = []
        self._diff_readers: list[PagedReader] = []
        self._diff_hex: HexView | None = None
        self._diff_regions_panel: DiffRegionsPanel | None = None
        self._diff_changed_panel: ChangedFieldsPanel | None = None
        self._diff_output: OutputPanel | None = None
        self._diff_overview: FileOverview | None = None
        self._diff_browser: FileBrowser | None = None
        self._diff_regions: list[tuple[int, int]] = []
        self._diff_index: int = -1
        self._diff_show_changed_fields: bool = False
        # Search lens state
        self._search_state = SearchState()
        self._search_panel: SearchPanel | None = None
        self._search_banner: SearchBanner | None = None
        # Chunking state
        self.chunking_widget: ChunkingWidget | None = None
        self.yaml_chunking_widget: YAMLChunkingWidget | None = None

    def compose(self) -> ComposeResult:  # noqa: D401 - Textual API
        # Delay opening until compose to give clear UI errors
        try:
            self._reader = PagedReader(self._path)
        except FileNotFoundError:
            yield Static(f"Error: file not found: {self._path}")
            return

        self.hex_view = HexView(self._reader)
        explore = self._build_explore_panes()
        self.yaml_chunking_widget = YAMLChunkingWidget(self._reader)
        yield Header(show_clock=False, id="header")
        # Add TabbedContent without positional TabPane args for broader compatibility
        with TabbedContent():
            yield TabPane("Explore", explore, id="tab-explore")
            yield TabPane("Diff", self._build_diff_panes(), id="tab-diff")
            yield TabPane("Chunking", self.yaml_chunking_widget, id="tab-chunking")
        yield self.status
        yield Footer(id="footer")

    def on_mount(self) -> None:
        self.update_status()
        if self.hex_view is not None:
            self.set_focus(self.hex_view)
        if self._schema is not None and not self._schema.text:
            self._schema.load_text(
                """# Schema (YAML)
types:
  leader_name: { type: string, length: 14, encoding: ascii }
  Item:
    type: struct
    fields:
      - { name: id, type: u8 }
      - { name: qty, type: u8 }

fields:
  - name: magic
    type: bytes
    length: 4
  - name: version
    type: u16
  - name: inventory
    type: array of Item  # shorthand
    length: 10
    stride: 2
  - name: leaders
    type: array of leader_name
    length: 3
"""
            )
            # Auto-apply the default schema immediately
            self.schedule_schema_apply(delay=0.1)

    # ---- Actions ----
    def action_cursor_up(self) -> None:
        if self.hex_view is None:
            return
        self.hex_view.move_cursor(-self.hex_view.bytes_per_row)
        self.update_status()

    def action_cursor_down(self) -> None:
        if self.hex_view is None:
            return
        self.hex_view.move_cursor(self.hex_view.bytes_per_row)
        self.update_status()

    def action_cursor_left(self) -> None:
        if self.hex_view is None:
            return
        self.hex_view.move_cursor(-1)
        self.update_status()

    def action_cursor_right(self) -> None:
        if self.hex_view is None:
            return
        self.hex_view.move_cursor(1)
        self.update_status()

    def action_page_up(self) -> None:
        if self.hex_view is None:
            return
        # Calculate cursor's relative position within current viewport
        top_before = self.hex_view.top_offset()
        bpr = self.hex_view.bytes_per_row
        cursor_row_offset = (self.hex_view.cursor_offset - top_before) // bpr
        cursor_col_offset = (self.hex_view.cursor_offset - top_before) % bpr

        # Page up
        self.hex_view.page_by(-1)

        # Move cursor to maintain relative position in new viewport
        top_after = self.hex_view.top_offset()
        new_cursor = top_after + cursor_row_offset * bpr + cursor_col_offset
        self.hex_view.set_cursor(new_cursor)
        self.update_status()

    def action_page_down(self) -> None:
        if self.hex_view is None:
            return
        # Calculate cursor's relative position within current viewport
        top_before = self.hex_view.top_offset()
        bpr = self.hex_view.bytes_per_row
        cursor_row_offset = (self.hex_view.cursor_offset - top_before) // bpr
        cursor_col_offset = (self.hex_view.cursor_offset - top_before) % bpr

        # Page down
        self.hex_view.page_by(1)

        # Move cursor to maintain relative position in new viewport
        top_after = self.hex_view.top_offset()
        new_cursor = top_after + cursor_row_offset * bpr + cursor_col_offset
        self.hex_view.set_cursor(new_cursor)
        self.update_status()

    def action_go_end(self) -> None:
        if self.hex_view is None or self._reader is None:
            return
        if self._reader.size > 0:
            self.hex_view.set_cursor(self._reader.size - 1)
        self.update_status()

    def action_go_start(self) -> None:
        if self.hex_view is None:
            return
        self.hex_view.set_cursor(0)
        self.update_status()

    # App-wide key handling no longer intercepts pane keys; widgets handle their own.

    # ---- Search ----
    def action_open_search(self) -> None:
        self.push_screen(SearchScreen(), self._search_submit)

    def action_search_next(self) -> None:
        if self.hex_view is None or self._reader is None or self._last_search is None:
            return
        mode, needle = self._last_search
        start = min(self._reader.size, self.hex_view.cursor_offset + 1)
        if mode == "bytes":
            found = find_bytes(self._reader, needle, start)
        else:
            found = find_bytes(self._reader, needle, start)
        if found is not None:
            self.hex_view.set_cursor(found)
            self.update_status()
        else:
            self._status_hint = "[no further match]"
            self.update_status()

    def action_open_help(self) -> None:
        self.push_screen(HelpScreen())

    # ---- Compare & Interpret (Strings) ----
    def action_open_compare_strings(self) -> None:
        # Determine invoking hex view (Explore or Diff)
        hv = None
        if isinstance(self.focused, HexView):
            hv = self.focused
        elif self.hex_view is not None:
            hv = self.hex_view
        if hv is None or self._reader is None:
            return

        # Determine anchor offset: for chunk search, use payload start; else cursor/selection
        anchor_offset = hv.cursor_offset
        sel = None

        # Check if active search is chunk mode with payload span
        if (
            hasattr(self, "_search_state")
            and self._search_state.is_active()
            and self._search_state.mode == "chunk"
        ):
            hit = self._search_state.current_hit()
            if hit and hit.spans:
                # Find payload span
                for span in hit.spans:
                    if span.role == "payload":
                        anchor_offset = span.offset
                        sel = (span.offset, span.length)
                        break

        # If no chunk payload, use first span if available
        if sel is None:
            spans = getattr(hv, "_selected_spans", [])
            if spans:
                s0 = spans[0]
                if s0[1] and s0[1] > 0:
                    sel = (int(s0[0]), int(s0[1]))
                    anchor_offset = s0[0]

        # Column files: baseline + selected snapshots
        files: list[tuple[str, PagedReader, bool]] = []
        files.append((self._primary_file or "", self._reader, True))
        for r, p in zip(self._diff_readers, self._diff_targets, strict=False):
            files.append((p, r, False))
        self.push_screen(CompareStringsModal(files, anchor_offset, sel))

    # Helper invoked by modal
    def commit_string_field(
        self, offset: int, fixed_len: int | None, cmax: int | None, name: str | None
    ) -> bool:
        if self._schema is None:
            return False
        text = self._schema.text or ""
        new_text, _spec = upsert_string_field(
            text,
            offset=int(offset),
            fixed_length=int(fixed_len) if fixed_len else None,
            cstring_max=int(cmax) if cmax else None,
            name=name,
        )
        self._schema.load_text(new_text)
        # Auto-apply so Diff/Explore refresh immediately
        from contextlib import suppress
        with suppress(Exception):
            self.action_apply_schema()
        return True

    def commit_numeric_field(self, offset: int, type_name: str, name: str | None) -> bool:
        if self._schema is None:
            return False
        text = self._schema.text or ""
        new_text, _spec = upsert_numeric_field(
            text,
            offset=int(offset),
            type_name=type_name,
            name=name,
        )
        self._schema.load_text(new_text)
        from contextlib import suppress
        with suppress(Exception):
            self.action_apply_schema()
        return True

    def current_schema_endian(self) -> str:
        # Best-effort: parse endian from YAML, default to little
        try:
            import yaml

            data = yaml.safe_load(self._schema.text or "") or {}
            e = data.get("endian")
            if e in ("little", "big"):
                return e
        except Exception:
            pass
        return "little"

    def commit_bytes_field(self, offset: int, length: int, name: str | None) -> bool:
        if self._schema is None:
            return False
        text = self._schema.text or ""
        new_text, _ = upsert_bytes_field(text, offset=int(offset), length=int(length), name=name)
        self._schema.load_text(new_text)
        from contextlib import suppress
        with suppress(Exception):
            self.action_apply_schema()
        return True

    def commit_array_field(
        self, offset: int, elem_type: str, length: int, name: str | None
    ) -> bool:
        if self._schema is None:
            return False
        text = self._schema.text or ""
        new_text, _ = upsert_array_field(
            text, offset=int(offset), elem_type=elem_type, length=int(length), name=name
        )
        self._schema.load_text(new_text)
        from contextlib import suppress
        with suppress(Exception):
            self.action_apply_schema()
        return True

    def commit_cstring_field(
        self, offset: int, slot_len: int, instances: int, name: str | None
    ) -> bool:
        if self._schema is None:
            return False
        text = self._schema.text or ""
        new_text, _ = upsert_cstring_type_and_field(
            text,
            offset=int(offset),
            slot_len=int(slot_len),
            instances=int(instances),
            name=name,
        )
        self._schema.load_text(new_text)
        from contextlib import suppress
        with suppress(Exception):
            self.action_apply_schema()
        return True


    def commit_ascii_field(
        self, offset: int, slot_len: int, instances: int, name: str | None
    ) -> bool:
        if self._schema is None:
            return False
        text = self._schema.text or ""
        new_text, _ = upsert_ascii_type_and_field(
            text,
            offset=int(offset),
            slot_len=int(slot_len),
            instances=int(instances),
            name=name,
        )
        self._schema.load_text(new_text)
        from contextlib import suppress
        with suppress(Exception):
            self.action_apply_schema()
        return True

    def commit_bytes_array_field(
        self, offset: int, elem_len: int, instances: int, name: str | None
    ) -> bool:
        if self._schema is None:
            return False
        text = self._schema.text or ""
        new_text, _ = upsert_bytes_type_and_field(
            text,
            offset=int(offset),
            elem_len=int(elem_len),
            instances=int(instances),
            name=name,
        )
        self._schema.load_text(new_text)
        from contextlib import suppress
        with suppress(Exception):
            self.action_apply_schema()
        return True

    def commit_date_field(self, offset: int, fmt: str, name: str | None) -> bool:
        if self._schema is None:
            return False
        text = self._schema.text or ""
        new_text, _spec = upsert_date_field(text, offset=int(offset), format=fmt, name=name)
        self._schema.load_text(new_text)
        self.schedule_schema_apply(delay=0.1)
        return True

    def commit_chunk_field(
        self, offset: int, length_type: str, length_includes_header: bool, name: str | None
    ) -> bool:
        if self._schema is None:
            return False
        try:
            text = self._schema.text or ""
            new_text, _spec = upsert_chunk_field(
                text,
                offset=int(offset),
                length_type=length_type,
                length_includes_header=length_includes_header,
                name=name,
            )
            self._schema.load_text(new_text)
            self.schedule_schema_apply(delay=0.1)
            return True
        except Exception as e:
            # Log error but return False for graceful handling
            import sys
            print(f"Error in commit_chunk_field: {e}", file=sys.stderr)
            return False

    def action_add_chunk_to_schema(self) -> None:
        """Add current chunk search hit to schema (key: 'a')."""
        try:
            # Only works when chunk search is active
            if not hasattr(self, "_search_state") or not self._search_state.is_active():
                self.set_status_hint("No active search (use chunk search first)")
                return

            if self._search_state.mode != "chunk":
                self.set_status_hint("Only works in chunk search mode")
                return

            # Get current hit
            hit = self._search_state.current_hit()
            if hit is None or not hit.matches:
                self.set_status_hint("No chunk selected")
                return

            # Extract chunk parameters from hit details
            details = hit.matches[0].details
            # Chunk search stores type as 'type' (e.g., 'u16 BE'), not 'length_type'
            length_type = details.get("type", "u16 LE")
            # For now, default to length_includes_header=False (payload mode)
            # User can edit YAML manually if needed
            length_includes_header = False

            # Get offset (start of length field)
            offset = hit.spans[0].offset if hit.spans else 0

            # Commit to schema
            success = self.commit_chunk_field(offset, length_type, length_includes_header, None)

            if success:
                # Count existing chunks to show progress
                if self._schema and self._schema.text:
                    import yaml
                    try:
                        data = yaml.safe_load(self._schema.text) or {}
                        fields = data.get("fields", [])
                        chunk_count = sum(
                            1 for f in fields if isinstance(f, dict) and f.get("type") == "chunk"
                        )
                        self.set_status_hint(f"Added chunk to schema ({chunk_count} total)")
                    except Exception:
                        self.set_status_hint("Added chunk to schema")
                else:
                    self.set_status_hint("Added chunk to schema")
            else:
                self.set_status_hint("Failed to add chunk (no schema loaded?)")
        except Exception as e:
            self.set_status_hint(f"Error adding chunk: {e}")

    def jump_cursor(self, offset: int) -> None:
        # Move cursor in active hex view (Diff or Explore)
        try:
            if isinstance(self.focused, HexView):
                self.focused.set_cursor(int(offset))
                return
        except Exception:
            pass
        if self.hex_view is not None:
            self.hex_view.set_cursor(int(offset))
        if getattr(self, "_diff_hex", None) is not None:
            from contextlib import suppress
            with suppress(Exception):
                self._diff_hex.set_cursor(int(offset))  # type: ignore[attr-defined]

    # Inspector toggles
    def action_toggle_inspector(self) -> None:
        try:
            if getattr(self, "_inspector", None) is not None:
                self._inspector.toggle_class("hidden")
                if getattr(self, "_insp_sep", None) is not None:
                    self._insp_sep.toggle_class("hidden")
                if getattr(self, "_insp_spacer", None) is not None:
                    self._insp_spacer.toggle_class("hidden")
            if getattr(self, "_diff_inspector", None) is not None:
                self._diff_inspector.toggle_class("hidden")  # type: ignore[attr-defined]
                if getattr(self, "_diff_insp_sep", None) is not None:
                    self._diff_insp_sep.toggle_class("hidden")
                if getattr(self, "_diff_insp_spacer", None) is not None:
                    self._diff_insp_spacer.toggle_class("hidden")
            # If in Diff and inspector just shown, scroll into view
            try:
                if (
                    self.query_one(TabbedContent).active == "tab-diff"  # type: ignore[call-arg]
                    and getattr(self, "_diff_hex_col", None) is not None
                    and hasattr(self._diff_inspector, "has_class")
                    and not self._diff_inspector.has_class("hidden")  # type: ignore[attr-defined]
                ):
                    from contextlib import suppress
                    with suppress(Exception):
                        self._diff_hex_col.scroll_end()  # type: ignore[attr-defined]
            except Exception:
                pass
        except Exception:
            pass

    def action_toggle_inspector_mode(self) -> None:
        try:
            if getattr(self, "_inspector", None) is not None and hasattr(
                self._inspector, "toggle_mode"
            ):
                self._inspector.toggle_mode()
            if getattr(self, "_diff_inspector", None) is not None and hasattr(
                self._diff_inspector, "toggle_mode"
            ):
                self._diff_inspector.toggle_mode()  # type: ignore[attr-defined]
        except Exception:
            pass

    def update_inspector_header(self, scope: str, left: str, mode: str) -> None:
        """Update the separator header bar for Inspector with left/right content."""
        try:
            from rich.text import Text
            if scope == "diff":
                if getattr(self, "_diff_insp_left", None) is not None:
                    self._diff_insp_left.update(left)
                if getattr(self, "_diff_insp_right", None) is not None:
                    self._diff_insp_right.update(Text(mode, justify="right"))
            else:
                if getattr(self, "_insp_left", None) is not None:
                    self._insp_left.update(left)
                if getattr(self, "_insp_right", None) is not None:
                    self._insp_right.update(Text(mode, justify="right"))
        except Exception:
            pass

    # ---- Tabs ----
    def action_switch_next_tab(self) -> None:
        self.query_one(TabbedContent).action_next_tab()

    def action_switch_previous_tab(self) -> None:
        self.query_one(TabbedContent).action_previous_tab()

    def action_tab_1(self) -> None:
        self.query_one(TabbedContent).active = "tab-explore"

    def action_tab_2(self) -> None:
        self.query_one(TabbedContent).active = "tab-diff"
        # Focus file browser first for quick selection
        if self._diff_browser is not None:
            self.set_focus(self._diff_browser)
        elif self._diff_hex is not None:
            self.set_focus(self._diff_hex)
        # Compact hint for Diff in status line
        self.set_status_hint(
            "q Quit  ? Help  1 Explore  2 Diff  i Inspector  I Mode  [/] Prev/Next  c Toggle"
        )

    def action_tab_3(self) -> None:
        self.query_one(TabbedContent).active = "tab-chunking"
        self.set_status_hint(
            "q Quit  ? Help  1 Explore  2 Diff  3 Chunking  Configure framing params and Scan"
        )

    # ---- Status ----
    def update_status(self) -> None:
        if self.hex_view is None or self._reader is None:
            self.status.update(Text("hexmap"))
            return
        top = self.hex_view.top_offset()
        name = os.path.basename(self._path)
        size = self._reader.size
        cur = self.hex_view.cursor_offset
        # Byte under cursor
        b = self._reader.byte_at(cur)
        b_hex = f"{b:02X}" if b is not None else "--"
        # Typed interpretations (if available)
        u16le = self._read_int(cur, 2, "little")
        u16be = self._read_int(cur, 2, "big")
        u32le = self._read_int(cur, 4, "little")
        u32be = self._read_int(cur, 4, "big")
        interp = (
            f"u8={b if b is not None else '--'} "
            f"u16le={u16le if u16le is not None else '--'} "
            f"u16be={u16be if u16be is not None else '--'} "
            f"u32le={u32le if u32le is not None else '--'} "
            f"u32be={u32be if u32be is not None else '--'}"
        )
        if self.hex_view is not None:
            ft = self.hex_view.field_at(cur)
            if ft is not None:
                name, typ = ft
                interp = f"{name}({typ})  " + interp
        hint = self._current_hint()
        status_prefix = (
            f"{name} | {size} bytes | top: 0x{top:08X} | "
            f"cursor: 0x{cur:08X} [{b_hex}]"
        )
        extra = f"  {self._status_hint}" if self._status_hint else ""
        percent = (top / size * 100.0) if size else 0.0
        mapped = f"mapped {self._mapped_percent:5.1f}%"
        self.status.update(
            Text(f"{status_prefix}  {percent:5.1f}%  {mapped}  {hint}{extra}  {interp}")
        )
        # Update overview viewport
        if hasattr(self, "_overview") and self._overview is not None:
            self._overview.update_state(
                file_size=self._reader.size,
                viewport=(top, self.hex_view.visible_rows() * self.hex_view.bytes_per_row),
            )

    def _current_hint(self) -> str:
        # Keep this succinct since Footer shows bindings for focused widget.
        if self.focused is self.hex_view:
            return "(Hex view active)"
        if self.focused is self._schema:
            return "(Schema editor active)"
        return ""

    def on_focus(self, event) -> None:  # type: ignore[override]
        # Update footer when focus changes
        self.update_status()

    # Allow child widgets to update status hints
    def set_status_hint(self, text: str | None) -> None:
        self._status_hint = text or ""
        self.update_status()

    def action_open_goto(self) -> None:
        self.push_screen(GotoScreen(), self._goto_submit)

    def _read_int(self, offset: int, width: int, endian: str) -> int | None:
        if self._reader is None:
            return None
        if offset + width > self._reader.size:
            return None
        data = self._reader.read(offset, width)
        return int.from_bytes(data, endian)

    # ---- Callbacks ----
    def _goto_submit(self, value: str | None) -> None:
        if value is None or self.hex_view is None or self._reader is None:
            return
        offs = self._parse_offset(value)
        if offs is None or offs < 0 or offs >= self._reader.size:
            self._status_hint = "[invalid offset]"
            self.update_status()
            return
        self.hex_view.set_cursor(offs)
        self._status_hint = ""
        self.update_status()

    def _search_submit(self, value: str | None) -> None:
        if value is None or self.hex_view is None or self._reader is None:
            return
        kind, needle = self._parse_search(value)
        if needle is None:
            self._status_hint = "[invalid pattern]"
            self.update_status()
            return
        self._last_search = (kind, needle)
        start = self.hex_view.cursor_offset
        found = find_bytes(self._reader, needle, start)
        if found is not None:
            self.hex_view.set_cursor(found)
            self._status_hint = ""
            self.update_status()
        else:
            self._status_hint = "[no match]"
            self.update_status()

    # ---- Parsers ----
    def _parse_offset(self, text: str) -> int | None:
        s = text.strip().lower()
        try:
            if s.startswith("0x"):
                return int(s, 16)
            return int(s, 10)
        except ValueError:
            return None

    def _parse_search(self, text: str) -> tuple[str, bytes | None]:
        s = text.strip()
        # If it looks like hex bytes (only hex digits and spaces), parse as bytes
        # Allow either 'DEADBEEF' or 'DE AD BE EF' or '0xDEADBEEF'
        s_no_space = s.replace(" ", "").lower()
        if s_no_space.startswith("0x"):
            s_no_space = s_no_space[2:]
        if all(c in "0123456789abcdef" for c in s_no_space) and len(s_no_space) % 2 == 0:
            try:
                return ("bytes", bytes.fromhex(s_no_space))
            except ValueError:
                return ("bytes", None)
        # Try space-separated pairs
        parts = s.split()
        if parts and all(
            len(p) == 2 and all(c in "0123456789abcdefABCDEF" for c in p) for p in parts
        ):
            try:
                return ("bytes", bytes.fromhex("".join(parts)))
            except ValueError:
                return ("bytes", None)
        # Fallback: ASCII
        try:
            return ("ascii", s.encode("utf-8"))
        except Exception:
            return ("ascii", None)

    # ---- Schema loading ----
    def action_open_schema_path(self) -> None:
        self.push_screen(SchemaLoadScreen(), self._schema_load_submit)

    def _schema_load_submit(self, value: str | None) -> None:
        if value is None:
            return
        try:
            with open(value, encoding="utf-8") as fh:
                content = fh.read()
            if self._schema is not None:
                self._schema.load_text(content)
            self._status_hint = "[schema loaded]"
            # Track the schema path for future saves
            self._schema_path = value
            # Auto-apply the loaded schema
            self.schedule_schema_apply(delay=0.1)
        except Exception:
            self._status_hint = "[failed to load schema]"
        self.update_status()

    def action_open_schema_library(self) -> None:
        """Open the Schema Library modal."""
        self.push_screen(SchemaLibraryModal(), self._schema_library_submit)

    def _schema_library_submit(self, result: tuple[str, SchemaEntry] | None) -> None:
        """Handle schema library modal result."""
        if result is None:
            return

        action, schema = result

        if action == "load":
            # Load the selected schema into the editor
            try:
                content = schema.load_content()
                if self._schema is not None:
                    self._schema.load_text(content)
                self._status_hint = f"[schema loaded: {schema.name}]"
                # Track the schema path for future saves
                self._schema_path = str(schema.path)
                # Auto-apply the loaded schema
                self.schedule_schema_apply(delay=0.1)
            except Exception:
                self._status_hint = "[failed to load schema]"
            self.update_status()

        elif action == "edit":
            # Load the schema for editing (typically for new schemas)
            try:
                content = schema.load_content()
                if self._schema is not None:
                    self._schema.load_text(content)
                    # Focus the schema editor
                    if self._schema.can_focus:
                        self.set_focus(self._schema)
                self._status_hint = f"[editing: {schema.name}]"
                self._schema_path = str(schema.path)
                # Auto-apply the loaded schema for immediate preview
                self.schedule_schema_apply(delay=0.1)
            except Exception:
                self._status_hint = "[failed to load schema]"
            self.update_status()

    # ---- Schema save/copy ----
    def action_save_schema(self) -> None:
        """Save schema: if path known, save directly; else open Save As."""
        if self._schema_path is not None:
            self._do_save_schema(self._schema_path)
        else:
            self.action_save_schema_as()

    def action_save_schema_as(self) -> None:
        """Always open Save As dialog."""
        self.push_screen(SaveAsModal(), self._save_as_submit)

    def _save_as_submit(self, value: str | None) -> None:
        if value is None:
            return
        self._do_save_schema(value)

    def _do_save_schema(self, path: str) -> None:
        """Actually write schema to disk."""
        if self._schema is None:
            self._status_hint = "[no schema to save]"
            self.update_status()
            return
        try:
            schema_text = self._schema.text or ""
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(schema_text)
            self._schema_path = path
            self._status_hint = f"[schema saved to {os.path.basename(path)}]"
        except Exception as e:
            self._status_hint = f"[save failed: {e}]"
        self.update_status()

    def action_copy_schema(self) -> None:
        """Copy entire schema YAML to clipboard."""
        if self._schema is None:
            self._status_hint = "[no schema to copy]"
            self.update_status()
            return

        schema_text = self._schema.text or ""
        if not schema_text.strip():
            self._status_hint = "[schema is empty]"
            self.update_status()
            return

        success = self._copy_to_clipboard(schema_text)
        if success:
            self._status_hint = "[schema copied to clipboard]"
        else:
            self._status_hint = "[clipboard copy failed]"
        self.update_status()

    def _copy_to_clipboard(self, text: str) -> bool:
        """Copy text to clipboard with OS fallbacks."""
        import platform
        import subprocess

        # Try Textual clipboard API if available
        try:
            if hasattr(self, "copy_to_clipboard"):
                self.copy_to_clipboard(text)  # type: ignore[attr-defined]
                return True
        except Exception:
            pass

        # OS-specific fallbacks
        system = platform.system()
        try:
            if system == "Darwin":  # macOS
                proc = subprocess.Popen(
                    ["pbcopy"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                proc.communicate(input=text.encode("utf-8"))
                return proc.returncode == 0
            elif system == "Windows":
                proc = subprocess.Popen(
                    ["clip"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                proc.communicate(input=text.encode("utf-8"))
                return proc.returncode == 0
            elif system == "Linux":
                # Try wl-copy (Wayland) first, then xclip (X11)
                for cmd in [["wl-copy"], ["xclip", "-selection", "clipboard"]]:
                    try:
                        proc = subprocess.Popen(
                            cmd,
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                        )
                        proc.communicate(input=text.encode("utf-8"))
                        if proc.returncode == 0:
                            return True
                    except FileNotFoundError:
                        continue
                return False
        except Exception:
            return False

        return False

    # ---- Selection model ----
    def set_selected_span(self, span: tuple[int, int] | None, path: str | None) -> None:
        # Normalize: if span length is missing/<=1, fill from span index when possible
        if (
            span is not None
            and (span[1] is None or span[1] <= 1)
            and hasattr(self, "_span_index")
            and self._span_index is not None
        ):
            sp = self._span_index.find(span[0])
            if sp is not None:
                span = (sp.offset, sp.length)
        self._selected_span = span  # type: ignore[attr-defined]
        self._selected_path = path  # type: ignore[attr-defined]
        if self.hex_view is not None:
            self.hex_view.set_selected_span(span)
        self.update_status()

    # Multi-span selection API
    def set_selected_spans(self, spans: list[tuple[int, int]] | None, path: str | None) -> None:
        self._selected_span = None  # type: ignore[attr-defined]
        self._selected_path = path  # type: ignore[attr-defined]
        if self.hex_view is not None:
            self.hex_view.set_selected_spans(spans)
        self.update_status()

    def on_hex_cursor_moved(self, offset: int) -> None:
        # Link hex cursor back to parsed selection
        target_path: str | None = None
        prev_path: str | None = getattr(self, "_selected_path", None)
        if hasattr(self, "_span_index") and self._span_index is not None:
            sp = self._span_index.find(offset)
            if sp is not None:
                target_path = sp.path
                # Only broadcast to OutputPanel when HexView has focus
                if (
                    self.hex_view is not None
                    and self.hex_view.has_focus
                    and self._output is not None
                    and target_path != prev_path
                ):
                    from contextlib import suppress
                    with suppress(Exception):
                        self._output.select_path(target_path)
                # Then update selected span/path on the app and hex view
                self.set_selected_span((sp.offset, sp.length), sp.path)
        if target_path is None and hasattr(self, "_unmapped") and self._unmapped is not None:
            for s, ln in self._unmapped:  # type: ignore[attr-defined]
                if s <= offset < s + ln:
                    self.set_selected_span((s, ln), "unmapped")
                    break
        # Note: selection in OutputPanel handled above when HexView has focus
        # Update Inspector panels
        try:
            if self._inspector is not None and self._reader is not None:
                sel = []
                if self.hex_view is not None:
                    sel = getattr(self.hex_view, "_selected_spans", [])
                compare = (
                    self._diff_readers[0]
                    if len(getattr(self, "_diff_readers", [])) == 1
                    else None
                )
                self._inspector.update_for(
                    self._reader,
                    offset,
                    getattr(self, "_span_index", None),
                    sel,
                    endian=getattr(self, "_endian", "little"),
                    compare=compare,
                )
        except Exception:
            pass
        try:
            if getattr(self, "_diff_inspector", None) is not None and self._reader is not None:
                sel = []
                if self._diff_hex is not None:
                    sel = getattr(self._diff_hex, "_selected_spans", [])
                compare = (
                    self._diff_readers[0]
                    if len(getattr(self, "_diff_readers", [])) == 1
                    else None
                )
                self._diff_inspector.update_for(  # type: ignore[attr-defined]
                    self._reader,
                    offset,
                    getattr(self, "_span_index", None),
                    sel,
                    endian=getattr(self, "_endian", "little"),
                    compare=compare,
                )
        except Exception:
            pass

    # ---- Schema apply ----
    def action_apply_schema(self) -> None:
        if self._schema is None or self._reader is None:
            return
        text = self._schema.text
        if self._last_schema_text == text:
            return
        try:
            schema = load_schema(text)
        except SchemaError as e:
            if self._output is not None:
                self._output.set_errors(e.errors)
            if self.hex_view is not None:
                self.hex_view.set_overlays([])
            self.set_status_hint("[schema errors]")
            return
        tree, leaves, errs = apply_schema_tree(self._reader, schema)
        self._last_schema_text = text
        if errs:
            if self._output is not None:
                self._output.set_errors(errs)
            if self.hex_view is not None:
                self.hex_view.set_overlays([])
            self.set_status_hint("[schema errors]")
            return
        if self._output is not None:
            self._output.set_tree(tree)
        regions: list[tuple[int, int, str, str]] = []
        for pf in leaves:
            if pf.error:
                continue
            regions.append((pf.offset, pf.length, pf.name, pf.type))
        if self.hex_view is not None:
            self.hex_view.set_overlays(regions)
        # Propagate mapped coverage to Diff hex as well
        if self._diff_hex is not None:
            from contextlib import suppress
            with suppress(Exception):
                self._diff_hex.set_overlays(regions)
        # Compute coverage and update UI components
        covered, unmapped = compute_coverage(leaves, self._reader.size)
        total = self._reader.size or 1
        unmapped_bytes = sum(ln for (_s, ln) in unmapped)
        self._mapped_percent = max(0.0, min(100.0, (1 - unmapped_bytes / total) * 100.0))
        if self._output is not None:
            from contextlib import suppress

            with suppress(Exception):
                self._output.set_unmapped(unmapped)
        if hasattr(self, "_overview") and self._overview is not None:
            self._overview.update_state(
                file_size=self._reader.size,
                covered=[(s, ln) for (s, ln, _p) in covered],
                viewport=(
                    self.hex_view.top_offset(),
                    self.hex_view.visible_rows() * self.hex_view.bytes_per_row,
                ),
            )
        # Build span index for linking
        spans = [
            Span(
                pf.offset,
                pf.length,
                pf.name,
                type_group(pf.type),
                pf.effective_endian,
                pf.endian_source,
                pf.color_override,
            )
            for pf in leaves
            if not pf.error and pf.length > 0
        ]
        self._span_index = SpanIndex(spans)
        if self.hex_view is not None:
            self.hex_view.set_span_index(self._span_index)
        # Set span index on Diff hex to enable mapped/unmapped styling there
        if self._diff_hex is not None:
            from contextlib import suppress
            with suppress(Exception):
                self._diff_hex.set_span_index(SpanIndex(spans))
        # Also update Diff tab's parsed structure if present, using current diff spans
        if self._diff_output is not None:
            try:
                # Push primary parsed tree
                self._diff_output.set_tree(tree)
                # Recompute changed map against current diff regions (if any)
                if self._diff_regions is not None:
                    fspans = [
                        Span(
                            pf.offset,
                            pf.length,
                            pf.name,
                            type_group(pf.type),
                            pf.effective_endian,
                            pf.endian_source,
                            pf.color_override,
                        )
                        for pf in leaves
                        if pf.length and pf.length > 0
                    ]
                    change_map = intersect_spans(fspans, self._diff_regions)
                    self._diff_output.set_change_map(change_map)
                    # Rebuild Changed Fields panel if available
                    if self._diff_changed_panel is not None:
                        items = []
                        for pf in leaves:
                            info = change_map.get(pf.name)
                            if info and info.get("changed"):
                                items.append(
                                    (
                                        pf.name,
                                        pf.offset,
                                        pf.length,
                                        int(info.get("changed_bytes", 0)),
                                    )
                                )
                        items.sort(key=lambda t: t[1])
                        self._diff_changed_panel.set_items(items)
            except Exception:
                pass
        # Update Diff overview with mapped coverage
        try:
            if self._diff_overview is not None and self._diff_hex is not None:
                self._diff_overview.update_state(
                    file_size=self._reader.size,
                    covered=[(s, ln) for (s, ln, _p) in covered],
                    viewport=(
                        self._diff_hex.top_offset(),
                        self._diff_hex.visible_rows() * self._diff_hex.bytes_per_row,
                    ),
                )
        except Exception:
            pass
        self.set_status_hint("[schema applied]")

    # Debounced schedule from SchemaEditor
    def schedule_schema_apply(self, delay: float = 0.2) -> None:
        try:
            if self._schema_apply_timer is not None:
                self._schema_apply_timer.stop()
        except Exception:
            pass
        # Clamp to a small positive delay to avoid zero-interval timer issues
        safe_delay = max(0.01, float(delay))
        self._schema_apply_timer = self.set_timer(safe_delay, self.action_apply_schema)

    # ---- Helpers ----
    def _build_explore_panes(self) -> Container:
        class FocusProxyScrollable(ScrollableContainer):
            # Not focusable itself; Tab should land on child directly, and Shift+Tab can move back.
            can_focus = False

        # Visualizer with scrollbars and a vertical file overview to the right
        self._overview = FileOverview()
        # Hex view with Inspector stacked below and a separator bar
        self._inspector = Inspector()
        self._inspector.set_scope("explore")
        self._insp_spacer = Static("", id="inspector-spacer")
        # Separator as a container with left/right labels
        self._insp_left = Static("", id="insp-left")
        self._insp_right = Static("", id="insp-right")
        self._insp_sep = Container(self._insp_left, self._insp_right, id="inspector-sep")
        left_col = Container(
            FocusProxyScrollable(self.hex_view),
            self._insp_spacer,
            self._insp_sep,
            self._inspector,
        )
        viz_row = Horizontal(
            left_col,
            Container(self._overview, id="overview"),
        )
        self._pane_viz = Container(viz_row, classes="pane", id="pane-visual")
        # Schema editor
        self._schema = SchemaEditor()
        self._pane_schema = Container(self._schema, classes="pane", id="pane-schema")
        # Output panel (Parsed Structure)
        self._output = OutputPanel()
        right = Container(self._output, classes="pane", id="pane-output")
        # Reorder: Schema -> Hex -> Right (Parsed/Inspector)
        grid = Container(self._pane_schema, self._pane_viz, right, id="explore-grid")
        # Initialize inspector header with defaults
        from contextlib import suppress
        with suppress(Exception):
            self.update_inspector_header(
                "explore", "@0x00000000 (0)   Within: Unmapped", "Full"
            )
        return grid

    def _build_diff_panes(self) -> Container:
        # Empty state if no primary
        if self._reader is None:
            return Container(Static("Open a file in Explore first (Ctrl+O)."), id="diff-empty")

        # Left: File browser (now its own column)
        # Pass primary_file as string or None
        self._diff_browser = FileBrowser(self._primary_file)
        files_panel = Container(
            self._diff_browser, classes="pane", id="pane-diff-browser"
        )

        # Middle-left: Search panel (now its own column)
        self._search_panel = SearchPanel()
        search_panel = Container(
            self._search_panel, classes="pane", id="pane-diff-search"
        )

        # Center: Search banner + Hex of primary + minimap, with Inspector stacked under Hex
        self._diff_overview = FileOverview()
        self._diff_hex = HexView(self._reader)
        self._diff_inspector = Inspector()
        self._diff_inspector.set_scope("diff")
        self._diff_insp_spacer = Static("", id="inspector-spacer-diff")
        self._diff_insp_left = Static("", id="insp-left-diff")
        self._diff_insp_right = Static("", id="insp-right-diff")
        self._diff_insp_sep = Container(
            self._diff_insp_left, self._diff_insp_right, id="inspector-sep-diff"
        )

        # Search banner (hidden by default)
        self._search_banner = SearchBanner()
        self._search_banner.display = False

        # Wrap Hex in a focus-proxy scrollable so Tab lands on Hex directly
        class FocusProxyScrollable(ScrollableContainer):
            # Not focusable itself; Tab lands on HexView, Shift+Tab moves back correctly.
            can_focus = False

        diff_left_col = Container(
            self._search_banner,
            FocusProxyScrollable(self._diff_hex, id="diff-hex"),
            self._diff_insp_spacer,
            self._diff_insp_sep,
            self._diff_inspector,
            id="diff-left",
        )
        hex_panel = Container(
            Horizontal(
                diff_left_col,
                Container(self._diff_overview, id="overview"),
                id="hex-overview-row",
            ),
            classes="pane",
            id="pane-diff-hex",
        )

        # Right: Parsed structure (top) + Changed regions (bottom)
        self._diff_output = OutputPanel()
        self._diff_output.show_diff_markers(True)
        self._diff_regions_panel = DiffRegionsPanel()
        right_panel = Container(
            self._diff_output,
            self._diff_regions_panel,
            classes="pane",
            id="pane-diff-info",
        )
        # Initialize diff inspector header
        from contextlib import suppress
        with suppress(Exception):
            self.update_inspector_header(
                "diff", "@0x00000000 (0)   Within: Unmapped", "Full"
            )
        return Container(files_panel, search_panel, hex_panel, right_panel, id="diff-grid")

    # ---- Diff actions ----
    def set_diff_target(self, path: str) -> None:
        # Set diff target and recompute if changed
        if not path or (self._diff_targets == [path]):
            return
        self.set_diff_targets([path])

    def set_diff_targets(self, paths: list[str]) -> None:
        # Multi-select snapshots
        # Filter out primary
        uniq: list[str] = []
        for p in paths:
            try:
                if self._primary_file and os.path.samefile(self._primary_file, p):
                    continue
            except Exception:
                pass
            if p not in uniq:
                uniq.append(p)
        self._diff_targets = uniq
        # Build readers
        self._diff_readers = []
        for p in self._diff_targets:
            try:
                self._diff_readers.append(PagedReader(p))
            except FileNotFoundError:
                continue
        self._apply_diff()

    def _apply_diff(self) -> None:
        if self._reader is None:
            # Clear overlays if target not set
            self._update_diff([])
            return
        # Mode: 0 targets -> clear; 1 -> diff; >=2 -> frequency
        if len(self._diff_readers) == 0:
            self._update_diff([])
            self._clear_frequency()
            stats = {"changed_bytes": 0, "changed_percent": 0.0}
        elif len(self._diff_readers) == 1:
            spans = compute_diff_spans(self._reader, self._diff_readers[0])
            stats = diff_stats(self._reader, self._diff_readers[0], spans)
            self._diff_regions = spans
            self._diff_index = 0 if spans else -1
            self._update_diff(spans)
            self._clear_frequency()
        else:
            counts, fstats = compute_frequency_map(self._reader, self._diff_readers)
            # Push to hex view
            if self._diff_hex is not None:
                self._diff_hex.set_frequency_map(counts, int(fstats["N"]))
                self._diff_hex.set_selected_spans(None)
            # Build hot regions as contiguous >0
            regions: list[tuple[int, int]] = []
            start = None
            length = 0
            for i in range(len(counts)):
                if counts[i] > 0:
                    if start is None:
                        start = i
                        length = 1
                    else:
                        length += 1
                else:
                    if start is not None and length > 0:
                        regions.append((start, length))
                    start = None
                    length = 0
            if start is not None and length > 0:
                regions.append((start, length))
            # Reuse changed regions panel for hot regions (MVP)
            self._diff_regions = regions
            self._diff_index = 0 if regions else -1
            if self._diff_regions_panel is not None:
                self._diff_regions_panel.set_regions(regions)
            # Overview: mark hot regions as covered
            if (
                self._diff_overview is not None
                and self._diff_hex is not None
                and self._reader is not None
            ):
                self._diff_overview.update_state(
                    file_size=self._reader.size,
                    covered=regions,
                    viewport=(
                        self._diff_hex.top_offset(),
                        self._diff_hex.visible_rows() * self._diff_hex.bytes_per_row,
                    ),
                )
            stats = {
                "changed_bytes": int(fstats["union_changed"]),
                "changed_percent": float(fstats["mean_diff_rate"]) * 100.0,
                "snapshots": int(fstats["N"]),
            }
        # If schema present, compute parsed tree and field changes
        try:
            if self._schema is not None and self._schema.text and self._reader is not None:
                schema = load_schema(self._schema.text)
                tree, leaves, errs = apply_schema_tree(self._reader, schema)
                if not errs and self._diff_output is not None:
                    # Push overlays and span index to Diff hex to enable mapped/unmapped styling
                    try:
                        if self._diff_hex is not None:
                            regions: list[tuple[int, int, str, str]] = []
                            for pf in leaves:
                                if pf.error:
                                    continue
                                regions.append((pf.offset, pf.length, pf.name, pf.type))
                            self._diff_hex.set_overlays(regions)
                            spans = [
                                Span(
                                    pf.offset,
                                    pf.length,
                                    pf.name,
                                    type_group(pf.type),
                                    pf.effective_endian,
                                    pf.endian_source,
                                    pf.color_override,
                                )
                                for pf in leaves
                                if pf.length and pf.length > 0
                            ]
                            self._diff_hex.set_span_index(SpanIndex(spans))
                    except Exception:
                        pass
                    # Build leaf spans and intersect with diffs
                    fspans = [
                        Span(
                            pf.offset,
                            pf.length,
                            pf.name,
                            type_group(pf.type),
                            pf.effective_endian,
                            pf.endian_source,
                            pf.color_override,
                        )
                        for pf in leaves
                        if pf.length and pf.length > 0
                    ]
                    change_map = intersect_spans(fspans, spans)
                    # Push to parsed structure and enable markers
                    self._diff_output.set_change_map(change_map)
                    self._diff_output.set_tree(tree)
                    # Build Changed Fields panel items
                    if self._diff_changed_panel is not None:
                        items = []
                        for pf in leaves:
                            info = change_map.get(pf.name)
                            if info and info.get("changed"):
                                items.append(
                                    (
                                        pf.name,
                                        pf.offset,
                                        pf.length,
                                        int(info.get("changed_bytes", 0)),
                                    )
                                )
                        items.sort(key=lambda t: t[1])
                        self._diff_changed_panel.set_items(items)
        except Exception:
            # If schema fails or parsing errors, keep diff UI without structure
            pass
        ch = int(stats.get("changed_bytes", 0))
        pct = float(stats.get("changed_percent", 0.0))
        snap = stats.get("snapshots")
        extra = f", snapshots: {int(snap)}" if snap is not None else ""
        self.set_status_hint(f"[diff: {ch} bytes, {pct:.1f}%{extra}]")

    def _clear_frequency(self) -> None:
        if self._diff_hex is not None:
            self._diff_hex.clear_frequency_map()

    def _update_diff(self, spans: list[tuple[int, int]]) -> None:
        # Push spans to widgets
        if self._diff_hex is not None:
            self._diff_hex.set_diff_regions(spans)
            if spans:
                self._diff_hex.set_selected_span(None)
        if self._diff_regions_panel is not None:
            self._diff_regions_panel.set_regions(spans)
        if (
            self._diff_overview is not None
            and self._diff_hex is not None
            and self._reader is not None
        ):
            self._diff_overview.update_state(
                file_size=self._reader.size,
                covered=[(s, ln) for (s, ln) in spans],
                viewport=(
                    self._diff_hex.top_offset(),
                    self._diff_hex.visible_rows() * self._diff_hex.bytes_per_row,
                ),
            )

    def action_next_diff_region(self) -> None:
        if not self._diff_regions or self._diff_hex is None:
            return
        step = 1 if self._diff_index >= 0 else 0
        self._diff_index = min(len(self._diff_regions) - 1, self._diff_index + step)
        s, ln = self._diff_regions[self._diff_index]
        self._jump_to_diff(s, ln)

    def action_prev_diff_region(self) -> None:
        if not self._diff_regions or self._diff_hex is None:
            return
        self._diff_index = max(0, self._diff_index - 1 if self._diff_index > 0 else 0)
        s, ln = self._diff_regions[self._diff_index]
        self._jump_to_diff(s, ln)

    def diff_goto_region(self, index: int, start: int, length: int) -> None:
        self._diff_index = max(0, min(index, len(self._diff_regions) - 1))
        self._jump_to_diff(start, length)

    def diff_regions_updated(self, regions: list[tuple[int, int]]) -> None:
        # Called by panel when view mode changes (Top/All/Grouped)
        self._diff_regions = regions
        if self._diff_index >= len(self._diff_regions):
            self._diff_index = len(self._diff_regions) - 1 if self._diff_regions else -1

    def _jump_to_diff(self, start: int, length: int) -> None:
        if self._diff_hex is None:
            return
        self._diff_hex.set_selected_span((start, length))
        self._diff_hex.set_cursor(start)
        self.set_focus(self._diff_hex)

    def diff_goto_field(self, path: str, start: int, length: int) -> None:
        # Select field in parsed structure and hex
        if self._diff_output is not None:
            from contextlib import suppress
            with suppress(Exception):
                self._diff_output.select_path(path)
        self._jump_to_diff(start, length)

    # Toggle right panel between regions and fields
    def action_diff_toggle_panel(self) -> None:
        self._diff_show_changed_fields = not self._diff_show_changed_fields
        if getattr(self, "_diff_right", None) is None:
            return
        try:
            # Clear and add the appropriate widget
            self._diff_right.remove_children()  # type: ignore[attr-defined]
        except Exception:
            for ch in list(self._diff_right.children):  # type: ignore[attr-defined]
                ch.remove()
        if self._diff_show_changed_fields and self._diff_changed_panel is not None:
            self._diff_right.mount(self._diff_changed_panel)  # type: ignore[attr-defined]
        elif self._diff_regions_panel is not None:
            self._diff_right.mount(self._diff_regions_panel)  # type: ignore[attr-defined]

    # ---- Search lens methods ----
    def on_search_mode_changed(self, mode: str) -> None:
        """Called when search mode selector changes."""
        if mode == "none":
            self.cancel_search()

    def run_date_search(
        self, start_date, end_date, alignment: int = 4, encodings: list[str] | None = None
    ) -> None:
        """Execute date/time search with OR semantics (union of all selected encodings)."""
        if self._reader is None or self._diff_hex is None:
            return

        # Default to unix_s if no encodings specified
        if not encodings:
            encodings = ["unix_s"]

        # Run search for each selected encoding
        all_hits: list[SearchHit] = []
        for encoding in encodings:
            if encoding == "unix_s":
                hits = search_date_unix_s(self._reader, start_date, end_date, alignment)
            elif encoding == "unix_ms":
                hits = search_date_unix_ms(self._reader, start_date, end_date, alignment)
            elif encoding == "filetime":
                hits = search_date_filetime(self._reader, start_date, end_date, alignment)
            elif encoding == "dos_datetime":
                hits = search_date_dos_datetime(self._reader, start_date, end_date, alignment)
            elif encoding == "dos_date":
                hits = search_date_dos_date(self._reader, start_date, end_date, alignment)
            elif encoding == "ole_date":
                hits = search_date_ole_date(self._reader, start_date, end_date, alignment)
            elif encoding == "days_since_1970":
                hits = search_date_days_since_1970(self._reader, start_date, end_date, alignment)
            elif encoding == "days_since_1980":
                hits = search_date_days_since_1980(self._reader, start_date, end_date, alignment)
            elif encoding == "ascii_text":
                hits = search_date_ascii_text(self._reader, start_date, end_date)
            elif encoding == "ftm_packed_date":
                hits = search_date_ftm_packed(self._reader, start_date, end_date, alignment)
            else:
                continue
            all_hits.extend(hits)

        # Deduplicate hits by (offset, length) and merge matches
        # Priority for best label: ASCII > DOS date > DOS datetime > days-since > OLE DATE > others
        encoding_priority = {
            "ASCII MM/DD/YY": 0,
            "ASCII MM/DD/YYYY": 0,
            "ASCII YYYY-MM-DD": 0,
            "DOS date (u16 LE)": 1,
            "DOS datetime (2×u16 LE)": 2,
            "FTM Packed Date (4-byte)": 2,
            "Days since 1970 (u16 LE)": 3,
            "Days since 1980 (u16 LE)": 3,
            "OLE DATE (f64 LE)": 4,
            "FILETIME (u64 LE)": 5,
            "unix_ms (u64 LE)": 6,
            "unix_s (u32 LE)": 7,
        }

        hit_map: dict[tuple[int, int], SearchHit] = {}
        for hit in all_hits:
            key = (hit.offset, hit.length)
            if key in hit_map:
                # Merge matches
                existing = hit_map[key]
                existing.matches.extend(hit.matches)
                # Update summary to use higher priority encoding
                for match in hit.matches:
                    enc = match.encoding
                    existing_priority = encoding_priority.get(
                        existing.matches[0].encoding, 999
                    )
                    new_priority = encoding_priority.get(enc, 999)
                    if new_priority < existing_priority:
                        existing.summary = match.summary
                        # Reorder matches to put best first
                        existing.matches.remove(match)
                        existing.matches.insert(0, match)
            else:
                hit_map[key] = hit

        # Convert back to list and sort by offset
        merged_hits = list(hit_map.values())
        merged_hits.sort(key=lambda h: h.offset)

        # Update state
        self._search_state.mode = "date"
        self._search_state.results = merged_hits
        self._search_state.params = {
            "start_date": start_date,
            "end_date": end_date,
            "alignment": alignment,
            "encodings": encodings,
        }

        if merged_hits:
            self._search_state.index = 0
            # Jump to first hit
            first_hit = merged_hits[0]
            self._navigate_to_hit(first_hit)
        else:
            self._search_state.index = -1

        # Update UI
        self._update_search_ui()

    def run_chunk_search(
        self,
        length_type: str = "u16 LE",
        min_length: int | None = None,
        max_length: int | None = None,
        alignment: int = 1,
    ) -> None:
        """Execute chunk (length-prefixed) search."""
        if self._reader is None or self._diff_hex is None:
            return

        from hexmap.core.search_lens import LengthType, search_length_prefixed_strings

        # Convert length_type string to LengthType object
        length_type_obj = LengthType.from_label(length_type)

        # Run search
        hits = search_length_prefixed_strings(
            self._reader,
            length_type=length_type_obj,
            min_length=min_length,
            max_length=max_length,
            alignment=alignment,
        )

        # Update state
        self._search_state.mode = "chunk"
        self._search_state.results = hits
        self._search_state.params = {
            "length_type": length_type,
            "min_length": min_length,
            "max_length": max_length,
            "alignment": alignment,
        }

        if hits:
            self._search_state.index = 0
            # Jump to first hit
            first_hit = hits[0]
            self._navigate_to_hit(first_hit)
        else:
            self._search_state.index = -1

        # Update UI
        self._update_search_ui()

    def run_pointer_search(
        self,
        pointer_type: str = "u32 LE",
        base_mode: str = "absolute",
        base_addend: int = 0,
        min_target: int | None = None,
        max_target: int | None = None,
        allow_zero: bool = False,
        target_alignment: int | None = None,
        scan_step: int | None = None,
        preview_length: int = 16,
    ) -> None:
        """Execute pointer search."""
        if self._reader is None or self._diff_hex is None:
            return

        from hexmap.core.search_lens import PointerType, search_pointers

        # Convert pointer_type string to PointerType object
        pointer_type_obj = PointerType.from_label(pointer_type)

        # Run search
        hits = search_pointers(
            self._reader,
            pointer_type=pointer_type_obj,
            base_mode=base_mode,  # type: ignore[arg-type]
            base_addend=base_addend,
            min_target=min_target,
            max_target=max_target,
            allow_zero=allow_zero,
            target_alignment=target_alignment,
            preview_length=preview_length,
            scan_step=scan_step,
        )

        # Update state
        self._search_state.mode = "pointer"
        self._search_state.results = hits
        self._search_state.params = {
            "pointer_type": pointer_type,
            "base_mode": base_mode,
            "base_addend": base_addend,
            "min_target": min_target,
            "max_target": max_target,
            "allow_zero": allow_zero,
            "target_alignment": target_alignment,
            "scan_step": scan_step,
            "preview_length": preview_length,
        }

        if hits:
            self._search_state.index = 0
            # Jump to first hit
            first_hit = hits[0]
            self._navigate_to_hit(first_hit)
        else:
            self._search_state.index = -1

        # Update UI
        self._update_search_ui()

    def _update_search_ui(self) -> None:
        """Update search banner and hex highlighting."""
        if not self._search_state.is_active():
            return

        # Show banner
        if self._search_banner:
            params_text = self._format_search_params()
            self._search_banner.update_search(
                self._search_state.mode,
                params_text,
                len(self._search_state.results),
            )
            self._search_banner.display = True

        # Update hex view highlighting
        if self._diff_hex:
            # Get current hit
            current_hit = self._search_state.current_hit()

            # Check if this is a multi-span search (like chunk search)
            has_multi_span_hit = current_hit and current_hit.spans and len(current_hit.spans) > 1

            if has_multi_span_hit:
                # For multi-span searches (chunk), build combined span list:
                # - All length fields get "length" role (green markers)
                # - Only current hit's payload gets "payload" role (blue background)
                all_spans = []

                # Add all length fields as "length" role spans
                for hit in self._search_state.results:
                    if hit.spans:
                        # Find length span
                        for span in hit.spans:
                            if span.role == "length":
                                all_spans.append((span.offset, span.length, "length"))
                                break
                    else:
                        all_spans.append((hit.offset, hit.length, "length"))

                # Add current hit's payload span
                for span in current_hit.spans:  # type: ignore[union-attr]
                    if span.role == "payload":
                        all_spans.append((span.offset, span.length, "payload"))
                        break

                # Set all spans at once (don't call set_search_hits, it would overwrite)
                self._diff_hex.set_search_spans(all_spans)
            else:
                # Simple search (date search) - show all hits
                hit_regions = [(h.offset, h.length) for h in self._search_state.results]
                self._diff_hex.set_search_hits(hit_regions)

        # Update inspector
        self._update_search_inspector()

    def _format_search_params(self) -> str:
        """Format search parameters for banner display."""
        if self._search_state.mode == "date":
            params = self._search_state.params
            start = params.get("start_date", "")
            end = params.get("end_date", "")
            if start and end:
                start_str = start.strftime("%Y-%m-%d") if hasattr(start, "strftime") else str(start)
                end_str = end.strftime("%Y-%m-%d") if hasattr(end, "strftime") else str(end)
                return f"(unix_s u32le) {start_str} → {end_str}"
        elif self._search_state.mode == "chunk":
            params = self._search_state.params
            length_type = params.get("length_type", "u16 LE")
            parts = []
            if params.get("min_length") is not None:
                parts.append(f"payload {params['min_length']}–")
            if params.get("max_length") is not None:
                if parts:  # Append to range
                    parts[-1] += f"{params['max_length']} bytes"
                else:
                    parts.append(f"payload ≤{params['max_length']} bytes")
            elif parts:  # Min only, no max
                parts[-1] += "∞ bytes"
            return f"({length_type}) {', '.join(parts)}" if parts else f"({length_type})"
        elif self._search_state.mode == "pointer":
            params = self._search_state.params
            pointer_type = params.get("pointer_type", "u32 LE")
            base_mode = params.get("base_mode", "absolute")
            preview_len = params.get("preview_length", 16)
            base_str = "file start" if base_mode == "absolute" else "relative"
            return f"Pointer ({pointer_type}) → {base_str}, preview {preview_len} bytes"
        return ""

    def _update_search_inspector(self) -> None:
        """Update inspector to show search results."""
        if not self._search_state.has_results() or self._diff_inspector is None:
            return

        hit = self._search_state.current_hit()
        if hit is None:
            return

        # Build search inspector content
        from rich.text import Text

        content = Text()
        idx = self._search_state.index + 1
        total = len(self._search_state.results)

        # Green header with navigation
        from hexmap.ui.palette import PALETTE

        header_style = f"{PALETTE.search_inspector_fg} on {PALETTE.search_inspector_bg}"
        content.append(
            f"◀ (p)rev   Result {idx}/{total}   (n)ext ▶   Esc: cancel\n",
            style=header_style,
        )
        content.append("\n")

        # Hit details
        content.append(f"Offset: 0x{hit.offset:08X}\n")

        # Check if this is a multi-span hit (e.g., length-prefixed string, pointer)
        if hit.spans and len(hit.spans) > 1:
            # Determine hit type from span roles
            span_roles = [s.role for s in hit.spans]

            if "pointer" in span_roles and "target_preview" in span_roles:
                # Pointer search hit
                if hit.matches:
                    details = hit.matches[0].details
                    ptr_type = details.get("pointer_type", "u32 LE")
                    ptr_value = details.get("ptr_value", 0)
                    target = details.get("target", 0)
                    base_mode = details.get("base_mode", "absolute")
                    base_addend = details.get("base_addend", 0)
                    preview_len = details.get("preview_length", 0)
                    confidence = details.get("confidence", "High")

                    content.append("Pointer type: ", style=PALETTE.inspector_label)
                    content.append(f"{ptr_type}\n", style=PALETTE.inspector_value)
                    content.append("Pointer value: ", style=PALETTE.inspector_label)
                    content.append(
                        f"{ptr_value} (0x{ptr_value:X})\n", style=PALETTE.inspector_value
                    )
                    content.append("Base mode: ", style=PALETTE.inspector_label)
                    base_str = (
                        "absolute"
                        if base_mode == "absolute"
                        else f"relative (+0x{hit.offset:x})"
                    )
                    content.append(f"{base_str}\n", style=PALETTE.inspector_value)
                    if base_addend != 0:
                        content.append("Addend: ", style=PALETTE.inspector_label)
                        content.append(f"{base_addend}\n", style=PALETTE.inspector_value)
                    content.append("Target: ", style=PALETTE.inspector_label)
                    content.append(f"0x{target:08X} ({target})\n", style=PALETTE.inspector_value)
                    if preview_len > 0:
                        content.append("Preview: ", style=PALETTE.inspector_label)
                        content.append(f"{preview_len} bytes\n", style=PALETTE.inspector_value)
                    if confidence != "High":
                        content.append("Confidence: ", style=PALETTE.inspector_label)
                        content.append(f"{confidence}\n", style=PALETTE.inspector_dim)
            else:
                # Length-prefixed string
                # Get length type from match details
                length_type_label = "u16 LE"  # Default
                if hit.matches:
                    length_type_label = hit.matches[0].details.get("type", "u16 LE")

                # Show each span with its role
                for span in hit.spans:
                    if span.role == "length":
                        content.append("Length field: ", style=PALETTE.inspector_label)
                        content.append(
                            f"{span.length} bytes ({length_type_label})\n",
                            style=PALETTE.inspector_value,
                        )
                    elif span.role == "payload":
                        content.append("Payload: ", style=PALETTE.inspector_label)
                        # Check if capped (payload span length < declared length)
                        if hit.matches and hit.matches[0].details.get("capped", False):
                            declared_len = hit.matches[0].details.get("length", span.length)
                            content.append(
                                f"{span.length} bytes (capped at EOF, declared: {declared_len})\n",
                                style=PALETTE.inspector_value,
                            )
                        else:
                            content.append(f"{span.length} bytes\n", style=PALETTE.inspector_value)
        else:
            # Simple hit, show total length
            content.append(f"Length: {hit.length} bytes\n")
        content.append("\n")

        # Show primary match (best encoding)
        if hit.matches:
            primary = hit.matches[0]
            content.append("Decoded: ", style=PALETTE.inspector_label)
            content.append(f"{primary.summary}\n", style=PALETTE.inspector_value)
            content.append("Encoding: ", style=PALETTE.inspector_label)
            content.append(f"{primary.encoding}\n", style=PALETTE.inspector_value)

            # Show additional matches if any
            if len(hit.matches) > 1:
                content.append("\n")
                content.append("Also matches as:\n", style=PALETTE.inspector_dim)
                for alt_match in hit.matches[1:]:
                    content.append(f"  • {alt_match.encoding}: ", style=PALETTE.inspector_dim)
                    content.append(f"{alt_match.summary}\n", style=PALETTE.inspector_value)

        # Show in inspector
        self._diff_inspector.set_search_content(content)

    def action_search_next_hit(self) -> None:
        """Navigate to next search hit."""
        if not self._search_state.has_results() or self._diff_hex is None:
            return

        hit = self._search_state.next_hit()
        if hit:
            self._navigate_to_hit(hit)
            self._update_search_inspector()
            self._update_search_ui()  # Refresh to show only active hit's payload

    def action_search_prev_hit(self) -> None:
        """Navigate to previous search hit."""
        if not self._search_state.has_results() or self._diff_hex is None:
            return

        hit = self._search_state.prev_hit()
        if hit:
            self._navigate_to_hit(hit)
            self._update_search_inspector()
            self._update_search_ui()  # Refresh to show only active hit's payload

    def _navigate_to_hit(self, hit) -> None:  # type: ignore[no-untyped-def]
        """Navigate cursor and selection to a search hit."""
        if self._diff_hex is None:
            return

        # Check if this is a multi-span hit (like chunk search)
        if hit.spans and len(hit.spans) > 1:
            # Find length and payload spans
            length_span = None
            payload_span = None
            for span in hit.spans:
                if span.role == "length":
                    length_span = span
                elif span.role == "payload":
                    payload_span = span

            if length_span and payload_span:
                # Set cursor to length field start
                self._diff_hex.set_cursor(length_span.offset)
                # Set selection to payload region only
                self._diff_hex.set_selected_spans([(payload_span.offset, payload_span.length)])
            else:
                # Fallback to entire hit
                self._diff_hex.set_cursor(hit.offset)
                self._diff_hex.set_selected_spans([(hit.offset, hit.length)])
        else:
            # Simple hit - cursor and selection to entire hit
            self._diff_hex.set_cursor(hit.offset)
            self._diff_hex.set_selected_spans([(hit.offset, hit.length)])

    def cancel_search(self) -> None:
        """Cancel active search and return to browse mode."""
        self._search_state.clear()

        # Hide banner
        if self._search_banner:
            self._search_banner.display = False

        # Clear hex highlighting
        if self._diff_hex:
            self._diff_hex.clear_search_hits()
            self._diff_hex.set_selected_spans([])

        # Reset search panel
        if self._search_panel:
            self._search_panel.reset_to_none()

        # Restore normal inspector
        if self._diff_inspector:
            self._diff_inspector.clear_search_content()

    def action_cancel_search(self) -> None:
        """Action for Esc key to cancel search."""
        if self._search_state.is_active():
            self.cancel_search()


# ---- Simple modals ----


class GotoScreen(ModalScreen[str | None]):
    def __init__(self):
        super().__init__()
        
    def compose(self) -> ComposeResult:  # type: ignore[override]
        yield Label("Goto offset (hex like 0x1A2B or decimal):")
        self._input = Input(placeholder="offset")
        yield self._input

    def on_mount(self) -> None:  # type: ignore[override]
        self.set_focus(self._input)

    def on_input_submitted(self, event: Input.Submitted) -> None:  # type: ignore[override]
        self.dismiss(event.value)

    def on_key(self, event) -> None:  # type: ignore[override]
        if event.key == "escape":
            self.dismiss(None)


class SearchScreen(ModalScreen[str | None]):
    def __init__(self):
        super().__init__()

    def compose(self) -> ComposeResult:  # type: ignore[override]
        yield Label("Search (ASCII text or hex bytes e.g. DE AD BE EF):")
        self._input = Input(placeholder="pattern")
        yield self._input

    def on_mount(self) -> None:  # type: ignore[override]
        self.set_focus(self._input)

    def on_input_submitted(self, event: Input.Submitted) -> None:  # type: ignore[override]
        self.dismiss(event.value)

    def on_key(self, event) -> None:  # type: ignore[override]
        if event.key == "escape":
            self.dismiss(None)

    # No callback wiring here; App will pass a callback when pushing the screen

    # Note: callbacks are handled by App._search_submit / _goto_submit


class HelpScreen(ModalScreen[None]):
    def compose(self) -> ComposeResult:  # type: ignore[override]
        text = (
            "Navigation: h/j/k/l, arrows, PgUp/PgDn, gg, G\n"
            "Search: / to open, n next\n"
            "View: Tab/Shift+Tab focus panes\n"
            "Tabs: Ctrl+Tab / Ctrl+Shift+Tab, 1 Explore, 2 Diff, d Diff\n"
            "Schema: Ctrl+O load, Ctrl+R re-apply; auto-applies on Enter/blur\n"
            "Diff: primary is the open file; pick a comparison from the left browser\n"
            "      [ prev, ] next diffs; c toggle regions/fields\n"
            "Diff coloring: changed bytes underlined in Hex and marked in tree\n"
            "DSL: sequential fields with optional offset/skip; struct fields\n"
            "Coverage: mapped = colored fields; unmapped = dim; Unmapped list selectable\n"
            "Minimap: right bar shows mapped/unmapped and viewport\n"
            "Quit: q"
        )
        yield Static(text)

    def on_key(self, event) -> None:  # type: ignore[override]
        if event.key in {"escape", "enter", "q"}:
            self.dismiss(None)


class SchemaLoadScreen(ModalScreen[str | None]):
    def compose(self) -> ComposeResult:  # type: ignore[override]
        yield Label("Load YAML schema from path:")
        self._input = Input(placeholder="path/to/schema.yaml")
        yield self._input

    def on_mount(self) -> None:  # type: ignore[override]
        self.set_focus(self._input)

    def on_input_submitted(self, event: Input.Submitted) -> None:  # type: ignore[override]
        self.dismiss(event.value)

    def on_key(self, event) -> None:  # type: ignore[override]
        if event.key == "escape":
            self.dismiss(None)


class DiffLoadScreen(ModalScreen[tuple[str, str] | None]):
    def compose(self) -> ComposeResult:  # type: ignore[override]
        yield Label("Select two files to diff:")
        self._input_a = Input(placeholder="File A path")
        self._input_b = Input(placeholder="File B path")
        yield self._input_a
        yield self._input_b

    def on_mount(self) -> None:  # type: ignore[override]
        self.set_focus(self._input_a)

    def on_input_submitted(self, event: Input.Submitted) -> None:  # type: ignore[override]
        if event.input is self._input_a:
            self.set_focus(self._input_b)
        else:
            a = self._input_a.value or ""
            b = self._input_b.value or ""
            if a and b:
                self.dismiss((a, b))

    def on_key(self, event) -> None:  # type: ignore[override]
        if event.key == "escape":
            self.dismiss(None)


class SaveAsModal(ModalScreen[str | None]):
    """Modal dialog for Save As functionality."""

    def compose(self) -> ComposeResult:  # type: ignore[override]
        yield Label("Save schema as:")
        self._input = Input(placeholder="path/to/schema.yaml")
        yield self._input
        with Horizontal():
            yield Button("Save", id="save-btn", variant="primary")
            yield Button("Cancel", id="cancel-btn")

    def on_mount(self) -> None:  # type: ignore[override]
        self.set_focus(self._input)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-btn":
            path = self._input.value.strip()
            if path:
                self.dismiss(path)
            else:
                self.dismiss(None)
        elif event.button.id == "cancel-btn":
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:  # type: ignore[override]
        path = event.value.strip()
        if path:
            self.dismiss(path)
        else:
            self.dismiss(None)

    def on_key(self, event) -> None:  # type: ignore[override]
        if event.key == "escape":
            self.dismiss(None)


class SchemaLibraryModal(ModalScreen[tuple[str, SchemaEntry] | None]):
    """Schema Library modal for browsing and managing schemas.

    Returns: Tuple of (action, schema_entry) or None if cancelled
        Actions: "load", "edit"
    """

    CSS = """
    SchemaLibraryModal {
        align: center middle;
    }

    #schema-library-container {
        width: 90%;
        height: 85%;
        background: $surface;
        border: thick $primary;
        padding: 1;
    }

    #schema-search {
        width: 100%;
        margin-bottom: 1;
    }

    #schema-content {
        layout: horizontal;
        height: 1fr;
    }

    #schema-list-container {
        width: 35%;
        height: 100%;
        border-right: solid $primary;
        padding-right: 1;
    }

    #schema-list {
        width: 100%;
        height: 100%;
    }

    #schema-details {
        width: 65%;
        height: 100%;
        padding-left: 1;
    }

    #schema-preview {
        height: 1fr;
        overflow-y: auto;
        border: solid $panel;
        padding: 1;
        margin-bottom: 1;
    }

    #schema-actions {
        height: auto;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._builtin_schemas: list[SchemaEntry] = []
        self._user_schemas: list[SchemaEntry] = []
        self._all_schemas: list[SchemaEntry] = []
        self._filtered_schemas: list[SchemaEntry] = []
        self._selected_schema: SchemaEntry | None = None
        self._index_to_schema: dict[int, SchemaEntry] = {}  # Map option index to schema

    def compose(self) -> ComposeResult:  # type: ignore[override]
        with Container(id="schema-library-container"):
            yield Label("Schema Library")
            self._search = Input(placeholder="Search schemas...", id="schema-search")
            yield self._search

            with Container(id="schema-content"):
                # Left: schema list
                with Container(id="schema-list-container"):
                    self._list = OptionList(id="schema-list")
                    yield self._list

                # Right: details and actions
                with Container(id="schema-details"):
                    self._preview = Static("Select a schema to view details", id="schema-preview")
                    yield self._preview

                    with Horizontal(id="schema-actions"):
                        yield Button("Load", id="btn-load", variant="primary")
                        yield Button("Duplicate to Mine", id="btn-duplicate")
                        yield Button("New", id="btn-new")
                        yield Button("Delete", id="btn-delete", variant="error")
                        yield Button("Close", id="btn-close")

    def on_mount(self) -> None:  # type: ignore[override]
        self._refresh_schemas()
        self._update_action_buttons()
        self.set_focus(self._search)

    def _refresh_schemas(self) -> None:
        """Discover and display all schemas."""
        self._builtin_schemas, self._user_schemas = discover_schemas()
        self._all_schemas = self._builtin_schemas + self._user_schemas
        self._filtered_schemas = self._all_schemas
        self._update_list()

    def _update_list(self) -> None:
        """Update the schema list display."""
        self._list.clear_options()
        self._index_to_schema.clear()
        option_index = 0

        # Add Built-in section
        if any(s.is_builtin for s in self._filtered_schemas):
            self._list.add_option("─── Built-in ───")
            option_index += 1
            for schema in self._filtered_schemas:
                if schema.is_builtin:
                    self._list.add_option(f"  {schema.name}")
                    self._index_to_schema[option_index] = schema
                    option_index += 1

        # Add Mine section
        if any(not s.is_builtin for s in self._filtered_schemas):
            self._list.add_option("─── Mine ───")
            option_index += 1
            for schema in self._filtered_schemas:
                if not schema.is_builtin:
                    self._list.add_option(f"  {schema.name}")
                    self._index_to_schema[option_index] = schema
                    option_index += 1

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter schemas as user types."""
        if event.input is self._search:
            query = event.value
            self._filtered_schemas = search_schemas(self._all_schemas, query)
            self._update_list()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle schema selection."""
        # Get the index of the selected option
        selected_index = event.option_index

        # Check if this is a header (not in our schema mapping)
        if selected_index not in self._index_to_schema:
            # Ignore header selections
            return

        # Get the schema from our mapping
        schema = self._index_to_schema[selected_index]
        self._selected_schema = schema
        self._update_preview()
        self._update_action_buttons()

    def _update_preview(self) -> None:
        """Update the preview pane with selected schema details."""
        if self._selected_schema is None:
            self._preview.update("Select a schema to view details")
            return

        schema = self._selected_schema
        meta = schema.metadata

        # Build preview content
        lines = []
        lines.append(f"[bold]{meta.name}[/bold]\n")

        if meta.description:
            lines.append(f"[dim]{meta.description}[/dim]\n")

        if meta.tags:
            tags_str = ", ".join(meta.tags)
            lines.append(f"Tags: {tags_str}\n")

        if meta.file_patterns:
            patterns_str = ", ".join(meta.file_patterns)
            lines.append(f"File patterns: {patterns_str}\n")

        if meta.endian:
            lines.append(f"Endian: {meta.endian}\n")

        lines.append(f"\nSource: {'Built-in' if schema.is_builtin else 'Mine'}")
        lines.append(f"\nPath: {schema.path}\n")

        lines.append("\n[dim]─── YAML Preview ───[/dim]\n")
        try:
            content = schema.load_content()
            # Show first 20 lines
            preview_lines = content.split("\n")[:20]
            lines.append("\n".join(preview_lines))
            if len(content.split("\n")) > 20:
                lines.append("\n[dim]...(truncated)[/dim]")
        except Exception:
            lines.append("[dim]Failed to load content[/dim]")

        self._preview.update("\n".join(lines))

    def _update_action_buttons(self) -> None:
        """Update button states based on selection."""
        has_selection = self._selected_schema is not None
        is_builtin = has_selection and self._selected_schema.is_builtin if has_selection else False

        load_btn = self.query_one("#btn-load", Button)
        duplicate_btn = self.query_one("#btn-duplicate", Button)
        delete_btn = self.query_one("#btn-delete", Button)

        load_btn.disabled = not has_selection
        duplicate_btn.disabled = not is_builtin
        delete_btn.disabled = is_builtin or not has_selection

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks."""
        if event.button.id == "btn-close":
            self.dismiss(None)

        elif event.button.id == "btn-load":
            if self._selected_schema:
                self.dismiss(("load", self._selected_schema))

        elif event.button.id == "btn-duplicate":
            if self._selected_schema and self._selected_schema.is_builtin:
                new_schema = duplicate_to_user(self._selected_schema)
                if new_schema:
                    self._refresh_schemas()
                    # Show success message (will appear in app status)
                    self.app._status_hint = f"[schema duplicated to {new_schema.path.name}]"  # type: ignore[attr-defined]

        elif event.button.id == "btn-new":
            # Create a new blank schema
            new_schema = create_new_schema("New Schema")
            if new_schema:
                self._refresh_schemas()
                # Load the new schema for editing
                self.dismiss(("edit", new_schema))

        elif event.button.id == "btn-delete":  # noqa: SIM102
            if (
                self._selected_schema
                and not self._selected_schema.is_builtin
                and delete_user_schema(self._selected_schema)
            ):
                self._selected_schema = None
                self._refresh_schemas()
                self._update_preview()
                self._update_action_buttons()
                self.app._status_hint = "[schema deleted]"  # type: ignore[attr-defined]

    def on_key(self, event) -> None:  # type: ignore[override]
        if event.key == "escape":
            self.dismiss(None)
        elif event.key == "enter" and self._selected_schema:
            self.dismiss(("load", self._selected_schema))
