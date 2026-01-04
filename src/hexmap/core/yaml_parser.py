"""Record parser using YAML grammar definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hexmap.core.io import PagedReader
from hexmap.core.yaml_grammar import (
    ArithmeticEvaluator,
    EndianType,
    FieldDef,
    Grammar,
    PrimitiveType,
    TypeDef,
)


@dataclass
class ParsedField:
    """A parsed field value."""

    name: str
    value: Any  # int, bytes, or nested dict
    raw_bytes: bytes
    offset: int
    size: int
    nested_fields: dict[str, "ParsedField"] | None = None  # For nested records
    color: str | None = None  # Color override from field definition


@dataclass
class ParsedRecord:
    """A parsed record."""

    offset: int
    size: int
    type_name: str
    fields: dict[str, ParsedField]
    type_discriminator: str | None = None  # The actual type value (e.g., "0x4E54")
    error: str | None = None


class RecordParser:
    """Parser for records using YAML grammar."""

    def __init__(self, grammar: Grammar):
        self.grammar = grammar
        self.evaluator = ArithmeticEvaluator()

    def parse_file(self, reader: PagedReader) -> tuple[list[ParsedRecord], list[str]]:
        """
        Parse entire file using grammar.

        Returns:
            (records, errors) - List of parsed records and error messages
        """
        records = []
        errors = []
        offset = 0
        file_size = reader.size

        while offset < file_size:
            try:
                record = self.parse_record(reader, offset)
                if record.error:
                    errors.append(f"Parse error at {offset:#x}: {record.error}")
                    break

                records.append(record)
                offset += record.size

            except Exception as e:
                errors.append(f"Fatal error at {offset:#x}: {e}")
                break

        return records, errors

    def parse_record(self, reader: PagedReader, offset: int) -> ParsedRecord:
        """Parse a single record at given offset."""
        # Determine which type to parse
        type_def = self._determine_record_type(reader, offset)

        if not type_def:
            return ParsedRecord(
                offset=offset,
                size=0,
                type_name="unknown",
                fields={},
                error="Could not determine record type",
            )

        # Parse the record
        return self._parse_type(reader, offset, type_def)

    def _determine_record_type(self, reader: PagedReader, offset: int) -> TypeDef | None:
        """Determine which type definition to use for this record."""
        if not self.grammar.record_switch:
            # No switch, use default type if specified
            if self.grammar.types:
                # Use first type as default
                return list(self.grammar.types.values())[0]
            return None

        # Parse enough to evaluate the switch expression
        switch = self.grammar.record_switch

        # Parse the header or fields needed for discrimination
        # For now, assume the discriminator is in a header type
        parts = switch.expr.split(".")
        if len(parts) != 2:
            return None

        container_name, field_name = parts

        # Parse the container type
        if container_name not in self.grammar.types:
            return None

        container_type = self.grammar.types[container_name]
        container_record = self._parse_type(reader, offset, container_type, partial=True)

        if container_record.error:
            return None

        # Get discriminator value
        if field_name not in container_record.fields:
            return None

        discriminator_field = container_record.fields[field_name]
        discriminator_value = discriminator_field.value

        # Convert to hex string for matching
        if isinstance(discriminator_value, int):
            disc_hex = f"0x{discriminator_value:04X}"
        else:
            return None

        # Look up in switch cases
        target_type_name = switch.cases.get(disc_hex, switch.default)

        if target_type_name not in self.grammar.types:
            return None

        return self.grammar.types[target_type_name]

    def _parse_type(
        self,
        reader: PagedReader,
        offset: int,
        type_def: TypeDef,
        partial: bool = False,
    ) -> ParsedRecord:
        """
        Parse a record of a specific type.

        Args:
            reader: File reader
            offset: Starting offset
            type_def: Type definition
            partial: If True, only parse enough fields for discrimination

        Returns:
            Parsed record
        """
        fields = {}
        current_offset = offset
        context = {}  # Field values for expression evaluation

        for field_def in type_def.fields:
            try:
                parsed_field = self._parse_field(reader, current_offset, field_def, context)

                if parsed_field is None:
                    return ParsedRecord(
                        offset=offset,
                        size=current_offset - offset,
                        type_name=type_def.name,
                        fields=fields,
                        error=f"Failed to parse field {field_def.name}",
                    )

                fields[field_def.name] = parsed_field
                context[field_def.name] = parsed_field.value
                current_offset += parsed_field.size

                # If partial parse and we have enough for discrimination, stop
                if partial and field_def.name == "type_raw":
                    break

            except Exception as e:
                return ParsedRecord(
                    offset=offset,
                    size=current_offset - offset,
                    type_name=type_def.name,
                    fields=fields,
                    error=f"Error parsing field {field_def.name}: {e}",
                )

        return ParsedRecord(
            offset=offset,
            size=current_offset - offset,
            type_name=type_def.name,
            fields=fields,
        )

    def _parse_field(
        self,
        reader: PagedReader,
        offset: int,
        field_def: FieldDef,
        context: dict[str, int],
    ) -> ParsedField | None:
        """Parse a single field."""
        # Check if this is a custom type (nested record)
        if field_def.type in self.grammar.types:
            # Parse nested type
            nested_type = self.grammar.types[field_def.type]
            nested_record = self._parse_type(reader, offset, nested_type)

            if nested_record.error:
                return None

            # Flatten nested fields into a dict
            nested_dict = {name: f.value for name, f in nested_record.fields.items()}

            # Also add nested fields to context for later expressions
            for name, field in nested_record.fields.items():
                context[name] = field.value

            return ParsedField(
                name=field_def.name,
                value=nested_dict,
                raw_bytes=b"",  # Not applicable for nested
                offset=offset,
                size=nested_record.size,
                nested_fields=nested_record.fields,  # Preserve nested fields
                color=field_def.color,
            )

        # Parse primitive type
        try:
            prim_type = PrimitiveType(field_def.type)
        except ValueError:
            return None

        if prim_type == PrimitiveType.U8:
            data = reader.read(offset, 1)
            if len(data) != 1:
                return None

            value = data[0]

            # Validation
            if field_def.validate:
                if not self._validate(value, field_def.validate, context):
                    return None

            return ParsedField(
                name=field_def.name,
                value=value,
                raw_bytes=data,
                offset=offset,
                size=1,
                color=field_def.color,
            )

        elif prim_type in (PrimitiveType.U16, PrimitiveType.U32):
            size = 2 if prim_type == PrimitiveType.U16 else 4
            data = reader.read(offset, size)
            if len(data) != size:
                return None

            # Determine endianness (field-level overrides global default)
            field_endian = field_def.endian or self.grammar.endian
            endian = "little" if field_endian == EndianType.LITTLE else "big"
            value = int.from_bytes(data, endian, signed=False)

            # Validation
            if field_def.validate:
                if not self._validate(value, field_def.validate, context):
                    return None

            return ParsedField(
                name=field_def.name,
                value=value,
                raw_bytes=data,
                offset=offset,
                size=size,
                color=field_def.color,
            )

        elif prim_type == PrimitiveType.BYTES:
            # Determine length
            length = self._determine_bytes_length(field_def, context)
            if length is None or length < 0:
                return None

            data = reader.read(offset, length)
            if len(data) != length:
                return None

            # Validation
            if field_def.validate:
                if not self._validate(data, field_def.validate, context):
                    return None

            # Store as bytes or decode as string
            value = data
            if field_def.encoding:
                try:
                    value = data.decode(field_def.encoding, errors="replace")
                except:
                    pass

            return ParsedField(
                name=field_def.name,
                value=value,
                raw_bytes=data,
                offset=offset,
                size=length,
                color=field_def.color,
            )

        return None

    def _determine_bytes_length(self, field_def: FieldDef, context: dict[str, int]) -> int | None:
        """Determine length for a bytes field."""
        if field_def.length is not None:
            return field_def.length

        if field_def.length_field:
            if field_def.length_field in context:
                return context[field_def.length_field]
            return None

        if field_def.length_expr:
            try:
                return self.evaluator.evaluate(field_def.length_expr, context)
            except Exception:
                return None

        return None

    def _validate(self, value: Any, rule, context: dict[str, int]) -> bool:
        """Validate a field value."""
        if rule.rule_type == "equals":
            return value == rule.value

        elif rule.rule_type == "equals_field":
            if rule.value in context:
                return value == context[rule.value]
            return False

        elif rule.rule_type == "all_bytes":
            if isinstance(value, bytes):
                return all(b == rule.value for b in value)
            return False

        return True


def decode_record_payload(
    record: ParsedRecord,
    grammar: Grammar,
) -> str | None:
    """
    Decode a record's payload using the registry.

    Args:
        record: Parsed record
        grammar: Grammar with registry

    Returns:
        Decoded string or None
    """
    # Get type discriminator from header.type_raw
    type_disc = None
    if "header" in record.fields:
        header = record.fields["header"].value
        if isinstance(header, dict) and "type_raw" in header:
            type_disc = f"0x{header['type_raw']:04X}"

    if not type_disc or type_disc not in grammar.registry:
        return None

    entry = grammar.registry[type_disc]
    decoder = entry.decode

    # Determine which field to decode
    target_field = None
    if decoder.field:
        # Decode specific field
        if decoder.field in record.fields:
            target_field = record.fields[decoder.field]
    elif "payload" in record.fields:
        # Default to payload field
        target_field = record.fields["payload"]

    if not target_field:
        return None

    # Decode based on type
    if decoder.as_type == "string":
        if isinstance(target_field.value, str):
            return target_field.value
        elif isinstance(target_field.value, bytes):
            encoding = decoder.encoding or "ascii"
            try:
                return target_field.value.decode(encoding, errors="replace")
            except:
                return None

    elif decoder.as_type in ("u16", "u32"):
        if isinstance(target_field.value, int):
            return str(target_field.value)
        elif isinstance(target_field.value, bytes):
            size = 2 if decoder.as_type == "u16" else 4
            if len(target_field.value) >= size:
                # Use decoder endian or fall back to grammar global endian
                decoder_endian = decoder.endian or grammar.endian
                endian = "little" if decoder_endian == EndianType.LITTLE else "big"
                value = int.from_bytes(target_field.value[:size], endian)
                return str(value)

    elif decoder.as_type == "hex":
        if isinstance(target_field.value, bytes):
            return target_field.value.hex()

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
                    return f"{year:04d}-{month:02d}-{day:02d}"
            except (ValueError, IndexError):
                pass

    return None
