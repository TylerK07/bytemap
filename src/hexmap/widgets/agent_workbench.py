"""Agent Workbench tab for LLM-driven spec iteration.

This widget provides the main UI for Phase 7's spec iteration system.
PR#1: Initial shell with 3-column placeholder layout.
PR#2: State model with selection cascade and mock data.
PR#3: Real SpecStore integration with run artifacts.
PR#4: Column 2 Patch Ops UI with real data.
PR#5: Column 2 Runs UI with real data.
PR#6: Column 3 Evidence with hex view integration.
PR#7: Draft/Promote/Branch functionality.
PR#8: Chat interface for LLM-driven patch proposals.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Button, Input, Label, OptionList, Static, TabbedContent, TabPane

from hexmap.core.run_scoring import score_run
from hexmap.core.spec_patch import InsertField, Patch, path_to_string
from hexmap.widgets.workbench_manager import WorkbenchManager
from hexmap.widgets.workbench_state import (
    EvidenceSelected,
    PatchOpSelected,
    RunSelected,
    VersionCheckedOut,
    VersionSelected,
    WorkbenchState,
)


# ============================================================================
# PR#6: HEX VIEW INTEGRATION MESSAGES
# ============================================================================


class HighlightBytesRequest(Message):
    """Request to highlight byte ranges in hex view.

    Posted when user selects a run with errors/anomalies or patch op.
    """

    def __init__(self, byte_ranges: list[tuple[int, int]], jump_to_offset: int | None = None) -> None:
        """Initialize highlight request.

        Args:
            byte_ranges: List of (offset, length) tuples to highlight
            jump_to_offset: Optional offset to jump cursor to
        """
        super().__init__()
        self.byte_ranges = byte_ranges
        self.jump_to_offset = jump_to_offset


class AgentWorkbenchTab(Container):
    """Agent Workbench tab - main container for spec iteration UI.

    Layout: 3 columns (Versions | Patches/Runs | Evidence).

    PR#2: Added state model and selection cascade with mock data.
    PR#6: Added hex view integration for byte highlighting.
    """

    # Reactive state fields
    selected_version_id: str | None = reactive(None)
    selected_patch_op_id: str | None = reactive(None)
    selected_run_id: str | None = reactive(None)

    def __init__(self, file_path: str) -> None:
        """Initialize the Agent Workbench tab.

        Args:
            file_path: Path to the binary file being analyzed
        """
        super().__init__()
        self.file_path = file_path
        self.state = WorkbenchState()

        # PR#3: WorkbenchManager for real SpecStore integration
        self.manager: WorkbenchManager | None = None

        # Widget references (populated in compose)
        self._version_list: OptionList | None = None
        self._patch_ops_list: OptionList | None = None
        self._runs_list: OptionList | None = None
        self._version_inspector: Static | None = None
        self._patch_ops_inspector: Static | None = None
        self._runs_inspector: Static | None = None
        self._evidence_content: Static | None = None
        self._checkout_button: Button | None = None
        self._promote_button: Button | None = None
        self._branch_button: Button | None = None

        # PR#8: Chat UI components
        self._chat_log: Static | None = None
        self._chat_input: Input | None = None
        self._chat_send_button: Button | None = None
        self._suggest_patch_button: Button | None = None
        self._chat_messages: list[tuple[str, str]] = []  # [(role, content), ...]

        # Index mappings for OptionList (option_index → id)
        self._version_index_to_id: dict[int, str] = {}
        self._patch_op_index_to_id: dict[int, str] = {}
        self._run_index_to_id: dict[int, str] = {}

    def compose(self) -> ComposeResult:
        """Compose the 3-column layout with selectable lists."""
        # Header showing file context
        yield Static(
            f"Agent Workbench: {self.file_path}",
            id="workbench-header"
        )

        # 3-column layout
        with Horizontal(id="workbench-columns"):
            # Column 1: Versions & Chat (left)
            with Vertical(id="workbench-col1", classes="workbench-column"):
                yield Label("Column 1: Versions & Chat", classes="column-header")

                # PR#8: Tabbed interface for Versions and Chat
                with TabbedContent(id="versions-chat-tabs"):
                    # Versions tab
                    with TabPane("Versions", id="tab-versions"):
                        with ScrollableContainer(classes="column-scroll"):
                            self._version_list = OptionList(id="version-list")
                            yield self._version_list

                        # Version inspector (bottom)
                        with Container(classes="column-inspector"):
                            self._version_inspector = Static(
                                "Select a version to view details",
                                id="version-inspector"
                            )
                            yield self._version_inspector

                            # Action buttons
                            with Horizontal(id="version-actions"):
                                self._checkout_button = Button("Checkout", id="btn-checkout", variant="primary")
                                yield self._checkout_button
                                self._promote_button = Button("Promote", id="btn-promote")
                                yield self._promote_button
                                self._branch_button = Button("Branch", id="btn-branch")
                                yield self._branch_button

                    # Chat tab (PR#8)
                    with TabPane("Chat", id="tab-chat"):
                        with Vertical(id="chat-container"):
                            # Chat message log
                            with ScrollableContainer(id="chat-log-scroll", classes="column-scroll"):
                                self._chat_log = Static(
                                    "Chat: Ask the assistant to suggest spec improvements.\n\n"
                                    'Try: "Suggest a patch to fix the parse errors"',
                                    id="chat-log"
                                )
                                yield self._chat_log

                            # Chat input area
                            with Vertical(id="chat-input-area"):
                                self._chat_input = Input(
                                    placeholder="Ask for patch suggestions...",
                                    id="chat-input"
                                )
                                yield self._chat_input

                                with Horizontal(id="chat-buttons"):
                                    self._chat_send_button = Button(
                                        "Send",
                                        id="btn-chat-send",
                                        variant="primary"
                                    )
                                    yield self._chat_send_button

                                    self._suggest_patch_button = Button(
                                        "Suggest Patch",
                                        id="btn-suggest-patch"
                                    )
                                    yield self._suggest_patch_button

            # Column 2: Patches & Runs (middle)
            with Vertical(id="workbench-col2", classes="workbench-column"):
                yield Label("Column 2: Patches & Runs", classes="column-header")

                with ScrollableContainer(classes="column-scroll"):
                    # Patch ops section
                    yield Label("Patch Operations:", classes="section-label")
                    self._patch_ops_list = OptionList(id="patch-ops-list")
                    yield self._patch_ops_list

                    # Runs section
                    yield Label("Runs:", classes="section-label")
                    self._runs_list = OptionList(id="runs-list")
                    yield self._runs_list

                # Patch/Run inspector (bottom)
                with Container(classes="column-inspector"):
                    self._patch_ops_inspector = Static(
                        "Patch operations will appear here",
                        id="patch-ops-inspector"
                    )
                    yield self._patch_ops_inspector

                    self._runs_inspector = Static(
                        "Run details will appear here",
                        id="runs-inspector"
                    )
                    yield self._runs_inspector

            # Column 3: Evidence (right)
            with Vertical(id="workbench-col3", classes="workbench-column"):
                yield Label("Column 3: Evidence", classes="column-header")

                with ScrollableContainer(classes="column-scroll"):
                    self._evidence_content = Static(
                        "Evidence will appear when patch op or run is selected",
                        id="evidence-content"
                    )
                    yield self._evidence_content

    def on_mount(self) -> None:
        """Initialize lists when mounted."""
        # Note: Version list will be empty until initialize_with_schema() is called
        # Show helpful message in version list
        if self._version_list:
            self._version_list.add_option("Waiting for schema initialization...")
        if self._version_inspector:
            self._version_inspector.update(
                "Workbench will initialize when you switch to this tab.\n\n"
                "If you see this message, try:\n"
                "1. Switch to another tab (e.g., Explore)\n"
                "2. Come back to the Workbench tab"
            )
        self._update_button_states()

    def initialize_with_schema(self, spec_text: str, label: str = "Initial") -> None:
        """Initialize workbench with schema text.

        This should be called by the app after the tab is mounted.

        Args:
            spec_text: YAML grammar text
            label: Display label for initial version
        """
        # Validate input
        if not spec_text or not spec_text.strip():
            if self._version_list:
                self._version_list.clear_options()
                self._version_list.add_option("Error: No schema text provided")
            if self._version_inspector:
                self._version_inspector.update(
                    "Cannot initialize: Schema is empty.\n\n"
                    "Please load or create a schema in the Explore tab."
                )
            return

        # Create manager
        self.manager = WorkbenchManager(self.file_path)

        # Create initial version
        try:
            version_id = self.manager.create_initial_version(spec_text, label)
            # Populate version list
            self._populate_version_list()
            # Auto-select the initial version
            if self._version_list and len(self._version_index_to_id) > 0:
                self._version_list.highlighted = 0
        except ValueError as e:
            # Show error in version list
            if self._version_list:
                self._version_list.clear_options()
                self._version_list.add_option(f"Error: {e}")
            if self._version_inspector:
                self._version_inspector.update(f"Failed to initialize: {e}")

    # ========================================================================
    # VERSION LIST POPULATION
    # ========================================================================

    def _populate_version_list(self) -> None:
        """Populate version list with real data from manager."""
        if self._version_list is None:
            # This should never happen, but handle gracefully
            return

        if self.manager is None:
            # Manager not initialized yet
            self._version_list.clear_options()
            self._version_list.add_option("Manager not initialized")
            return

        self._version_list.clear_options()
        self._version_index_to_id.clear()

        # Get all versions from manager
        versions = self.manager.get_all_versions()

        if not versions:
            # No versions available
            self._version_list.add_option("No versions available")
            return

        for idx, metadata in enumerate(versions):
            # Get display info
            info = self.manager.get_version_display_info(metadata.version.id)

            # Format: "[role] label status (score: X, Δ: +Y%)"
            role_badge = f"[{info['role']}]"

            # Status badge
            if info['status'] == 'ok':
                status_badge = "✓"
            elif info['status'] == 'lint_error':
                status_badge = "✗lint"
            elif info['status'] == 'parse_error':
                status_badge = "✗parse"
            else:
                status_badge = "?"

            # Score
            score_str = f"{info['score']:.0f}" if info['score'] is not None else "—"

            # Coverage delta
            delta_str = ""
            if info['coverage_delta'] is not None:
                delta_str = f", Δ: {info['coverage_delta']:+.1f}%"

            # Checkout marker
            checkout_marker = " ⬤" if info['is_checked_out'] else ""

            label = f"{role_badge} {info['label']} {status_badge} (score: {score_str}{delta_str}){checkout_marker}"

            self._version_list.add_option(label)
            self._version_index_to_id[idx] = info['version_id']

    # ========================================================================
    # SELECTION HANDLERS
    # ========================================================================

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle selection in any OptionList."""
        # Determine which list was selected
        if event.option_list is self._version_list:
            self._handle_version_selected(event.option_index)
        elif event.option_list is self._patch_ops_list:
            self._handle_patch_op_selected(event.option_index)
        elif event.option_list is self._runs_list:
            self._handle_run_selected(event.option_index)

    def _handle_version_selected(self, option_index: int) -> None:
        """Handle version selection."""
        version_id = self._version_index_to_id.get(option_index)
        if version_id is None:
            return

        # Update state
        self.state.selected_version_id = version_id
        self.state.clear_derived_selections()

        # Update reactive property (triggers watchers)
        self.selected_version_id = version_id

        # Post message for other components
        self.post_message(VersionSelected(version_id))

    def _handle_patch_op_selected(self, option_index: int) -> None:
        """Handle patch op selection."""
        patch_op_id = self._patch_op_index_to_id.get(option_index)
        if patch_op_id is None:
            return

        # Update state
        self.state.selected_patch_op_id = patch_op_id
        self.state.clear_evidence_selection()

        # Update reactive property
        self.selected_patch_op_id = patch_op_id

        # Post message
        self.post_message(PatchOpSelected(patch_op_id))

    def _handle_run_selected(self, option_index: int) -> None:
        """Handle run selection."""
        run_id = self._run_index_to_id.get(option_index)
        if run_id is None:
            return

        # Update state
        self.state.selected_run_id = run_id
        self.state.clear_evidence_selection()

        # Update reactive property
        self.selected_run_id = run_id

        # Post message
        self.post_message(RunSelected(run_id))

    # ========================================================================
    # REACTIVE WATCHERS (selection cascade)
    # ========================================================================

    def watch_selected_version_id(self, new_version_id: str | None) -> None:
        """React to version selection changes - update Column 2."""
        if new_version_id is None:
            # Clear Column 2
            self._clear_column2()
            self._update_version_inspector(None)
            return

        # Update Column 2 with patch ops and runs for this version
        self._populate_patch_ops_list(new_version_id)
        self._populate_runs_list(new_version_id)
        self._update_version_inspector(new_version_id)

    def watch_selected_patch_op_id(self, new_patch_op_id: str | None) -> None:
        """React to patch op selection changes - update Column 3.

        PR#6: Now updates evidence and posts hex highlight request.
        """
        if new_patch_op_id is None:
            self._update_patch_ops_inspector(None)
            self._clear_evidence()
            return

        self._update_patch_ops_inspector(new_patch_op_id)
        self._update_evidence_for_patch_op(new_patch_op_id)

    def watch_selected_run_id(self, new_run_id: str | None) -> None:
        """React to run selection changes - update Column 3.

        PR#6: Now updates evidence and posts hex highlight request.
        """
        if new_run_id is None:
            self._update_runs_inspector(None)
            self._clear_evidence()
            return

        self._update_runs_inspector(new_run_id)
        self._update_evidence_for_run(new_run_id)

    # ========================================================================
    # UPDATE METHODS
    # ========================================================================

    def _clear_column2(self) -> None:
        """Clear Column 2 lists and inspectors."""
        if self._patch_ops_list:
            self._patch_ops_list.clear_options()
        if self._runs_list:
            self._runs_list.clear_options()
        self._patch_op_index_to_id.clear()
        self._run_index_to_id.clear()

        if self._patch_ops_inspector:
            self._patch_ops_inspector.update("No version selected")
        if self._runs_inspector:
            self._runs_inspector.update("No version selected")

    def _populate_patch_ops_list(self, version_id: str) -> None:
        """Populate patch ops list for given version.

        PR#4: Now uses real patch operations from version.patch_applied.
        """
        if self._patch_ops_list is None:
            return

        self._patch_ops_list.clear_options()
        self._patch_op_index_to_id.clear()

        # PR#4: Get real patch ops from version
        if self.manager is None:
            self._patch_ops_list.add_option("(no manager)")
            return

        version = self.manager.get_version(version_id)
        if version is None:
            self._patch_ops_list.add_option("(version not found)")
            return

        # Initial version has no patch
        if version.patch_applied is None:
            self._patch_ops_list.add_option("(initial version - no patch)")
            return

        patch = version.patch_applied
        if not patch.ops:
            self._patch_ops_list.add_option("(no patch operations)")
            return

        # Show each op with type and path
        for idx, op in enumerate(patch.ops):
            path_str = path_to_string(op.path)
            label = f"{op.op_type}: {path_str}"
            self._patch_ops_list.add_option(label)
            # Use string index as ID since PatchOp doesn't have an id field
            self._patch_op_index_to_id[idx] = str(idx)

    def _populate_runs_list(self, version_id: str) -> None:
        """Populate runs list for given version.

        PR#5: Now uses real run artifacts from WorkbenchManager.
        """
        if self._runs_list is None:
            return

        self._runs_list.clear_options()
        self._run_index_to_id.clear()

        # PR#5: Get real runs from manager
        if self.manager is None:
            self._runs_list.add_option("(no manager)")
            return

        runs = self.manager.get_runs_for_version(version_id)

        for idx, run in enumerate(runs):
            # Determine status from run stats
            if run.stats.error_count > 0 or run.stats.high_severity_anomalies > 0:
                status_badge = "✗"
            else:
                status_badge = "✓"

            # Get score
            score_result = score_run(run)
            score = score_result.total_score if score_result.passed_hard_gates else 0.0

            # Format label
            label = f"{status_badge} Coverage: {run.stats.coverage_percentage:.1f}%, Score: {score:.0f}"
            self._runs_list.add_option(label)
            self._run_index_to_id[idx] = run.run_id

        if not runs:
            self._runs_list.add_option("(no runs)")

    def _update_version_inspector(self, version_id: str | None) -> None:
        """Update version inspector with selected version details."""
        if self._version_inspector is None:
            return

        if version_id is None or self.manager is None:
            self._version_inspector.update("Select a version to view details")
            self._update_button_states()
            return

        # Get display info
        info = self.manager.get_version_display_info(version_id)
        if "error" in info:
            self._version_inspector.update(f"Error: {info['error']}")
            self._update_button_states()
            return

        # Get metadata
        metadata = self.manager.get_version_metadata(version_id)
        if metadata is None:
            self._version_inspector.update("Version not found")
            self._update_button_states()
            return

        # Format inspector content
        lines = [f"Version: {info['label']}"]
        lines.append(f"Role: {info['role']}")
        lines.append(f"Status: {info['status']}")

        # Lint info
        if not info['lint_valid']:
            lines.append(f"Lint Errors: {len(info['lint_errors'])}")
            if info['lint_errors']:
                lines.append(f"  {info['lint_errors'][0]}")
        else:
            lines.append("Lint: ✓")

        # Run info
        if metadata.run_artifact:
            run = metadata.run_artifact
            lines.append(f"Coverage: {run.stats.coverage_percentage:.1f}%")
            lines.append(f"Records: {run.stats.record_count}")
            lines.append(f"Errors: {run.stats.error_count}")
            lines.append(f"Anomalies: {run.stats.anomaly_count}")
        else:
            lines.append("Run: (none)")

        # Score
        score_str = f"{info['score']:.1f}" if info['score'] is not None else "—"
        lines.append(f"Score: {score_str}")

        # Coverage delta
        if info['coverage_delta'] is not None:
            lines.append(f"Coverage Δ: {info['coverage_delta']:+.1f}%")

        # Checkout status
        if info['is_checked_out']:
            lines.append("Status: ⬤ Checked out")

        content = "\n".join(lines)
        self._version_inspector.update(content)
        self._update_button_states()

    def _update_patch_ops_inspector(self, patch_op_id: str | None) -> None:
        """Update patch ops inspector with selected operation details.

        PR#4: Now shows real patch op details from version.patch_applied.
        """
        if self._patch_ops_inspector is None:
            return

        if patch_op_id is None:
            self._patch_ops_inspector.update("Select a patch operation")
            return

        # Find the patch op in current version's ops
        version_id = self.state.selected_version_id
        if version_id is None or self.manager is None:
            return

        version = self.manager.get_version(version_id)
        if version is None or version.patch_applied is None:
            self._patch_ops_inspector.update("No patch for this version")
            return

        # patch_op_id is a string index
        try:
            op_index = int(patch_op_id)
        except ValueError:
            self._patch_ops_inspector.update("Invalid patch op ID")
            return

        patch = version.patch_applied
        if op_index < 0 or op_index >= len(patch.ops):
            self._patch_ops_inspector.update("Patch operation not found")
            return

        op = patch.ops[op_index]

        # Build inspector content
        lines = []
        lines.append(f"Operation: {op.op_type}")
        lines.append(f"Path: {path_to_string(op.path)}")

        # Show operation-specific details
        if hasattr(op, "field_def"):
            # InsertField
            lines.append(f"Index: {op.index}")
            lines.append(f"Field: {op.field_def}")
        elif hasattr(op, "updates"):
            # UpdateField or UpdateType
            lines.append(f"Updates: {op.updates}")
        elif hasattr(op, "type_def"):
            # AddType
            lines.append(f"Type definition: {len(op.type_def.get('fields', []))} fields")
        elif hasattr(op, "entry"):
            # AddRegistryEntry
            lines.append(f"Registry entry: {op.entry.get('name', '?')}")

        # Show validation status
        is_valid, error = op.validate()
        if is_valid:
            lines.append("\nValidation: ✓")
        else:
            lines.append(f"\nValidation: ✗ {error}")

        # Show patch description
        if patch.description:
            lines.append(f"\nPatch: {patch.description}")

        content = "\n".join(lines)
        self._patch_ops_inspector.update(content)

    def _update_runs_inspector(self, run_id: str | None) -> None:
        """Update runs inspector with selected run details.

        PR#5: Now shows real run artifact details.
        """
        if self._runs_inspector is None:
            return

        if run_id is None:
            self._runs_inspector.update("Select a run")
            return

        # Find the run in current version's runs
        version_id = self.state.selected_version_id
        if version_id is None or self.manager is None:
            return

        # Get the specific run artifact
        run = self.manager.get_run_artifact(run_id)
        if run is None:
            self._runs_inspector.update("Run not found")
            return

        # Build inspector content
        lines = []
        lines.append(f"Run: {run.run_id}")

        # Status
        if run.stats.error_count > 0:
            lines.append(f"Status: ✗ {run.stats.error_count} errors")
        elif run.stats.high_severity_anomalies > 0:
            lines.append(f"Status: ⚠ {run.stats.high_severity_anomalies} high-severity anomalies")
        else:
            lines.append("Status: ✓ ok")

        # Stats
        lines.append(f"Coverage: {run.stats.coverage_percentage:.1f}%")
        lines.append(f"Records: {run.stats.record_count}")
        lines.append(f"Bytes parsed: {run.stats.total_bytes_parsed:,} / {run.stats.file_size:,}")

        # Errors and anomalies
        if run.stats.error_count > 0:
            lines.append(f"Errors: {run.stats.error_count}")
            # Show first error
            if run.parse_result.errors:
                first_error = run.parse_result.errors[0]
                lines.append(f"  First: {first_error[:60]}...")

        if run.stats.anomaly_count > 0:
            lines.append(f"Anomalies: {run.stats.anomaly_count}")
            if run.stats.high_severity_anomalies > 0:
                lines.append(f"  High severity: {run.stats.high_severity_anomalies}")
            # Show first anomaly
            if run.anomalies:
                first_anomaly = run.anomalies[0]
                lines.append(f"  {first_anomaly.severity.upper()}: {first_anomaly.message[:50]}...")

        # Score
        score_result = score_run(run)
        if score_result.passed_hard_gates:
            lines.append(f"Score: {score_result.total_score:.1f}")
        else:
            lines.append("Score: Failed hard gates")
            if score_result.hard_gate_failures:
                lines.append(f"  {score_result.hard_gate_failures[0]}")

        # Parse stopped info
        if run.stats.parse_stopped_at < run.stats.file_size:
            stopped_pct = (run.stats.parse_stopped_at / run.stats.file_size) * 100
            lines.append(f"Parse stopped: {run.stats.parse_stopped_at:,} ({stopped_pct:.1f}%)")

        content = "\n".join(lines)
        self._runs_inspector.update(content)

    # ========================================================================
    # PR#6: EVIDENCE COLUMN METHODS
    # ========================================================================

    def _clear_evidence(self) -> None:
        """Clear evidence display."""
        if self._evidence_content:
            self._evidence_content.update("Select a patch operation or run to view evidence")
        # Clear hex view highlighting
        self.post_message(HighlightBytesRequest(byte_ranges=[], jump_to_offset=None))

    def _update_evidence_for_patch_op(self, patch_op_id: str) -> None:
        """Update evidence display for selected patch operation.

        PR#6: Shows which bytes would be affected by the patch operation.
        """
        if self._evidence_content is None or self.manager is None:
            return

        version_id = self.state.selected_version_id
        if version_id is None:
            return

        version = self.manager.get_version(version_id)
        if version is None or version.patch_applied is None:
            self._evidence_content.update("No patch for this version")
            return

        # Get the patch op
        try:
            op_index = int(patch_op_id)
        except ValueError:
            self._evidence_content.update("Invalid patch op ID")
            return

        patch = version.patch_applied
        if op_index < 0 or op_index >= len(patch.ops):
            self._evidence_content.update("Patch operation not found")
            return

        op = patch.ops[op_index]

        # Build evidence display
        lines = []
        lines.append("Evidence: Patch Operation")
        lines.append("")
        lines.append(f"Operation: {op.op_type}")
        lines.append(f"Path: {path_to_string(op.path)}")
        lines.append("")
        lines.append("Note: Patch operations modify the schema, not the binary.")
        lines.append("No byte ranges to highlight.")
        lines.append("")
        lines.append("To see the effect of this patch:")
        lines.append("1. Apply the patch (create new version)")
        lines.append("2. View the new version's run results")

        content = "\n".join(lines)
        self._evidence_content.update(content)

        # Patch ops don't have byte ranges (they modify schema)
        # So we don't post any highlight request

    def _update_evidence_for_run(self, run_id: str) -> None:
        """Update evidence display for selected run.

        PR#6: Shows errors and anomalies with byte ranges, posts hex highlight request.
        """
        if self._evidence_content is None or self.manager is None:
            return

        # Get the run artifact
        run = self.manager.get_run_artifact(run_id)
        if run is None:
            self._evidence_content.update("Run not found")
            return

        # Build evidence display
        lines = []
        lines.append("Evidence: Parse Run")
        lines.append("")

        # Collect byte ranges for highlighting
        byte_ranges: list[tuple[int, int]] = []
        jump_to_offset: int | None = None

        # Show errors
        if run.stats.error_count > 0:
            lines.append(f"Errors: {run.stats.error_count}")
            for i, error in enumerate(run.parse_result.errors[:5]):  # Show first 5
                lines.append(f"  {i+1}. {error[:70]}")
                # Try to extract offset from error message
                if "at" in error and "0x" in error:
                    try:
                        offset_str = error.split("0x")[1].split(":")[0].split(" ")[0]
                        offset = int(offset_str, 16)
                        if i == 0:  # First error
                            jump_to_offset = offset
                        # Highlight a small range around error
                        byte_ranges.append((offset, min(16, run.stats.file_size - offset)))
                    except:
                        pass
            if run.stats.error_count > 5:
                lines.append(f"  ... and {run.stats.error_count - 5} more")
            lines.append("")

        # Show anomalies
        if run.stats.anomaly_count > 0:
            lines.append(f"Anomalies: {run.stats.anomaly_count}")
            for i, anomaly in enumerate(run.anomalies[:5]):  # Show first 5
                severity_badge = anomaly.severity.upper()[0]  # H/M/L
                field_str = f" ({anomaly.field_name})" if anomaly.field_name else ""
                lines.append(f"  {i+1}. [{severity_badge}] {anomaly.message[:60]}{field_str}")
                # Add anomaly location to highlights
                if jump_to_offset is None and i == 0:  # Jump to first if no error
                    jump_to_offset = anomaly.record_offset
                byte_ranges.append((anomaly.record_offset, min(16, run.stats.file_size - anomaly.record_offset)))
            if run.stats.anomaly_count > 5:
                lines.append(f"  ... and {run.stats.anomaly_count - 5} more")
            lines.append("")

        # Show coverage info
        if run.stats.coverage_percentage < 100.0:
            lines.append(f"Coverage: {run.stats.coverage_percentage:.1f}%")
            lines.append(f"Parse stopped at: 0x{run.stats.parse_stopped_at:X}")
            lines.append("")

        # Instructions
        if byte_ranges:
            lines.append(f"Highlighting {len(byte_ranges)} locations in hex view")
            if jump_to_offset is not None:
                lines.append(f"Jumped to first issue at 0x{jump_to_offset:X}")
        else:
            lines.append("No issues found - clean parse!")

        content = "\n".join(lines)
        self._evidence_content.update(content)

        # Post hex highlight request
        self.post_message(HighlightBytesRequest(
            byte_ranges=byte_ranges,
            jump_to_offset=jump_to_offset
        ))

    # ========================================================================
    # BUTTON HANDLERS (PR#3)
    # ========================================================================

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-checkout":
            self._handle_checkout()
        elif event.button.id == "btn-promote":
            self._handle_promote()
        elif event.button.id == "btn-branch":
            self._handle_branch()
        elif event.button.id == "btn-chat-send":
            self._handle_chat_send()
        elif event.button.id == "btn-suggest-patch":
            self._handle_suggest_patch()

    def _handle_checkout(self) -> None:
        """Handle Checkout button press."""
        if self.manager is None or self.state.selected_version_id is None:
            return

        # Checkout the selected version
        self.manager.checkout_version(self.state.selected_version_id)

        # Post message
        self.post_message(VersionCheckedOut(self.state.selected_version_id))

        # Refresh version list to show checkout marker
        self._populate_version_list()

        # Update inspector to show checkout status
        self._update_version_inspector(self.state.selected_version_id)

    def _handle_promote(self) -> None:
        """Handle Promote button press.

        PR#7: Promotes selected version to baseline.
        """
        if self.manager is None or self.state.selected_version_id is None:
            return

        # Promote to baseline
        self.manager.promote_to_baseline(self.state.selected_version_id)

        # Refresh version list to show new baseline badge
        self._populate_version_list()

        # Update inspector to show new role
        self._update_version_inspector(self.state.selected_version_id)

    def _handle_branch(self) -> None:
        """Handle Branch button press.

        PR#7: Creates a new version branching from selected version.
        For now, creates a simple test patch (adds a comment field).
        """
        if self.manager is None or self.state.selected_version_id is None:
            return

        # Get the selected version to branch from
        version = self.manager.get_version(self.state.selected_version_id)
        if version is None:
            return

        # Find the first type in the schema
        types_dict = version.spec_dict.get("types", {})
        if not types_dict:
            if self._version_inspector:
                self._version_inspector.update(
                    f"{self._version_inspector.renderable}\n\n"
                    "Cannot branch: Schema has no types"
                )
            return

        first_type_name = next(iter(types_dict.keys()))

        # Create a simple test patch: add a comment field
        test_patch = Patch(
            ops=(
                InsertField(
                    path=("types", first_type_name),
                    index=-1,  # Append to end
                    field_def={"name": "comment", "type": "str", "length": 64}
                ),
            ),
            description=f"Branch from {self.manager.get_version_metadata(self.state.selected_version_id).label}: Add comment field"
        )

        # Create branch version
        new_version_id = self.manager.create_branch_version(
            parent_version_id=self.state.selected_version_id,
            patch=test_patch,
            label=f"Branch from {self.manager.get_version_metadata(self.state.selected_version_id).label}"
        )

        if new_version_id:
            # Refresh version list to show new version
            self._populate_version_list()

            # Auto-select the new version
            for idx, vid in self._version_index_to_id.items():
                if vid == new_version_id:
                    if self._version_list:
                        self._version_list.highlighted = idx
                    break
        else:
            if self._version_inspector:
                self._version_inspector.update(
                    f"{self._version_inspector.renderable}\n\n"
                    "Branch failed: Patch could not be applied"
                )

    # ========================================================================
    # PR#8: CHAT HANDLERS
    # ========================================================================

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle chat input submission."""
        if event.input.id == "chat-input":
            self._handle_chat_send()

    def _handle_chat_send(self) -> None:
        """Handle Send button press or input submission."""
        if self._chat_input is None or self._chat_log is None:
            return

        user_message = self._chat_input.value.strip()
        if not user_message:
            return

        # Add user message to history
        self._chat_messages.append(("user", user_message))

        # Clear input
        self._chat_input.value = ""

        # Generate assistant response (demo mode)
        assistant_response = self._generate_demo_response(user_message)
        self._chat_messages.append(("assistant", assistant_response))

        # Update chat log display
        self._update_chat_log()

    def _handle_suggest_patch(self) -> None:
        """Handle Suggest Patch button press.

        PR#8: Generates a patch suggestion based on current version's errors.
        """
        if self.manager is None or self.state.selected_version_id is None:
            if self._chat_log:
                self._chat_messages.append((
                    "system",
                    "Please select a version first to get patch suggestions."
                ))
                self._update_chat_log()
            return

        # Add user intent to chat
        self._chat_messages.append(("user", "Suggest a patch to improve the parse results"))

        # Get current version and run data
        version_id = self.state.selected_version_id
        metadata = self.manager.get_version_metadata(version_id)
        if metadata is None or metadata.run_artifact is None:
            self._chat_messages.append((
                "assistant",
                "No run data available for this version. Cannot suggest patches."
            ))
            self._update_chat_log()
            return

        run = metadata.run_artifact

        # Build context for patch suggestion
        context = self._build_patch_context(version_id, run)

        # Generate patch suggestion (demo mode)
        suggestion = self._generate_demo_patch_suggestion(context)
        self._chat_messages.append(("assistant", suggestion))

        # Update chat log
        self._update_chat_log()

    def _update_chat_log(self) -> None:
        """Update chat log display with message history."""
        if self._chat_log is None:
            return

        lines = []
        for role, content in self._chat_messages:
            if role == "user":
                lines.append(f"You: {content}")
            elif role == "assistant":
                lines.append(f"Assistant: {content}")
            elif role == "system":
                lines.append(f"[System] {content}")
            lines.append("")  # Blank line between messages

        if not lines:
            lines = [
                "Chat: Ask the assistant to suggest spec improvements.",
                "",
                'Try: "Suggest a patch to fix the parse errors"'
            ]

        self._chat_log.update("\n".join(lines))

    def _build_patch_context(self, version_id: str, run: "RunArtifact") -> dict:
        """Build context for LLM patch suggestion.

        PR#8: Prepares current schema, errors, anomalies for LLM.
        """
        version = self.manager.get_version(version_id) if self.manager else None
        if version is None:
            return {}

        context = {
            "schema": version.spec_text,
            "file_size": run.file_size,
            "coverage_percentage": run.stats.coverage_percentage,
            "record_count": run.stats.record_count,
            "error_count": run.stats.error_count,
            "errors": run.parse_result.errors[:5],  # First 5 errors
            "anomaly_count": run.stats.anomaly_count,
            "anomalies": [
                {
                    "type": a.type,
                    "severity": a.severity,
                    "message": a.message,
                    "offset": a.record_offset
                }
                for a in run.anomalies[:5]  # First 5 anomalies
            ],
        }

        return context

    def _generate_demo_response(self, user_message: str) -> str:
        """Generate demo assistant response.

        PR#8: Placeholder for real LLM integration.
        """
        message_lower = user_message.lower()

        if "patch" in message_lower or "fix" in message_lower or "improve" in message_lower:
            return (
                "I can suggest patches to improve your schema! "
                "Click 'Suggest Patch' to get a specific recommendation based on "
                "the current version's parse results.\n\n"
                "Note: This is demo mode. Real LLM integration would analyze errors "
                "and propose targeted fixes."
            )
        elif "help" in message_lower:
            return (
                "I can help you iterate on binary format specifications!\n\n"
                "Try:\n"
                "- 'Suggest a patch to fix errors'\n"
                "- 'Why is coverage low?'\n"
                "- 'How can I improve the schema?'\n\n"
                "Click 'Suggest Patch' for automated suggestions."
            )
        else:
            return (
                f"You said: '{user_message}'\n\n"
                "This is demo mode. In production, an LLM would analyze your "
                "schema and suggest improvements.\n\n"
                "Try clicking 'Suggest Patch' for a demonstration!"
            )

    def _generate_demo_patch_suggestion(self, context: dict) -> str:
        """Generate demo patch suggestion.

        PR#8: Placeholder for real LLM patch generation.
        """
        coverage = context.get("coverage_percentage", 0)
        error_count = context.get("error_count", 0)
        anomaly_count = context.get("anomaly_count", 0)

        response = "Based on the current version:\n\n"
        response += f"- Coverage: {coverage:.1f}%\n"
        response += f"- Errors: {error_count}\n"
        response += f"- Anomalies: {anomaly_count}\n\n"

        if error_count > 0:
            errors = context.get("errors", [])
            if errors:
                response += f"First error: {errors[0][:80]}...\n\n"

        response += "Demo mode suggestion:\n"
        response += "In production, an LLM would:\n"
        response += "1. Analyze parse errors and anomalies\n"
        response += "2. Propose specific field type changes\n"
        response += "3. Suggest length adjustments\n"
        response += "4. Recommend registry additions\n\n"

        response += "For now, try using the 'Branch' button to create test versions manually.\n\n"
        response += "To integrate real LLM: See PR8_CHAT_INTERFACE.md"

        return response

    def _update_button_states(self) -> None:
        """Update button enabled/disabled states based on selection."""
        has_selection = self.state.selected_version_id is not None
        has_manager = self.manager is not None

        # Checkout button: enabled if version selected and not already checked out
        if self._checkout_button:
            is_checked_out = False
            if has_selection and has_manager:
                metadata = self.manager.get_version_metadata(self.state.selected_version_id)
                is_checked_out = metadata.is_checked_out if metadata else False

            self._checkout_button.disabled = not has_selection or is_checked_out

        # Promote and Branch: enabled if version selected
        if self._promote_button:
            self._promote_button.disabled = not has_selection

        if self._branch_button:
            self._branch_button.disabled = not has_selection
