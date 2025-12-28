from __future__ import annotations

from contextlib import suppress
from math import ceil

from rich.style import Style
from rich.text import Text
from textual.reactive import reactive
from textual.widget import Widget

from hexmap.core.diff import DiffIndex, SearchSpanIndex
from hexmap.core.io import PagedReader
from hexmap.core.spans import SpanIndex
from hexmap.ui.palette import PALETTE


class HexView(Widget):
    """Read-only hex viewer widget backed by PagedReader.

    - Renders only the visible rows based on widget height.
    - Does not load the full file into memory.
    - Scrolling is controlled by `scroll_rows` and helpers.
    """

    DEFAULT_BYTES_PER_ROW = 16
    can_focus = True

    BINDINGS = [
        ("left", "cursor_left", "Left"),
        ("right", "cursor_right", "Right"),
        ("h", "cursor_left", "Left"),
        ("l", "cursor_right", "Right"),
        ("up", "cursor_up", "Up"),
        ("down", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
        ("j", "cursor_down", "Down"),
        ("pageup", "page_up", "PgUp"),
        ("pagedown", "page_down", "PgDn"),
        ("G", "go_end", "End"),
        ("/", "open_search", "Search"),
        ("n", "search_next", "Next"),
        ("v", "open_compare_strings", "Compare Strings"),
    ]

    scroll_rows: int = reactive(0)
    cursor_offset: int = reactive(0)
    viewport_offset: int = reactive(0)

    def __init__(self, reader: PagedReader, *, bytes_per_row: int | None = None) -> None:
        super().__init__()
        self.reader = reader
        self.bytes_per_row = bytes_per_row or self.DEFAULT_BYTES_PER_ROW
        self.cursor_offset = 0
        self.viewport_offset = 0
        self._overlays: list[tuple[int, int, str, str]] = []  # (start,end,name,type)
        self._covered_ranges: list[tuple[int, int]] = []
        self._span_index: SpanIndex | None = None
        self._selected_spans: list[tuple[int, int]] = []
        # Diff index for changed bytes
        self._diff_index: DiffIndex | None = None
        # Frequency overlay
        self._freq_counts = None
        self._freq_n: int = 0
        # Search hits overlay
        # Format: list of (offset, length, role) tuples
        # role can be "hit" (simple hit), "length" (length marker), or "payload" (payload region)
        self._search_spans: list[tuple[int, int, str]] = []
        self._search_span_index: SearchSpanIndex | None = None

    # ---- Scrolling helpers ----
    def total_rows(self) -> int:
        if self.reader.size == 0:
            return 1
        return int(ceil(self.reader.size / self.bytes_per_row))

    def visible_rows(self) -> int:
        # Fallback to 16 rows if height is unknown yet.
        h = self.size.height or 0
        return max(16, h)

    def top_offset(self) -> int:
        # Keep viewport_offset as the source of truth; sync scroll_rows for compatibility
        self.scroll_rows = self.viewport_offset // self.bytes_per_row
        return self.viewport_offset

    def set_top_row(self, row: int) -> None:
        max_top = max(0, self.total_rows() - 1)
        self.scroll_rows = max(0, min(row, max_top))
        self.viewport_offset = self.scroll_rows * self.bytes_per_row
        self.refresh()

    def scroll_by(self, delta_rows: int) -> None:
        self.set_top_row(self.scroll_rows + delta_rows)

    def page_by(self, delta_pages: int) -> None:
        self.scroll_by(delta_pages * self.visible_rows())

    def _collect_chunk_boundaries(self) -> dict[int, set[str]]:
        """Collect all chunk payload boundaries from parsed schema.

        Returns dict mapping byte offset -> set of marker types:
        - "start": payload start (╎)
        - "end": payload end (┆)
        - "length": length field (•)
        """
        boundaries: dict[int, set[str]] = {}
        if self._span_index is None:
            return boundaries

        # Iterate through all spans looking for chunk nodes
        for span in self._span_index._spans:
            # Check if this span belongs to a chunk by examining the path
            if ".payload" in span.path:
                # This is a payload node - mark its boundaries
                payload_start = span.offset
                payload_end = span.offset + span.length
                boundaries.setdefault(payload_start, set()).add("start")
                boundaries.setdefault(payload_end, set()).add("end")

                # Also try to find the corresponding length field
                # Length field is at chunk base (before payload)
                # Parse path to get chunk base: "chunk_01.payload" -> "chunk_01.length"
                base_path = span.path.rsplit(".payload", 1)[0]
                length_path = f"{base_path}.length"

                # Find the length span
                for length_span in self._span_index._spans:
                    if length_span.path == length_path:
                        boundaries.setdefault(length_span.offset, set()).add("length")
                        break

        return boundaries

    def _render_gutter(self, boundaries: dict[int, set[str]], row_start: int, row_end: int) -> str:
        """Render 2-character gutter marker for a row.

        Checks if any byte in [row_start, row_end) has chunk boundary markers.
        Priority: start+end (╳), start (╎), end (┆), length (•), none (  )
        """
        markers_in_row: set[str] = set()
        for offset in range(row_start, row_end):
            if offset in boundaries:
                markers_in_row.update(boundaries[offset])

        # Combine markers with priority
        if "start" in markers_in_row and "end" in markers_in_row:
            return "╳ "  # Both start and end
        if "start" in markers_in_row:
            return "╎ "  # Payload start
        if "end" in markers_in_row:
            return "┆ "  # Payload end
        if "length" in markers_in_row:
            return "• "  # Length field
        return "  "  # No marker

    # ---- Rendering ----
    def render(self) -> Text:
        # Determine rows to render
        start_row = self.scroll_rows
        rows = self.visible_rows()
        bpr = self.bytes_per_row

        # If height not yet known, show at least first 256 bytes (16 rows)
        if self.size.height == 0:
            start_row = 0
            rows = max(rows, 16)

        # Collect chunk boundaries for gutter markers
        chunk_boundaries = self._collect_chunk_boundaries()

        text = Text()
        for i in range(rows):
            offset = (start_row + i) * bpr
            if offset >= self.reader.size:
                break
            chunk = self.reader.read(offset, bpr)
            if not chunk and i > 0:
                break

            # Compute gutter marker for this row
            # Check start and end of row for boundary markers
            row_start = offset
            row_end = offset + bpr
            gutter = self._render_gutter(chunk_boundaries, row_start, row_end)

            # Build the line with stylable segments
            line = Text(gutter + f"{offset:08X}  ")
            # Hex cells
            # overlay no longer used for styling
            for idx, b in enumerate(chunk):
                cell = f"{b:02X}"
                sep = " " if idx < bpr - 1 else ""
                style = None
                cur_off = offset + idx
                # Backgrounds: cursor / selection
                is_cursor = cur_off == self.cursor_offset
                in_sel = any(s <= cur_off < s + ln for (s, ln) in self._selected_spans)
                if is_cursor:
                    style = Style(bgcolor=PALETTE.hex_cursor_bg, color=PALETTE.hex_selected_fg)
                elif in_sel:
                    # Check if selection is over a payload/target_preview region
                    # Preserve text color if so
                    search_role = self._get_search_span_role(cur_off)
                    if search_role in ("payload", "target_preview"):
                        fg = self._byte_fg(cur_off)
                        style = Style(bgcolor=PALETTE.search_payload_bg, color=fg)
                    else:
                        style = Style(
                            bgcolor=PALETTE.hex_selection_bg,
                            color=PALETTE.hex_selected_fg,
                        )
                else:
                    # Text color by span type / unmapped
                    fg = self._byte_fg(cur_off)
                    bg = None

                    # Check search span role
                    search_role = self._get_search_span_role(cur_off)

                    # Search hit (length/pointer field) takes precedence
                    # for text color (bright green)
                    if search_role in ("hit", "length", "pointer"):
                        style = Style(color=PALETTE.search_hit_fg, bold=True)
                    # Payload/target_preview region gets background highlight, preserves text color
                    elif search_role in ("payload", "target_preview"):
                        bg = PALETTE.search_payload_bg
                        style = Style(color=fg, bgcolor=bg)
                    # Diff underline or frequency overlay
                    elif self._is_changed(cur_off):
                        style = Style(color=fg, underline=True)
                    elif self._freq_n > 1:
                        lvl = self._freq_level(cur_off)
                        if lvl == 1:
                            style = Style(color=PALETTE.freq_low_fg)
                        elif lvl == 2:
                            style = Style(color=PALETTE.freq_mid_fg)
                        elif lvl == 3:
                            style = Style(color=PALETTE.freq_high_fg, bold=True)
                        else:
                            style = Style(color=fg)
                    else:
                        style = Style(color=fg)
                line.append(cell, style=style)
                if idx < bpr - 1:
                    # Style the inter-cell space with same bg if current or next byte
                    # is selected/cursor to create a continuous highlight block.
                    next_off = cur_off + 1
                    next_is_cursor = next_off == self.cursor_offset
                    next_in_sel = any(s <= next_off < s + ln for (s, ln) in self._selected_spans)
                    sep_style = None
                    if is_cursor or next_is_cursor:
                        sep_style = Style(
                            bgcolor=PALETTE.hex_cursor_bg,
                            color=PALETTE.hex_selected_fg,
                        )
                    elif in_sel or next_in_sel:
                        # Check if either byte is in a payload/target_preview region
                        cur_role = self._get_search_span_role(cur_off)
                        next_role = self._get_search_span_role(next_off)
                        if (
                            cur_role in ("payload", "target_preview")
                            or next_role in ("payload", "target_preview")
                        ):
                            sep_style = Style(bgcolor=PALETTE.search_payload_bg)
                        else:
                            sep_style = Style(
                                bgcolor=PALETTE.hex_selection_bg,
                                color=PALETTE.hex_selected_fg,
                            )
                    else:
                        # Check if current or next byte is in a payload region
                        cur_role = self._get_search_span_role(cur_off)
                        next_role = self._get_search_span_role(next_off)
                        if cur_role == "payload" or next_role == "payload":
                            sep_style = Style(bgcolor=PALETTE.search_payload_bg)
                        # Diff: underline the separator if either adjacent byte changed
                        elif self._is_changed(cur_off) or self._is_changed(next_off):
                            sep_style = Style(color=PALETTE.diff_changed_punct, underline=True)
                    line.append(sep, style=sep_style)
            # Pad remaining hex cells
            for pad in range(len(chunk), bpr):
                line.append("  ")
                if pad < bpr - 1:
                    line.append(" ")

            # ASCII gutter
            line.append("  |")
            for idx, b in enumerate(chunk):
                ch = chr(b) if 32 <= b <= 126 else "."
                cur_off = offset + idx
                if cur_off == self.cursor_offset:
                    style = Style(bgcolor=PALETTE.hex_cursor_bg, color=PALETTE.hex_selected_fg)
                elif any(s <= cur_off < s + ln for (s, ln) in self._selected_spans):
                    # Check if selection is over a payload/target_preview region
                    # Preserve text color if so
                    search_role = self._get_search_span_role(cur_off)
                    if search_role in ("payload", "target_preview"):
                        fg = self._byte_fg(cur_off)
                        style = Style(bgcolor=PALETTE.search_payload_bg, color=fg)
                    else:
                        style = Style(
                            bgcolor=PALETTE.hex_selection_bg,
                            color=PALETTE.hex_selected_fg,
                        )
                else:
                    fg = self._byte_fg(cur_off)
                    bg = None

                    # Check search span role
                    search_role = self._get_search_span_role(cur_off)

                    # Search hit (length field) takes precedence for text color
                    if search_role in ("hit", "length"):
                        style = Style(color=PALETTE.search_hit_fg, bold=True)
                    # Payload region gets background highlight, preserves text color
                    elif search_role == "payload":
                        bg = PALETTE.search_payload_bg
                        style = Style(color=fg, bgcolor=bg)
                    elif self._is_changed(cur_off):
                        style = Style(color=fg, underline=True)
                    elif self._freq_n > 1:
                        lvl = self._freq_level(cur_off)
                        if lvl == 1:
                            style = Style(color=PALETTE.freq_low_fg)
                        elif lvl == 2:
                            style = Style(color=PALETTE.freq_mid_fg)
                        elif lvl == 3:
                            style = Style(color=PALETTE.freq_high_fg, bold=True)
                        else:
                            style = Style(color=fg)
                    else:
                        style = Style(color=fg)
                line.append(ch, style=style)
            line.append("|")

            text.append(line)
            text.append("\n")

        if len(text.plain) == 0:
            return Text("<empty>")
        # Remove final newline for cleaner render
        if text.plain.endswith("\n"):
            text = text[:-1]
        return text

    @staticmethod
    def _format_hex(data: bytes, width: int) -> str:
        # Two-digit uppercase hex, pad to width
        cells = [f"{b:02X}" for b in data]
        if len(cells) < width:
            cells += ["  "] * (width - len(cells))
        # Grouping can be added later; for now simple spacing
        return " ".join(cells)

    @staticmethod
    def _format_ascii(data: bytes) -> str:
        def conv(b: int) -> str:
            return chr(b) if 32 <= b <= 126 else "."

        return "".join(conv(b) for b in data).ljust(len(data))

    # ---- Cursor movement ----
    def move_cursor(self, delta: int) -> None:
        if self.reader.size == 0:
            self.cursor_offset = 0
            return
        new = self.cursor_offset + delta
        new = max(0, min(new, self.reader.size - 1))
        self.cursor_offset = new
        self.ensure_cursor_visible()
        self.refresh()
        # Notify app for linking to parsed tree
        if hasattr(self.app, "on_hex_cursor_moved"):
            with suppress(Exception):
                self.app.on_hex_cursor_moved(self.cursor_offset)  # type: ignore[attr-defined]

    def set_cursor(self, offset: int) -> None:
        if self.reader.size == 0:
            self.cursor_offset = 0
        else:
            self.cursor_offset = max(0, min(offset, self.reader.size - 1))
        self.ensure_cursor_visible()
        self.refresh()
        if hasattr(self.app, "on_hex_cursor_moved"):
            with suppress(Exception):
                self.app.on_hex_cursor_moved(self.cursor_offset)  # type: ignore[attr-defined]

    def set_selected_spans(self, spans: list[tuple[int, int]] | None) -> None:
        self._selected_spans = [s for s in (spans or []) if s[1] > 0]
        self.refresh()

    def ensure_cursor_visible(self) -> None:
        bpr = self.bytes_per_row
        top = self.viewport_offset
        bottom = top + self.visible_rows() * bpr - 1
        if self.cursor_offset < top:
            self.viewport_offset = (self.cursor_offset // bpr) * bpr
            self.scroll_rows = self.viewport_offset // bpr
        elif self.cursor_offset > bottom:
            row = self.cursor_offset // bpr
            # place cursor's row at bottom-keeping alignment
            top_row = row - self.visible_rows() + 1
            self.set_top_row(max(0, top_row))

    # ---- Overlays ----
    def set_overlays(self, regions: list[tuple[int, int, str, str]]) -> None:
        # keep ranges for field lookup only
        covered_simple: list[tuple[int, int]] = []
        simple: list[tuple[int, int, str, str]] = []
        for (start, length, name, typ) in regions:
            end = start + max(0, length)
            simple.append((start, end, name, typ))
            covered_simple.append((start, end))
        self._overlays = simple
        self._covered_ranges = covered_simple
        self.refresh()

    def _overlay_for_range(self, start: int, length: int) -> list[Style | None] | None:
        if not self._overlays:
            return None
        out: list[Style | None] = [None] * length
        for (s, e, _n, _t) in self._overlays:
            if e <= start or s >= start + length:
                continue
            # overlap
            for i in range(max(s, start), min(e, start + length)):
                out[i - start] = None
        return out

    def _coverage_for_range(self, start: int, length: int) -> list[bool] | None:
        if not self._covered_ranges:
            return [False] * length
        covered = [False] * length
        for (s, e) in self._covered_ranges:
            if e <= start or s >= start + length:
                continue
            for i in range(max(s, start), min(e, start + length)):
                covered[i - start] = True
        return covered

    def field_at(self, offset: int) -> tuple[str, str] | None:
        for (s, e, name, typ) in self._overlays:
            if s <= offset < e:
                return (name, typ)
        return None

    # ---- Diff overlay API ----
    def set_diff_regions(self, regions: list[tuple[int, int]]) -> None:
        self._diff_index = DiffIndex(regions)
        self.refresh()

    def _is_changed(self, off: int) -> bool:
        return self._diff_index.contains(off) if self._diff_index is not None else False

    def set_frequency_map(self, counts, n: int) -> None:
        self._freq_counts = counts
        self._freq_n = int(n)
        self.refresh()

    def clear_frequency_map(self) -> None:
        self._freq_counts = None
        self._freq_n = 0
        self.refresh()

    def _freq_level(self, off: int) -> int:
        if not self._freq_counts or self._freq_n <= 1:
            return 0
        if off < 0 or off >= len(self._freq_counts):
            return 0
        cnt = int(self._freq_counts[off])
        if cnt <= 0:
            return 0
        pct = cnt / self._freq_n * 100.0
        if pct <= 25.0:
            return 1
        if pct <= 75.0:
            return 2
        return 3

    # ---- Search hits overlay API ----
    def set_search_hits(self, hits: list[tuple[int, int]]) -> None:
        """Set search hit regions (offset, length). Legacy API for simple hits."""
        self._search_spans = [(off, ln, "hit") for (off, ln) in hits]
        self._search_span_index = SearchSpanIndex(self._search_spans)
        self.refresh()

    def set_search_spans(self, spans: list[tuple[int, int, str]]) -> None:
        """Set search hit spans with roles (offset, length, role)."""
        self._search_spans = spans
        self._search_span_index = SearchSpanIndex(spans)
        self.refresh()

    def clear_search_hits(self) -> None:
        """Clear search hit highlighting."""
        self._search_spans = []
        self._search_span_index = None
        self.refresh()

    def _get_search_span_role(self, off: int) -> str | None:
        """Get the role of the search span at this offset, or None if not in a search span."""
        if self._search_span_index is None:
            return None
        return self._search_span_index.get_role(off)

    def _is_search_hit(self, off: int) -> bool:
        """Check if byte offset is within any search hit (for backwards compatibility)."""
        role = self._get_search_span_role(off)
        return role in ("hit", "length")

    def set_span_index(self, index: SpanIndex | None) -> None:
        self._span_index = index
        self.refresh()

    def set_selected_span(self, span: tuple[int, int] | None) -> None:
        self._selected_span = span
        self.refresh()

    def _get_default_color_for_group(self, group: str) -> str:
        """Get default color for a type group."""
        if group == "int":
            return PALETTE.hex_type_int_fg
        if group == "float":
            return PALETTE.hex_type_float_fg
        if group == "string":
            return PALETTE.hex_type_string_fg
        if group == "bytes":
            return PALETTE.hex_type_bytes_fg
        return PALETTE.parsed_value

    def _byte_fg(self, off: int) -> str:
        # Determine text color for a byte
        if self._span_index is None:
            covered = any(s <= off < e for (s, e) in self._covered_ranges)
            return PALETTE.hex_unmapped_fg if not covered else PALETTE.parsed_value
        sp = self._span_index.find(off)
        if sp is None:
            return PALETTE.hex_unmapped_fg

        # Check for explicit color override first
        if sp.color_override is not None:
            # Map common color variations to Rich-compatible names
            color = sp.color_override.lower()
            # Rich uses "bright_black" for gray, but also accepts "grey"
            color_map = {
                "gray": "grey",  # Map gray to grey (Rich standard)
            }
            color = color_map.get(color, color)

            # Validate that Rich can handle this color by attempting to create a Style
            # If it fails, fall back to default type-based color
            try:
                Style(color=color)  # Test if color is valid
                return color
            except Exception:
                # Color is invalid for Rich, fall back to type-based color
                return self._get_default_color_for_group(sp.group)

        # Otherwise use type-based coloring
        return self._get_default_color_for_group(sp.group)

    # ---- Actions (bound in BINDINGS) ----
    def action_cursor_left(self) -> None:
        self.move_cursor(-1)

    def action_cursor_right(self) -> None:
        self.move_cursor(1)

    def action_cursor_up(self) -> None:
        self.move_cursor(-self.bytes_per_row)

    def action_cursor_down(self) -> None:
        self.move_cursor(self.bytes_per_row)

    def action_page_up(self) -> None:
        # Calculate cursor's relative position within current viewport
        top_before = self.top_offset()
        bpr = self.bytes_per_row
        cursor_row_offset = (self.cursor_offset - top_before) // bpr
        cursor_col_offset = (self.cursor_offset - top_before) % bpr

        # Page up
        self.page_by(-1)

        # Move cursor to maintain relative position in new viewport
        top_after = self.top_offset()
        new_cursor = top_after + cursor_row_offset * bpr + cursor_col_offset
        self.set_cursor(new_cursor)

    def action_page_down(self) -> None:
        # Calculate cursor's relative position within current viewport
        top_before = self.top_offset()
        bpr = self.bytes_per_row
        cursor_row_offset = (self.cursor_offset - top_before) // bpr
        cursor_col_offset = (self.cursor_offset - top_before) % bpr

        # Page down
        self.page_by(1)

        # Move cursor to maintain relative position in new viewport
        top_after = self.top_offset()
        new_cursor = top_after + cursor_row_offset * bpr + cursor_col_offset
        self.set_cursor(new_cursor)

    def action_go_end(self) -> None:
        if self.reader.size > 0:
            self.set_cursor(self.reader.size - 1)

    def action_go_start(self) -> None:
        self.set_cursor(0)

    def action_open_search(self) -> None:
        if hasattr(self.app, "action_open_search"):
            self.app.action_open_search()  # type: ignore[attr-defined]

    def action_search_next(self) -> None:
        # Check if lens search is active first (takes precedence)
        if (
            hasattr(self.app, "_search_state")
            and hasattr(self.app, "action_search_next_hit")
            and self.app._search_state.is_active()  # type: ignore[attr-defined]
        ):
            self.app.action_search_next_hit()  # type: ignore[attr-defined]
            return
        # Fall back to old-style search
        if hasattr(self.app, "action_search_next"):
            self.app.action_search_next()  # type: ignore[attr-defined]

    def action_open_compare_strings(self) -> None:
        if hasattr(self.app, "action_open_compare_strings"):
            self.app.action_open_compare_strings()  # type: ignore[attr-defined]

    def on_key(self, event) -> None:  # type: ignore[override]
        # Handle 'g' sequences locally so the Footer still shows HexView bindings
        key = event.key
        if key == "g":
            # Show hint and wait for next key (g or o)
            if hasattr(self.app, "set_status_hint"):
                self.app.set_status_hint("[g: g=start, o=goto]")  # type: ignore[attr-defined]
            self._pending_g = True  # type: ignore[attr-defined]
            event.prevent_default()
            return
        if key.lower() == "o" and getattr(self, "_pending_g", False):
            self._pending_g = False  # type: ignore[attr-defined]
            if hasattr(self.app, "set_status_hint"):
                self.app.set_status_hint("")  # type: ignore[attr-defined]
            if hasattr(self.app, "action_open_goto"):
                self.app.action_open_goto()  # type: ignore[attr-defined]
            event.prevent_default()
            return
        if key == "G":
            self.action_go_end()
            event.prevent_default()
            return
        if key == "g" and getattr(self, "_pending_g", False):
            # gg -> start of file
            self._pending_g = False  # type: ignore[attr-defined]
            if hasattr(self.app, "set_status_hint"):
                self.app.set_status_hint("")  # type: ignore[attr-defined]
            self.action_go_start()
            event.prevent_default()
            return
