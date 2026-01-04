"""YAML-driven record grammar parser."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import yaml

from hexmap.core.schema import normalize_color


class EndianType(Enum):
    """Byte order for multi-byte integers."""

    LITTLE = "little"
    BIG = "big"


class PrimitiveType(Enum):
    """Primitive field types."""

    U8 = "u8"
    U16 = "u16"
    U32 = "u32"
    BYTES = "bytes"


@dataclass
class ValidationRule:
    """Validation rule for a field."""

    rule_type: str  # "equals", "equals_field", "all_bytes"
    value: Any


@dataclass
class FieldDef:
    """Field definition in a record type."""

    name: str
    type: str  # Primitive type name or custom type name
    endian: EndianType | None = None
    length: int | None = None  # Fixed length for bytes
    length_field: str | None = None  # Reference to another field for length
    length_expr: str | None = None  # Arithmetic expression for length
    validate: ValidationRule | None = None
    encoding: str | None = None  # For bytes with text encoding
    color: str | None = None  # Color override (named color or #RGB/#RRGGBB)


@dataclass
class TypeDef:
    """Record type definition."""

    name: str
    fields: list[FieldDef]


@dataclass
class SwitchCase:
    """Switch case mapping for variant records."""

    expr: str  # Field path like "header.type"
    cases: dict[str, str]  # hex value -> type name
    default: str  # default type name


@dataclass
class FramingDef:
    """Top-level framing definition."""

    repeat: str = "until_eof"


@dataclass
class DecoderDef:
    """Decoder definition for registry."""

    as_type: str  # "string", "u16", "u32", "hex", "bytes"
    encoding: str | None = None  # For string
    endian: EndianType | None = None  # For integers
    field: str | None = None  # Which field to decode (for complex records)


@dataclass
class RegistryEntry:
    """Registry entry mapping type to name and decoder."""

    name: str
    decode: DecoderDef


@dataclass
class Grammar:
    """Complete grammar specification."""

    format: str
    framing: FramingDef
    record_switch: SwitchCase | None  # None if no switch
    types: dict[str, TypeDef]
    registry: dict[str, RegistryEntry]
    endian: EndianType | None = None  # Global default endianness


class ArithmeticEvaluator:
    """Safe arithmetic expression evaluator for length expressions."""

    # Allowed operators
    OPERATORS = {"+", "-", "*", "/", "(", ")"}

    def __init__(self):
        self.context: dict[str, int] = {}

    def evaluate(self, expr: str, context: dict[str, int]) -> int:
        """
        Evaluate an arithmetic expression safely.

        Args:
            expr: Expression like "nt_len_1 - 4"
            context: Field values available in current scope

        Returns:
            Integer result

        Raises:
            ValueError: If expression is invalid or uses unavailable fields
        """
        self.context = context

        # Remove whitespace
        expr = expr.replace(" ", "")

        # Tokenize
        tokens = self._tokenize(expr)

        # Parse and evaluate
        return self._eval_expr(tokens)

    def _tokenize(self, expr: str) -> list[str]:
        """Tokenize expression into operators, numbers, and field names."""
        tokens = []
        current = ""

        for char in expr:
            if char in self.OPERATORS:
                if current:
                    tokens.append(current)
                    current = ""
                tokens.append(char)
            elif char.isalnum() or char == "_":
                current += char
            else:
                raise ValueError(f"Invalid character in expression: {char}")

        if current:
            tokens.append(current)

        return tokens

    def _eval_expr(self, tokens: list[str]) -> int:
        """Evaluate expression using recursive descent parser."""
        # Convert to RPN using shunting yard, then evaluate
        output = []
        operators = []

        precedence = {"+": 1, "-": 1, "*": 2, "/": 2}

        for token in tokens:
            if token.isdigit():
                output.append(int(token))
            elif token in self.context:
                output.append(self.context[token])
            elif token in precedence:
                while (
                    operators
                    and operators[-1] != "("
                    and precedence.get(operators[-1], 0) >= precedence[token]
                ):
                    output.append(operators.pop())
                operators.append(token)
            elif token == "(":
                operators.append(token)
            elif token == ")":
                while operators and operators[-1] != "(":
                    output.append(operators.pop())
                if operators:
                    operators.pop()  # Remove (
            else:
                raise ValueError(f"Unknown token: {token}")

        while operators:
            output.append(operators.pop())

        # Evaluate RPN
        stack = []
        for item in output:
            if isinstance(item, int):
                stack.append(item)
            else:
                if len(stack) < 2:
                    raise ValueError(f"Invalid expression")
                b = stack.pop()
                a = stack.pop()
                if item == "+":
                    stack.append(a + b)
                elif item == "-":
                    stack.append(a - b)
                elif item == "*":
                    stack.append(a * b)
                elif item == "/":
                    stack.append(a // b)  # Integer division

        if len(stack) != 1:
            raise ValueError("Invalid expression")

        return stack[0]


def parse_yaml_grammar(yaml_text: str) -> Grammar:
    """Parse YAML grammar specification."""
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        raise ValueError(f"YAML parse error: {e}")

    # Parse format
    format_type = data.get("format", "record_stream")
    if format_type != "record_stream":
        raise ValueError(f"Unsupported format: {format_type}")

    # Parse global endianness (optional)
    global_endian = None
    if "endian" in data:
        global_endian = EndianType(data["endian"])

    # Parse framing
    framing_data = data.get("framing", {})
    framing = FramingDef(repeat=framing_data.get("repeat", "until_eof"))

    # Parse record switch (if present)
    record_switch = None
    record_data = data.get("record", {})
    if "switch" in record_data:
        switch_data = record_data["switch"]
        record_switch = SwitchCase(
            expr=switch_data["expr"],
            cases=switch_data.get("cases", {}),
            default=switch_data.get("default", ""),
        )

    # Parse types
    types = {}
    types_data = data.get("types", {})
    for type_name, type_spec in types_data.items():
        fields = []
        for field_spec in type_spec.get("fields", []):
            # Parse validation
            validation = None
            if "validate" in field_spec:
                val_spec = field_spec["validate"]
                if "equals" in val_spec:
                    validation = ValidationRule("equals", val_spec["equals"])
                elif "equals_field" in val_spec:
                    validation = ValidationRule("equals_field", val_spec["equals_field"])
                elif "all_bytes" in val_spec:
                    validation = ValidationRule("all_bytes", val_spec["all_bytes"])

            # Parse endian
            endian = None
            if "endian" in field_spec:
                endian = EndianType(field_spec["endian"])

            # Parse color
            field_color = None
            if "color" in field_spec:
                normalized, color_err = normalize_color(field_spec["color"])
                if color_err:
                    raise ValueError(f"Field {field_spec['name']}: {color_err}")
                field_color = normalized

            # Parse length with syntactic sugar
            # Supports three forms:
            # 1. length: 10 (static int)
            # 2. length: field_name (field reference)
            # 3. length: "expr + 1" (arithmetic expression)
            static_length = None
            length_field = None
            length_expr = None

            # Explicit forms (backward compatibility)
            if "length_field" in field_spec:
                length_field = field_spec["length_field"]
            if "length_expr" in field_spec:
                length_expr = field_spec["length_expr"]

            # Syntactic sugar: interpret "length" based on type
            if "length" in field_spec and length_field is None and length_expr is None:
                length_val = field_spec["length"]
                if isinstance(length_val, int):
                    # Form 1: static length
                    static_length = length_val
                elif isinstance(length_val, str):
                    # Determine if it's an expression or field reference
                    # If it contains operators, treat as expression
                    if any(op in length_val for op in ["+", "-", "*", "/", "(", ")"]):
                        # Form 3: arithmetic expression
                        length_expr = length_val
                    else:
                        # Form 2: field reference
                        length_field = length_val
                else:
                    raise ValueError(f"length must be int, field name, or expression string")
            elif "length" in field_spec and isinstance(field_spec["length"], int):
                # Explicit length still works
                static_length = field_spec["length"]

            field = FieldDef(
                name=field_spec["name"],
                type=field_spec["type"],
                endian=endian,
                length=static_length,
                length_field=length_field,
                length_expr=length_expr,
                validate=validation,
                encoding=field_spec.get("encoding"),
                color=field_color,
            )
            fields.append(field)

        types[type_name] = TypeDef(name=type_name, fields=fields)

    # Parse registry
    registry = {}
    registry_data = data.get("registry", {})
    for type_key, entry_spec in registry_data.items():
        decode_spec = entry_spec.get("decode", {})

        # Parse decoder
        decoder_endian = None
        if "endian" in decode_spec:
            decoder_endian = EndianType(decode_spec["endian"])

        decoder = DecoderDef(
            as_type=decode_spec.get("as", "hex"),
            encoding=decode_spec.get("encoding"),
            endian=decoder_endian,
            field=decode_spec.get("field"),
        )

        registry[type_key] = RegistryEntry(
            name=entry_spec["name"],
            decode=decoder,
        )

    return Grammar(
        format=format_type,
        framing=framing,
        record_switch=record_switch,
        types=types,
        registry=registry,
        endian=global_endian,
    )
