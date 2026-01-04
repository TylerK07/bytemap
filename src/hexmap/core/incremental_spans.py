"""Viewport-based span generation for large YAML-parsed files."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from typing import TYPE_CHECKING

from hexmap.core.spans import Span, SpanIndex

if TYPE_CHECKING:
    from hexmap.core.yaml_parser import ParsedRecord


@dataclass
class RecordOffset:
    """Lightweight record location info."""

    offset: int  # File offset where this record starts
    size: int  # Record size in bytes
    record_index: int  # Index into records list


class IncrementalSpanManager:
    """Viewport-based span generation.

    Builds lightweight offset index upfront, then generates spans only
    for records visible in current viewport.
    """

    def __init__(self, records: list[ParsedRecord]) -> None:
        self.records = records
        self._record_offsets: list[RecordOffset] = []
        self._current_viewport_start: int = -1
        self._current_viewport_end: int = -1
        self._cached_spans: list[Span] = []
        self._cached_span_index: SpanIndex | None = None

        # Build lightweight offset index (fast, just offset + size)
        self._build_offset_index()

    def _build_offset_index(self) -> None:
        """Build lightweight index of record offsets and sizes."""
        for i, record in enumerate(self.records):
            if not record.error:
                self._record_offsets.append(
                    RecordOffset(offset=record.offset, size=record.size, record_index=i)
                )

    def update_viewport(self, viewport_start: int, viewport_end: int) -> SpanIndex | None:
        """Update spans for current viewport.

        Generates spans only for records visible in viewport.
        Returns SpanIndex if viewport changed, None if cached.
        """
        # Check if viewport unchanged
        if (
            viewport_start == self._current_viewport_start
            and viewport_end == self._current_viewport_end
        ):
            return self._cached_span_index

        # Find records that overlap the viewport
        record_indices = self._find_records_in_range(viewport_start, viewport_end)

        # Generate spans for visible records only
        self._cached_spans = []
        for idx in record_indices:
            record = self.records[idx]
            self._add_record_spans(record)

        # Build span index from generated spans
        if self._cached_spans:
            self._cached_span_index = SpanIndex(self._cached_spans)
        else:
            self._cached_span_index = None

        # Update cached viewport
        self._current_viewport_start = viewport_start
        self._current_viewport_end = viewport_end

        return self._cached_span_index

    def get_span_index(self) -> SpanIndex | None:
        """Get cached span index for current viewport."""
        return self._cached_span_index

    def _find_records_in_range(self, start: int, end: int) -> list[int]:
        """Find record indices that overlap [start, end) range."""
        if not self._record_offsets:
            return []

        # Use binary search to find first record that might overlap
        offsets = [r.offset for r in self._record_offsets]
        first_idx = bisect_right(offsets, start) - 1
        if first_idx < 0:
            first_idx = 0

        # Collect all overlapping records
        overlapping = []
        for i in range(first_idx, len(self._record_offsets)):
            rec = self._record_offsets[i]
            rec_end = rec.offset + rec.size

            # Record overlaps if it starts before viewport end and ends after viewport start
            if rec.offset < end and rec_end > start:
                overlapping.append(rec.record_index)
            elif rec.offset >= end:
                # Past viewport, stop searching
                break

        return overlapping

    def _add_record_spans(self, record) -> None:
        """Add spans for a single record."""
        if record.error:
            return

        # Generate spans for each field
        self._add_field_spans(record.type_name, record.fields, record.offset)

    def _add_field_spans(
        self, type_name: str, fields: dict, base_offset: int, path_prefix: str = ""
    ) -> None:
        """Recursively add field spans."""
        for field_name, parsed_field in fields.items():
            # Create field path
            if path_prefix:
                path = f"{path_prefix}.{field_name}"
            else:
                path = f"{type_name}.{field_name}" if type_name else field_name

            # Check if nested
            if parsed_field.nested_fields:
                # Recurse into nested fields
                self._add_field_spans("", parsed_field.nested_fields, base_offset, path)
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
                    color_override=parsed_field.color,
                )
                self._cached_spans.append(span)
