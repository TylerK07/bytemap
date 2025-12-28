from __future__ import annotations

from pathlib import Path

import pytest

from hexmap.core.io import PagedReader
from hexmap.core.parse import apply_schema_tree
from hexmap.core.schema import SchemaError, load_schema


def test_shorthand_basic_rewrite(tmp_path: Path) -> None:
    schema_txt = """
types:
  Item:
    type: struct
    fields:
      - { name: id, type: u8 }
      - { name: qty, type: u8 }

fields:
  - name: inventory
    type: array of Item
    length: 2
    stride: 2
"""
    p = tmp_path / "f.bin"
    p.write_bytes(bytes([1, 9, 2, 8]))
    schema = load_schema(schema_txt)
    with PagedReader(str(p)) as r:
        tree, leaves, errs = apply_schema_tree(r, schema)
    assert not errs
    names = {pf.name for pf in leaves}
    assert "inventory[0].id" in names
    assert "inventory[1].qty" in names


def test_shorthand_missing_length_errors() -> None:
    bad = """
types:
  Item:
    type: struct
    fields:
      - { name: v, type: u8 }

fields:
  - name: inventory
    type: array of Item
    stride: 1
"""
    with pytest.raises(SchemaError) as ei:
        load_schema(bad)
    assert "requires length" in "; ".join(ei.value.errors)


def test_shorthand_with_element_conflict_errors() -> None:
    bad = """
types:
  Item:
    type: struct
    fields:
      - { name: v, type: u8 }

fields:
  - name: inventory
    type: array of Item
    length: 1
    element:
      type: Item
"""
    with pytest.raises(SchemaError) as ei:
        load_schema(bad)
    assert "array-of shorthand cannot also specify 'element'" in "; ".join(ei.value.errors)


@pytest.mark.parametrize(
    "bad_type",
    [
        "arrayof Item",
        "array Item",
        "array of Item stride 2",
    ],
)
def test_invalid_patterns_do_not_rewrite(bad_type: str) -> None:
    bad = f"""
fields:
  - name: inv
    type: {bad_type}
    length: 1
    stride: 1
"""
    with pytest.raises(SchemaError):
        load_schema(bad)

