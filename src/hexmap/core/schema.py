from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import yaml

from hexmap.core.endian import normalize_endian


class SchemaError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


NUM_SIZES = {
    "u8": 1,
    "u16": 2,
    "u32": 4,
    "u64": 8,
    "i8": 1,
    "i16": 2,
    "i32": 4,
    "i64": 8,
}

# Named colors (normalized to lowercase)
NAMED_COLORS = {
    "black", "white", "gray", "grey", "red", "green", "blue",
    "yellow", "cyan", "magenta", "purple", "orange", "pink", "brown"
}


def normalize_color(color: str | None) -> tuple[str | None, str | None]:
    """
    Normalize a color specification to a canonical form.

    Returns (normalized_color, error_message).
    - Named colors normalize to lowercase
    - #RGB expands to #RRGGBB
    - #RRGGBB stays as-is but normalized to lowercase

    Returns (None, error) if invalid.
    """
    if color is None:
        return None, None

    if not isinstance(color, str):
        return None, f"color must be a string, got {type(color).__name__}"

    color_lower = color.lower().strip()

    # Check named colors
    if color_lower in NAMED_COLORS:
        return color_lower, None

    # Check hex formats
    # #RGB format
    match_rgb = re.match(r"^#([0-9a-fA-F]{3})$", color)
    if match_rgb:
        rgb = match_rgb.group(1).lower()
        # Expand: #324 -> #332244
        expanded = f"#{rgb[0]}{rgb[0]}{rgb[1]}{rgb[1]}{rgb[2]}{rgb[2]}"
        return expanded, None

    # #RRGGBB format
    match_rrggbb = re.match(r"^#([0-9a-fA-F]{6})$", color)
    if match_rrggbb:
        return color_lower, None

    # Invalid format
    return None, f"Invalid color '{color}'. Use a named color or hex #RGB/#RRGGBB."


@dataclass(frozen=True)
class Primitive:
    type: str
    length: int | None = None  # for string fixed length
    length_ref: str | None = None  # for string dynamic length
    encoding: str | None = None
    null_terminated: bool | None = None
    max_length: int | None = None
    endian: str | None = None  # field-level endian override
    format: str | None = None  # date/time format (e.g., unix_s, filetime, etc.)
    color: str | None = None  # normalized color override (named or #rrggbb)

    def size(self) -> int | None:
        if self.type in NUM_SIZES:
            return NUM_SIZES[self.type]
        if self.type == "bytes":
            return self.length
        if self.type == "string":
            if self.null_terminated:
                return self.max_length
            return self.length
        return None


@dataclass(frozen=True)
class Node:
    name: str
    # New DSL: either absolute offset (from container base) or skip (from end of previous)
    offset: int | None  # absolute for current container, may be None for sequential
    skip: int | None
    kind: str  # 'primitive'|'struct'|'array'|'soa'|'chunk'
    prim: Primitive | None = None
    fields: list[Node] | None = None
    array_length: int | None = None
    array_length_ref: str | None = None
    element: Node | None = None
    stride: int | None = None
    endian: str | None = None  # type/struct-level endian override
    color: str | None = None  # normalized color override (named or #rrggbb)
    # Chunk-specific fields
    length_type: str | None = None  # e.g., "u16 LE", "u32 BE"
    length_includes_header: bool = False
    payload: Node | None = None  # payload field spec


@dataclass(frozen=True)
class Schema:
    endian: str
    fields: list[Node]


def load_schema(text: str) -> Schema:
    try:
        data = yaml.safe_load(text) or {}
    except Exception as e:  # pragma: no cover
        raise SchemaError([f"YAML parse error: {e}"]) from None

    if not isinstance(data, dict):
        raise SchemaError(["Top-level YAML must be a mapping (use 'endian' and 'fields')."])

    errors: list[str] = []
    raw_endian = data.get("endian", "little")
    try:
        endian = normalize_endian(raw_endian) or "little"
    except ValueError:
        errors.append("endian must be 'little' or 'big'")

    raw_types = data.get("types")
    raw_fields = data.get("fields")
    if not isinstance(raw_fields, list) or not raw_fields:
        errors.append("fields must be a non-empty list")
        raise SchemaError(errors)

    # Build type registry (aliases for any field spec)
    type_defs: dict[str, Any] = {}
    if raw_types is not None:
        if not isinstance(raw_types, dict):
            errors.append("types must be a mapping of name -> field spec")
        else:
            type_defs = raw_types

    # Alias resolver (spec-level) with memoization and cycle detection
    resolved_specs: dict[str, dict[str, Any]] = {}

    def _rewrite_array_of(spec: dict[str, Any]) -> dict[str, Any]:
        t = spec.get("type")
        if isinstance(t, str):
            m = re.fullmatch(r"array of ([A-Za-z0-9_]+)", t)
            if m:
                out = dict(spec)
                out["type"] = "array"
                if "element" in out:
                    return out  # error handled later
                out["element"] = {"type": m.group(1)}
                return out
        return spec

    def resolve_alias_spec(tname: str, stack: list[str]) -> dict[str, Any] | None:
        if tname in stack:
            chain = " -> ".join(stack + [tname])
            errors.append(f"type cycle detected: {chain}")
            return None
        if tname in resolved_specs:
            return deepcopy(resolved_specs[tname])
        tdef = type_defs.get(tname)
        if tdef is None:
            errors.append(f"unknown type reference: {tname}")
            return None
        if not isinstance(tdef, dict) or "type" not in tdef:
            errors.append(f"types[{tname}] must be a mapping with a 'type'")
            return None
        spec = deepcopy(tdef)
        spec = _rewrite_array_of(spec)
        inner_type = spec.get("type")
        if isinstance(inner_type, str) and inner_type not in (
            *NUM_SIZES.keys(),
            "bytes",
            "string",
            "struct",
            "array",
        ):
            # alias chaining: inner refers to another alias
            inner = resolve_alias_spec(inner_type, stack + [tname])
            if inner is None:
                return None
            # merge shallowly: inner base first, then spec overrides (excluding type)
            merged = deepcopy(inner)
            for k, v in spec.items():
                if k == "type":
                    continue
                merged[k] = v
            spec = merged
        # Validate bounded strings on alias spec
        if spec.get("type") == "string" and spec.get("null_terminated"):
            max_len = spec.get("max_length")
            if not isinstance(max_len, int) or max_len <= 0:
                errors.append(
                    f"types[{tname}].max_length required and must be > 0 when null_terminated"
                )
                return None
        resolved_specs[tname] = deepcopy(spec)
        return deepcopy(spec)

    fields: list[Node] = []
    for i, f in enumerate(raw_fields):
        ctx = f"fields[{i}]"
        if not isinstance(f, dict):
            errors.append(f"{ctx} must be a mapping")
            continue
        node = _parse_node(f, ctx, errors, resolve_alias_spec, [])
        if node is not None:
            fields.append(node)

    if errors:
        raise SchemaError(errors)

    return Schema(endian=endian, fields=fields)


def _parse_node(
    f: dict[str, Any],
    ctx: str,
    errors: list[str],
    resolve_type,
    stack: list[str],
    is_chunk_payload: bool = False,
) -> Node | None:
    name = f.get("name")
    raw_offset = f.get("offset")
    raw_skip = f.get("skip")
    ftype = f.get("type")
    raw_endian = f.get("endian")

    # Validate endian if present
    field_endian: str | None = None
    if raw_endian is not None:
        try:
            field_endian = normalize_endian(raw_endian)
        except ValueError as e:
            errors.append(f"{ctx}.endian: {e}")
            return None

    # Validate and normalize color if present
    raw_color = f.get("color")
    field_color: str | None = None
    if raw_color is not None:
        normalized, color_err = normalize_color(raw_color)
        if color_err:
            errors.append(f"{ctx}.color: {color_err}")
            return None
        field_color = normalized

    if not isinstance(name, str) or not name:
        errors.append(f"{ctx}.name is required")
        return None
    # Parse offset / skip (mutually exclusive, optional)
    if raw_offset is not None and raw_skip is not None:
        errors.append(f"{ctx} cannot specify both offset and skip")
        return None
    def _as_int(v: Any) -> int | None:
        if v is None:
            return None
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            try:
                return int(v, 0)
            except Exception:
                return None
        return None
    offset = _as_int(raw_offset)
    skip = _as_int(raw_skip)
    if raw_offset is not None and (offset is None or offset < 0):
        errors.append(f"{ctx}.offset must be a non-negative integer")
        return None
    if raw_skip is not None and (skip is None or skip < 0):
        errors.append(f"{ctx}.skip must be a non-negative integer")
        return None
    if not isinstance(ftype, str):
        errors.append(f"{ctx}.type is required")
        return None
    # Shorthand: type: "array of <TypeName>"
    m = re.fullmatch(r"array of ([A-Za-z0-9_]+)", ftype)
    if m:
        if "element" in f:
            errors.append(f"{ctx}: array-of shorthand cannot also specify 'element'")
            return None
        # Rewrite to canonical array form
        ftype = "array"
        f = dict(f)  # shallow copy
        f["type"] = "array"
        f["element"] = {"type": m.group(1)}
    if ftype in (*NUM_SIZES.keys(), "bytes", "string"):
        # Extract format field if present
        fmt = f.get("format")
        if fmt is not None and not isinstance(fmt, str):
            errors.append(f"{ctx}.format must be a string")
            fmt = None

        prim = Primitive(type=ftype, endian=field_endian, format=fmt, color=field_color)
        if ftype == "bytes":
            raw_len = f.get("length")
            # Support legacy length_from key
            length_from = f.get("length_from")
            if length_from is not None and isinstance(length_from, str):
                ln_ref = length_from
                ln = None
                err = None
            else:
                ln, ln_ref, err = _parse_length_value(raw_len)
            if err:
                errors.append(f"{ctx}.length: {err}")
                return None
            # Allow either static length or dynamic length_ref
            # Skip validation for chunk payloads (length determined by chunk)
            if not is_chunk_payload and ln is None and not ln_ref:
                errors.append(f"{ctx}.length required for bytes (int or ref)")
                return None
            if not is_chunk_payload and ln is not None and ln <= 0:
                errors.append(f"{ctx}.length must be > 0 for bytes")
                return None
            prim = Primitive(
                type=ftype,
                length=ln,
                length_ref=ln_ref,
                endian=field_endian,
                format=fmt,
                color=field_color,
            )
        elif ftype == "string":
            encoding = f.get("encoding", "ascii")
            if encoding not in ("ascii", "utf-8", "utf-16le", "utf-16be"):
                errors.append(f"{ctx}.encoding unsupported: {encoding}")
                return None
            if f.get("null_terminated"):
                max_len = f.get("max_length")
                if not isinstance(max_len, int) or max_len <= 0:
                    errors.append(f"{ctx}.max_length required and must be > 0 when null_terminated")
                    return None
                prim = Primitive(
                    type=ftype,
                    encoding=encoding,
                    null_terminated=True,
                    max_length=max_len,
                    endian=field_endian,
                    format=fmt,
                    color=field_color,
                )
            else:
                raw_len = f.get("length")
                # Support legacy length_from key
                length_from = f.get("length_from")
                if length_from is not None and isinstance(length_from, str):
                    ln_ref = length_from
                    ln = None
                    err = None
                else:
                    ln, ln_ref, err = _parse_length_value(raw_len)
                if err:
                    errors.append(f"{ctx}.length: {err}")
                    return None
                if ln is None and not ln_ref:
                    errors.append(f"{ctx}.length required for string (int or ref)")
                    return None
                prim = Primitive(
                    type=ftype,
                    encoding=encoding,
                    length=ln,
                    length_ref=ln_ref,
                    endian=field_endian,
                    format=fmt,
                    color=field_color,
                )
        return Node(
            name=name,
            offset=offset,
            skip=skip,
            kind="primitive",
            prim=prim,
            color=field_color,
        )
    if ftype == "struct":
        sub_fields = f.get("fields")
        if not isinstance(sub_fields, list) or not sub_fields:
            errors.append(f"{ctx}.fields must be a non-empty list for struct")
            return None
        nodes: list[Node] = []
        # Track field names as we parse for length_ref validation
        parsed_field_names: set[str] = set()
        for j, sf in enumerate(sub_fields):
            if not isinstance(sf, dict):
                errors.append(f"{ctx}.fields[{j}] must be a mapping")
                continue
            child = _parse_node(sf, f"{ctx}.fields[{j}]", errors, resolve_type, stack)
            if child is not None:
                nodes.append(child)
                # Validate length_ref references if present
                if child.kind == "primitive" and child.prim and child.prim.length_ref:
                    ref = child.prim.length_ref
                    if ref not in parsed_field_names:
                        errors.append(
                            f"{ctx}.fields[{j}]: length_ref '{ref}' references "
                            f"unknown or later field in struct"
                        )
                # Add this field's name to the set
                parsed_field_names.add(child.name)
        return Node(
            name=name,
            offset=offset,
            skip=skip,
            kind="struct",
            fields=nodes,
            endian=field_endian,
            color=field_color,
        )
    if ftype == "array":
        raw_len = f.get("length")
        ln, ln_ref, err = _parse_length_value(raw_len)
        length_from = f.get("length_from")  # legacy
        if ln is None and not ln_ref and not length_from:
            errors.append(f"{ctx} requires length")
            return None
        layout = f.get("layout")
        if layout == "soa":
            sub_fields = f.get("fields")
            if not isinstance(sub_fields, list) or not sub_fields:
                errors.append(f"{ctx}.fields must be a non-empty list for layout: soa")
                return None
            children: list[Node] = []
            for j, sf in enumerate(sub_fields):
                if not isinstance(sf, dict):
                    errors.append(f"{ctx}.fields[{j}] must be a mapping")
                    continue
                if sf.get("offset") is not None or sf.get("skip") is not None:
                    errors.append(f"{ctx}.fields[{j}]: offset/skip not allowed for layout: soa")
                    continue
                child = _parse_node(
                    {**sf, "name": sf.get("name") or f"f{j}"},
                    f"{ctx}.fields[{j}]",
                    errors,
                    resolve_type,
                    stack,
                )
                if child is None:
                    continue
                # Must be fixed-size primitive
                if child.kind != "primitive" or child.prim is None:
                    errors.append(
                        f"{ctx}.fields[{j}] must be a fixed-size primitive for layout: soa"
                    )
                    continue
                p = child.prim
                if p.type == "string":
                    if p.null_terminated:
                        errors.append(
                            f"{ctx}.fields[{j}] string cannot be null_terminated for layout: soa"
                        )
                        continue
                    if p.length is None and p.length_ref is None:
                        errors.append(
                            f"{ctx}.fields[{j}] string requires fixed length for layout: soa"
                        )
                        continue
                    if p.length is None:
                        errors.append(
                            f"{ctx}.fields[{j}] string length ref not supported for layout: soa"
                        )
                        continue
                if p.type == "bytes" and (p.length is None or p.length <= 0):
                    errors.append(
                        f"{ctx}.fields[{j}] bytes requires positive length for layout: soa"
                    )
                    continue
                # numeric types ok by size table
                children.append(child)
            if not children:
                return None
            return Node(
                name=name,
                offset=offset,
                skip=skip,
                kind="soa",
                fields=children,
                array_length=ln,
                array_length_ref=ln_ref or (length_from if isinstance(length_from, str) else None),
                endian=field_endian,
                color=field_color,
            )
        element = f.get("element")
        if not isinstance(element, dict):
            errors.append(f"{ctx}.element must be a mapping")
            return None
        stride = f.get("stride")
        if stride is not None and (not isinstance(stride, int) or stride <= 0):
            errors.append(f"{ctx}.stride must be > 0 if provided")
            return None
        el = _parse_node(
            {**element, "name": f"{name}.elem", "offset": 0},
            f"{ctx}.element",
            errors,
            resolve_type,
            stack,
        )
        if el is None:
            return None
        return Node(
            name=name,
            offset=offset,
            skip=skip,
            kind="array",
            array_length=ln,
            array_length_ref=ln_ref or (length_from if isinstance(length_from, str) else None),
            element=el,
            stride=stride,
            endian=field_endian,
            color=field_color,
        )
    if ftype == "chunk":
        # Parse chunk field: length_type, length_includes_header, payload
        length_type = f.get("length_type")
        if not isinstance(length_type, str):
            errors.append(f"{ctx}.length_type required for chunk")
            return None
        # Validate length_type format
        valid_length_types = {
            "u8",
            "u16 LE",
            "u16 BE",
            "u32 LE",
            "u32 BE",
        }
        if length_type not in valid_length_types:
            errors.append(
                f"{ctx}.length_type must be one of: {', '.join(sorted(valid_length_types))}"
            )
            return None
        length_includes_header = bool(f.get("length_includes_header", False))
        # Parse payload spec (default to bytes)
        payload_spec = f.get("payload")
        if payload_spec is None:
            payload_spec = {"type": "bytes"}
        if not isinstance(payload_spec, dict):
            errors.append(f"{ctx}.payload must be a mapping")
            return None
        # Parse payload node (pass is_chunk_payload=True to skip bytes length validation)
        payload_node = _parse_node(
            {**payload_spec, "name": f"{name}.payload", "offset": 0},
            f"{ctx}.payload",
            errors,
            resolve_type,
            stack,
            is_chunk_payload=True,
        )
        if payload_node is None:
            return None
        return Node(
            name=name,
            offset=offset,
            skip=skip,
            kind="chunk",
            length_type=length_type,
            length_includes_header=length_includes_header,
            payload=payload_node,
            endian=field_endian,
            color=field_color,
        )
    # Alias reference: expand by merging call-site overrides into alias spec
    alias_spec = resolve_type(ftype, stack)
    if alias_spec is None:
        errors.append(f"{ctx}: unknown type reference: {ftype}")
        return None
    if not isinstance(alias_spec, dict) or "type" not in alias_spec:
        errors.append(f"{ctx}: invalid alias spec for {ftype}")
        return None
    # Build merged spec
    merged: dict[str, Any] = deepcopy(alias_spec)
    # Apply call-site overrides excluding type/name/offset/skip
    for k, v in f.items():
        if k in ("type", "name", "offset", "skip"):
            continue
        merged[k] = v
    merged["name"] = name
    merged["offset"] = offset
    merged["skip"] = skip
    # Parse the expanded spec
    return _parse_node(merged, ctx + ".expanded", errors, resolve_type, stack + [ftype])


def _parse_length_value(raw: Any) -> tuple[int | None, str | None, str | None]:
    """Parse a length value which may be int, numeric string, or reference.

    Returns (int_value, ref_path, error_message)
    """
    if raw is None:
        return None, None, None
    if isinstance(raw, int):
        return raw, None, None
    if isinstance(raw, str):
        s = raw.strip()
        # Numeric string? support hex
        try:
            base = 16 if s.lower().startswith("0x") else 10
            val = int(s, base)
            return val, None, None
        except Exception:
            return None, s, None
    if isinstance(raw, dict) and "ref" in raw:
        ref = raw.get("ref")
        if isinstance(ref, str) and ref:
            return None, ref, None
        return None, None, "invalid ref mapping"
    return None, None, "invalid length value"
