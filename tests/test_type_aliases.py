from __future__ import annotations

import textwrap

import pytest

from hexmap.core.schema import SchemaError, load_schema


def test_alias_fixed_length_string_expands() -> None:
    schema_text = textwrap.dedent(
        """
        types:
          leader_name: { type: string, length: 14, encoding: ascii }
        fields:
          - { name: leader, type: leader_name }
        """
    )
    schema = load_schema(schema_text)
    assert schema.fields[0].kind == "primitive"
    prim = schema.fields[0].prim
    assert prim is not None
    assert prim.type == "string"
    assert prim.length == 14
    assert prim.encoding == "ascii"


def test_call_site_override() -> None:
    schema_text = textwrap.dedent(
        """
        types:
          leader_name: { type: string, length: 14, encoding: ascii }
        fields:
          - name: leader
            type: leader_name
            encoding: utf-8
        """
    )
    schema = load_schema(schema_text)
    prim = schema.fields[0].prim
    assert prim is not None and prim.encoding == "utf-8"


def test_alias_in_array_of() -> None:
    schema_text = textwrap.dedent(
        """
        types:
          money: { type: i16 }
        fields:
          - name: balances
            type: array of money
            length: 8
        """
    )
    schema = load_schema(schema_text)
    arr = schema.fields[0]
    assert arr.kind == "array" and arr.element is not None and arr.element.prim is not None
    assert arr.element.prim.type == "i16"


def test_alias_chaining() -> None:
    schema_text = textwrap.dedent(
        """
        types:
          money_base: { type: i16 }
          money: { type: money_base }
        fields:
          - { name: balances, type: array of money, length: 2 }
        """
    )
    schema = load_schema(schema_text)
    el = schema.fields[0].element
    assert el is not None and el.prim is not None and el.prim.type == "i16"


def test_cycle_detection() -> None:
    schema_text = textwrap.dedent(
        """
        types:
          A: { type: B }
          B: { type: A }
        fields:
          - { name: x, type: A }
        """
    )
    with pytest.raises(SchemaError) as ei:
        load_schema(schema_text)
    assert any("type cycle" in e for e in ei.value.errors)


def test_unknown_alias_reference() -> None:
    schema_text = textwrap.dedent(
        """
        fields:
          - { name: x, type: UnknownAlias }
        """
    )
    with pytest.raises(SchemaError) as ei:
        load_schema(schema_text)
    assert any("unknown type reference" in e for e in ei.value.errors)


def test_bounded_string_rule_on_alias() -> None:
    schema_text = textwrap.dedent(
        """
        types:
          name_nt: { type: string, null_terminated: true }
        fields:
          - { name: x, type: name_nt }
        """
    )
    with pytest.raises(SchemaError) as ei:
        load_schema(schema_text)
    assert any("max_length" in e for e in ei.value.errors)
