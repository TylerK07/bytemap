"""Spec versioning and patch application system.

This module manages versions of YAML grammar specifications, applies patches,
and tracks the evolution of specs through the iteration process.
"""

from __future__ import annotations

import time
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

import yaml

from hexmap.core.spec_patch import (
    AddRegistryEntry,
    AddType,
    DeleteField,
    InsertField,
    Patch,
    PatchOp,
    PatchResult,
    UpdateField,
    UpdateType,
    path_to_string,
)
from hexmap.core.tool_host import LintGrammarInput, ToolHost


# ============================================================================
# SPEC VERSION
# ============================================================================

@dataclass(frozen=True)
class SpecVersion:
    """Immutable snapshot of a spec at a point in time.

    Attributes:
        id: Unique identifier for this version
        parent_id: ID of parent version (None for initial)
        created_at: Unix timestamp when created
        spec_text: YAML text of spec
        spec_dict: Parsed spec as dict
        patch_applied: Patch that created this version (None for initial)
        lint_valid: Whether spec passes lint (None = not checked)
        lint_errors: Lint errors (empty if valid)
        lint_warnings: Lint warnings
    """
    id: str
    parent_id: str | None
    created_at: float
    spec_text: str
    spec_dict: dict[str, Any]
    patch_applied: Patch | None = None
    lint_valid: bool | None = None
    lint_errors: tuple[str, ...] = ()
    lint_warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict (excluding large fields)."""
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "created_at": self.created_at,
            "patch_description": self.patch_applied.description if self.patch_applied else None,
            "lint_valid": self.lint_valid,
            "lint_errors": list(self.lint_errors),
            "lint_warnings": list(self.lint_warnings),
        }


# ============================================================================
# SPEC STORE
# ============================================================================

class SpecStore:
    """In-memory store for spec versions and patch application.

    This manages the version graph and provides atomic patch application.
    """

    def __init__(self):
        """Initialize empty spec store."""
        self._versions: dict[str, SpecVersion] = {}

        # Working draft state (shared across tabs)
        self._working_draft_text: str = ""
        self._working_draft_validation: Any = None  # LintGrammarOutput cache

    # ========================================================================
    # WORKING DRAFT API (Shared YAML Buffer)
    # ========================================================================

    def get_working_text(self) -> str:
        """Get current working draft YAML text.

        Returns:
            YAML text of working draft (may be empty string)
        """
        return self._working_draft_text

    def set_working_text(self, text: str) -> None:
        """Update working draft YAML text.

        This invalidates the validation cache. All tabs should call this
        when YAML is edited to keep the buffer synchronized.

        Args:
            text: New YAML text
        """
        self._working_draft_text = text
        self._working_draft_validation = None  # Invalidate cache

    def validate_working_draft(self) -> Any:
        """Validate working draft using ToolHost (cached).

        Returns:
            LintGrammarOutput with success status, errors, warnings, and grammar
        """
        if self._working_draft_validation is None:
            self._working_draft_validation = ToolHost.lint_grammar(
                LintGrammarInput(yaml_text=self._working_draft_text)
            )
        return self._working_draft_validation

    def has_working_draft(self) -> bool:
        """Check if working draft has any content.

        Returns:
            True if working draft is non-empty
        """
        return bool(self._working_draft_text.strip())

    def commit_working_draft(self, label: str = "Working Draft") -> str:
        """Commit working draft as new immutable version.

        Args:
            label: Human-readable label for this version (not used in current impl)

        Returns:
            Version ID of newly created version

        Raises:
            ValueError: If working draft is empty or invalid YAML
        """
        if not self.has_working_draft():
            raise ValueError("Cannot commit empty working draft")

        # Use create_initial to validate and create version
        version = self.create_initial(self._working_draft_text, run_lint=True)
        return version.id

    # ========================================================================
    # VERSION MANAGEMENT API
    # ========================================================================

    def create_initial(self, spec_text: str, run_lint: bool = True) -> SpecVersion:
        """Create initial spec version from YAML text.

        Args:
            spec_text: YAML grammar text
            run_lint: Whether to run lint validation

        Returns:
            New SpecVersion

        Raises:
            ValueError: If YAML is invalid
        """
        # Parse YAML
        try:
            spec_dict = yaml.safe_load(spec_text)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML: {e}")

        # Generate ID
        version_id = str(uuid.uuid4())[:8]

        # Run lint if requested
        lint_valid = None
        lint_errors = ()
        lint_warnings = ()

        if run_lint:
            lint_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=spec_text))
            lint_valid = lint_result.success
            lint_errors = lint_result.errors
            lint_warnings = lint_result.warnings

        # Create version
        version = SpecVersion(
            id=version_id,
            parent_id=None,
            created_at=time.time(),
            spec_text=spec_text,
            spec_dict=spec_dict,
            patch_applied=None,
            lint_valid=lint_valid,
            lint_errors=lint_errors,
            lint_warnings=lint_warnings,
        )

        self._versions[version_id] = version
        return version

    def get(self, version_id: str) -> SpecVersion | None:
        """Get spec version by ID.

        Args:
            version_id: Version ID to retrieve

        Returns:
            SpecVersion or None if not found
        """
        return self._versions.get(version_id)

    def apply_patch(
        self,
        parent_version_id: str,
        patch: Patch,
        run_lint: bool = True
    ) -> PatchResult:
        """Apply patch to create new spec version.

        This is atomic: either all ops succeed or none are applied.

        Args:
            parent_version_id: ID of parent version to patch
            patch: Patch to apply
            run_lint: Whether to run lint on result

        Returns:
            PatchResult with success status and new version ID (if successful)
        """
        # Get parent version
        parent = self.get(parent_version_id)
        if parent is None:
            return PatchResult(
                success=False,
                errors=(f"Parent version {parent_version_id} not found",)
            )

        # Validate patch
        is_valid, errors = patch.validate()
        if not is_valid:
            return PatchResult(
                success=False,
                errors=tuple(errors)
            )

        # Apply ops to a copy of spec dict
        new_spec_dict = deepcopy(parent.spec_dict)

        try:
            for i, op in enumerate(patch.ops):
                self._apply_op(new_spec_dict, op)
        except Exception as e:
            return PatchResult(
                success=False,
                errors=(f"Failed to apply op {i}: {e}",),
                rejected_ops=(i,)
            )

        # Convert back to YAML text
        try:
            new_spec_text = yaml.dump(new_spec_dict, default_flow_style=False, sort_keys=False)
        except Exception as e:
            return PatchResult(
                success=False,
                errors=(f"Failed to serialize YAML: {e}",)
            )

        # Run lint if requested
        lint_valid = None
        lint_errors = ()
        lint_warnings = ()

        if run_lint:
            lint_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=new_spec_text))
            lint_valid = lint_result.success
            lint_errors = lint_result.errors
            lint_warnings = lint_result.warnings

            # Reject if lint fails
            if not lint_valid:
                return PatchResult(
                    success=False,
                    errors=tuple([f"Lint failed: {err}" for err in lint_errors])
                )

        # Create new version
        version_id = str(uuid.uuid4())[:8]
        new_version = SpecVersion(
            id=version_id,
            parent_id=parent_version_id,
            created_at=time.time(),
            spec_text=new_spec_text,
            spec_dict=new_spec_dict,
            patch_applied=patch,
            lint_valid=lint_valid,
            lint_errors=lint_errors,
            lint_warnings=lint_warnings,
        )

        self._versions[version_id] = new_version

        return PatchResult(
            success=True,
            new_spec_id=version_id
        )

    def _apply_op(self, spec_dict: dict, op: PatchOp) -> None:
        """Apply a single patch operation to spec dict.

        Modifies spec_dict in place.

        Args:
            spec_dict: Spec dictionary to modify
            op: Operation to apply

        Raises:
            KeyError: If path doesn't exist
            ValueError: If operation is invalid
        """
        if isinstance(op, InsertField):
            # Navigate to parent type
            type_name = op.path[1]
            if "types" not in spec_dict:
                spec_dict["types"] = {}
            if type_name not in spec_dict["types"]:
                raise KeyError(f"Type {type_name} not found")

            type_def = spec_dict["types"][type_name]
            if "fields" not in type_def:
                type_def["fields"] = []

            # Insert field
            fields = type_def["fields"]
            index = op.index if op.index >= 0 else len(fields)
            fields.insert(index, op.field_def)

        elif isinstance(op, UpdateField):
            # Navigate to field
            type_name = op.path[1]
            field_index = op.path[3]

            type_def = spec_dict["types"][type_name]
            fields = type_def["fields"]

            if field_index >= len(fields):
                raise IndexError(f"Field index {field_index} out of range")

            # Update field properties
            field = fields[field_index]
            for key, value in op.updates.items():
                field[key] = value

        elif isinstance(op, DeleteField):
            # Navigate to field
            type_name = op.path[1]
            field_index = op.path[3]

            type_def = spec_dict["types"][type_name]
            fields = type_def["fields"]

            if field_index >= len(fields):
                raise IndexError(f"Field index {field_index} out of range")

            # Delete field
            del fields[field_index]

        elif isinstance(op, AddType):
            # Add new type
            type_name = op.path[1]
            if "types" not in spec_dict:
                spec_dict["types"] = {}

            if type_name in spec_dict["types"]:
                raise ValueError(f"Type {type_name} already exists")

            spec_dict["types"][type_name] = op.type_def

        elif isinstance(op, UpdateType):
            # Update type properties
            type_name = op.path[1]
            if type_name not in spec_dict.get("types", {}):
                raise KeyError(f"Type {type_name} not found")

            type_def = spec_dict["types"][type_name]
            for key, value in op.updates.items():
                type_def[key] = value

        elif isinstance(op, AddRegistryEntry):
            # Add registry entry
            discriminator = op.path[1]
            if "registry" not in spec_dict:
                spec_dict["registry"] = {}

            if discriminator in spec_dict["registry"]:
                raise ValueError(f"Registry entry {discriminator} already exists")

            spec_dict["registry"][discriminator] = op.entry

        else:
            raise ValueError(f"Unknown operation type: {type(op)}")

    def diff_specs(self, version_a_id: str, version_b_id: str) -> SpecDiff:
        """Compute structured diff between two spec versions.

        Args:
            version_a_id: First version ID
            version_b_id: Second version ID

        Returns:
            SpecDiff describing changes from A to B
        """
        version_a = self.get(version_a_id)
        version_b = self.get(version_b_id)

        if version_a is None:
            raise ValueError(f"Version {version_a_id} not found")
        if version_b is None:
            raise ValueError(f"Version {version_b_id} not found")

        changes = []

        # Compare types
        types_a = version_a.spec_dict.get("types", {})
        types_b = version_b.spec_dict.get("types", {})

        # Added types
        for type_name in types_b.keys() - types_a.keys():
            changes.append(f"Added type: {type_name}")

        # Removed types
        for type_name in types_a.keys() - types_b.keys():
            changes.append(f"Removed type: {type_name}")

        # Changed types
        for type_name in types_a.keys() & types_b.keys():
            type_a = types_a[type_name]
            type_b = types_b[type_name]

            # Compare field counts
            fields_a = type_a.get("fields", [])
            fields_b = type_b.get("fields", [])

            if len(fields_a) != len(fields_b):
                changes.append(
                    f"Type {type_name}: field count {len(fields_a)} → {len(fields_b)}"
                )

        # Compare registry
        registry_a = version_a.spec_dict.get("registry", {})
        registry_b = version_b.spec_dict.get("registry", {})

        for disc in registry_b.keys() - registry_a.keys():
            changes.append(f"Added registry entry: {disc}")

        for disc in registry_a.keys() - registry_b.keys():
            changes.append(f"Removed registry entry: {disc}")

        return SpecDiff(
            version_a_id=version_a_id,
            version_b_id=version_b_id,
            changes=tuple(changes),
        )

    def get_lineage(self, version_id: str) -> list[str]:
        """Get lineage of version IDs from root to specified version.

        Args:
            version_id: Version to trace lineage for

        Returns:
            List of version IDs from root to specified version
        """
        lineage = []
        current_id = version_id

        while current_id is not None:
            lineage.append(current_id)
            version = self.get(current_id)
            if version is None:
                break
            current_id = version.parent_id

        return list(reversed(lineage))


# ============================================================================
# SPEC DIFF
# ============================================================================

@dataclass(frozen=True)
class SpecDiff:
    """Structured diff between two spec versions.

    Attributes:
        version_a_id: First version ID
        version_b_id: Second version ID
        changes: List of human-readable change descriptions
    """
    version_a_id: str
    version_b_id: str
    changes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "version_a_id": self.version_a_id,
            "version_b_id": self.version_b_id,
            "changes": list(self.changes),
            "change_count": len(self.changes),
        }
