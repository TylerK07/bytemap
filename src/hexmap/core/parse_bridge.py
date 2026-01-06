"""Bridge between ToolHost parsing and legacy Explore tab format.

This module provides converters that transform ToolHost output (ParsedRecord, Span)
into the legacy formats expected by Explore tab widgets (ParsedNode, ParsedField).

This enables Explore tab to use the unified ToolHost parser while maintaining
backwards compatibility with existing UI components.
"""

from __future__ import annotations

from typing import Any

from hexmap.core.parse import ParsedField, ParsedNode
from hexmap.core.spans import Span
from hexmap.core.yaml_parser import ParsedRecord


def convert_records_to_nodes(records: list[ParsedRecord]) -> list[ParsedNode]:
    """Convert ToolHost ParsedRecord objects to legacy ParsedNode format.

    Args:
        records: List of parsed records from ToolHost

    Returns:
        List of ParsedNode objects for OutputPanel tree view
    """
    nodes = []
    for idx, record in enumerate(records):
        node = _convert_record_to_node(record, idx)
        nodes.append(node)
    return nodes


def _convert_record_to_node(record: ParsedRecord, record_idx: int) -> ParsedNode:
    """Convert a single ParsedRecord to ParsedNode.

    Args:
        record: Parsed record from ToolHost
        record_idx: Index of record in file (for path construction)

    Returns:
        ParsedNode with hierarchical structure
    """
    # Create path: record[0], record[1], etc.
    path = f"record[{record_idx}]"

    # Convert fields to children
    children = []
    for field_name, field_value in record.fields.items():
        child_path = f"{path}.{field_name}"
        child = _convert_field_to_node(field_value, child_path, field_name)
        children.append(child)

    # Create parent node for the record
    return ParsedNode(
        path=path,
        offset=record.offset,
        length=record.size,
        type=record.type_name,
        value=None,  # Records don't have direct values
        error=record.error,
        children=children if children else None,
        effective_endian=None,  # Not tracked at record level
        endian_source=None,
        format=None,
        formatted_value=None,
        color_override=None,
    )


def _convert_field_to_node(
    field: Any, path: str, name: str
) -> ParsedNode:
    """Convert a field value to ParsedNode.

    Args:
        field: Field value from ParsedRecord (could be primitive or nested)
        path: Full path to this field
        name: Field name

    Returns:
        ParsedNode for this field
    """
    # Handle different field types
    if isinstance(field, dict):
        # Nested structure (e.g., struct fields)
        if "offset" in field and "size" in field:
            # This is a field descriptor
            return ParsedNode(
                path=path,
                offset=field.get("offset", 0),
                length=field.get("size", 0),
                type=field.get("type", "unknown"),
                value=field.get("value"),
                error=field.get("error"),
                children=None,
                effective_endian=field.get("endian"),
                endian_source=None,
                format=None,
                formatted_value=None,
                color_override=field.get("color"),
            )
        else:
            # Nested dict - convert each entry to child
            children = []
            for child_name, child_value in field.items():
                child_path = f"{path}.{child_name}"
                child = _convert_field_to_node(child_value, child_path, child_name)
                children.append(child)
            return ParsedNode(
                path=path,
                offset=0,
                length=None,
                type="struct",
                value=None,
                error=None,
                children=children if children else None,
            )
    elif isinstance(field, list):
        # Array of items
        children = []
        for idx, item in enumerate(field):
            child_path = f"{path}[{idx}]"
            child = _convert_field_to_node(item, child_path, f"[{idx}]")
            children.append(child)
        return ParsedNode(
            path=path,
            offset=0,
            length=None,
            type="array",
            value=None,
            error=None,
            children=children if children else None,
        )
    else:
        # Primitive value
        return ParsedNode(
            path=path,
            offset=0,
            length=None,
            type=type(field).__name__,
            value=field,
            error=None,
            children=None,
        )


def convert_spans_to_overlays(spans: list[Span]) -> list[tuple[int, int, str, str]]:
    """Convert ToolHost Span objects to legacy overlay format.

    Args:
        spans: List of Span objects from ToolHost.generate_spans()

    Returns:
        List of overlay tuples (offset, length, path, group)
    """
    overlays = []
    for span in spans:
        overlays.append((span.offset, span.length, span.path, span.group))
    return overlays


def convert_spans_to_parsed_fields(spans: list[Span]) -> list[ParsedField]:
    """Convert ToolHost Span objects to ParsedField objects.

    Args:
        spans: List of Span objects from ToolHost

    Returns:
        List of ParsedField objects for coverage computation
    """
    fields = []
    for span in spans:
        field = ParsedField(
            name=span.path,  # Span uses 'path' not 'name'
            offset=span.offset,
            length=span.length,
            type=span.group,  # Span uses 'group' not 'kind'
            value=None,  # Spans don't carry decoded values
            error=None,  # Spans don't have errors
            effective_endian=span.effective_endian or "little",
            endian_source=span.endian_source or "default",
            format=None,
            formatted_value=None,
            color_override=span.color_override,
        )
        fields.append(field)
    return fields
