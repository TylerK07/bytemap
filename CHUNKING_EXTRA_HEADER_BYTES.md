# Chunking Tab - Extra Header Bytes Support ✅

## Problem Discovered

When parsing the AA.FTM file with initial framing parameters (type_width=3, length_width=2), the scanner stopped prematurely at offset 0xe16d, leaving **28KB of unparsed data**. The missing type `010400` that the user saw in the file bytes wasn't appearing in the types list.

## Root Cause

The file format was misinterpreted. The actual structure is:

```
Byte 0-2:  Type identifier (3 bytes)
Byte 3:    Payload length (u8, 0-255 bytes)
Byte 4:    Unknown/Flags byte
Bytes 5+:  Payload data
```

**NOT:**
```
Byte 0-2:  Type identifier (3 bytes)
Byte 3-4:  Payload length (u16)  ← WRONG!
Bytes 5+:  Payload data
```

The unknown byte at position 4 has varied values:
- `0x00`: 34.8% (most common)
- `0x01`: 18.3%
- `0x02`: 6.4%
- ASCII characters: `0x57` (W), `0x45` (E), `0x4d` (M), etc.

This suggests it's meaningful metadata (subtype, version, or flags), not just padding.

## Solution: Extra Header Bytes Parameter

Added a new `extra_header_bytes` parameter to `FramingParams` to support additional header bytes after the length field but before the payload.

### Code Changes

**1. Updated FramingParams** (src/hexmap/core/chunks.py:51):
```python
@dataclass(frozen=True)
class FramingParams:
    """Parameters for parsing chunk streams."""

    type_width: int
    length_width: int
    length_endian: str
    length_semantics: LengthSemantics
    max_payload_len: int | None = None
    strict_eof: bool = True
    type_normalization: TypeNormalization = TypeNormalization.RAW
    extra_header_bytes: int = 0  # NEW: Additional bytes after length field
```

**2. Updated scan_chunks()** (src/hexmap/core/chunks.py:235):
```python
header_size = params.type_width + params.length_width + params.extra_header_bytes
```

The `payload_offset` calculation already accounts for this since it uses `header_size`:
```python
payload_offset = offset + header_size
```

**3. Added UI Control** (src/hexmap/widgets/chunking.py:80-81):
```python
yield Label("Extra Header Bytes:")
yield Input(value="0", id="extra-header-input")
```

## Usage

For the AA.FTM file format, set these framing parameters in the Chunking tab:

```
Type Width:          3
Length Width:        1
Extra Header Bytes:  1
Endian:              Big
Semantics:           Payload Only
```

## Results

With the correct parameters:
- ✅ **Parsed 9,023 records** (entire file)
- ✅ **Only 24 bytes remaining** (incomplete final record)
- ✅ **Found 7,764 unique types**
- ✅ **Found type `010400`** - Appears 2 times at offsets 0x000131 and 0x000295

### Type Distribution (Top 20)

```
000000: 19×    010000: 8×     020000: 8×     030000: 8×
040000: 7×     050000: 7×     070000: 6×     080000: 6×
090000: 6×     060000: 6×     001c00: 5×     0a0000: 5×
0d0000: 5×     0e0000: 5×     0f0000: 5×     160000: 5×
170000: 5×     0b0000: 5×     0c0000: 5×     202020: 5×
```

## About Type `010400`

The bytes `01 04 00` appear **786 times** in the file, but almost all occurrences are **inside payload data**, not as chunk headers. They're part of structured sub-records within larger payloads.

With the correct framing parameters, only **2 actual chunk records** have type `010400`:
- Offset 0x000131: payload length 2 bytes
- Offset 0x000295: payload length 2 bytes

## General Use Case

The `extra_header_bytes` parameter is useful for formats that have:
- **Flags/version bytes** after the length field
- **Padding/alignment** requirements
- **Reserved bytes** in the header
- **Extended metadata** that's part of the header but not the payload

## Testing

All existing tests pass:
```bash
pytest tests/test_chunking.py  # 6/6 tests pass
```

The backward compatibility is maintained - `extra_header_bytes` defaults to `0`, so existing code continues to work without changes.
