"""Deterministic tool host for binary analysis.

This module provides a stable, pure-function API for binary parsing operations.
All tools are:
- Pure functions (deterministic)
- Explicitly typed inputs/outputs
- No global state mutation
- No file I/O side effects (except reading)
- Fail loudly on invalid inputs

Designed to be safely callable by autonomous agents or UI code.
"""

from __future__ import annotations

import time
from bisect import bisect_right
from dataclasses import dataclass
from typing import TYPE_CHECKING

from hexmap.core.io import PagedReader
from hexmap.core.spans import Span, SpanIndex
from hexmap.core.yaml_grammar import EndianType, Grammar, parse_yaml_grammar
from hexmap.core.yaml_parser import ParsedRecord, RecordParser

if TYPE_CHECKING:
    pass


# ============================================================================
# INPUT SCHEMAS
# ============================================================================

@dataclass(frozen=True)
class LintGrammarInput:
    """Input for grammar validation.

    Args:
        yaml_text: Raw YAML grammar text to validate
    """
    yaml_text: str


@dataclass(frozen=True)
class ParseBinaryInput:
    """Input for binary parsing.

    Args:
        grammar: Previously validated grammar object
        file_path: Absolute path to binary file
        offset: Start offset in file (default: 0)
        limit: Max bytes to parse (default: entire file)
        max_records: Max records to parse (default: unlimited)
    """
    grammar: Grammar
    file_path: str
    offset: int = 0
    limit: int | None = None
    max_records: int | None = None


@dataclass(frozen=True)
class GenerateSpansInput:
    """Input for span generation.

    Args:
        parse_result: Parse result from parse_binary
        viewport_start: Start offset of viewport (inclusive)
        viewport_end: End offset of viewport (exclusive)
    """
    parse_result: ParseResult
    viewport_start: int
    viewport_end: int


@dataclass(frozen=True)
class AnalyzeCoverageInput:
    """Input for coverage analysis.

    Args:
        parse_result: Parse result from parse_binary
        file_size: Total size of the binary file in bytes
    """
    parse_result: ParseResult
    file_size: int


# ============================================================================
# OUTPUT SCHEMAS
# ============================================================================

@dataclass(frozen=True)
class LintGrammarOutput:
    """Output from grammar validation.

    Attributes:
        success: True if grammar is valid and usable
        grammar: Parsed grammar object (None if validation failed)
        errors: Error messages (empty if success=True)
        warnings: Non-fatal warnings about grammar quality
    """
    success: bool
    grammar: Grammar | None
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ParseResult:
    """Immutable parse result from binary parsing.

    Attributes:
        records: All parsed records (frozen tuple)
        errors: Error messages encountered during parsing
        file_path: Path to the file that was parsed
        grammar_format: Grammar format used (e.g., "record_stream")
        total_bytes_parsed: Total number of bytes consumed
        parse_stopped_at: File offset where parsing stopped
        timestamp: Unix timestamp when parse completed
        record_count: Number of records parsed
    """
    records: tuple[ParsedRecord, ...]
    errors: tuple[str, ...]
    file_path: str
    grammar_format: str
    total_bytes_parsed: int
    parse_stopped_at: int
    timestamp: float
    record_count: int


@dataclass(frozen=True)
class SpanSet:
    """Immutable set of field spans for a viewport.

    Attributes:
        spans: All field spans in viewport (frozen tuple)
        viewport_start: Start offset of viewport
        viewport_end: End offset of viewport
        record_count: Number of records that contributed spans
        span_index: SpanIndex for fast lookup (None if no spans)
    """
    spans: tuple[Span, ...]
    viewport_start: int
    viewport_end: int
    record_count: int
    span_index: SpanIndex | None


@dataclass(frozen=True)
class CoverageReport:
    """Immutable coverage analysis report.

    Attributes:
        file_size: Total size of file in bytes
        bytes_covered: Number of bytes covered by parsing
        bytes_uncovered: Number of bytes not covered
        coverage_percentage: Percentage of file covered (0-100)
        gaps: Uncovered byte ranges as (start, end) tuples
        record_count: Number of records parsed
        largest_gap: Largest uncovered range (None if no gaps)
    """
    file_size: int
    bytes_covered: int
    bytes_uncovered: int
    coverage_percentage: float
    gaps: tuple[tuple[int, int], ...]
    record_count: int
    largest_gap: tuple[int, int] | None


@dataclass(frozen=True)
class DecodeFieldInput:
    """Input for decode_field tool.

    Attributes:
        record: Parsed record to decode from
        grammar: Grammar with registry and decoder definitions
        field_name: Specific field to decode (None = use registry logic)
    """
    record: ParsedRecord
    grammar: Grammar
    field_name: str | None = None


@dataclass(frozen=True)
class DecodedValue:
    """Immutable decoded field result.

    Attributes:
        success: Whether decoding succeeded
        value: Decoded string value (None if failed)
        decoder_type: Type of decoder used (string, u16, u32, hex, ftm_packed_date, none)
        field_path: Path to the field that was decoded
        error: Error message if decoding failed
    """
    success: bool
    value: str | None
    decoder_type: str
    field_path: str
    error: str | None


@dataclass(frozen=True)
class QueryRecordsInput:
    """Input for query_records tool.

    Attributes:
        parse_result: Parse result containing records to query
        filter_type: Type of filter to apply
        filter_value: Value for the filter (type depends on filter_type)
    """
    parse_result: ParseResult
    filter_type: str  # "type", "offset_range", "has_field", "all"
    filter_value: str | tuple[int, int] | None = None


@dataclass(frozen=True)
class RecordSet:
    """Immutable query result set.

    Attributes:
        records: Filtered records as immutable tuple
        filter_applied: Description of filter that was applied
        total_count: Total number of records in result
        original_count: Number of records before filtering
    """
    records: tuple[ParsedRecord, ...]
    filter_applied: str
    total_count: int
    original_count: int


# ============================================================================
# TOOL HOST
# ============================================================================

class ToolHost:
    """Deterministic tool interface for binary analysis.

    All tools are static methods that take explicit input schemas
    and return explicit output schemas. No instance state.
    """

    @staticmethod
    def lint_grammar(input: LintGrammarInput) -> LintGrammarOutput:
        """Validate YAML grammar without parsing binary data.

        Checks:
        - YAML syntax correctness
        - Required sections present (format, types)
        - Valid type references in fields
        - Valid endianness values
        - Valid color specifications
        - Valid arithmetic expression syntax

        Does NOT:
        - Read binary files
        - Parse records
        - Access file system beyond grammar text

        Args:
            input: Grammar text to validate

        Returns:
            Validation result with grammar object or errors

        Examples:
            >>> result = ToolHost.lint_grammar(LintGrammarInput(yaml_text="format: record_stream\\n..."))
            >>> if result.success:
            ...     grammar = result.grammar
            ...     # Use grammar for parsing
            >>> else:
            ...     print(result.errors[0])
        """
        try:
            # Parse and validate grammar
            grammar = parse_yaml_grammar(input.yaml_text)

            # Additional validation checks for grammar quality
            warnings = []

            # Check for empty types section
            if not grammar.types:
                warnings.append("Grammar has no type definitions")

            # Check for unused types (defined but never referenced)
            referenced_types = set()

            # Collect types referenced in switch cases
            if grammar.record_switch:
                referenced_types.update(grammar.record_switch.cases.values())
                if grammar.record_switch.default:
                    referenced_types.add(grammar.record_switch.default)

            # Collect types referenced in field definitions
            for type_def in grammar.types.values():
                for field in type_def.fields:
                    if field.type in grammar.types:
                        referenced_types.add(field.type)

            # Find unused types
            defined_types = set(grammar.types.keys())
            unused = defined_types - referenced_types

            # Filter out types that might be entry points (no switch = all types are entry points)
            if grammar.record_switch and unused:
                warnings.append(f"Unused types: {', '.join(sorted(unused))}")

            # Check for registry entries without corresponding types
            if grammar.registry:
                registry_type_codes = set()
                for type_key in grammar.registry.keys():
                    registry_type_codes.add(type_key)

                # This is just informational - registry can define more than what's in switch
                if len(grammar.registry) > len(defined_types):
                    warnings.append(
                        f"Registry has {len(grammar.registry)} entries but only "
                        f"{len(defined_types)} types defined"
                    )

            return LintGrammarOutput(
                success=True,
                grammar=grammar,
                errors=(),
                warnings=tuple(warnings)
            )

        except Exception as e:
            # Any exception during parsing = validation failure
            return LintGrammarOutput(
                success=False,
                grammar=None,
                errors=(str(e),),
                warnings=()
            )

    @staticmethod
    def parse_binary(input: ParseBinaryInput) -> ParseResult:
        """Parse binary file using validated grammar.

        Reads the binary file and parses records according to the grammar.
        Parsing continues until:
        - End of file is reached
        - max_records limit is hit (if specified)
        - limit bytes have been parsed (if specified)
        - A fatal error occurs

        This is a pure function - same input always produces same output.
        File is only read, never modified.

        Args:
            input: Binary parsing parameters

        Returns:
            Parse result with records, errors, and metadata

        Examples:
            >>> grammar = ...  # From lint_grammar
            >>> result = ToolHost.parse_binary(ParseBinaryInput(
            ...     grammar=grammar,
            ...     file_path="/path/to/file.bin"
            ... ))
            >>> print(f"Parsed {result.record_count} records")
            >>> if result.errors:
            ...     print(f"Errors: {result.errors}")
        """
        start_time = time.time()

        try:
            # Open file for reading
            reader = PagedReader(input.file_path)

            # Create parser
            parser = RecordParser(input.grammar)

            # Parse records
            records = []
            errors = []
            offset = input.offset
            file_size = reader.size

            # Determine parse limit
            if input.limit is not None:
                parse_limit = min(input.offset + input.limit, file_size)
            else:
                parse_limit = file_size

            # Parse until stopping condition
            while offset < parse_limit:
                # Check max_records limit
                if input.max_records is not None and len(records) >= input.max_records:
                    break

                try:
                    record = parser.parse_record(reader, offset)

                    if record.error:
                        # Non-fatal error - record parse failed but we can report it
                        errors.append(f"Parse error at {offset:#x}: {record.error}")
                        # Stop parsing on error (conservative approach)
                        break

                    # Check if adding this record would exceed limit
                    if input.limit is not None:
                        record_end = offset + record.size
                        if record_end > input.offset + input.limit:
                            # Would exceed limit, stop
                            break

                    records.append(record)
                    offset += record.size

                except Exception as e:
                    # Fatal error
                    errors.append(f"Fatal error at {offset:#x}: {str(e)}")
                    break

            # Calculate metadata
            total_bytes = offset - input.offset
            timestamp = time.time()

            return ParseResult(
                records=tuple(records),
                errors=tuple(errors),
                file_path=input.file_path,
                grammar_format=input.grammar.format,
                total_bytes_parsed=total_bytes,
                parse_stopped_at=offset,
                timestamp=timestamp,
                record_count=len(records)
            )

        except Exception as e:
            # Failed to even start parsing
            return ParseResult(
                records=(),
                errors=(f"Failed to parse binary: {str(e)}",),
                file_path=input.file_path,
                grammar_format=input.grammar.format if input.grammar else "unknown",
                total_bytes_parsed=0,
                parse_stopped_at=input.offset,
                timestamp=time.time(),
                record_count=0
            )

    @staticmethod
    def generate_spans(input: GenerateSpansInput) -> SpanSet:
        """Generate field spans for viewport range.

        Only generates spans for records that overlap the viewport.
        This enables efficient rendering of large files by only processing
        visible data.

        This is a pure function - same input always produces same output.

        Args:
            input: Span generation parameters

        Returns:
            SpanSet with spans for viewport

        Examples:
            >>> parse_result = ToolHost.parse_binary(...)
            >>> span_set = ToolHost.generate_spans(GenerateSpansInput(
            ...     parse_result=parse_result,
            ...     viewport_start=0,
            ...     viewport_end=1024
            ... ))
            >>> print(f"Generated {len(span_set.spans)} spans")
            >>> print(f"From {span_set.record_count} records")
        """
        # Find records that overlap the viewport
        overlapping_record_indices = ToolHost._find_records_in_viewport(
            input.parse_result.records,
            input.viewport_start,
            input.viewport_end
        )

        # Generate spans for overlapping records
        spans = []
        for idx in overlapping_record_indices:
            record = input.parse_result.records[idx]
            if not record.error:
                ToolHost._add_record_spans(record, spans)

        # Build span index if we have spans
        span_index = None
        if spans:
            span_index = SpanIndex(spans)

        return SpanSet(
            spans=tuple(spans),
            viewport_start=input.viewport_start,
            viewport_end=input.viewport_end,
            record_count=len(overlapping_record_indices),
            span_index=span_index
        )

    @staticmethod
    def _find_records_in_viewport(
        records: tuple[ParsedRecord, ...],
        viewport_start: int,
        viewport_end: int
    ) -> list[int]:
        """Find record indices that overlap viewport range.

        Uses binary search for efficient lookup.
        """
        if not records:
            return []

        # Build offset list for binary search
        offsets = [r.offset for r in records]

        # Find first record that might overlap
        first_idx = bisect_right(offsets, viewport_start) - 1
        if first_idx < 0:
            first_idx = 0

        # Collect all overlapping records
        overlapping = []
        for i in range(first_idx, len(records)):
            record = records[i]
            record_end = record.offset + record.size

            # Record overlaps if it starts before viewport end and ends after viewport start
            if record.offset < viewport_end and record_end > viewport_start:
                overlapping.append(i)
            elif record.offset >= viewport_end:
                # Past viewport, stop searching
                break

        return overlapping

    @staticmethod
    def _add_record_spans(record: ParsedRecord, spans: list[Span]) -> None:
        """Add spans for all fields in a record.

        Recursively processes nested fields.
        """
        ToolHost._add_field_spans(
            record.type_name,
            record.fields,
            record.offset,
            spans,
            path_prefix=""
        )

    @staticmethod
    def _add_field_spans(
        type_name: str,
        fields: dict,
        base_offset: int,
        spans: list[Span],
        path_prefix: str
    ) -> None:
        """Recursively add field spans.

        Handles both leaf fields and nested types.
        """
        for field_name, parsed_field in fields.items():
            # Create field path
            if path_prefix:
                path = f"{path_prefix}.{field_name}"
            else:
                path = f"{type_name}.{field_name}" if type_name else field_name

            # Check if nested
            if parsed_field.nested_fields:
                # Recurse into nested fields
                ToolHost._add_field_spans("", parsed_field.nested_fields, base_offset, spans, path)
            else:
                # Leaf field - determine type group
                if isinstance(parsed_field.value, int):
                    group = "int"
                elif isinstance(parsed_field.value, str):
                    group = "string"
                elif isinstance(parsed_field.value, bytes):
                    group = "bytes"
                else:
                    group = "unknown"

                # Create span
                span = Span(
                    offset=parsed_field.offset,
                    length=parsed_field.size,
                    path=path,
                    group=group,
                    effective_endian=None,
                    endian_source=None,
                    color_override=parsed_field.color
                )
                spans.append(span)

    @staticmethod
    def analyze_coverage(input: AnalyzeCoverageInput) -> CoverageReport:
        """Analyze parse coverage - identify unparsed byte ranges.

        Examines which bytes in the file were covered by parsed records
        and identifies gaps (unparsed regions). Useful for:
        - Grammar debugging (finding missing patterns)
        - File format reverse engineering
        - Validating complete parsing
        - Finding hidden/trailer data

        This is a pure function - same input always produces same output.

        Args:
            input: Coverage analysis parameters

        Returns:
            Coverage report with statistics and gaps

        Examples:
            >>> parse_result = ToolHost.parse_binary(...)
            >>> coverage = ToolHost.analyze_coverage(AnalyzeCoverageInput(
            ...     parse_result=parse_result,
            ...     file_size=1024
            ... ))
            >>> print(f"Coverage: {coverage.coverage_percentage:.1f}%")
            >>> print(f"Gaps: {len(coverage.gaps)}")
        """
        # Build list of covered ranges from records
        covered_ranges = []
        for record in input.parse_result.records:
            if not record.error:
                covered_ranges.append((record.offset, record.offset + record.size))

        # Sort and merge overlapping ranges
        covered_ranges = ToolHost._merge_ranges(covered_ranges)

        # Calculate total bytes covered
        bytes_covered = sum(end - start for start, end in covered_ranges)
        bytes_uncovered = input.file_size - bytes_covered

        # Find gaps between covered ranges
        gaps = ToolHost._find_gaps(covered_ranges, input.file_size)

        # Find largest gap
        largest_gap = None
        if gaps:
            largest_gap = max(gaps, key=lambda g: g[1] - g[0])

        # Calculate coverage percentage
        coverage_percentage = (bytes_covered / input.file_size * 100) if input.file_size > 0 else 0.0

        return CoverageReport(
            file_size=input.file_size,
            bytes_covered=bytes_covered,
            bytes_uncovered=bytes_uncovered,
            coverage_percentage=coverage_percentage,
            gaps=tuple(gaps),
            record_count=len(input.parse_result.records),
            largest_gap=largest_gap
        )

    @staticmethod
    def _merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
        """Merge overlapping or adjacent ranges.

        Args:
            ranges: List of (start, end) tuples

        Returns:
            Merged list of non-overlapping ranges
        """
        if not ranges:
            return []

        # Sort by start position
        sorted_ranges = sorted(ranges)

        merged = [sorted_ranges[0]]
        for start, end in sorted_ranges[1:]:
            last_start, last_end = merged[-1]

            # Check if ranges overlap or are adjacent
            if start <= last_end:
                # Merge: extend the last range
                merged[-1] = (last_start, max(last_end, end))
            else:
                # No overlap: add as new range
                merged.append((start, end))

        return merged

    @staticmethod
    def _find_gaps(covered_ranges: list[tuple[int, int]], file_size: int) -> list[tuple[int, int]]:
        """Find gaps between covered ranges.

        Args:
            covered_ranges: Sorted, merged list of covered ranges
            file_size: Total file size

        Returns:
            List of (start, end) tuples for uncovered regions
        """
        if not covered_ranges:
            # Entire file is a gap
            if file_size > 0:
                return [(0, file_size)]
            return []

        gaps = []

        # Check for gap at start of file
        first_start, _ = covered_ranges[0]
        if first_start > 0:
            gaps.append((0, first_start))

        # Check for gaps between covered ranges
        for i in range(len(covered_ranges) - 1):
            _, current_end = covered_ranges[i]
            next_start, _ = covered_ranges[i + 1]

            if next_start > current_end:
                gaps.append((current_end, next_start))

        # Check for gap at end of file
        _, last_end = covered_ranges[-1]
        if last_end < file_size:
            gaps.append((last_end, file_size))

        return gaps

    @staticmethod
    def decode_field(input: DecodeFieldInput) -> DecodedValue:
        """Decode a field value using grammar registry rules.

        This tool extracts human-readable values from parsed record fields
        using decoder specifications in the grammar registry. It supports
        various decoding strategies:
        - string: Decode bytes to text with encoding
        - u16/u32: Convert bytes to integers
        - hex: Convert bytes to hex string
        - ftm_packed_date: Decode FTM date format

        Args:
            input: DecodeFieldInput with record, grammar, and optional field name

        Returns:
            DecodedValue with success status, decoded value, metadata

        Examples:
            >>> # Decode using registry (automatic field selection)
            >>> result = ToolHost.decode_field(
            ...     DecodeFieldInput(record=parsed_record, grammar=grammar)
            ... )
            >>> if result.success:
            ...     print(f"{result.field_path}: {result.value}")

            >>> # Decode specific field
            >>> result = ToolHost.decode_field(
            ...     DecodeFieldInput(
            ...         record=parsed_record,
            ...         grammar=grammar,
            ...         field_name="payload"
            ...     )
            ... )
        """
        record = input.record
        grammar = input.grammar

        # If field_name specified, decode that specific field
        if input.field_name:
            if input.field_name not in record.fields:
                return DecodedValue(
                    success=False,
                    value=None,
                    decoder_type="none",
                    field_path=input.field_name,
                    error=f"Field '{input.field_name}' not found in record",
                )

            target_field = record.fields[input.field_name]

            # Try to decode as string (simple heuristic)
            if isinstance(target_field.value, str):
                return DecodedValue(
                    success=True,
                    value=target_field.value,
                    decoder_type="string",
                    field_path=input.field_name,
                    error=None,
                )
            elif isinstance(target_field.value, bytes):
                try:
                    decoded = target_field.value.decode("utf-8", errors="replace")
                    return DecodedValue(
                        success=True,
                        value=decoded,
                        decoder_type="string",
                        field_path=input.field_name,
                        error=None,
                    )
                except:
                    return DecodedValue(
                        success=False,
                        value=None,
                        decoder_type="none",
                        field_path=input.field_name,
                        error="Failed to decode bytes as string",
                    )
            elif isinstance(target_field.value, int):
                return DecodedValue(
                    success=True,
                    value=str(target_field.value),
                    decoder_type="u32",  # Generic integer
                    field_path=input.field_name,
                    error=None,
                )
            else:
                return DecodedValue(
                    success=False,
                    value=None,
                    decoder_type="none",
                    field_path=input.field_name,
                    error=f"Unsupported field type: {type(target_field.value)}",
                )

        # Use registry-based decoding (from decode_record_payload logic)
        # Get type discriminator from header.type_raw
        type_disc = None
        if "header" in record.fields:
            header = record.fields["header"].value
            if isinstance(header, dict) and "type_raw" in header:
                type_disc = f"0x{header['type_raw']:04X}"

        if not type_disc:
            return DecodedValue(
                success=False,
                value=None,
                decoder_type="none",
                field_path="header.type_raw",
                error="Could not extract type discriminator from header.type_raw",
            )

        if type_disc not in grammar.registry:
            return DecodedValue(
                success=False,
                value=None,
                decoder_type="none",
                field_path="header.type_raw",
                error=f"Type discriminator {type_disc} not found in registry",
            )

        entry = grammar.registry[type_disc]
        decoder = entry.decode

        # Determine which field to decode
        target_field = None
        field_path = None

        if decoder.field:
            # Decode specific field
            if decoder.field in record.fields:
                target_field = record.fields[decoder.field]
                field_path = decoder.field
        elif "payload" in record.fields:
            # Default to payload field
            target_field = record.fields["payload"]
            field_path = "payload"

        if not target_field:
            return DecodedValue(
                success=False,
                value=None,
                decoder_type=decoder.as_type,
                field_path=decoder.field or "payload",
                error=f"Target field not found in record",
            )

        # Decode based on decoder type
        if decoder.as_type == "string":
            if isinstance(target_field.value, str):
                return DecodedValue(
                    success=True,
                    value=target_field.value,
                    decoder_type="string",
                    field_path=field_path,
                    error=None,
                )
            elif isinstance(target_field.value, bytes):
                encoding = decoder.encoding or "ascii"
                try:
                    decoded = target_field.value.decode(encoding, errors="replace")
                    return DecodedValue(
                        success=True,
                        value=decoded,
                        decoder_type="string",
                        field_path=field_path,
                        error=None,
                    )
                except Exception as e:
                    return DecodedValue(
                        success=False,
                        value=None,
                        decoder_type="string",
                        field_path=field_path,
                        error=f"Failed to decode as string: {e}",
                    )

        elif decoder.as_type in ("u16", "u32"):
            if isinstance(target_field.value, int):
                return DecodedValue(
                    success=True,
                    value=str(target_field.value),
                    decoder_type=decoder.as_type,
                    field_path=field_path,
                    error=None,
                )
            elif isinstance(target_field.value, bytes):
                size = 2 if decoder.as_type == "u16" else 4
                if len(target_field.value) >= size:
                    # Use decoder endian or fall back to grammar global endian
                    decoder_endian = decoder.endian or grammar.endian
                    endian = "little" if decoder_endian == EndianType.LITTLE else "big"
                    try:
                        value = int.from_bytes(target_field.value[:size], endian)
                        return DecodedValue(
                            success=True,
                            value=str(value),
                            decoder_type=decoder.as_type,
                            field_path=field_path,
                            error=None,
                        )
                    except Exception as e:
                        return DecodedValue(
                            success=False,
                            value=None,
                            decoder_type=decoder.as_type,
                            field_path=field_path,
                            error=f"Failed to decode as {decoder.as_type}: {e}",
                        )
                else:
                    return DecodedValue(
                        success=False,
                        value=None,
                        decoder_type=decoder.as_type,
                        field_path=field_path,
                        error=f"Insufficient bytes for {decoder.as_type} (need {size}, got {len(target_field.value)})",
                    )

        elif decoder.as_type == "hex":
            if isinstance(target_field.value, bytes):
                return DecodedValue(
                    success=True,
                    value=target_field.value.hex(),
                    decoder_type="hex",
                    field_path=field_path,
                    error=None,
                )
            else:
                return DecodedValue(
                    success=False,
                    value=None,
                    decoder_type="hex",
                    field_path=field_path,
                    error="Field value is not bytes",
                )

        elif decoder.as_type == "ftm_packed_date":
            if isinstance(target_field.value, bytes) and len(target_field.value) >= 4:
                # FTM Packed Date format (4 bytes):
                # byte0: (day << 3) | flags
                # byte1: (month << 1) | must_be_zero
                # byte2-3: year (u16 LE)
                try:
                    b0, b1, year_lo, year_hi = target_field.value[:4]
                    day = b0 >> 3
                    month = b1 >> 1
                    year = year_lo | (year_hi << 8)

                    # Validate
                    if b1 & 0x01 == 0 and 1 <= month <= 12 and 1 <= day <= 31 and year > 0:
                        date_str = f"{year:04d}-{month:02d}-{day:02d}"
                        return DecodedValue(
                            success=True,
                            value=date_str,
                            decoder_type="ftm_packed_date",
                            field_path=field_path,
                            error=None,
                        )
                    else:
                        return DecodedValue(
                            success=False,
                            value=None,
                            decoder_type="ftm_packed_date",
                            field_path=field_path,
                            error="Invalid FTM date values",
                        )
                except (ValueError, IndexError) as e:
                    return DecodedValue(
                        success=False,
                        value=None,
                        decoder_type="ftm_packed_date",
                        field_path=field_path,
                        error=f"Failed to decode FTM date: {e}",
                    )
            else:
                return DecodedValue(
                    success=False,
                    value=None,
                    decoder_type="ftm_packed_date",
                    field_path=field_path,
                    error="Insufficient bytes for FTM date (need 4)",
                )

        # Unknown decoder type
        return DecodedValue(
            success=False,
            value=None,
            decoder_type=decoder.as_type,
            field_path=field_path,
            error=f"Unsupported decoder type: {decoder.as_type}",
        )

    @staticmethod
    def query_records(input: QueryRecordsInput) -> RecordSet:
        """Query and filter records from parse results.

        This tool enables exploratory analysis and record filtering based
        on various criteria. Useful for finding specific records, analyzing
        subsets, or extracting records in a given range.

        Supported filter types:
        - "all": Return all records (no filtering)
        - "type": Filter by record type name
        - "offset_range": Filter by byte offset range
        - "has_field": Filter records containing a specific field

        Args:
            input: QueryRecordsInput with parse result, filter type, and value

        Returns:
            RecordSet with filtered records and metadata

        Examples:
            >>> # Get all records
            >>> result = ToolHost.query_records(
            ...     QueryRecordsInput(
            ...         parse_result=parse_result,
            ...         filter_type="all"
            ...     )
            ... )

            >>> # Filter by type
            >>> result = ToolHost.query_records(
            ...     QueryRecordsInput(
            ...         parse_result=parse_result,
            ...         filter_type="type",
            ...         filter_value="NameRecord"
            ...     )
            ... )

            >>> # Filter by offset range
            >>> result = ToolHost.query_records(
            ...     QueryRecordsInput(
            ...         parse_result=parse_result,
            ...         filter_type="offset_range",
            ...         filter_value=(100, 500)
            ...     )
            ... )

            >>> # Filter by field presence
            >>> result = ToolHost.query_records(
            ...     QueryRecordsInput(
            ...         parse_result=parse_result,
            ...         filter_type="has_field",
            ...         filter_value="payload"
            ...     )
            ... )
        """
        parse_result = input.parse_result
        filter_type = input.filter_type
        filter_value = input.filter_value

        original_count = len(parse_result.records)

        # Filter: all - return all records
        if filter_type == "all":
            return RecordSet(
                records=parse_result.records,
                filter_applied="all records",
                total_count=original_count,
                original_count=original_count,
            )

        # Filter: type - filter by record type name
        elif filter_type == "type":
            if not isinstance(filter_value, str):
                # Return empty with error description
                return RecordSet(
                    records=(),
                    filter_applied=f"type={filter_value} (invalid: expected string)",
                    total_count=0,
                    original_count=original_count,
                )

            filtered = tuple(r for r in parse_result.records if r.type_name == filter_value)

            return RecordSet(
                records=filtered,
                filter_applied=f"type={filter_value}",
                total_count=len(filtered),
                original_count=original_count,
            )

        # Filter: offset_range - filter by byte offset range
        elif filter_type == "offset_range":
            if not isinstance(filter_value, tuple) or len(filter_value) != 2:
                # Return empty with error description
                return RecordSet(
                    records=(),
                    filter_applied=f"offset_range={filter_value} (invalid: expected (start, end) tuple)",
                    total_count=0,
                    original_count=original_count,
                )

            start_offset, end_offset = filter_value

            # Filter records that overlap with the range
            filtered = tuple(
                r
                for r in parse_result.records
                if r.offset < end_offset and (r.offset + r.size) > start_offset
            )

            return RecordSet(
                records=filtered,
                filter_applied=f"offset_range=({start_offset:#x}, {end_offset:#x})",
                total_count=len(filtered),
                original_count=original_count,
            )

        # Filter: has_field - filter records containing a specific field
        elif filter_type == "has_field":
            if not isinstance(filter_value, str):
                # Return empty with error description
                return RecordSet(
                    records=(),
                    filter_applied=f"has_field={filter_value} (invalid: expected string)",
                    total_count=0,
                    original_count=original_count,
                )

            filtered = tuple(r for r in parse_result.records if filter_value in r.fields)

            return RecordSet(
                records=filtered,
                filter_applied=f"has_field={filter_value}",
                total_count=len(filtered),
                original_count=original_count,
            )

        # Unknown filter type
        else:
            return RecordSet(
                records=(),
                filter_applied=f"{filter_type} (unknown filter type)",
                total_count=0,
                original_count=original_count,
            )
