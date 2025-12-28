from __future__ import annotations
# ruff: noqa: I001  # keep imports grouped for clarity across stdlib/third-party/local

import os
from dataclasses import dataclass
from contextlib import suppress

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Static

from hexmap.core.io import PagedReader
from hexmap.core.numbers import (
    NumCell,
    array_summary,
    decode_float,
    decode_int,
    decode_int_array,
)
from hexmap.core.strings import ascii_fixed, decode_cstring_fixed_slot
from hexmap.widgets.byte_strip import ByteStrip

# Import date decoding functions
import struct
from datetime import datetime, timedelta


def _decode_date(reader: PagedReader, offset: int, fmt: str) -> str:
    """Decode date at offset using specified format."""
    try:
        if fmt == "unix_s":
            data = reader.read(offset, 4)
            if len(data) < 4:
                return "—"
            val = struct.unpack("<I", data)[0]
            dt = datetime(1970, 1, 1) + timedelta(seconds=val)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        elif fmt == "unix_ms":
            data = reader.read(offset, 8)
            if len(data) < 8:
                return "—"
            val = struct.unpack("<Q", data)[0]
            dt = datetime(1970, 1, 1) + timedelta(milliseconds=val)
            return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        elif fmt == "filetime":
            data = reader.read(offset, 8)
            if len(data) < 8:
                return "—"
            val = struct.unpack("<Q", data)[0]
            # FILETIME: 100-nanosecond intervals since 1601-01-01
            dt = datetime(1601, 1, 1) + timedelta(microseconds=val / 10)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        elif fmt == "dos_date":
            data = reader.read(offset, 2)
            if len(data) < 2:
                return "—"
            val = struct.unpack("<H", data)[0]
            day = val & 0x1F
            month = (val >> 5) & 0x0F
            year = 1980 + ((val >> 9) & 0x7F)
            if month == 0 or month > 12 or day == 0 or day > 31:
                return f"[invalid: 0x{val:04X}]"
            return f"{year:04d}-{month:02d}-{day:02d}"
        elif fmt == "dos_datetime":
            data = reader.read(offset, 4)
            if len(data) < 4:
                return "—"
            time_val = struct.unpack("<H", data[:2])[0]
            date_val = struct.unpack("<H", data[2:4])[0]
            sec = (time_val & 0x1F) * 2
            minute = (time_val >> 5) & 0x3F
            hour = (time_val >> 11) & 0x1F
            day = date_val & 0x1F
            month = (date_val >> 5) & 0x0F
            year = 1980 + ((date_val >> 9) & 0x7F)
            if month == 0 or month > 12 or day == 0 or day > 31:
                return f"[invalid date: 0x{date_val:04X}]"
            return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{sec:02d}"
        elif fmt == "ole_date":
            data = reader.read(offset, 8)
            if len(data) < 8:
                return "—"
            val = struct.unpack("<d", data)[0]
            # OLE DATE: days since 1899-12-30
            dt = datetime(1899, 12, 30) + timedelta(days=val)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        elif fmt == "ftm_packed":
            data = reader.read(offset, 4)
            if len(data) < 4:
                return "—"
            val = struct.unpack("<I", data)[0]
            year = (val >> 20) & 0xFFF
            month = (val >> 16) & 0x0F
            day = (val >> 11) & 0x1F
            hour = (val >> 6) & 0x1F
            minute = val & 0x3F
            if year == 0 or month == 0 or month > 12 or day == 0 or day > 31:
                return f"[invalid: 0x{val:08X}]"
            return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}"
        else:
            return "—"
    except Exception:
        return "[error]"


@dataclass(frozen=True)
class FileCol:
    name: str
    reader: PagedReader
    is_baseline: bool = False


class CompareStringsModal(ModalScreen[None]):
    """Compare & Interpret — unified Strings + Numbers."""

    DEFAULT_N = 16
    DEFAULT_M = 64
    MIN_N = 1
    MAX_N = 256
    MIN_M = 2
    MAX_M = 512

    BINDINGS = [
        ("up", "select_prev", "Select Up"),
        ("down", "select_next", "Select Down"),
        ("left", "adjust_small_dec", "Adjust -1"),
        ("right", "adjust_small_inc", "Adjust +1"),
        ("shift+left", "adjust_big_dec", "Adjust -4"),
        ("shift+right", "adjust_big_inc", "Adjust +4"),
        ("enter", "commit", "Add to schema"),
        ("shift+enter", "commit_and_jump", "Add+Jump"),
        ("escape", "close", "Close"),
    ]

    def __init__(
        self,
        files: list[tuple[str, PagedReader, bool]],
        offset: int,
        selection_span: tuple[int, int] | None,
    ) -> None:
        super().__init__()
        self._files = [FileCol(n, r, b) for (n, r, b) in files]
        self._offset = int(offset)
        self._sel = selection_span if (selection_span and selection_span[1] > 0) else None
        self._n = self._sel[1] if self._sel else self.DEFAULT_N
        self._unit_len = self._sel[1] if self._sel else self._n
        self._m = self.DEFAULT_M
        # 0=ascii, 1=cstring, >=2 numeric rows
        self._row_index = 0
        self._chosen_row = None  # mark ✓ when committed/matching schema
        # Cache per-file reads for responsiveness at this offset
        self._cache_ascii: dict[str, str] = {}
        self._cache_cstr: dict[str, tuple[str, bool, int, bool]] = {}
        # Precompute names for headers
        self._col_labels: list[str] = []
        for f in self._files:
            base = os.path.basename(f.name)
            star = "★ " if f.is_baseline else "✓ "
            self._col_labels.append(f"{star}{base}")
        # DataTable keys
        self._col_keys: list[object] = []
        self._row_keys: list[object] = []
        self._columns_ready: bool = False

    # ---- Compose ----
    def compose(self) -> ComposeResult:  # type: ignore[override]
        title = self._title_text()
        self._title = Static(title, id="cmp-title")
        # Byte strip visualization
        self._strip = ByteStrip()
        from contextlib import suppress
        with suppress(Exception):
            self._strip.id = "cmp-strip"
        # Interpretation table
        # Interactive table
        self._dt = DataTable(id="cmp-table")
        # Visual style preferences
        with suppress(Exception):
            self._dt.cursor_type = "row"  # type: ignore[attr-defined]
        footer = Static(
            "↑/↓ Select  ←/→ ±1  Shift+←/→ ±4  Tab Focus  Enter Add  Shift+Enter Jump  Esc Close",
            id="cmp-footer",
        )
        with Container(id="cmp-root"):
            yield self._title
            # Byte strip above the table - wrapped in scroll with max height
            with VerticalScroll(id="cmp-strip-scroll"):
                yield self._strip
            # Table wrapper intended to fill remaining space
            with Container(id="cmp-table-wrap"):
                yield self._dt
            # Bottom controls: Field name + Instances
            default_name = f"string_0x{self._offset:08X}"
            with Container(id="cmp-name-row"):
                yield Static("Field name:", id="cmp-name-label")
                self._name_input = Input(value=default_name, placeholder="name", id="cmp-name")
                yield self._name_input
                yield Static("Instances:", id="cmp-instances-label")
                self._instances = 1
                self._instances_dirty = False
                self._inst_input = Input(
                    value=str(self._instances), placeholder="1", id="cmp-instances"
                )
                yield self._inst_input
            # Preview area
            self._preview = Static("", id="cmp-preview")
            yield self._preview
            # Warning area
            self._warn = Static("", id="cmp-warn")
            yield self._warn
            yield footer

    def on_mount(self) -> None:  # type: ignore[override]
        # Pick default row: prefer cstring if baseline terminates
        best = 1 if (self._get_cstr(self._files[0])[1]) else 0
        self._row_index = best
        def _do_init() -> None:
            self._refresh_all()
            self._select_row(self._row_index)
            self.set_focus(self._dt)
        try:
            self.call_after_refresh(_do_init)
        except Exception:
            _do_init()

    # ---- Actions ----
    def action_select_prev(self) -> None:
        self._select_row(self._row_index - 1)
        self._refresh_len_dependent_ui()

    def action_select_next(self) -> None:
        self._select_row(self._row_index + 1)
        self._refresh_len_dependent_ui()

    def _adjust(self, delta: int) -> None:
        # Determine active param by selected row; make arrows useful on any row
        rows = self._row_defs()
        rd = rows[self._row_index]
        kind = rd.get("kind")
        if kind in {"ascii", "cstring", "bytes"}:
            # Adjust the active unit length used by string/bytes previews
            new_len = int(self._unit_len) + int(delta)
            # Use the broader cstring cap for bounds so bytes/ascii can be larger too
            new_len = max(self.MIN_N, min(self.MAX_M, new_len))
            self._unit_len = new_len
            # Clear caches so all string/bytes rows reflect the new length
            self._cache_ascii.clear()
            self._cache_cstr.clear()
            self._refresh_len_dependent_ui()
            return
        if kind in {"int", "float"}:
            # Adjust instances count when on numeric rows for convenience
            cur = int(getattr(self, "_instances", 1))
            new_n = max(1, min(9999, cur + int(delta)))
            self._instances = new_n
            self._instances_dirty = True
            self._refresh_len_dependent_ui()
            return
        # Fallback: refresh to keep UI responsive even if no direct parameter
        self._refresh_len_dependent_ui()

    def action_adjust_small_dec(self) -> None:
        self._adjust(-1)

    def action_adjust_small_inc(self) -> None:
        self._adjust(+1)

    def action_adjust_big_dec(self) -> None:
        self._adjust(-4)

    def action_adjust_big_inc(self) -> None:
        self._adjust(+4)

    def action_commit(self) -> None:
        # Write to YAML schema editor via app helper
        try:
            rows = self._row_defs()
            rd = rows[self._row_index]
            name = (self._name_input.value or "").strip() if hasattr(self, "_name_input") else None
            ok = False
            if rd["kind"] in {"ascii", "cstring"}:
                inst = max(1, int(getattr(self, "_instances", 1)))
                slot_len = int(self._unit_len)
                if rd["kind"] == "cstring":
                    if hasattr(self.app, "commit_cstring_field"):
                        ok = self.app.commit_cstring_field(  # type: ignore[attr-defined]
                            self._offset, slot_len, inst, name or None
                        )
                else:
                    if hasattr(self.app, "commit_ascii_field"):
                        ok = self.app.commit_ascii_field(  # type: ignore[attr-defined]
                            self._offset, slot_len, inst, name or None
                        )
            elif rd["kind"] == "int" and hasattr(self.app, "commit_numeric_field"):
                base = "i" if rd.get("signed") else "u"
                bits = int(rd.get("bits", 8))
                type_name = f"{base}{bits}"
                inst = max(1, int(getattr(self, "_instances", 1)))
                if inst > 1 and hasattr(self.app, "commit_array_field"):
                    # Arrays only for numeric types
                    ok = self.app.commit_array_field(self._offset, type_name, inst, name or None)  # type: ignore[attr-defined]
                else:
                    ok = self.app.commit_numeric_field(self._offset, type_name, name or None)  # type: ignore[attr-defined]
                lbl = rd["label"]() if callable(rd["label"]) else str(rd["label"])  # type: ignore[index]
                if "(BE)" in lbl and hasattr(self.app, "current_schema_endian") and (
                    self.app.current_schema_endian() == "little"  # type: ignore[attr-defined]
                ):
                    cur = (self._warn.renderable or "").rstrip()
                    warn = (
                        "\n[warning] BE selected but schema is little-endian; "
                        "consider per-field endian"
                    )
                    self._warn.update(f"{cur}{warn}")
            elif rd["kind"] == "bytes":
                inst = max(1, int(getattr(self, "_instances", 1)))
                L = int(rd.get("length", int(self._unit_len)))
                if inst > 1 and hasattr(self.app, "commit_bytes_array_field"):
                    ok = self.app.commit_bytes_array_field(self._offset, L, inst, name or None)  # type: ignore[attr-defined]
                elif hasattr(self.app, "commit_bytes_field"):
                    ok = self.app.commit_bytes_field(self._offset, L, name or None)  # type: ignore[attr-defined]
            elif rd["kind"] == "date" and hasattr(self.app, "commit_date_field"):
                fmt = str(rd.get("format", ""))
                ok = self.app.commit_date_field(self._offset, fmt, name or None)  # type: ignore[attr-defined]
            elif rd["kind"] == "array" and hasattr(self.app, "commit_array_field"):
                bits = int(rd.get("bits", 16))
                count = int(rd.get("count", 0))
                lbl = rd["label"]() if callable(rd["label"]) else str(rd["label"])  # type: ignore[index]
                base = "i" if bool(rd.get("signed", False)) else "u"
                elem = f"{base}{bits}"
                if "(BE)" in lbl and hasattr(self.app, "current_schema_endian") and (
                    self.app.current_schema_endian() == "little"  # type: ignore[attr-defined]
                ):
                    cur = (self._warn.renderable or "").rstrip()
                    warn = (
                        "\n[warning] BE selected but schema endian is little; commit blocked"
                    )
                    self._warn.update(f"{cur}{warn}")
                    ok = False
                else:
                    ok = self.app.commit_array_field(self._offset, elem, count, name or None)  # type: ignore[attr-defined]
            if ok:
                self._chosen_row = self._row_index
                self._refresh_all()
        except Exception:
            pass

    def _committed_span_len(self, rd: dict) -> int:
        L = int(self._unit_len)
        kind = rd.get("kind")
        if kind == "bytes":
            return L
        if kind == "ascii":
            return L
        if kind == "array":
            bits = int(rd.get("bits", 16))
            count = int(rd.get("count", 0))
            return (bits // 8) * count
        if kind == "cstring":
            return 1
        if kind == "int":
            return int(rd.get("bits", 8)) // 8
        return 0

    def action_commit_and_jump(self) -> None:
        rows = self._row_defs()
        if not rows:
            return
        rd = rows[self._row_index]
        start = self._offset
        self.action_commit()
        jump = self._committed_span_len(rd)
        if jump > 0 and hasattr(self.app, "jump_cursor"):
            self.app.jump_cursor(start + jump)  # type: ignore[attr-defined]

    def action_close(self) -> None:
        self.dismiss(None)

    # ---- Rendering helpers ----
    def _title_text(self) -> str:
        pos = f"@0x{self._offset:08X}"
        ln = self._unit_len
        basis = "selection" if self._sel else "cursor"
        return f"Compare & Interpret    {pos}  len={ln}  ({basis})"

    def _refresh_all(self) -> None:
        self._title.update(self._title_text())
        # Rebuild table fully each refresh for stability
        self._rebuild_table()
        self._update_strip()
        self._render_table()
        self._refresh_preview()

    def _update_strip(self) -> None:
        # Update byte strip visualization with current unit length
        start = self._sel[0] if self._sel else self._offset
        selection = (start, int(self._unit_len))
        files = []
        for f in self._files:
            base = os.path.basename(f.name)
            star = "★ " if f.is_baseline else "✓ "
            files.append((f"{star}{base}", f.reader))
        self._strip.update_state(files, start, selection)

    def _refresh_len_dependent_ui(self) -> None:
        # Only refresh visuals and table dependent on unit length
        self._title.update(self._title_text())
        # Preserve selection key before rebuild
        prev_key = None
        try:
            rows = self._row_defs()
            rd = rows[self._row_index]
            prev_key = self._row_identity(rd)
        except Exception:
            prev_key = None
        self._rebuild_table()
        self._render_table()
        # Reselect matching row if possible
        try:
            rows = self._row_defs()
            idx = 0
            if prev_key is not None:
                for i, r in enumerate(rows):
                    if self._row_identity(r) == prev_key:
                        idx = i
                        break
            self._select_row(idx)
        except Exception:
            pass
        self._update_strip()
        # Ensure preview reflects the current selection/length as well
        self._refresh_preview()

    # candidates block removed in favor of Byte Strip

    def _get_ascii(self, f: FileCol) -> str:
        key = f.name
        if key not in self._cache_ascii:
            ln = int(self._unit_len)
            self._cache_ascii[key] = ascii_fixed(f.reader, self._offset, ln)
        return self._cache_ascii.get(key, "")

    def _get_cstr(self, f: FileCol) -> tuple[str, bool, int, bool]:
        # Deprecated legacy; now fallback to fixed-slot using current unit length
        L = int(self._unit_len)
        data = f.reader.read(self._offset, L)
        txt, term, used = decode_cstring_fixed_slot(data)
        return (txt, term, used, False)

    def _rebuild_table(self) -> None:
        # Clear columns and rows completely, then build fresh
        with suppress(Exception):
            self._dt.clear(columns=True)
        cols = ["Type", *self._col_labels]
        self._dt.add_columns(*cols)
        self._row_keys = []
        self._col_keys = list(range(len(cols)))

    def _row_defs(self) -> list[dict]:
        rows: list[dict] = []
        L = int(self._unit_len)
        # Strings
        rows.append(
            {
                "kind": "ascii",
                "label": lambda: f"ascii (fixed {L})",
            }
        )
        rows.append({"kind": "cstring", "label": lambda: f"cstring (len {L})", "length": L})
        # Bytes blob row
        rows.append({"kind": "bytes", "label": (lambda s=f"bytes (len {L})": s), "length": L})
        # Integers (8/16/32/64)
        int_specs = [
            ("u8", 8, False, None),
            ("i8", 8, True, None),
            ("u16 (LE)", 16, False, "little"),
            ("i16 (LE)", 16, True, "little"),
            ("u16 (BE)", 16, False, "big"),
            ("i16 (BE)", 16, True, "big"),
            ("u32 (LE)", 32, False, "little"),
            ("i32 (LE)", 32, True, "little"),
            ("u32 (BE)", 32, False, "big"),
            ("i32 (BE)", 32, True, "big"),
            ("u64 (LE)", 64, False, "little"),
            ("i64 (LE)", 64, True, "little"),
            ("u64 (BE)", 64, False, "big"),
            ("i64 (BE)", 64, True, "big"),
        ]
        for lbl, bits, signed, endian in int_specs:
            rows.append(
                {
                    "kind": "int",
                    "label": (lambda s=lbl: s),
                    "bits": bits,
                    "signed": signed,
                    "endian": endian,
                }
            )
        # Floats (optional)
        float_specs = [
            ("f32 (LE)", 32, "little"),
            ("f32 (BE)", 32, "big"),
            ("f64 (LE)", 64, "little"),
            ("f64 (BE)", 64, "big"),
        ]
        for lbl, bits, endian in float_specs:
            rows.append(
                {"kind": "float", "label": (lambda s=lbl: s), "bits": bits, "endian": endian}
            )
        # Date interpretations
        date_specs = [
            ("unix_s (u32)", "unix_s", 4, "little"),
            ("unix_ms (u64)", "unix_ms", 8, "little"),
            ("filetime (u64)", "filetime", 8, "little"),
            ("dos_date (u16)", "dos_date", 2, "little"),
            ("dos_datetime (4B)", "dos_datetime", 4, "little"),
            ("ole_date (f64)", "ole_date", 8, "little"),
            ("ftm_packed (4B)", "ftm_packed", 4, "little"),
        ]
        for lbl, fmt, req_bytes, endian in date_specs:
            rows.append(
                {
                    "kind": "date",
                    "label": (lambda s=lbl: s),
                    "format": fmt,
                    "req_bytes": req_bytes,
                    "endian": endian,
                }
            )
        return rows

    def _row_identity(self, rd: dict) -> tuple:
        kind = rd.get("kind")
        if kind in {"ascii", "cstring", "bytes"}:
            return (kind,)
        if kind == "int":
            return (
                kind,
                int(rd.get("bits", 0)),
                bool(rd.get("signed", False)),
                str(rd.get("endian", "")),
            )
        if kind == "array":
            return (
                kind,
                int(rd.get("bits", 0)),
                bool(rd.get("signed", False)),
                str(rd.get("endian", "")),
            )
        if kind == "float":
            return (kind, int(rd.get("bits", 0)), str(rd.get("endian", "")))
        if kind == "date":
            return (kind, str(rd.get("format", "")))
        return (str(kind),)

    def _maybe_suggest_instances(self, rd: dict) -> None:
        # Suggest instances if selection length divisible by type width, unless user edited
        if getattr(self, "_instances_dirty", False):
            return
        kind = rd.get("kind")
        if kind == "int":
            width = int(rd.get("bits", 8)) // 8
        elif kind == "float":
            width = int(rd.get("bits", 32)) // 8
        else:
            return
        L = int(self._unit_len)
        suggested = max(1, L // width) if width > 0 and L % width == 0 else 1
        self._instances = int(suggested)
        from contextlib import suppress
        with suppress(Exception):
            self._inst_input.value = str(self._instances)

    def _refresh_preview(self) -> None:
        # Build preview text based on selected row and instances
        rows = self._row_defs()
        rd = rows[self._row_index]
        self._maybe_suggest_instances(rd)
        kind = rd.get("kind")
        lines: list[str] = []
        start = self._sel[0] if self._sel else self._offset
        n = max(1, int(getattr(self, "_instances", 1)))
        # Attempt to fit values by preview width
        try:
            total_w = int(getattr(self._preview.size, "width", 0)) or 0
        except Exception:
            total_w = 0
        if total_w <= 0:
            total_w = 80

        def join_fit(vals: list[str], head: str) -> str:
            # Fit a comma-separated list within remaining width.
            rem = max(10, total_w - len(head) - 2)
            out: list[str] = []
            used = 0
            for i, v in enumerate(vals):
                part = ((", " if i else "") + v)
                # Leave room for ellipsis when more remain
                reserve = 2 if i < len(vals) - 1 else 0
                if used + len(part) + reserve > rem:
                    if i < len(vals):
                        out.append("…")
                    break
                out.append(v)
                used += len(part)
            return "[" + ", ".join(out) + "]"

        def fmt_vals(vals) -> str:
            if vals is None:
                return "—"
            return join_fit([str(v) for v in vals], head="")
        hdr = ""
        if kind == "int":
            bits = int(rd.get("bits", 8))
            signed = bool(rd.get("signed", False))
            endian = str(rd.get("endian", "little"))
            el = ("i" if signed else "u") + str(bits)
            hdr = f"Preview: {'array of ' + el if n>1 else el} (n={n}) @0x{start:08X}"
            for f in self._files:
                label = ("★ " if f.is_baseline else "✓ ") + os.path.basename(f.name)
                if n > 1:
                    vals = decode_int_array(
                        f.reader,
                        start,
                        bits=bits,
                        signed=signed,
                        endian=endian,
                        count=n,
                    )
                    lines.append(f"{label}  {fmt_vals(vals)}")
                else:
                    cell = decode_int(f.reader, start, bits=bits, signed=signed, endian=endian)
                    lines.append(f"{label}  {cell.text}")
        elif kind == "float":
            bits = int(rd.get("bits", 32))
            endian = str(rd.get("endian", "little"))
            el = f"f{bits}"
            hdr = f"Preview: {el} (n={n}) @0x{start:08X}"
            for f in self._files:
                label = ("★ " if f.is_baseline else "✓ ") + os.path.basename(f.name)
                if n > 1:
                    # arrays of floats not supported yet
                    lines.append(f"{label}  [floats array preview not supported]")
                else:
                    cell = decode_float(f.reader, start, bits=bits, endian=endian)
                    lines.append(f"{label}  {cell.text}")
        elif kind in {"ascii", "cstring", "bytes"}:
            hdr = f"Preview: {kind} (n={n}) @0x{start:08X}"
            for f in self._files:
                label = ("★ " if f.is_baseline else "✓ ") + os.path.basename(f.name)
                if n > 1:
                    L = int(self._unit_len)
                    vals: list[str] = []
                    any_no_term = False
                    data = f.reader.read(start, L * n)
                    for i in range(n):
                        slot = data[i * L : (i + 1) * L]
                        if kind == "cstring":
                            txt, term, _used = decode_cstring_fixed_slot(slot)
                            vals.append(txt)
                            if not term:
                                any_no_term = True
                        elif kind == "ascii":
                            text = "".join(chr(b) if 32 <= b <= 126 else "·" for b in slot)
                            vals.append(text)
                        else:  # bytes
                            hexes = " ".join(f"{b:02X}" for b in slot[:4])
                            vals.append(hexes if hexes else "∅")
                    head = f"k={n} "
                    head_values = join_fit(vals, head=head)
                    lines.append(f"{label}  {head}{head_values}")
                    if kind == "cstring" and any_no_term:
                        hdr += "  [warn: some no␀]"
                else:
                    if kind == "ascii":
                        ln = int(self._unit_len)
                        data = f.reader.read(start, ln)
                        txt = ascii_fixed(f.reader, start, ln)
                        lines.append(f"{label}  \"{txt}\" ({len(data)})")
                    elif kind == "cstring":
                        L = int(self._unit_len)
                        data = f.reader.read(start, L)
                        txt, term, used = decode_cstring_fixed_slot(data)
                        suffix = " ␀" if term else " no␀"
                        lines.append(f"{label}  \"{txt}\"{suffix}")
                    elif kind == "bytes":
                        L = int(self._unit_len)
                        data = f.reader.read(start, L)
                        hexes = " ".join(f"{b:02X}" for b in data[:8])
                        lines.append(f"{label}  {hexes}{' …' if len(data)>8 else ''}")
        self._preview.update((hdr + "\n" + "\n".join(lines)).strip())

    def _select_row(self, row: int) -> None:
        max_row = max(0, len(self._row_defs()) - 1)
        self._row_index = max(0, min(max_row, row))
        with suppress(Exception):
            # Prefer select by key if supported
            key = self._row_keys[self._row_index] if self._row_keys else None
            if key is not None:
                self._dt.select_row(key)
        with suppress(Exception):
            # Also move cursor by coordinate for visual feedback
            self._dt.cursor_coordinate = (self._row_index, 0)  # type: ignore[attr-defined]

    def _render_table(self) -> None:
        # Ensure no stale rows remain
        with suppress(Exception):
            # Best-effort: remove rows by key if supported
            for k in list(self._row_keys):
                self._dt.remove_row(k)
        with suppress(Exception):
            # Fallback: clear rows only
            self._dt.clear(rows=True)
        self._row_keys = []
        rows = self._row_defs()
        for idx, rd in enumerate(rows):
            label = rd["label"]() if callable(rd["label"]) else str(rd["label"])  # type: ignore[index]
            if self._chosen_row == idx:
                label = "✓ " + label
            cells: list[str] = [label]
            for f in self._files:
                kind = rd.get("kind")
                if kind == "ascii":
                    cells.append(_truncate(self._get_ascii(f)))
                elif kind == "cstring":
                    L = int(rd.get("length", int(self._unit_len)))
                    data = f.reader.read(self._offset, L)
                    txt, term, used = decode_cstring_fixed_slot(data)
                    suffix = " ␀" if term else " no␀"
                    cells.append(_truncate(txt + suffix))
                elif kind == "int":
                    endian = rd.get("endian") or "little"
                    nc: NumCell = decode_int(
                        f.reader,
                        self._offset,
                        bits=int(rd.get("bits", 8)),
                        signed=bool(rd.get("signed", False)),
                        endian=str(endian),
                    )
                    cells.append(nc.text)
                elif kind == "bytes":
                    L = int(rd.get("length", 0))
                    data = f.reader.read(self._offset, L)
                    hexes = " ".join(f"{b:02X}" for b in data[:8])
                    suffix = " …"
                    if len(data) < L:
                        eof = (self._offset + len(data)) >= f.reader.size
                        extra = "(EOF)" if eof else f"(len={len(data)})"
                        suffix += f" {extra}"
                    cells.append((hexes + suffix).strip())
                elif kind == "array":
                    bits = int(rd.get("bits", 16))
                    signed = bool(rd.get("signed", False))
                    endian = str(rd.get("endian", "little"))
                    count = int(rd.get("count", 0))
                    vals = decode_int_array(
                        f.reader,
                        self._offset,
                        bits=bits,
                        signed=signed,
                        endian=endian,
                        count=count,
                    )
                    cells.append(array_summary(vals) if vals is not None else "—")
                elif kind == "float":
                    nc: NumCell = decode_float(
                        f.reader,
                        self._offset,
                        bits=int(rd.get("bits", 32)),
                        endian=str(rd.get("endian", "little")),
                    )
                    cells.append(nc.text)
                elif kind == "date":
                    fmt = str(rd.get("format", ""))
                    date_str = _decode_date(f.reader, self._offset, fmt)
                    cells.append(date_str)
                else:
                    cells.append("")
            key = self._dt.add_row(*cells)
            self._row_keys.append(key if key is not None else idx)
        self._select_row(self._row_index)

    # Intercept arrow keys at modal level so arrows work anywhere
    def on_key(self, event) -> None:  # type: ignore[override]
        key = event.key
        if key in {"up", "down", "left", "right", "enter", "shift+enter"} or (
            key in {"shift+left", "shift+right"}
        ):
            if key == "up":
                self.action_select_prev()
            elif key == "down":
                self.action_select_next()
            elif key == "left":
                self.action_adjust_small_dec()
            elif key == "right":
                self.action_adjust_small_inc()
            elif key == "shift+left":
                self.action_adjust_big_dec()
            elif key == "shift+right":
                self.action_adjust_big_inc()
            elif key == "enter":
                self.action_commit()
            elif key == "shift+enter":
                self.action_commit_and_jump()
            with suppress(Exception):
                event.stop()

    def on_input_changed(self, event: Input.Changed) -> None:  # type: ignore[override]
        if hasattr(self, "_inst_input") and event.input is self._inst_input:
            txt = (self._inst_input.value or "").strip()
            try:
                n = int(txt)
                if n < 1:
                    n = 1
                if n > 9999:
                    n = 9999
                self._instances = n
                self._instances_dirty = True
                self._refresh_len_dependent_ui()
            except Exception:
                pass


def _truncate(s: str, width: int = 32) -> str:
    if len(s) <= width:
        return s
    return s[: max(0, width - 1)] + "…"
