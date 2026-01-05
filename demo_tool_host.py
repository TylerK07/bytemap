#!/usr/bin/env python3
"""Demonstration of Tool Host usage.

This script shows how to use the ToolHost for deterministic binary analysis.
All operations are pure functions with explicit inputs/outputs.
"""

import tempfile
from pathlib import Path

from hexmap.core.tool_host import (
    AnalyzeCoverageInput,
    GenerateSpansInput,
    LintGrammarInput,
    ParseBinaryInput,
    ToolHost,
)

# Example 1: Valid grammar
print("=" * 70)
print("Example 1: Valid Grammar")
print("=" * 70)

valid_yaml = """
format: record_stream
endian: little
framing:
  repeat: until_eof
types:
  Header:
    fields:
      - { name: type, type: u16 }
      - { name: length, type: u16 }
  Record:
    fields:
      - { name: header, type: Header }
      - { name: data, type: bytes, length: 10 }
"""

result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=valid_yaml))

print(f"Success: {result.success}")
print(f"Errors: {result.errors}")
print(f"Warnings: {result.warnings}")
if result.grammar:
    print(f"Grammar format: {result.grammar.format}")
    print(f"Number of types: {len(result.grammar.types)}")
    print(f"Types defined: {', '.join(result.grammar.types.keys())}")
print()

# Example 2: Invalid YAML syntax
print("=" * 70)
print("Example 2: Invalid YAML Syntax")
print("=" * 70)

invalid_yaml = """
format: record_stream
types:
  Header
    - invalid syntax here
"""

result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=invalid_yaml))

print(f"Success: {result.success}")
print(f"Errors: {result.errors}")
print(f"Grammar: {result.grammar}")
print()

# Example 3: Grammar with unused types (warning)
print("=" * 70)
print("Example 3: Grammar with Unused Types (Warning)")
print("=" * 70)

unused_yaml = """
format: record_stream
endian: little
framing:
  repeat: until_eof
record:
  switch:
    expr: Header.type
    cases:
      "0x01": UsedType
    default: UsedType
types:
  Header:
    fields:
      - { name: type, type: u8 }
  UsedType:
    fields:
      - { name: header, type: Header }
      - { name: data, type: u8 }
  UnusedType1:
    fields:
      - { name: stuff, type: u16 }
  UnusedType2:
    fields:
      - { name: more_stuff, type: u32 }
"""

result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=unused_yaml))

print(f"Success: {result.success}")
print(f"Errors: {result.errors}")
print(f"Warnings: {result.warnings}")
if result.grammar:
    print(f"Number of types: {len(result.grammar.types)}")
    print(f"Types defined: {', '.join(sorted(result.grammar.types.keys()))}")
print()

# Example 4: Complex grammar with all features
print("=" * 70)
print("Example 4: Complex Grammar with All Features")
print("=" * 70)

complex_yaml = """
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
      - { name: header, type: Header, color: red }
      - { name: payload_len, type: u8, color: orange }
      - { name: payload, type: bytes, length: payload_len, color: cyan }
  NTRecord:
    fields:
      - { name: header, type: Header }
      - { name: nt_len_1, type: u16 }
      - { name: nt_len_2, type: u16 }
      - { name: pad10, type: bytes, length: 10 }
      - { name: delimiter, type: u16, validate: { equals: 0x001C } }
      - { name: note_text, type: bytes, length: "nt_len_1 - 4", encoding: ascii }
      - { name: terminator, type: u16 }
registry:
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

result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=complex_yaml))

print(f"Success: {result.success}")
print(f"Errors: {result.errors}")
print(f"Warnings: {result.warnings}")
if result.grammar:
    print(f"Grammar format: {result.grammar.format}")
    print(f"Global endianness: {result.grammar.endian}")
    print(f"Number of types: {len(result.grammar.types)}")
    print(f"Number of registry entries: {len(result.grammar.registry)}")
    print(f"Has record switch: {result.grammar.record_switch is not None}")

    # Show some grammar details
    if result.grammar.record_switch:
        print(f"Switch expression: {result.grammar.record_switch.expr}")
        print(f"Switch cases: {result.grammar.record_switch.cases}")

    # Show field details for one type
    nt_record = result.grammar.types["NTRecord"]
    print(f"\nNTRecord fields:")
    for field in nt_record.fields:
        print(f"  - {field.name}: {field.type}", end="")
        if field.length is not None:
            print(f" (length={field.length})", end="")
        if field.length_expr:
            print(f" (length_expr='{field.length_expr}')", end="")
        if field.encoding:
            print(f" (encoding={field.encoding})", end="")
        if field.validate:
            print(f" (validate={field.validate.rule_type})", end="")
        print()
print()

# Example 5: Demonstrating determinism
print("=" * 70)
print("Example 5: Demonstrating Determinism")
print("=" * 70)

yaml = """
format: record_stream
endian: little
types:
  Record:
    fields:
      - { name: x, type: u16 }
      - { name: y, type: u16 }
"""

result1 = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
result2 = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))
result3 = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml))

print(f"All results successful: {all([r.success for r in [result1, result2, result3]])}")
print(f"All results identical:")
print(f"  - success: {result1.success == result2.success == result3.success}")
print(f"  - errors: {result1.errors == result2.errors == result3.errors}")
print(f"  - warnings: {result1.warnings == result2.warnings == result3.warnings}")
print(f"  - format: {result1.grammar.format == result2.grammar.format == result3.grammar.format}")
print(f"  - types: {len(result1.grammar.types) == len(result2.grammar.types) == len(result3.grammar.types)}")
print("\n✓ Same input always produces same output (deterministic)")
print()

# Example 6: Binary Parsing
print("=" * 70)
print("Example 6: Binary Parsing")
print("=" * 70)

# Create a simple grammar
simple_yaml = """
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

grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=simple_yaml))

if grammar_result.success:
    print(f"Grammar validated: {grammar_result.grammar.format}")

    # Create a temporary binary file
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.bin"

        # Create test data: two records
        data = b""
        data += b"\x01\x00"  # type (u16 little-endian)
        data += b"\x05"      # length (u8)
        data += b"HELLO"     # data (5 bytes)
        data += b"\x02\x00"  # type (u16 little-endian)
        data += b"\x05"      # length (u8)
        data += b"WORLD"     # data (5 bytes)

        test_file.write_bytes(data)
        print(f"Created test file: {len(data)} bytes")

        # Parse the binary file
        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(
                grammar=grammar_result.grammar,
                file_path=str(test_file)
            )
        )

        print(f"\nParse Results:")
        print(f"  Records parsed: {parse_result.record_count}")
        print(f"  Total bytes: {parse_result.total_bytes_parsed}")
        print(f"  Errors: {len(parse_result.errors)}")
        print(f"  Parse stopped at: {parse_result.parse_stopped_at:#x}")
        print(f"  Timestamp: {parse_result.timestamp}")

        # Show record details
        print(f"\nRecord Details:")
        for i, record in enumerate(parse_result.records):
            print(f"  Record {i+1}:")
            print(f"    Offset: {record.offset:#x}")
            print(f"    Size: {record.size} bytes")
            print(f"    Type: {record.type_name}")
            print(f"    Fields:")
            print(f"      type: {record.fields['type'].value:#x}")
            print(f"      length: {record.fields['length'].value}")
            print(f"      data: {record.fields['data'].value}")

        # Demonstrate determinism
        print(f"\nDeterminism Check:")
        parse_result2 = ToolHost.parse_binary(
            ParseBinaryInput(
                grammar=grammar_result.grammar,
                file_path=str(test_file)
            )
        )

        print(f"  Same record count: {parse_result.record_count == parse_result2.record_count}")
        print(f"  Same bytes parsed: {parse_result.total_bytes_parsed == parse_result2.total_bytes_parsed}")
        print(f"  First record matches: {parse_result.records[0].offset == parse_result2.records[0].offset}")

        # Demonstrate with limits
        print(f"\nParsing with Limits:")
        limited_result = ToolHost.parse_binary(
            ParseBinaryInput(
                grammar=grammar_result.grammar,
                file_path=str(test_file),
                max_records=1  # Only parse first record
            )
        )
        print(f"  Max records=1: parsed {limited_result.record_count} record(s)")
        print(f"  First record data: {limited_result.records[0].fields['data'].value}")

        offset_result = ToolHost.parse_binary(
            ParseBinaryInput(
                grammar=grammar_result.grammar,
                file_path=str(test_file),
                offset=8  # Start at second record
            )
        )
        print(f"  Offset=8: parsed {offset_result.record_count} record(s)")
        print(f"  Second record data: {offset_result.records[0].fields['data'].value}")

# Example 7: Span Generation
print("=" * 70)
print("Example 7: Span Generation (Viewport-Based)")
print("=" * 70)

# Use the parse result from Example 6
if grammar_result.success:
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.bin"

        # Create test data: three records at known offsets
        data = b""
        # Record 1 at offset 0 (7 bytes)
        data += b"\x01\x00"  # type
        data += b"\x04"      # length
        data += b"AAAA"      # data
        # Record 2 at offset 7 (7 bytes)
        data += b"\x02\x00"  # type
        data += b"\x04"      # length
        data += b"BBBB"      # data
        # Record 3 at offset 14 (7 bytes)
        data += b"\x03\x00"  # type
        data += b"\x04"      # length
        data += b"CCCC"      # data

        test_file.write_bytes(data)
        print(f"Created test file: {len(data)} bytes, 3 records")

        # Parse the file
        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(
                grammar=grammar_result.grammar,
                file_path=str(test_file)
            )
        )

        print(f"Parsed {parse_result.record_count} records")

        # Generate spans for different viewports
        print(f"\nViewport 1: Full file (0-100)")
        full_spans = ToolHost.generate_spans(
            GenerateSpansInput(
                parse_result=parse_result,
                viewport_start=0,
                viewport_end=100
            )
        )
        print(f"  Records in viewport: {full_spans.record_count}")
        print(f"  Total spans: {len(full_spans.spans)}")
        print(f"  Span index created: {full_spans.span_index is not None}")

        print(f"\nViewport 2: First record only (0-7)")
        first_spans = ToolHost.generate_spans(
            GenerateSpansInput(
                parse_result=parse_result,
                viewport_start=0,
                viewport_end=7
            )
        )
        print(f"  Records in viewport: {first_spans.record_count}")
        print(f"  Total spans: {len(first_spans.spans)}")

        print(f"\nViewport 3: Middle record (7-14)")
        middle_spans = ToolHost.generate_spans(
            GenerateSpansInput(
                parse_result=parse_result,
                viewport_start=7,
                viewport_end=14
            )
        )
        print(f"  Records in viewport: {middle_spans.record_count}")
        print(f"  Total spans: {len(middle_spans.spans)}")

        print(f"\nViewport 4: Beyond file (1000-2000)")
        empty_spans = ToolHost.generate_spans(
            GenerateSpansInput(
                parse_result=parse_result,
                viewport_start=1000,
                viewport_end=2000
            )
        )
        print(f"  Records in viewport: {empty_spans.record_count}")
        print(f"  Total spans: {len(empty_spans.spans)}")

        # Show span details
        print(f"\nSpan Details (first viewport):")
        for i, span in enumerate(list(first_spans.spans)[:3]):
            print(f"  Span {i+1}:")
            print(f"    Path: {span.path}")
            print(f"    Offset: {span.offset:#x}")
            print(f"    Length: {span.length}")
            print(f"    Group: {span.group}")

        # Demonstrate determinism
        print(f"\nDeterminism Check:")
        spans2 = ToolHost.generate_spans(
            GenerateSpansInput(
                parse_result=parse_result,
                viewport_start=0,
                viewport_end=7
            )
        )
        print(f"  Same record count: {first_spans.record_count == spans2.record_count}")
        print(f"  Same span count: {len(first_spans.spans) == len(spans2.spans)}")
        print(f"  First span matches: {first_spans.spans[0].offset == spans2.spans[0].offset}")

# Example 8: Coverage Analysis
print("=" * 70)
print("Example 8: Coverage Analysis")
print("=" * 70)

if grammar_result.success:
    with tempfile.TemporaryDirectory() as tmpdir:
        # Test 1: Full coverage
        print("\nScenario 1: Full Coverage")
        test_file = Path(tmpdir) / "full.bin"
        # Create valid data: type (u16) + length (u8) + data (length bytes)
        data = (
            b"\x01\x00" + b"\x04" + b"AAAA" +  # Record 1: type=1, length=4, data=AAAA
            b"\x02\x00" + b"\x04" + b"BBBB" +  # Record 2: type=2, length=4, data=BBBB
            b"\x03\x00" + b"\x04" + b"CCCC"    # Record 3: type=3, length=4, data=CCCC
        )
        test_file.write_bytes(data)

        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(
                grammar=grammar_result.grammar,
                file_path=str(test_file)
            )
        )

        coverage = ToolHost.analyze_coverage(
            AnalyzeCoverageInput(
                parse_result=parse_result,
                file_size=len(data)
            )
        )

        print(f"  File size: {coverage.file_size} bytes")
        print(f"  Bytes covered: {coverage.bytes_covered}")
        print(f"  Bytes uncovered: {coverage.bytes_uncovered}")
        print(f"  Coverage: {coverage.coverage_percentage:.1f}%")
        print(f"  Gaps: {len(coverage.gaps)}")
        print(f"  Records: {coverage.record_count}")

        # Test 2: Partial coverage (with gap at end)
        print("\nScenario 2: Partial Coverage (trailing data)")
        test_file2 = Path(tmpdir) / "partial.bin"
        data2 = b"\x01\x00" + b"\x04" + b"AAAA" + b"\x00" * 10  # Record + 10 bytes trailing
        test_file2.write_bytes(data2)

        parse_result2 = ToolHost.parse_binary(
            ParseBinaryInput(
                grammar=grammar_result.grammar,
                file_path=str(test_file2),
                max_records=1  # Only parse first record
            )
        )

        coverage2 = ToolHost.analyze_coverage(
            AnalyzeCoverageInput(
                parse_result=parse_result2,
                file_size=len(data2)
            )
        )

        print(f"  File size: {coverage2.file_size} bytes")
        print(f"  Bytes covered: {coverage2.bytes_covered}")
        print(f"  Bytes uncovered: {coverage2.bytes_uncovered}")
        print(f"  Coverage: {coverage2.coverage_percentage:.1f}%")
        print(f"  Gaps: {len(coverage2.gaps)}")
        if coverage2.gaps:
            print(f"  Gap locations:")
            for i, (start, end) in enumerate(coverage2.gaps):
                print(f"    Gap {i+1}: {start:#x}-{end:#x} ({end-start} bytes)")
        if coverage2.largest_gap:
            start, end = coverage2.largest_gap
            print(f"  Largest gap: {start:#x}-{end:#x} ({end-start} bytes)")

        # Test 3: No coverage (empty parse)
        print("\nScenario 3: No Coverage (parse failure)")
        # Simulate empty parse
        from hexmap.core.tool_host import ParseResult

        empty_parse = ParseResult(
            records=(),
            errors=(),
            file_path="/fake/path",
            grammar_format="record_stream",
            total_bytes_parsed=0,
            parse_stopped_at=0,
            timestamp=0.0,
            record_count=0,
        )

        coverage3 = ToolHost.analyze_coverage(
            AnalyzeCoverageInput(parse_result=empty_parse, file_size=100)
        )

        print(f"  File size: {coverage3.file_size} bytes")
        print(f"  Bytes covered: {coverage3.bytes_covered}")
        print(f"  Coverage: {coverage3.coverage_percentage:.1f}%")
        print(f"  Gaps: {len(coverage3.gaps)}")
        if coverage3.largest_gap:
            start, end = coverage3.largest_gap
            print(f"  Entire file is gap: {start:#x}-{end:#x}")

print()

# ============================================================================
# EXAMPLE 9: FIELD DECODING
# ============================================================================

if True:
    print("=" * 70)
    print("EXAMPLE 9: Field Decoding with Registry")
    print("=" * 70)
    print("\nDemonstrates decode_field tool for extracting human-readable values")
    print()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Grammar with registry entries for different decoder types
        yaml_with_registry = """
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
      "0x4E54": Record
      "0x0001": Record
      "0x0002": Record
    default: Record

registry:
  "0x4E54":  # Name Type
    name: NameRecord
    decode:
      as: string
      encoding: utf-8

  "0x0001":  # Counter Type
    name: CounterRecord
    decode:
      as: u16

  "0x0002":  # Hex Data Type
    name: HexRecord
    decode:
      as: hex
"""

        grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml_with_registry))

        if not grammar_result.success:
            print(f"ERROR: {grammar_result.errors[0]}")
        else:
            print("✓ Grammar validated with 3 registry entries\n")

            # Scenario 1: String decoder
            print("Scenario 1: String Decoder (0x4E54)")
            data1 = b"\x4E\x54" + b"\x05" + b"Alice"  # NT type + length + name
            file1 = Path(tmpdir) / "demo_decode_string.bin"
            file1.write_bytes(data1)

            parse1 = ToolHost.parse_binary(
                ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file1))
            )

            from hexmap.core.tool_host import DecodeFieldInput

            decoded1 = ToolHost.decode_field(
                DecodeFieldInput(record=parse1.records[0], grammar=grammar_result.grammar)
            )

            print(f"  Record type: 0x4E54 (NameRecord)")
            print(f"  Success: {decoded1.success}")
            print(f"  Decoded value: '{decoded1.value}'")
            print(f"  Decoder type: {decoded1.decoder_type}")
            print(f"  Field path: {decoded1.field_path}")
            print()

            # Scenario 2: U16 decoder
            print("Scenario 2: U16 Decoder (0x0001)")
            data2 = b"\x01\x00" + b"\x02" + b"\x2A\x00"  # Counter type + u16 value = 42
            file2 = Path(tmpdir) / "demo_decode_u16.bin"
            file2.write_bytes(data2)

            parse2 = ToolHost.parse_binary(
                ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file2))
            )

            decoded2 = ToolHost.decode_field(
                DecodeFieldInput(record=parse2.records[0], grammar=grammar_result.grammar)
            )

            print(f"  Record type: 0x0001 (CounterRecord)")
            print(f"  Success: {decoded2.success}")
            print(f"  Decoded value: {decoded2.value}")
            print(f"  Decoder type: {decoded2.decoder_type}")
            print(f"  Field path: {decoded2.field_path}")
            print()

            # Scenario 3: Hex decoder
            print("Scenario 3: Hex Decoder (0x0002)")
            data3 = b"\x02\x00" + b"\x04" + b"\xDE\xAD\xBE\xEF"  # Hex type + binary data
            file3 = Path(tmpdir) / "demo_decode_hex.bin"
            file3.write_bytes(data3)

            parse3 = ToolHost.parse_binary(
                ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file3))
            )

            decoded3 = ToolHost.decode_field(
                DecodeFieldInput(record=parse3.records[0], grammar=grammar_result.grammar)
            )

            print(f"  Record type: 0x0002 (HexRecord)")
            print(f"  Success: {decoded3.success}")
            print(f"  Decoded value: {decoded3.value}")
            print(f"  Decoder type: {decoded3.decoder_type}")
            print(f"  Field path: {decoded3.field_path}")
            print()

            # Scenario 4: Direct field decoding (without registry)
            print("Scenario 4: Direct Field Decoding")
            print("  Decoding specific field 'payload' directly...")

            decoded4 = ToolHost.decode_field(
                DecodeFieldInput(
                    record=parse1.records[0], grammar=grammar_result.grammar, field_name="payload"
                )
            )

            print(f"  Success: {decoded4.success}")
            print(f"  Decoded value: '{decoded4.value}'")
            print(f"  Decoder type: {decoded4.decoder_type}")
            print(f"  Field path: {decoded4.field_path}")
            print()

print()

# ============================================================================
# EXAMPLE 10: RECORD QUERYING
# ============================================================================

if True:
    print("=" * 70)
    print("EXAMPLE 10: Record Querying and Filtering")
    print("=" * 70)
    print("\nDemonstrates query_records tool for filtering and searching records")
    print()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Grammar with multiple record types
        yaml_multi = """
format: record_stream
endian: little
framing:
  repeat: until_eof
types:
  Header:
    fields:
      - { name: type_id, type: u16 }
      - { name: length, type: u8 }
  NameRecord:
    fields:
      - { name: header, type: Header }
      - { name: name, type: bytes, length_field: length }
  CountRecord:
    fields:
      - { name: header, type: Header }
      - { name: count, type: bytes, length_field: length }

record:
  switch:
    expr: Header.type_id
    cases:
      "0x0001": NameRecord
      "0x0002": CountRecord
    default: NameRecord
"""

        grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml_multi))

        if not grammar_result.success:
            print(f"ERROR: {grammar_result.errors[0]}")
        else:
            print("✓ Grammar validated\n")

            # Create mixed records at known offsets
            data = b"\x01\x00" + b"\x05" + b"Alice"  # Offset 0-7: NameRecord
            data += b"\x02\x00" + b"\x02" + b"\x0A\x00"  # Offset 8-12: CountRecord
            data += b"\x01\x00" + b"\x03" + b"Bob"  # Offset 13-18: NameRecord
            data += b"\x02\x00" + b"\x02" + b"\x14\x00"  # Offset 19-23: CountRecord
            data += b"\x01\x00" + b"\x07" + b"Charlie"  # Offset 24-33: NameRecord

            file_path = Path(tmpdir) / "demo_query.bin"
            file_path.write_bytes(data)

            parse_result = ToolHost.parse_binary(
                ParseBinaryInput(grammar=grammar_result.grammar, file_path=str(file_path))
            )

            from hexmap.core.tool_host import QueryRecordsInput

            print(f"Parsed {parse_result.record_count} records\n")

            # Scenario 1: Get all records
            print("Scenario 1: Query All Records")
            result_all = ToolHost.query_records(
                QueryRecordsInput(parse_result=parse_result, filter_type="all")
            )

            print(f"  Filter: {result_all.filter_applied}")
            print(f"  Total count: {result_all.total_count}")
            print(f"  Original count: {result_all.original_count}")
            print()

            # Scenario 2: Filter by type
            print("Scenario 2: Filter by Record Type")
            result_names = ToolHost.query_records(
                QueryRecordsInput(
                    parse_result=parse_result, filter_type="type", filter_value="NameRecord"
                )
            )

            print(f"  Filter: {result_all.filter_applied}")
            print(f"  Found {result_names.total_count} NameRecord(s) out of {result_names.original_count}")
            for rec in result_names.records:
                print(f"    - Record at offset {rec.offset:#x}, type={rec.type_name}")
            print()

            # Scenario 3: Filter by offset range
            print("Scenario 3: Filter by Offset Range")
            result_range = ToolHost.query_records(
                QueryRecordsInput(
                    parse_result=parse_result, filter_type="offset_range", filter_value=(10, 25)
                )
            )

            print(f"  Filter: {result_range.filter_applied}")
            print(f"  Found {result_range.total_count} record(s) in range")
            for rec in result_range.records:
                print(f"    - Record at offset {rec.offset:#x}, size={rec.size}")
            print()

            # Scenario 4: Filter by field presence
            print("Scenario 4: Filter by Field Presence")
            result_field = ToolHost.query_records(
                QueryRecordsInput(
                    parse_result=parse_result, filter_type="has_field", filter_value="name"
                )
            )

            print(f"  Filter: {result_field.filter_applied}")
            print(f"  Found {result_field.total_count} record(s) with 'name' field")
            for rec in result_field.records:
                print(f"    - Record at offset {rec.offset:#x}")
            print()

print()

print("=" * 70)
print("Tool Host demonstration complete!")
print("=" * 70)
print("\nTools Demonstrated:")
print("  ✓ lint_grammar - Grammar validation")
print("  ✓ parse_binary - Binary file parsing")
print("  ✓ generate_spans - Viewport-based field highlighting")
print("  ✓ analyze_coverage - Parse coverage analysis")
print("  ✓ decode_field - Field value decoding")
print("  ✓ query_records - Record querying and filtering")
print("\nKey properties demonstrated:")
print("  ✓ Explicit input/output schemas")
print("  ✓ Deterministic behavior")
print("  ✓ Immutable outputs (frozen dataclasses)")
print("  ✓ Clear error/warning separation")
print("  ✓ No side effects")
print("  ✓ Safe for LLM/agent usage")
print("  ✓ Efficient viewport-based processing")
print("  ✓ Gap detection and coverage analysis")
print("  ✓ Registry-based field decoding")
