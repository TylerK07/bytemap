"""Core data structures and logic for chunk stream analysis."""

from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from hexmap.core.io import PagedReader


class LengthSemantics(Enum):
    """How to interpret the length field."""

    PAYLOAD_ONLY = "payload_only"
    INCLUDES_HEADER = "includes_header"


class TypeNormalization(Enum):
    """How to normalize type bytes for grouping."""

    RAW = "raw"  # Use raw bytes as-is
    UINT_BE = "uint_be"  # Interpret as big-endian unsigned int
    UINT_LE = "uint_le"  # Interpret as little-endian unsigned int
    ASCII = "ascii"  # Interpret as ASCII string (if printable)


class DecoderStatus(Enum):
    """Status of type registry entry."""

    UNKNOWN = "unknown"
    TENTATIVE = "tentative"
    CONFIRMED = "confirmed"


@dataclass(frozen=True)
class FramingParams:
    """Parameters for parsing chunk streams."""

    type_width: int  # Bytes in type field
    length_width: int  # Bytes in length field
    length_endian: str  # "little" or "big"
    length_semantics: LengthSemantics
    max_payload_len: int | None = None  # Cap for sanity checking
    strict_eof: bool = True  # Error on trailing bytes vs allow
    type_normalization: TypeNormalization = TypeNormalization.RAW
    extra_header_bytes: int = 0  # Additional bytes after length field (flags, padding, etc.)


@dataclass(frozen=True)
class RecordSpan:
    """A single parsed record/chunk in a file."""

    file_id: str  # File path or identifier
    offset: int  # Start offset in file
    type_bytes: bytes  # Raw type field bytes
    type_key: str  # Normalized key for grouping
    length_value: int  # Value from length field
    payload_offset: int  # Start of payload
    payload_len: int  # Actual payload length
    suspicious: bool  # Exceeds limits or other issues
    payload_hash: str  # Quick hash for deduplication
    header_len: int  # Size of type + length fields

    @property
    def total_len(self) -> int:
        """Total record size including header and payload."""
        return self.header_len + self.payload_len

    def get_payload_preview(self, reader: PagedReader, max_bytes: int = 16) -> bytes:
        """Read payload preview bytes."""
        preview_len = min(max_bytes, self.payload_len)
        return reader.read(self.payload_offset, preview_len)


@dataclass
class TypeStats:
    """Statistics for a unique chunk type."""

    type_key: str
    type_bytes: bytes
    count: int = 0
    min_len: int | None = None
    max_len: int | None = None
    total_len: int = 0
    distinct_hashes: set[str] = field(default_factory=set)
    example_records: list[RecordSpan] = field(default_factory=list)

    @property
    def avg_len(self) -> float:
        """Average payload length."""
        return self.total_len / self.count if self.count > 0 else 0.0

    def update(self, record: RecordSpan) -> None:
        """Update stats with a new record."""
        self.count += 1
        self.total_len += record.payload_len
        self.distinct_hashes.add(record.payload_hash)

        if self.min_len is None or record.payload_len < self.min_len:
            self.min_len = record.payload_len
        if self.max_len is None or record.payload_len > self.max_len:
            self.max_len = record.payload_len

        # Keep diverse examples (first, shortest, longest, random sampling)
        if len(self.example_records) < 20:
            self.example_records.append(record)
        else:
            # Replace longest example if this is shorter
            longest_idx = max(
                range(len(self.example_records)),
                key=lambda i: self.example_records[i].payload_len,
            )
            if record.payload_len < self.example_records[longest_idx].payload_len:
                self.example_records[longest_idx] = record


@dataclass
class DecoderParams:
    """Parameters for a specific decoder type."""

    # Integer decoders
    int_width: int | None = None  # 1, 2, 4, 8
    int_endian: str | None = None  # "little" or "big"
    int_signed: bool = False

    # String decoders
    string_encoding: str = "ascii"  # "ascii", "utf-8", etc.
    string_null_terminated: bool = False
    string_strip_nulls: bool = True

    # Date decoders
    date_format: str | None = None  # "unix_s", "unix_ms", "filetime", etc.

    # Bitflags
    bitflags_width: int | None = None

    # Nested stream
    nested_framing: FramingParams | None = None


@dataclass
class TypeRegistryEntry:
    """Registry entry for a chunk type with decoder information."""

    key_bytes: bytes  # Raw type bytes (primary key)
    name: str  # User-assigned name
    decoder_id: str  # "none", "int", "string", "date", "bitflags", "nested"
    decoder_params: DecoderParams = field(default_factory=DecoderParams)
    notes: str = ""
    status: DecoderStatus = DecoderStatus.UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON persistence."""
        return {
            "key_bytes": self.key_bytes.hex(),
            "name": self.name,
            "decoder_id": self.decoder_id,
            "decoder_params": {
                k: v
                for k, v in self.decoder_params.__dict__.items()
                if v is not None
                and not (isinstance(v, FramingParams))  # Skip nested for now
            },
            "notes": self.notes,
            "status": self.status.value,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> TypeRegistryEntry:
        """Deserialize from dictionary."""
        params = DecoderParams(**data.get("decoder_params", {}))
        return TypeRegistryEntry(
            key_bytes=bytes.fromhex(data["key_bytes"]),
            name=data["name"],
            decoder_id=data["decoder_id"],
            decoder_params=params,
            notes=data.get("notes", ""),
            status=DecoderStatus(data.get("status", "unknown")),
        )


def normalize_type_key(
    type_bytes: bytes, normalization: TypeNormalization
) -> str:
    """Normalize type bytes to a canonical key string."""
    if normalization == TypeNormalization.RAW:
        return type_bytes.hex()

    elif normalization == TypeNormalization.UINT_BE:
        if len(type_bytes) <= 8:
            value = int.from_bytes(type_bytes, "big", signed=False)
            return f"u{len(type_bytes)*8}be:{value}"
        return type_bytes.hex()

    elif normalization == TypeNormalization.UINT_LE:
        if len(type_bytes) <= 8:
            value = int.from_bytes(type_bytes, "little", signed=False)
            return f"u{len(type_bytes)*8}le:{value}"
        return type_bytes.hex()

    elif normalization == TypeNormalization.ASCII:
        try:
            text = type_bytes.decode("ascii")
            if text.isprintable():
                return f"ascii:{text}"
        except UnicodeDecodeError:
            pass
        return type_bytes.hex()

    return type_bytes.hex()


def scan_chunks(
    reader: PagedReader, params: FramingParams, file_id: str | None = None
) -> tuple[list[RecordSpan], list[str]]:
    """
    Scan a file for chunk records using framing parameters.

    Returns:
        (records, errors) - List of successfully parsed records and error messages.
    """
    if file_id is None:
        file_id = str(reader.path) if hasattr(reader, "path") else "unknown"

    records: list[RecordSpan] = []
    errors: list[str] = []
    offset = 0
    file_size = reader.size

    header_size = params.type_width + params.length_width + params.extra_header_bytes

    while offset < file_size:
        # Check if we have enough bytes for header
        if offset + header_size > file_size:
            if params.strict_eof:
                errors.append(
                    f"Incomplete header at offset {offset:#x} "
                    f"(need {header_size}, have {file_size - offset})"
                )
            break

        # Read type field
        type_bytes = reader.read(offset, params.type_width)
        if len(type_bytes) != params.type_width:
            errors.append(f"Failed to read type at offset {offset:#x}")
            break

        # Read length field
        length_offset = offset + params.type_width
        length_bytes = reader.read(length_offset, params.length_width)
        if len(length_bytes) != params.length_width:
            errors.append(f"Failed to read length at offset {offset:#x}")
            break

        # Parse length value
        try:
            if params.length_endian == "big":
                length_value = int.from_bytes(length_bytes, "big", signed=False)
            else:
                length_value = int.from_bytes(length_bytes, "little", signed=False)
        except Exception as e:
            errors.append(f"Failed to parse length at offset {offset:#x}: {e}")
            break

        # Compute payload offset and length
        if params.length_semantics == LengthSemantics.PAYLOAD_ONLY:
            payload_offset = offset + header_size
            payload_len = length_value
        else:  # INCLUDES_HEADER
            payload_offset = offset + header_size
            payload_len = length_value - header_size
            if payload_len < 0:
                errors.append(
                    f"Invalid length at offset {offset:#x}: "
                    f"length_value={length_value} < header_size={header_size}"
                )
                break

        # Sanity checks
        suspicious = False
        if params.max_payload_len is not None and payload_len > params.max_payload_len:
            suspicious = True
            errors.append(
                f"Suspicious length at offset {offset:#x}: "
                f"{payload_len} exceeds max {params.max_payload_len}"
            )
            break

        if payload_offset + payload_len > file_size:
            suspicious = True
            errors.append(
                f"Payload extends beyond EOF at offset {offset:#x}: "
                f"need {payload_offset + payload_len}, have {file_size}"
            )
            break

        # Compute type key
        type_key = normalize_type_key(type_bytes, params.type_normalization)

        # Compute payload hash (first 32 bytes for speed)
        hash_sample_len = min(32, payload_len)
        if hash_sample_len > 0:
            hash_sample = reader.read(payload_offset, hash_sample_len)
            payload_hash = hashlib.md5(hash_sample).hexdigest()[:8]
        else:
            payload_hash = "empty"

        # Create record
        record = RecordSpan(
            file_id=file_id,
            offset=offset,
            type_bytes=type_bytes,
            type_key=type_key,
            length_value=length_value,
            payload_offset=payload_offset,
            payload_len=payload_len,
            suspicious=suspicious,
            payload_hash=payload_hash,
            header_len=header_size,
        )
        records.append(record)

        # Advance to next record
        offset = payload_offset + payload_len

    return records, errors


def build_type_stats(records: list[RecordSpan]) -> dict[str, TypeStats]:
    """Build statistics for each unique type from record list."""
    stats_map: dict[str, TypeStats] = {}

    for record in records:
        if record.type_key not in stats_map:
            stats_map[record.type_key] = TypeStats(
                type_key=record.type_key,
                type_bytes=record.type_bytes,
            )
        stats_map[record.type_key].update(record)

    return stats_map


def decode_payload(
    payload: bytes, decoder_id: str, params: DecoderParams
) -> str | None:
    """
    Decode a payload using the specified decoder.

    Returns:
        Decoded string representation or None if decoding fails.
    """
    try:
        if decoder_id == "none":
            return None

        elif decoder_id == "int":
            width = params.int_width or len(payload)
            if width > len(payload):
                return None
            endian = params.int_endian or "little"
            value = int.from_bytes(
                payload[:width], endian, signed=params.int_signed
            )
            return str(value)

        elif decoder_id == "string":
            text = payload.decode(params.string_encoding, errors="replace")
            if params.string_null_terminated:
                text = text.split("\x00", 1)[0]
            elif params.string_strip_nulls:
                text = text.rstrip("\x00")
            return text

        elif decoder_id == "date":
            # Implement date decoding based on params.date_format
            if params.date_format == "unix_s" and len(payload) >= 4:
                timestamp = int.from_bytes(payload[:4], "little", signed=False)
                from datetime import datetime, timedelta

                dt = datetime(1970, 1, 1) + timedelta(seconds=timestamp)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            return None

        elif decoder_id == "bitflags":
            width = params.bitflags_width or len(payload)
            if width > len(payload):
                return None
            value = int.from_bytes(payload[:width], "little", signed=False)
            bits = format(value, f"0{width*8}b")
            return f"{value:#x} ({bits})"

        elif decoder_id == "hex":
            return payload.hex()

        return None

    except Exception:
        return None


def save_registry(
    registry: dict[str, TypeRegistryEntry],
    params: FramingParams,
    output_path: Path,
) -> None:
    """Save type registry and framing params to JSON file."""
    data = {
        "version": 1,
        "framing_params": {
            "type_width": params.type_width,
            "length_width": params.length_width,
            "length_endian": params.length_endian,
            "length_semantics": params.length_semantics.value,
            "max_payload_len": params.max_payload_len,
            "strict_eof": params.strict_eof,
            "type_normalization": params.type_normalization.value,
        },
        "registry": {key: entry.to_dict() for key, entry in registry.items()},
    }

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)


def load_registry(
    input_path: Path,
) -> tuple[dict[str, TypeRegistryEntry], FramingParams]:
    """Load type registry and framing params from JSON file."""
    with open(input_path, "r") as f:
        data = json.load(f)

    # Parse framing params
    fp = data.get("framing_params", {})
    params = FramingParams(
        type_width=fp.get("type_width", 3),
        length_width=fp.get("length_width", 2),
        length_endian=fp.get("length_endian", "big"),
        length_semantics=LengthSemantics(fp.get("length_semantics", "payload_only")),
        max_payload_len=fp.get("max_payload_len"),
        strict_eof=fp.get("strict_eof", True),
        type_normalization=TypeNormalization(fp.get("type_normalization", "raw")),
    )

    # Parse registry
    registry: dict[str, TypeRegistryEntry] = {}
    for key, entry_dict in data.get("registry", {}).items():
        entry = TypeRegistryEntry.from_dict(entry_dict)
        registry[key] = entry

    return registry, params
