#!/usr/bin/env python3
"""Comprehensive tests for dynamic length references in type definitions."""

import tempfile
from pathlib import Path

from hexmap.core.io import PagedReader
from hexmap.core.schema import load_schema, SchemaError

# Test 1: Simple TLV pattern
def test_simple_tlv():
    print("\n=== Test 1: Simple TLV pattern ===")
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
        schema = load_schema(schema_yaml)
        print("✓ Schema parsed successfully")

        from hexmap.core.parse import apply_schema_tree
        reader = PagedReader(Path(test_file))
        tree, leaves, parse_errors = apply_schema_tree(reader, schema)

        if parse_errors:
            print(f"✗ Parse errors: {parse_errors}")
            return False

        size_field = next((f for f in leaves if f.name == "my_record.field_size"), None)
        payload_field = next((f for f in leaves if f.name == "my_record.field_payload"), None)

        assert size_field is not None and size_field.value == 5
        assert payload_field is not None and payload_field.value == b"HELLO"
        assert payload_field.length == 5

        print("✓ Test passed!")
        return True
    finally:
        import os
        os.unlink(test_file)


# Test 2: Array of TLV records with explicit stride
def test_array_of_tlv():
    print("\n=== Test 2: Array of TLV records ===")
    schema_yaml = """
types:
  tlv_record:
    type: struct
    fields:
      - name: size
        type: u8
      - name: data
        type: bytes
        length_from: size

fields:
  - name: count
    type: u16
  - name: records
    type: array
    length_from: count
    stride: 5
    element:
      type: tlv_record
"""
    # Create test binary: u16(2) for count, then two TLV records
    # Record 1: u8(4) + "ABCD" (5 bytes total)
    # Record 2: u8(4) + "WXYZ" (5 bytes total)
    test_data = b"\x02\x00" + b"\x04ABCD" + b"\x04WXYZ"

    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.bin') as f:
        f.write(test_data)
        test_file = f.name

    try:
        schema = load_schema(schema_yaml)
        print("✓ Schema parsed successfully")

        from hexmap.core.parse import apply_schema_tree
        reader = PagedReader(Path(test_file))
        tree, leaves, parse_errors = apply_schema_tree(reader, schema)

        if parse_errors:
            print(f"✗ Parse errors: {parse_errors}")
            return False

        # Check count field
        count_field = next((f for f in leaves if f.name == "count"), None)
        assert count_field is not None and count_field.value == 2

        # Check first record
        rec0_size = next((f for f in leaves if f.name == "records[0].size"), None)
        rec0_data = next((f for f in leaves if f.name == "records[0].data"), None)
        assert rec0_size is not None and rec0_size.value == 4
        assert rec0_data is not None and rec0_data.value == b"ABCD"

        # Check second record
        rec1_size = next((f for f in leaves if f.name == "records[1].size"), None)
        rec1_data = next((f for f in leaves if f.name == "records[1].data"), None)
        assert rec1_size is not None and rec1_size.value == 4
        assert rec1_data is not None and rec1_data.value == b"WXYZ"

        print("✓ Test passed!")
        return True
    finally:
        import os
        os.unlink(test_file)


# Test 3: Forward reference should be rejected
def test_forward_reference_rejected():
    print("\n=== Test 3: Forward reference should be rejected ===")
    schema_yaml = """
types:
  bad_record:
    type: struct
    fields:
      - name: data
        type: bytes
        length_from: size
      - name: size
        type: u16

fields:
  - name: my_record
    type: bad_record
"""
    try:
        schema = load_schema(schema_yaml)
        print("✗ Schema should have been rejected!")
        return False
    except SchemaError as e:
        if "length_ref 'size' references unknown or later field" in str(e):
            print(f"✓ Correctly rejected with error: {e}")
            return True
        else:
            print(f"✗ Wrong error: {e}")
            return False


# Test 4: Dynamic string length
def test_dynamic_string_length():
    print("\n=== Test 4: Dynamic string length ===")
    schema_yaml = """
types:
  string_record:
    type: struct
    fields:
      - name: str_len
        type: u8
      - name: text
        type: string
        length_from: str_len

fields:
  - name: my_string
    type: string_record
"""
    # Create test binary: u8(5) + "HELLO"
    test_data = b"\x05HELLO"

    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.bin') as f:
        f.write(test_data)
        test_file = f.name

    try:
        schema = load_schema(schema_yaml)
        print("✓ Schema parsed successfully")

        from hexmap.core.parse import apply_schema_tree
        reader = PagedReader(Path(test_file))
        tree, leaves, parse_errors = apply_schema_tree(reader, schema)

        if parse_errors:
            print(f"✗ Parse errors: {parse_errors}")
            return False

        str_len = next((f for f in leaves if f.name == "my_string.str_len"), None)
        text = next((f for f in leaves if f.name == "my_string.text"), None)

        assert str_len is not None and str_len.value == 5
        assert text is not None and text.value == "HELLO"

        print("✓ Test passed!")
        return True
    finally:
        import os
        os.unlink(test_file)


# Test 5: Nested structs with dynamic lengths
def test_nested_structs():
    print("\n=== Test 5: Nested structs with dynamic lengths ===")
    schema_yaml = """
types:
  inner:
    type: struct
    fields:
      - name: len
        type: u8
      - name: payload
        type: bytes
        length_from: len

  outer:
    type: struct
    fields:
      - name: magic
        type: u16
      - name: inner_data
        type: inner

fields:
  - name: record
    type: outer
"""
    # Create test binary: u16(0xABCD) + u8(3) + "XYZ"
    test_data = b"\xCD\xAB\x03XYZ"

    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.bin') as f:
        f.write(test_data)
        test_file = f.name

    try:
        schema = load_schema(schema_yaml)
        print("✓ Schema parsed successfully")

        from hexmap.core.parse import apply_schema_tree
        reader = PagedReader(Path(test_file))
        tree, leaves, parse_errors = apply_schema_tree(reader, schema)

        if parse_errors:
            print(f"✗ Parse errors: {parse_errors}")
            return False

        magic = next((f for f in leaves if f.name == "record.magic"), None)
        inner_len = next((f for f in leaves if f.name == "record.inner_data.len"), None)
        payload = next((f for f in leaves if f.name == "record.inner_data.payload"), None)

        assert magic is not None and magic.value == 0xABCD
        assert inner_len is not None and inner_len.value == 3
        assert payload is not None and payload.value == b"XYZ"

        print("✓ Test passed!")
        return True
    finally:
        import os
        os.unlink(test_file)


# Run all tests
if __name__ == "__main__":
    print("=" * 60)
    print("Testing dynamic length references in type definitions")
    print("=" * 60)

    results = []
    results.append(("Simple TLV pattern", test_simple_tlv()))
    results.append(("Array of TLV records", test_array_of_tlv()))
    results.append(("Forward reference rejection", test_forward_reference_rejected()))
    results.append(("Dynamic string length", test_dynamic_string_length()))
    results.append(("Nested structs", test_nested_structs()))

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")

    all_passed = all(passed for _, passed in results)
    print("\n" + ("=" * 60))
    if all_passed:
        print("✓✓✓ ALL TESTS PASSED ✓✓✓")
        exit(0)
    else:
        print("✗✗✗ SOME TESTS FAILED ✗✗✗")
        exit(1)
