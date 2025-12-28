from __future__ import annotations

from pathlib import Path

from hexmap.core.io import PagedReader
from hexmap.core.parse import apply_schema_tree
from hexmap.core.schema import load_schema


def write_sample(tmp_path: Path) -> Path:
    p = tmp_path / "bin.bin"
    data = bytearray(256)
    # version u16le at 4
    data[4:6] = (7).to_bytes(2, "little")
    # player struct at 0x20: hp=1000, mp=50
    data[0x20:0x22] = (1000).to_bytes(2, "little")
    data[0x22:0x24] = (50).to_bytes(2, "little")
    # inventory_count at 0x30
    data[0x30:0x31] = bytes([3])
    # inventory array at 0x40 with three items (id,qty)
    base = 0x40
    items = [(1, 9), (2, 8), (3, 7)]
    for i, (iid, qty) in enumerate(items):
        data[base + i * 2] = iid
        data[base + i * 2 + 1] = qty
    # utf-16le string at 0x10 of length 6 bytes (3 chars)
    data[0x10:0x16] = "ABC".encode("utf-16le")
    p.write_bytes(data)
    return p


def test_struct_and_array_stride_infer_and_length_from(tmp_path: Path) -> None:
    p = write_sample(tmp_path)
    schema_txt = """
endian: little
fields:
  - { name: magic, type: bytes, length: 4 }
  - { name: version, type: u16 }
  - name: player
    offset: 0x20
    type: struct
    fields:
      - { name: hp, type: u16 }
      - { name: mp, type: u16 }
  - { name: inventory_count, offset: 0x30, type: u8 }
  - name: inventory
    offset: 0x40
    type: array
    length_from: inventory_count
    element:
      type: struct
      fields:
        - { name: id, type: u8 }
        - { name: qty, type: u8 }
"""
    schema = load_schema(schema_txt)
    with PagedReader(str(p)) as r:
        tree, leaves, errs = apply_schema_tree(r, schema)
    assert not errs
    # Check some leaves by path
    by_path = {pf.name: pf for pf in leaves}
    assert by_path["version"].value == 7
    assert by_path["player.hp"].value == 1000
    assert by_path["player.mp"].value == 50
    assert by_path["inventory[0].id"].value == 1
    assert by_path["inventory[1].qty"].value == 8


def test_string_utf16le_and_null_terminated(tmp_path: Path) -> None:
    p = write_sample(tmp_path)
    schema_txt = """
endian: little
fields:
  - { name: title, offset: 0x10, type: string, encoding: utf-16le, length: 6 }
  - name: name_nt
    offset: 0x50
    type: string
    encoding: ascii
    null_terminated: true
    max_length: 8
"""
    # write a null-terminated ascii string at 0x50
    with open(p, "rb") as fh:
        b = bytearray(fh.read())
    b[0x50:0x58] = b"HELLO\x00\xFF\xFF"
    p.write_bytes(b)
    schema = load_schema(schema_txt)
    with PagedReader(str(p)) as r:
        tree, leaves, errs = apply_schema_tree(r, schema)
    assert not errs
    by = {pf.name: pf for pf in leaves}
    assert by["title"].value == "ABC"  # utf-16le decoded
    assert by["name_nt"].value == "HELLO"


def test_overlap_detection_on_leaves(tmp_path: Path) -> None:
    p = write_sample(tmp_path)
    # Overlap inside a struct (relative offsets)
    schema_txt = """
endian: little
fields:
  - name: s
    offset: 0x10
    type: struct
    fields:
      - { name: a, offset: 0, type: u32 }
      - { name: b, offset: 2, type: u16 }
"""
    schema = load_schema(schema_txt)
    with PagedReader(str(p)) as r:
        tree, leaves, errs = apply_schema_tree(r, schema)
    assert any("Overlap" in e for e in errs)
