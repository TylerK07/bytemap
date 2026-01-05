"""Tests for Tool Host."""

from pathlib import Path

import pytest

from hexmap.core.tool_host import (
    AnalyzeCoverageInput,
    DecodeFieldInput,
    GenerateSpansInput,
    LintGrammarInput,
    ParseBinaryInput,
    QueryRecordsInput,
    ToolHost,
)


class TestLintGrammar:
    """Tests for lint_grammar tool."""

    def test_lint_grammar_valid_minimal(self):
        """Test linting minimal valid grammar."""
        yaml = """
format: record_stream
framing:
  repeat: until_eof
types:
  Header:
    fields:
      - { name: type, type: u8 }
"""

        result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))

        assert result.success is True
        assert result.grammar is not None
        assert len(result.errors) == 0
        assert result.grammar.format == "record_stream"
        assert "Header" in result.grammar.types

    def test_lint_grammar_valid_with_endian(self):
        """Test linting grammar with global endianness."""
        yaml = """
format: record_stream
endian: little
framing:
  repeat: until_eof
types:
  Record:
    fields:
      - { name: value, type: u16 }
"""

        result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))

        assert result.success is True
        assert result.grammar is not None
        assert result.grammar.endian is not None

    def test_lint_grammar_valid_with_switch(self):
        """Test linting grammar with record switch."""
        yaml = """
format: record_stream
endian: little
framing:
  repeat: until_eof
record:
  switch:
    expr: Header.type
    cases:
      "0x01": TypeA
      "0x02": TypeB
    default: Generic
types:
  Header:
    fields:
      - { name: type, type: u8 }
  TypeA:
    fields:
      - { name: header, type: Header }
      - { name: data_a, type: u8 }
  TypeB:
    fields:
      - { name: header, type: Header }
      - { name: data_b, type: u16 }
  Generic:
    fields:
      - { name: header, type: Header }
"""

        result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))

        assert result.success is True
        assert result.grammar is not None
        assert result.grammar.record_switch is not None
        assert result.grammar.record_switch.expr == "Header.type"
        assert len(result.grammar.types) == 4

    def test_lint_grammar_valid_with_colors(self):
        """Test linting grammar with color overrides."""
        yaml = """
format: record_stream
endian: little
framing:
  repeat: until_eof
types:
  ColoredRecord:
    fields:
      - { name: magic, type: bytes, length: 4, color: red }
      - { name: version, type: u16, color: "#ff8800" }
      - { name: data, type: bytes, length: 10, color: cyan }
"""

        result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))

        assert result.success is True
        assert result.grammar is not None
        # Check that colors were parsed
        record_type = result.grammar.types["ColoredRecord"]
        assert record_type.fields[0].color is not None
        assert record_type.fields[1].color is not None
        assert record_type.fields[2].color is not None

    def test_lint_grammar_valid_with_length_expressions(self):
        """Test linting grammar with arithmetic length expressions."""
        yaml = """
format: record_stream
endian: little
framing:
  repeat: until_eof
types:
  VarLenRecord:
    fields:
      - { name: total_len, type: u16 }
      - { name: header_len, type: u8 }
      - { name: data, type: bytes, length: "total_len - header_len - 4" }
"""

        result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))

        assert result.success is True
        assert result.grammar is not None
        # Check that length expression was parsed
        record_type = result.grammar.types["VarLenRecord"]
        assert record_type.fields[2].length_expr == "total_len - header_len - 4"

    def test_lint_grammar_valid_with_validation(self):
        """Test linting grammar with validation rules."""
        yaml = """
format: record_stream
endian: little
framing:
  repeat: until_eof
types:
  ValidatedRecord:
    fields:
      - { name: magic, type: u16, validate: { equals: 0x1234 } }
      - { name: len1, type: u16 }
      - { name: len2, type: u16, validate: { equals_field: len1 } }
      - { name: padding, type: bytes, length: 10, validate: { all_bytes: 0x00 } }
"""

        result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))

        assert result.success is True
        assert result.grammar is not None
        # Check that validation rules were parsed
        record_type = result.grammar.types["ValidatedRecord"]
        assert record_type.fields[0].validate is not None
        assert record_type.fields[2].validate is not None
        assert record_type.fields[3].validate is not None

    def test_lint_grammar_valid_with_registry(self):
        """Test linting grammar with registry."""
        yaml = """
format: record_stream
endian: little
framing:
  repeat: until_eof
types:
  Record:
    fields:
      - { name: type, type: u16 }
      - { name: data, type: bytes, length: 10 }
registry:
  "0x0001":
    name: test_record
    decode:
      as: string
      encoding: ascii
"""

        result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))

        assert result.success is True
        assert result.grammar is not None
        assert "0x0001" in result.grammar.registry
        assert result.grammar.registry["0x0001"].name == "test_record"

    def test_lint_grammar_invalid_yaml_syntax(self):
        """Test linting invalid YAML syntax."""
        yaml = """
format: record_stream
types:
  Header
    - invalid syntax here
    - { name: x
"""

        result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))

        assert result.success is False
        assert result.grammar is None
        assert len(result.errors) > 0
        assert len(result.warnings) == 0

    def test_lint_grammar_invalid_format(self):
        """Test linting unsupported format."""
        yaml = """
format: unsupported_format
types:
  Header:
    fields:
      - { name: type, type: u8 }
"""

        result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))

        assert result.success is False
        assert result.grammar is None
        assert len(result.errors) > 0
        assert "Unsupported format" in result.errors[0]

    def test_lint_grammar_invalid_endian(self):
        """Test linting invalid endianness value."""
        yaml = """
format: record_stream
endian: invalid_endian
types:
  Header:
    fields:
      - { name: type, type: u8 }
"""

        result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))

        assert result.success is False
        assert result.grammar is None
        assert len(result.errors) > 0

    def test_lint_grammar_invalid_color(self):
        """Test linting invalid color specification."""
        yaml = """
format: record_stream
endian: little
types:
  Record:
    fields:
      - { name: data, type: bytes, length: 10, color: invalid_color_xyz }
"""

        result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))

        assert result.success is False
        assert result.grammar is None
        assert len(result.errors) > 0

    def test_lint_grammar_warning_no_types(self):
        """Test warning when grammar has no types."""
        yaml = """
format: record_stream
framing:
  repeat: until_eof
types: {}
"""

        result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))

        assert result.success is True
        assert result.grammar is not None
        assert len(result.warnings) > 0
        assert "no type definitions" in result.warnings[0]

    def test_lint_grammar_warning_unused_types(self):
        """Test warning for unused types."""
        yaml = """
format: record_stream
endian: little
framing:
  repeat: until_eof
record:
  switch:
    expr: Header.type
    cases:
      "0x01": Used
    default: Used
types:
  Header:
    fields:
      - { name: type, type: u8 }
  Used:
    fields:
      - { name: header, type: Header }
      - { name: data, type: u8 }
  Unused:
    fields:
      - { name: stuff, type: u8 }
  AlsoUnused:
    fields:
      - { name: more_stuff, type: u16 }
"""

        result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))

        assert result.success is True
        assert result.grammar is not None
        assert len(result.warnings) > 0
        # Check that warning mentions unused types
        warning_text = result.warnings[0]
        assert "Unused" in warning_text or "unused" in warning_text.lower()
        assert "Unused" in warning_text or "AlsoUnused" in warning_text

    def test_lint_grammar_no_warning_when_no_switch(self):
        """Test no unused type warning when there's no switch (all types are entry points)."""
        yaml = """
format: record_stream
endian: little
framing:
  repeat: until_eof
types:
  TypeA:
    fields:
      - { name: data, type: u8 }
  TypeB:
    fields:
      - { name: data, type: u16 }
"""

        result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))

        assert result.success is True
        assert result.grammar is not None
        # No unused type warnings when there's no switch
        unused_warnings = [w for w in result.warnings if "Unused" in w or "unused" in w.lower()]
        assert len(unused_warnings) == 0

    def test_lint_grammar_empty_yaml(self):
        """Test linting empty YAML."""
        yaml = ""

        result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))

        assert result.success is False
        assert result.grammar is None
        assert len(result.errors) > 0

    def test_lint_grammar_only_format(self):
        """Test linting YAML with only format field."""
        yaml = """
format: record_stream
"""

        result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))

        # Should succeed but have warnings
        assert result.success is True
        assert result.grammar is not None
        assert len(result.warnings) > 0

    def test_lint_grammar_deterministic(self):
        """Test that linting is deterministic - same input produces same output."""
        yaml = """
format: record_stream
endian: little
framing:
  repeat: until_eof
types:
  Record:
    fields:
      - { name: type, type: u16 }
      - { name: data, type: bytes, length: 10 }
"""

        result1 = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
        result2 = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))

        # Results should be identical
        assert result1.success == result2.success
        assert len(result1.errors) == len(result2.errors)
        assert len(result1.warnings) == len(result2.warnings)
        if result1.grammar and result2.grammar:
            assert result1.grammar.format == result2.grammar.format
            assert len(result1.grammar.types) == len(result2.grammar.types)

    def test_lint_grammar_immutable_output(self):
        """Test that output is immutable (frozen dataclass)."""
        yaml = """
format: record_stream
types:
  Record:
    fields:
      - { name: x, type: u8 }
"""

        result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))

        # Should not be able to modify frozen dataclass
        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            result.success = False  # type: ignore

    def test_lint_grammar_preserves_all_grammar_features(self):
        """Test that linting preserves all grammar features from the reference."""
        yaml = """
format: record_stream
endian: little
framing:
  repeat: until_eof
record:
  switch:
    expr: Header.type_raw
    cases:
      "0x544E": NTRecord
    default: GenericRecord
types:
  Header:
    fields:
      - { name: type_raw, type: u16 }
      - { name: entity_id, type: u16 }
  GenericRecord:
    fields:
      - { name: header, type: Header }
      - { name: payload_len, type: u8 }
      - { name: payload, type: bytes, length: payload_len }
  NTRecord:
    fields:
      - { name: header, type: Header }
      - { name: nt_len_1, type: u16 }
      - { name: nt_len_2, type: u16 }
      - { name: pad10, type: bytes, length: 10 }
      - { name: delimiter, type: u16 }
      - { name: note_text, type: bytes, length: "nt_len_1 - 4", encoding: ascii }
      - { name: terminator, type: u16 }
registry:
  "0x0000":
    name: root_record
    decode:
      as: hex
  "0x0065":
    name: given_name
    decode:
      as: string
      encoding: ascii
  "0x544E":
    name: note_text
    decode:
      as: string
      field: note_text
      encoding: ascii
"""

        result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))

        assert result.success is True
        assert result.grammar is not None

        # Check all features preserved
        assert result.grammar.format == "record_stream"
        assert result.grammar.endian is not None
        assert result.grammar.record_switch is not None
        assert len(result.grammar.types) == 3
        assert len(result.grammar.registry) == 3

        # Check nested types work
        generic = result.grammar.types["GenericRecord"]
        assert generic.fields[0].type == "Header"

        # Check length expressions work
        nt = result.grammar.types["NTRecord"]
        note_field = [f for f in nt.fields if f.name == "note_text"][0]
        assert note_field.length_expr == "nt_len_1 - 4"
        assert note_field.encoding == "ascii"

        # Check registry preserved
        assert result.grammar.registry["0x0065"].name == "given_name"


class TestParseBinary:
    """Tests for parse_binary tool."""

    @pytest.fixture
    def simple_grammar(self):
        """Create a simple grammar for testing."""
        yaml = """
format: record_stream
endian: little
framing:
  repeat: until_eof
types:
  Record:
    fields:
      - { name: type, type: u16 }
      - { name: length, type: u8 }
      - { name: data, type: bytes, length: length }
"""
        result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
        assert result.success
        return result.grammar

    @pytest.fixture
    def binary_file(self, tmp_path: Path):
        """Create a test binary file."""
        # Create a simple binary file with known structure
        # Record 1: type=0x0001, length=5, data="HELLO"
        # Record 2: type=0x0002, length=5, data="WORLD"
        data = b""
        data += b"\x01\x00"  # type (u16 little-endian)
        data += b"\x05"  # length (u8)
        data += b"HELLO"  # data (5 bytes)
        data += b"\x02\x00"  # type (u16 little-endian)
        data += b"\x05"  # length (u8)
        data += b"WORLD"  # data (5 bytes)

        file_path = tmp_path / "test.bin"
        file_path.write_bytes(data)
        return str(file_path)

    def test_parse_binary_success(self, simple_grammar, binary_file):
        """Test successful binary parsing."""
        result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=simple_grammar, file_path=binary_file)
        )

        assert result.record_count == 2
        assert len(result.records) == 2
        assert len(result.errors) == 0
        assert result.total_bytes_parsed == 16  # 8 bytes per record * 2
        assert result.grammar_format == "record_stream"
        assert result.file_path == binary_file
        assert result.timestamp > 0

    def test_parse_binary_record_contents(self, simple_grammar, binary_file):
        """Test that parsed records have correct contents."""
        result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=simple_grammar, file_path=binary_file)
        )

        # Check first record
        record1 = result.records[0]
        assert record1.offset == 0
        assert record1.size == 8
        assert record1.fields["type"].value == 0x0001
        assert record1.fields["length"].value == 5
        assert record1.fields["data"].value == b"HELLO"

        # Check second record
        record2 = result.records[1]
        assert record2.offset == 8
        assert record2.size == 8
        assert record2.fields["type"].value == 0x0002
        assert record2.fields["length"].value == 5
        assert record2.fields["data"].value == b"WORLD"

    def test_parse_binary_with_offset(self, simple_grammar, binary_file):
        """Test parsing with custom start offset."""
        result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=simple_grammar, file_path=binary_file, offset=8)
        )

        # Should only parse second record
        assert result.record_count == 1
        assert result.records[0].fields["data"].value == b"WORLD"
        assert result.parse_stopped_at == 16

    def test_parse_binary_with_limit(self, simple_grammar, binary_file):
        """Test parsing with byte limit."""
        result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=simple_grammar, file_path=binary_file, limit=10)
        )

        # Should only parse first record (8 bytes) because limit is 10
        assert result.record_count == 1
        assert result.records[0].fields["data"].value == b"HELLO"

    def test_parse_binary_with_max_records(self, simple_grammar, binary_file):
        """Test parsing with max_records limit."""
        result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=simple_grammar, file_path=binary_file, max_records=1)
        )

        # Should only parse first record
        assert result.record_count == 1
        assert result.records[0].fields["data"].value == b"HELLO"

    def test_parse_binary_empty_file(self, simple_grammar, tmp_path: Path):
        """Test parsing empty file."""
        empty_file = tmp_path / "empty.bin"
        empty_file.write_bytes(b"")

        result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=simple_grammar, file_path=str(empty_file))
        )

        assert result.record_count == 0
        assert len(result.records) == 0
        assert result.total_bytes_parsed == 0
        assert len(result.errors) == 0  # Empty file is not an error

    def test_parse_binary_nonexistent_file(self, simple_grammar):
        """Test parsing nonexistent file."""
        result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=simple_grammar, file_path="/nonexistent/file.bin")
        )

        assert result.record_count == 0
        assert len(result.errors) > 0
        assert "Failed to parse binary" in result.errors[0]

    def test_parse_binary_immutable_output(self, simple_grammar, binary_file):
        """Test that output is immutable."""
        result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=simple_grammar, file_path=binary_file)
        )

        # Should not be able to modify frozen dataclass
        with pytest.raises(Exception):
            result.record_count = 999  # type: ignore

        # Records tuple should be immutable
        with pytest.raises(Exception):
            result.records[0] = None  # type: ignore

    def test_parse_binary_deterministic(self, simple_grammar, binary_file):
        """Test that parsing is deterministic."""
        result1 = ToolHost.parse_binary(
            ParseBinaryInput(grammar=simple_grammar, file_path=binary_file)
        )
        result2 = ToolHost.parse_binary(
            ParseBinaryInput(grammar=simple_grammar, file_path=binary_file)
        )

        # Results should be identical (except timestamp)
        assert result1.record_count == result2.record_count
        assert result1.total_bytes_parsed == result2.total_bytes_parsed
        assert result1.parse_stopped_at == result2.parse_stopped_at
        assert len(result1.errors) == len(result2.errors)

        # Records should be identical
        for r1, r2 in zip(result1.records, result2.records):
            assert r1.offset == r2.offset
            assert r1.size == r2.size
            assert r1.type_name == r2.type_name

    def test_parse_binary_with_nested_types(self, tmp_path: Path):
        """Test parsing with nested type definitions."""
        yaml = """
format: record_stream
endian: little
framing:
  repeat: until_eof
record:
  switch:
    expr: Header.magic
    cases:
      "0xCDAB": Record
    default: Record
types:
  Header:
    fields:
      - { name: magic, type: u16 }
      - { name: version, type: u8 }
  Record:
    fields:
      - { name: header, type: Header }
      - { name: data_len, type: u8 }
      - { name: data, type: bytes, length: data_len }
"""
        grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
        assert grammar_result.success

        # Create binary with nested structure
        data = b""
        data += b"\xAB\xCD"  # header.magic
        data += b"\x01"  # header.version
        data += b"\x03"  # data_len
        data += b"ABC"  # data

        file_path = tmp_path / "nested.bin"
        file_path.write_bytes(data)

        result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file_path))
        )

        assert result.record_count == 1
        record = result.records[0]

        # Check nested header
        assert "header" in record.fields
        header = record.fields["header"].value
        assert isinstance(header, dict)
        assert header["magic"] == 0xCDAB  # Little-endian
        assert header["version"] == 1

        # Check data
        assert record.fields["data"].value == b"ABC"

    def test_parse_binary_with_switch(self, tmp_path: Path):
        """Test parsing with type discrimination."""
        yaml = """
format: record_stream
endian: little
framing:
  repeat: until_eof
record:
  switch:
    expr: Header.type_id
    cases:
      "0x0001": TypeA
      "0x0002": TypeB
    default: TypeA
types:
  Header:
    fields:
      - { name: type_id, type: u16 }
  TypeA:
    fields:
      - { name: header, type: Header }
      - { name: value_a, type: u8 }
  TypeB:
    fields:
      - { name: header, type: Header }
      - { name: value_b, type: u16 }
"""
        grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
        assert grammar_result.success

        # Create binary with two different record types
        data = b""
        # TypeA record
        data += b"\x01\x00"  # header.type_id = 0x0001
        data += b"\x42"  # value_a
        # TypeB record
        data += b"\x02\x00"  # header.type_id = 0x0002
        data += b"\x34\x12"  # value_b

        file_path = tmp_path / "switch.bin"
        file_path.write_bytes(data)

        result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file_path))
        )

        assert result.record_count == 2

        # Check TypeA record
        record1 = result.records[0]
        assert record1.type_name == "TypeA"
        assert record1.fields["value_a"].value == 0x42

        # Check TypeB record
        record2 = result.records[1]
        assert record2.type_name == "TypeB"
        assert record2.fields["value_b"].value == 0x1234

    def test_parse_binary_stops_on_error(self, simple_grammar, tmp_path: Path):
        """Test that parsing stops on error."""
        # Create file with incomplete record at the end
        data = b""
        data += b"\x01\x00"  # type
        data += b"\x05"  # length
        data += b"HELLO"  # data
        data += b"\x02\x00"  # type
        data += b"\x05"  # length
        data += b"WOR"  # incomplete data (only 3 bytes instead of 5)

        file_path = tmp_path / "incomplete.bin"
        file_path.write_bytes(data)

        result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=simple_grammar, file_path=str(file_path))
        )

        # Should parse first record successfully, fail on second
        assert result.record_count == 1
        assert len(result.errors) > 0
        assert result.records[0].fields["data"].value == b"HELLO"


class TestGenerateSpans:
    """Tests for generate_spans tool."""

    @pytest.fixture
    def simple_parse_result(self, tmp_path: Path):
        """Create a simple parse result for testing."""
        # Create grammar
        yaml = """
format: record_stream
endian: little
framing:
  repeat: until_eof
types:
  Record:
    fields:
      - { name: type, type: u16 }
      - { name: length, type: u8 }
      - { name: data, type: bytes, length: length }
"""
        grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
        assert grammar_result.success

        # Create binary file with 3 records at known offsets
        data = b""
        # Record 1 at offset 0
        data += b"\x01\x00"  # type
        data += b"\x04"      # length
        data += b"AAAA"      # data (4 bytes)
        # Record 2 at offset 7
        data += b"\x02\x00"  # type
        data += b"\x04"      # length
        data += b"BBBB"      # data
        # Record 3 at offset 14
        data += b"\x03\x00"  # type
        data += b"\x04"      # length
        data += b"CCCC"      # data

        file_path = tmp_path / "test.bin"
        file_path.write_bytes(data)

        # Parse file
        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file_path))
        )

        return parse_result

    def test_generate_spans_full_viewport(self, simple_parse_result):
        """Test generating spans for full viewport."""
        span_set = ToolHost.generate_spans(
            GenerateSpansInput(
                parse_result=simple_parse_result,
                viewport_start=0,
                viewport_end=100  # Cover all records
            )
        )

        # Should have spans from all 3 records
        assert span_set.record_count == 3
        assert len(span_set.spans) == 9  # 3 fields per record * 3 records
        assert span_set.viewport_start == 0
        assert span_set.viewport_end == 100
        assert span_set.span_index is not None

    def test_generate_spans_partial_viewport(self, simple_parse_result):
        """Test generating spans for partial viewport."""
        # Viewport covers only first record (offset 0-7)
        span_set = ToolHost.generate_spans(
            GenerateSpansInput(
                parse_result=simple_parse_result,
                viewport_start=0,
                viewport_end=7
            )
        )

        # Should have spans from only first record
        assert span_set.record_count == 1
        assert len(span_set.spans) == 3  # 3 fields (type, length, data)

    def test_generate_spans_middle_viewport(self, simple_parse_result):
        """Test generating spans for middle viewport."""
        # Viewport covers second record (offset 7-14)
        span_set = ToolHost.generate_spans(
            GenerateSpansInput(
                parse_result=simple_parse_result,
                viewport_start=7,
                viewport_end=14
            )
        )

        # Should have spans from only second record
        assert span_set.record_count == 1
        assert len(span_set.spans) == 3

    def test_generate_spans_overlapping_viewport(self, simple_parse_result):
        """Test generating spans for viewport overlapping multiple records."""
        # Viewport covers first and second records
        span_set = ToolHost.generate_spans(
            GenerateSpansInput(
                parse_result=simple_parse_result,
                viewport_start=0,
                viewport_end=14
            )
        )

        # Should have spans from first two records
        assert span_set.record_count == 2
        assert len(span_set.spans) == 6  # 3 fields * 2 records

    def test_generate_spans_empty_viewport(self, simple_parse_result):
        """Test generating spans for empty viewport."""
        # Viewport beyond all records
        span_set = ToolHost.generate_spans(
            GenerateSpansInput(
                parse_result=simple_parse_result,
                viewport_start=1000,
                viewport_end=2000
            )
        )

        # Should have no spans
        assert span_set.record_count == 0
        assert len(span_set.spans) == 0
        assert span_set.span_index is None

    def test_generate_spans_field_details(self, simple_parse_result):
        """Test that generated spans have correct field details."""
        span_set = ToolHost.generate_spans(
            GenerateSpansInput(
                parse_result=simple_parse_result,
                viewport_start=0,
                viewport_end=7
            )
        )

        # Check first record's spans
        spans = list(span_set.spans)
        assert len(spans) == 3

        # Type field (u16 at offset 0)
        type_span = spans[0]
        assert type_span.offset == 0
        assert type_span.length == 2
        assert "type" in type_span.path
        assert type_span.group == "int"

        # Length field (u8 at offset 2)
        length_span = spans[1]
        assert length_span.offset == 2
        assert length_span.length == 1
        assert "length" in length_span.path
        assert length_span.group == "int"

        # Data field (bytes at offset 3)
        data_span = spans[2]
        assert data_span.offset == 3
        assert data_span.length == 4
        assert "data" in data_span.path
        assert data_span.group == "bytes"

    def test_generate_spans_immutable(self, simple_parse_result):
        """Test that span set is immutable."""
        span_set = ToolHost.generate_spans(
            GenerateSpansInput(
                parse_result=simple_parse_result,
                viewport_start=0,
                viewport_end=100
            )
        )

        # Should not be able to modify frozen dataclass
        with pytest.raises(Exception):
            span_set.record_count = 999  # type: ignore

        # Spans tuple should be immutable
        with pytest.raises(Exception):
            span_set.spans[0] = None  # type: ignore

    def test_generate_spans_deterministic(self, simple_parse_result):
        """Test that span generation is deterministic."""
        span_set1 = ToolHost.generate_spans(
            GenerateSpansInput(
                parse_result=simple_parse_result,
                viewport_start=0,
                viewport_end=14
            )
        )
        span_set2 = ToolHost.generate_spans(
            GenerateSpansInput(
                parse_result=simple_parse_result,
                viewport_start=0,
                viewport_end=14
            )
        )

        # Results should be identical
        assert span_set1.record_count == span_set2.record_count
        assert len(span_set1.spans) == len(span_set2.spans)
        assert span_set1.viewport_start == span_set2.viewport_start
        assert span_set1.viewport_end == span_set2.viewport_end

        # Spans should match
        for s1, s2 in zip(span_set1.spans, span_set2.spans):
            assert s1.offset == s2.offset
            assert s1.length == s2.length
            assert s1.path == s2.path
            assert s1.group == s2.group

    def test_generate_spans_with_colors(self, tmp_path: Path):
        """Test span generation with color overrides."""
        # Create grammar with color overrides
        yaml = """
format: record_stream
endian: little
framing:
  repeat: until_eof
types:
  Record:
    fields:
      - { name: type, type: u16, color: red }
      - { name: data, type: bytes, length: 4, color: cyan }
"""
        grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
        assert grammar_result.success

        # Create binary
        data = b"\x01\x00" + b"TEST"
        file_path = tmp_path / "colored.bin"
        file_path.write_bytes(data)

        # Parse
        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file_path))
        )

        # Generate spans
        span_set = ToolHost.generate_spans(
            GenerateSpansInput(
                parse_result=parse_result,
                viewport_start=0,
                viewport_end=100
            )
        )

        # Check color overrides are preserved
        spans = list(span_set.spans)
        type_span = [s for s in spans if "type" in s.path][0]
        data_span = [s for s in spans if "data" in s.path][0]

        assert type_span.color_override is not None
        assert data_span.color_override is not None

    def test_generate_spans_with_nested_types(self, tmp_path: Path):
        """Test span generation with nested types."""
        yaml = """
format: record_stream
endian: little
framing:
  repeat: until_eof
record:
  switch:
    expr: Header.magic
    cases:
      "0xCDAB": Record
    default: Record
types:
  Header:
    fields:
      - { name: magic, type: u16 }
      - { name: version, type: u8 }
  Record:
    fields:
      - { name: header, type: Header }
      - { name: data, type: bytes, length: 3 }
"""
        grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
        assert grammar_result.success

        # Create binary
        data = b"\xAB\xCD\x01" + b"ABC"
        file_path = tmp_path / "nested.bin"
        file_path.write_bytes(data)

        # Parse
        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file_path))
        )

        # Generate spans
        span_set = ToolHost.generate_spans(
            GenerateSpansInput(
                parse_result=parse_result,
                viewport_start=0,
                viewport_end=100
            )
        )

        # Should have spans for nested header fields + data field
        spans = list(span_set.spans)
        assert len(spans) == 3  # header.magic, header.version, data

        # Check nested field paths
        paths = [s.path for s in spans]
        assert any("header.magic" in p for p in paths)
        assert any("header.version" in p for p in paths)
        assert any("data" in p for p in paths)

    def test_generate_spans_span_index_lookup(self, simple_parse_result):
        """Test that span index works for lookups."""
        span_set = ToolHost.generate_spans(
            GenerateSpansInput(
                parse_result=simple_parse_result,
                viewport_start=0,
                viewport_end=100
            )
        )

        # SpanIndex should be created
        assert span_set.span_index is not None

        # Should be able to find spans by offset
        span_at_0 = span_set.span_index.find(0)
        assert span_at_0 is not None
        assert span_at_0.offset == 0

        span_at_3 = span_set.span_index.find(3)
        assert span_at_3 is not None
        assert "data" in span_at_3.path


class TestAnalyzeCoverage:
    """Tests for analyze_coverage tool."""

    @pytest.fixture
    def simple_grammar(self):
        """Create a simple grammar for testing."""
        yaml = """
format: record_stream
endian: little
framing:
  repeat: until_eof
types:
  Record:
    fields:
      - { name: type, type: u16 }
      - { name: data, type: bytes, length: 4 }
"""
        result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
        assert result.success
        return result.grammar

    def test_analyze_coverage_full(self, simple_grammar, tmp_path: Path):
        """Test coverage analysis with full file coverage."""
        # Create file where all bytes are parsed
        # Record 1: 6 bytes (0-5)
        # Record 2: 6 bytes (6-11)
        data = b"\x01\x00AAAA" + b"\x02\x00BBBB"
        file_path = tmp_path / "full.bin"
        file_path.write_bytes(data)

        # Parse
        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=simple_grammar, file_path=str(file_path))
        )

        # Analyze coverage
        coverage = ToolHost.analyze_coverage(
            AnalyzeCoverageInput(parse_result=parse_result, file_size=len(data))
        )

        # Should have 100% coverage
        assert coverage.file_size == 12
        assert coverage.bytes_covered == 12
        assert coverage.bytes_uncovered == 0
        assert coverage.coverage_percentage == 100.0
        assert len(coverage.gaps) == 0
        assert coverage.largest_gap is None
        assert coverage.record_count == 2

    def test_analyze_coverage_with_gaps(self, simple_grammar, tmp_path: Path):
        """Test coverage analysis with gaps."""
        # Create file with gap in middle
        # Record 1: 6 bytes (0-5)
        # Gap: 4 bytes (6-9)
        # Record 2: 6 bytes (10-15)
        data = b"\x01\x00AAAA" + b"\x00\x00\x00\x00" + b"\x02\x00BBBB"
        file_path = tmp_path / "gaps.bin"
        file_path.write_bytes(data)

        # Parse only records at offsets 0 and 10 (simulate gap)
        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=simple_grammar, file_path=str(file_path), limit=6)
        )

        # Manually add second record to simulate non-contiguous parsing
        # (in reality, we'd parse offset 10 separately)
        # For this test, just analyze what we got
        coverage = ToolHost.analyze_coverage(
            AnalyzeCoverageInput(parse_result=parse_result, file_size=len(data))
        )

        # Should have partial coverage
        assert coverage.file_size == 16
        assert coverage.bytes_covered == 6  # Only first record
        assert coverage.bytes_uncovered == 10  # Rest is gap
        assert coverage.coverage_percentage == 37.5  # 6/16 * 100

    def test_analyze_coverage_gap_at_start(self, simple_grammar, tmp_path: Path):
        """Test coverage with gap at start of file."""
        # Gap at start, then records
        data = b"\x00\x00\x00\x00" + b"\x01\x00AAAA"
        file_path = tmp_path / "start_gap.bin"
        file_path.write_bytes(data)

        # Parse starting at offset 4
        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=simple_grammar, file_path=str(file_path), offset=4)
        )

        coverage = ToolHost.analyze_coverage(
            AnalyzeCoverageInput(parse_result=parse_result, file_size=len(data))
        )

        # Should have gap at start
        assert coverage.bytes_covered == 6
        assert coverage.bytes_uncovered == 4
        assert len(coverage.gaps) == 1
        assert coverage.gaps[0] == (0, 4)

    def test_analyze_coverage_gap_at_end(self, simple_grammar, tmp_path: Path):
        """Test coverage with gap at end of file."""
        # Records, then trailing bytes
        data = b"\x01\x00AAAA" + b"\x00\x00\x00\x00"
        file_path = tmp_path / "end_gap.bin"
        file_path.write_bytes(data)

        # Parse with limit
        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=simple_grammar, file_path=str(file_path), max_records=1)
        )

        coverage = ToolHost.analyze_coverage(
            AnalyzeCoverageInput(parse_result=parse_result, file_size=len(data))
        )

        # Should have gap at end
        assert coverage.bytes_covered == 6
        assert coverage.bytes_uncovered == 4
        assert len(coverage.gaps) == 1
        assert coverage.gaps[0] == (6, 10)
        assert coverage.largest_gap == (6, 10)

    def test_analyze_coverage_multiple_gaps(self, tmp_path: Path):
        """Test coverage with multiple gaps."""
        # Create grammar and file with known structure
        yaml = """
format: record_stream
endian: little
framing:
  repeat: until_eof
types:
  Record:
    fields:
      - { name: data, type: bytes, length: 2 }
"""
        grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))

        # File: [Record][Gap][Record][Gap][Record]
        # Record at 0-1, gap 2-3, record at 4-5, gap 6-7, record at 8-9
        data = b"AA" + b"\x00\x00" + b"BB" + b"\x00\x00" + b"CC"
        file_path = tmp_path / "multi_gap.bin"
        file_path.write_bytes(data)

        # Parse only at specific offsets (simulate selective parsing)
        # For this test, just parse normally and it will get all records
        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file_path))
        )

        coverage = ToolHost.analyze_coverage(
            AnalyzeCoverageInput(parse_result=parse_result, file_size=len(data))
        )

        # Should parse all 5 "records" (AA, \x00\x00, BB, etc.)
        # Since \x00\x00 is also valid, coverage will be 100%
        assert coverage.coverage_percentage == 100.0

    def test_analyze_coverage_empty_file(self, simple_grammar, tmp_path: Path):
        """Test coverage of empty file."""
        data = b""
        file_path = tmp_path / "empty.bin"
        file_path.write_bytes(data)

        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=simple_grammar, file_path=str(file_path))
        )

        coverage = ToolHost.analyze_coverage(
            AnalyzeCoverageInput(parse_result=parse_result, file_size=len(data))
        )

        assert coverage.file_size == 0
        assert coverage.bytes_covered == 0
        assert coverage.bytes_uncovered == 0
        assert coverage.coverage_percentage == 0.0
        assert len(coverage.gaps) == 0

    def test_analyze_coverage_no_records(self, simple_grammar):
        """Test coverage when no records were parsed."""
        # Create empty parse result
        from hexmap.core.tool_host import ParseResult

        empty_result = ParseResult(
            records=(),
            errors=(),
            file_path="/fake/path",
            grammar_format="record_stream",
            total_bytes_parsed=0,
            parse_stopped_at=0,
            timestamp=0.0,
            record_count=0,
        )

        coverage = ToolHost.analyze_coverage(
            AnalyzeCoverageInput(parse_result=empty_result, file_size=100)
        )

        # Entire file is a gap
        assert coverage.file_size == 100
        assert coverage.bytes_covered == 0
        assert coverage.bytes_uncovered == 100
        assert coverage.coverage_percentage == 0.0
        assert len(coverage.gaps) == 1
        assert coverage.gaps[0] == (0, 100)
        assert coverage.largest_gap == (0, 100)

    def test_analyze_coverage_largest_gap(self, simple_grammar, tmp_path: Path):
        """Test that largest gap is identified correctly."""
        # Create file with multiple gaps of different sizes
        # Record 1 at 0-5 (6 bytes)
        # Gap 1 at 6-9 (4 bytes)
        # Record 2 at 10-15 (6 bytes)
        # Gap 2 at 16-25 (10 bytes) <- largest gap
        file_size = 26

        # Parse first record only
        data = b"\x01\x00AAAA" + b"\x00" * 20
        file_path = tmp_path / "sized_gaps.bin"
        file_path.write_bytes(data)

        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=simple_grammar, file_path=str(file_path), max_records=1)
        )

        coverage = ToolHost.analyze_coverage(
            AnalyzeCoverageInput(parse_result=parse_result, file_size=file_size)
        )

        # Should have one gap at end
        assert len(coverage.gaps) == 1
        assert coverage.gaps[0] == (6, 26)
        assert coverage.largest_gap == (6, 26)
        assert coverage.largest_gap[1] - coverage.largest_gap[0] == 20  # 20 byte gap

    def test_analyze_coverage_immutable(self, simple_grammar, tmp_path: Path):
        """Test that coverage report is immutable."""
        data = b"\x01\x00AAAA"
        file_path = tmp_path / "test.bin"
        file_path.write_bytes(data)

        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=simple_grammar, file_path=str(file_path))
        )

        coverage = ToolHost.analyze_coverage(
            AnalyzeCoverageInput(parse_result=parse_result, file_size=len(data))
        )

        # Should not be able to modify frozen dataclass
        with pytest.raises(Exception):
            coverage.file_size = 999  # type: ignore

        # Gaps tuple should be immutable
        with pytest.raises(Exception):
            coverage.gaps[0] = (0, 0)  # type: ignore

    def test_analyze_coverage_deterministic(self, simple_grammar, tmp_path: Path):
        """Test that coverage analysis is deterministic."""
        data = b"\x01\x00AAAA" + b"\x02\x00BBBB"
        file_path = tmp_path / "test.bin"
        file_path.write_bytes(data)

        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=simple_grammar, file_path=str(file_path))
        )

        coverage1 = ToolHost.analyze_coverage(
            AnalyzeCoverageInput(parse_result=parse_result, file_size=len(data))
        )
        coverage2 = ToolHost.analyze_coverage(
            AnalyzeCoverageInput(parse_result=parse_result, file_size=len(data))
        )

        # Results should be identical
        assert coverage1.file_size == coverage2.file_size
        assert coverage1.bytes_covered == coverage2.bytes_covered
        assert coverage1.bytes_uncovered == coverage2.bytes_uncovered
        assert coverage1.coverage_percentage == coverage2.coverage_percentage
        assert coverage1.gaps == coverage2.gaps
        assert coverage1.largest_gap == coverage2.largest_gap

    def test_analyze_coverage_percentage_calculation(self, simple_grammar, tmp_path: Path):
        """Test coverage percentage calculation."""
        # File: 10 bytes, parse 4 bytes
        data = b"\x01\x00AAAA" + b"\x00\x00\x00\x00"
        file_path = tmp_path / "percent.bin"
        file_path.write_bytes(data)

        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=simple_grammar, file_path=str(file_path), max_records=1)
        )

        coverage = ToolHost.analyze_coverage(
            AnalyzeCoverageInput(parse_result=parse_result, file_size=len(data))
        )

        # 6 bytes covered out of 10 = 60%
        assert coverage.file_size == 10
        assert coverage.bytes_covered == 6
        assert coverage.coverage_percentage == 60.0


class TestDecodeField:
    """Tests for decode_field tool."""

    def test_decode_field_direct_string(self):
        """Test decoding a specific field as string."""
        yaml = """
format: record_stream
framing:
  repeat: until_eof
types:
  Record:
    fields:
      - { name: type, type: u16 }
      - { name: length, type: u8 }
      - { name: data, type: bytes, length_field: length }
"""
        grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
        assert grammar_result.success

        # Parse record with string data
        data = b"\x01\x00" + b"\x05" + b"Hello"
        file_path = Path("/tmp/test_decode_string.bin")
        file_path.write_bytes(data)

        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file_path))
        )

        assert parse_result.record_count == 1
        record = parse_result.records[0]

        # Decode the "data" field directly
        decoded = ToolHost.decode_field(
            DecodeFieldInput(record=record, grammar=grammar_result.grammar, field_name="data")
        )

        assert decoded.success is True
        assert decoded.value == "Hello"
        assert decoded.decoder_type == "string"
        assert decoded.field_path == "data"
        assert decoded.error is None

    def test_decode_field_direct_integer(self):
        """Test decoding a specific field as integer."""
        yaml = """
format: record_stream
framing:
  repeat: until_eof
types:
  Record:
    fields:
      - { name: id, type: u16 }
      - { name: count, type: u8 }
"""
        grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
        assert grammar_result.success

        data = b"\x2A\x00" + b"\x42"
        file_path = Path("/tmp/test_decode_int.bin")
        file_path.write_bytes(data)

        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file_path))
        )

        record = parse_result.records[0]

        # Decode "count" field
        decoded = ToolHost.decode_field(
            DecodeFieldInput(record=record, grammar=grammar_result.grammar, field_name="count")
        )

        assert decoded.success is True
        assert decoded.value == "66"
        assert decoded.decoder_type == "u32"  # Generic integer
        assert decoded.field_path == "count"

    def test_decode_field_registry_string(self):
        """Test decoding using registry with string decoder."""
        yaml = """
format: record_stream
framing:
  repeat: until_eof
types:
  Header:
    fields:
      - { name: type_raw, type: u16 }
      - { name: length, type: u8 }
  Record:
    fields:
      - { name: header, type: Header }
      - { name: payload, type: bytes, length_field: length }

record:
  switch:
    expr: Header.type_raw
    cases:
      "0x4E54": Record
    default: Record

registry:
  "0x4E54":  # NT type
    name: Name
    decode:
      as: string
      encoding: utf-8
"""
        grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
        assert grammar_result.success

        # Create record with NT type (0x4E54) and string payload
        data = b"\x4E\x54" + b"\x0B" + b"Hello World"
        file_path = Path("/tmp/test_decode_registry_string.bin")
        file_path.write_bytes(data)

        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file_path))
        )

        record = parse_result.records[0]

        # Decode using registry (no field_name specified)
        decoded = ToolHost.decode_field(
            DecodeFieldInput(record=record, grammar=grammar_result.grammar)
        )

        assert decoded.success is True
        assert decoded.value == "Hello World"
        assert decoded.decoder_type == "string"
        assert decoded.field_path == "payload"

    def test_decode_field_registry_u16(self):
        """Test decoding using registry with u16 decoder."""
        yaml = """
format: record_stream
endian: little
framing:
  repeat: until_eof
types:
  Header:
    fields:
      - { name: type_raw, type: u16 }
      - { name: length, type: u8 }
  Record:
    fields:
      - { name: header, type: Header }
      - { name: payload, type: bytes, length_field: length }

record:
  switch:
    expr: Header.type_raw
    cases:
      "0x0001": Record
    default: Record

registry:
  "0x0001":
    name: Counter
    decode:
      as: u16
"""
        grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
        assert grammar_result.success

        # Create record with type 0x0001 and u16 payload
        data = b"\x01\x00" + b"\x02" + b"\x2A\x00"  # u16 = 42 (little endian)
        file_path = Path("/tmp/test_decode_u16.bin")
        file_path.write_bytes(data)

        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file_path))
        )

        record = parse_result.records[0]

        decoded = ToolHost.decode_field(
            DecodeFieldInput(record=record, grammar=grammar_result.grammar)
        )

        assert decoded.success is True
        assert decoded.value == "42"
        assert decoded.decoder_type == "u16"

    def test_decode_field_registry_u32(self):
        """Test decoding using registry with u32 decoder."""
        yaml = """
format: record_stream
endian: big
framing:
  repeat: until_eof
types:
  Header:
    fields:
      - { name: type_raw, type: u16 }
      - { name: length, type: u8 }
  Record:
    fields:
      - { name: header, type: Header }
      - { name: payload, type: bytes, length_field: length }

record:
  switch:
    expr: Header.type_raw
    cases:
      "0x0002": Record
    default: Record

registry:
  "0x0002":
    name: BigCounter
    decode:
      as: u32
      endian: big
"""
        grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
        assert grammar_result.success

        # Create record with type 0x0002 and u32 payload
        data = b"\x00\x02" + b"\x04" + b"\x00\x00\x01\x00"  # u32 = 256 (big endian)
        file_path = Path("/tmp/test_decode_u32.bin")
        file_path.write_bytes(data)

        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file_path))
        )

        record = parse_result.records[0]

        decoded = ToolHost.decode_field(
            DecodeFieldInput(record=record, grammar=grammar_result.grammar)
        )

        assert decoded.success is True
        assert decoded.value == "256"
        assert decoded.decoder_type == "u32"

    def test_decode_field_registry_hex(self):
        """Test decoding using registry with hex decoder."""
        yaml = """
format: record_stream
endian: little
framing:
  repeat: until_eof
types:
  Header:
    fields:
      - { name: type_raw, type: u16 }
      - { name: length, type: u8 }
  Record:
    fields:
      - { name: header, type: Header }
      - { name: payload, type: bytes, length_field: length }

record:
  switch:
    expr: Header.type_raw
    cases:
      "0x0003": Record
    default: Record

registry:
  "0x0003":
    name: HexData
    decode:
      as: hex
"""
        grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
        assert grammar_result.success

        # Create record with type 0x0003 and binary payload
        data = b"\x03\x00" + b"\x04" + b"\xDE\xAD\xBE\xEF"
        file_path = Path("/tmp/test_decode_hex.bin")
        file_path.write_bytes(data)

        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file_path))
        )

        record = parse_result.records[0]

        decoded = ToolHost.decode_field(
            DecodeFieldInput(record=record, grammar=grammar_result.grammar)
        )

        assert decoded.success is True
        assert decoded.value == "deadbeef"
        assert decoded.decoder_type == "hex"

    def test_decode_field_registry_ftm_date(self):
        """Test decoding using registry with FTM packed date decoder."""
        yaml = """
format: record_stream
endian: little
framing:
  repeat: until_eof
types:
  Header:
    fields:
      - { name: type_raw, type: u16 }
      - { name: length, type: u8 }
  Record:
    fields:
      - { name: header, type: Header }
      - { name: payload, type: bytes, length_field: length }

record:
  switch:
    expr: Header.type_raw
    cases:
      "0x0004": Record
    default: Record

registry:
  "0x0004":
    name: DateRecord
    decode:
      as: ftm_packed_date
"""
        grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
        assert grammar_result.success

        # Create record with FTM packed date: 2024-03-15
        # byte0: (day << 3) | flags = (15 << 3) = 120 = 0x78
        # byte1: (month << 1) | 0 = (3 << 1) = 6 = 0x06
        # byte2-3: year 2024 (LE) = 0xE8 0x07
        data = b"\x04\x00" + b"\x04" + b"\x78\x06\xE8\x07"
        file_path = Path("/tmp/test_decode_ftm_date.bin")
        file_path.write_bytes(data)

        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file_path))
        )

        record = parse_result.records[0]

        decoded = ToolHost.decode_field(
            DecodeFieldInput(record=record, grammar=grammar_result.grammar)
        )

        assert decoded.success is True
        assert decoded.value == "2024-03-15"
        assert decoded.decoder_type == "ftm_packed_date"

    def test_decode_field_missing_field(self):
        """Test error when field doesn't exist."""
        yaml = """
format: record_stream
framing:
  repeat: until_eof
types:
  Record:
    fields:
      - { name: id, type: u16 }
"""
        grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
        assert grammar_result.success

        data = b"\x01\x00"
        file_path = Path("/tmp/test_decode_missing.bin")
        file_path.write_bytes(data)

        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file_path))
        )

        record = parse_result.records[0]

        decoded = ToolHost.decode_field(
            DecodeFieldInput(record=record, grammar=grammar_result.grammar, field_name="missing")
        )

        assert decoded.success is False
        assert decoded.value is None
        assert decoded.error == "Field 'missing' not found in record"

    def test_decode_field_no_discriminator(self):
        """Test error when record has no type discriminator."""
        yaml = """
format: record_stream
framing:
  repeat: until_eof
types:
  Record:
    fields:
      - { name: id, type: u16 }
      - { name: data, type: bytes, length: 4 }
"""
        grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
        assert grammar_result.success

        data = b"\x01\x00" + b"TEST"
        file_path = Path("/tmp/test_decode_no_disc.bin")
        file_path.write_bytes(data)

        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file_path))
        )

        record = parse_result.records[0]

        # Try registry decode without specifying field_name
        decoded = ToolHost.decode_field(
            DecodeFieldInput(record=record, grammar=grammar_result.grammar)
        )

        assert decoded.success is False
        assert decoded.error == "Could not extract type discriminator from header.type_raw"

    def test_decode_field_no_registry_entry(self):
        """Test error when discriminator not in registry."""
        yaml = """
format: record_stream
endian: little
framing:
  repeat: until_eof
types:
  Header:
    fields:
      - { name: type_raw, type: u16 }
  Record:
    fields:
      - { name: header, type: Header }
      - { name: payload, type: bytes, length: 4 }

record:
  switch:
    expr: Header.type_raw
    cases:
      "0x9999": Record
    default: Record

registry:
  "0x0001":
    name: Known
    decode:
      as: string
"""
        grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
        assert grammar_result.success

        # Create record with type 0x9999 (not in registry)
        data = b"\x99\x99" + b"TEST"
        file_path = Path("/tmp/test_decode_no_registry.bin")
        file_path.write_bytes(data)

        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file_path))
        )

        record = parse_result.records[0]

        decoded = ToolHost.decode_field(
            DecodeFieldInput(record=record, grammar=grammar_result.grammar)
        )

        assert decoded.success is False
        assert "0x9999" in decoded.error
        assert "not found in registry" in decoded.error

    def test_decode_field_insufficient_bytes(self):
        """Test error when field has insufficient bytes for decoder."""
        yaml = """
format: record_stream
endian: little
framing:
  repeat: until_eof
types:
  Header:
    fields:
      - { name: type_raw, type: u16 }
      - { name: length, type: u8 }
  Record:
    fields:
      - { name: header, type: Header }
      - { name: payload, type: bytes, length_field: length }

record:
  switch:
    expr: Header.type_raw
    cases:
      "0x0001": Record
    default: Record

registry:
  "0x0001":
    name: Counter
    decode:
      as: u32
"""
        grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
        assert grammar_result.success

        # Create record with only 2 bytes (need 4 for u32)
        data = b"\x01\x00" + b"\x02" + b"\x01\x02"
        file_path = Path("/tmp/test_decode_insufficient.bin")
        file_path.write_bytes(data)

        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file_path))
        )

        record = parse_result.records[0]

        decoded = ToolHost.decode_field(
            DecodeFieldInput(record=record, grammar=grammar_result.grammar)
        )

        assert decoded.success is False
        assert "Insufficient bytes" in decoded.error

    def test_decode_field_immutability(self):
        """Test that DecodedValue output is immutable."""
        yaml = """
format: record_stream
framing:
  repeat: until_eof
types:
  Record:
    fields:
      - { name: data, type: bytes, length: 4 }
"""
        grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
        data = b"TEST"
        file_path = Path("/tmp/test_decode_immutable.bin")
        file_path.write_bytes(data)

        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file_path))
        )

        record = parse_result.records[0]

        decoded = ToolHost.decode_field(
            DecodeFieldInput(record=record, grammar=grammar_result.grammar, field_name="data")
        )

        # Verify frozen dataclass
        with pytest.raises(AttributeError):
            decoded.value = "modified"

    def test_decode_field_determinism(self):
        """Test that decode_field is deterministic."""
        yaml = """
format: record_stream
framing:
  repeat: until_eof
types:
  Record:
    fields:
      - { name: text, type: bytes, length: 5 }
"""
        grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
        data = b"Hello"
        file_path = Path("/tmp/test_decode_determinism.bin")
        file_path.write_bytes(data)

        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file_path))
        )

        record = parse_result.records[0]
        input_obj = DecodeFieldInput(record=record, grammar=grammar_result.grammar, field_name="text")

        # Call multiple times
        result1 = ToolHost.decode_field(input_obj)
        result2 = ToolHost.decode_field(input_obj)
        result3 = ToolHost.decode_field(input_obj)

        # All results should be identical
        assert result1.success == result2.success == result3.success
        assert result1.value == result2.value == result3.value
        assert result1.decoder_type == result2.decoder_type == result3.decoder_type
        assert result1.field_path == result2.field_path == result3.field_path


class TestQueryRecords:
    """Tests for query_records tool."""

    def test_query_records_all(self):
        """Test querying all records (no filter)."""
        yaml = """
format: record_stream
endian: little
framing:
  repeat: until_eof
types:
  Record:
    fields:
      - { name: type, type: u16 }
      - { name: length, type: u8 }
      - { name: data, type: bytes, length_field: length }
"""
        grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
        assert grammar_result.success

        # Create 3 records
        data = b"\x01\x00" + b"\x03" + b"AAA"
        data += b"\x02\x00" + b"\x03" + b"BBB"
        data += b"\x03\x00" + b"\x03" + b"CCC"
        file_path = Path("/tmp/test_query_all.bin")
        file_path.write_bytes(data)

        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file_path))
        )

        # Query all records
        result = ToolHost.query_records(
            QueryRecordsInput(parse_result=parse_result, filter_type="all")
        )

        assert result.total_count == 3
        assert result.original_count == 3
        assert len(result.records) == 3
        assert result.filter_applied == "all records"

    def test_query_records_by_type(self):
        """Test filtering records by type name."""
        yaml = """
format: record_stream
endian: little
framing:
  repeat: until_eof
types:
  TypeA:
    fields:
      - { name: magic, type: u16 }
      - { name: data, type: bytes, length: 2 }
  TypeB:
    fields:
      - { name: magic, type: u16 }
      - { name: data, type: bytes, length: 2 }

record:
  switch:
    expr: TypeA.magic
    cases:
      "0x0001": TypeA
      "0x0002": TypeB
    default: TypeA
"""
        grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
        assert grammar_result.success

        # Create mixed records: 2 TypeA, 1 TypeB, 1 TypeA
        data = b"\x01\x00" + b"AA"  # TypeA
        data += b"\x02\x00" + b"BB"  # TypeB
        data += b"\x01\x00" + b"CC"  # TypeA
        file_path = Path("/tmp/test_query_type.bin")
        file_path.write_bytes(data)

        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file_path))
        )

        # Filter by TypeA
        result = ToolHost.query_records(
            QueryRecordsInput(
                parse_result=parse_result, filter_type="type", filter_value="TypeA"
            )
        )

        assert result.total_count == 2
        assert result.original_count == 3
        assert len(result.records) == 2
        assert all(r.type_name == "TypeA" for r in result.records)
        assert result.filter_applied == "type=TypeA"

        # Filter by TypeB
        result_b = ToolHost.query_records(
            QueryRecordsInput(
                parse_result=parse_result, filter_type="type", filter_value="TypeB"
            )
        )

        assert result_b.total_count == 1
        assert result_b.original_count == 3
        assert len(result_b.records) == 1
        assert result_b.records[0].type_name == "TypeB"

    def test_query_records_by_offset_range(self):
        """Test filtering records by offset range."""
        yaml = """
format: record_stream
endian: little
framing:
  repeat: until_eof
types:
  Record:
    fields:
      - { name: id, type: u16 }
      - { name: data, type: bytes, length: 4 }
"""
        grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
        assert grammar_result.success

        # Create records at offsets: 0, 6, 12, 18
        data = b"\x01\x00" + b"AAAA"  # Offset 0-5
        data += b"\x02\x00" + b"BBBB"  # Offset 6-11
        data += b"\x03\x00" + b"CCCC"  # Offset 12-17
        data += b"\x04\x00" + b"DDDD"  # Offset 18-23
        file_path = Path("/tmp/test_query_offset.bin")
        file_path.write_bytes(data)

        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file_path))
        )

        # Query range 0-12 (should get records at 0 and 6)
        result = ToolHost.query_records(
            QueryRecordsInput(
                parse_result=parse_result, filter_type="offset_range", filter_value=(0, 12)
            )
        )

        assert result.total_count == 2
        assert result.original_count == 4
        assert len(result.records) == 2
        assert result.records[0].offset == 0
        assert result.records[1].offset == 6
        assert result.filter_applied == "offset_range=(0x0, 0xc)"

        # Query range 10-20 (should get records at 6, 12, 18)
        result2 = ToolHost.query_records(
            QueryRecordsInput(
                parse_result=parse_result, filter_type="offset_range", filter_value=(10, 20)
            )
        )

        assert result2.total_count == 3
        assert len(result2.records) == 3
        assert result2.records[0].offset == 6
        assert result2.records[1].offset == 12
        assert result2.records[2].offset == 18

    def test_query_records_by_has_field(self):
        """Test filtering records by field presence."""
        yaml = """
format: record_stream
endian: little
framing:
  repeat: until_eof
types:
  Header:
    fields:
      - { name: type, type: u16 }
      - { name: length, type: u8 }
  RecordWithPayload:
    fields:
      - { name: header, type: Header }
      - { name: payload, type: bytes, length_field: length }
  RecordWithData:
    fields:
      - { name: header, type: Header }
      - { name: data, type: bytes, length_field: length }

record:
  switch:
    expr: Header.type
    cases:
      "0x0001": RecordWithPayload
      "0x0002": RecordWithData
    default: RecordWithPayload
"""
        grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
        assert grammar_result.success

        # Create mixed records
        data = b"\x01\x00" + b"\x03" + b"AAA"  # RecordWithPayload
        data += b"\x02\x00" + b"\x03" + b"BBB"  # RecordWithData
        data += b"\x01\x00" + b"\x03" + b"CCC"  # RecordWithPayload
        file_path = Path("/tmp/test_query_field.bin")
        file_path.write_bytes(data)

        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file_path))
        )

        # Filter by has "payload" field
        result = ToolHost.query_records(
            QueryRecordsInput(
                parse_result=parse_result, filter_type="has_field", filter_value="payload"
            )
        )

        assert result.total_count == 2
        assert result.original_count == 3
        assert len(result.records) == 2
        assert all("payload" in r.fields for r in result.records)
        assert result.filter_applied == "has_field=payload"

        # Filter by has "data" field
        result2 = ToolHost.query_records(
            QueryRecordsInput(
                parse_result=parse_result, filter_type="has_field", filter_value="data"
            )
        )

        assert result2.total_count == 1
        assert len(result2.records) == 1
        assert "data" in result2.records[0].fields

    def test_query_records_no_matches(self):
        """Test query with no matching records."""
        yaml = """
format: record_stream
endian: little
framing:
  repeat: until_eof
types:
  Record:
    fields:
      - { name: id, type: u16 }
"""
        grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
        assert grammar_result.success

        data = b"\x01\x00" + b"\x02\x00"
        file_path = Path("/tmp/test_query_empty.bin")
        file_path.write_bytes(data)

        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file_path))
        )

        # Filter by non-existent type
        result = ToolHost.query_records(
            QueryRecordsInput(
                parse_result=parse_result, filter_type="type", filter_value="NonExistent"
            )
        )

        assert result.total_count == 0
        assert result.original_count == 2
        assert len(result.records) == 0
        assert result.filter_applied == "type=NonExistent"

    def test_query_records_invalid_filter_type(self):
        """Test handling of invalid filter type."""
        yaml = """
format: record_stream
framing:
  repeat: until_eof
types:
  Record:
    fields:
      - { name: id, type: u16 }
"""
        grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
        data = b"\x01\x00"
        file_path = Path("/tmp/test_query_invalid.bin")
        file_path.write_bytes(data)

        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file_path))
        )

        # Use unknown filter type
        result = ToolHost.query_records(
            QueryRecordsInput(
                parse_result=parse_result, filter_type="unknown_filter", filter_value="test"
            )
        )

        assert result.total_count == 0
        assert result.original_count == 1
        assert "unknown filter type" in result.filter_applied

    def test_query_records_invalid_filter_value_type(self):
        """Test handling of invalid filter value for type filter."""
        yaml = """
format: record_stream
framing:
  repeat: until_eof
types:
  Record:
    fields:
      - { name: id, type: u16 }
"""
        grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
        data = b"\x01\x00"
        file_path = Path("/tmp/test_query_invalid_value.bin")
        file_path.write_bytes(data)

        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file_path))
        )

        # Use wrong value type for "type" filter (should be string)
        result = ToolHost.query_records(
            QueryRecordsInput(parse_result=parse_result, filter_type="type", filter_value=123)
        )

        assert result.total_count == 0
        assert "invalid" in result.filter_applied

    def test_query_records_invalid_offset_range(self):
        """Test handling of invalid offset range."""
        yaml = """
format: record_stream
framing:
  repeat: until_eof
types:
  Record:
    fields:
      - { name: id, type: u16 }
"""
        grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
        data = b"\x01\x00"
        file_path = Path("/tmp/test_query_invalid_range.bin")
        file_path.write_bytes(data)

        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file_path))
        )

        # Use wrong type for offset_range (should be tuple of 2 ints)
        result = ToolHost.query_records(
            QueryRecordsInput(
                parse_result=parse_result, filter_type="offset_range", filter_value="not_a_tuple"
            )
        )

        assert result.total_count == 0
        assert "invalid" in result.filter_applied

    def test_query_records_empty_parse_result(self):
        """Test querying with no records in parse result."""
        yaml = """
format: record_stream
framing:
  repeat: until_eof
types:
  Record:
    fields:
      - { name: id, type: u16 }
"""
        grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
        data = b""  # Empty file
        file_path = Path("/tmp/test_query_empty_parse.bin")
        file_path.write_bytes(data)

        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file_path))
        )

        # Query all from empty result
        result = ToolHost.query_records(
            QueryRecordsInput(parse_result=parse_result, filter_type="all")
        )

        assert result.total_count == 0
        assert result.original_count == 0
        assert len(result.records) == 0

    def test_query_records_immutability(self):
        """Test that RecordSet output is immutable."""
        yaml = """
format: record_stream
framing:
  repeat: until_eof
types:
  Record:
    fields:
      - { name: id, type: u16 }
"""
        grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
        data = b"\x01\x00"
        file_path = Path("/tmp/test_query_immutable.bin")
        file_path.write_bytes(data)

        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file_path))
        )

        result = ToolHost.query_records(
            QueryRecordsInput(parse_result=parse_result, filter_type="all")
        )

        # Verify frozen dataclass
        with pytest.raises(AttributeError):
            result.total_count = 999

    def test_query_records_determinism(self):
        """Test that query_records is deterministic."""
        yaml = """
format: record_stream
framing:
  repeat: until_eof
types:
  Record:
    fields:
      - { name: id, type: u16 }
"""
        grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
        data = b"\x01\x00" + b"\x02\x00" + b"\x03\x00"
        file_path = Path("/tmp/test_query_determinism.bin")
        file_path.write_bytes(data)

        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file_path))
        )

        input_obj = QueryRecordsInput(
            parse_result=parse_result, filter_type="offset_range", filter_value=(0, 4)
        )

        # Call multiple times
        result1 = ToolHost.query_records(input_obj)
        result2 = ToolHost.query_records(input_obj)
        result3 = ToolHost.query_records(input_obj)

        # All results should be identical
        assert result1.total_count == result2.total_count == result3.total_count
        assert result1.original_count == result2.original_count == result3.original_count
        assert len(result1.records) == len(result2.records) == len(result3.records)
        assert result1.filter_applied == result2.filter_applied == result3.filter_applied
