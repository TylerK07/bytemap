from __future__ import annotations

import yaml

from hexmap.core.schema_edit import upsert_numeric_field


def test_commit_numeric_field_yaml() -> None:
    base = "fields:\n  - name: header\n    type: bytes\n    length: 4\n"
    new, spec = upsert_numeric_field(base, offset=0x10, type_name="u16", name="count")
    data = yaml.safe_load(new)
    assert isinstance(data, dict)
    f = data["fields"][-1]
    assert f["name"] == "count"
    assert int(f["offset"], 0) == 0x10
    assert f["type"] == "u16"

