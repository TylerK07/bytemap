"""Tests for color override support in YAML grammar."""

import pytest
from hexmap.core.yaml_grammar import parse_yaml_grammar
from hexmap.core.yaml_parser import RecordParser
from hexmap.core.io import PagedReader
from hexmap.core.incremental_spans import IncrementalSpanManager
import tempfile


def test_color_override_named_color():
    """Test that named colors are parsed and applied."""
    yaml_text = """
format: record_stream
endian: little

types:
  TestRecord:
    fields:
      - { name: magic, type: u16, color: red }
      - { name: version, type: u8, color: blue }
      - { name: data, type: bytes, length: 4, color: green }
"""

    grammar = parse_yaml_grammar(yaml_text)

    # Check that colors are stored in FieldDef
    test_type = grammar.types["TestRecord"]
    assert test_type.fields[0].color == "red"
    assert test_type.fields[1].color == "blue"
    assert test_type.fields[2].color == "green"


def test_color_override_hex_rgb():
    """Test that hex RGB colors are parsed and normalized."""
    yaml_text = """
format: record_stream
endian: little

types:
  TestRecord:
    fields:
      - { name: field1, type: u16, color: "#f80" }
      - { name: field2, type: u8, color: "#FF8800" }
      - { name: field3, type: bytes, length: 2, color: "#3498db" }
"""

    grammar = parse_yaml_grammar(yaml_text)

    # Check that colors are normalized
    test_type = grammar.types["TestRecord"]
    assert test_type.fields[0].color == "#ff8800"  # #f80 expanded to #ff8800
    assert test_type.fields[1].color == "#ff8800"  # Normalized to lowercase
    assert test_type.fields[2].color == "#3498db"


def test_color_override_invalid():
    """Test that invalid colors raise an error."""
    yaml_text = """
format: record_stream
endian: little

types:
  TestRecord:
    fields:
      - { name: field1, type: u16, color: invalid_color }
"""

    with pytest.raises(ValueError, match="Invalid color"):
        parse_yaml_grammar(yaml_text)


def test_color_propagates_to_parsed_field():
    """Test that color flows from FieldDef to ParsedField."""
    yaml_text = """
format: record_stream
endian: little

types:
  TestRecord:
    fields:
      - { name: magic, type: u16, color: purple }
      - { name: value, type: u8, color: orange }
"""

    grammar = parse_yaml_grammar(yaml_text)

    # Create test data
    test_data = bytes([0x12, 0x34, 0x56])

    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(test_data)
        f.flush()

        reader = PagedReader(f.name)
        parser = RecordParser(grammar)

        # Parse the record
        record = parser.parse_record(reader, 0)

        # Check that ParsedField has color
        assert record.fields["magic"].color == "purple"
        assert record.fields["value"].color == "orange"


def test_color_flows_to_spans():
    """Test that color flows from ParsedField to Span."""
    yaml_text = """
format: record_stream
endian: little

types:
  TestRecord:
    fields:
      - { name: magic, type: u16, color: "#ff0000" }
      - { name: value, type: u8, color: cyan }
      - { name: data, type: bytes, length: 2, color: yellow }
"""

    grammar = parse_yaml_grammar(yaml_text)

    # Create test data: 2 bytes (u16) + 1 byte (u8) + 2 bytes (data)
    test_data = bytes([0x12, 0x34, 0x56, 0xAB, 0xCD])

    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(test_data)
        f.flush()

        reader = PagedReader(f.name)
        parser = RecordParser(grammar)

        # Parse records
        records, _ = parser.parse_file(reader)

        # Create span manager
        manager = IncrementalSpanManager(records)

        # Generate spans for entire file
        span_index = manager.update_viewport(0, len(test_data))

        assert span_index is not None
        assert len(span_index._spans) == 3

        # Check that spans have correct colors
        spans_by_path = {s.path: s for s in span_index._spans}

        assert "TestRecord.magic" in spans_by_path
        assert spans_by_path["TestRecord.magic"].color_override == "#ff0000"

        assert "TestRecord.value" in spans_by_path
        assert spans_by_path["TestRecord.value"].color_override == "cyan"

        assert "TestRecord.data" in spans_by_path
        assert spans_by_path["TestRecord.data"].color_override == "yellow"


def test_nested_type_with_color():
    """Test that nested types with colors work correctly."""
    yaml_text = """
format: record_stream
endian: little

types:
  Header:
    fields:
      - { name: magic, type: u16 }
      - { name: version, type: u8 }

  Record:
    fields:
      - { name: header, type: Header, color: purple }
      - { name: payload, type: bytes, length: 2, color: green }
"""

    grammar = parse_yaml_grammar(yaml_text)

    # Check that color is set on nested field
    record_type = grammar.types["Record"]
    assert record_type.fields[0].color == "purple"
    assert record_type.fields[1].color == "green"

    # Create test data
    test_data = bytes([0x12, 0x34, 0x56, 0xAB, 0xCD])

    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(test_data)
        f.flush()

        reader = PagedReader(f.name)
        parser = RecordParser(grammar)

        # Directly parse Record type (not using record switch)
        record_type_def = grammar.types["Record"]
        record = parser._parse_type(reader, 0, record_type_def)

        # The nested field should have the color
        assert record.fields["header"].color == "purple"
        assert record.fields["payload"].color == "green"


def test_fields_without_color():
    """Test that fields without color have None."""
    yaml_text = """
format: record_stream
endian: little

types:
  TestRecord:
    fields:
      - { name: field1, type: u16 }
      - { name: field2, type: u8, color: red }
      - { name: field3, type: bytes, length: 2 }
"""

    grammar = parse_yaml_grammar(yaml_text)

    test_type = grammar.types["TestRecord"]
    assert test_type.fields[0].color is None
    assert test_type.fields[1].color == "red"
    assert test_type.fields[2].color is None

    # Create test data
    test_data = bytes([0x12, 0x34, 0x56, 0xAB, 0xCD])

    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(test_data)
        f.flush()

        reader = PagedReader(f.name)
        parser = RecordParser(grammar)

        # Parse records
        records, _ = parser.parse_file(reader)

        # Create spans
        manager = IncrementalSpanManager(records)
        span_index = manager.update_viewport(0, len(test_data))

        assert span_index is not None
        spans_by_path = {s.path: s for s in span_index._spans}

        # Fields without color should have None for color_override
        assert spans_by_path["TestRecord.field1"].color_override is None
        assert spans_by_path["TestRecord.field2"].color_override == "red"
        assert spans_by_path["TestRecord.field3"].color_override is None
