from __future__ import annotations

import yaml

from hexmap.core.schema_edit import upsert_string_field


def test_commit_fixed_and_cstring_upsert() -> None:
    base = "fields:\n  - name: magic\n    type: bytes\n    length: 4\n"
    # Insert fixed-length
    new, spec = upsert_string_field(base, offset=0x98, fixed_length=16)
    data = yaml.safe_load(new)
    assert isinstance(data, dict) and isinstance(data.get("fields"), list)
    last = data["fields"][-1]
    assert last["name"].startswith("field_0x") and last["type"] == "string"
    assert int(last["offset"], 0) == 0x98
    assert last["length"] == 16
    # Overwrite same offset with cstring
    newer, spec2 = upsert_string_field(new, offset=0x98, cstring_max=64)
    data2 = yaml.safe_load(newer)
    last2 = data2["fields"][-1]
    assert last2.get("null_terminated") is True
    assert last2.get("max_length") == 64
    # Ensure only one entry for offset remains
    offs = []
    for f in data2["fields"]:
        offv = f.get("offset")
        offs.append(int(offv, 0) if isinstance(offv, str) else offv)
    assert offs.count(0x98) == 1
