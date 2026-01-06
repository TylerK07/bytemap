"""Unified parsing pipeline for all tabs.

This module provides a single entrypoint for parsing binary files using ToolHost
with execution profiles. All tabs (Explore, Chunking, Workbench) should use this
to ensure consistent parsing behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hexmap.core.coverage import compute_coverage
from hexmap.core.execution_profiles import ExecutionProfile
from hexmap.core.io import PagedReader
from hexmap.core.parse import ParsedField, ParsedNode
from hexmap.core.parse_bridge import (
    convert_records_to_nodes,
    convert_spans_to_overlays,
    convert_spans_to_parsed_fields,
)
from hexmap.core.spans import Span, SpanIndex
from hexmap.core.tool_host import (
    GenerateSpansInput,
    LintGrammarInput,
    ParseBinaryInput,
    ToolHost,
)


@dataclass
class UnifiedParseResult:
    """Result of unified parsing operation.

    Contains all data needed by Explore, Chunking, and Workbench tabs.
    """

    # Success/Error status
    success: bool
    errors: list[str]
    warnings: list[str]

    # Grammar validation
    grammar: str | None  # Validated grammar text (None if lint failed)

    # Parse results (None if parsing failed)
    tree: list[ParsedNode] | None  # Hierarchical tree for OutputPanel
    leaves: list[ParsedField] | None  # Flat field list for coverage
    overlays: list[tuple[int, int, str, str]] | None  # Overlays for HexView
    spans: list[Span] | None  # Spans for SpanIndex
    span_index: SpanIndex | None  # Index for linking

    # Coverage analysis (None if parsing failed)
    covered: list[tuple[int, int, str]] | None  # Covered regions
    unmapped: list[tuple[int, int]] | None  # Unmapped regions
    coverage_percent: float  # Percentage of file covered (0-100)

    # Metadata
    record_count: int  # Number of records parsed
    bytes_parsed: int  # Total bytes parsed
    profile_name: str  # Which profile was used


def unified_parse(
    yaml_text: str,
    file_path: str,
    profile: ExecutionProfile,
    viewport_start: int = 0,
    viewport_end: int | None = None,
) -> UnifiedParseResult:
    """Parse binary file with unified ToolHost pipeline.

    This is the single entrypoint for all tabs to parse binary files.
    Uses ToolHost for validation and parsing, with profile-specific parameters.

    Args:
        yaml_text: YAML grammar text
        file_path: Path to binary file
        profile: Execution profile (EXPLORE_PROFILE, CHUNKING_PROFILE, etc.)
        viewport_start: Start offset for span generation (default: 0)
        viewport_end: End offset for span generation (default: file size)

    Returns:
        UnifiedParseResult with all data needed by tabs

    Examples:
        >>> from hexmap.core.execution_profiles import EXPLORE_PROFILE
        >>> result = unified_parse(
        ...     yaml_text=my_grammar,
        ...     file_path="/path/to/file.bin",
        ...     profile=EXPLORE_PROFILE
        ... )
        >>> if result.success:
        ...     print(f"Parsed {result.record_count} records")
        ...     output_panel.set_tree(result.tree)
        ...     hex_view.set_overlays(result.overlays)
    """
    # Step 1: Validate grammar
    lint_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml_text))

    if not lint_result.success:
        return UnifiedParseResult(
            success=False,
            errors=list(lint_result.errors),
            warnings=list(lint_result.warnings),
            grammar=None,
            tree=None,
            leaves=None,
            overlays=None,
            spans=None,
            span_index=None,
            covered=None,
            unmapped=None,
            coverage_percent=0.0,
            record_count=0,
            bytes_parsed=0,
            profile_name=profile.name,
        )

    # Step 2: Parse binary file
    parse_result = ToolHost.parse_binary(
        ParseBinaryInput(
            grammar=lint_result.grammar,
            file_path=file_path,
            offset=profile.offset,
            limit=profile.limit,
            max_records=profile.max_records,
        )
    )

    if parse_result.errors:
        return UnifiedParseResult(
            success=False,
            errors=list(parse_result.errors),
            warnings=list(lint_result.warnings),
            grammar=lint_result.grammar,
            tree=None,
            leaves=None,
            overlays=None,
            spans=None,
            span_index=None,
            covered=None,
            unmapped=None,
            coverage_percent=0.0,
            record_count=parse_result.record_count,
            bytes_parsed=parse_result.total_bytes_parsed,
            profile_name=profile.name,
        )

    # Step 3: Generate spans (if enabled in profile)
    spans = []
    span_index = None

    if profile.enable_span_generation:
        # Determine viewport range
        reader = PagedReader(file_path)
        if viewport_end is None:
            viewport_end = reader.size

        span_set = ToolHost.generate_spans(
            GenerateSpansInput(
                parse_result=parse_result,
                viewport_start=viewport_start,
                viewport_end=viewport_end,
            )
        )
        spans = list(span_set.spans)
        span_index = span_set.span_index

    # Step 4: Convert to legacy format for compatibility
    tree = convert_records_to_nodes(list(parse_result.records))
    leaves = convert_spans_to_parsed_fields(spans) if spans else []
    overlays = convert_spans_to_overlays(spans) if spans else []

    # Step 5: Compute coverage (if enabled in profile)
    covered = []
    unmapped = []
    coverage_percent = 0.0

    if profile.enable_coverage_analysis and leaves:
        reader = PagedReader(file_path)
        file_size = reader.size
        covered, unmapped = compute_coverage(leaves, file_size)

        if file_size > 0:
            unmapped_bytes = sum(length for (_offset, length) in unmapped)
            coverage_percent = max(0.0, min(100.0, (1 - unmapped_bytes / file_size) * 100.0))

    # Success!
    return UnifiedParseResult(
        success=True,
        errors=[],
        warnings=list(lint_result.warnings),
        grammar=lint_result.grammar,
        tree=tree,
        leaves=leaves,
        overlays=overlays,
        spans=spans,
        span_index=span_index,
        covered=covered,
        unmapped=unmapped,
        coverage_percent=coverage_percent,
        record_count=parse_result.record_count,
        bytes_parsed=parse_result.total_bytes_parsed,
        profile_name=profile.name,
    )
