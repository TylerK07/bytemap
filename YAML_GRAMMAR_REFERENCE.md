# YAML Grammar Reference

Complete reference for the YAML-driven record parsing system in the Chunking tab.

## Table of Contents

1. [Overview](#overview)
2. [File Structure](#file-structure)
3. [Format Field](#format-field)
4. [Global Endianness](#global-endianness)
5. [Framing Section](#framing-section)
6. [Record Section](#record-section)
7. [Types Section](#types-section)
8. [Registry Section](#registry-section)
9. [Field Types](#field-types)
10. [Length Specifications](#length-specifications)
11. [Validation Rules](#validation-rules)
12. [Color Overrides](#color-overrides)
13. [Arithmetic Expressions](#arithmetic-expressions)
14. [Complete Example](#complete-example)

---

## Overview

The YAML grammar defines how to parse binary files with structured records. It supports:

- **Variable-length records** with different types
- **Type discrimination** using switch statements
- **Nested types** (records within records)
- **Dynamic length calculation** with arithmetic expressions
- **Field validation** to ensure data integrity
- **Semantic decoding** via registry mappings

---

## File Structure

A YAML grammar file has the following main sections:

```yaml
format: record_stream      # File format type
endian: little             # (Optional) Global default endianness
framing:                   # How records repeat in the file
  repeat: until_eof
record:                    # How to determine record type
  switch: ...
types:                     # Record type definitions
  TypeName: ...
registry:                  # Semantic mappings for decoded values
  "0x1234": ...
```

---

## Format Field

**Purpose:** Declares the overall file structure.

**Syntax:**
```yaml
format: record_stream
```

**Supported values:**
- `record_stream`: File contains a sequence of records (currently the only supported format)

**Example:**
```yaml
format: record_stream
```

---

## Global Endianness

**Purpose:** Sets the default byte order for all multi-byte integer fields (u16, u32).

**Syntax:**
```yaml
endian: little | big
```

**Supported values:**
- `little`: Little-endian byte order (least significant byte first)
- `big`: Big-endian byte order (most significant byte first)

**Behavior:**
- When specified at the root level, all u16 and u32 fields inherit this endianness
- Individual fields can override the global setting with their own `endian:` attribute
- If not specified, fields without an explicit `endian:` will fail to parse

**Example:**
```yaml
format: record_stream
endian: little              # Global default for all multi-byte integers

types:
  MyRecord:
    fields:
      - { name: field1, type: u16 }              # Uses little-endian (inherits global)
      - { name: field2, type: u16, endian: big } # Override: uses big-endian
      - { name: field3, type: u32 }              # Uses little-endian (inherits global)
```

**Use cases:**
- Simplifies grammar when all or most fields share the same endianness
- Reduces repetition in field definitions
- Makes it easy to adapt grammars for different file formats

---

## Framing Section

**Purpose:** Defines how records repeat in the file.

**Syntax:**
```yaml
framing:
  repeat: until_eof
```

**Fields:**
- `repeat`: How to iterate through records
  - `until_eof`: Parse records until end of file (currently the only supported option)

**Example:**
```yaml
framing:
  repeat: until_eof
```

---

## Record Section

**Purpose:** Defines how to determine which type to use for each record (type discrimination).

### Switch-based Type Discrimination

**Syntax:**
```yaml
record:
  switch:
    expr: <field_path>           # Field to discriminate on (e.g., "Header.type_raw")
    cases:
      "<value1>": TypeName1      # Map values to type names
      "<value2>": TypeName2
    default: DefaultTypeName     # Fallback type
```

**How it works:**
1. Parser reads the discriminator field (e.g., `Header.type_raw`)
2. Looks up the value in `cases`
3. Uses the corresponding type definition to parse the record
4. Falls back to `default` type if no match

**Example:**
```yaml
record:
  switch:
    expr: Header.type_raw        # Read Header.type_raw field
    cases:
      "0x544E": NTRecord         # If value is 0x544E, use NTRecord type
      "0x0065": NameRecord       # If value is 0x0065, use NameRecord type
    default: GenericRecord       # Otherwise use GenericRecord type
```

**Notes:**
- The `expr` must reference a field path (e.g., `TypeName.field_name`)
- Case values are hex strings (e.g., `"0x544E"`)
- The referenced type (e.g., `Header`) must be defined in the `types` section
- Parser will first parse enough of the record to extract the discriminator field

---

## Types Section

**Purpose:** Defines the structure of record types with their fields.

**Syntax:**
```yaml
types:
  TypeName:
    fields:
      - { name: field1, type: u16, endian: little }
      - { name: field2, type: bytes, length: 10 }
      # ... more fields
```

### Field Definition

Each field has these properties:

| Property | Required | Description | Values |
|----------|----------|-------------|--------|
| `name` | Yes | Field name | Any string |
| `type` | Yes | Data type | `u8`, `u16`, `u32`, `bytes`, or custom type name |
| `endian` | For u16/u32 | Byte order | `little`, `big` |
| `length` | For bytes | Fixed length in bytes | Integer |
| `length_field` | For bytes | Reference to length field | Field name |
| `length_expr` | For bytes | Arithmetic expression for length | Expression string |
| `encoding` | For bytes | Text encoding | `ascii`, `utf-8`, etc. |
| `validate` | Optional | Validation rule | See [Validation Rules](#validation-rules) |

**Example:**
```yaml
types:
  Header:
    fields:
      - { name: type_raw, type: u16, endian: little }
      - { name: entity_id, type: u16, endian: little }

  GenericRecord:
    fields:
      - { name: header, type: Header }           # Nested type
      - { name: payload_len, type: u8 }
      - { name: payload, type: bytes, length_field: payload_len }

  NTRecord:
    fields:
      - { name: header, type: Header }
      - { name: nt_len_1, type: u16, endian: little }
      - { name: nt_len_2, type: u16, endian: little }
      - { name: pad10, type: bytes, length: 10 }
      - { name: note_text, type: bytes, length_expr: "nt_len_1 - 4", encoding: ascii }
```

---

## Registry Section

**Purpose:** Maps record types to semantic names and defines how to decode their values.

**Syntax:**
```yaml
registry:
  "<type_value>":
    name: semantic_name
    decode:
      as: decoder_type
      # ... decoder-specific options
```

### Registry Entry

| Property | Required | Description |
|----------|----------|-------------|
| `name` | Yes | Human-readable name for this record type |
| `decode.as` | Yes | Decoder type (see below) |
| `decode.encoding` | For string | Text encoding (e.g., `ascii`, `utf-8`) |
| `decode.endian` | For u16/u32 | Byte order (`little`, `big`) |
| `decode.field` | Optional | Specific field to decode (for complex records) |

### Decoder Types

| Decoder | Description | Options | Output |
|---------|-------------|---------|--------|
| `string` | Decode as text | `encoding` | Text string |
| `u16` | Decode as 16-bit unsigned int | `endian` | Decimal number |
| `u32` | Decode as 32-bit unsigned int | `endian` | Decimal number |
| `hex` | Decode as hexadecimal bytes | None | Hex string |
| `ftm_packed_date` | Decode FTM packed date format | None | `YYYY-MM-DD` |

**Example:**
```yaml
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

  "0x0101":
    name: birth_year
    decode:
      as: u16
      endian: little

  "0x0200":
    name: birth_date
    decode:
      as: ftm_packed_date

  "0x544E":
    name: note_text
    decode:
      as: string
      field: note_text    # Decode specific field for complex records
      encoding: ascii
```

**Notes:**
- Registry keys must match the hex format used in type discrimination (e.g., `"0x544E"`)
- Use `field` parameter to specify which field to decode in complex records
- FTM packed date format: 4 bytes encoding day/month/year with bit packing

---

## Field Types

### Primitive Types

#### u8 - Unsigned 8-bit Integer

**Size:** 1 byte
**Range:** 0 to 255
**Endianness:** N/A (single byte)

```yaml
- { name: length, type: u8 }
```

#### u16 - Unsigned 16-bit Integer

**Size:** 2 bytes
**Range:** 0 to 65,535
**Endianness:** Required (`little` or `big`)

```yaml
- { name: type_code, type: u16, endian: little }
```

**Example values:**
- Bytes `4E 54` with `endian: little` → 0x544E (21582)
- Bytes `4E 54` with `endian: big` → 0x4E54 (20052)

#### u32 - Unsigned 32-bit Integer

**Size:** 4 bytes
**Range:** 0 to 4,294,967,295
**Endianness:** Required (`little` or `big`)

```yaml
- { name: timestamp, type: u32, endian: little }
```

#### bytes - Raw Bytes

**Size:** Variable (see [Length Specifications](#length-specifications))
**Encoding:** Optional (for text data)

```yaml
- { name: data, type: bytes, length: 16 }
- { name: name, type: bytes, length: 50, encoding: ascii }
```

### Custom Types (Nested Records)

You can reference other type definitions to create nested structures:

```yaml
types:
  Header:
    fields:
      - { name: magic, type: u16, endian: little }
      - { name: version, type: u8 }

  Record:
    fields:
      - { name: header, type: Header }      # Nested type
      - { name: payload_len, type: u8 }
      - { name: payload, type: bytes, length_field: payload_len }
```

**How it works:**
- Parser recursively parses the nested type
- Nested fields are accessible via dot notation (e.g., `Record.header.magic`)
- Useful for discriminating record types via header fields

---

## Length Specifications

For `bytes` fields, you must specify the length using one of three methods:

### 1. Fixed Length

**Use when:** Length is constant for this field

```yaml
- { name: magic, type: bytes, length: 4 }
- { name: padding, type: bytes, length: 10 }
```

**Example:** A 4-byte magic number at the start of each record

---

### 2. Length Field Reference

**Use when:** Another field contains the length value

```yaml
- { name: payload_len, type: u8 }
- { name: payload, type: bytes, length_field: payload_len }
```

**How it works:**
1. Parser reads `payload_len` field (e.g., value is 42)
2. Parser reads 42 bytes for `payload` field

**Example:**
```
Bytes: 05 48 65 6C 6C 6F
       ↑  ↑-----------↑
       |  payload (5 bytes: "Hello")
       payload_len (5)
```

---

### 3. Length Expression (Arithmetic)

**Use when:** Length requires calculation from other fields

```yaml
- { name: total_len, type: u16, endian: little }
- { name: header_len, type: u8 }
- { name: body, type: bytes, length_expr: "total_len - header_len - 4" }
```

**Supported operators:** `+`, `-`, `*`, `/`, `(`, `)`

**Examples:**
```yaml
# Subtract delimiter length
length_expr: "nt_len_1 - 4"

# Calculate remaining space
length_expr: "total_size - header_size - footer_size"

# Multiply for array size
length_expr: "num_items * 8"

# Complex expression
length_expr: "(total_len - 10) / 2"
```

**Rules:**
- Expression must evaluate to a positive integer
- Referenced fields must be parsed before the bytes field
- See [Arithmetic Expressions](#arithmetic-expressions) for details

---

## Validation Rules

Add validation to fields to ensure data integrity. Parser will fail the record if validation fails.

### equals - Value Must Match Constant

**Use when:** Field must have a specific value (magic numbers, delimiters)

```yaml
- { name: delimiter, type: u16, endian: little, validate: { equals: 0x001C } }
- { name: magic, type: u8, validate: { equals: 0xFF } }
```

**Example:**
```
Record with delimiter field:
  Bytes: 1C 00
  Parsed: 0x001C
  Validation: equals 0x001C → PASS ✓

Record with wrong delimiter:
  Bytes: 1D 00
  Parsed: 0x001D
  Validation: equals 0x001C → FAIL ✗ (record rejected)
```

---

### equals_field - Value Must Match Another Field

**Use when:** Two fields must have the same value (checksums, repeated values)

```yaml
- { name: len1, type: u16, endian: little }
- { name: len2, type: u16, endian: little, validate: { equals_field: len1 } }
```

**Example:**
```
Record with matching lengths:
  len1: 0x002C (44)
  len2: 0x002C (44)
  Validation: len2 equals_field len1 → PASS ✓

Record with mismatched lengths:
  len1: 0x002C (44)
  len2: 0x0030 (48)
  Validation: len2 equals_field len1 → FAIL ✗
```

**Note:** This validation is often too strict for real-world data. Use sparingly.

---

### all_bytes - All Bytes Must Equal Value

**Use when:** Padding or reserved fields must be all zeros (or other value)

```yaml
- { name: padding, type: bytes, length: 10, validate: { all_bytes: 0x00 } }
- { name: reserved, type: bytes, length: 4, validate: { all_bytes: 0xFF } }
```

**Example:**
```
Valid padding (all zeros):
  Bytes: 00 00 00 00 00 00 00 00 00 00
  Validation: all_bytes 0x00 → PASS ✓

Invalid padding (not all zeros):
  Bytes: 00 00 01 00 00 00 00 00 00 00
  Validation: all_bytes 0x00 → FAIL ✗
```

---

## Color Overrides

Fields can specify custom colors for visualization in the Hex view. This overrides the default color assigned based on the field's type group (int, string, bytes, etc.).

### Supported Color Formats

#### Named Colors
Use predefined color names:

```yaml
- { name: magic, type: bytes, length: 4, color: red }
- { name: version, type: u16, endian: little, color: blue }
- { name: name, type: bytes, length: 50, encoding: ascii, color: green }
```

**Available named colors:**
- `black`, `white`, `gray`/`grey`
- `red`, `green`, `blue`
- `yellow`, `cyan`, `magenta`
- `purple`, `orange`, `pink`, `brown`

#### Hex RGB Colors
Use 3-digit or 6-digit hex format (with `#` prefix):

```yaml
- { name: header, type: Header, color: "#f80" }       # #RGB format (expands to #ff8800)
- { name: timestamp, type: u32, endian: little, color: "#3498db" }  # #RRGGBB format
- { name: payload, type: bytes, length: data_len, color: "#2ecc71" }
```

**Format rules:**
- Must start with `#`
- 3-digit: `#RGB` → expands to `#RRGGBB` (e.g., `#f80` → `#ff8800`)
- 6-digit: `#RRGGBB` → used as-is
- Case-insensitive (normalized to lowercase internally)

### Nested Types and Color Inheritance

When a field references a nested type, the color applies to all fields within that type:

```yaml
types:
  Header:
    fields:
      - { name: magic, type: u16, endian: little }
      - { name: version, type: u16, endian: little }

  Record:
    fields:
      - { name: header, type: Header, color: purple }  # All Header fields colored purple
      - { name: payload_len, type: u8 }
      - { name: payload, type: bytes, length: payload_len, color: cyan }
```

### Complete Example with Colors

```yaml
types:
  FTMRecord:
    fields:
      - { name: type_raw, type: u16, endian: little, color: "#ff6b6b" }     # Red for type
      - { name: entity_id, type: u16, endian: little, color: "#4ecdc4" }    # Teal for ID
      - { name: payload_len, type: u8, color: orange }                      # Orange for length
      - { name: payload, type: bytes, length: payload_len, color: "#95e1d3" }  # Light green
```

### Visual Result

In the Hex view, each field will be highlighted with its specified color, making it easy to visually distinguish different parts of the record structure.

**Default colors (without override):**
- Integer fields (`u8`, `u16`, `u32`): Default int color
- String fields (bytes with encoding): Default string color
- Raw bytes: Default bytes color

**With color override:** Custom color takes precedence over default group color.

---

## Arithmetic Expressions

Used in `length_expr` to calculate dynamic lengths.

### Syntax

```
expression ::= term (('+' | '-') term)*
term       ::= factor (('*' | '/') factor)*
factor     ::= number | field_name | '(' expression ')'
```

### Supported Operators

| Operator | Description | Example | Result |
|----------|-------------|---------|--------|
| `+` | Addition | `10 + 5` | 15 |
| `-` | Subtraction | `total - 4` | Varies |
| `*` | Multiplication | `count * 8` | Varies |
| `/` | Integer division | `size / 2` | Integer result |
| `( )` | Grouping | `(a + b) * 2` | Varies |

### Examples

#### Simple Subtraction
```yaml
# String length excludes 4-byte delimiter
- { name: total_len, type: u16, endian: little }
- { name: string, type: bytes, length_expr: "total_len - 4" }
```

#### Multiple Operations
```yaml
# Calculate body size after header and footer
- { name: total, type: u16, endian: little }
- { name: header_size, type: u8 }
- { name: body, type: bytes, length_expr: "total - header_size - 2" }
```

#### Parentheses for Order of Operations
```yaml
# Calculate half of remaining space
- { name: total, type: u16, endian: little }
- { name: data, type: bytes, length_expr: "(total - 10) / 2" }
```

#### Array Size Calculation
```yaml
# Each item is 12 bytes
- { name: num_items, type: u8 }
- { name: items, type: bytes, length_expr: "num_items * 12" }
```

### Rules and Constraints

1. **Field References:** Referenced fields must be parsed before the expression is evaluated
2. **Integer Results:** Division is integer division (truncates)
3. **Non-negative:** Result must be ≥ 0
4. **Safe Evaluation:** No variable assignment or function calls allowed
5. **Whitespace:** Spaces are optional but improve readability

### Error Handling

If an expression fails to evaluate:
- **Missing field:** Field not yet parsed or doesn't exist
- **Division by zero:** Denominator is zero
- **Invalid result:** Result is negative or not an integer
- **Syntax error:** Invalid expression syntax

**Result:** Record parsing fails with error message.

---

## Complete Example

Here's a complete YAML grammar for a file format with multiple record types:

```yaml
format: record_stream
endian: little                # Global default for all multi-byte integers

framing:
  repeat: until_eof

record:
  switch:
    expr: Header.type_raw
    cases:
      "0x544E": NTRecord      # Note record (special format)
      "0x0065": NameRecord    # Name record
      "0x0200": DateRecord    # Date record
    default: GenericRecord    # Fallback for unknown types

types:
  # Common header used by all records
  Header:
    fields:
      - { name: type_raw, type: u16 }    # Inherits little-endian
      - { name: entity_id, type: u16 }   # Inherits little-endian

  # Generic record for most types
  GenericRecord:
    fields:
      - { name: header, type: Header }
      - { name: payload_len, type: u8 }
      - { name: payload, type: bytes, length: payload_len }  # Using syntactic sugar

  # Specialized record for names
  NameRecord:
    fields:
      - { name: header, type: Header }
      - { name: name_len, type: u8 }
      - { name: name_text, type: bytes, length: name_len, encoding: ascii }

  # Specialized record for dates
  DateRecord:
    fields:
      - { name: header, type: Header }
      - { name: date_data, type: bytes, length: 4 }

  # Note record with complex structure
  NTRecord:
    fields:
      - { name: header, type: Header }
      - { name: nt_len_1, type: u16 }      # Inherits little-endian
      - { name: nt_len_2, type: u16 }      # Inherits little-endian
      - { name: pad10, type: bytes, length: 10 }
      - { name: delimiter, type: u16 }     # Inherits little-endian
      - { name: note_text, type: bytes, length: "nt_len_1 - 4", encoding: ascii }  # Expression
      - { name: terminator, type: u16 }    # Inherits little-endian

registry:
  "0x0000":
    name: root_record
    decode:
      as: hex

  "0x0065":
    name: person_name
    decode:
      as: string
      field: name_text
      encoding: ascii

  "0x0101":
    name: birth_year
    decode:
      as: u16           # Inherits little-endian from global setting

  "0x0200":
    name: birth_date
    decode:
      as: ftm_packed_date

  "0x0201":
    name: death_date
    decode:
      as: ftm_packed_date

  "0x544E":
    name: note_text
    decode:
      as: string
      field: note_text
      encoding: ascii
```

### How This Works

1. **Parser starts at offset 0**
2. **Reads Header type** (e.g., `Header.type_raw = 0x0065`)
3. **Switch determines type:** 0x0065 → NameRecord
4. **Parses NameRecord fields:**
   - `header`: Already parsed (Header with type_raw=0x0065, entity_id=123)
   - `name_len`: Reads 1 byte (e.g., 10)
   - `name_text`: Reads 10 bytes, decodes as ASCII
5. **Registry lookup:** 0x0065 → "person_name"
6. **Decodes value:** Extracts `name_text` field, returns as string
7. **Displays in table:**
   - Offset: 00000000
   - Type: 0x0065
   - Name: person_name
   - Decoded: "John Smith"
8. **Moves to next record** at offset = current_offset + record_size

---

## Tips and Best Practices

### 1. Start Simple

Begin with a basic structure and add complexity incrementally:

```yaml
# Step 1: Parse as generic records
format: record_stream
endian: little
types:
  GenericRecord:
    fields:
      - { name: type, type: u16 }
      - { name: length, type: u8 }
      - { name: data, type: bytes, length: length }

# Step 2: Add type discrimination
record:
  switch:
    expr: Header.type
    default: GenericRecord

# Step 3: Add specialized types as needed
```

### 2. Use Global Endianness

Set a global default endianness to simplify your grammar:

```yaml
# Without global endian (repetitive)
format: record_stream
types:
  Header:
    fields:
      - { name: type_raw, type: u16, endian: little }
      - { name: entity_id, type: u16, endian: little }
  Record:
    fields:
      - { name: length, type: u16, endian: little }
      - { name: value, type: u32, endian: little }

# With global endian (cleaner)
format: record_stream
endian: little
types:
  Header:
    fields:
      - { name: type_raw, type: u16 }
      - { name: entity_id, type: u16 }
  Record:
    fields:
      - { name: length, type: u16 }
      - { name: value, type: u32 }
```

This makes your grammar more readable and easier to maintain.

### 3. Avoid Over-Validation

Validation rules can cause parsing to stop if data doesn't match exactly:

```yaml
# Too strict (may fail on valid data)
- { name: len2, type: u16, validate: { equals_field: len1 } }

# Better (allow minor variations)
- { name: len2, type: u16 }
```

### 4. Use Meaningful Names

Choose descriptive names for types and fields:

```yaml
# Poor
type1, field1, data

# Good
PersonRecord, birth_date, person_name
```

### 5. Document Assumptions

Add comments to explain non-obvious aspects:

```yaml
types:
  NTRecord:
    fields:
      # Length includes both delimiter (2 bytes) and terminator (2 bytes)
      - { name: total_len, type: u16, endian: little }
      - { name: text, type: bytes, length_expr: "total_len - 4" }
```

### 5. Test Incrementally

After each change:
1. Click Parse button
2. Check record count matches expected
3. Verify Decoded column shows correct values
4. Inspect a few records in the Inspector panel

---

## Troubleshooting

### Parser Stops Early

**Symptom:** Only parses first few records, then stops

**Causes:**
- Validation rule failed (check for `equals_field` or `all_bytes`)
- Length calculation error (expression produces negative or too-large value)
- Missing length specification for bytes field

**Solution:**
- Remove or relax validation rules
- Check arithmetic expressions for correctness
- Verify all bytes fields have length/length_field/length_expr

### Type Not Matching

**Symptom:** All records show as GenericRecord

**Causes:**
- Switch expression references wrong field
- Case values don't match actual data (check endianness!)
- Type name spelling mismatch

**Solution:**
- Verify switch `expr` path (e.g., `Header.type_raw`)
- Check hex values match (remember: little-endian reverses bytes)
- Ensure case type names match `types` section exactly

### Registry Not Decoding

**Symptom:** Name and Decoded columns show "—"

**Causes:**
- Registry key doesn't match type value format
- Type value formatted inconsistently (0x0065 vs 0x6500)
- Field reference in decoder doesn't exist

**Solution:**
- Format registry keys as hex: `"0x0065"`
- Ensure type_raw format matches registry keys
- Verify `field` parameter references existing field

### Arithmetic Expression Fails

**Symptom:** Parse error mentioning field name

**Causes:**
- Referenced field not yet parsed
- Field name misspelled
- Expression syntax error

**Solution:**
- Ensure referenced fields come before the expression
- Check field names match exactly (case-sensitive)
- Test expression with known values

---

## Reference: FTM Packed Date Format

**Size:** 4 bytes
**Encoding:** Custom bit-packed format

### Structure

```
Byte 0: (day << 3) | flags
Byte 1: (month << 1) | must_be_zero
Byte 2: year_low (u8)
Byte 3: year_high (u8)
```

### Decoding Algorithm

```python
b0, b1, year_lo, year_hi = bytes[0:4]

day = b0 >> 3              # Extract day (bits 3-7)
flags = b0 & 0x07          # Extract flags (bits 0-2)
month = b1 >> 1            # Extract month (bits 1-7)
year = year_lo | (year_hi << 8)  # Combine year bytes (little-endian)

# Validate
if b1 & 0x01 != 0:
    # Invalid: low bit of month byte must be 0
    raise ValueError

if not (1 <= month <= 12 and 1 <= day <= 31):
    # Invalid: out of range
    raise ValueError

# Format as YYYY-MM-DD
date_string = f"{year:04d}-{month:02d}-{day:02d}"
```

### Example

```
Bytes: 4A 06 2A 07
       ↓  ↓  ↓  ↓
       |  |  |  year_high = 0x07
       |  |  year_low = 0x2A
       |  month_byte = 0x06
       day_byte = 0x4A

day = 0x4A >> 3 = 9
flags = 0x4A & 0x07 = 2
month = 0x06 >> 1 = 3
year = 0x2A | (0x07 << 8) = 0x072A = 1834

Result: 1834-03-09
```

---

## Related Files

- **Grammar Parser:** `src/hexmap/core/yaml_grammar.py`
- **Record Parser:** `src/hexmap/core/yaml_parser.py`
- **UI Widget:** `src/hexmap/widgets/yaml_chunking.py`
- **Example Grammar:** Default YAML in yaml_chunking.py
- **Test File:** `tests/test_chunking.py`

---

## Version History

- **v1.0** (2025-12-30): Initial YAML grammar system
  - Basic types (u8, u16, u32, bytes)
  - Switch-based discrimination
  - Length expressions with arithmetic
  - Validation rules
  - Registry with decoders
  - FTM packed date support
