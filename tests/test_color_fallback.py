#!/usr/bin/env python3
"""Test color fallback mechanism."""

import tempfile
from pathlib import Path

from hexmap.core.io import PagedReader
from hexmap.core.schema import load_schema
from hexmap.core.parse import apply_schema_tree
from hexmap.core.spans import SpanIndex, Span, type_group
from hexmap.widgets.hex_view import HexView


def test_gray_color_mapping():
    """Test that 'gray' maps to 'grey' and works correctly."""
    print("\n=== Test Gray Color Mapping ===")

    schema_yaml = """
fields:
  - name: field1
    type: u32
    color: gray
  - name: field2
    type: u32
    color: grey
"""

    # Create test binary
    test_data = b"\x01\x02\x03\x04\x05\x06\x07\x08"

    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.bin') as f:
        f.write(test_data)
        test_file = f.name

    try:
        schema = load_schema(schema_yaml)

        reader = PagedReader(Path(test_file))
        tree, leaves, errors = apply_schema_tree(reader, schema)

        assert not errors, f"Parse errors: {errors}"

        # Create spans
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

        # Create HexView and test color retrieval
        hex_view = HexView(reader)
        hex_view._span_index = span_index

        # Test that gray is mapped correctly
        color1 = hex_view._byte_fg(0)  # field1 with "gray"
        color2 = hex_view._byte_fg(4)  # field2 with "grey"

        print(f"  Color for 'gray': {color1}")
        print(f"  Color for 'grey': {color2}")

        # Both should map successfully and not crash
        assert color1 is not None, "Color should not be None"
        assert color2 is not None, "Color should not be None"

        # Both should resolve to the same color (gray -> grey mapping)
        assert color1 == color2, f"Gray and grey should map to same color, got {color1} vs {color2}"

        # The important thing is that it didn't crash and returned a valid color
        print("✓ Gray/grey color mapping works correctly (no crash)")

    finally:
        import os
        os.unlink(test_file)


def test_invalid_color_fallback():
    """Test that invalid colors fall back to type-based colors."""
    print("\n=== Test Invalid Color Fallback ===")

    # Create a simple test file
    test_data = b"\x01\x02\x03\x04"
    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.bin') as f:
        f.write(test_data)
        test_file = f.name

    try:
        reader = PagedReader(Path(test_file))

        # Directly test _byte_fg with an invalid color in span_index
        from hexmap.core.spans import Span

        # Create a span with an invalid color (one that Rich won't recognize)
        # Note: This would have been caught by schema validation, but let's test the fallback anyway
        spans = [
            Span(
                offset=0,
                length=4,
                path="test_field",
                group="int",
                effective_endian="little",
                endian_source="default",
                color_override="totally_invalid_color_12345",
            )
        ]

        span_index = SpanIndex(spans)
        hex_view = HexView(reader)
        hex_view._span_index = span_index

        # This should fall back to type-based color (int) instead of crashing
        color = hex_view._byte_fg(0)

        print(f"  Fallback color for invalid: {color}")

        # Should fall back to the default int color from PALETTE
        from hexmap.ui.palette import PALETTE
        assert color == PALETTE.hex_type_int_fg, f"Should fall back to int color, got {color}"

        print("✓ Invalid color falls back to type-based color")

    finally:
        import os
        os.unlink(test_file)


# Run tests
if __name__ == "__main__":
    print("=" * 60)
    print("Testing Color Fallback Mechanism")
    print("=" * 60)

    test_gray_color_mapping()
    test_invalid_color_fallback()

    print("\n" + "=" * 60)
    print("✓✓✓ ALL FALLBACK TESTS PASSED ✓✓✓")
    print("=" * 60)
