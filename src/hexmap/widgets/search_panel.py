"""Search panel for left sidebar in Diff tab."""

from __future__ import annotations

from contextlib import suppress
from datetime import datetime

from textual import events
from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Button, Checkbox, Input, Label, Select, Static


class EncodingList(Vertical):
    """Custom container for encoding checkboxes with arrow key navigation."""

    def __init__(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(**kwargs)
        # Container itself should not be focusable
        self.can_focus = False

    def on_key(self, event: events.Key) -> None:
        """Handle up/down arrow keys to navigate between checkboxes."""
        # Only handle up/down arrows
        if event.key not in ("up", "down"):
            return

        # Prevent default handling immediately for arrow keys
        event.prevent_default()
        event.stop()

        # Get all enabled checkbox children (skip disabled ones)
        checkboxes = [w for w in self.children if isinstance(w, Checkbox) and not w.disabled]
        if not checkboxes:
            return

        # Find which checkbox currently has focus
        focused = self.app.focused
        if focused not in checkboxes:
            # If none of our checkboxes has focus, focus the first enabled one
            checkboxes[0].focus()
            return

        # Move focus to next/prev checkbox
        current_idx = checkboxes.index(focused)
        if event.key == "down":
            next_idx = (current_idx + 1) % len(checkboxes)
            checkboxes[next_idx].focus()
        elif event.key == "up":
            prev_idx = (current_idx - 1) % len(checkboxes)
            checkboxes[prev_idx].focus()


class SearchPanel(Container):
    """Search mode selector and parameters panel."""

    def __init__(self) -> None:
        super().__init__()
        self._mode = "none"
        self._selected_encodings: set[str] = {"unix_s", "dos_datetime", "ascii_text"}  # Default
        self._last_chunk_length_type = "u16 LE"  # Track for scan step auto-update
        # Container should not intercept focus - let children handle it
        self.can_focus = False

    def on_mount(self) -> None:
        """Initialize the encoding list highlight after mounting."""
        # Set highlight after refresh to ensure widget is ready
        self.call_after_refresh(self._init_encoding_highlight)

    def _init_encoding_highlight(self) -> None:
        """Not needed with Checkbox approach."""
        pass

    def compose(self) -> ComposeResult:  # type: ignore[override]
        # Mode selector (no form-row wrapper to avoid extra spacing)
        yield Label("Search:", id="search-mode-label")
        self._mode_select = Select[str](
            options=[
                ("None", "none"),
                ("Date/Time", "date"),
                ("Chunk (length-prefixed)", "chunk"),
                ("Pointer (offsets)", "pointer"),
                ("String", "string"),
                ("Bytes", "bytes"),
                ("Integer (u16)", "u16"),
            ],
            value="none",
            id="search-mode-select",
        )
        yield self._mode_select

        # Date/Time parameters
        with Container(id="search-date-params", classes="hidden") as self._date_params:
            # Start date
            yield Label("Start date (YYYY-MM-DD):")
            self._start_date = Input(
                value="1970-01-01",
                placeholder="1970-01-01",
                id="search-start-date",
            )
            yield self._start_date
            yield Static("")  # Blank line

            # End date
            yield Label("End date (YYYY-MM-DD):")
            self._end_date = Input(
                value="2030-12-31",
                placeholder="2030-12-31",
                id="search-end-date",
            )
            yield self._end_date
            yield Static("")  # Blank line

            # Encodings - simple checkboxes with arrow key navigation
            yield Label("Encodings:")
            with EncodingList(id="search-encodings"):
                self._unix_s_cb = Checkbox(
                    "unix_s (u32 LE)", value=True, id="cb-unix-s"
                )
                yield self._unix_s_cb
                self._unix_ms_cb = Checkbox(
                    "unix_ms (u64 LE)", value=False, id="cb-unix-ms"
                )
                yield self._unix_ms_cb
                self._filetime_cb = Checkbox(
                    "FILETIME (u64 LE)", value=False, id="cb-filetime"
                )
                yield self._filetime_cb
                self._dos_datetime_cb = Checkbox(
                    "DOS datetime (2×u16)", value=True, id="cb-dos-datetime"
                )
                yield self._dos_datetime_cb
                self._dos_date_cb = Checkbox(
                    "DOS date (u16)", value=False, id="cb-dos-date"
                )
                yield self._dos_date_cb
                self._ole_date_cb = Checkbox(
                    "OLE DATE (f64)", value=False, id="cb-ole-date"
                )
                yield self._ole_date_cb
                self._days_1970_cb = Checkbox(
                    "Days since 1970 (u16)", value=False, id="cb-days-1970"
                )
                yield self._days_1970_cb
                self._days_1980_cb = Checkbox(
                    "Days since 1980 (u16)", value=False, id="cb-days-1980"
                )
                yield self._days_1980_cb
                self._ascii_text_cb = Checkbox(
                    "ASCII date text", value=True, id="cb-ascii-text"
                )
                yield self._ascii_text_cb
                self._ftm_packed_cb = Checkbox(
                    "FTM Packed Date (4-byte)", value=False, id="cb-ftm-packed"
                )
                yield self._ftm_packed_cb
            yield Static("")  # Blank line

            # Scan step
            yield Label("Scan step (bytes):")
            self._scan_step = Input(value="4", placeholder="4", id="search-scan-step")
            yield self._scan_step
            yield Label(
                "Offsets checked: 0, step, 2×step… (use 4 for u32, 8 for u64)",
                classes="help-hint",
            )
            yield Static("")  # Blank line

            # Run button
            self._run_button = Button(
                "Run search", id="search-run-button", variant="primary"
            )
            yield self._run_button

        # Chunk (length-prefixed) parameters
        with Container(id="search-chunk-params", classes="hidden") as self._chunk_params:
            # Length type selector
            yield Label("Length type:")
            self._chunk_length_type = Select[str](
                options=[
                    ("u8", "u8"),
                    ("u16 LE", "u16 LE"),
                    ("u16 BE", "u16 BE"),
                    ("u32 LE", "u32 LE"),
                    ("u32 BE", "u32 BE"),
                ],
                value="u16 LE",
                id="search-chunk-length-type",
            )
            yield self._chunk_length_type
            yield Static("")  # Blank line

            # Min length
            yield Label("Min length (optional):")
            self._chunk_min_length = Input(
                value="",
                placeholder="e.g., 10",
                id="search-chunk-min-length",
            )
            yield self._chunk_min_length
            yield Label("Leave empty for no minimum", classes="help-hint")
            yield Static("")  # Blank line

            # Max length
            yield Label("Max length (optional):")
            self._chunk_max_length = Input(
                value="",
                placeholder="e.g., 1024",
                id="search-chunk-max-length",
            )
            yield self._chunk_max_length
            yield Label("Leave empty for no maximum", classes="help-hint")
            yield Static("")  # Blank line

            # Scan step
            yield Label("Scan step (bytes):")
            self._chunk_scan_step = Input(value="2", placeholder="2", id="search-chunk-scan-step")
            yield self._chunk_scan_step
            yield Label(
                "Alignment for scanning (1 = check every byte)",
                classes="help-hint",
            )
            yield Static("")  # Blank line

            # Run button
            self._chunk_run_button = Button(
                "Run search", id="search-chunk-run-button", variant="primary"
            )
            yield self._chunk_run_button

        # Pointer parameters
        with Container(id="search-pointer-params", classes="hidden") as self._pointer_params:
            # Pointer type selector
            yield Label("Pointer type:")
            self._pointer_type = Select[str](
                options=[
                    ("u16 LE", "u16 LE"),
                    ("u16 BE", "u16 BE"),
                    ("u32 LE", "u32 LE"),
                    ("u32 BE", "u32 BE"),
                    ("u64 LE", "u64 LE"),
                    ("u64 BE", "u64 BE"),
                ],
                value="u32 LE",
                id="search-pointer-type",
            )
            yield self._pointer_type
            yield Static("")  # Blank line

            # Pointer base mode
            yield Label("Pointer base:")
            self._pointer_base = Select[str](
                options=[
                    ("File start (absolute)", "absolute"),
                    ("Relative to current offset", "relative"),
                ],
                value="absolute",
                id="search-pointer-base",
            )
            yield self._pointer_base
            yield Static("")  # Blank line

            # Base addend
            yield Label("Base addend (optional):")
            self._pointer_addend = Input(
                value="0",
                placeholder="0",
                id="search-pointer-addend",
            )
            yield self._pointer_addend
            yield Label("Offset added to computed target", classes="help-hint")
            yield Static("")  # Blank line

            # Target constraints
            yield Label("Min target (optional):")
            self._pointer_min_target = Input(
                value="",
                placeholder="e.g., 0",
                id="search-pointer-min-target",
            )
            yield self._pointer_min_target
            yield Static("")  # Blank line

            yield Label("Max target (optional):")
            self._pointer_max_target = Input(
                value="",
                placeholder="e.g., file size",
                id="search-pointer-max-target",
            )
            yield self._pointer_max_target
            yield Label("Leave empty to cap at file size", classes="help-hint")
            yield Static("")  # Blank line

            # Allow zero checkbox
            self._pointer_allow_zero = Checkbox(
                "Allow zero pointer values", value=False, id="pointer-allow-zero"
            )
            yield self._pointer_allow_zero
            yield Static("")  # Blank line

            # Target alignment
            yield Label("Target alignment:")
            self._pointer_alignment = Select[str](
                options=[
                    ("Any", "any"),
                    ("2 bytes", "2"),
                    ("4 bytes", "4"),
                    ("8 bytes", "8"),
                ],
                value="any",
                id="search-pointer-alignment",
            )
            yield self._pointer_alignment
            yield Static("")  # Blank line

            # Scan step
            yield Label("Scan step (bytes):")
            self._pointer_scan_step = Input(
                value="4", placeholder="4", id="search-pointer-scan-step"
            )
            yield self._pointer_scan_step
            yield Label(
                "Alignment for scanning (defaults to pointer size)",
                classes="help-hint",
            )
            yield Static("")  # Blank line

            # Preview length
            yield Label("Preview length (bytes):")
            self._pointer_preview_length = Input(
                value="16",
                placeholder="16",
                id="search-pointer-preview-length",
            )
            yield self._pointer_preview_length
            yield Label("Bytes to highlight at target (0 = no preview)", classes="help-hint")
            yield Static("")  # Blank line

            # Run button
            self._pointer_run_button = Button(
                "Run search", id="search-pointer-run-button", variant="primary"
            )
            yield self._pointer_run_button

        # String parameters (stub for MVP)
        with Container(id="search-string-params", classes="hidden") as self._string_params:
            yield Static("String search not implemented in MVP")

        # Bytes parameters (stub for MVP)
        with Container(id="search-bytes-params", classes="hidden") as self._bytes_params:
            yield Static("Bytes search not implemented in MVP")

        # U16 parameters (stub for MVP)
        with Container(id="search-u16-params", classes="hidden") as self._u16_params:
            yield Static("Integer search not implemented in MVP")

    def on_select_changed(self, event: Select.Changed) -> None:  # type: ignore[name-defined]
        if event.select is self._mode_select:
            self._mode = str(event.value)
            self._update_params_visibility()
            # Notify app of mode change
            if hasattr(self.app, "on_search_mode_changed"):
                self.app.on_search_mode_changed(self._mode)  # type: ignore[attr-defined]
        elif event.select is self._chunk_length_type:
            # Auto-update scan step when length type changes
            length_type = str(event.value)
            if length_type != self._last_chunk_length_type:
                self._last_chunk_length_type = length_type
                # Set default scan step based on length type
                default_steps = {
                    "u8": "1",
                    "u16 LE": "2",
                    "u16 BE": "2",
                    "u32 LE": "4",
                    "u32 BE": "4",
                }
                self._chunk_scan_step.value = default_steps.get(length_type, "1")
        elif event.select is self._pointer_type:
            # Auto-update scan step when pointer type changes
            pointer_type = str(event.value)
            default_steps = {
                "u16 LE": "2",
                "u16 BE": "2",
                "u32 LE": "4",
                "u32 BE": "4",
                "u64 LE": "8",
                "u64 BE": "8",
            }
            self._pointer_scan_step.value = default_steps.get(pointer_type, "4")

    def on_button_pressed(self, event: Button.Pressed) -> None:  # type: ignore[override]
        if event.button in (
            self._run_button,
            self._chunk_run_button,
            self._pointer_run_button,
        ):
            self._run_search()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Update selected encodings when checkboxes change."""
        checkbox_id = event.checkbox.id or ""
        # Map checkbox IDs to encoding names
        encoding_map = {
            "cb-unix-s": "unix_s",
            "cb-unix-ms": "unix_ms",
            "cb-filetime": "filetime",
            "cb-dos-datetime": "dos_datetime",
            "cb-dos-date": "dos_date",
            "cb-ole-date": "ole_date",
            "cb-days-1970": "days_since_1970",
            "cb-days-1980": "days_since_1980",
            "cb-ascii-text": "ascii_text",
            "cb-ftm-packed": "ftm_packed_date",
        }

        encoding = encoding_map.get(checkbox_id)
        if encoding:
            if event.value:
                self._selected_encodings.add(encoding)
            else:
                self._selected_encodings.discard(encoding)

    def _update_params_visibility(self) -> None:
        # Hide all param containers
        self._date_params.add_class("hidden")
        self._chunk_params.add_class("hidden")
        self._pointer_params.add_class("hidden")
        self._string_params.add_class("hidden")
        self._bytes_params.add_class("hidden")
        self._u16_params.add_class("hidden")

        # Show relevant container
        if self._mode == "date":
            self._date_params.remove_class("hidden")
        elif self._mode == "chunk":
            self._chunk_params.remove_class("hidden")
        elif self._mode == "pointer":
            self._pointer_params.remove_class("hidden")
        elif self._mode == "string":
            self._string_params.remove_class("hidden")
        elif self._mode == "bytes":
            self._bytes_params.remove_class("hidden")
        elif self._mode == "u16":
            self._u16_params.remove_class("hidden")

    def _run_search(self) -> None:
        if self._mode == "date":
            params = self._get_date_params()
            if params and hasattr(self.app, "run_date_search"):
                self.app.run_date_search(**params)  # type: ignore[attr-defined]
        elif self._mode == "chunk":
            params = self._get_chunk_params()
            if params and hasattr(self.app, "run_chunk_search"):
                self.app.run_chunk_search(**params)  # type: ignore[attr-defined]
        elif self._mode == "pointer":
            params = self._get_pointer_params()
            if params and hasattr(self.app, "run_pointer_search"):
                self.app.run_pointer_search(**params)  # type: ignore[attr-defined]

    def _get_date_params(self) -> dict | None:
        try:
            start_str = self._start_date.value.strip()
            end_str = self._end_date.value.strip()
            scan_step = int(self._scan_step.value.strip() or "4")

            start_date = datetime.strptime(start_str, "%Y-%m-%d")
            end_date = datetime.strptime(end_str, "%Y-%m-%d")

            return {
                "start_date": start_date,
                "end_date": end_date,
                "alignment": scan_step,
                "encodings": list(self._selected_encodings),
            }
        except (ValueError, AttributeError):
            return None

    def _get_chunk_params(self) -> dict | None:
        try:
            length_type = str(self._chunk_length_type.value)
            min_length_str = self._chunk_min_length.value.strip()
            max_length_str = self._chunk_max_length.value.strip()
            scan_step_str = self._chunk_scan_step.value.strip()

            min_length = int(min_length_str) if min_length_str else None
            max_length = int(max_length_str) if max_length_str else None
            alignment = int(scan_step_str) if scan_step_str else 1

            return {
                "length_type": length_type,
                "min_length": min_length,
                "max_length": max_length,
                "alignment": alignment,
            }
        except (ValueError, AttributeError):
            return None

    def _get_pointer_params(self) -> dict | None:
        try:
            pointer_type = str(self._pointer_type.value)
            base_mode = str(self._pointer_base.value)
            base_addend_str = self._pointer_addend.value.strip()
            min_target_str = self._pointer_min_target.value.strip()
            max_target_str = self._pointer_max_target.value.strip()
            allow_zero = self._pointer_allow_zero.value
            alignment_str = str(self._pointer_alignment.value)
            scan_step_str = self._pointer_scan_step.value.strip()
            preview_length_str = self._pointer_preview_length.value.strip()

            base_addend = int(base_addend_str) if base_addend_str else 0
            min_target = int(min_target_str) if min_target_str else None
            max_target = int(max_target_str) if max_target_str else None
            target_alignment = int(alignment_str) if alignment_str != "any" else None
            scan_step = int(scan_step_str) if scan_step_str else None
            preview_length = int(preview_length_str) if preview_length_str else 16

            return {
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
        except (ValueError, AttributeError):
            return None

    def reset_to_none(self) -> None:
        """Reset selector to None mode."""
        self._mode = "none"
        with suppress(Exception):
            self._mode_select.value = "none"
        self._update_params_visibility()
