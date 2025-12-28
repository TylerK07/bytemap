from __future__ import annotations

from typing import Any

import yaml


def _hex_name(offset: int) -> str:
    return f"field_0x{offset:08X}"


def _offset_value(offset: int) -> str:
    # Represent as hex like 0x98
    return hex(int(offset))


def upsert_string_field(
    yaml_text: str,
    *,
    offset: int,
    fixed_length: int | None = None,
    cstring_max: int | None = None,
    name: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Insert or update a string field at `offset`.

    If `fixed_length` is provided, inserts a fixed-length ASCII string.
    If `cstring_max` is provided, inserts a null-terminated string with max_length.

    Returns (new_yaml_text, field_dict_used).
    """
    if (fixed_length is None) == (cstring_max is None):
        raise ValueError("exactly one of fixed_length or cstring_max must be set")

    try:
        data = yaml.safe_load(yaml_text) or {}
    except Exception:
        data = {}

    if not isinstance(data, dict):
        data = {}
    fields = data.get("fields")
    if not isinstance(fields, list):
        fields = []
    # Build field spec
    field_name = (name or _hex_name(offset))
    spec: dict[str, Any] = {
        "name": field_name,
        "offset": _offset_value(offset),
        "type": "string",
    }
    if fixed_length is not None:
        spec["length"] = int(fixed_length)
    else:
        spec["null_terminated"] = True
        spec["max_length"] = int(cstring_max or 0)

    # Overwrite existing by offset (and if name already present)
    new_fields: list[dict[str, Any]] = []
    replaced = False
    for f in fields:
        if not isinstance(f, dict):
            new_fields.append(f)
            continue
        off = f.get("offset")
        # safe_load parses 0x.. to int; be permissive
        try:
            off_int = int(off, 0) if isinstance(off, str) else int(off)
        except Exception:
            off_int = None
        if off_int == offset:
            if not replaced:
                new_fields.append(spec)
                replaced = True
            # skip duplicates at same offset
        else:
            new_fields.append(f)
    if not replaced:
        new_fields.append(spec)

    data["fields"] = new_fields
    new_text = yaml.safe_dump(data, sort_keys=False)
    return new_text, spec


def upsert_numeric_field(
    yaml_text: str,
    *,
    offset: int,
    type_name: str,
    name: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Insert or update a numeric field at `offset` with canonical DSL type.

    Returns (new_yaml_text, field_dict_used).
    """
    try:
        data = yaml.safe_load(yaml_text) or {}
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    fields = data.get("fields")
    if not isinstance(fields, list):
        fields = []
    spec: dict[str, Any] = {
        "name": (name or _hex_name(offset)),
        "offset": _offset_value(offset),
        "type": type_name,
    }
    new_fields: list[dict[str, Any]] = []
    replaced = False
    for f in fields:
        if not isinstance(f, dict):
            new_fields.append(f)
            continue
        off = f.get("offset")
        try:
            off_int = int(off, 0) if isinstance(off, str) else int(off)
        except Exception:
            off_int = None
        if off_int == offset:
            if not replaced:
                new_fields.append(spec)
                replaced = True
        else:
            new_fields.append(f)
    if not replaced:
        new_fields.append(spec)
    data["fields"] = new_fields
    new_text = yaml.safe_dump(data, sort_keys=False)
    return new_text, spec


def upsert_bytes_field(
    yaml_text: str,
    *,
    offset: int,
    length: int,
    name: str | None = None,
) -> tuple[str, dict[str, Any]]:
    try:
        data = yaml.safe_load(yaml_text) or {}
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    fields = data.get("fields")
    if not isinstance(fields, list):
        fields = []
    spec: dict[str, Any] = {
        "name": (name or _hex_name(offset)),
        "offset": _offset_value(offset),
        "type": "bytes",
        "length": int(length),
    }
    new_fields: list[dict[str, Any]] = []
    replaced = False
    for f in fields:
        if not isinstance(f, dict):
            new_fields.append(f)
            continue
        off = f.get("offset")
        try:
            off_int = int(off, 0) if isinstance(off, str) else int(off)
        except Exception:
            off_int = None
        if off_int == offset:
            if not replaced:
                new_fields.append(spec)
                replaced = True
        else:
            new_fields.append(f)
    if not replaced:
        new_fields.append(spec)
    data["fields"] = new_fields
    new_text = yaml.safe_dump(data, sort_keys=False)
    return new_text, spec


def upsert_array_field(
    yaml_text: str,
    *,
    offset: int,
    elem_type: str,
    length: int,
    name: str | None = None,
) -> tuple[str, dict[str, Any]]:
    try:
        data = yaml.safe_load(yaml_text) or {}
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    fields = data.get("fields")
    if not isinstance(fields, list):
        fields = []
    spec: dict[str, Any] = {
        "name": (name or _hex_name(offset)),
        "offset": _offset_value(offset),
        "type": f"array of {elem_type}",
        "length": int(length),
    }
    new_fields: list[dict[str, Any]] = []
    replaced = False
    for f in fields:
        if not isinstance(f, dict):
            new_fields.append(f)
            continue
        off = f.get("offset")
        try:
            off_int = int(off, 0) if isinstance(off, str) else int(off)
        except Exception:
            off_int = None
        if off_int == offset:
            if not replaced:
                new_fields.append(spec)
                replaced = True
        else:
            new_fields.append(f)
    if not replaced:
        new_fields.append(spec)
    data["fields"] = new_fields
    new_text = yaml.safe_dump(data, sort_keys=False)
    return new_text, spec


def upsert_ascii_type_and_field(
    yaml_text: str,
    *,
    offset: int,
    slot_len: int,
    instances: int = 1,
    name: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Ensure a ascii_<L> alias (fixed-length string) exists and upsert field.

    Alias form: ascii_<L>: { type: string, length: L }
    """
    try:
        data = yaml.safe_load(yaml_text) or {}
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    types = data.get("types")
    if types is None or not isinstance(types, dict):
        types = {}
    tname = f"ascii_{int(slot_len)}"
    desired = {"type": "string", "length": int(slot_len)}
    existing = types.get(tname)
    if existing is None:
        types[tname] = desired
    else:
        try:
            ok = (
                isinstance(existing, dict)
                and existing.get("type") == "string"
                and int(existing.get("length", 0)) == int(slot_len)
                and not bool(existing.get("null_terminated", False))
            )
        except Exception:
            ok = False
        if not ok:
            tname = f"{tname}_v2"
            types[tname] = desired
    data["types"] = types
    if int(instances) > 1:
        spec = {
            "name": (name or _hex_name(offset)),
            "offset": _offset_value(offset),
            "type": f"array of {tname}",
            "length": int(instances),
        }
    else:
        spec = {"name": (name or _hex_name(offset)), "offset": _offset_value(offset), "type": tname}
    fields = data.get("fields")
    if not isinstance(fields, list):
        fields = []
    new_fields: list[dict[str, Any]] = []
    replaced = False
    for f in fields:
        if not isinstance(f, dict):
            new_fields.append(f)
            continue
        off = f.get("offset")
        try:
            off_int = int(off, 0) if isinstance(off, str) else int(off)
        except Exception:
            off_int = None
        if off_int == offset:
            if not replaced:
                new_fields.append(spec)
                replaced = True
        else:
            new_fields.append(f)
    if not replaced:
        new_fields.append(spec)
    data["fields"] = new_fields
    return yaml.safe_dump(data, sort_keys=False), spec


def upsert_bytes_type_and_field(
    yaml_text: str,
    *,
    offset: int,
    elem_len: int,
    instances: int,
    name: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Ensure a bytes_<L> alias exists and upsert an array field of that alias."""
    try:
        data = yaml.safe_load(yaml_text) or {}
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    types = data.get("types")
    if types is None or not isinstance(types, dict):
        types = {}
    tname = f"bytes_{int(elem_len)}"
    desired = {"type": "bytes", "length": int(elem_len)}
    existing = types.get(tname)
    if existing is None:
        types[tname] = desired
    else:
        try:
            ok = (
                isinstance(existing, dict)
                and existing.get("type") == "bytes"
                and int(existing.get("length", 0)) == int(elem_len)
            )
        except Exception:
            ok = False
        if not ok:
            tname = f"{tname}_v2"
            types[tname] = desired
    data["types"] = types
    spec = {
        "name": (name or _hex_name(offset)),
        "offset": _offset_value(offset),
        "type": f"array of {tname}",
        "length": int(instances),
    }
    fields = data.get("fields")
    if not isinstance(fields, list):
        fields = []
    new_fields: list[dict[str, Any]] = []
    replaced = False
    for f in fields:
        if not isinstance(f, dict):
            new_fields.append(f)
            continue
        off = f.get("offset")
        try:
            off_int = int(off, 0) if isinstance(off, str) else int(off)
        except Exception:
            off_int = None
        if off_int == offset:
            if not replaced:
                new_fields.append(spec)
                replaced = True
        else:
            new_fields.append(f)
    if not replaced:
        new_fields.append(spec)
    data["fields"] = new_fields
    return yaml.safe_dump(data, sort_keys=False), spec
def upsert_cstring_type_and_field(
    yaml_text: str,
    *,
    offset: int,
    slot_len: int,
    instances: int = 1,
    name: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Ensure a cstring_<L> type exists and upsert a field using it (scalar or array)."""
    try:
        data = yaml.safe_load(yaml_text) or {}
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    types = data.get("types")
    if types is None or not isinstance(types, dict):
        types = {}
    # Desired alias: null-terminated strings must use max_length (not length)
    tname = f"cstring_{int(slot_len)}"
    desired = {"type": "string", "null_terminated": True, "max_length": int(slot_len)}
    existing = types.get(tname)
    if existing is None:
        types[tname] = desired
    else:
        try:
            ok = (
                isinstance(existing, dict)
                and existing.get("type") == "string"
                and bool(existing.get("null_terminated", False)) is True
                and int(existing.get("max_length", 0)) == int(slot_len)
            )
        except Exception:
            ok = False
        if not ok:
            tname = f"{tname}_v2"
            types[tname] = desired
    data["types"] = types
    # Field spec
    if int(instances) > 1:
        spec = {
            "name": (name or _hex_name(offset)),
            "offset": _offset_value(offset),
            "type": f"array of {tname}",
            "length": int(instances),
        }
    else:
        spec = {
            "name": (name or _hex_name(offset)),
            "offset": _offset_value(offset),
            "type": tname,
        }
    # Upsert field at offset
    fields = data.get("fields")
    if not isinstance(fields, list):
        fields = []
    new_fields: list[dict[str, Any]] = []
    replaced = False
    for f in fields:
        if not isinstance(f, dict):
            new_fields.append(f)
            continue
        off = f.get("offset")
        try:
            off_int = int(off, 0) if isinstance(off, str) else int(off)
        except Exception:
            off_int = None
        if off_int == offset:
            if not replaced:
                new_fields.append(spec)
                replaced = True
        else:
            new_fields.append(f)
    if not replaced:
        new_fields.append(spec)
    data["fields"] = new_fields
    return yaml.safe_dump(data, sort_keys=False), spec


def upsert_date_field(
    yaml_text: str,
    *,
    offset: int,
    format: str,
    name: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Insert or update a date field at `offset` with appropriate storage type.

    Maps date format to storage type:
    - unix_s → u32
    - unix_ms → u64
    - filetime → u64
    - dos_date → u16
    - dos_datetime → u32
    - ole_date → bytes (8) [double precision float]
    - ftm_packed → u32

    Returns (new_yaml_text, field_dict_used).
    """
    # Map format to storage type
    format_to_type = {
        "unix_s": "u32",
        "unix_ms": "u64",
        "filetime": "u64",
        "dos_date": "u16",
        "dos_datetime": "u32",
        "ole_date": "bytes",  # 8-byte double
        "ftm_packed": "u32",
    }

    storage_type = format_to_type.get(format)
    if storage_type is None:
        raise ValueError(f"Unknown date format: {format}")

    try:
        data = yaml.safe_load(yaml_text) or {}
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    fields = data.get("fields")
    if not isinstance(fields, list):
        fields = []

    spec: dict[str, Any] = {
        "name": (name or _hex_name(offset)),
        "offset": _offset_value(offset),
        "type": storage_type,
        "format": format,
    }

    # ole_date needs length since it's stored as bytes
    if format == "ole_date":
        spec["length"] = 8

    new_fields: list[dict[str, Any]] = []
    replaced = False
    for f in fields:
        if not isinstance(f, dict):
            new_fields.append(f)
            continue
        off = f.get("offset")
        try:
            off_int = int(off, 0) if isinstance(off, str) else int(off)
        except Exception:
            off_int = None
        if off_int == offset:
            if not replaced:
                new_fields.append(spec)
                replaced = True
        else:
            new_fields.append(f)
    if not replaced:
        new_fields.append(spec)
    data["fields"] = new_fields
    new_text = yaml.safe_dump(data, sort_keys=False)
    return new_text, spec


def upsert_chunk_field(
    yaml_text: str,
    *,
    offset: int,
    length_type: str,
    length_includes_header: bool = False,
    name: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Insert or update a chunk field at `offset`.

    Args:
        yaml_text: Current YAML schema text
        offset: Byte offset for the chunk
        length_type: One of: u8, u16 LE, u16 BE, u32 LE, u32 BE
        length_includes_header: Whether declared length includes the length field itself
        name: Field name (defaults to chunk_XX)

    Returns (new_yaml_text, field_dict_used).
    """
    try:
        data = yaml.safe_load(yaml_text) or {}
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    fields = data.get("fields")
    if not isinstance(fields, list):
        fields = []

    # Generate unique name if not provided
    if name is None:
        existing_names = {f.get("name") for f in fields if isinstance(f, dict)}
        idx = 1
        while f"chunk_{idx:02d}" in existing_names:
            idx += 1
        name = f"chunk_{idx:02d}"

    spec: dict[str, Any] = {
        "name": name,
        "offset": _offset_value(offset),
        "type": "chunk",
        "length_type": length_type,
        "payload": {"type": "bytes"},
    }

    if length_includes_header:
        spec["length_includes_header"] = True

    new_fields: list[dict[str, Any]] = []
    replaced = False
    for f in fields:
        if not isinstance(f, dict):
            new_fields.append(f)
            continue
        off = f.get("offset")
        try:
            off_int = int(off, 0) if isinstance(off, str) else int(off)
        except Exception:
            off_int = None
        if off_int == offset:
            if not replaced:
                new_fields.append(spec)
                replaced = True
        else:
            new_fields.append(f)
    if not replaced:
        new_fields.append(spec)
    data["fields"] = new_fields
    new_text = yaml.safe_dump(data, sort_keys=False)
    return new_text, spec
