from __future__ import annotations

from pathlib import Path

import pytest

from hexmap.core.io import PagedReader
from hexmap.core.parse import apply_schema_tree
from hexmap.core.schema import SchemaError, load_schema


def test_schema_validation_missing_and_overlap(tmp_path: Path) -> None:
    # Overlap detected at parse-time via expanded leaves inside a struct
    bad = """
fields:
  - name: s
    type: struct
    fields:
      - { name: a, type: u16 }
      - { name: b, type: u16, offset: 1 }
"""
    schema = load_schema(bad)
    p = tmp_path / "z.bin"
    p.write_bytes(bytes(16))
    with PagedReader(str(p)) as r:
        tree, leaves, errs = apply_schema_tree(r, schema)
    assert any("Overlap" in e for e in errs)


def test_schema_validation_length_required() -> None:
    bad = """
fields:
  - name: data
    type: bytes
"""
    with pytest.raises(SchemaError) as ei:
        load_schema(bad)
    assert any("length required" in e for e in ei.value.errors)


def test_parse_primitives_and_bounds(tmp_path: Path) -> None:
    p = tmp_path / "bin.bin"
    # Construct simple data: magic + version + hp + name
    data = bytearray()
    data += b"MAGC"
    data += (5).to_bytes(2, "little")  # version u16
    data += (1234).to_bytes(2, "little")  # hp u16
    name = b"ALICE".ljust(16, b"\x00")
    data += name
    p.write_bytes(data)

    schema_txt = """
endian: little
fields:
  - name: header_magic
    type: bytes
    length: 4
  - name: version
    type: u16
  - name: player_hp
    type: u16
  - name: name
    type: string
    length: 16
  - name: over
    offset: 1000
    type: u8
"""
    schema = load_schema(schema_txt)
    with PagedReader(str(p)) as r:
        _, parsed, _ = apply_schema_tree(r, schema)
    by_name = {pf.name: pf for pf in parsed}
    assert by_name["header_magic"].value == b"MAGC"
    assert by_name["version"].value == 5
    assert by_name["player_hp"].value == 1234
    assert str(by_name["name"].value).startswith("ALICE")


def test_schema_endian_root_validation_little() -> None:
    """Test that root endian accepts 'little'."""
    schema_txt = """
endian: little
fields:
  - name: test
    type: u32
"""
    schema = load_schema(schema_txt)
    assert schema.endian == "little"


def test_schema_endian_root_validation_big() -> None:
    """Test that root endian accepts 'big'."""
    schema_txt = """
endian: big
fields:
  - name: test
    type: u32
"""
    schema = load_schema(schema_txt)
    assert schema.endian == "big"


def test_schema_endian_root_invalid() -> None:
    """Test that invalid root endian produces clear error."""
    schema_txt = """
endian: invalid
fields:
  - name: test
    type: u32
"""
    with pytest.raises(SchemaError) as exc:
        load_schema(schema_txt)
    assert "endian must be 'little' or 'big'" in str(exc.value)


def test_schema_endian_field_level() -> None:
    """Test field-level endian extraction."""
    schema_txt = """
endian: little
fields:
  - name: little_value
    type: u32
  - name: big_value
    type: u32
    endian: big
"""
    schema = load_schema(schema_txt)
    assert schema.fields[0].prim.endian is None  # Inherits from root
    assert schema.fields[1].prim.endian == "big"  # Override


def test_schema_endian_field_invalid() -> None:
    """Test that invalid field endian produces error with correct path."""
    schema_txt = """
endian: little
fields:
  - name: test1
    type: u32
  - name: test2
    type: u32
    endian: invalid_endian
"""
    with pytest.raises(SchemaError) as exc:
        load_schema(schema_txt)
    errors = str(exc.value)
    assert "fields[1].endian" in errors
    assert "Invalid endian 'invalid_endian'" in errors


def test_schema_endian_struct_level() -> None:
    """Test struct-level endian extraction."""
    schema_txt = """
endian: little
fields:
  - name: big_struct
    type: struct
    endian: big
    fields:
      - name: field1
        type: u16
      - name: field2
        type: u32
"""
    schema = load_schema(schema_txt)
    assert schema.fields[0].endian == "big"


def test_schema_endian_struct_field_invalid() -> None:
    """Test that invalid struct field endian produces correct error path."""
    schema_txt = """
endian: little
fields:
  - name: my_struct
    type: struct
    fields:
      - name: field1
        type: u16
      - name: bad_field
        type: u32
        endian: wrong
"""
    with pytest.raises(SchemaError) as exc:
        load_schema(schema_txt)
    errors = str(exc.value)
    assert "fields[0].fields[1].endian" in errors
    assert "Invalid endian 'wrong'" in errors


def test_schema_endian_array_level() -> None:
    """Test array-level endian extraction."""
    schema_txt = """
endian: little
fields:
  - name: big_array
    type: array
    length: 4
    endian: big
    element:
      type: u32
"""
    schema = load_schema(schema_txt)
    assert schema.fields[0].endian == "big"


def test_schema_endian_soa_level() -> None:
    """Test SOA array endian extraction."""
    schema_txt = """
endian: little
fields:
  - name: data
    type: array
    layout: soa
    length: 3
    endian: big
    fields:
      - name: x
        type: u16
      - name: y
        type: u16
"""
    schema = load_schema(schema_txt)
    assert schema.fields[0].endian == "big"


def test_schema_endian_type_definition() -> None:
    """Test endian in type definitions."""
    schema_txt = """
endian: little
types:
  BigInt:
    type: u32
    endian: big

fields:
  - name: value
    type: BigInt
"""
    schema = load_schema(schema_txt)
    # The type's endian should be present on the field after alias expansion
    assert schema.fields[0].prim.endian == "big"


def test_schema_endian_nested_struct_override() -> None:
    """Test endian overrides in nested structures."""
    schema_txt = """
endian: little
fields:
  - name: outer
    type: struct
    endian: big
    fields:
      - name: inner
        type: struct
        endian: little
        fields:
          - name: value
            type: u32
            endian: big
"""
    schema = load_schema(schema_txt)
    outer = schema.fields[0]
    assert outer.endian == "big"
    inner = outer.fields[0]
    assert inner.endian == "little"
    value = inner.fields[0]
    assert value.prim.endian == "big"


def test_schema_endian_case_insensitive() -> None:
    """Test that endian values are case-insensitive."""
    schema_txt = """
endian: Little
fields:
  - name: test1
    type: u32
    endian: BIG
  - name: test2
    type: u16
    endian: LiTtLe
"""
    schema = load_schema(schema_txt)
    assert schema.endian == "little"
    assert schema.fields[0].prim.endian == "big"
    assert schema.fields[1].prim.endian == "little"


def test_parser_endian_root_default(tmp_path: Path) -> None:
    """Test that parser uses root endian by default."""
    p = tmp_path / "data.bin"
    # Write a u32 value 0x12345678 in little-endian
    p.write_bytes((0x12345678).to_bytes(4, "little"))

    schema_txt = """
endian: little
fields:
  - name: value
    type: u32
"""
    schema = load_schema(schema_txt)
    with PagedReader(str(p)) as r:
        _, parsed, _ = apply_schema_tree(r, schema)

    assert len(parsed) == 1
    assert parsed[0].name == "value"
    assert parsed[0].value == 0x12345678
    assert parsed[0].effective_endian == "little"
    assert parsed[0].endian_source == "root"


def test_parser_endian_field_override(tmp_path: Path) -> None:
    """Test that field-level endian overrides root."""
    p = tmp_path / "data.bin"
    # Write two u32 values: 0x12345678 in little-endian, then in big-endian
    data = (0x12345678).to_bytes(4, "little") + (0x12345678).to_bytes(4, "big")
    p.write_bytes(data)

    schema_txt = """
endian: little
fields:
  - name: little_value
    type: u32
  - name: big_value
    type: u32
    endian: big
"""
    schema = load_schema(schema_txt)
    with PagedReader(str(p)) as r:
        _, parsed, _ = apply_schema_tree(r, schema)

    assert len(parsed) == 2
    # First field uses root endian (little)
    assert parsed[0].value == 0x12345678
    assert parsed[0].effective_endian == "little"
    assert parsed[0].endian_source == "root"

    # Second field uses field endian override (big)
    assert parsed[1].value == 0x12345678
    assert parsed[1].effective_endian == "big"
    assert parsed[1].endian_source == "field"


def test_parser_endian_struct_propagation(tmp_path: Path) -> None:
    """Test that struct endian propagates to children."""
    p = tmp_path / "data.bin"
    # Write two u16 values in big-endian: 0x1234, 0x5678
    data = (0x1234).to_bytes(2, "big") + (0x5678).to_bytes(2, "big")
    p.write_bytes(data)

    schema_txt = """
endian: little
fields:
  - name: big_struct
    type: struct
    endian: big
    fields:
      - name: field1
        type: u16
      - name: field2
        type: u16
"""
    schema = load_schema(schema_txt)
    with PagedReader(str(p)) as r:
        tree, parsed, _ = apply_schema_tree(r, schema)

    assert len(parsed) == 2
    # Both fields inherit parent struct's big endian
    assert parsed[0].value == 0x1234
    assert parsed[0].effective_endian == "big"
    assert parsed[0].endian_source == "parent"

    assert parsed[1].value == 0x5678
    assert parsed[1].effective_endian == "big"
    assert parsed[1].endian_source == "parent"


def test_parser_endian_nested_override(tmp_path: Path) -> None:
    """Test endian resolution with nested struct overrides."""
    p = tmp_path / "data.bin"
    # Write three u16 values:
    # - 0xABCD in big-endian (outer struct)
    # - 0x1234 in little-endian (inner struct)
    # - 0x5678 in big-endian (field override)
    data = (
        (0xABCD).to_bytes(2, "big")
        + (0x1234).to_bytes(2, "little")
        + (0x5678).to_bytes(2, "big")
    )
    p.write_bytes(data)

    schema_txt = """
endian: little
fields:
  - name: outer
    type: struct
    endian: big
    fields:
      - name: outer_field
        type: u16
      - name: inner
        type: struct
        endian: little
        fields:
          - name: inner_field
            type: u16
          - name: override_field
            type: u16
            endian: big
"""
    schema = load_schema(schema_txt)
    with PagedReader(str(p)) as r:
        _, parsed, _ = apply_schema_tree(r, schema)

    assert len(parsed) == 3
    # Outer field uses parent (outer struct big endian)
    assert parsed[0].value == 0xABCD
    assert parsed[0].effective_endian == "big"
    assert parsed[0].endian_source == "parent"

    # Inner field uses parent (inner struct little endian)
    assert parsed[1].value == 0x1234
    assert parsed[1].effective_endian == "little"
    assert parsed[1].endian_source == "parent"

    # Override field uses field-level endian
    assert parsed[2].value == 0x5678
    assert parsed[2].effective_endian == "big"
    assert parsed[2].endian_source == "field"


def test_parser_endian_array_propagation(tmp_path: Path) -> None:
    """Test that array endian propagates to elements."""
    p = tmp_path / "data.bin"
    # Write 3 u16 values in big-endian: 0x0001, 0x0002, 0x0003
    data = b"\x00\x01\x00\x02\x00\x03"
    p.write_bytes(data)

    schema_txt = """
endian: little
fields:
  - name: big_array
    type: array
    length: 3
    endian: big
    element:
      type: u16
"""
    schema = load_schema(schema_txt)
    with PagedReader(str(p)) as r:
        tree, parsed, _ = apply_schema_tree(r, schema)

    assert len(parsed) == 3
    # All elements inherit array's big endian
    for i in range(3):
        assert parsed[i].value == i + 1
        assert parsed[i].effective_endian == "big"
        assert parsed[i].endian_source == "parent"


def test_parser_endian_resolution_priority(tmp_path: Path) -> None:
    """Test endian resolution priority: field > type > parent > root."""
    p = tmp_path / "data.bin"
    # Write a u32 value 0x12345678 in big-endian
    p.write_bytes((0x12345678).to_bytes(4, "big"))

    schema_txt = """
endian: little
types:
  BigInt:
    type: u32
    endian: big

fields:
  - name: type_endian
    type: BigInt
"""
    schema = load_schema(schema_txt)
    with PagedReader(str(p)) as r:
        _, parsed, _ = apply_schema_tree(r, schema)

    assert len(parsed) == 1
    assert parsed[0].value == 0x12345678
    # Type endian is merged into field_endian during schema parsing
    assert parsed[0].effective_endian == "big"
    assert parsed[0].endian_source == "field"
