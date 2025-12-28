from __future__ import annotations

from pathlib import Path

import pytest

from hexmap.core.io import PagedReader
from hexmap.core.parse import apply_schema_tree
from hexmap.core.schema import SchemaError, load_schema


def test_top_level_type_expansion(tmp_path: Path) -> None:
    schema_txt = """
types:
  Header:
    type: struct
    fields:
      - { name: magic, type: bytes, length: 4 }
      - { name: version, type: u16 }

fields:
  - { name: header, type: Header }
"""
    p = tmp_path / "f.bin"
    p.write_bytes(b"MAGC" + (5).to_bytes(2, "little"))
    schema = load_schema(schema_txt)
    with PagedReader(str(p)) as r:
        tree, leaves, errs = apply_schema_tree(r, schema)
    assert not errs
    by = {pf.name: pf for pf in leaves}
    assert by["header.magic"].value == b"MAGC"
    assert by["header.version"].value == 5


def test_nested_type_in_struct(tmp_path: Path) -> None:
    schema_txt = """
types:
  Item:
    type: struct
    fields:
      - { name: id, type: u8 }
      - { name: qty, type: u8 }

fields:
  - name: container
    type: struct
    fields:
      - { name: a, type: Item }
"""
    p = tmp_path / "f.bin"
    p.write_bytes(bytes([1, 9]))
    schema = load_schema(schema_txt)
    with PagedReader(str(p)) as r:
        tree, leaves, errs = apply_schema_tree(r, schema)
    assert not errs
    by = {pf.name: pf for pf in leaves}
    assert by["container.a.id"].value == 1
    assert by["container.a.qty"].value == 9


def test_array_element_type(tmp_path: Path) -> None:
    schema_txt = """
types:
  Item:
    type: struct
    fields:
      - { name: id, type: u8 }
      - { name: qty, type: u8 }

fields:
  - name: inventory
    type: array
    length: 2
    stride: 2
    element:
      type: Item
"""
    p = tmp_path / "f.bin"
    p.write_bytes(bytes([1, 9, 2, 8]))
    schema = load_schema(schema_txt)
    with PagedReader(str(p)) as r:
        tree, leaves, errs = apply_schema_tree(r, schema)
    assert not errs
    by = {pf.name: pf for pf in leaves}
    assert by["inventory[0].id"].value == 1
    assert by["inventory[1].qty"].value == 8


def test_unknown_type_error() -> None:
    bad = """
fields:
  - { name: x, type: Unknown }
"""
    with pytest.raises(SchemaError) as ei:
        load_schema(bad)
    assert "unknown type reference" in "; ".join(ei.value.errors)


def test_cycle_detection_error() -> None:
    bad = """
types:
  A:
    type: struct
    fields:
      - { name: b, type: B }
  B:
    type: struct
    fields:
      - { name: a, type: A }

fields:
  - { name: x, type: A }
"""
    with pytest.raises(SchemaError) as ei:
        load_schema(bad)
    msg = "; ".join(ei.value.errors)
    assert "type cycle detected" in msg

