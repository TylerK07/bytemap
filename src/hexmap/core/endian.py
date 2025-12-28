"""Endianness support for hexmap: types, resolution, and decoding."""

from __future__ import annotations

import struct
from typing import Literal

# Type alias for endianness
Endian = Literal["little", "big"]

# Source of endianness for debugging/UI
EndianSource = Literal["field", "type", "parent", "root", "default"]


def normalize_endian(value: str | None) -> Endian | None:
    """Normalize an endian value from schema.

    Args:
        value: String value from YAML (or None)

    Returns:
        Normalized Endian value, or None if input was None

    Raises:
        ValueError: If value is not 'little' or 'big'
    """
    if value is None:
        return None

    value_lower = value.lower()
    if value_lower not in ("little", "big"):
        raise ValueError(f"Invalid endian '{value}'. Expected 'little' or 'big'.")

    return value_lower  # type: ignore[return-value]


def resolve_endian(
    field_endian: Endian | None,
    type_endian: Endian | None,
    parent_endian: Endian | None,
    root_endian: Endian | None,
) -> tuple[Endian, EndianSource]:
    """Resolve effective endianness using hierarchical rules.

    Resolution order (highest priority first):
    1. field_endian (field-level override)
    2. type_endian (type definition)
    3. parent_endian (parent struct/container)
    4. root_endian (schema root)
    5. default fallback: "little"

    Args:
        field_endian: Endian specified on the field itself
        type_endian: Endian specified on the type definition
        parent_endian: Endian from parent context (struct/container)
        root_endian: Endian from schema root

    Returns:
        Tuple of (effective_endian, source)
    """
    if field_endian is not None:
        return field_endian, "field"
    if type_endian is not None:
        return type_endian, "type"
    if parent_endian is not None:
        return parent_endian, "parent"
    if root_endian is not None:
        return root_endian, "root"
    return "little", "default"


def decode_int(data: bytes, endian: Endian, signed: bool) -> int:
    """Decode integer from bytes with specified endianness.

    Args:
        data: Bytes to decode
        endian: Byte order ('little' or 'big')
        signed: Whether the integer is signed

    Returns:
        Decoded integer value
    """
    return int.from_bytes(data, byteorder=endian, signed=signed)


def decode_float32(data: bytes, endian: Endian) -> float:
    """Decode 32-bit float from bytes with specified endianness.

    Args:
        data: 4 bytes to decode
        endian: Byte order ('little' or 'big')

    Returns:
        Decoded float value
    """
    format_char = "<f" if endian == "little" else ">f"
    return struct.unpack(format_char, data)[0]


def decode_float64(data: bytes, endian: Endian) -> float:
    """Decode 64-bit float (double) from bytes with specified endianness.

    Args:
        data: 8 bytes to decode
        endian: Byte order ('little' or 'big')

    Returns:
        Decoded double value
    """
    format_char = "<d" if endian == "little" else ">d"
    return struct.unpack(format_char, data)[0]


def decode_primitive(data: bytes, type_name: str, endian: Endian) -> int | float:
    """Decode a primitive numeric value.

    Args:
        data: Bytes to decode
        type_name: Type name (u8, u16, u32, i8, i16, i32, f32, f64, etc.)
        endian: Byte order

    Returns:
        Decoded numeric value

    Raises:
        ValueError: If type_name is not a supported numeric type
    """
    # Integer types
    if type_name in ("u8", "u16", "u32", "u64"):
        return decode_int(data, endian, signed=False)
    if type_name in ("i8", "i16", "i32", "i64"):
        return decode_int(data, endian, signed=True)

    # Float types
    if type_name == "f32":
        return decode_float32(data, endian)
    if type_name == "f64":
        return decode_float64(data, endian)

    raise ValueError(f"Unsupported numeric type: {type_name}")
