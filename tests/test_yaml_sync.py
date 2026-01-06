"""Test YAML synchronization across tabs (PR#1)."""

import pytest
from hexmap.core.spec_version import SpecStore


def test_spec_store_working_draft():
    """Test SpecStore working draft API."""
    store = SpecStore()

    # Initially empty
    assert store.get_working_text() == ""
    assert not store.has_working_draft()

    # Set working text
    yaml_text = "format:\n  endian: little\ntypes:\n  Header:\n    type: struct"
    store.set_working_text(yaml_text)

    # Verify it was stored
    assert store.get_working_text() == yaml_text
    assert store.has_working_draft()

    # Update working text
    new_yaml = "format:\n  endian: big\ntypes:\n  Header:\n    type: struct"
    store.set_working_text(new_yaml)

    # Verify update
    assert store.get_working_text() == new_yaml


def test_spec_store_validation_cache():
    """Test that validation is cached."""
    store = SpecStore()

    # Set valid YAML (using correct ToolHost format)
    yaml_text = """format: record_stream
endian: little
framing:
  repeat: until_eof
record:
  use: Header
types:
  Header:
    fields:
      - { name: magic, type: u32 }
"""
    store.set_working_text(yaml_text)

    # First validation
    result1 = store.validate_working_draft()
    assert result1.success

    # Second validation should use cache
    result2 = store.validate_working_draft()
    assert result2 is result1  # Same object reference = cached

    # Update text should invalidate cache
    store.set_working_text(yaml_text + "\n# comment")
    result3 = store.validate_working_draft()
    assert result3 is not result1  # Different object = cache was invalidated


def test_spec_store_commit_working_draft():
    """Test committing working draft to version."""
    store = SpecStore()

    # Set valid YAML (using correct ToolHost format)
    yaml_text = """format: record_stream
endian: little
framing:
  repeat: until_eof
record:
  use: Header
types:
  Header:
    fields:
      - { name: magic, type: u32 }
"""
    store.set_working_text(yaml_text)

    # Commit to version
    version_id = store.commit_working_draft("Test Version")

    # Verify version was created
    version = store.get(version_id)
    assert version is not None
    assert version.spec_text == yaml_text
    assert version.lint_valid is True


def test_spec_store_cannot_commit_empty():
    """Test that empty working draft cannot be committed."""
    store = SpecStore()

    with pytest.raises(ValueError, match="Cannot commit empty"):
        store.commit_working_draft()


def test_spec_store_synchronization_simulation():
    """Simulate tab synchronization behavior."""
    store = SpecStore()

    # Explore tab sets YAML (using correct ToolHost format)
    explore_yaml = """format: record_stream
endian: little
framing:
  repeat: until_eof
record:
  use: Record
types:
  Record:
    fields:
      - { name: id, type: u16 }
"""
    store.set_working_text(explore_yaml)

    # Chunking tab reads YAML (should see Explore's YAML)
    chunking_yaml = store.get_working_text()
    assert chunking_yaml == explore_yaml

    # Chunking tab modifies YAML (change endian and field type)
    modified_yaml = """format: record_stream
endian: big
framing:
  repeat: until_eof
record:
  use: Record
types:
  Record:
    fields:
      - { name: id, type: u32 }
"""
    store.set_working_text(modified_yaml)

    # Explore tab reads YAML (should see Chunking's changes)
    updated_explore_yaml = store.get_working_text()
    assert updated_explore_yaml == modified_yaml

    # Workbench tab reads YAML (should see latest)
    workbench_yaml = store.get_working_text()
    assert workbench_yaml == modified_yaml


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
