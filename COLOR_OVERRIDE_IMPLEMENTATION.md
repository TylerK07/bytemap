# Color Override Implementation

## Summary

Added support for custom color overrides in the YAML grammar system. Fields can now specify colors (named or hex RGB) that will be applied in the Hex view visualization, overriding the default colors assigned based on field type groups.

## Problem

The user reported that color overrides specified in YAML were not affecting the visualization in the Chunking tab's Hex view. Investigation revealed that while the `Span` dataclass and HexView already supported `color_override`, the YAML grammar system didn't have support for parsing or propagating color information.

## Solution

Implemented full color override support by:

1. **Extended FieldDef** - Added `color` field to `FieldDef` in `yaml_grammar.py`
2. **Updated YAML parser** - Parse and validate color specifications from YAML
3. **Extended ParsedField** - Added `color` field to `ParsedField` to preserve color through parsing
4. **Updated span generation** - Modified `incremental_spans.py` to pass color to `Span` objects
5. **Added documentation** - Comprehensive documentation in `YAML_GRAMMAR_REFERENCE.md`
6. **Added tests** - 7 new tests verifying color functionality

## Implementation Details

### 1. Grammar Support (`yaml_grammar.py`)

**FieldDef dataclass:**
```python
@dataclass
class FieldDef:
    name: str
    type: str
    # ... other fields ...
    color: str | None = None  # Color override (named color or #RGB/#RRGGBB)
```

**YAML parsing:**
```python
# Parse color
field_color = None
if "color" in field_spec:
    normalized, color_err = normalize_color(field_spec["color"])
    if color_err:
        raise ValueError(f"Field {field_spec['name']}: {color_err}")
    field_color = normalized
```

### 2. Parser Support (`yaml_parser.py`)

**ParsedField dataclass:**
```python
@dataclass
class ParsedField:
    name: str
    value: Any
    raw_bytes: bytes
    offset: int
    size: int
    nested_fields: dict[str, "ParsedField"] | None = None
    color: str | None = None  # Color override from field definition
```

**Color propagation:**
All `ParsedField` constructor calls now include `color=field_def.color` to preserve the color from the grammar definition.

### 3. Span Generation (`incremental_spans.py`)

**Updated Span creation:**
```python
span = Span(
    offset=parsed_field.offset,
    length=parsed_field.size,
    path=path,
    group=group,
    color_override=parsed_field.color,  # Now includes color!
)
```

### 4. Supported Color Formats

**Named colors:**
- `red`, `green`, `blue`, `yellow`, `cyan`, `magenta`
- `purple`, `orange`, `pink`, `brown`
- `black`, `white`, `gray`/`grey`

**Hex RGB:**
- `#RGB` format (e.g., `#f80`) → expands to `#RRGGBB` (`#ff8800`)
- `#RRGGBB` format (e.g., `#3498db`)
- Case-insensitive, normalized to lowercase

**Validation:**
Uses existing `normalize_color()` function from `schema.py` to ensure colors are valid.

## Usage Examples

### Basic Named Colors

```yaml
types:
  MyRecord:
    fields:
      - { name: magic, type: bytes, length: 4, color: red }
      - { name: version, type: u16, endian: little, color: blue }
      - { name: data, type: bytes, length: 10, color: green }
```

### Hex RGB Colors

```yaml
types:
  MyRecord:
    fields:
      - { name: type_code, type: u16, endian: little, color: "#ff6b6b" }
      - { name: entity_id, type: u16, endian: little, color: "#4ecdc4" }
      - { name: payload, type: bytes, length: data_len, color: "#95e1d3" }
```

### Mixed Colors

```yaml
types:
  Header:
    fields:
      - { name: magic, type: u16, endian: little, color: purple }
      - { name: version, type: u8, color: orange }

  Record:
    fields:
      - { name: header, type: Header, color: "#f80" }  # Overrides Header field colors
      - { name: payload, type: bytes, length: 50, color: cyan }
```

## Visual Result

In the Hex view:
- Fields with `color` specified → displayed with custom color
- Fields without `color` → displayed with default type group color
  - Integer fields → default int color
  - String fields → default string color
  - Bytes fields → default bytes color

## Files Modified

### New Files
- `tests/test_yaml_color_overrides.py` - 7 comprehensive tests for color functionality

### Modified Files
- `src/hexmap/core/yaml_grammar.py`:
  - Added `color` field to `FieldDef`
  - Added color parsing and validation
  - Import `normalize_color` from schema

- `src/hexmap/core/yaml_parser.py`:
  - Added `color` field to `ParsedField`
  - Pass color from `FieldDef` to `ParsedField` in all field types

- `src/hexmap/core/incremental_spans.py`:
  - Pass `color_override=parsed_field.color` when creating Span objects

- `src/hexmap/widgets/yaml_chunking.py`:
  - Added comment about color support in DEFAULT_YAML

- `YAML_GRAMMAR_REFERENCE.md`:
  - Added "Color Overrides" section with full documentation
  - Updated table of contents

## Testing

### Test Coverage

1. **test_color_override_named_color** - Named colors parse correctly
2. **test_color_override_hex_rgb** - Hex RGB colors parse and normalize
3. **test_color_override_invalid** - Invalid colors raise errors
4. **test_color_propagates_to_parsed_field** - Color flows to ParsedField
5. **test_color_flows_to_spans** - Color flows to Span objects
6. **test_nested_type_with_color** - Nested types with colors work
7. **test_fields_without_color** - Fields without color have None

### Test Results

```
tests/test_yaml_color_overrides.py .......           [100%]
7 passed in 0.14s
```

All existing tests continue to pass:
```
tests/test_chunking.py ......                         [ 25%]
tests/test_incremental_spans.py ...........           [ 70%]
tests/test_yaml_color_overrides.py .......            [100%]
24 passed in 0.19s
```

## Architecture Flow

```
YAML Grammar File
    ↓ (parse_yaml_grammar)
FieldDef with color
    ↓ (RecordParser._parse_field)
ParsedField with color
    ↓ (IncrementalSpanManager._add_field_spans)
Span with color_override
    ↓ (HexView rendering)
Colored visualization in Hex view
```

## Benefits

1. **Visual Clarity** - Custom colors help distinguish different field types in complex formats
2. **Consistent API** - Uses same color system as existing schema format
3. **Validation** - Colors are validated at parse time with clear error messages
4. **Flexible** - Supports both named colors (convenient) and hex RGB (precise)
5. **Optional** - Fields without color continue to work with default colors

## Example Use Case: FTM File Format

```yaml
types:
  Header:
    fields:
      - { name: type_raw, type: u16, endian: little, color: "#ff6b6b" }    # Red for type
      - { name: entity_id, type: u16, endian: little, color: "#4ecdc4" }   # Teal for ID

  GenericRecord:
    fields:
      - { name: header, type: Header }
      - { name: payload_len, type: u8, color: orange }                     # Orange for length
      - { name: payload, type: bytes, length: payload_len, color: "#95e1d3" }  # Light green

  NTRecord:
    fields:
      - { name: header, type: Header }
      - { name: nt_len_1, type: u16, color: yellow }
      - { name: nt_len_2, type: u16, color: yellow }
      - { name: pad10, type: bytes, length: 10, color: gray }              # Gray for padding
      - { name: delimiter, type: u16, color: purple }
      - { name: note_text, type: bytes, length: "nt_len_1 - 4", encoding: ascii, color: cyan }
      - { name: terminator, type: u16, color: purple }
```

In the Hex view, each field type is clearly distinguished by color, making it easy to visually parse the binary structure.

## Backward Compatibility

- Fully backward compatible
- Existing YAML grammars without color specifications continue to work unchanged
- Color is optional - fields without `color` use default type group colors
- No breaking changes to any existing APIs

## Future Enhancements

Potential improvements:
- Color palettes/themes
- Per-type default colors
- Conditional colors based on field values
- Color intensity based on data patterns
