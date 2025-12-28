#!/usr/bin/env python3
"""Test color override feature."""

import tempfile
from pathlib import Path

from hexmap.core.io import PagedReader
from hexmap.core.schema import load_schema, SchemaError, normalize_color


def test_color_normalization():
    """Test color normalization function."""
    print("\n=== Test Color Normalization ===")

    # Named colors (case insensitive)
    assert normalize_color("purple") == ("purple", None)
    assert normalize_color("PURPLE") == ("purple", None)
    assert normalize_color("red") == ("red", None)
    assert normalize_color("  blue  ") == ("blue", None)

    # #RGB expansion
    assert normalize_color("#324") == ("#332244", None)
    assert normalize_color("#ABC") == ("#aabbcc", None)
    assert normalize_color("#abc") == ("#aabbcc", None)

    # #RRGGBB normalization
    assert normalize_color("#112233") == ("#112233", None)
    assert normalize_color("#AABBCC") == ("#aabbcc", None)

    # Invalid formats
    _, err = normalize_color("112233")
    assert "Invalid color" in err

    _, err = normalize_color("rgb(1,2,3)")
    assert "Invalid color" in err

    _, err = normalize_color("#12")
    assert "Invalid color" in err

    _, err = normalize_color("#12345")
    assert "Invalid color" in err

    print("✓ Color normalization works correctly")


def test_color_validation():
    """Test that schema validates colors."""
    print("\n=== Test Color Validation ===")

    # Valid colors should be accepted
    schema_yaml = """
fields:
  - name: magic
    type: u32
    color: purple
  - name: checksum
    type: u16
    color: "#ff00ff"
  - name: data
    type: bytes
    length: 10
    color: "#abc"
"""
    schema = load_schema(schema_yaml)
    print("✓ Valid colors accepted")

    # Invalid colors should be rejected
    bad_schema_yaml = """
fields:
  - name: magic
    type: u32
    color: notacolor
"""
    try:
        load_schema(bad_schema_yaml)
        assert False, "Should have rejected invalid color"
    except SchemaError as e:
        assert "Invalid color" in str(e)
        print(f"✓ Invalid color rejected: {e}")


def test_color_propagation():
    """Test that colors are propagated to parsed fields and spans."""
    print("\n=== Test Color Propagation ===")

    schema_yaml = """
fields:
  - name: magic
    type: u32
    color: purple
  - name: checksum
    type: u16
    color: "#324"
  - name: data
    type: bytes
    length: 5
    color: red
"""

    # Create test binary
    test_data = b"\x01\x02\x03\x04" + b"\x05\x06" + b"HELLO"

    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.bin') as f:
        f.write(test_data)
        test_file = f.name

    try:
        schema = load_schema(schema_yaml)

        from hexmap.core.parse import apply_schema_tree
        from hexmap.core.spans import SpanIndex, Span, type_group

        reader = PagedReader(Path(test_file))
        tree, leaves, errors = apply_schema_tree(reader, schema)

        assert not errors, f"Parse errors: {errors}"

        # Check that color_override is propagated to ParsedField objects
        magic_field = next((f for f in leaves if f.name == "magic"), None)
        checksum_field = next((f for f in leaves if f.name == "checksum"), None)
        data_field = next((f for f in leaves if f.name == "data"), None)

        assert magic_field is not None
        assert magic_field.color_override == "purple", f"Expected 'purple', got {magic_field.color_override}"

        assert checksum_field is not None
        assert checksum_field.color_override == "#332244", f"Expected '#332244', got {checksum_field.color_override}"

        assert data_field is not None
        assert data_field.color_override == "red", f"Expected 'red', got {data_field.color_override}"

        # Create spans and verify color_override is propagated
        spans = [
            Span(
                pf.offset,
                pf.length,
                pf.name,
                type_group(pf.type),
                pf.effective_endian,
                pf.endian_source,
                pf.color_override,
            )
            for pf in leaves
            if not pf.error and pf.length > 0
        ]

        span_index = SpanIndex(spans)

        # Check spans have correct colors
        magic_span = span_index.find(0)
        assert magic_span is not None
        assert magic_span.color_override == "purple"

        checksum_span = span_index.find(4)
        assert checksum_span is not None
        assert checksum_span.color_override == "#332244"

        data_span = span_index.find(6)
        assert data_span is not None
        assert data_span.color_override == "red"

        print("✓ Colors propagated to fields and spans")

    finally:
        import os
        os.unlink(test_file)


def test_color_inheritance():
    """Test that colors inherit from parent fields."""
    print("\n=== Test Color Inheritance ===")

    schema_yaml = """
fields:
  - name: header
    type: struct
    color: purple
    fields:
      - name: magic
        type: u32
      - name: version
        type: u16
  - name: payload
    type: struct
    fields:
      - name: size
        type: u16
        color: red
      - name: data
        type: u32
"""

    # Create test binary
    test_data = b"\x01\x02\x03\x04\x05\x06" + b"\x07\x08\x09\x0a\x0b\x0c"

    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.bin') as f:
        f.write(test_data)
        test_file = f.name

    try:
        schema = load_schema(schema_yaml)

        from hexmap.core.parse import apply_schema_tree

        reader = PagedReader(Path(test_file))
        tree, leaves, errors = apply_schema_tree(reader, schema)

        assert not errors, f"Parse errors: {errors}"

        # Check that color inherits from struct
        magic_field = next((f for f in leaves if f.name == "header.magic"), None)
        version_field = next((f for f in leaves if f.name == "header.version"), None)

        assert magic_field is not None
        assert magic_field.color_override == "purple", f"Magic should inherit purple, got {magic_field.color_override}"

        assert version_field is not None
        assert version_field.color_override == "purple", f"Version should inherit purple, got {version_field.color_override}"

        # Check that explicit color overrides parent
        size_field = next((f for f in leaves if f.name == "payload.size"), None)
        data_field = next((f for f in leaves if f.name == "payload.data"), None)

        assert size_field is not None
        assert size_field.color_override == "red", f"Size should have explicit red, got {size_field.color_override}"

        assert data_field is not None
        assert data_field.color_override is None, f"Data should have no color, got {data_field.color_override}"

        print("✓ Color inheritance works correctly")

    finally:
        import os
        os.unlink(test_file)


# Run all tests
if __name__ == "__main__":
    print("=" * 60)
    print("Testing Color Override Feature")
    print("=" * 60)

    test_color_normalization()
    test_color_validation()
    test_color_propagation()
    test_color_inheritance()

    print("\n" + "=" * 60)
    print("✓✓✓ ALL COLOR TESTS PASSED ✓✓✓")
    print("=" * 60)
