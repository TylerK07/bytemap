"""Test chunking/chunk stream analysis functionality."""

import tempfile
from pathlib import Path

from hexmap.core.chunks import (
    FramingParams,
    LengthSemantics,
    TypeNormalization,
    build_type_stats,
    decode_payload,
    DecoderParams,
    normalize_type_key,
    scan_chunks,
    TypeRegistryEntry,
    save_registry,
    load_registry,
)
from hexmap.core.io import PagedReader


def test_normalize_type_key():
    """Test type key normalization strategies."""
    type_bytes = b"\x01\x02\x03"

    # Raw
    assert normalize_type_key(type_bytes, TypeNormalization.RAW) == "010203"

    # Big endian uint
    key = normalize_type_key(type_bytes, TypeNormalization.UINT_BE)
    assert key == "u24be:66051"  # 0x010203 = 66051

    # Little endian uint
    key = normalize_type_key(type_bytes, TypeNormalization.UINT_LE)
    assert key == "u24le:197121"  # 0x030201 = 197121

    # ASCII (not printable, falls back to hex)
    key = normalize_type_key(type_bytes, TypeNormalization.ASCII)
    assert key == "010203"

    # ASCII (printable)
    ascii_bytes = b"ABC"
    key = normalize_type_key(ascii_bytes, TypeNormalization.ASCII)
    assert key == "ascii:ABC"


def test_scan_chunks_basic():
    """Test basic chunk scanning with simple framing."""
    # Create a test file with 2 chunks:
    # Chunk 1: type=0x01 0x02 0x03, length=0x00 0x04 (payload only), payload="TEST"
    # Chunk 2: type=0x01 0x02 0x03, length=0x00 0x05 (payload only), payload="HELLO"
    test_data = (
        b"\x01\x02\x03"  # Type 1
        b"\x00\x04"       # Length = 4
        b"TEST"           # Payload
        b"\x01\x02\x03"  # Type 1
        b"\x00\x05"       # Length = 5
        b"HELLO"          # Payload
    )

    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.bin') as f:
        f.write(test_data)
        test_file = f.name

    try:
        params = FramingParams(
            type_width=3,
            length_width=2,
            length_endian="big",
            length_semantics=LengthSemantics.PAYLOAD_ONLY,
        )

        reader = PagedReader(test_file)
        records, errors = scan_chunks(reader, params)

        assert len(errors) == 0, f"Unexpected errors: {errors}"
        assert len(records) == 2

        # Check first chunk
        rec1 = records[0]
        assert rec1.offset == 0
        assert rec1.type_bytes == b"\x01\x02\x03"
        assert rec1.payload_len == 4
        assert rec1.payload_offset == 5
        assert rec1.header_len == 5
        assert rec1.total_len == 9

        # Check second chunk
        rec2 = records[1]
        assert rec2.offset == 9
        assert rec2.type_bytes == b"\x01\x02\x03"
        assert rec2.payload_len == 5
        assert rec2.payload_offset == 14

    finally:
        import os
        os.unlink(test_file)


def test_scan_chunks_includes_header():
    """Test chunk scanning with length that includes header."""
    # Chunk: type=0xAA, length=0x00 0x06 (includes header), payload="AB"
    test_data = (
        b"\xAA"      # Type (1 byte)
        b"\x00\x06"  # Length = 6 (includes 3-byte header + 3-byte payload)
        b"ABC"       # Payload (3 bytes to match length-header=3)
    )

    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.bin') as f:
        f.write(test_data)
        test_file = f.name

    try:
        params = FramingParams(
            type_width=1,
            length_width=2,
            length_endian="big",
            length_semantics=LengthSemantics.INCLUDES_HEADER,
        )

        reader = PagedReader(test_file)
        records, errors = scan_chunks(reader, params)

        assert len(errors) == 0
        assert len(records) == 1

        rec = records[0]
        assert rec.type_bytes == b"\xAA"
        assert rec.length_value == 6
        assert rec.payload_len == 3  # 6 - 3 (header)
        assert rec.header_len == 3

    finally:
        import os
        os.unlink(test_file)


def test_build_type_stats():
    """Test building type statistics from records."""
    # Create test file with chunks of different types
    test_data = (
        b"\x01\x00\x03ABC"  # Type 1, len 3
        b"\x02\x00\x02XY"   # Type 2, len 2
        b"\x01\x00\x05HELLO"  # Type 1, len 5
        b"\x01\x00\x03DEF"  # Type 1, len 3
    )

    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.bin') as f:
        f.write(test_data)
        test_file = f.name

    try:
        params = FramingParams(
            type_width=1,
            length_width=2,
            length_endian="big",
            length_semantics=LengthSemantics.PAYLOAD_ONLY,
        )

        reader = PagedReader(test_file)
        records, errors = scan_chunks(reader, params)

        assert len(errors) == 0
        stats = build_type_stats(records)

        # Should have 2 unique types
        assert len(stats) == 2

        # Type 1 stats
        type1_key = normalize_type_key(b"\x01", TypeNormalization.RAW)
        assert type1_key in stats
        type1_stats = stats[type1_key]
        assert type1_stats.count == 3
        assert type1_stats.min_len == 3
        assert type1_stats.max_len == 5
        assert type1_stats.avg_len == (3 + 5 + 3) / 3

        # Type 2 stats
        type2_key = normalize_type_key(b"\x02", TypeNormalization.RAW)
        assert type2_key in stats
        type2_stats = stats[type2_key]
        assert type2_stats.count == 1
        assert type2_stats.min_len == 2
        assert type2_stats.max_len == 2

    finally:
        import os
        os.unlink(test_file)


def test_decode_payload():
    """Test payload decoding with different decoders."""
    # Integer decoding
    payload = b"\x01\x00\x00\x00"
    params = DecoderParams(int_width=4, int_endian="little", int_signed=False)
    result = decode_payload(payload, "int", params)
    assert result == "1"

    # String decoding
    payload = b"Hello\x00World"
    params = DecoderParams(string_encoding="ascii", string_null_terminated=True)
    result = decode_payload(payload, "string", params)
    assert result == "Hello"

    # Hex decoding
    payload = b"\xDE\xAD\xBE\xEF"
    result = decode_payload(payload, "hex", DecoderParams())
    assert result == "deadbeef"


def test_registry_persistence():
    """Test saving and loading registry."""
    # Create test registry
    registry = {
        "010203": TypeRegistryEntry(
            key_bytes=b"\x01\x02\x03",
            name="RecordType1",
            decoder_id="int",
            decoder_params=DecoderParams(int_width=4, int_endian="little"),
            notes="Test record type",
        )
    }

    params = FramingParams(
        type_width=3,
        length_width=2,
        length_endian="big",
        length_semantics=LengthSemantics.PAYLOAD_ONLY,
    )

    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        test_file = Path(f.name)

    try:
        # Save
        save_registry(registry, params, test_file)

        # Load
        loaded_registry, loaded_params = load_registry(test_file)

        # Verify params
        assert loaded_params.type_width == 3
        assert loaded_params.length_width == 2
        assert loaded_params.length_endian == "big"
        assert loaded_params.length_semantics == LengthSemantics.PAYLOAD_ONLY

        # Verify registry
        assert "010203" in loaded_registry
        entry = loaded_registry["010203"]
        assert entry.name == "RecordType1"
        assert entry.decoder_id == "int"
        assert entry.decoder_params.int_width == 4
        assert entry.decoder_params.int_endian == "little"
        assert entry.notes == "Test record type"

    finally:
        import os
        if test_file.exists():
            os.unlink(test_file)


if __name__ == "__main__":
    test_normalize_type_key()
    test_scan_chunks_basic()
    test_scan_chunks_includes_header()
    test_build_type_stats()
    test_decode_payload()
    test_registry_persistence()
    print("✓ All chunking tests passed!")
