"""Workbench state model and selection messages.

PR#2: Reactive state for Agent Workbench tab with selection cascade.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from textual.message import Message


# ============================================================================
# SELECTION MESSAGES
# ============================================================================


class VersionSelected(Message):
    """Posted when a version is selected in Column 1."""

    def __init__(self, version_id: str | None) -> None:
        """Initialize version selection message.

        Args:
            version_id: Selected version ID, or None to clear selection
        """
        super().__init__()
        self.version_id = version_id


class VersionCheckedOut(Message):
    """Posted when a version is checked out (becomes working version)."""

    def __init__(self, version_id: str) -> None:
        """Initialize version checkout message.

        Args:
            version_id: Version ID being checked out
        """
        super().__init__()
        self.version_id = version_id


class PatchOpSelected(Message):
    """Posted when a patch operation is selected in Column 2."""

    def __init__(self, patch_op_id: str | None) -> None:
        """Initialize patch op selection message.

        Args:
            patch_op_id: Selected patch op ID, or None to clear selection
        """
        super().__init__()
        self.patch_op_id = patch_op_id


class RunSelected(Message):
    """Posted when a run is selected in Column 2."""

    def __init__(self, run_id: str | None) -> None:
        """Initialize run selection message.

        Args:
            run_id: Selected run ID, or None to clear selection
        """
        super().__init__()
        self.run_id = run_id


class EvidenceSelected(Message):
    """Posted when evidence is selected (byte range, anomaly, coverage region)."""

    def __init__(self, evidence_ref: dict[str, Any] | None) -> None:
        """Initialize evidence selection message.

        Args:
            evidence_ref: Evidence reference dict with type and range,
                         or None to clear selection
        """
        super().__init__()
        self.evidence_ref = evidence_ref


# ============================================================================
# STATE MODEL
# ============================================================================


@dataclass
class WorkbenchState:
    """Reactive state for Agent Workbench.

    This state drives the selection cascade:
    - Selecting a version updates patch ops and runs for that version
    - Checking out a version sets it as the working version
    - Selecting a patch op or run updates evidence display
    - Selecting evidence highlights bytes in hex view

    All fields are optional (None = no selection).
    """

    selected_version_id: str | None = None
    """Currently selected version in Column 1 (for inspection)."""

    checked_out_version_id: str | None = None
    """Currently checked out version (working version for edits)."""

    selected_patch_op_id: str | None = None
    """Currently selected patch operation in Column 2."""

    selected_run_id: str | None = None
    """Currently selected run in Column 2."""

    selected_evidence_ref: dict[str, Any] | None = None
    """Currently selected evidence (byte range, anomaly, etc)."""

    def clear_derived_selections(self) -> None:
        """Clear selections derived from version (called when version changes).

        When version changes, patch ops and runs are different, so clear those selections.
        """
        self.selected_patch_op_id = None
        self.selected_run_id = None
        self.selected_evidence_ref = None

    def clear_evidence_selection(self) -> None:
        """Clear evidence selection (called when patch op/run changes)."""
        self.selected_evidence_ref = None


# ============================================================================
# MOCK DATA (PR#2 only - replaced by real SpecStore in PR#3)
# ============================================================================


@dataclass
class MockVersion:
    """Mock version data for PR#2."""

    id: str
    label: str
    role: str  # "baseline" | "candidate" | "draft"
    status: str  # "ok" | "lint_error" | "parse_error"
    score: float | None
    coverage_delta: float | None  # vs baseline


@dataclass
class MockPatchOp:
    """Mock patch operation for PR#2."""

    id: str
    op_type: str
    path: str
    summary: str


@dataclass
class MockRun:
    """Mock run for PR#2."""

    id: str
    status: str  # "ok" | "error"
    coverage: float
    score: float


# In-memory mock data for PR#2
MOCK_VERSIONS = [
    MockVersion("v1", "Initial", "baseline", "ok", 45.0, None),
    MockVersion("v2", "Add header fields", "candidate", "ok", 67.0, +22.0),
    MockVersion("v3", "Fix length parsing", "candidate", "parse_error", None, -5.0),
    MockVersion("draft", "Work in progress", "draft", "ok", 55.0, +10.0),
]

MOCK_PATCH_OPS = {
    "v2": [
        MockPatchOp("op1", "InsertField", "types.Header.fields[2]", "Add flags: u16"),
        MockPatchOp("op2", "InsertField", "types.Header.fields[3]", "Add count: u8"),
    ],
    "v3": [
        MockPatchOp("op3", "UpdateField", "types.Header.fields[1]", "Change type u8 → u16"),
    ],
    "draft": [
        MockPatchOp("op4", "InsertField", "types.Header.fields[2]", "Add timestamp: u32"),
    ],
}

MOCK_RUNS = {
    "v1": [MockRun("r1", "ok", 45.0, 45.0)],
    "v2": [MockRun("r2", "ok", 67.0, 67.0)],
    "v3": [MockRun("r3", "error", 40.0, 0.0)],
    "draft": [MockRun("r4", "ok", 55.0, 55.0)],
}
