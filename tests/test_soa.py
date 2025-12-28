from __future__ import annotations

from pathlib import Path

from hexmap.core.io import PagedReader
from hexmap.core.parse import apply_schema_tree
from hexmap.core.schema import load_schema


def make_bytes(cols: list[bytes]) -> bytes:
    # Concatenate columns (each is N items * item_size)
    return b"".join(cols)


def test_soa_schema_validation_and_parsing(tmp_path: Path) -> None:
    # Define SoA with 3 items: leader (2 bytes), cash (i16)
    schema_text = (
        "types:\n"
        "  leader_name: { type: string, length: 2, encoding: ascii }\n"
        "fields:\n"
        "  - name: civs\n"
        "    type: array\n"
        "    length: 3\n"
        "    layout: soa\n"
        "    fields:\n"
        "      - { name: leader, type: leader_name }\n"
        "      - { name: cash, type: i16 }\n"
    )
    schema = load_schema(schema_text)
    # Build bytes: leader[3] then cash[3]
    leaders = b"AA" + b"BB" + b"CC"  # 3 * 2 bytes
    cash = (
        (1).to_bytes(2, "little", signed=False)
        + (2).to_bytes(2, "little", signed=False)
        + (3).to_bytes(2, "little", signed=False)
    )
    data = make_bytes([leaders, cash])
    p = tmp_path / "soa.bin"
    p.write_bytes(data)
    with PagedReader(str(p)) as r:
        tree, leaves, errs = apply_schema_tree(r, schema)
    assert not errs
    civs = next(n for n in tree if n.path == "civs")
    assert civs.type == "array" and civs.children is not None and len(civs.children) == 3
    # Check record 0
    rec0 = civs.children[0]
    names = [ch.path for ch in rec0.children or []]
    assert names == ["civs[0].leader", "civs[0].cash"]
    vals = [ch.value for ch in rec0.children or []]
    assert vals[0] == "AA" and vals[1] == 1
    # Offsets: leader column at 0,2,4; cash column starts at 6
    leader_offsets = [
        c.offset for c in (civs.children[0].children or []) if c.path.endswith("leader")
    ]
    assert leader_offsets[0] == 0
    leader_offsets1 = [
        c.offset for c in (civs.children[1].children or []) if c.path.endswith("leader")
    ]
    assert leader_offsets1[0] == 2
    # Leaves include both columns
    assert any(pf.name.endswith("leader") for pf in leaves)
    assert any(pf.name.endswith("cash") for pf in leaves)
