"""Tests for schema library functionality."""

from __future__ import annotations

from pathlib import Path

import yaml


def test_discover_schemas_finds_builtin(tmp_path: Path) -> None:
    """Test that discover_schemas finds built-in schemas."""
    from hexmap.core.schema_library import discover_schemas, get_builtin_schemas_dir

    # Built-in schemas should exist in the package
    builtin_dir = get_builtin_schemas_dir()
    assert builtin_dir.exists(), "Built-in schemas directory should exist"

    builtin_schemas, _ = discover_schemas()

    # Should find at least the example schemas we created
    assert len(builtin_schemas) > 0, "Should find built-in schemas"
    assert all(s.is_builtin for s in builtin_schemas), "All should be marked as built-in"


def test_discover_schemas_finds_user(tmp_path: Path, monkeypatch) -> None:
    """Test that discover_schemas finds user schemas."""
    from hexmap.core.schema_library import discover_schemas

    # Mock user schemas directory to tmp_path
    user_dir = tmp_path / "schemas"
    user_dir.mkdir(parents=True)

    # Create a test user schema
    test_schema = user_dir / "my_schema.yaml"
    test_schema.write_text(
        """meta:
  name: My Test Schema
  description: A test schema
  tags: [test, example]

fields:
  - name: test_field
    type: u32
"""
    )

    # Monkey patch the get_user_schemas_dir function
    monkeypatch.setattr(
        "hexmap.core.schema_library.get_user_schemas_dir", lambda: user_dir
    )

    builtin_schemas, user_schemas = discover_schemas()

    assert len(user_schemas) == 1, "Should find one user schema"
    assert user_schemas[0].metadata.name == "My Test Schema"
    assert not user_schemas[0].is_builtin


def test_parse_schema_metadata_with_meta(tmp_path: Path) -> None:
    """Test parsing schema metadata from meta section."""
    from hexmap.core.schema_library import parse_schema_metadata

    schema_file = tmp_path / "test.yaml"
    schema_file.write_text(
        """meta:
  name: Test Schema
  description: This is a test
  tags: [tag1, tag2]
  file_patterns: ["*.bin", "*.dat"]
  endian: little

fields:
  - name: field1
"""
    )

    metadata = parse_schema_metadata(schema_file)

    assert metadata.name == "Test Schema"
    assert metadata.description == "This is a test"
    assert metadata.tags == ["tag1", "tag2"]
    assert metadata.file_patterns == ["*.bin", "*.dat"]
    assert metadata.endian == "little"


def test_parse_schema_metadata_without_meta(tmp_path: Path) -> None:
    """Test parsing schema when meta section is missing."""
    from hexmap.core.schema_library import parse_schema_metadata

    schema_file = tmp_path / "my_custom_schema.yaml"
    schema_file.write_text(
        """# No meta section
fields:
  - name: field1
    type: u32
"""
    )

    metadata = parse_schema_metadata(schema_file)

    # Should infer name from filename
    assert metadata.name == "My Custom Schema"
    assert metadata.description == ""
    assert metadata.tags == []
    assert metadata.file_patterns == []


def test_duplicate_to_user(tmp_path: Path, monkeypatch) -> None:
    """Test duplicating a built-in schema to user directory."""
    from hexmap.core.schema_library import SchemaEntry, SchemaMetadata, duplicate_to_user

    # Mock user directory
    user_dir = tmp_path / "user_schemas"
    user_dir.mkdir(parents=True)

    monkeypatch.setattr(
        "hexmap.core.schema_library.get_user_schemas_dir", lambda: user_dir
    )

    # Create a fake built-in schema
    builtin_file = tmp_path / "builtin.yaml"
    builtin_content = """meta:
  name: Builtin Schema

fields:
  - name: test
"""
    builtin_file.write_text(builtin_content)

    builtin_entry = SchemaEntry(
        path=builtin_file,
        metadata=SchemaMetadata(name="Builtin Schema"),
        is_builtin=True,
    )

    # Duplicate it
    result = duplicate_to_user(builtin_entry)

    assert result is not None
    assert not result.is_builtin
    assert result.path.parent == user_dir
    assert result.path.exists()
    assert result.path.read_text() == builtin_content


def test_duplicate_non_builtin_returns_none(tmp_path: Path) -> None:
    """Test that duplicating a non-builtin schema returns None."""
    from hexmap.core.schema_library import SchemaEntry, SchemaMetadata, duplicate_to_user

    user_file = tmp_path / "user.yaml"
    user_file.write_text("# User schema\n")

    user_entry = SchemaEntry(
        path=user_file,
        metadata=SchemaMetadata(name="User Schema"),
        is_builtin=False,
    )

    result = duplicate_to_user(user_entry)
    assert result is None


def test_create_new_schema(tmp_path: Path, monkeypatch) -> None:
    """Test creating a new schema in user directory."""
    from hexmap.core.schema_library import create_new_schema

    # Mock user directory
    user_dir = tmp_path / "user_schemas"
    user_dir.mkdir(parents=True)

    monkeypatch.setattr(
        "hexmap.core.schema_library.get_user_schemas_dir", lambda: user_dir
    )

    # Create new schema
    result = create_new_schema("My New Schema")

    assert result is not None
    assert not result.is_builtin
    assert result.path.exists()
    assert "My New Schema" in result.path.read_text()

    # Verify it's valid YAML
    content = yaml.safe_load(result.path.read_text())
    assert "meta" in content
    assert content["meta"]["name"] == "My New Schema"


def test_create_new_schema_with_template(tmp_path: Path, monkeypatch) -> None:
    """Test creating a new schema with custom template."""
    from hexmap.core.schema_library import create_new_schema

    user_dir = tmp_path / "user_schemas"
    user_dir.mkdir(parents=True)

    monkeypatch.setattr(
        "hexmap.core.schema_library.get_user_schemas_dir", lambda: user_dir
    )

    template = """# Custom template
fields:
  - name: custom_field
    type: u16
"""

    result = create_new_schema("Custom", template=template)

    assert result is not None
    assert result.path.read_text() == template


def test_delete_user_schema(tmp_path: Path) -> None:
    """Test deleting a user schema."""
    from hexmap.core.schema_library import SchemaEntry, SchemaMetadata, delete_user_schema

    user_file = tmp_path / "delete_me.yaml"
    user_file.write_text("# Schema to delete\n")

    user_entry = SchemaEntry(
        path=user_file,
        metadata=SchemaMetadata(name="Delete Me"),
        is_builtin=False,
    )

    assert user_file.exists()
    result = delete_user_schema(user_entry)
    assert result is True
    assert not user_file.exists()


def test_delete_builtin_schema_returns_false(tmp_path: Path) -> None:
    """Test that deleting a built-in schema returns False."""
    from hexmap.core.schema_library import SchemaEntry, SchemaMetadata, delete_user_schema

    builtin_file = tmp_path / "builtin.yaml"
    builtin_file.write_text("# Builtin schema\n")

    builtin_entry = SchemaEntry(
        path=builtin_file,
        metadata=SchemaMetadata(name="Builtin"),
        is_builtin=True,
    )

    result = delete_user_schema(builtin_entry)
    assert result is False
    assert builtin_file.exists()


def test_search_schemas_by_name(tmp_path: Path) -> None:
    """Test searching schemas by name."""
    from hexmap.core.schema_library import SchemaEntry, SchemaMetadata, search_schemas

    schemas = [
        SchemaEntry(
            path=tmp_path / "bmp.yaml",
            metadata=SchemaMetadata(name="BMP Header"),
            is_builtin=True,
        ),
        SchemaEntry(
            path=tmp_path / "zip.yaml",
            metadata=SchemaMetadata(name="ZIP Archive"),
            is_builtin=True,
        ),
        SchemaEntry(
            path=tmp_path / "test.yaml",
            metadata=SchemaMetadata(name="Test Schema"),
            is_builtin=False,
        ),
    ]

    results = search_schemas(schemas, "bmp")
    assert len(results) == 1
    assert results[0].name == "BMP Header"

    results = search_schemas(schemas, "archive")
    assert len(results) == 1
    assert results[0].name == "ZIP Archive"


def test_search_schemas_by_description(tmp_path: Path) -> None:
    """Test searching schemas by description."""
    from hexmap.core.schema_library import SchemaEntry, SchemaMetadata, search_schemas

    schemas = [
        SchemaEntry(
            path=tmp_path / "bmp.yaml",
            metadata=SchemaMetadata(
                name="BMP", description="Windows Bitmap file format"
            ),
            is_builtin=True,
        ),
        SchemaEntry(
            path=tmp_path / "zip.yaml",
            metadata=SchemaMetadata(
                name="ZIP", description="Compressed archive format"
            ),
            is_builtin=True,
        ),
    ]

    results = search_schemas(schemas, "compressed")
    assert len(results) == 1
    assert results[0].name == "ZIP"


def test_search_schemas_by_tag(tmp_path: Path) -> None:
    """Test searching schemas by tag."""
    from hexmap.core.schema_library import SchemaEntry, SchemaMetadata, search_schemas

    schemas = [
        SchemaEntry(
            path=tmp_path / "bmp.yaml",
            metadata=SchemaMetadata(name="BMP", tags=["image", "graphics"]),
            is_builtin=True,
        ),
        SchemaEntry(
            path=tmp_path / "zip.yaml",
            metadata=SchemaMetadata(name="ZIP", tags=["archive", "compression"]),
            is_builtin=True,
        ),
    ]

    results = search_schemas(schemas, "image")
    assert len(results) == 1
    assert results[0].name == "BMP"

    results = search_schemas(schemas, "compression")
    assert len(results) == 1
    assert results[0].name == "ZIP"


def test_search_schemas_empty_query_returns_all(tmp_path: Path) -> None:
    """Test that empty search query returns all schemas."""
    from hexmap.core.schema_library import SchemaEntry, SchemaMetadata, search_schemas

    schemas = [
        SchemaEntry(
            path=tmp_path / "a.yaml",
            metadata=SchemaMetadata(name="A"),
            is_builtin=True,
        ),
        SchemaEntry(
            path=tmp_path / "b.yaml",
            metadata=SchemaMetadata(name="B"),
            is_builtin=False,
        ),
    ]

    results = search_schemas(schemas, "")
    assert len(results) == 2

    results = search_schemas(schemas, "   ")
    assert len(results) == 2
