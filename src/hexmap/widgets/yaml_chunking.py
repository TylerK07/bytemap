"""YAML-driven chunking widget."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from rich.text import Text
from textual import on
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Input, Label, Static, TextArea

from hexmap.core.incremental_spans import IncrementalSpanManager
from hexmap.core.io import PagedReader
from hexmap.core.spans import Span, SpanIndex
from hexmap.core.tool_host import LintGrammarInput, ParseBinaryInput, ToolHost
from hexmap.core.yaml_parser import ParsedRecord, decode_record_payload
from hexmap.ui.palette import PALETTE
from hexmap.widgets.hex_view import HexView

if TYPE_CHECKING:
    from hexmap.app import HexmapApp


# Default YAML for AA.FTM with inline documentation
DEFAULT_YAML = """# YAML Grammar for Family Tree Maker (FTM) format
# See YAML_GRAMMAR_REFERENCE.md for complete documentation

format: record_stream           # File is a stream of records
endian: little                  # Global default: all multi-byte integers are little-endian

framing:
  repeat: until_eof             # Parse records until end of file

# Type discrimination: determine which record type to use
record:
  switch:
    expr: Header.type_raw       # Read Header.type_raw field to discriminate
    cases:
      "0x544E": NTRecord        # Type 0x544E (NT) = Note record with text
    default: GenericRecord      # All other types = Generic record

# Type definitions: structure of each record type
# Note: Fields can specify 'color' for custom visualization (e.g., color: red, color: "#ff8800")
types:
  # Common header (4 bytes) used by all records
  Header:
    fields:
      - { name: type_raw, type: u16 }      # 2 bytes: record type (inherits little-endian)
      - { name: entity_id, type: u16 }     # 2 bytes: person/entity ID

  # Generic record: [header][1-byte length][variable payload]
  # Used by 99.5% of records (names, dates, relationships, etc.)
  GenericRecord:
    fields:
      - { name: header, type: Header }                   # 4-byte header
      - { name: payload_len, type: u8 }                  # 1 byte: payload length (0-255)
      - { name: payload, type: bytes, length: payload_len }  # Variable payload (now using syntactic sugar)

  # NT Record: Extended format for biographical notes
  # Structure: [header][len1][len2][10 zeros][1C00][text][0D00]
  NTRecord:
    fields:
      - { name: header, type: Header }                   # 4-byte header
      - { name: nt_len_1, type: u16 }                    # Length of (delimiter + text + terminator)
      - { name: nt_len_2, type: u16 }                    # Usually same as nt_len_1
      - { name: pad10, type: bytes, length: 10 }         # 10 zero bytes (padding/reserved)
      - { name: delimiter, type: u16 }                   # 0x001C delimiter
      - { name: note_text, type: bytes, length: "nt_len_1 - 4", encoding: ascii }  # Text (len excludes delimiters)
      - { name: terminator, type: u16 }                  # 0x000D terminator

# Registry: semantic names and decoders for record types
# Keys use canonical hex format (e.g., "0x0065" not "0x6500")
registry:
  "0x0000":
    name: root_record
    decode:
      as: hex                   # Display as hex bytes

  "0x0065":
    name: given_name
    decode:
      as: string                # Decode payload as ASCII string
      encoding: ascii

  "0x0101":
    name: birth_year
    decode:
      as: u16                   # Decode payload as 16-bit integer (inherits little-endian)

  "0x0200":
    name: birth_date
    decode:
      as: ftm_packed_date       # Decode 4-byte FTM date format → YYYY-MM-DD

  "0x0201":
    name: death_date
    decode:
      as: ftm_packed_date       # Decode 4-byte FTM date format → YYYY-MM-DD

  "0x544E":
    name: note_text
    decode:
      as: string                # Decode note_text field as ASCII
      field: note_text          # Target specific field (for complex records)
      encoding: ascii
"""


class YAMLEditorPanel(Static):
    """Panel with YAML editor and parse button."""

    DEFAULT_CSS = """
    YAMLEditorPanel {
        border: solid #3b4252;
        height: 1fr;
        layout: vertical;
    }
    YAMLEditorPanel:focus-within {
        border: solid #ffa657;
    }

    #yaml-editor-container {
        height: 1fr;
    }

    #yaml-editor {
        width: 100%;
        height: 1fr;
    }

    #yaml-errors {
        height: auto;
        max-height: 5;
        background: $error;
        color: $text;
        padding: 1;
        display: none;
    }

    #yaml-errors.visible {
        display: block;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.yaml_text = DEFAULT_YAML

    def compose(self):
        yield Label("YAML Grammar", id="yaml-header")
        with Vertical(id="yaml-editor-container"):
            yield TextArea(self.yaml_text, language="yaml", id="yaml-editor")
        yield Static("", id="yaml-errors")
        yield Button("Parse", variant="primary", id="parse-button")

    @on(Button.Pressed, "#parse-button")
    def parse_clicked(self) -> None:
        """Trigger parse with current YAML."""
        editor = self.query_one("#yaml-editor", TextArea)
        self.yaml_text = editor.text

        # Clear errors
        errors_display = self.query_one("#yaml-errors", Static)
        errors_display.remove_class("visible")

        # Validate YAML using Tool Host
        result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=self.yaml_text))

        if not result.success:
            # Show error
            errors_display.update(f"YAML Error: {result.errors[0]}")
            errors_display.add_class("visible")
        else:
            # Grammar is valid - proceed with parsing
            app: HexmapApp = self.app  # type: ignore

            # Show warnings if any (non-fatal)
            if result.warnings:
                warnings_text = "; ".join(result.warnings)
                app.set_status_hint(f"Warnings: {warnings_text}")

            # Trigger binary parsing with validated grammar
            if hasattr(app, "yaml_chunking_widget"):
                app.yaml_chunking_widget.parse_with_grammar(result.grammar)


class RecordTablePanel(Static):
    """Middle panel with Hex, Raw, Types tabs."""

    DEFAULT_CSS = """
    RecordTablePanel {
        border: solid #3b4252;
        height: 1fr;
        layout: vertical;
    }
    RecordTablePanel:focus-within {
        border: solid #ffa657;
    }

    #tab-buttons {
        height: 3;
        padding: 0 1;
        margin: 0;
        dock: top;
    }

    #tab-content {
        height: 1fr;
        width: 100%;
    }

    #record-table {
        height: 1fr;
        width: 100%;
    }

    #record-hex-view {
        height: 1fr;
        width: 100%;
    }

    .hidden {
        display: none;
    }
    """

    BINDINGS = [
        ("j", "cursor_down", "Next"),
        ("k", "cursor_up", "Previous"),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.records: list[ParsedRecord] = []
        self.reader: PagedReader | None = None
        self.current_tab = "raw"  # raw, hex, types
        self.sort_column: str | None = None
        self.sort_reverse: bool = False
        self._span_manager: IncrementalSpanManager | None = None
        self._viewport_timer: str | None = None
        self._hex_view: HexView | None = None

    def compose(self):
        # Tab buttons
        yield Horizontal(
            Button("Hex", id="tab-hex-btn"),
            Button("Raw", id="tab-raw-btn", variant="primary"),
            Button("Types", id="tab-types-btn"),
            id="tab-buttons",
        )
        # Tab content container
        yield Container(id="tab-content")

    @on(Button.Pressed, "#tab-hex-btn")
    def show_hex(self) -> None:
        self.current_tab = "hex"
        self._update_button_styles()
        self.rebuild()

    @on(Button.Pressed, "#tab-raw-btn")
    def show_raw(self) -> None:
        self.current_tab = "raw"
        self._update_button_styles()
        self.rebuild()

    @on(Button.Pressed, "#tab-types-btn")
    def show_types(self) -> None:
        self.current_tab = "types"
        self._update_button_styles()
        self.rebuild()

    def _update_button_styles(self) -> None:
        """Update button variants based on current tab."""
        self.query_one("#tab-hex-btn", Button).variant = (
            "primary" if self.current_tab == "hex" else "default"
        )
        self.query_one("#tab-raw-btn", Button).variant = (
            "primary" if self.current_tab == "raw" else "default"
        )
        self.query_one("#tab-types-btn", Button).variant = (
            "primary" if self.current_tab == "types" else "default"
        )

    def set_data(self, records: list[ParsedRecord], reader: PagedReader) -> None:
        """Update with new parse results."""
        self.records = records
        self.reader = reader
        # Create new span manager with lightweight offset index
        self._span_manager = IncrementalSpanManager(records) if records else None
        self.rebuild()

    def rebuild(self) -> None:
        """Rebuild view based on current tab."""
        container = self.query_one("#tab-content", Container)

        # Reset sort state when rebuilding
        self.sort_column = None
        self.sort_reverse = False

        if self.current_tab == "hex":
            # Hide table, show hex view
            try:
                table = container.query_one("#record-table", DataTable)
                table.add_class("hidden")
            except:
                pass

            # Get or create hex view
            try:
                hex_view = container.query_one("#record-hex-view", HexView)
                hex_view.remove_class("hidden")
                # Update reader in case it changed
                if self.reader:
                    hex_view.reader = self.reader
            except:
                # Create new hex view if it doesn't exist
                if self.reader:
                    hex_view = HexView(self.reader)
                    hex_view.id = "record-hex-view"
                    container.mount(hex_view)
                else:
                    return

            # Store reference for incremental parsing
            self._hex_view = hex_view

            if self.reader:
                self._build_hex_view(hex_view)
                # Start viewport monitoring
                self._start_viewport_monitoring()
                # Focus the hex view so keyboard navigation works
                hex_view.focus()
        else:
            # Stop viewport monitoring when leaving hex view
            self._stop_viewport_monitoring()
            self._hex_view = None

            # Hide hex view, show table
            try:
                hex_view = container.query_one("#record-hex-view", HexView)
                hex_view.add_class("hidden")
            except:
                pass

            # Get or create table
            try:
                table = container.query_one("#record-table", DataTable)
                table.remove_class("hidden")
                table.clear(columns=True)
            except:
                # Create new table if it doesn't exist
                table = DataTable(id="record-table", cursor_type="row", zebra_stripes=True)
                container.mount(table)

            if self.current_tab == "raw":
                self._build_raw_view(table)
            elif self.current_tab == "types":
                self._build_types_view(table)

            # Focus the table so keyboard navigation works
            table.focus()

    def _build_hex_view(self, hex_view: HexView) -> None:
        """Build hex view with viewport-based field span overlays."""
        if not self.records or not self._span_manager:
            return

        # Update spans for initial viewport
        self._update_viewport()

    def _start_viewport_monitoring(self) -> None:
        """Start monitoring viewport for changes."""
        if not self._span_manager:
            return

        # Cancel existing timer if any
        self._stop_viewport_monitoring()

        # Start viewport monitoring timer (check every 100ms)
        self._viewport_timer = self.set_interval(0.1, self._check_viewport)

    def _stop_viewport_monitoring(self) -> None:
        """Stop viewport monitoring timer."""
        if self._viewport_timer:
            try:
                self.remove_timer(self._viewport_timer)
            except:
                pass
            self._viewport_timer = None

    def _check_viewport(self) -> None:
        """Check if viewport changed and update spans if needed."""
        if not self._span_manager or not self._hex_view:
            self._stop_viewport_monitoring()
            return

        # Update viewport (only generates spans if viewport changed)
        self._update_viewport()

    def _update_viewport(self) -> None:
        """Update spans for current viewport."""
        if not self._span_manager or not self._hex_view:
            return

        # Calculate viewport range
        viewport_start = self._hex_view.viewport_offset
        viewport_size = self._hex_view.visible_rows() * self._hex_view.bytes_per_row
        viewport_end = viewport_start + viewport_size

        # Update spans for viewport (returns SpanIndex if changed, None if cached)
        span_index = self._span_manager.update_viewport(viewport_start, viewport_end)

        # Only update HexView if spans changed
        if span_index is not None:
            self._hex_view.set_span_index(span_index)

    def _build_raw_view(self, table: DataTable) -> None:
        """Build raw view showing all fields."""
        # Add columns
        table.add_column("Offset", key="offset", width=10)
        table.add_column("Type", key="type", width=8)
        table.add_column("Name", key="name", width=15)
        table.add_column("Entity ID", key="entity", width=10)
        table.add_column("Length", key="length", width=8)
        table.add_column("Decoded", key="decoded", width=20)
        table.add_column("Payload Preview", key="payload", width=30)

        if not self.records:
            return

        # Get grammar for registry lookups
        app: HexmapApp = self.app  # type: ignore
        grammar = None
        if hasattr(app, "yaml_chunking_widget") and app.yaml_chunking_widget:
            grammar = app.yaml_chunking_widget.grammar

        # Add all rows (DataTable handles large datasets efficiently)
        for i, rec in enumerate(self.records):
            # Extract type and entity ID from header
            type_hex = "?"
            type_raw_value = None
            entity_hex = "?"
            if "header" in rec.fields:
                header = rec.fields["header"].value
                if isinstance(header, dict):
                    if "type_raw" in header:
                        type_raw_value = header["type_raw"]
                        type_hex = f"0x{type_raw_value:04X}"
                    if "entity_id" in header:
                        entity_hex = f"0x{header['entity_id']:04X}"

            # Get length
            length_str = f"{rec.size}b"

            # Get registry name and decoded value
            registry_name = "—"
            decoded_value = "—"
            if grammar and type_raw_value is not None:
                type_key = f"0x{type_raw_value:04X}"
                if type_key in grammar.registry:
                    entry = grammar.registry[type_key]
                    registry_name = entry.name
                    # Try to decode
                    decoded = decode_record_payload(rec, grammar)
                    if decoded:
                        decoded_value = decoded[:40] + ("..." if len(decoded) > 40 else "")

            # Get payload preview
            payload_preview = self._get_payload_preview(rec)

            table.add_row(
                f"{rec.offset:08x}",
                type_hex,
                registry_name,
                entity_hex,
                length_str,
                decoded_value,
                payload_preview,
                key=str(i),
            )

    def _build_types_view(self, table: DataTable) -> None:
        """Build types summary view."""
        # Add columns
        table.add_column("Type", key="type")
        table.add_column("Count", key="count")
        table.add_column("Name", key="name")

        # Group by type
        type_groups: dict[str, list[ParsedRecord]] = {}
        for rec in self.records:
            type_key = rec.type_discriminator or rec.type_name
            if type_key not in type_groups:
                type_groups[type_key] = []
            type_groups[type_key].append(rec)

        # Sort by count
        sorted_types = sorted(type_groups.items(), key=lambda x: len(x[1]), reverse=True)

        if not sorted_types:
            return

        # Add rows
        for i, (type_key, records) in enumerate(sorted_types):
            table.add_row(
                type_key,
                f"{len(records)}",
                records[0].type_name,
                key=str(i),
            )

    def _get_payload_preview(self, record: ParsedRecord) -> str:
        """Get payload preview (hex + ASCII)."""
        # For NT records, show the decoded note text
        if record.type_name == "NTRecord" and "note_text" in record.fields:
            note = record.fields["note_text"].value
            if isinstance(note, str):
                return f'"{note[:40]}{"..." if len(note) > 40 else ""}"'
            elif isinstance(note, bytes):
                return note.hex()[:40] + ("..." if len(note) > 20 else "")

        # For generic records, show payload field
        if "payload" in record.fields:
            payload = record.fields["payload"].value
            if isinstance(payload, bytes):
                hex_str = payload.hex()[:16]
                ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in payload[:8])
                return f"{hex_str}  {ascii_str}"
            return str(payload)[:40]

        return ""

    @on(DataTable.HeaderSelected, "#record-table")
    def header_selected(self, event: DataTable.HeaderSelected) -> None:
        """Handle column header click for sorting."""
        table = event.data_table
        column_key = str(event.column_key.value)

        # Toggle sort direction if same column, otherwise default to ascending
        if self.sort_column == column_key:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column_key
            self.sort_reverse = False

        # Sort the table
        table.sort(column_key, reverse=self.sort_reverse)

    @on(DataTable.RowSelected, "#record-table")
    def record_selected(self, event: DataTable.RowSelected) -> None:
        """Handle record selection."""
        # Get the record index from the row key
        try:
            row_index = int(event.row_key.value)
            if 0 <= row_index < len(self.records):
                record = self.records[row_index]
                app: HexmapApp = self.app  # type: ignore

                # Jump to record in hex view
                if hasattr(app, "hex_view") and app.hex_view:
                    app.hex_view.set_cursor(record.offset)
                    # Also highlight the selected record
                    app.hex_view.set_selected_spans([(record.offset, record.size)])

                # Update inspector
                if hasattr(app, "yaml_chunking_widget"):
                    app.yaml_chunking_widget.select_record(record)

                # If we're on the hex tab, highlight the record there too
                if self.current_tab == "hex":
                    try:
                        hex_view = self.query_one("#record-hex-view", HexView)
                        hex_view.set_cursor(record.offset)
                        hex_view.set_selected_spans([(record.offset, record.size)])
                        hex_view.ensure_cursor_visible()
                    except:
                        pass
        except (ValueError, AttributeError):
            pass


class RecordInspectorPanel(Static):
    """Right panel showing record details and decoded values."""

    DEFAULT_CSS = """
    RecordInspectorPanel {
        border: solid #3b4252;
        height: 1fr;
        layout: vertical;
    }
    RecordInspectorPanel:focus-within {
        border: solid #ffa657;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.current_record: ParsedRecord | None = None

    def compose(self):
        yield Label("Record Inspector", id="inspector-header")
        with VerticalScroll(id="inspector-content"):
            yield Static("No record selected", id="inspector-display")

    def set_record(self, record: ParsedRecord, grammar, reader: PagedReader) -> None:
        """Display record details."""
        self.current_record = record

        text = Text()
        text.append(f"Offset: {record.offset:#08x}\n", style=PALETTE.parsed_offset)
        text.append(f"Size: {record.size} bytes\n", style=PALETTE.parsed_type)
        text.append(f"Type: {record.type_name}\n\n", style=PALETTE.parsed_name)

        if record.type_discriminator:
            text.append(f"Type ID: {record.type_discriminator}\n\n", style=PALETTE.inspector_label)

        # Show decoded value if available
        decoded = decode_record_payload(record, grammar)
        if decoded:
            text.append("Decoded:\n", style=PALETTE.inspector_label)
            text.append(f"{decoded}\n\n", style=PALETTE.inspector_value)

        # Show fields
        text.append("Fields:\n", style=PALETTE.inspector_label)
        for field_name, field in record.fields.items():
            text.append(f"  {field_name}: ", style=PALETTE.inspector_label)

            if isinstance(field.value, dict):
                text.append("{\n")
                for k, v in field.value.items():
                    text.append(f"    {k}: {v}\n", style=PALETTE.inspector_dim)
                text.append("  }\n")
            elif isinstance(field.value, bytes):
                text.append(f"{field.value.hex()[:60]}\n", style=PALETTE.parsed_value)
            elif isinstance(field.value, str):
                text.append(f'"{field.value[:60]}"\n', style=PALETTE.inspector_value)
            else:
                text.append(f"{field.value}\n", style=PALETTE.parsed_value)

        self.query_one("#inspector-display", Static).update(text)


class YAMLChunkingWidget(Container):
    """Main YAML-driven chunking widget."""

    DEFAULT_CSS = """
    YAMLChunkingWidget {
        layout: horizontal;
        height: 1fr;
    }

    #chunking-left-col {
        width: 48;
        min-width: 48;
        max-width: 60;
    }

    #record-table {
        width: 1fr;
        min-width: 40;
    }

    #chunking-right-col {
        width: 36;
        min-width: 36;
    }
    """

    def __init__(self, reader: PagedReader | None = None) -> None:
        super().__init__()
        self.reader = reader
        self.records: list[ParsedRecord] = []
        self.grammar = None

    def compose(self):
        # Left: YAML editor
        with Vertical(id="chunking-left-col", classes="chunking-column"):
            yield YAMLEditorPanel()

        # Middle: Records table with tabs
        yield RecordTablePanel(classes="chunking-column", id="record-table")

        # Right: Inspector
        with Vertical(id="chunking-right-col", classes="chunking-column"):
            yield RecordInspectorPanel()

    def parse_with_grammar(self, grammar) -> None:
        """Parse file with given grammar."""
        app: HexmapApp = self.app  # type: ignore

        if not self.reader:
            app.set_status_hint("No file loaded")
            return

        app.set_status_hint("Parsing records...")

        self.grammar = grammar

        # Parse file using Tool Host
        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(
                grammar=grammar,
                file_path=self.reader.path
            )
        )

        # Convert immutable tuple to list for compatibility
        self.records = list(parse_result.records)

        # Update table
        table = self.query_one(RecordTablePanel)
        table.set_data(self.records, self.reader)

        # Update status
        status = f"Parsed {parse_result.record_count} records"
        if parse_result.errors:
            status += f" ({len(parse_result.errors)} errors)"
        app.set_status_hint(status)

    def select_record(self, record: ParsedRecord) -> None:
        """Handle record selection."""
        if self.grammar:
            inspector = self.query_one(RecordInspectorPanel)
            inspector.set_record(record, self.grammar, self.reader)

    def update_for(self, reader: PagedReader) -> None:
        """Update when reader changes."""
        self.reader = reader
