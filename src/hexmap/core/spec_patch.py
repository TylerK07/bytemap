"""Structured patch operations for YAML grammar specifications.

This module provides a deterministic, type-safe way to express changes to
binary grammar specifications without direct YAML manipulation.

Key Concepts:
- Path: Immutable tuple addressing into spec structure
- PatchOp: Atomic, validated operation on the spec
- Patch: Collection of ops applied atomically
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ============================================================================
# PATH MODEL
# ============================================================================

def validate_path(path: tuple[str | int, ...]) -> bool:
    """Validate that a path is well-formed.

    Valid paths:
    - ("types", "Header")
    - ("types", "Header", "fields", 0)
    - ("types", "Header", "fields", 0, "name")
    - ("registry", "0x4E54")
    - ("endian",)

    Args:
        path: Path tuple to validate

    Returns:
        True if valid, False otherwise
    """
    if not path:
        return False

    # Must start with valid root
    valid_roots = {"types", "registry", "endian", "record", "framing", "format"}
    if path[0] not in valid_roots:
        return False

    # Check alternating string/int pattern for nested access
    for i, component in enumerate(path):
        if i % 2 == 0:  # Even indices should be strings (keys)
            if not isinstance(component, str):
                return False
        else:  # Odd indices can be strings (dict keys) or ints (list indices)
            if not isinstance(component, (str, int)):
                return False

    return True


def path_to_string(path: tuple[str | int, ...]) -> str:
    """Convert path tuple to human-readable string.

    Examples:
        ("types", "Header") → "types.Header"
        ("types", "Header", "fields", 0) → "types.Header.fields[0]"
        ("registry", "0x4E54") → "registry['0x4E54']"

    Args:
        path: Path tuple

    Returns:
        Human-readable path string
    """
    if not path:
        return ""

    parts = []
    for i, component in enumerate(path):
        if i == 0:
            parts.append(str(component))
        elif isinstance(component, int):
            parts.append(f"[{component}]")
        elif isinstance(component, str):
            # Use bracket notation for special chars
            if any(c in component for c in [".", "[", "]", " "]):
                parts.append(f"['{component}']")
            else:
                parts.append(f".{component}")

    return "".join(parts)


# ============================================================================
# PATCH OPERATIONS
# ============================================================================

@dataclass(frozen=True)
class PatchOp:
    """Base class for all patch operations.

    Attributes:
        op_type: Type of operation (insert_field, update_field, etc.)
        path: Immutable path into spec structure
    """
    op_type: str
    path: tuple[str | int, ...]

    def validate(self) -> tuple[bool, str | None]:
        """Validate this operation.

        Returns:
            (is_valid, error_message)
        """
        # Validate path
        if not validate_path(self.path):
            return False, f"Invalid path: {path_to_string(self.path)}"

        return True, None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "op_type": self.op_type,
            "path": list(self.path),
        }


@dataclass(frozen=True)
class InsertField(PatchOp):
    """Insert a field at specific index in a type's field list.

    Attributes:
        path: Path to parent type (e.g., ("types", "Header"))
        index: Index to insert at (0 = beginning, -1 = end)
        field_def: Field definition dict with {name, type, ...}

    Example:
        InsertField(
            path=("types", "Header"),
            index=0,
            field_def={"name": "magic", "type": "u16"}
        )
    """
    op_type: str = field(default="insert_field", init=False)
    index: int = 0
    field_def: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> tuple[bool, str | None]:
        """Validate insert field operation."""
        is_valid, error = super().validate()
        if not is_valid:
            return is_valid, error

        # Path must point to a type
        if len(self.path) != 2 or self.path[0] != "types":
            return False, f"Path must be ('types', 'TypeName'), got {path_to_string(self.path)}"

        # Must have field definition
        if not self.field_def:
            return False, "field_def is empty"

        # Must have name and type
        if "name" not in self.field_def:
            return False, "field_def missing 'name'"
        if "type" not in self.field_def:
            return False, "field_def missing 'type'"

        return True, None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "op_type": self.op_type,
            "path": list(self.path),
            "index": self.index,
            "field_def": self.field_def,
        }


@dataclass(frozen=True)
class UpdateField(PatchOp):
    """Update properties of an existing field.

    Attributes:
        path: Path to field (e.g., ("types", "Header", "fields", 0))
        updates: Dict of properties to update

    Example:
        UpdateField(
            path=("types", "Header", "fields", 0),
            updates={"type": "u32", "color": "red"}
        )
    """
    op_type: str = field(default="update_field", init=False)
    updates: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> tuple[bool, str | None]:
        """Validate update field operation."""
        is_valid, error = super().validate()
        if not is_valid:
            return is_valid, error

        # Path must point to a field
        if len(self.path) < 4:
            return False, f"Path too short for field: {path_to_string(self.path)}"
        if self.path[0] != "types" or self.path[2] != "fields":
            return False, f"Path must be ('types', name, 'fields', index), got {path_to_string(self.path)}"
        if not isinstance(self.path[3], int):
            return False, f"Field index must be int, got {type(self.path[3])}"

        # Must have updates
        if not self.updates:
            return False, "updates is empty"

        return True, None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "op_type": self.op_type,
            "path": list(self.path),
            "updates": self.updates,
        }


@dataclass(frozen=True)
class DeleteField(PatchOp):
    """Remove a field from a type.

    Attributes:
        path: Path to field (e.g., ("types", "Header", "fields", 0))

    Example:
        DeleteField(path=("types", "Header", "fields", 0))
    """
    op_type: str = field(default="delete_field", init=False)

    def validate(self) -> tuple[bool, str | None]:
        """Validate delete field operation."""
        is_valid, error = super().validate()
        if not is_valid:
            return is_valid, error

        # Path must point to a field
        if len(self.path) < 4:
            return False, f"Path too short for field: {path_to_string(self.path)}"
        if self.path[0] != "types" or self.path[2] != "fields":
            return False, f"Path must be ('types', name, 'fields', index), got {path_to_string(self.path)}"
        if not isinstance(self.path[3], int):
            return False, f"Field index must be int, got {type(self.path[3])}"

        return True, None


@dataclass(frozen=True)
class AddType(PatchOp):
    """Add a new type definition.

    Attributes:
        path: Path to new type (e.g., ("types", "NewType"))
        type_def: Type definition dict with {fields: [...]}

    Example:
        AddType(
            path=("types", "NewType"),
            type_def={"fields": [{"name": "id", "type": "u16"}]}
        )
    """
    op_type: str = field(default="add_type", init=False)
    type_def: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> tuple[bool, str | None]:
        """Validate add type operation."""
        is_valid, error = super().validate()
        if not is_valid:
            return is_valid, error

        # Path must be ("types", type_name)
        if len(self.path) != 2 or self.path[0] != "types":
            return False, f"Path must be ('types', 'TypeName'), got {path_to_string(self.path)}"

        # Must have type definition with fields
        if not self.type_def:
            return False, "type_def is empty"
        if "fields" not in self.type_def:
            return False, "type_def missing 'fields'"
        if not isinstance(self.type_def["fields"], list):
            return False, "type_def['fields'] must be a list"

        return True, None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "op_type": self.op_type,
            "path": list(self.path),
            "type_def": self.type_def,
        }


@dataclass(frozen=True)
class UpdateType(PatchOp):
    """Update properties of an existing type (non-field properties).

    Attributes:
        path: Path to type (e.g., ("types", "Header"))
        updates: Dict of properties to update

    Example:
        UpdateType(
            path=("types", "Header"),
            updates={"description": "Updated header"}
        )
    """
    op_type: str = field(default="update_type", init=False)
    updates: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> tuple[bool, str | None]:
        """Validate update type operation."""
        is_valid, error = super().validate()
        if not is_valid:
            return is_valid, error

        # Path must point to a type
        if len(self.path) != 2 or self.path[0] != "types":
            return False, f"Path must be ('types', 'TypeName'), got {path_to_string(self.path)}"

        # Must have updates
        if not self.updates:
            return False, "updates is empty"

        return True, None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "op_type": self.op_type,
            "path": list(self.path),
            "updates": self.updates,
        }


@dataclass(frozen=True)
class AddRegistryEntry(PatchOp):
    """Add a registry entry for type discriminator.

    Attributes:
        path: Path to registry entry (e.g., ("registry", "0x4E54"))
        entry: Registry entry dict with {name, decode: {...}}

    Example:
        AddRegistryEntry(
            path=("registry", "0x4E54"),
            entry={"name": "NameRecord", "decode": {"as": "string"}}
        )
    """
    op_type: str = field(default="add_registry_entry", init=False)
    entry: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> tuple[bool, str | None]:
        """Validate add registry entry operation."""
        is_valid, error = super().validate()
        if not is_valid:
            return is_valid, error

        # Path must be ("registry", discriminator)
        if len(self.path) != 2 or self.path[0] != "registry":
            return False, f"Path must be ('registry', 'discriminator'), got {path_to_string(self.path)}"

        # Must have entry with name
        if not self.entry:
            return False, "entry is empty"
        if "name" not in self.entry:
            return False, "entry missing 'name'"

        return True, None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "op_type": self.op_type,
            "path": list(self.path),
            "entry": self.entry,
        }


# ============================================================================
# PATCH COLLECTION
# ============================================================================

@dataclass(frozen=True)
class Patch:
    """Collection of patch operations applied atomically.

    Attributes:
        ops: Tuple of patch operations
        description: Human-readable description of what this patch does
    """
    ops: tuple[PatchOp, ...]
    description: str = ""

    def validate(self) -> tuple[bool, list[str]]:
        """Validate all operations in this patch.

        Returns:
            (all_valid, list_of_errors)
        """
        errors = []

        if not self.ops:
            errors.append("Patch has no operations")
            return False, errors

        for i, op in enumerate(self.ops):
            is_valid, error = op.validate()
            if not is_valid:
                errors.append(f"Op {i} ({op.op_type}): {error}")

        return len(errors) == 0, errors

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "description": self.description,
            "ops": [op.to_dict() for op in self.ops],
        }


# ============================================================================
# PATCH RESULT
# ============================================================================

@dataclass(frozen=True)
class PatchResult:
    """Result of attempting to apply a patch.

    Attributes:
        success: Whether patch was applied successfully
        new_spec_id: ID of new spec version (if successful)
        errors: List of error messages (if failed)
        rejected_ops: List of rejected operation indices
    """
    success: bool
    new_spec_id: str | None = None
    errors: tuple[str, ...] = ()
    rejected_ops: tuple[int, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "success": self.success,
            "new_spec_id": self.new_spec_id,
            "errors": list(self.errors),
            "rejected_ops": list(self.rejected_ops),
        }
