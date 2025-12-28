#!/usr/bin/env python3
"""Test dynamic length references in type definitions."""

import tempfile
from pathlib import Path

from hexmap.core.io import PagedReader
from hexmap.core.schema import load_schema

# Test 1: Simple TLV pattern
schema_yaml = """
types:
  tlv_record:
    type: struct
    fields:
      - name: field_size
        type: u16
      - name: field_payload
        type: bytes
        length_from: field_size

fields:
  - name: my_record
    type: tlv_record
"""

# Create test binary: u16(5) followed by 5 bytes "HELLO"
test_data = b"\x05\x00HELLO"

with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.bin') as f:
    f.write(test_data)
    test_file = f.name

try:
    # Parse schema
    try:
        schema = load_schema(schema_yaml)
        print("✓ Schema parsed successfully")
    except Exception as e:
        print(f"Schema errors: {e}")
        exit(1)

    # Apply schema
    from hexmap.core.parse import apply_schema_tree

    reader = PagedReader(Path(test_file))
    tree, leaves, parse_errors = apply_schema_tree(reader, schema)

    if parse_errors:
        print(f"Parse errors: {parse_errors}")
        exit(1)

    print("✓ Schema applied successfully")

    # Verify results
    print(f"\nParsed {len(leaves)} fields:")
    for leaf in leaves:
        print(f"  {leaf.name:30} @ {leaf.offset:4} len={leaf.length:3} value={leaf.value!r}")

    # Check specific values
    size_field = next((f for f in leaves if f.name == "my_record.field_size"), None)
    payload_field = next((f for f in leaves if f.name == "my_record.field_payload"), None)

    assert size_field is not None, "field_size not found"
    assert payload_field is not None, "field_payload not found"
    assert size_field.value == 5, f"Expected size=5, got {size_field.value}"
    assert payload_field.value == b"HELLO", f"Expected payload=b'HELLO', got {payload_field.value}"
    assert payload_field.length == 5, f"Expected payload length=5, got {payload_field.length}"

    print("\n✓ All assertions passed!")
    print("✓ Dynamic length references in type definitions work correctly!")

finally:
    import os
    os.unlink(test_file)
