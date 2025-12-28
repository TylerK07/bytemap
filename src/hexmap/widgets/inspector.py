from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from hexmap.core.inspect import (
    ascii_preview,
    c_string_guess,
    decode_floats,
    decode_ints,
    read_bytes,
)
from hexmap.core.io import PagedReader
from hexmap.core.spans import SpanIndex
from hexmap.ui.palette import PALETTE


class Inspector(Static):
    """Byte inspector for decoding values at the hex cursor with scannable layout."""

    BINDINGS = [("I", "toggle_mode", "Mode")]

    def __init__(self) -> None:
        super().__init__(Text("Inspector"))
        self._compact = False
        self._default_endian = "little"
        self._last = None
        self._scope: str = "explore"
        self._search_mode = False
        self._search_content: Text | None = None

    def set_scope(self, scope: str) -> None:
        # scope: "explore" or "diff"
        self._scope = scope

    def set_search_content(self, content: Text) -> None:
        """Set search-specific content (overrides normal inspector)."""
        self._search_mode = True
        self._search_content = content
        self.update(content)

    def clear_search_content(self) -> None:
        """Clear search content and return to normal mode."""
        self._search_mode = False
        self._search_content = None
        # Trigger refresh with last known state if available
        if self._last:
            self._refresh_view()

    def set_default_endian(self, endian: str | None) -> None:
        if endian in ("little", "big"):
            self._default_endian = endian or "little"

    def update_for(
        self,
        reader: PagedReader,
        offset: int,
        span_index: SpanIndex | None,
        selected_spans: list[tuple[int, int]] | None,
        *,
        endian: str | None = None,
        compare: PagedReader | None = None,
    ) -> None:
        # Don't override search content
        if self._search_mode:
            return

        if endian in ("little", "big"):
            self._default_endian = endian or self._default_endian
        raw8 = read_bytes(reader, offset, 8)
        raw16 = read_bytes(reader, offset, 16)
        ints = decode_ints(raw8)
        floats = decode_floats(raw8)
        # Optional compare values (B)
        brow8 = read_bytes(compare, offset, 8) if compare is not None else None  # type: ignore[arg-type]
        bints = decode_ints(brow8 or b"") if brow8 is not None else None
        ascii16 = ascii_preview(raw16)
        cguess = c_string_guess(read_bytes(reader, offset, 32))
        within_path = None
        within_group = None
        within_endian = None
        within_endian_source = None
        within_color = None
        if span_index is not None:
            sp = span_index.find(offset)
            if sp is not None:
                within_path = sp.path
                within_group = sp.group
                within_endian = sp.effective_endian
                within_endian_source = sp.endian_source
                within_color = sp.color_override
        total_sel = sum(ln for (_s, ln) in (selected_spans or [])) if selected_spans else 0
        self._last = (
            offset,
            within_path,
            within_group,
            total_sel,
            raw16,
            ascii16,
            cguess,
            ints,
            floats,
            brow8,
            bints,
            within_endian,
            within_endian_source,
            within_color,
        )
        self._refresh_view()

    def action_toggle_mode(self) -> None:
        self._compact = not self._compact
        self._refresh_view()

    def toggle_mode(self) -> None:  # for tests
        self.action_toggle_mode()

    def _refresh_view(self) -> None:
        if self._last is None:
            return
        (
            offset,
            within_path,
            within_group,
            total_sel,
            raw16,
            ascii16,
            cguess,
            ints,
            floats,
            brow8,
            bints,
            within_endian,
            within_endian_source,
            within_color,
        ) = self._last
        t = Text()
        # Context
        # Update inspector header bar in the App: left shows offset/within, right shows mode
        left_header = (
            f"@0x{offset:08X} ({offset})   Within: {within_path if within_path else 'Unmapped'}"
        )
        try:
            if hasattr(self.app, "update_inspector_header"):
                self.app.update_inspector_header(  # type: ignore[attr-defined]
                    self._scope, left_header, ("Compact" if self._compact else "Full")
                )
        except Exception:
            pass
        # Selection summary within inspector body
        if total_sel:
            t.append("   Selection: ", style=PALETTE.inspector_label)
            t.append(f"{total_sel} bytes", style=PALETTE.inspector_value)
        t.append("\n")
        # Display endian info if within a mapped field
        if within_path and within_endian:
            t.append("      Endian: ", style=PALETTE.inspector_label)
            endian_display = within_endian
            if within_endian_source:
                # Show source with friendly names
                source_map = {
                    "field": "field override",
                    "type": "type definition",
                    "parent": "parent container",
                    "root": "schema root",
                    "default": "default",
                }
                source_text = source_map.get(within_endian_source, within_endian_source)
                endian_display += f" (from {source_text})"
            t.append(endian_display + "\n", style=PALETTE.inspector_value)
        # Display color override if within a mapped field
        if within_path and within_color:
            t.append("       Color: ", style=PALETTE.inspector_label)
            t.append(f"{within_color} (override)\n", style=PALETTE.inspector_value)
        t.append("Bytes (16): ", style=PALETTE.inspector_label)
        t.append(" ".join(f"{b:02X}" for b in raw16) + "\n", style=PALETTE.inspector_value)
        t.append("ASCII (16): ", style=PALETTE.inspector_label)
        t.append(ascii16 + "\n", style=PALETTE.inspector_value)
        if cguess is not None:
            s, ln = cguess
            t.append("CString: ", style=PALETTE.inspector_label)
            t.append(f'"{s}" ({ln})\n', style=PALETTE.inspector_value)

        # Diff (A/B) byte and typed deltas when compare provided
        if brow8 is not None:
            if len(raw16) and len(brow8):
                a0 = raw16[0]
                b0 = brow8[0]
                if a0 == b0:
                    t.append("Diff: ", style=PALETTE.inspector_label)
                    t.append("unchanged\n", style=PALETTE.inspector_dim)
                else:
                    delta = int(b0) - int(a0)
                    t.append("Diff: ", style=PALETTE.inspector_label)
                    t.append(
                        f"A=0x{a0:02X}  B=0x{b0:02X}  Δ={delta:+d}\n",
                        style=PALETTE.inspector_value,
                    )
            # Typed diffs for u16/u32 le/be
            pref = "le" if self._default_endian == "little" else "be"
            def add_typed(label: str, key: str) -> None:
                if key in ints and bints is not None and key in bints:
                    da = ints[key]
                    db = bints[key]
                    dd = int(db) - int(da)
                    t.append(f"{label} ", style=PALETTE.parsed_type)
                    t.append(f"A={da} B={db} Δ={dd:+d}\n", style=PALETTE.inspector_value)
            if bints is not None:
                add_typed(f"u16{pref}", f"u16{pref}")
                add_typed(f"i16{pref}", f"i16{pref}")
                add_typed(f"u32{pref}", f"u32{pref}")
                add_typed(f"i32{pref}", f"i32{pref}")

        # Likely
        likely_lines: list[str] = []
        if cguess is not None:
            likely_lines.append(f'string: "{cguess[0]}" ({cguess[1]})')
        pref = "le" if self._default_endian == "little" else "be"
        for k in (f"u32{pref}", f"i32{pref}", f"u16{pref}", f"i16{pref}"):
            if k in ints and len(likely_lines) < 3:
                likely_lines.append(f"{k:5}: {ints[k]}")
        for k in (f"f32{pref}", f"f64{pref}"):
            if k in floats and len(likely_lines) < 3:
                v = floats[k]
                if v == v and v != float("inf") and v != float("-inf") and abs(v) < 1e9:
                    likely_lines.append(f"{k:5}: {v:.6g}")
        if likely_lines:
            t.append("Likely:\n", style=PALETTE.inspector_header)
            for line in likely_lines[:3]:
                t.append("  " + line + "\n", style=PALETTE.inspector_value)

        if not self._compact:
            t.append("Integers:\n", style=PALETTE.inspector_header)
            def add_row(label: str, vals: list[tuple[str, str]]) -> None:
                row = Text("  ")
                row.append(f"{label:<4}", style=PALETTE.inspector_label)
                for (sub, val) in vals:
                    row.append(f" {sub:<2} ", style=PALETTE.inspector_dim)
                    width = 20 if sub == "LE" else 12
                    row.append(f"{val:<{width}}", style=PALETTE.inspector_value)
                row.append("\n")
                t.append(row)
            if "u8" in ints:
                add_row("u8", [(" ", str(ints["u8"]))])
            if "i8" in ints:
                add_row("i8", [(" ", str(ints["i8"]))])
            for base in ("u16", "i16", "u32", "i32", "u64", "i64"):
                vals = []
                for sub in ("LE", "BE"):
                    key = f"{base}{sub.lower()}"
                    if key in ints:
                        vals.append((sub, str(ints[key])))
                if vals:
                    add_row(base, vals)
            t.append("Floats:\n", style=PALETTE.inspector_header)
            for base in ("f32", "f64"):
                vals = []
                for sub in ("LE", "BE"):
                    key = f"{base}{sub.lower()}"
                    if key in floats:
                        vals.append((sub, f"{floats[key]:.6g}"))
                if vals:
                    add_row(base, vals)
        self.update(t)
