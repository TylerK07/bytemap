"""Integration tests for endian support across schema, parser, and UI layers."""

from __future__ import annotations

from pathlib import Path

from hexmap.core.io import PagedReader
from hexmap.core.parse import apply_schema_tree
from hexmap.core.schema import load_schema
from hexmap.core.spans import Span, SpanIndex, type_group


def test_endian_integration_mixed_file(tmp_path: Path) -> None:
    """Test full endian flow: schema → parse → spans with mixed endianness."""
    # Create a binary file with mixed-endian data
    p = tmp_path / "mixed.bin"
    data = bytearray()
    # Header: 2 bytes big-endian u16 = 0x1234
    data += (0x1234).to_bytes(2, "big")
    # Body: 4 bytes little-endian u32 = 0x12345678
    data += (0x12345678).to_bytes(4, "little")
    # Footer: 2 bytes big-endian u16 = 0xABCD
    data += (0xABCD).to_bytes(2, "big")
    p.write_bytes(data)

    schema_txt = """
endian: little
fields:
  - name: header
    type: struct
    endian: big
    fields:
      - name: magic
        type: u16
  - name: body
    type: u32
  - name: footer
    type: struct
    endian: big
    fields:
      - name: checksum
        type: u16
"""

    schema = load_schema(schema_txt)
    assert schema.endian == "little"

    with PagedReader(str(p)) as r:
        tree, leaves, errs = apply_schema_tree(r, schema)

    assert not errs
    assert len(leaves) == 3

    # Verify header.magic uses big endian from parent struct
    assert leaves[0].name == "header.magic"
    assert leaves[0].value == 0x1234
    assert leaves[0].effective_endian == "big"
    assert leaves[0].endian_source == "parent"

    # Verify body uses little endian from root
    assert leaves[1].name == "body"
    assert leaves[1].value == 0x12345678
    assert leaves[1].effective_endian == "little"
    assert leaves[1].endian_source == "root"

    # Verify footer.checksum uses big endian from parent struct
    assert leaves[2].name == "footer.checksum"
    assert leaves[2].value == 0xABCD
    assert leaves[2].effective_endian == "big"
    assert leaves[2].endian_source == "parent"

    # Verify spans include endian info
    spans = [
        Span(
            pf.offset,
            pf.length,
            pf.name,
            type_group(pf.type),
            pf.effective_endian,
            pf.endian_source,
        )
        for pf in leaves
        if not pf.error and pf.length > 0
    ]

    assert len(spans) == 3
    assert spans[0].effective_endian == "big"
    assert spans[0].endian_source == "parent"
    assert spans[1].effective_endian == "little"
    assert spans[1].endian_source == "root"
    assert spans[2].effective_endian == "big"
    assert spans[2].endian_source == "parent"

    # Verify SpanIndex can find spans with endian info
    span_index = SpanIndex(spans)
    sp = span_index.find(0)  # header.magic
    assert sp is not None
    assert sp.path == "header.magic"
    assert sp.effective_endian == "big"
    assert sp.endian_source == "parent"


def test_endian_integration_field_override(tmp_path: Path) -> None:
    """Test field-level endian override takes highest priority."""
    p = tmp_path / "override.bin"
    # Write 3 u16 values: 0x1234 in BE, 0x5678 in BE, 0xABCD in BE
    data = (0x1234).to_bytes(2, "big") + (0x5678).to_bytes(2, "big") + (0xABCD).to_bytes(2, "big")
    p.write_bytes(data)

    schema_txt = """
endian: little
fields:
  - name: container
    type: struct
    endian: little
    fields:
      - name: default_field
        type: u16
        endian: big
      - name: parent_field
        type: u16
      - name: field_override
        type: u16
        endian: big
"""

    schema = load_schema(schema_txt)
    with PagedReader(str(p)) as r:
        tree, leaves, errs = apply_schema_tree(r, schema)

    assert not errs
    assert len(leaves) == 3

    # First field: field override should take precedence
    assert leaves[0].name == "container.default_field"
    assert leaves[0].value == 0x1234
    assert leaves[0].effective_endian == "big"
    assert leaves[0].endian_source == "field"

    # Second field: should use parent (little) endian
    assert leaves[1].name == "container.parent_field"
    assert leaves[1].value == 0x7856  # Little-endian interpretation of 0x5678 bytes
    assert leaves[1].effective_endian == "little"
    assert leaves[1].endian_source == "parent"

    # Third field: field override takes precedence over parent
    assert leaves[2].name == "container.field_override"
    assert leaves[2].value == 0xABCD
    assert leaves[2].effective_endian == "big"
    assert leaves[2].endian_source == "field"


def test_endian_integration_array_propagation(tmp_path: Path) -> None:
    """Test endian propagates through array elements."""
    p = tmp_path / "array.bin"
    # Write 4 u16 values in big-endian: 0x0001, 0x0002, 0x0003, 0x0004
    data = b"\x00\x01\x00\x02\x00\x03\x00\x04"
    p.write_bytes(data)

    schema_txt = """
endian: little
fields:
  - name: big_array
    type: array
    length: 4
    endian: big
    element:
      type: u16
"""

    schema = load_schema(schema_txt)
    with PagedReader(str(p)) as r:
        tree, leaves, errs = apply_schema_tree(r, schema)

    assert not errs
    assert len(leaves) == 4

    # All array elements should inherit big endian from parent array
    for i in range(4):
        assert leaves[i].name == f"big_array[{i}]"
        assert leaves[i].value == i + 1
        assert leaves[i].effective_endian == "big"
        assert leaves[i].endian_source == "parent"


def test_endian_integration_type_definition(tmp_path: Path) -> None:
    """Test endian in type definitions."""
    p = tmp_path / "typedef.bin"
    # Write a u32 value 0x12345678 in big-endian
    p.write_bytes((0x12345678).to_bytes(4, "big"))

    schema_txt = """
endian: little
types:
  BigU32:
    type: u32
    endian: big

fields:
  - name: value
    type: BigU32
"""

    schema = load_schema(schema_txt)
    with PagedReader(str(p)) as r:
        tree, leaves, errs = apply_schema_tree(r, schema)

    assert not errs
    assert len(leaves) == 1

    # Type endian is merged into field_endian by schema parser
    assert leaves[0].name == "value"
    assert leaves[0].value == 0x12345678
    assert leaves[0].effective_endian == "big"
    assert leaves[0].endian_source == "field"


def test_endian_integration_nested_structs(tmp_path: Path) -> None:
    """Test endian resolution in deeply nested structures."""
    p = tmp_path / "nested.bin"
    # Write 4 u16 values:
    # outer.a: 0x1234 in big (from outer struct)
    # outer.middle.b: 0x5678 in little (from middle struct)
    # outer.middle.c: 0xABCD in big (field override)
    # outer.d: 0xDEAD in big (from outer struct)
    data = (
        (0x1234).to_bytes(2, "big")
        + (0x5678).to_bytes(2, "little")
        + (0xABCD).to_bytes(2, "big")
        + (0xDEAD).to_bytes(2, "big")
    )
    p.write_bytes(data)

    schema_txt = """
endian: little
fields:
  - name: outer
    type: struct
    endian: big
    fields:
      - name: a
        type: u16
      - name: middle
        type: struct
        endian: little
        fields:
          - name: b
            type: u16
          - name: c
            type: u16
            endian: big
      - name: d
        type: u16
"""

    schema = load_schema(schema_txt)
    with PagedReader(str(p)) as r:
        tree, leaves, errs = apply_schema_tree(r, schema)

    assert not errs
    assert len(leaves) == 4

    # outer.a uses outer struct's big endian
    assert leaves[0].name == "outer.a"
    assert leaves[0].value == 0x1234
    assert leaves[0].effective_endian == "big"
    assert leaves[0].endian_source == "parent"

    # outer.middle.b uses middle struct's little endian
    assert leaves[1].name == "outer.middle.b"
    assert leaves[1].value == 0x5678
    assert leaves[1].effective_endian == "little"
    assert leaves[1].endian_source == "parent"

    # outer.middle.c uses field override (big)
    assert leaves[2].name == "outer.middle.c"
    assert leaves[2].value == 0xABCD
    assert leaves[2].effective_endian == "big"
    assert leaves[2].endian_source == "field"

    # outer.d uses outer struct's big endian
    assert leaves[3].name == "outer.d"
    assert leaves[3].value == 0xDEAD
    assert leaves[3].effective_endian == "big"
    assert leaves[3].endian_source == "parent"
