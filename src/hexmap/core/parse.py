from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from hexmap.core.endian import Endian, resolve_endian
from hexmap.core.io import PagedReader
from hexmap.core.schema import Node, Primitive, Schema

# Safety caps for dynamic lengths
MAX_ARRAY_ITEMS_DEFAULT = 10_000
MAX_STRING_BYTES_DEFAULT = 1_000_000


def _format_date_value(value: Any, fmt: str | None) -> str | None:
    """Format a numeric value as a date string based on format specifier."""
    if fmt is None or value is None:
        return None
    try:
        if fmt == "unix_s" and isinstance(value, int):
            dt = datetime(1970, 1, 1) + timedelta(seconds=value)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        elif fmt == "unix_ms" and isinstance(value, int):
            dt = datetime(1970, 1, 1) + timedelta(milliseconds=value)
            return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        elif fmt == "filetime" and isinstance(value, int):
            dt = datetime(1601, 1, 1) + timedelta(microseconds=value / 10)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        elif fmt == "dos_date" and isinstance(value, int):
            day = value & 0x1F
            month = (value >> 5) & 0x0F
            year = 1980 + ((value >> 9) & 0x7F)
            if month == 0 or month > 12 or day == 0 or day > 31:
                return f"[invalid: 0x{value:04X}]"
            return f"{year:04d}-{month:02d}-{day:02d}"
        elif fmt == "dos_datetime" and isinstance(value, bytes) and len(value) >= 4:
            time_val = struct.unpack("<H", value[:2])[0]
            date_val = struct.unpack("<H", value[2:4])[0]
            sec = (time_val & 0x1F) * 2
            minute = (time_val >> 5) & 0x3F
            hour = (time_val >> 11) & 0x1F
            day = date_val & 0x1F
            month = (date_val >> 5) & 0x0F
            year = 1980 + ((date_val >> 9) & 0x7F)
            if month == 0 or month > 12 or day == 0 or day > 31:
                return f"[invalid date: 0x{date_val:04X}]"
            return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{sec:02d}"
        elif fmt == "ole_date" and isinstance(value, float):
            dt = datetime(1899, 12, 30) + timedelta(days=value)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        elif fmt == "ftm_packed" and isinstance(value, (int, bytes)):
            if isinstance(value, bytes):
                if len(value) < 4:
                    return None
                val = struct.unpack("<I", value[:4])[0]
            else:
                val = value
            year = (val >> 20) & 0xFFF
            month = (val >> 16) & 0x0F
            day = (val >> 11) & 0x1F
            hour = (val >> 6) & 0x1F
            minute = val & 0x3F
            if year == 0 or month == 0 or month > 12 or day == 0 or day > 31:
                return f"[invalid: 0x{val:08X}]"
            return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}"
    except Exception:
        return "[error]"
    return None


@dataclass(frozen=True)
class ParsedField:
    name: str
    offset: int
    length: int
    type: str
    value: object | None
    error: str | None = None
    effective_endian: str | None = None  # effective endianness used
    endian_source: str | None = None  # where endian came from
    format: str | None = None  # date/time format
    formatted_value: str | None = None  # formatted display string (for dates)
    color_override: str | None = None  # normalized color (named or #rrggbb)


def apply_schema(reader: PagedReader, schema: Schema) -> list[ParsedField]:
    # Back-compat: flatten leaf nodes only
    tree, leaves, _ = apply_schema_tree(reader, schema)
    return leaves


@dataclass(frozen=True)
class ParsedNode:
    path: str
    offset: int
    length: int | None
    type: str
    value: Any | None
    error: str | None
    children: list[ParsedNode] | None = None
    effective_endian: str | None = None  # effective endianness used
    endian_source: str | None = None  # where endian came from
    format: str | None = None  # date/time format
    formatted_value: str | None = None  # formatted display string (for dates)
    color_override: str | None = None  # normalized color (named or #rrggbb)


def apply_schema_tree(
    reader: PagedReader, schema: Schema
) -> tuple[list[ParsedNode], list[ParsedField], list[str]]:
    errors: list[str] = []
    values_by_path: dict[str, Any] = {}
    tree: list[ParsedNode] = []
    leaves: list[ParsedField] = []

    def prim_size(prim: Primitive) -> int | None:
        return prim.size()

    def infer_stride(el: Node) -> int | None:
        if el.kind == "primitive" and el.prim is not None:
            return prim_size(el.prim)
        if el.kind == "struct" and el.fields:
            # Simulate sequential layout within struct starting at 0
            cursor = 0
            for ch in el.fields:
                if ch.kind == "array":
                    return None
                # determine child size
                if ch.kind == "primitive" and ch.prim is not None:
                    sz = prim_size(ch.prim)
                elif ch.kind == "struct":
                    sz = infer_stride(ch)
                else:
                    return None
                if sz is None:
                    return None
                start = ch.offset if ch.offset is not None else cursor + (ch.skip or 0)
                cursor = start + sz
            return cursor
        return None

    def read_primitive(
        off: int, prim: Primitive, effective_endian: Endian, current_path: str
    ) -> tuple[Any | None, str | None, int]:
        # returns value, error, size
        # current_path is the full path to the current field being parsed
        sz = prim_size(prim) or 0

        def resolve_ref(ref_name: str) -> int | None:
            """Resolve a length_ref by looking in current struct scope."""
            # First try direct lookup (for top-level fields)
            ref_val = values_by_path.get(ref_name)
            if isinstance(ref_val, int) and ref_val >= 0:
                return ref_val

            # Try sibling reference (same struct scope)
            # e.g., if current_path is "my_record.field_payload"
            # and ref_name is "field_size"
            # then try "my_record.field_size"
            if "." in current_path:
                parent_path = current_path.rsplit(".", 1)[0]
                full_ref = f"{parent_path}.{ref_name}"
                ref_val = values_by_path.get(full_ref)
                if isinstance(ref_val, int) and ref_val >= 0:
                    return ref_val

            return None

        if prim.type == "string":
            # handle null-terminated with max_length
            if prim.null_terminated:
                max_len = prim.max_length or 0
                sz = max_len
                data = reader.read(off, sz)
                nul = data.find(b"\x00")
                if nul != -1:
                    data = data[:nul]
            else:
                # dynamic/static string length
                length = prim.length
                if length is None and getattr(prim, "length_ref", None):
                    ref_name = prim.length_ref
                    length = resolve_ref(ref_name)
                    if length is None:
                        return None, f"invalid string length ref: {ref_name}", 0
                if length is None or length < 0:
                    return None, "missing string length", 0
                if length > MAX_STRING_BYTES_DEFAULT:
                    return None, "string length exceeds safety cap", 0
                sz = length
                data = reader.read(off, sz)
            try:
                enc = prim.encoding or "ascii"
                val = data.decode(enc, errors="replace")
                return val, None, sz
            except Exception:
                return "<decode error>", None, sz
        elif prim.type == "bytes":
            # Handle dynamic length for bytes
            length = prim.length
            if length is None and getattr(prim, "length_ref", None):
                ref_name = prim.length_ref
                length = resolve_ref(ref_name)
                if length is None:
                    return None, f"invalid bytes length ref: {ref_name}", 0
            if length is None or length < 0:
                return None, "missing bytes length", 0
            sz = length
            if off + sz > reader.size:
                return None, "field extends past EOF", sz
            data = reader.read(off, sz)
            return data, None, sz
        else:
            # numeric types
            if off + sz > reader.size:
                return None, "field extends past EOF", sz
            data = reader.read(off, sz)
            signed = prim.type.startswith("i")
            val = int.from_bytes(data, effective_endian, signed=signed)
            return val, None, sz

    def parse_node(
        base: int,
        node: Node,
        path: str,
        parent_endian: Endian | None,
        parent_color: str | None = None,
    ) -> tuple[ParsedNode, int]:
        # Returns parsed node and its size for layout
        abs_off = base

        # Resolve effective endian for this node
        # For primitives: field_endian comes from prim.endian,
        # type_endian is None (no separate type)
        # For structs/arrays: field_endian comes from node.endian
        field_endian = node.prim.endian if node.prim else node.endian
        type_endian = None  # Type-level endian is already merged into field_endian by schema parser
        root_endian = schema.endian
        effective_endian, endian_source = resolve_endian(
            field_endian, type_endian, parent_endian, root_endian
        )

        # Resolve effective color with inheritance
        # Priority: node color (field/primitive) > node color (struct level) > parent color
        field_color = (node.prim.color if node.prim else None) or node.color
        effective_color = field_color or parent_color

        if node.kind == "primitive" and node.prim is not None:
            # Resolve and read value; dynamic string lengths resolved here
            val, err, used = read_primitive(abs_off, node.prim, effective_endian, path)
            sz = used or (node.prim.size() or 0)

            # Format date if format is specified
            fmt = node.prim.format
            formatted = _format_date_value(val, fmt) if fmt else None

            pn = ParsedNode(
                path,
                abs_off,
                sz,
                node.prim.type,
                val,
                err,
                effective_endian=effective_endian,
                endian_source=endian_source,
                format=fmt,
                formatted_value=formatted,
                color_override=effective_color,
            )
            leaves.append(
                ParsedField(
                    path,
                    abs_off,
                    sz,
                    node.prim.type,
                    pn.value,
                    pn.error,
                    effective_endian=effective_endian,
                    endian_source=endian_source,
                    format=fmt,
                    formatted_value=formatted,
                    color_override=effective_color,
                )
            )
            values_by_path[path] = pn.value
            return pn, sz
        if node.kind == "struct" and node.fields is not None:
            kids: list[ParsedNode] = []
            # layout cursor within struct
            cursor = abs_off
            for ch in node.fields:
                cpath = f"{path}.{ch.name}" if path else ch.name
                # Resolve child's start
                if ch.offset is not None:
                    child_abs = abs_off + ch.offset
                else:
                    gap = ch.skip or 0
                    child_abs = cursor + gap
                # Parse child with base = child_abs
                parsed_child, child_size = parse_node(
                    child_abs, ch, cpath, effective_endian, effective_color
                )
                kids.append(parsed_child)
                cursor = child_abs + (child_size or 0)
            struct_size = cursor - abs_off
            pn_struct = ParsedNode(
                path,
                abs_off,
                struct_size,
                "struct",
                None,
                None,
                children=kids,
                effective_endian=effective_endian,
                endian_source=endian_source,
                color_override=effective_color,
            )
            return pn_struct, struct_size
        if node.kind == "soa" and node.fields is not None:
            # Struct-of-Arrays: parse columns sequentially, materialize records
            # Resolve length
            count = node.array_length
            if count is None and getattr(node, "array_length_ref", None):
                ref_path = node.array_length_ref
                count_val = values_by_path.get(ref_path)
                if isinstance(count_val, int) and count_val >= 0:
                    count = count_val
                else:
                    errors.append(
                        f"array length ref unresolved or not integer: {ref_path}"
                    )
                    return (
                        ParsedNode(
                            path,
                            abs_off,
                            None,
                            "array",
                            None,
                            "length ref unresolved",
                            effective_endian=effective_endian,
                            endian_source=endian_source,
                        ),
                        0,
                    )
            if count is None or count < 0:
                errors.append(f"array length invalid for {path}")
                return (
                    ParsedNode(
                        path,
                        abs_off,
                        None,
                        "array",
                        None,
                        "invalid length",
                        effective_endian=effective_endian,
                        endian_source=endian_source,
                    ),
                    0,
                )
            # Pre-parse columns
            col_nodes: list[Node] = node.fields
            # initialize per-record children
            records: list[list[ParsedNode]] = [[] for _ in range(count)]
            cursor = abs_off
            total_size = 0
            # For coverage / leaves, we record leaf spans as we go
            for col in col_nodes:
                if col.prim is None:
                    # should be validated earlier
                    return (
                        ParsedNode(
                            path,
                            abs_off,
                            None,
                            "array",
                            None,
                            "invalid soa field",
                            effective_endian=effective_endian,
                            endian_source=endian_source,
                        ),
                        0,
                    )

                # Resolve endian for this column (field within SOA)
                col_field_endian = col.prim.endian
                col_effective_endian, col_endian_source = resolve_endian(
                    col_field_endian, None, effective_endian, root_endian
                )

                # Determine element size
                el_size = 0
                sz = prim_size(col.prim)
                if sz is None or sz <= 0:
                    errors.append(f"cannot determine fixed size for {path}.{col.name}")
                    return (
                        ParsedNode(
                            path,
                            abs_off,
                            None,
                            "array",
                            None,
                            "invalid field size",
                            effective_endian=effective_endian,
                            endian_source=endian_source,
                        ),
                        0,
                    )
                el_size = sz
                # Parse N elements sequentially
                for i in range(count):
                    off_i = cursor + i * el_size
                    leaf_path = f"{path}[{i}].{col.name}"
                    val, err, used = read_primitive(
                        off_i, col.prim, col_effective_endian, leaf_path
                    )
                    leaf = ParsedNode(
                        f"{path}[{i}].{col.name}",
                        off_i,
                        used,
                        col.prim.type,
                        val,
                        err,
                        children=None,
                        effective_endian=col_effective_endian,
                        endian_source=col_endian_source,
                    )
                    records[i].append(leaf)
                    leaves.append(
                        ParsedField(
                            leaf.path,
                            leaf.offset,
                            leaf.length or 0,
                            leaf.type,
                            leaf.value,
                            leaf.error,
                            effective_endian=col_effective_endian,
                            endian_source=col_endian_source,
                        )
                    )
                # advance cursor by the column size
                consumed = count * el_size
                cursor += consumed
                total_size += consumed
            # Build per-record struct nodes
            items: list[ParsedNode] = []
            for i in range(count):
                rec_children = records[i]
                # aggregate length as sum of child lengths
                agg_len = sum(ch.length or 0 for ch in rec_children)
                # offset choose min child offset for display
                rec_off = min((ch.offset for ch in rec_children), default=abs_off)
                items.append(
                    ParsedNode(
                        f"{path}[{i}]",
                        rec_off,
                        agg_len,
                        "struct",
                        None,
                        None,
                        children=rec_children,
                        effective_endian=effective_endian,
                        endian_source=endian_source,
                    )
                )
            return (
                ParsedNode(
                    path,
                    abs_off,
                    total_size,
                    "array",
                    None,
                    None,
                    children=items,
                    effective_endian=effective_endian,
                    endian_source=endian_source,
                ),
                total_size,
            )
        if node.kind == "array" and node.element is not None:
            # resolve length
            count = node.array_length
            if count is None and getattr(node, "array_length_ref", None):
                ref_path = node.array_length_ref
                count_val = values_by_path.get(ref_path)
                if isinstance(count_val, int) and count_val >= 0:
                    count = count_val
                else:
                    errors.append(
                        f"array length ref unresolved or not integer: {ref_path}"
                    )
                    pn_err = ParsedNode(
                        path,
                        abs_off,
                        None,
                        "array",
                        None,
                        "length ref unresolved",
                        effective_endian=effective_endian,
                        endian_source=endian_source,
                    )
                    return pn_err, 0
            if count is None or count < 0:
                errors.append(f"array length invalid for {path}")
                return (
                    ParsedNode(
                        path,
                        abs_off,
                        None,
                        "array",
                        None,
                        "invalid length",
                        effective_endian=effective_endian,
                        endian_source=endian_source,
                    ),
                    0,
                )
            if count > MAX_ARRAY_ITEMS_DEFAULT:
                errors.append(f"array length exceeds safety cap for {path}")
                return (
                    ParsedNode(
                        path,
                        abs_off,
                        None,
                        "array",
                        None,
                        "length too large",
                        effective_endian=effective_endian,
                        endian_source=endian_source,
                    ),
                    0,
                )
            stride = node.stride or infer_stride(node.element)
            if stride is None or stride <= 0:
                errors.append(f"cannot infer stride for {path}")
                return (
                    ParsedNode(
                        path,
                        abs_off,
                        None,
                        "array",
                        None,
                        "stride inference error",
                        effective_endian=effective_endian,
                        endian_source=endian_source,
                    ),
                    0,
                )
            items: list[ParsedNode] = []
            for i in range(count):
                ipath = f"{path}[{i}]"
                item_parsed, _ = parse_node(
                    abs_off + i * stride, node.element, ipath, effective_endian, effective_color
                )
                items.append(item_parsed)
            return (
                ParsedNode(
                    path,
                    abs_off,
                    count * stride,
                    "array",
                    None,
                    None,
                    children=items,
                    effective_endian=effective_endian,
                    endian_source=endian_source,
                    color_override=effective_color,
                ),
                count * stride,
            )
        if node.kind == "chunk":
            # Parse chunk: read length field, compute payload span, parse payload
            if node.length_type is None or node.payload is None:
                return (
                    ParsedNode(
                        path,
                        abs_off,
                        None,
                        "chunk",
                        None,
                        "invalid chunk spec",
                        effective_endian=effective_endian,
                        endian_source=endian_source,
                    ),
                    0,
                )
            # Map length_type to size and endian
            length_type = node.length_type
            length_size_map = {
                "u8": (1, "little"),
                "u16 LE": (2, "little"),
                "u16 BE": (2, "big"),
                "u32 LE": (4, "little"),
                "u32 BE": (4, "big"),
            }
            if length_type not in length_size_map:
                return (
                    ParsedNode(
                        path,
                        abs_off,
                        None,
                        "chunk",
                        None,
                        f"invalid length_type: {length_type}",
                        effective_endian=effective_endian,
                        endian_source=endian_source,
                    ),
                    0,
                )
            len_size, len_endian = length_size_map[length_type]
            # Read length field
            len_data = reader.read(abs_off, len_size)
            if len(len_data) < len_size:
                return (
                    ParsedNode(
                        path,
                        abs_off,
                        None,
                        "chunk",
                        None,
                        "cannot read length field",
                        effective_endian=effective_endian,
                        endian_source=endian_source,
                    ),
                    0,
                )
            declared_len = int.from_bytes(len_data, len_endian, signed=False)
            # Compute payload length
            if node.length_includes_header:
                payload_len = max(0, declared_len - len_size)
            else:
                payload_len = declared_len
            # Compute payload span and cap at EOF
            payload_start = abs_off + len_size
            file_size = reader.size
            capped_at_eof = False
            if payload_start + payload_len > file_size:
                payload_len = max(0, file_size - payload_start)
                capped_at_eof = True
            # Create length field node
            len_node = ParsedNode(
                f"{path}.length",
                abs_off,
                len_size,
                length_type,
                declared_len,
                None,
                effective_endian=len_endian,
                endian_source="chunk length_type",
            )
            leaves.append(
                ParsedField(
                    len_node.path,
                    len_node.offset,
                    len_node.length or 0,
                    len_node.type,
                    len_node.value,
                    len_node.error,
                    effective_endian=len_endian,
                    endian_source="chunk length_type",
                )
            )
            # Parse payload
            payload_node_spec = node.payload
            # If payload is just bytes, create a simple bytes node
            if payload_node_spec.kind == "primitive" and payload_node_spec.prim:
                if payload_node_spec.prim.type == "bytes":
                    # Read payload bytes
                    payload_data = reader.read(payload_start, payload_len)
                    payload_node = ParsedNode(
                        f"{path}.payload",
                        payload_start,
                        payload_len,
                        "bytes",
                        payload_data,
                        "truncated at EOF" if capped_at_eof else None,
                        effective_endian=effective_endian,
                        endian_source=endian_source,
                    )
                    leaves.append(
                        ParsedField(
                            payload_node.path,
                            payload_node.offset,
                            payload_node.length or 0,
                            payload_node.type,
                            payload_node.value,
                            payload_node.error,
                            effective_endian=effective_endian,
                            endian_source=endian_source,
                        )
                    )
                else:
                    # For other primitives, parse normally
                    payload_node, _ = parse_node(
                        payload_start,
                        payload_node_spec,
                        f"{path}.payload",
                        effective_endian,
                        effective_color,
                    )
            else:
                # For struct or other complex types
                payload_node, _ = parse_node(
                    payload_start,
                    payload_node_spec,
                    f"{path}.payload",
                    effective_endian,
                    effective_color,
                )
            # Create chunk node with length and payload as children
            chunk_node = ParsedNode(
                path,
                abs_off,
                len_size + payload_len,
                "chunk",
                None,
                None,
                children=[len_node, payload_node],
                effective_endian=effective_endian,
                endian_source=endian_source,
                color_override=effective_color,
            )
            return chunk_node, len_size + payload_len
        return (
            ParsedNode(
                path,
                abs_off,
                None,
                node.kind,
                None,
                "unsupported node",
                effective_endian=effective_endian,
                endian_source=endian_source,
                color_override=None,
            ),
            0,
        )

    # Build tree
    # Layout at top level
    base = 0
    cursor = base
    for n in schema.fields:
        path = n.name
        start = base + n.offset if n.offset is not None else cursor + (n.skip or 0)
        # No parent endian/color for top-level fields
        pn, size = parse_node(start, n, path, None, None)
        tree.append(pn)
        # If size is unknown (0) and we need sequential layout, emit error
        if n.offset is None and size == 0:
            errors.append(f"cannot determine size for {path} to continue sequential layout")
        cursor = start + size

    # Overlap detection on expanded leaves
    spans = [(pf.offset, pf.offset + pf.length, pf.name) for pf in leaves]
    spans.sort(key=lambda s: s[0])
    for i in range(1, len(spans)):
        a = spans[i - 1]
        b = spans[i]
        if b[0] < a[1]:
            errors.append(f"Overlap: {a[2]} and {b[2]}")

    return tree, leaves, errors
