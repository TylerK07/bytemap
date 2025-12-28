from __future__ import annotations

from pathlib import Path

from hexmap.core.io import PagedReader
from hexmap.core.parse import apply_schema_tree
from hexmap.core.schema import load_schema


def parse(schema_txt: str, data: bytes):
    return schema_txt, data


def test_array_length_static_int(tmp_path: Path) -> None:
    schema_txt = """
fields:
  - name: items
    type: array
    length: 3
    stride: 1
    element:
      type: struct
      fields:
        - { name: v, type: u8 }
"""
    p = tmp_path / "f.bin"
    p.write_bytes(bytes([1, 2, 3]))
    schema = load_schema(schema_txt)
    with PagedReader(str(p)) as r:
        tree, leaves, errs = apply_schema_tree(r, schema)
    assert not errs
    assert len([pf for pf in leaves if pf.name.endswith(".v")]) == 3


def test_array_length_numeric_string(tmp_path: Path) -> None:
    schema_txt = """
fields:
  - name: items
    type: array
    length: "10"
    stride: 1
    element:
      type: struct
      fields:
        - { name: v, type: u8 }
"""
    p = tmp_path / "f.bin"
    p.write_bytes(bytes(range(10)))
    schema = load_schema(schema_txt)
    with PagedReader(str(p)) as r:
        tree, leaves, errs = apply_schema_tree(r, schema)
    assert not errs
    assert len([pf for pf in leaves if pf.name.endswith(".v")]) == 10


def test_array_length_hex_string(tmp_path: Path) -> None:
    schema_txt = """
fields:
  - name: items
    type: array
    length: "0x0A"
    stride: 1
    element:
      type: struct
      fields:
        - { name: v, type: u8 }
"""
    p = tmp_path / "f.bin"
    p.write_bytes(bytes(range(10)))
    schema = load_schema(schema_txt)
    with PagedReader(str(p)) as r:
        tree, leaves, errs = apply_schema_tree(r, schema)
    assert not errs
    assert len([pf for pf in leaves if pf.name.endswith(".v")]) == 10


def test_array_length_ref(tmp_path: Path) -> None:
    schema_txt = """
fields:
  - { name: num_rows, type: u8 }
  - name: items
    type: array
    length: num_rows
    stride: 1
    element:
      type: struct
      fields:
        - { name: v, type: u8 }
"""
    p = tmp_path / "f.bin"
    p.write_bytes(bytes([3, 10, 11, 12]))
    schema = load_schema(schema_txt)
    with PagedReader(str(p)) as r:
        tree, leaves, errs = apply_schema_tree(r, schema)
    assert not errs
    assert len([pf for pf in leaves if pf.name.endswith(".v")]) == 3


def test_array_length_ref_mapping(tmp_path: Path) -> None:
    schema_txt = """
fields:
  - { name: num_rows, type: u8 }
  - name: items
    type: array
    length: { ref: num_rows }
    stride: 1
    element:
      type: struct
      fields:
        - { name: v, type: u8 }
"""
    p = tmp_path / "f.bin"
    p.write_bytes(bytes([2, 10, 11]))
    schema = load_schema(schema_txt)
    with PagedReader(str(p)) as r:
        tree, leaves, errs = apply_schema_tree(r, schema)
    assert not errs
    assert len([pf for pf in leaves if pf.name.endswith(".v")]) == 2


def test_string_length_ref(tmp_path: Path) -> None:
    schema_txt = """
fields:
  - { name: name_len, type: u8 }
  - name: name
    type: string
    length: name_len
    encoding: ascii
"""
    p = tmp_path / "f.bin"
    p.write_bytes(bytes([5]) + b"HELLOWORLD")
    schema = load_schema(schema_txt)
    with PagedReader(str(p)) as r:
        tree, leaves, errs = apply_schema_tree(r, schema)
    assert not errs
    by = {pf.name: pf for pf in leaves}
    assert by["name"].value == "HELLO"


def test_unresolved_ref_error(tmp_path: Path) -> None:
    schema_txt = """
fields:
  - name: items
    type: array
    length: rows_count
    stride: 1
    element:
      type: struct
      fields:
        - { name: v, type: u8 }
"""
    p = tmp_path / "f.bin"
    p.write_bytes(bytes([1, 2, 3]))
    schema = load_schema(schema_txt)
    with PagedReader(str(p)) as r:
        tree, leaves, errs = apply_schema_tree(r, schema)
    assert any("length ref unresolved" in e or "unresolved" in e for e in errs)


def test_non_int_ref_error(tmp_path: Path) -> None:
    schema_txt = """
fields:
  - name: other
    type: string
    length: 3
    encoding: ascii
  - name: items
    type: array
    length: other
    stride: 1
    element:
      type: struct
      fields:
        - { name: v, type: u8 }
"""
    p = tmp_path / "f.bin"
    p.write_bytes(b"ABC" + bytes([1, 2, 3]))
    schema = load_schema(schema_txt)
    with PagedReader(str(p)) as r:
        tree, leaves, errs = apply_schema_tree(r, schema)
    assert any("length ref" in e for e in errs)


def test_length_cap_enforcement(tmp_path: Path) -> None:
    # string length exceeds cap
    schema_txt = """
fields:
  - name: name
    type: string
    length: "1000001"
    encoding: ascii
"""
    p = tmp_path / "f.bin"
    p.write_bytes(b"A" * 2)
    schema = load_schema(schema_txt)
    with PagedReader(str(p)) as r:
        tree, leaves, errs = apply_schema_tree(r, schema)
    # Node should record error even if not bubbled to errs
    assert any(pf.error and "exceeds safety cap" in pf.error for pf in leaves)
