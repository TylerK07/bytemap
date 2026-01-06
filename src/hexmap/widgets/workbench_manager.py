"""Workbench manager for SpecStore and run artifact management.

PR#3: Manages real SpecStore integration, run artifacts, and version metadata.
PR#7: Added promote and branch operations.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hexmap.core.run_artifacts import RunArtifact, create_run_artifact
from hexmap.core.run_scoring import score_run
from hexmap.core.spec_patch import Patch
from hexmap.core.spec_version import SpecStore, SpecVersion
from hexmap.core.tool_host import LintGrammarInput, ParseBinaryInput, ToolHost


@dataclass
class VersionMetadata:
    """Metadata for a version in the workbench.

    Augments SpecVersion with UI-specific data like role and run artifacts.
    """

    version: SpecVersion
    role: str  # "baseline" | "candidate" | "draft" | "checked_out"
    label: str  # Display label
    run_artifact: RunArtifact | None = None  # Latest run for this version
    is_checked_out: bool = False  # Whether this is the working version


class WorkbenchManager:
    """Manages SpecStore, run artifacts, and version metadata.

    This is the data layer for the workbench UI.
    PR#3: Initial implementation with basic version management.
    """

    def __init__(self, binary_file_path: str) -> None:
        """Initialize workbench manager.

        Args:
            binary_file_path: Path to binary file being analyzed
        """
        self.binary_file_path = binary_file_path
        self.binary_file_size = Path(binary_file_path).stat().st_size

        # Phase 7 components
        self.spec_store = SpecStore()

        # Version metadata (version_id → VersionMetadata)
        self._version_metadata: dict[str, VersionMetadata] = {}

        # Run artifacts (run_id → RunArtifact)
        self._run_artifacts: dict[str, RunArtifact] = {}

        # Checked out version (working version)
        self._checked_out_version_id: str | None = None

        # Baseline version (for comparison)
        self._baseline_version_id: str | None = None

    # ========================================================================
    # VERSION MANAGEMENT
    # ========================================================================

    def create_initial_version(self, spec_text: str, label: str = "Initial") -> str:
        """Create initial spec version and mark as baseline.

        Args:
            spec_text: YAML grammar text
            label: Display label for version

        Returns:
            Version ID

        Raises:
            ValueError: If YAML is invalid or lint fails
        """
        # Create version via SpecStore
        version = self.spec_store.create_initial(spec_text, run_lint=True)

        if not version.lint_valid:
            raise ValueError(f"Spec failed lint: {version.lint_errors[0]}")

        # Create metadata
        metadata = VersionMetadata(
            version=version,
            role="baseline",
            label=label,
            run_artifact=None,
            is_checked_out=True,
        )
        self._version_metadata[version.id] = metadata

        # Set as baseline and checked out
        self._baseline_version_id = version.id
        self._checked_out_version_id = version.id

        # Auto-run parse for initial version
        self._run_parse_for_version(version.id)

        return version.id

    def get_version(self, version_id: str) -> SpecVersion | None:
        """Get version by ID.

        Args:
            version_id: Version ID

        Returns:
            SpecVersion or None if not found
        """
        return self.spec_store.get(version_id)

    def get_version_metadata(self, version_id: str) -> VersionMetadata | None:
        """Get version metadata by ID.

        Args:
            version_id: Version ID

        Returns:
            VersionMetadata or None if not found
        """
        return self._version_metadata.get(version_id)

    def get_all_versions(self) -> list[VersionMetadata]:
        """Get all versions sorted by creation time.

        Returns:
            List of VersionMetadata, newest first
        """
        versions = list(self._version_metadata.values())
        versions.sort(key=lambda m: m.version.created_at, reverse=True)
        return versions

    def checkout_version(self, version_id: str) -> None:
        """Checkout a version (make it the working version).

        Args:
            version_id: Version ID to checkout
        """
        # Clear previous checkout
        if self._checked_out_version_id:
            old_metadata = self._version_metadata.get(self._checked_out_version_id)
            if old_metadata:
                old_metadata.is_checked_out = False
                # Revert role if it was "checked_out"
                if old_metadata.role == "checked_out":
                    old_metadata.role = "candidate"

        # Set new checkout
        self._checked_out_version_id = version_id
        metadata = self._version_metadata.get(version_id)
        if metadata:
            metadata.is_checked_out = True
            if metadata.role not in ("baseline", "draft"):
                metadata.role = "checked_out"

    def get_checked_out_version_id(self) -> str | None:
        """Get currently checked out version ID.

        Returns:
            Version ID or None if no version checked out
        """
        return self._checked_out_version_id

    def get_baseline_version_id(self) -> str | None:
        """Get baseline version ID.

        Returns:
            Version ID or None if no baseline set
        """
        return self._baseline_version_id

    def promote_to_baseline(self, version_id: str) -> None:
        """Promote a version to baseline.

        The baseline is the reference version for coverage comparisons.

        Args:
            version_id: Version ID to promote to baseline
        """
        # Clear previous baseline role
        if self._baseline_version_id:
            old_baseline = self._version_metadata.get(self._baseline_version_id)
            if old_baseline and old_baseline.role == "baseline":
                old_baseline.role = "candidate"

        # Set new baseline
        self._baseline_version_id = version_id
        metadata = self._version_metadata.get(version_id)
        if metadata:
            # Preserve checked_out role if it has it
            if not metadata.is_checked_out:
                metadata.role = "baseline"

    def create_branch_version(
        self,
        parent_version_id: str,
        patch: "Patch",
        label: str = "Branch"
    ) -> str | None:
        """Create a new version by applying a patch to a parent version.

        Args:
            parent_version_id: ID of parent version
            patch: Patch to apply
            label: Display label for new version

        Returns:
            New version ID or None if patch failed
        """
        # Apply patch via SpecStore
        result = self.spec_store.apply_patch(
            parent_version_id=parent_version_id,
            patch=patch,
            run_lint=True
        )

        if not result.success or result.new_spec_id is None:
            return None

        new_version_id = result.new_spec_id

        # Get the new version
        new_version = self.spec_store.get(new_version_id)
        if new_version is None:
            return None

        # Create metadata
        metadata = VersionMetadata(
            version=new_version,
            role="candidate",
            label=label,
            run_artifact=None,
            is_checked_out=False,
        )
        self._version_metadata[new_version_id] = metadata

        # Auto-run parse for new version
        self._run_parse_for_version(new_version_id)

        return new_version_id

    # ========================================================================
    # RUN MANAGEMENT
    # ========================================================================

    def run_parse_for_version(self, version_id: str) -> RunArtifact | None:
        """Trigger a parse run for a version.

        Args:
            version_id: Version ID to run parse for

        Returns:
            RunArtifact or None if parse failed
        """
        return self._run_parse_for_version(version_id)

    def _run_parse_for_version(self, version_id: str) -> RunArtifact | None:
        """Internal: Run parse for version and store artifact.

        Args:
            version_id: Version ID to run parse for

        Returns:
            RunArtifact or None if parse failed
        """
        version = self.spec_store.get(version_id)
        if version is None:
            return None

        # Lint to get Grammar object
        lint_result = ToolHost.lint_grammar(
            LintGrammarInput(yaml_text=version.spec_text)
        )

        if not lint_result.success or lint_result.grammar is None:
            # Parse failed at lint stage - create error artifact
            return None

        # Parse binary
        try:
            parse_result = ToolHost.parse_binary(
                ParseBinaryInput(
                    grammar=lint_result.grammar,
                    file_path=self.binary_file_path,
                    max_records=1000,  # Safety limit
                )
            )
        except Exception:
            return None

        # Create run artifact
        run_id = f"run_{version_id}_{uuid.uuid4().hex[:8]}"
        run_artifact = create_run_artifact(
            run_id=run_id,
            spec_version_id=version_id,
            parse_result=parse_result,
            file_path=self.binary_file_path,
            file_size=self.binary_file_size,
        )

        # Store run artifact
        self._run_artifacts[run_id] = run_artifact

        # Update version metadata with latest run
        metadata = self._version_metadata.get(version_id)
        if metadata:
            metadata.run_artifact = run_artifact

        return run_artifact

    def get_run_artifact(self, run_id: str) -> RunArtifact | None:
        """Get run artifact by ID.

        Args:
            run_id: Run ID

        Returns:
            RunArtifact or None if not found
        """
        return self._run_artifacts.get(run_id)

    def get_runs_for_version(self, version_id: str) -> list[RunArtifact]:
        """Get all run artifacts for a version.

        Args:
            version_id: Version ID

        Returns:
            List of RunArtifacts for this version
        """
        return [
            run
            for run in self._run_artifacts.values()
            if run.spec_version_id == version_id
        ]

    # ========================================================================
    # SCORING & COMPARISON
    # ========================================================================

    def get_score_for_version(self, version_id: str) -> float | None:
        """Get latest score for a version.

        Args:
            version_id: Version ID

        Returns:
            Score (0-100) or None if no run or score failed
        """
        metadata = self._version_metadata.get(version_id)
        if metadata is None or metadata.run_artifact is None:
            return None

        score = score_run(metadata.run_artifact)
        if not score.passed_hard_gates:
            return None

        return score.total_score

    def get_coverage_delta_vs_baseline(self, version_id: str) -> float | None:
        """Get coverage delta vs baseline for a version.

        Args:
            version_id: Version ID

        Returns:
            Coverage delta percentage or None if no baseline or run
        """
        if self._baseline_version_id is None:
            return None

        if version_id == self._baseline_version_id:
            return None  # Baseline has no delta

        metadata = self._version_metadata.get(version_id)
        baseline_metadata = self._version_metadata.get(self._baseline_version_id)

        if (
            metadata is None
            or metadata.run_artifact is None
            or baseline_metadata is None
            or baseline_metadata.run_artifact is None
        ):
            return None

        # Compute delta
        version_coverage = metadata.run_artifact.stats.coverage_percentage
        baseline_coverage = baseline_metadata.run_artifact.stats.coverage_percentage

        return version_coverage - baseline_coverage

    # ========================================================================
    # CONVENIENCE GETTERS
    # ========================================================================

    def get_version_display_info(self, version_id: str) -> dict[str, Any]:
        """Get display info for a version (for UI rendering).

        Args:
            version_id: Version ID

        Returns:
            Dict with display info
        """
        metadata = self._version_metadata.get(version_id)
        if metadata is None:
            return {"error": "Version not found"}

        version = metadata.version
        run = metadata.run_artifact

        # Determine status
        if not version.lint_valid:
            status = "lint_error"
        elif run is None:
            status = "no_run"
        elif run.stats.error_count > 0 or run.stats.high_severity_anomalies > 0:
            status = "parse_error"
        else:
            status = "ok"

        # Get score
        score = self.get_score_for_version(version_id)

        # Get coverage delta
        coverage_delta = self.get_coverage_delta_vs_baseline(version_id)

        return {
            "version_id": version_id,
            "label": metadata.label,
            "role": metadata.role,
            "status": status,
            "score": score,
            "coverage_delta": coverage_delta,
            "is_checked_out": metadata.is_checked_out,
            "lint_valid": version.lint_valid,
            "lint_errors": version.lint_errors,
            "lint_warnings": version.lint_warnings,
            "created_at": version.created_at,
        }
