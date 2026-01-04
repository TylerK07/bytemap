"""Tests for viewport-based incremental span generation."""

import pytest
from hexmap.core.incremental_spans import IncrementalSpanManager, RecordOffset
from hexmap.core.yaml_parser import ParsedRecord, ParsedField


def create_test_records(count: int, record_size: int = 100) -> list[ParsedRecord]:
    """Create test records for testing."""
    records = []
    offset = 0

    for i in range(count):
        # Create simple fields for each record
        fields = {
            "field1": ParsedField(
                name="field1",
                value=i,
                raw_bytes=b"\x00" * 10,
                offset=offset,
                size=10,
            ),
            "field2": ParsedField(
                name="field2",
                value=f"test_{i}",
                raw_bytes=b"\x00" * 20,
                offset=offset + 10,
                size=20,
            ),
        }

        record = ParsedRecord(
            offset=offset,
            size=record_size,
            type_name="TestRecord",
            fields=fields,
        )

        records.append(record)
        offset += record_size

    return records


def test_manager_initialization():
    """Test IncrementalSpanManager initialization."""
    records = create_test_records(100)
    manager = IncrementalSpanManager(records)

    assert len(manager._record_offsets) == 100
    assert manager._current_viewport_start == -1
    assert manager._current_viewport_end == -1
    assert manager._cached_spans == []
    assert manager._cached_span_index is None


def test_offset_index_building():
    """Test that offset index is built correctly."""
    records = create_test_records(10, record_size=50)
    manager = IncrementalSpanManager(records)

    # Check offsets are correct
    assert len(manager._record_offsets) == 10

    for i, rec_offset in enumerate(manager._record_offsets):
        assert rec_offset.offset == i * 50
        assert rec_offset.size == 50
        assert rec_offset.record_index == i


def test_viewport_initial_update():
    """Test initial viewport update."""
    records = create_test_records(100, record_size=100)
    manager = IncrementalSpanManager(records)

    # Update viewport for first 3 records
    span_index = manager.update_viewport(0, 300)

    assert span_index is not None
    # Should have spans for records 0, 1, 2 (2 fields each = 6 spans)
    assert len(span_index._spans) > 0
    assert manager._current_viewport_start == 0
    assert manager._current_viewport_end == 300


def test_viewport_caching():
    """Test that viewport updates are cached."""
    records = create_test_records(100, record_size=100)
    manager = IncrementalSpanManager(records)

    # First update
    span_index1 = manager.update_viewport(0, 300)
    assert span_index1 is not None

    # Second update with same viewport should return cached result
    span_index2 = manager.update_viewport(0, 300)
    assert span_index2 is not None
    assert span_index2 is span_index1  # Same object


def test_viewport_change():
    """Test viewport change detection."""
    records = create_test_records(100, record_size=100)
    manager = IncrementalSpanManager(records)

    # First viewport
    span_index1 = manager.update_viewport(0, 300)
    span_count1 = len(span_index1._spans) if span_index1 else 0

    # Move to different viewport
    span_index2 = manager.update_viewport(500, 800)
    span_count2 = len(span_index2._spans) if span_index2 else 0

    assert span_index2 is not None
    assert span_index2 is not span_index1  # Different object
    assert span_count2 > 0  # Has new spans


def test_find_records_in_range():
    """Test binary search for records in range."""
    records = create_test_records(10, record_size=100)
    manager = IncrementalSpanManager(records)

    # Records are at offsets: 0, 100, 200, 300, ..., 900

    # Test 1: Viewport covers records 0, 1, 2
    indices = manager._find_records_in_range(0, 300)
    assert indices == [0, 1, 2]

    # Test 2: Viewport covers records 5, 6
    indices = manager._find_records_in_range(500, 700)
    assert indices == [5, 6]

    # Test 3: Viewport covers last record
    indices = manager._find_records_in_range(900, 1000)
    assert indices == [9]

    # Test 4: Viewport covers partial records (450-550 overlaps records 4 and 5)
    indices = manager._find_records_in_range(450, 550)
    assert indices == [4, 5]

    # Test 5: Viewport beyond all records
    indices = manager._find_records_in_range(2000, 3000)
    assert indices == []


def test_error_records_excluded():
    """Test that records with errors are excluded from index."""
    records = create_test_records(10, record_size=100)

    # Mark some records as having errors
    records[3].error = "Parse error"
    records[7].error = "Invalid data"

    manager = IncrementalSpanManager(records)

    # Should only index 8 records (10 - 2 with errors)
    assert len(manager._record_offsets) == 8

    # Verify error records are not in index
    indexed_offsets = {r.offset for r in manager._record_offsets}
    assert 300 not in indexed_offsets  # Record 3
    assert 700 not in indexed_offsets  # Record 7


def test_nested_fields():
    """Test span generation for nested fields."""
    # Create record with nested fields
    nested_fields = {
        "nested_int": ParsedField(
            name="nested_int",
            value=42,
            raw_bytes=b"\x00\x00\x00\x2a",
            offset=10,
            size=4,
        ),
        "nested_str": ParsedField(
            name="nested_str",
            value="hello",
            raw_bytes=b"hello",
            offset=14,
            size=5,
        ),
    }

    fields = {
        "simple": ParsedField(
            name="simple",
            value=123,
            raw_bytes=b"\x7b",
            offset=0,
            size=1,
        ),
        "nested": ParsedField(
            name="nested",
            value={"nested_int": 42, "nested_str": "hello"},
            raw_bytes=b"",
            offset=10,
            size=9,
            nested_fields=nested_fields,
        ),
    }

    record = ParsedRecord(
        offset=0,
        size=19,
        type_name="TestRecord",
        fields=fields,
    )

    manager = IncrementalSpanManager([record])
    span_index = manager.update_viewport(0, 100)

    assert span_index is not None
    # Should have 3 spans: simple, nested_int, nested_str
    assert len(span_index._spans) == 3

    # Check paths
    paths = {s.path for s in span_index._spans}
    assert "TestRecord.simple" in paths
    assert "TestRecord.nested.nested_int" in paths
    assert "TestRecord.nested.nested_str" in paths


def test_large_viewport():
    """Test with large viewport covering many records."""
    records = create_test_records(1000, record_size=50)
    manager = IncrementalSpanManager(records)

    # Viewport covering first 100 records
    span_index = manager.update_viewport(0, 5000)

    assert span_index is not None
    # Should have spans for 100 records (2 fields each = 200 spans)
    assert len(span_index._spans) == 200


def test_empty_records():
    """Test with empty record list."""
    manager = IncrementalSpanManager([])

    span_index = manager.update_viewport(0, 1000)

    assert span_index is None
    assert len(manager._record_offsets) == 0


def test_span_groups():
    """Test that span groups are set correctly based on field types."""
    fields = {
        "int_field": ParsedField(
            name="int_field",
            value=42,
            raw_bytes=b"\x2a",
            offset=0,
            size=1,
        ),
        "str_field": ParsedField(
            name="str_field",
            value="test",
            raw_bytes=b"test",
            offset=1,
            size=4,
        ),
        "bytes_field": ParsedField(
            name="bytes_field",
            value=b"\x00\x01\x02",
            raw_bytes=b"\x00\x01\x02",
            offset=5,
            size=3,
        ),
    }

    record = ParsedRecord(
        offset=0,
        size=8,
        type_name="TestRecord",
        fields=fields,
    )

    manager = IncrementalSpanManager([record])
    span_index = manager.update_viewport(0, 100)

    assert span_index is not None
    assert len(span_index._spans) == 3

    # Check groups
    groups = {s.path.split(".")[-1]: s.group for s in span_index._spans}
    assert groups["int_field"] == "int"
    assert groups["str_field"] == "string"
    assert groups["bytes_field"] == "bytes"
