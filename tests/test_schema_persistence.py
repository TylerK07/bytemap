"""Tests for schema save and copy functionality."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

textual = pytest.importorskip("textual")


def test_save_schema_writes_content(tmp_path: Path) -> None:
    """Test that saving schema writes correct contents to disk."""
    from hexmap.app import HexmapApp

    # Create fixture file
    data_file = tmp_path / "test.bin"
    data_file.write_bytes(bytes(range(64)))

    # Create app
    app = HexmapApp(str(data_file))

    # Set up schema with test content
    test_schema = """# Test schema
types:
  MyType:
    name: u32

fields:
  - type: MyType
"""
    app._schema = MagicMock()
    app._schema.text = test_schema

    # Save to a path
    schema_path = tmp_path / "test_schema.yaml"
    app._do_save_schema(str(schema_path))

    # Verify file was written
    assert schema_path.exists()
    assert schema_path.read_text() == test_schema

    # Verify schema_path was tracked
    assert app._schema_path == str(schema_path)


def test_save_schema_action_with_path(tmp_path: Path) -> None:
    """Test action_save_schema when schema_path is already set."""
    from hexmap.app import HexmapApp

    # Create fixture file
    data_file = tmp_path / "test.bin"
    data_file.write_bytes(bytes(range(64)))

    # Create app
    app = HexmapApp(str(data_file))

    # Set up schema
    test_schema = "# Simple schema\n"
    app._schema = MagicMock()
    app._schema.text = test_schema

    # Set schema_path
    schema_path = tmp_path / "saved.yaml"
    app._schema_path = str(schema_path)

    # Call action_save_schema
    with patch.object(app, "_do_save_schema") as mock_save:
        app.action_save_schema()
        mock_save.assert_called_once_with(str(schema_path))


def test_save_schema_action_without_path(tmp_path: Path) -> None:
    """Test action_save_schema opens Save As when no path is set."""
    from hexmap.app import HexmapApp

    # Create fixture file
    data_file = tmp_path / "test.bin"
    data_file.write_bytes(bytes(range(64)))

    # Create app
    app = HexmapApp(str(data_file))

    # Set up schema
    app._schema = MagicMock()
    app._schema.text = "# Schema\n"

    # No schema_path set
    app._schema_path = None

    # Call action_save_schema, should trigger save_as
    with patch.object(app, "action_save_schema_as") as mock_save_as:
        app.action_save_schema()
        mock_save_as.assert_called_once()


def test_copy_schema_invokes_clipboard(tmp_path: Path) -> None:
    """Test copy_schema calls clipboard method with correct content."""
    from hexmap.app import HexmapApp

    # Create fixture file
    data_file = tmp_path / "test.bin"
    data_file.write_bytes(bytes(range(64)))

    # Create app
    app = HexmapApp(str(data_file))

    # Set up schema with test content
    test_schema = """# Full schema to copy
types:
  Header:
    magic: bytes(4)
    version: u32

fields:
  - type: Header
"""
    app._schema = MagicMock()
    app._schema.text = test_schema

    # Mock clipboard method
    with patch.object(app, "_copy_to_clipboard", return_value=True) as mock_copy:
        app.action_copy_schema()
        mock_copy.assert_called_once_with(test_schema)


def test_copy_schema_handles_empty(tmp_path: Path) -> None:
    """Test copy_schema handles empty schema gracefully."""
    from hexmap.app import HexmapApp

    # Create fixture file
    data_file = tmp_path / "test.bin"
    data_file.write_bytes(bytes(range(64)))

    # Create app
    app = HexmapApp(str(data_file))

    # Set up empty schema
    app._schema = MagicMock()
    app._schema.text = "   \n  \n"

    # Mock update_status to capture hint
    app.update_status = MagicMock()

    # Copy should fail gracefully
    with patch.object(app, "_copy_to_clipboard") as mock_copy:
        app.action_copy_schema()
        # Should not call clipboard for empty schema
        mock_copy.assert_not_called()
        assert app._status_hint == "[schema is empty]"


def test_copy_to_clipboard_macos(tmp_path: Path) -> None:
    """Test clipboard copy on macOS."""
    from hexmap.app import HexmapApp

    # Create fixture file
    data_file = tmp_path / "test.bin"
    data_file.write_bytes(bytes(range(64)))

    # Create app
    app = HexmapApp(str(data_file))

    test_text = "test schema content"

    # Mock platform and subprocess
    with (
        patch("platform.system", return_value="Darwin"),
        patch("subprocess.Popen") as mock_popen,
    ):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = (b"", b"")
        mock_popen.return_value = mock_proc

        result = app._copy_to_clipboard(test_text)
        assert result is True
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert args == ["pbcopy"]
        # Verify text was passed to stdin
        mock_proc.communicate.assert_called_once()
        assert mock_proc.communicate.call_args[1]["input"] == test_text.encode("utf-8")


def test_copy_to_clipboard_linux_wlcopy(tmp_path: Path) -> None:
    """Test clipboard copy on Linux with wl-copy."""
    from hexmap.app import HexmapApp

    # Create fixture file
    data_file = tmp_path / "test.bin"
    data_file.write_bytes(bytes(range(64)))

    # Create app
    app = HexmapApp(str(data_file))

    test_text = "test schema"

    # Mock platform and subprocess
    with (
        patch("platform.system", return_value="Linux"),
        patch("subprocess.Popen") as mock_popen,
    ):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = (b"", b"")
        mock_popen.return_value = mock_proc

        result = app._copy_to_clipboard(test_text)
        assert result is True
        # Should try wl-copy first
        args = mock_popen.call_args[0][0]
        assert args == ["wl-copy"]


def test_schema_load_tracks_path(tmp_path: Path) -> None:
    """Test that loading a schema tracks its path for future saves."""
    from hexmap.app import HexmapApp

    # Create fixture file
    data_file = tmp_path / "test.bin"
    data_file.write_bytes(bytes(range(64)))

    # Create schema file
    schema_file = tmp_path / "schema.yaml"
    schema_content = "# Test\nfields:\n  - name: test\n"
    schema_file.write_text(schema_content)

    # Create app
    app = HexmapApp(str(data_file))
    app._schema = MagicMock()
    app._schema.load_text = MagicMock()

    # Mock update_status
    app.update_status = MagicMock()

    # Load schema
    app._schema_load_submit(str(schema_file))

    # Verify path was tracked
    assert app._schema_path == str(schema_file)
    app._schema.load_text.assert_called_once_with(schema_content)
