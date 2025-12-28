"""Schema library for discovering and managing built-in and user schemas."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class SchemaMetadata:
    """Metadata extracted from schema YAML."""

    name: str
    description: str = ""
    tags: list[str] = None  # type: ignore[assignment]
    file_patterns: list[str] = None  # type: ignore[assignment]
    endian: str | None = None

    def __post_init__(self) -> None:
        if self.tags is None:
            self.tags = []
        if self.file_patterns is None:
            self.file_patterns = []


@dataclass
class SchemaEntry:
    """A schema entry with metadata and source info."""

    path: Path
    metadata: SchemaMetadata
    is_builtin: bool

    @property
    def name(self) -> str:
        return self.metadata.name

    def load_content(self) -> str:
        """Load full YAML content."""
        return self.path.read_text(encoding="utf-8")


def get_user_schemas_dir() -> Path:
    """Get platform-appropriate user schemas directory."""
    if os.name == "nt":  # Windows
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        return Path(base) / "bytemap" / "schemas"
    else:  # macOS, Linux
        return Path.home() / ".config" / "bytemap" / "schemas"


def get_builtin_schemas_dir() -> Path:
    """Get built-in schemas directory."""
    # Relative to this module
    return Path(__file__).parent.parent / "schemas" / "builtin"


def parse_schema_metadata(path: Path) -> SchemaMetadata:
    """Parse metadata from schema YAML file."""
    try:
        content = path.read_text(encoding="utf-8")
        data = yaml.safe_load(content) or {}

        # Extract meta section if present
        meta = data.get("meta", {})

        # Infer name from filename if not in meta
        name = meta.get("name", path.stem.replace("_", " ").title())

        return SchemaMetadata(
            name=name,
            description=meta.get("description", ""),
            tags=meta.get("tags", []),
            file_patterns=meta.get("file_patterns", []),
            endian=meta.get("endian"),
        )
    except Exception:
        # Fallback if parsing fails
        return SchemaMetadata(name=path.stem.replace("_", " ").title())


def discover_schemas() -> tuple[list[SchemaEntry], list[SchemaEntry]]:
    """Discover all available schemas.

    Returns:
        Tuple of (builtin_schemas, user_schemas)
    """
    builtin_schemas: list[SchemaEntry] = []
    user_schemas: list[SchemaEntry] = []

    # Discover built-in schemas
    builtin_dir = get_builtin_schemas_dir()
    if builtin_dir.exists():
        for yaml_file in sorted(builtin_dir.glob("*.yaml")):
            try:
                metadata = parse_schema_metadata(yaml_file)
                builtin_schemas.append(
                    SchemaEntry(path=yaml_file, metadata=metadata, is_builtin=True)
                )
            except Exception:
                continue

    # Discover user schemas
    user_dir = get_user_schemas_dir()
    if user_dir.exists():
        for yaml_file in sorted(user_dir.glob("*.yaml")):
            try:
                metadata = parse_schema_metadata(yaml_file)
                user_schemas.append(
                    SchemaEntry(path=yaml_file, metadata=metadata, is_builtin=False)
                )
            except Exception:
                continue

    return builtin_schemas, user_schemas


def duplicate_to_user(schema_entry: SchemaEntry) -> SchemaEntry | None:
    """Duplicate a built-in schema to user directory.

    Args:
        schema_entry: Schema to duplicate

    Returns:
        New SchemaEntry in user directory, or None if failed
    """
    if not schema_entry.is_builtin:
        return None  # Can only duplicate built-in schemas

    user_dir = get_user_schemas_dir()
    user_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique filename if needed
    dest_path = user_dir / schema_entry.path.name
    counter = 1
    while dest_path.exists():
        stem = schema_entry.path.stem
        dest_path = user_dir / f"{stem}_{counter}.yaml"
        counter += 1

    try:
        shutil.copy2(schema_entry.path, dest_path)
        metadata = parse_schema_metadata(dest_path)
        return SchemaEntry(path=dest_path, metadata=metadata, is_builtin=False)
    except Exception:
        return None


def create_new_schema(name: str, template: str = "") -> SchemaEntry | None:
    """Create a new schema in user directory.

    Args:
        name: Name for the new schema
        template: Optional template content

    Returns:
        New SchemaEntry, or None if failed
    """
    user_dir = get_user_schemas_dir()
    user_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize filename
    safe_name = "".join(c if c.isalnum() or c in (" ", "_", "-") else "_" for c in name)
    safe_name = safe_name.strip().replace(" ", "_").lower()
    if not safe_name:
        safe_name = "new_schema"

    # Generate unique filename
    dest_path = user_dir / f"{safe_name}.yaml"
    counter = 1
    while dest_path.exists():
        dest_path = user_dir / f"{safe_name}_{counter}.yaml"
        counter += 1

    try:
        # Use template or create blank schema
        if not template:
            template = f"""meta:
  name: {name}
  description: ""
  tags: []
  file_patterns: []

# Define custom types here
types:

# Define field structure here
fields:
"""
        dest_path.write_text(template, encoding="utf-8")
        metadata = parse_schema_metadata(dest_path)
        return SchemaEntry(path=dest_path, metadata=metadata, is_builtin=False)
    except Exception:
        return None


def delete_user_schema(schema_entry: SchemaEntry) -> bool:
    """Delete a user schema.

    Args:
        schema_entry: Schema to delete (must be user schema)

    Returns:
        True if deleted successfully
    """
    if schema_entry.is_builtin:
        return False  # Cannot delete built-in schemas

    try:
        schema_entry.path.unlink()
        return True
    except Exception:
        return False


def search_schemas(
    schemas: list[SchemaEntry], query: str
) -> list[SchemaEntry]:
    """Filter schemas by search query.

    Args:
        schemas: List of schemas to search
        query: Search query (matches name, description, tags)

    Returns:
        Filtered list of matching schemas
    """
    if not query.strip():
        return schemas

    query_lower = query.lower()
    results = []

    for schema in schemas:
        # Search in name
        if query_lower in schema.metadata.name.lower():
            results.append(schema)
            continue

        # Search in description
        if query_lower in schema.metadata.description.lower():
            results.append(schema)
            continue

        # Search in tags
        if any(query_lower in tag.lower() for tag in schema.metadata.tags):
            results.append(schema)
            continue

    return results
