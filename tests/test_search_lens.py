"""Tests for search lens functionality."""

import struct
from datetime import datetime
from pathlib import Path

from hexmap.core.io import PagedReader
from hexmap.core.search_lens import (
    MatchDetail,
    SearchHit,
    SearchState,
    search_date_ascii_text,
    search_date_days_since_1970,
    search_date_days_since_1980,
    search_date_dos_date,
    search_date_dos_datetime,
    search_date_ftm_packed,
    search_date_ole_date,
    search_date_unix_s,
)


def test_search_state_lifecycle():
    """Test SearchState basic lifecycle."""
    state = SearchState()
    assert not state.is_active()
    assert not state.has_results()
    assert state.current_hit() is None

    state.mode = "date"
    assert state.is_active()

    state.clear()
    assert not state.is_active()
    assert state.mode == "none"


def test_search_date_unix_s_finds_timestamps(tmp_path: Path):
    """Test date search finds known unix timestamps."""
    # Create test file with embedded timestamps
    test_file = tmp_path / "test.bin"

    # Known dates:
    # 2020-01-01 00:00:00 UTC = 1577836800
    # 2020-06-15 12:30:45 UTC = 1592226645
    # 2021-12-25 23:59:59 UTC = 1640476799

    ts1 = 1577836800
    ts2 = 1592226645
    ts3 = 1640476799

    # Build file with timestamps at aligned positions
    data = bytearray(256)
    # Put timestamps at offsets 0, 16, 32
    data[0:4] = struct.pack("<I", ts1)
    data[16:20] = struct.pack("<I", ts2)
    data[32:36] = struct.pack("<I", ts3)

    test_file.write_bytes(data)

    reader = PagedReader(str(test_file))

    # Search for dates in 2020-2021 range
    start = datetime(2020, 1, 1)
    end = datetime(2021, 12, 31)

    hits = search_date_unix_s(reader, start, end, alignment=4)

    assert len(hits) == 3
    assert hits[0].offset == 0
    assert hits[0].length == 4
    assert "2020-01-01" in hits[0].summary

    assert hits[1].offset == 16
    assert "2020-06-15" in hits[1].summary

    assert hits[2].offset == 32
    assert "2021-12-25" in hits[2].summary


def test_search_date_unix_s_ignores_out_of_range(tmp_path: Path):
    """Test date search ignores timestamps outside range."""
    test_file = tmp_path / "test.bin"

    # 1990-01-01 = 631152000
    # 2025-01-01 = 1735689600
    old_ts = 631152000
    future_ts = 1735689600
    valid_ts = 1577836800  # 2020-01-01

    data = bytearray(64)
    data[0:4] = struct.pack("<I", old_ts)
    data[16:20] = struct.pack("<I", valid_ts)
    data[32:36] = struct.pack("<I", future_ts)

    test_file.write_bytes(data)

    reader = PagedReader(str(test_file))

    # Search only for 2020
    start = datetime(2020, 1, 1)
    end = datetime(2020, 12, 31)

    hits = search_date_unix_s(reader, start, end, alignment=4)

    # Should only find the middle one
    assert len(hits) == 1
    assert hits[0].offset == 16
    assert "2020-01-01" in hits[0].summary


def test_search_date_unix_s_respects_alignment(tmp_path: Path):
    """Test alignment parameter controls scan step."""
    test_file = tmp_path / "test.bin"

    ts = 1577836800  # 2020-01-01
    data = bytearray(64)
    # Put timestamp at unaligned offset 3
    data[3:7] = struct.pack("<I", ts)

    test_file.write_bytes(data)

    reader = PagedReader(str(test_file))
    start = datetime(2020, 1, 1)
    end = datetime(2020, 12, 31)

    # With alignment=4, should miss it (scans 0, 4, 8...)
    hits_aligned = search_date_unix_s(reader, start, end, alignment=4)
    assert len(hits_aligned) == 0

    # With alignment=1, should find it
    hits_unaligned = search_date_unix_s(reader, start, end, alignment=1)
    assert len(hits_unaligned) == 1
    assert hits_unaligned[0].offset == 3


def test_search_state_navigation():
    """Test next/prev hit navigation."""
    state = SearchState()

    # Add some mock hits
    match1 = MatchDetail("test", "hit1", {})
    match2 = MatchDetail("test", "hit2", {})
    match3 = MatchDetail("test", "hit3", {})

    state.results = [
        SearchHit(0, 4, "hit1", [match1]),
        SearchHit(16, 4, "hit2", [match2]),
        SearchHit(32, 4, "hit3", [match3]),
    ]
    state.index = 0

    # Next cycles forward
    hit = state.next_hit()
    assert hit is not None
    assert hit.offset == 16
    assert state.index == 1

    hit = state.next_hit()
    assert hit.offset == 32
    assert state.index == 2

    # Next wraps around
    hit = state.next_hit()
    assert hit.offset == 0
    assert state.index == 0

    # Prev cycles backward
    hit = state.prev_hit()
    assert hit.offset == 32
    assert state.index == 2

    hit = state.prev_hit()
    assert hit.offset == 16
    assert state.index == 1


def test_search_empty_file(tmp_path: Path):
    """Test search handles empty file gracefully."""
    test_file = tmp_path / "empty.bin"
    test_file.write_bytes(b"")

    reader = PagedReader(str(test_file))
    start = datetime(2020, 1, 1)
    end = datetime(2021, 12, 31)

    hits = search_date_unix_s(reader, start, end)
    assert len(hits) == 0


def test_search_file_too_small(tmp_path: Path):
    """Test search handles file smaller than type size."""
    test_file = tmp_path / "small.bin"
    test_file.write_bytes(b"ab")  # Only 2 bytes

    reader = PagedReader(str(test_file))
    start = datetime(2020, 1, 1)
    end = datetime(2021, 12, 31)

    hits = search_date_unix_s(reader, start, end)
    assert len(hits) == 0


def test_search_date_dos_datetime(tmp_path: Path):
    """Test DOS datetime search finds packed dates."""
    test_file = tmp_path / "test.bin"

    # DOS datetime for 1991-12-18 14:30:24
    # Date: year=1991 (11 from 1980), month=12, day=18
    # date_u16 = ((11 << 9) | (12 << 5) | 18) = 5632 + 384 + 18 = 6034
    # Time: hour=14, minute=30, second/2=12
    # time_u16 = ((14 << 11) | (30 << 5) | 12) = 28672 + 960 + 12 = 29644

    date_u16 = 6034
    time_u16 = 29644

    data = bytearray(64)
    data[0:4] = struct.pack("<HH", date_u16, time_u16)

    test_file.write_bytes(data)

    reader = PagedReader(str(test_file))
    start = datetime(1991, 1, 1)
    end = datetime(1991, 12, 31)

    hits = search_date_dos_datetime(reader, start, end, alignment=4)

    assert len(hits) == 1
    assert hits[0].offset == 0
    assert hits[0].length == 4
    assert "1991-12-18" in hits[0].summary
    assert "14:30:24" in hits[0].summary


def test_search_date_dos_datetime_validates_ranges(tmp_path: Path):
    """Test DOS datetime rejects invalid dates."""
    test_file = tmp_path / "test.bin"

    # Invalid month (13)
    date_u16 = (11 << 9) | (13 << 5) | 18  # month=13 is invalid
    time_u16 = 0

    data = bytearray(64)
    data[0:4] = struct.pack("<HH", date_u16, time_u16)

    test_file.write_bytes(data)

    reader = PagedReader(str(test_file))
    start = datetime(1980, 1, 1)
    end = datetime(2100, 12, 31)

    hits = search_date_dos_datetime(reader, start, end, alignment=1)

    # Should find nothing because month is invalid
    assert len(hits) == 0


def test_search_date_ole_date(tmp_path: Path):
    """Test OLE DATE search finds floating point dates."""
    test_file = tmp_path / "test.bin"

    # OLE DATE for 2020-06-15 12:00:00
    # Days since 1899-12-30
    from datetime import UTC

    ole_epoch = datetime(1899, 12, 30, tzinfo=UTC)
    target_date = datetime(2020, 6, 15, 12, 0, 0, tzinfo=UTC)
    days = (target_date - ole_epoch).total_seconds() / 86400

    data = bytearray(64)
    data[0:8] = struct.pack("<d", days)

    test_file.write_bytes(data)

    reader = PagedReader(str(test_file))
    start = datetime(2020, 1, 1)
    end = datetime(2020, 12, 31)

    hits = search_date_ole_date(reader, start, end, alignment=8)

    assert len(hits) == 1
    assert hits[0].offset == 0
    assert hits[0].length == 8
    assert "2020-06-15" in hits[0].summary


def test_search_date_ole_date_rejects_invalid(tmp_path: Path):
    """Test OLE DATE rejects NaN and extreme values."""
    test_file = tmp_path / "test.bin"

    data = bytearray(64)
    # Put NaN at offset 0
    data[0:8] = struct.pack("<d", float("nan"))
    # Put extreme value at offset 16 (>3M days would overflow datetime)
    data[16:24] = struct.pack("<d", 4000000.0)

    test_file.write_bytes(data)

    reader = PagedReader(str(test_file))
    start = datetime(1900, 1, 1)
    end = datetime(2100, 12, 31)

    hits = search_date_ole_date(reader, start, end, alignment=8)

    # Should find nothing
    assert len(hits) == 0


def test_search_date_ascii_text(tmp_path: Path):
    """Test ASCII date text search finds text dates."""
    test_file = tmp_path / "test.bin"

    # Embed various date formats in ASCII text
    text = b"Created: 12/18/91\nModified: 06/15/2020\nExpires: 2021-12-25\n"

    test_file.write_bytes(text)

    reader = PagedReader(str(test_file))
    start = datetime(1991, 1, 1)
    end = datetime(2021, 12, 31)

    hits = search_date_ascii_text(reader, start, end)

    # Should find all three dates
    assert len(hits) == 3

    # Check first hit (MM/DD/YY)
    assert hits[0].offset == 9  # Position of "12/18/91"
    assert hits[0].length == 8
    assert "1991-12-18" in hits[0].summary

    # Check second hit (MM/DD/YYYY)
    assert hits[1].offset == 28  # Position of "06/15/2020"
    assert hits[1].length == 10
    assert "2020-06-15" in hits[1].summary

    # Check third hit (YYYY-MM-DD)
    assert hits[2].offset == 48  # Position of "2021-12-25"
    assert hits[2].length == 10
    assert "2021-12-25" in hits[2].summary


def test_search_date_ascii_two_digit_year_mapping(tmp_path: Path):
    """Test ASCII date 2-digit year mapping."""
    test_file = tmp_path / "test.bin"

    # Test year mapping: 00-69 => 2000-2069, 70-99 => 1970-1999
    text = b"Date1: 12/18/69\nDate2: 12/18/70\n"

    test_file.write_bytes(text)

    reader = PagedReader(str(test_file))
    start = datetime(1960, 1, 1)
    end = datetime(2100, 12, 31)

    hits = search_date_ascii_text(reader, start, end)

    assert len(hits) == 2
    assert "2069" in hits[0].summary  # 69 => 2069
    assert "1970" in hits[1].summary  # 70 => 1970


def test_search_multiple_encodings_or_semantics(tmp_path: Path):
    """Test that multiple encodings produce union of results."""
    test_file = tmp_path / "test.bin"

    # Create file with both unix_s timestamp and DOS datetime
    data = bytearray(64)

    # Unix timestamp at offset 0: 2020-01-01
    unix_ts = 1577836800
    data[0:4] = struct.pack("<I", unix_ts)

    # DOS datetime at offset 16: 1991-12-18
    date_u16 = 6034
    time_u16 = 29644
    data[16:20] = struct.pack("<HH", date_u16, time_u16)

    test_file.write_bytes(data)

    reader = PagedReader(str(test_file))
    start = datetime(1990, 1, 1)
    end = datetime(2021, 12, 31)

    # Search with unix_s
    hits_unix = search_date_unix_s(reader, start, end, alignment=4)
    # Search with DOS datetime
    hits_dos = search_date_dos_datetime(reader, start, end, alignment=4)

    # Should find different hits
    assert len(hits_unix) == 1
    assert hits_unix[0].offset == 0

    assert len(hits_dos) == 1
    assert hits_dos[0].offset == 16

    # Union should have both
    all_hits = hits_unix + hits_dos
    assert len(all_hits) == 2


def test_search_deduplication_same_offset_length(tmp_path: Path):
    """Test that hits with same (offset, length) are deduplicated."""
    # This is a conceptual test - in practice, dedup happens in app.py
    # Here we just verify that hits can have same offset/length
    match1 = MatchDetail("unix_s (u32 LE)", "2020-01-01 00:00:00 UTC", {})
    match2 = MatchDetail("DOS datetime (2×u16 LE)", "2020-01-01 00:00:00 UTC", {})

    hit1 = SearchHit(0, 4, "2020-01-01 00:00:00 UTC", [match1])
    hit2 = SearchHit(0, 4, "2020-01-01 00:00:00 UTC", [match2])

    # Both hits have same offset and length
    assert hit1.offset == hit2.offset
    assert hit1.length == hit2.length

    # When deduplicated, matches should be merged
    hit1.matches.extend(hit2.matches)
    assert len(hit1.matches) == 2


def test_search_date_dos_date(tmp_path: Path):
    """Test DOS date (u16 only) search finds packed dates."""
    test_file = tmp_path / "test.bin"

    # DOS date for 1991-12-18 (no time component)
    # year=1991 (11 from 1980), month=12, day=18
    # date_u16 = ((11 << 9) | (12 << 5) | 18) = 5632 + 384 + 18 = 6034

    date_u16 = 6034

    data = bytearray(64)
    data[0:2] = struct.pack("<H", date_u16)

    test_file.write_bytes(data)

    reader = PagedReader(str(test_file))
    start = datetime(1991, 1, 1)
    end = datetime(1991, 12, 31)

    hits = search_date_dos_date(reader, start, end, alignment=2)

    assert len(hits) == 1
    assert hits[0].offset == 0
    assert hits[0].length == 2
    assert "1991-12-18" in hits[0].summary
    # Date only format should not include time
    assert ":" not in hits[0].summary


def test_search_date_days_since_1970(tmp_path: Path):
    """Test days since 1970 search finds dates."""
    test_file = tmp_path / "test.bin"

    # 2020-01-01 is 18262 days since 1970-01-01
    days_value = 18262

    data = bytearray(64)
    data[0:2] = struct.pack("<H", days_value)

    test_file.write_bytes(data)

    reader = PagedReader(str(test_file))
    start = datetime(2020, 1, 1)
    end = datetime(2020, 12, 31)

    hits = search_date_days_since_1970(reader, start, end, alignment=2)

    assert len(hits) == 1
    assert hits[0].offset == 0
    assert hits[0].length == 2
    assert "2020-01-01" in hits[0].summary
    # Date only format should not include time
    assert ":" not in hits[0].summary


def test_search_date_days_since_1980(tmp_path: Path):
    """Test days since 1980 search finds dates."""
    test_file = tmp_path / "test.bin"

    # 2020-01-01 is 14610 days since 1980-01-01
    days_value = 14610

    data = bytearray(64)
    data[0:2] = struct.pack("<H", days_value)

    test_file.write_bytes(data)

    reader = PagedReader(str(test_file))
    start = datetime(2020, 1, 1)
    end = datetime(2020, 12, 31)

    hits = search_date_days_since_1980(reader, start, end, alignment=2)

    assert len(hits) == 1
    assert hits[0].offset == 0
    assert hits[0].length == 2
    assert "2020-01-01" in hits[0].summary
    # Date only format should not include time
    assert ":" not in hits[0].summary


def test_search_date_dos_date_validates_ranges(tmp_path: Path):
    """Test DOS date (u16) rejects invalid dates."""
    test_file = tmp_path / "test.bin"

    # Invalid month (13)
    date_u16 = (11 << 9) | (13 << 5) | 18  # month=13 is invalid

    data = bytearray(64)
    data[0:2] = struct.pack("<H", date_u16)

    test_file.write_bytes(data)

    reader = PagedReader(str(test_file))
    start = datetime(1980, 1, 1)
    end = datetime(2100, 12, 31)

    hits = search_date_dos_date(reader, start, end, alignment=1)

    # Should find nothing because month is invalid
    assert len(hits) == 0


def test_search_date_ftm_packed_high_confidence(tmp_path: Path):
    """Test FTM Packed Date with High confidence (flags=0x02)."""
    test_file = tmp_path / "test.bin"

    # 2012-11-18 with flags=0x02 (High confidence)
    # byte0: (18 << 3) | 0x02 = 144 + 2 = 146 = 0x92
    # byte1: (11 << 1) = 22 = 0x16
    # year: 2012 = 0x07DC
    data = bytearray(64)
    data[0:4] = bytes([0x92, 0x16, 0xDC, 0x07])

    test_file.write_bytes(data)

    reader = PagedReader(str(test_file))
    start = datetime(2012, 1, 1)
    end = datetime(2012, 12, 31)

    hits = search_date_ftm_packed(reader, start, end, alignment=2)

    assert len(hits) == 1
    assert hits[0].offset == 0
    assert hits[0].length == 4
    assert "2012-11-18" in hits[0].summary
    assert "[High]" in hits[0].summary
    assert hits[0].matches[0].encoding == "FTM Packed Date (4-byte)"
    assert hits[0].matches[0].details["confidence"] == "High"


def test_search_date_ftm_packed_low_confidence(tmp_path: Path):
    """Test FTM Packed Date with Low confidence (flags != 0x02)."""
    test_file = tmp_path / "test.bin"

    # 2001-03-21 with flags=0x05 (Low confidence - unexpected flags)
    # byte0: (21 << 3) | 0x05 = 168 + 5 = 173 = 0xAD
    # byte1: (3 << 1) = 6 = 0x06
    # year: 2001 = 0x07D1
    data = bytearray(64)
    data[0:4] = bytes([0xAD, 0x06, 0xD1, 0x07])

    test_file.write_bytes(data)

    reader = PagedReader(str(test_file))
    start = datetime(2001, 1, 1)
    end = datetime(2001, 12, 31)

    hits = search_date_ftm_packed(reader, start, end, alignment=2)

    assert len(hits) == 1
    assert hits[0].offset == 0
    assert hits[0].length == 4
    assert "2001-03-21" in hits[0].summary
    assert "[Low" in hits[0].summary
    assert "unexpected flags" in hits[0].summary.lower()
    assert hits[0].matches[0].details["confidence"].startswith("Low")


def test_search_date_ftm_packed_rejects_invalid_month_encoding(tmp_path: Path):
    """Test FTM Packed Date rejects invalid month encoding (low bit set)."""
    test_file = tmp_path / "test.bin"

    # Valid date fields but byte1 has low bit set (invalid encoding)
    # byte0: (15 << 3) | 0x02 = 122 = 0x7A
    # byte1: (6 << 1) | 0x01 = 13 = 0x0D (low bit set - INVALID)
    # year: 2020 = 0x07E4
    data = bytearray(64)
    data[0:4] = bytes([0x7A, 0x0D, 0xE4, 0x07])

    test_file.write_bytes(data)

    reader = PagedReader(str(test_file))
    start = datetime(2020, 1, 1)
    end = datetime(2020, 12, 31)

    hits = search_date_ftm_packed(reader, start, end, alignment=2)

    # Should find nothing because month encoding is invalid
    assert len(hits) == 0


def test_search_date_ftm_packed_validates_ranges(tmp_path: Path):
    """Test FTM Packed Date rejects invalid date ranges."""
    test_file = tmp_path / "test.bin"

    # Invalid day (32)
    # byte0: (32 << 3) | 0x02 = 256 + 2 = 258 (but only 8 bits, so wraps)
    # Actually, let's use day=0 which is invalid
    # byte0: (0 << 3) | 0x02 = 0x02
    # byte1: (6 << 1) = 12 = 0x0C
    # year: 2020 = 0x07E4
    data = bytearray(64)
    data[0:4] = bytes([0x02, 0x0C, 0xE4, 0x07])

    test_file.write_bytes(data)

    reader = PagedReader(str(test_file))
    start = datetime(2020, 1, 1)
    end = datetime(2020, 12, 31)

    hits = search_date_ftm_packed(reader, start, end, alignment=2)

    # Should find nothing because day=0 is invalid
    assert len(hits) == 0


def test_search_date_ftm_packed_known_test_case(tmp_path: Path):
    """Test FTM Packed Date with known test case from user."""
    test_file = tmp_path / "test.bin"

    # 2001-03-21 encoded as AA 06 D1 07 (from user's test case)
    # Let's verify: byte0=0xAA=170, byte1=0x06, year=0x07D1=2001
    # flags = 0xAA & 0x07 = 0x02 (High confidence)
    # day = 0xAA >> 3 = 21
    # month = 0x06 >> 1 = 3
    data = bytearray(64)
    data[0:4] = bytes([0xAA, 0x06, 0xD1, 0x07])

    test_file.write_bytes(data)

    reader = PagedReader(str(test_file))
    start = datetime(2001, 1, 1)
    end = datetime(2001, 12, 31)

    hits = search_date_ftm_packed(reader, start, end, alignment=2)

    assert len(hits) == 1
    assert hits[0].offset == 0
    assert hits[0].length == 4
    assert "2001-03-21" in hits[0].summary
    assert "[High]" in hits[0].summary
