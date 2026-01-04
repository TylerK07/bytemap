"""Widgets for the Chunking tab."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from rich.text import Text
from textual import on
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Input, Label, Select, Static, Tree

from hexmap.core.chunks import (
    DecoderParams,
    DecoderStatus,
    FramingParams,
    LengthSemantics,
    RecordSpan,
    TypeNormalization,
    TypeRegistryEntry,
    TypeStats,
    build_type_stats,
    decode_payload,
    normalize_type_key,
    scan_chunks,
)
from hexmap.core.io import PagedReader
from hexmap.ui.palette import PALETTE

if TYPE_CHECKING:
    from hexmap.app import HexmapApp


class ChunkFramingPanel(Static):
    """Panel for configuring chunk framing parameters."""

    DEFAULT_CSS = """
    ChunkFramingPanel {
        border: solid #3b4252;
        height: auto;
    }
    ChunkFramingPanel:focus-within {
        border: solid #ffa657;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.params = FramingParams(
            type_width=3,
            length_width=2,
            length_endian="big",
            length_semantics=LengthSemantics.PAYLOAD_ONLY,
            max_payload_len=None,
            strict_eof=True,
            type_normalization=TypeNormalization.RAW,
        )

    def compose(self):
        yield Label("Chunk Framing", id="framing-header")
        with Vertical(id="framing-inputs"):
            yield Label("Type Width:")
            yield Input(value="3", id="type-width-input")
            yield Label("Length Width:")
            yield Input(value="2", id="length-width-input")
            yield Label("Endian:")
            yield Select(
                [("Big", "big"), ("Little", "little")],
                value="big",
                id="length-endian-select",
            )
            yield Label("Semantics:")
            yield Select(
                [("Payload Only", "payload_only"), ("+ Header", "includes_header")],
                value="payload_only",
                id="length-semantics-select",
            )
            yield Label("Max Payload:")
            yield Input(value="", placeholder="unlimited", id="max-payload-input")
            yield Label("Extra Header Bytes:")
            yield Input(value="0", id="extra-header-input")
            yield Label("Normalization:")
            yield Select(
                [
                    ("Raw Hex", "raw"),
                    ("Uint BE", "uint_be"),
                    ("Uint LE", "uint_le"),
                    ("ASCII", "ascii"),
                ],
                value="raw",
                id="type-norm-select",
            )
            yield Button("Scan", variant="primary", id="scan-button")

    @on(Button.Pressed, "#scan-button")
    def scan_clicked(self) -> None:
        """Trigger chunk scan with current parameters."""
        self._update_params()
        app: HexmapApp = self.app  # type: ignore
        if hasattr(app, "chunking_widget"):
            app.chunking_widget.scan_with_params(self.params)

    @on(Input.Changed, "#type-width-input, #length-width-input, #max-payload-input, #extra-header-input")
    def input_changed(self, event: Input.Changed) -> None:
        """Update params when input changes (no auto-rescan)."""
        self._update_params()

    @on(Select.Changed, "#length-endian-select, #length-semantics-select, #type-norm-select")
    def select_changed(self, event: Select.Changed) -> None:
        """Update params when select changes (no auto-rescan)."""
        self._update_params()

    def _update_params(self) -> None:
        """Read current input values and update params."""
        try:
            type_width = int(self.query_one("#type-width-input", Input).value)
            length_width = int(self.query_one("#length-width-input", Input).value)
            length_endian = self.query_one("#length-endian-select", Select).value
            length_semantics_str = self.query_one("#length-semantics-select", Select).value
            max_payload_str = self.query_one("#max-payload-input", Input).value
            extra_header_str = self.query_one("#extra-header-input", Input).value
            type_norm_str = self.query_one("#type-norm-select", Select).value

            length_semantics = LengthSemantics(length_semantics_str)
            type_normalization = TypeNormalization(type_norm_str)
            max_payload = int(max_payload_str) if max_payload_str else None
            extra_header = int(extra_header_str) if extra_header_str else 0

            self.params = FramingParams(
                type_width=type_width,
                length_width=length_width,
                length_endian=str(length_endian),
                length_semantics=length_semantics,
                max_payload_len=max_payload,
                strict_eof=True,
                type_normalization=type_normalization,
                extra_header_bytes=extra_header,
            )
        except (ValueError, KeyError):
            pass


class FileCorpusSelector(Static):
    """Panel for selecting files to include in corpus."""

    DEFAULT_CSS = """
    FileCorpusSelector {
        border: solid #3b4252;
        height: auto;
        margin-top: 1;
    }
    FileCorpusSelector:focus-within {
        border: solid #ffa657;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.selected_files: list[str] = []
        self.corpus_mode = False

    def compose(self):
        yield Label("File Selection", id="corpus-header")
        with Vertical(id="corpus-controls"):
            yield Label("Mode:")
            yield Select(
                [("Current File", "single"), ("Multiple Files (Corpus)", "corpus")],
                value="single",
                id="corpus-mode-select",
            )
            yield Label("Available Files:")
            yield VerticalScroll(
                Static("No files loaded", id="file-list-display"),
                id="file-list-scroll",
            )

    @on(Select.Changed, "#corpus-mode-select")
    def mode_changed(self, event: Select.Changed) -> None:
        """Toggle between single file and corpus mode."""
        self.corpus_mode = event.value == "corpus"
        app: HexmapApp = self.app  # type: ignore
        if hasattr(app, "chunking_widget"):
            app.chunking_widget.set_corpus_mode(self.corpus_mode)


class ChunkTablePanel(Static):
    """Main table panel showing records in three modes: Raw, Decoded, Types."""

    DEFAULT_CSS = """
    ChunkTablePanel {
        border: solid #3b4252;
        height: 1fr;
        layout: vertical;
    }
    ChunkTablePanel:focus-within {
        border: solid #ffa657;
    }
    """

    BINDINGS = [
        ("j", "next_item", "Next"),
        ("k", "prev_item", "Previous"),
        ("n", "next_unknown", "Next Unknown"),
        ("enter", "focus_name", "Edit Type"),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.records: list[RecordSpan] = []
        self.type_stats: dict[str, TypeStats] = {}
        self.registry: dict[str, TypeRegistryEntry] = {}
        self.readers: dict[str, PagedReader] = {}
        self.current_mode = "types"  # Default to Types view (type-centric workflow)
        self.type_filter = "all"  # all, unknown, tentative, confirmed
        self.type_sort = "count_desc"  # count_desc, unknown_first, variability

    def compose(self):
        # Mode selector
        yield Horizontal(
            Button("Types", id="mode-types-btn", variant="primary"),
            Button("Raw", id="mode-raw-btn"),
            Button("Decoded", id="mode-decoded-btn"),
            id="mode-buttons",
        )
        # Types toolbar (only visible in Types mode)
        with Horizontal(id="types-toolbar", classes="hidden"):
            yield Label("Filter:")
            yield Select(
                [
                    ("All", "all"),
                    ("Unknown", "unknown"),
                    ("Tentative", "tentative"),
                    ("Confirmed", "confirmed"),
                ],
                value="all",
                id="type-filter-select",
            )
            yield Label("Sort:")
            yield Select(
                [
                    ("Count ↓", "count_desc"),
                    ("Type ID", "type_id"),
                    ("Unknown First", "unknown_first"),
                    ("Variability", "variability"),
                ],
                value="count_desc",
                id="type-sort-select",
            )
            yield Label("", id="type-progress-label")
        # Main tree
        yield Tree("Records", id="chunk-tree")

    @on(Button.Pressed, "#mode-types-btn")
    def show_types(self) -> None:
        self.current_mode = "types"
        self._update_button_styles()
        self._update_toolbar_visibility()
        self.rebuild()

    @on(Button.Pressed, "#mode-raw-btn")
    def show_raw(self) -> None:
        self.current_mode = "raw"
        self._update_button_styles()
        self._update_toolbar_visibility()
        self.rebuild()

    @on(Button.Pressed, "#mode-decoded-btn")
    def show_decoded(self) -> None:
        self.current_mode = "decoded"
        self._update_button_styles()
        self._update_toolbar_visibility()
        self.rebuild()

    @on(Select.Changed, "#type-filter-select")
    def filter_changed(self, event: Select.Changed) -> None:
        self.type_filter = str(event.value)
        self.rebuild()

    @on(Select.Changed, "#type-sort-select")
    def sort_changed(self, event: Select.Changed) -> None:
        self.type_sort = str(event.value)
        self.rebuild()

    def _update_button_styles(self) -> None:
        """Update button variants based on current mode."""
        self.query_one("#mode-types-btn", Button).variant = (
            "primary" if self.current_mode == "types" else "default"
        )
        self.query_one("#mode-raw-btn", Button).variant = (
            "primary" if self.current_mode == "raw" else "default"
        )
        self.query_one("#mode-decoded-btn", Button).variant = (
            "primary" if self.current_mode == "decoded" else "default"
        )

    def _update_toolbar_visibility(self) -> None:
        """Show/hide types toolbar based on current mode."""
        toolbar = self.query_one("#types-toolbar", Horizontal)
        if self.current_mode == "types":
            toolbar.remove_class("hidden")
        else:
            toolbar.add_class("hidden")

    def set_data(
        self,
        records: list[RecordSpan],
        type_stats: dict[str, TypeStats],
        registry: dict[str, TypeRegistryEntry],
        readers: dict[str, PagedReader],
    ) -> None:
        """Update table with new scan results."""
        self.records = records
        self.type_stats = type_stats
        self.registry = registry
        self.readers = readers
        self.rebuild()

    def rebuild(self) -> None:
        """Rebuild tree based on current mode."""
        tree = self.query_one("#chunk-tree", Tree)
        tree.clear()

        if self.current_mode == "raw":
            self._build_raw_view(tree)
        elif self.current_mode == "decoded":
            self._build_decoded_view(tree)
        elif self.current_mode == "types":
            self._build_types_view(tree)

        tree.root.expand()

    def _build_raw_view(self, tree: Tree) -> None:
        """Build raw records view."""
        tree.label = f"Raw Records ({len(self.records)} total)"
        if not self.records:
            tree.root.add_leaf(
                Text("No records found — adjust framing params and Scan", style="italic dim")
            )
        else:
            for i, record in enumerate(self.records[:1000]):  # Limit to 1000 for performance
                label = self._format_raw_record(record)
                tree.root.add_leaf(label, data=record)

    def _build_decoded_view(self, tree: Tree) -> None:
        """Build decoded records view."""
        tree.label = f"Decoded Records ({len(self.records)} total)"
        if not self.records:
            tree.root.add_leaf(
                Text("No records found — adjust framing params and Scan", style="italic dim")
            )
        else:
            for i, record in enumerate(self.records[:1000]):
                label = self._format_decoded_record(record)
                tree.root.add_leaf(label, data=record)

    def _build_types_view(self, tree: Tree) -> None:
        """Build types summary view with filtering and sorting."""
        # Filter types based on status
        filtered_stats = self._filter_types()

        # Sort types
        sorted_types = self._sort_types(filtered_stats)

        # Update progress label
        total_types = len(self.type_stats)
        assigned_types = sum(1 for key in self.type_stats if key in self.registry)
        try:
            progress_label = self.query_one("#type-progress-label", Label)
            progress_label.update(f"Assigned {assigned_types} / {total_types}")
        except:
            pass

        # Update tree
        tree.label = f"Types ({len(sorted_types)} shown, {len(self.type_stats)} total)"

        if not sorted_types:
            if self.type_filter != "all":
                tree.root.add_leaf(
                    Text(f"No {self.type_filter} types", style="italic dim")
                )
            else:
                tree.root.add_leaf(
                    Text("No types found — scan file first", style="italic dim")
                )
        else:
            for type_key, stats in sorted_types:
                label = self._format_type_stats(type_key, stats)
                node = tree.root.add(label, data=stats, expand=False)
                # Add example records as children
                for example in stats.example_records[:10]:
                    example_label = self._format_raw_record(example, show_type=False)
                    node.add_leaf(example_label, data=example)

    def _filter_types(self) -> dict[str, TypeStats]:
        """Filter types based on current filter setting."""
        if self.type_filter == "all":
            return self.type_stats

        filtered = {}
        for type_key, stats in self.type_stats.items():
            entry = self.registry.get(type_key)
            if self.type_filter == "unknown":
                if entry is None or entry.status == DecoderStatus.UNKNOWN:
                    filtered[type_key] = stats
            elif self.type_filter == "tentative":
                if entry and entry.status == DecoderStatus.TENTATIVE:
                    filtered[type_key] = stats
            elif self.type_filter == "confirmed":
                if entry and entry.status == DecoderStatus.CONFIRMED:
                    filtered[type_key] = stats
        return filtered

    def _sort_types(self, stats_dict: dict[str, TypeStats]) -> list[tuple[str, TypeStats]]:
        """Sort types based on current sort setting."""
        items = list(stats_dict.items())

        if self.type_sort == "count_desc":
            return sorted(items, key=lambda x: x[1].count, reverse=True)
        elif self.type_sort == "type_id":
            # Sort alphabetically by type_key (hex string)
            return sorted(items, key=lambda x: x[0])
        elif self.type_sort == "unknown_first":
            # Unknown first, then by count
            def sort_key(item):
                type_key, stats = item
                entry = self.registry.get(type_key)
                is_unknown = entry is None or entry.status == DecoderStatus.UNKNOWN
                return (not is_unknown, -stats.count)
            return sorted(items, key=sort_key)
        elif self.type_sort == "variability":
            # Most variable first (max-min len + distinct payload hashes)
            def variability(stats: TypeStats) -> float:
                len_spread = (stats.max_len or 0) - (stats.min_len or 0) if stats.min_len is not None else 0
                hash_diversity = len(stats.distinct_hashes)
                return len_spread + hash_diversity * 10
            return sorted(items, key=lambda x: variability(x[1]), reverse=True)

        return items

    def _format_raw_record(self, record: RecordSpan, show_type: bool = True) -> Text:
        """Format a record for raw view."""
        text = Text()
        text.append(f"{record.offset:08x}", style=PALETTE.parsed_offset)
        if show_type:
            text.append(" │ ", style=PALETTE.parsed_punct)
            text.append(record.type_bytes.hex(), style=PALETTE.parsed_name)
        text.append(" │ ", style=PALETTE.parsed_punct)
        text.append(f"len={record.payload_len}", style=PALETTE.parsed_type)

        # Get payload preview
        if record.file_id in self.readers:
            reader = self.readers[record.file_id]
            preview = record.get_payload_preview(reader, 16)
            text.append(" │ ", style=PALETTE.parsed_punct)
            text.append(preview.hex()[:32], style=PALETTE.parsed_value)

        if record.suspicious:
            text.append(" ⚠", style="red")
        return text

    def _format_decoded_record(self, record: RecordSpan) -> Text:
        """Format a record for decoded view."""
        text = Text()
        text.append(f"{record.offset:08x}", style=PALETTE.parsed_offset)
        text.append(" │ ", style=PALETTE.parsed_punct)

        # Get type name
        entry = self.registry.get(record.type_key)
        if entry:
            text.append(entry.name, style=PALETTE.parsed_name)
            text.append(" │ ", style=PALETTE.parsed_punct)

            # Decode payload
            if record.file_id in self.readers:
                reader = self.readers[record.file_id]
                payload = reader.read(record.payload_offset, record.payload_len)
                decoded = decode_payload(payload, entry.decoder_id, entry.decoder_params)
                if decoded:
                    text.append(decoded[:60], style=PALETTE.parsed_value)
                else:
                    text.append(payload.hex()[:32], style=PALETTE.parsed_value)
        else:
            text.append(record.type_key, style=PALETTE.inspector_dim)
            text.append(" │ ", style=PALETTE.parsed_punct)
            if record.file_id in self.readers:
                reader = self.readers[record.file_id]
                preview = record.get_payload_preview(reader, 16)
                text.append(preview.hex()[:32], style=PALETTE.parsed_value)

        return text

    def _format_type_stats(self, type_key: str, stats: TypeStats) -> Text:
        """Format type statistics with raw hex (and optional ASCII if printable)."""
        text = Text()
        entry = self.registry.get(type_key)

        # Status indicator
        if entry is None or entry.status == DecoderStatus.UNKNOWN:
            text.append("? ", style="yellow bold")
        elif entry.status == DecoderStatus.TENTATIVE:
            text.append("~ ", style="cyan")
        elif entry.status == DecoderStatus.CONFIRMED:
            text.append("✓ ", style="green")

        # Name or raw bytes
        if entry:
            text.append(entry.name, style=PALETTE.parsed_name)
        else:
            text.append(f"unk_{stats.type_bytes.hex()[:6]}", style=PALETTE.inspector_dim)

        # Type bytes (raw hex only)
        text.append(" │ ", style=PALETTE.parsed_punct)
        text.append(stats.type_bytes.hex(), style=PALETTE.parsed_offset)

        # Show ASCII if printable
        try:
            ascii_str = stats.type_bytes.decode('ascii')
            if ascii_str.isprintable() and not ascii_str.isspace():
                text.append(f" ({ascii_str})", style=PALETTE.inspector_dim)
        except:
            pass

        # Count and stats
        text.append(" │ ", style=PALETTE.parsed_punct)
        text.append(f"{stats.count}×", style=PALETTE.parsed_type)
        text.append(" │ ", style=PALETTE.parsed_punct)
        text.append(
            f"{stats.min_len}-{stats.max_len}b",
            style=PALETTE.parsed_value,
        )

        return text

    @on(Tree.NodeSelected, "#chunk-tree")
    def record_selected(self, event: Tree.NodeSelected) -> None:
        """Handle record/type selection."""
        if event.node.data:
            app: HexmapApp = self.app  # type: ignore
            if isinstance(event.node.data, RecordSpan):
                # Jump to record in hex view
                if hasattr(app, "hex_view") and app.hex_view:
                    app.hex_view.set_cursor(event.node.data.offset)
                # Update inspector
                if hasattr(app, "chunking_widget"):
                    app.chunking_widget.select_record(event.node.data)
            elif isinstance(event.node.data, TypeStats):
                # Show type in inspector
                if hasattr(app, "chunking_widget"):
                    app.chunking_widget.select_type(event.node.data)

    def action_next_item(self) -> None:
        """Move selection down in the tree (j key)."""
        tree = self.query_one("#chunk-tree", Tree)
        if tree.cursor_node:
            next_node = tree.cursor_node.next_node
            if next_node:
                tree.select_node(next_node)

    def action_prev_item(self) -> None:
        """Move selection up in the tree (k key)."""
        tree = self.query_one("#chunk-tree", Tree)
        if tree.cursor_node:
            prev_node = tree.cursor_node.previous_node
            if prev_node:
                tree.select_node(prev_node)

    def action_next_unknown(self) -> None:
        """Jump to next unknown type (n key)."""
        if self.current_mode != "types":
            return

        tree = self.query_one("#chunk-tree", Tree)

        # Find all unknown type nodes
        unknown_nodes = []
        for node in tree.root.children:
            if isinstance(node.data, TypeStats):
                type_key = node.data.type_key
                entry = self.registry.get(type_key)
                if entry is None or entry.status == DecoderStatus.UNKNOWN:
                    unknown_nodes.append(node)

        if not unknown_nodes:
            return

        # Find next unknown after current selection
        current = tree.cursor_node
        if current:
            try:
                current_idx = unknown_nodes.index(current)
                # Move to next unknown (wrap around)
                next_idx = (current_idx + 1) % len(unknown_nodes)
                tree.select_node(unknown_nodes[next_idx])
            except ValueError:
                # Current node not in unknowns, jump to first
                tree.select_node(unknown_nodes[0])
        else:
            # No current selection, jump to first unknown
            tree.select_node(unknown_nodes[0])

    def action_focus_name(self) -> None:
        """Focus the Name input field in inspector (enter key)."""
        app: HexmapApp = self.app  # type: ignore
        if hasattr(app, "chunking_widget"):
            app.chunking_widget.focus_name_field()


class TypeRegistryInspector(Static):
    """Inspector panel for editing type registry entries."""

    DEFAULT_CSS = """
    TypeRegistryInspector {
        border: solid #3b4252;
        height: 1fr;
        layout: vertical;
    }
    TypeRegistryInspector:focus-within {
        border: solid #ffa657;
    }
    """

    BINDINGS = [
        ("ctrl+enter", "apply_quick", "Apply"),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.current_type_key: str | None = None
        self.current_entry: TypeRegistryEntry | None = None
        self.current_stats: TypeStats | None = None
        self.registry: dict[str, TypeRegistryEntry] = {}
        self.readers: dict[str, PagedReader] = {}
        # Preview state (live decoder selection before Apply)
        self.preview_decoder_id: str = "none"
        self.preview_decoder_params: DecoderParams = DecoderParams()

    def compose(self):
        yield Label("Type Inspector", id="registry-header")
        with VerticalScroll(id="registry-content"):
            # Empty state
            yield Static("No type selected\nSelect a type from Types view", id="registry-info")

            # === PREVIEW SECTION (top): decoder picker + live decoded examples ===
            with Vertical(id="preview-section", classes="hidden"):
                yield Label("Preview", id="preview-header")
                # Type identity (raw + ASCII only)
                yield Static("", id="type-key-display")
                yield Static("", id="type-normalized-display")
                # Decoder selector (preview control)
                yield Label("Decoder:")
                yield Select(
                    [
                        ("None", "none"),
                        ("Integer", "int"),
                        ("String", "string"),
                        ("Date", "date"),
                        ("Bit Flags", "bitflags"),
                        ("Hex", "hex"),
                    ],
                    value="none",
                    id="preview-decoder-select",
                )
                # Decoded examples (rendered with preview decoder)
                yield Label("Examples:")
                yield VerticalScroll(Static("", id="examples-display"), id="examples-scroll")

            # === REGISTRY SECTION (below): commit with name/notes/status ===
            with Vertical(id="registry-section", classes="hidden"):
                yield Label("Registry", id="registry-label")
                yield Label("Name:")
                yield Input(value="", id="type-name-input")
                yield Label("Notes:")
                yield Input(value="", id="type-notes-input")
                yield Label("Status:")
                yield Select(
                    [
                        ("Unknown", "unknown"),
                        ("Tentative", "tentative"),
                        ("Confirmed", "confirmed"),
                    ],
                    value="unknown",
                    id="status-select",
                )
                with Horizontal(id="registry-buttons"):
                    yield Button("Apply", variant="primary", id="apply-button")
                    yield Button("Revert", id="revert-button")

    def set_type(
        self,
        type_stats: TypeStats,
        registry: dict[str, TypeRegistryEntry],
        readers: dict[str, PagedReader],
    ) -> None:
        """Set the current type to inspect/edit."""
        self.current_type_key = type_stats.type_key
        self.current_stats = type_stats
        self.registry = registry
        self.readers = readers

        # Get or create registry entry
        if type_stats.type_key in registry:
            self.current_entry = registry[type_stats.type_key]
        else:
            self.current_entry = TypeRegistryEntry(
                key_bytes=type_stats.type_bytes,
                name=f"unk_{type_stats.type_bytes.hex()[:8]}",
                decoder_id="none",
            )

        # Initialize preview state from current entry
        self.preview_decoder_id = self.current_entry.decoder_id
        self.preview_decoder_params = self.current_entry.decoder_params

        # Show sections
        self.query_one("#registry-info", Static).display = False
        self.query_one("#preview-section", Vertical).remove_class("hidden")
        self.query_one("#registry-section", Vertical).remove_class("hidden")

        self._populate_identity()
        self._populate_fields()
        self._update_examples()

    def _populate_identity(self) -> None:
        """Populate type identity section - raw hex and ASCII if printable."""
        if not self.current_entry or not self.current_stats:
            return

        # Show raw bytes
        raw_display = self.query_one("#type-key-display", Static)
        raw_display.update(f"Raw: {self.current_entry.key_bytes.hex()}")

        # Show ASCII only if printable
        norm_display = self.query_one("#type-normalized-display", Static)
        try:
            ascii_str = self.current_entry.key_bytes.decode('ascii')
            if ascii_str.isprintable() and not ascii_str.isspace():
                norm_display.update(f"ASCII: {ascii_str}")
            else:
                norm_display.update("ASCII: —")
        except:
            norm_display.update("ASCII: —")

    def _populate_fields(self) -> None:
        """Populate editor fields with current entry."""
        if not self.current_entry:
            return

        # Set preview decoder select
        self.query_one("#preview-decoder-select", Select).value = self.preview_decoder_id
        # Set registry fields
        self.query_one("#type-name-input", Input).value = self.current_entry.name
        self.query_one("#type-notes-input", Input).value = self.current_entry.notes
        self.query_one("#status-select", Select).value = self.current_entry.status.value

    @on(Select.Changed, "#preview-decoder-select")
    def preview_decoder_changed(self, event: Select.Changed) -> None:
        """Handle preview decoder selection - immediately re-render examples."""
        self.preview_decoder_id = str(event.value)
        # TODO: Update decoder params based on decoder type
        self.preview_decoder_params = DecoderParams()
        # Re-render examples with new decoder
        self._update_examples()

    def _update_examples(self) -> None:
        """Update examples display with decoded previews using preview decoder."""
        if not self.current_stats:
            return

        # Get diverse examples: shortest, longest, first, last, random samples
        examples = []
        all_examples = self.current_stats.example_records

        if all_examples:
            # Shortest
            shortest = min(all_examples, key=lambda r: r.payload_len)
            examples.append(("Shortest", shortest))

            # Longest
            longest = max(all_examples, key=lambda r: r.payload_len)
            if longest != shortest:
                examples.append(("Longest", longest))

            # First and last
            if len(all_examples) > 2:
                examples.append(("First", all_examples[0]))
                if all_examples[-1] not in [shortest, longest, all_examples[0]]:
                    examples.append(("Last", all_examples[-1]))

            # Random samples
            import random
            remaining = [r for r in all_examples if r not in [e[1] for e in examples]]
            if remaining:
                samples = random.sample(remaining, min(6, len(remaining)))
                for i, sample in enumerate(samples):
                    examples.append((f"Sample {i+1}", sample))

        # Format examples with decoded previews using preview decoder
        examples_text = Text()
        for label, example in examples[:10]:  # Limit to 10
            examples_text.append(f"{label}: ", style=PALETTE.inspector_label)
            examples_text.append(f"{example.offset:08x}", style=PALETTE.parsed_offset)
            examples_text.append(f" [{example.payload_len}b] ", style=PALETTE.parsed_type)

            if example.file_id in self.readers:
                reader = self.readers[example.file_id]
                payload = reader.read(example.payload_offset, example.payload_len)

                # Show decoded preview if preview decoder is set
                if self.preview_decoder_id != "none":
                    from hexmap.core.chunks import decode_payload
                    decoded = decode_payload(payload, self.preview_decoder_id, self.preview_decoder_params)
                    if decoded:
                        # Show decoded value prominently
                        examples_text.append(decoded[:60], style=PALETTE.inspector_value)
                        # Show hex as secondary
                        preview = payload[:16]
                        examples_text.append(f" ({preview.hex()[:32]})", style=PALETTE.inspector_dim)
                    else:
                        # Decoder failed, show hex
                        preview = payload[:16]
                        examples_text.append(preview.hex()[:32], style=PALETTE.parsed_value)
                else:
                    # No decoder, show hex only
                    preview = payload[:16]
                    examples_text.append(preview.hex()[:32], style=PALETTE.parsed_value)

            examples_text.append("\n")

        self.query_one("#examples-display", Static).update(examples_text)

    @on(Button.Pressed, "#apply-button")
    def apply_changes(self) -> None:
        """Apply changes to registry entry - commits preview decoder."""
        if not self.current_type_key or not self.current_entry:
            return

        # Read current values
        name = self.query_one("#type-name-input", Input).value
        notes = self.query_one("#type-notes-input", Input).value
        status_str = str(self.query_one("#status-select", Select).value)

        # Update entry with preview decoder (commit the preview)
        self.current_entry = TypeRegistryEntry(
            key_bytes=self.current_entry.key_bytes,
            name=name,
            decoder_id=self.preview_decoder_id,  # Commit preview decoder
            decoder_params=self.preview_decoder_params,  # Commit preview params
            notes=notes,
            status=DecoderStatus(status_str),
        )

        # Update registry
        self.registry[self.current_type_key] = self.current_entry

        # Notify app to refresh views
        app: HexmapApp = self.app  # type: ignore
        if hasattr(app, "chunking_widget"):
            app.chunking_widget.registry_updated()

    @on(Button.Pressed, "#revert-button")
    def revert_changes(self) -> None:
        """Revert to saved registry entry and reset preview decoder."""
        if self.current_entry:
            # Reset preview state to match current entry
            self.preview_decoder_id = self.current_entry.decoder_id
            self.preview_decoder_params = self.current_entry.decoder_params
        self._populate_fields()
        self._update_examples()

    def action_apply_quick(self) -> None:
        """Quick apply with ctrl+enter."""
        self.apply_changes()


class ChunkingWidget(Container):
    """Main coordinating widget for the Chunking tab."""

    DEFAULT_CSS = """
    ChunkingWidget {
        layout: horizontal;
        height: 1fr;
    }
    """

    def __init__(self, reader: PagedReader | None = None) -> None:
        super().__init__()
        self.reader = reader
        self.records: list[RecordSpan] = []
        self.type_stats: dict[str, TypeStats] = {}
        self.registry: dict[str, TypeRegistryEntry] = {}
        self.readers: dict[str, PagedReader] = {}
        self.corpus_mode = False

        if reader:
            file_id = str(reader.path) if hasattr(reader, "path") else "primary"
            self.readers[file_id] = reader

    def compose(self):
        # Left column: framing controls + file selector
        with Vertical(id="chunking-left-col", classes="chunking-column"):
            yield ChunkFramingPanel()
            yield FileCorpusSelector()
        # Middle column: main table
        yield ChunkTablePanel(classes="chunking-column chunking-middle")
        # Right column: inspector
        yield TypeRegistryInspector(classes="chunking-column")

    def on_mount(self) -> None:
        """Auto-scan with default params on mount."""
        if self.readers:
            # Update file list display
            self._update_file_list()
            # Get default params from framing panel
            framing_panel = self.query_one(ChunkFramingPanel)
            self.scan_with_params(framing_panel.params)

    def _update_file_list(self) -> None:
        """Update the file list display in the corpus selector."""
        try:
            file_list_display = self.query_one("#file-list-display", Static)
            if self.readers:
                file_names = [str(Path(file_id).name) for file_id in self.readers.keys()]
                file_list_display.update("\n".join(f"• {name}" for name in file_names))
            else:
                file_list_display.update("No files loaded")
        except:
            pass

    def scan_with_params(self, params: FramingParams) -> None:
        """Scan current file(s) with given framing parameters."""
        app: HexmapApp = self.app  # type: ignore

        if not self.readers:
            app.set_status_hint("No file loaded")
            return

        app.set_status_hint("Scanning chunks...")

        all_records: list[RecordSpan] = []
        all_errors: list[str] = []

        # Scan all readers
        for file_id, reader in self.readers.items():
            try:
                records, errors = scan_chunks(reader, params, file_id)
                all_records.extend(records)
                all_errors.extend(errors)
            except Exception as e:
                all_errors.append(f"Scan failed for {file_id}: {e}")

        self.records = all_records
        self.type_stats = build_type_stats(all_records)

        # Update table
        table = self.query_one(ChunkTablePanel)
        table.set_data(self.records, self.type_stats, self.registry, self.readers)

        # Update status
        status = f"Found {len(all_records)} records, {len(self.type_stats)} unique types"
        if all_errors:
            status += f" ({len(all_errors)} errors)"
        app.set_status_hint(status)

    def set_corpus_mode(self, enabled: bool) -> None:
        """Toggle corpus mode."""
        self.corpus_mode = enabled
        # TODO: Implement multi-file selection UI

    def select_record(self, record: RecordSpan) -> None:
        """Handle record selection."""
        # Could show record details in inspector
        pass

    def select_type(self, type_stats: TypeStats) -> None:
        """Handle type selection - show in inspector."""
        inspector = self.query_one(TypeRegistryInspector)
        inspector.set_type(type_stats, self.registry, self.readers)

    def focus_name_field(self) -> None:
        """Focus the Name input field in the inspector."""
        try:
            name_input = self.query_one("#type-name-input", Input)
            name_input.focus()
        except:
            pass

    def registry_updated(self) -> None:
        """Called when registry is modified - refresh decoded view."""
        table = self.query_one(ChunkTablePanel)
        table.set_data(self.records, self.type_stats, self.registry, self.readers)

    def update_for(self, reader: PagedReader) -> None:
        """Update when reader changes."""
        self.reader = reader
        file_id = str(reader.path) if hasattr(reader, "path") else "primary"
        self.readers[file_id] = reader
