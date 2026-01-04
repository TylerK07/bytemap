# ByteMap Architecture

Comprehensive documentation of the ByteMap application architecture, including frontend stack, parsing system, and YAML grammar framework.

## Table of Contents

1. [System Overview](#system-overview)
2. [Frontend Stack](#frontend-stack)
3. [Core Architecture](#core-architecture)
4. [Parsing System](#parsing-system)
5. [YAML Grammar System](#yaml-grammar-system)
6. [Data Flow](#data-flow)
7. [Key Design Patterns](#key-design-patterns)

---

## System Overview

ByteMap is a Terminal User Interface (TUI) application for exploring and analyzing binary files. It provides multiple views for understanding binary data:

- **Explore Tab**: Raw hex view with schema-based field highlighting
- **Chunking Tab**: YAML-driven record parsing with hex/raw/types views
- **Compare Tab**: Diff two binary files
- **Search Tab**: Search for patterns in binary data

**Technology Stack:**
- Language: Python 3.12+
- UI Framework: Textual (TUI framework)
- Data Structures: dataclasses, NumPy arrays
- I/O: Custom paged reader for memory-efficient file access

---

## Frontend Stack

### Textual TUI Framework

ByteMap is built on [Textual](https://textual.textualize.io/), a Python framework for building sophisticated terminal user interfaces.

#### Key Textual Concepts

**App (`HexmapApp`)**
- Entry point: `src/hexmap/app.py:101`
- Manages global state, file reader, schema
- Coordinates between tabs and widgets
- Handles keyboard shortcuts and navigation

**Widgets**
- Reusable UI components (buttons, tables, text areas, etc.)
- Custom widgets extend Textual base classes
- Each major view is a custom widget

**Screens**
- Full-screen views that can be pushed/popped on a stack
- Used for modals, dialogs, help screens

**CSS Styling**
- Textual CSS for layout and appearance: `src/hexmap/ui/theme.tcss`
- Supports flexbox-like layouts, colors, borders, dimensions

**Reactive Properties**
- Properties that trigger UI updates when changed
- Example: `reactive(False)` for boolean flags

**Message Passing**
- Event-driven architecture
- Widgets emit messages, handlers respond
- Example: `@on(Button.Pressed)` decorator

#### Main UI Components

**Main Application** (`src/hexmap/app.py`)
```python
class HexmapApp(App):
    TITLE = "bytemap"
    CSS_PATH = "ui/theme.tcss"

    def compose(self) -> ComposeResult:
        # Build UI hierarchy
        yield Header()
        yield TabbedContent(...)
        yield Footer()
```

**Tab System**
- Uses `TabbedContent` for tab navigation
- Each tab is a distinct widget with its own logic
- Tabs:
  - Explore: `ExploreWidget`
  - Chunking: `YAMLChunkingWidget`
  - Compare: `CompareWidget`
  - Search: `SearchWidget`

**Custom Widgets**

1. **HexView** (`src/hexmap/widgets/hex_view.py`)
   - Core hex viewer with byte grid
   - Supports span-based coloring
   - Viewport-based rendering (only renders visible rows)
   - Handles scrolling, selection, keyboard navigation

2. **YAMLChunkingWidget** (`src/hexmap/widgets/yaml_chunking.py`)
   - 3-column layout: YAML editor | DataTable/HexView | Inspector
   - Manages YAML grammar and record parsing
   - Switches between Hex/Raw/Types views
   - Viewport-based span generation for performance

3. **DataTable** (Textual built-in)
   - Used for Raw and Types views
   - Virtual scrolling for large datasets
   - Sortable columns
   - Row selection

4. **TextArea** (Textual built-in)
   - YAML editor with syntax highlighting
   - Used for schema editing

### Styling System

**CSS File** (`src/hexmap/ui/theme.tcss`)
- Global styles for all widgets
- Layout rules (flex, grid)
- Color scheme
- Widget-specific overrides

**Example:**
```css
#record-hex-view {
    height: 1fr;
    width: 100%;
}

YAMLChunkingWidget {
    layout: horizontal;
}
```

### Event Handling

**Keyboard Shortcuts**
- Defined in `HexmapApp.BINDINGS`
- Tab navigation: Ctrl+1-4
- Actions: Ctrl+O (open), Ctrl+S (save), etc.

**Message Handlers**
```python
@on(DataTable.HeaderSelected, "#record-table")
def header_selected(self, event: DataTable.HeaderSelected) -> None:
    # Handle column sort
    ...
```

**Timers**
- Used for periodic updates (e.g., viewport monitoring)
- `self.set_interval(0.1, callback)` - calls callback every 100ms

---

## Core Architecture

### Module Structure

```
src/hexmap/
├── app.py                 # Main application entry point
├── core/                  # Core parsing and data structures
│   ├── io.py             # PagedReader for file I/O
│   ├── schema.py         # Schema parsing (old format)
│   ├── spans.py          # Span system for field highlighting
│   ├── yaml_grammar.py   # YAML grammar parsing
│   ├── yaml_parser.py    # Binary parsing using YAML grammars
│   └── incremental_spans.py  # Viewport-based span generation
├── widgets/              # UI widgets
│   ├── hex_view.py       # Hex viewer widget
│   ├── yaml_chunking.py  # Chunking tab widget
│   ├── inspector.py      # Field inspector
│   └── ...
└── ui/
    └── theme.tcss        # Textual CSS styles
```

### Key Data Structures

**Span** (`src/hexmap/core/spans.py:7`)
```python
@dataclass(frozen=True)
class Span:
    offset: int                    # File byte offset
    length: int                    # Field size in bytes
    path: str                      # Field path (e.g., "Record.header.magic")
    group: str                     # Type group (int|string|bytes|float|unknown)
    effective_endian: str | None   # Byte order
    endian_source: str | None      # Where endianness came from
    color_override: str | None     # Custom color
```

**SpanIndex** (`src/hexmap/core/spans.py:22`)
- Fast lookup structure for spans by offset
- Uses binary search on sorted span list
- `find(offset) -> Span | None`

**ParsedRecord** (`src/hexmap/core/yaml_parser.py:32`)
```python
@dataclass
class ParsedRecord:
    offset: int                           # Record start in file
    size: int                             # Record size in bytes
    type_name: str                        # Type from grammar
    fields: dict[str, ParsedField]        # Parsed fields
    type_discriminator: str | None        # Actual type value
    error: str | None                     # Parse error if any
```

**ParsedField** (`src/hexmap/core/yaml_parser.py:19`)
```python
@dataclass
class ParsedField:
    name: str                             # Field name
    value: Any                            # Parsed value (int, bytes, str, dict)
    raw_bytes: bytes                      # Raw byte data
    offset: int                           # Field start in file
    size: int                             # Field size
    nested_fields: dict[str, ParsedField] | None  # Nested records
    color: str | None                     # Color override
```

### Memory-Efficient I/O

**PagedReader** (`src/hexmap/core/io.py`)
- Reads file in chunks (pages) instead of loading entirely
- Caches recently accessed pages
- Supports random access
- Used by both HexView and parsers

```python
class PagedReader:
    def __init__(self, path: str, page_size: int = 65536):
        self.size = os.path.getsize(path)
        # Reads data in 64KB chunks

    def read(self, offset: int, length: int) -> bytes:
        # Returns bytes at offset, transparently handling paging
```

---

## Parsing System

### Two Parsing Approaches

ByteMap supports two different parsing systems:

1. **Schema-based parsing** (`core/schema.py`) - Original system
   - Used by Explore tab
   - Declarative field definitions
   - Support for primitives, arrays, structs

2. **YAML Grammar parsing** (`core/yaml_grammar.py` + `yaml_parser.py`) - New system
   - Used by Chunking tab
   - Record-stream format (sequence of typed records)
   - Type discrimination via switch statements
   - Dynamic length calculations

### YAML Grammar Parser Architecture

**Location:** `src/hexmap/core/yaml_parser.py`

#### RecordParser Class

Main parser that processes binary files using YAML grammars:

```python
class RecordParser:
    def __init__(self, grammar: Grammar):
        self.grammar = grammar
        self.evaluator = ArithmeticEvaluator()

    def parse_file(self, reader: PagedReader) -> tuple[list[ParsedRecord], list[str]]:
        """Parse entire file, returning records and errors"""

    def parse_record(self, reader: PagedReader, offset: int) -> ParsedRecord:
        """Parse single record at offset"""
```

#### Parsing Flow

1. **Type Determination** (`_determine_record_type`)
   - Uses record switch to discriminate record types
   - Parses header to get discriminator field
   - Looks up type in switch cases
   - Returns `TypeDef` for parsing

2. **Record Parsing** (`_parse_type`)
   - Iterates through fields in type definition
   - Parses each field sequentially
   - Maintains context for dynamic length calculations
   - Returns `ParsedRecord` with all fields

3. **Field Parsing** (`_parse_field`)
   - Checks if custom type (nested record) or primitive
   - For primitives: reads bytes and decodes based on type
   - For nested: recursively parses nested type
   - Validates field values if validation rules present
   - Returns `ParsedField` with value and metadata

4. **Length Resolution** (`_determine_bytes_length`)
   - Handles three forms:
     - Static: `length: 10`
     - Field reference: `length: payload_len`
     - Expression: `length: "nt_len_1 - 4"`
   - Uses `ArithmeticEvaluator` for expressions

#### Primitive Type Handling

**u8 - Unsigned 8-bit Integer**
```python
data = reader.read(offset, 1)
value = data[0]  # Single byte, no endianness
```

**u16/u32 - Multi-byte Integers**
```python
size = 2 if prim_type == PrimitiveType.U16 else 4
data = reader.read(offset, size)
# Respect field-level or global endianness
endian = "little" if field_def.endian == EndianType.LITTLE else "big"
value = int.from_bytes(data, endian, signed=False)
```

**bytes - Variable-length Data**
```python
length = self._determine_bytes_length(field_def, context)
data = reader.read(offset, length)
# Optionally decode as string
if field_def.encoding:
    value = data.decode(field_def.encoding, errors="replace")
```

#### Nested Type Handling

When a field references another type:
```python
if field_def.type in self.grammar.types:
    nested_type = self.grammar.types[field_def.type]
    nested_record = self._parse_type(reader, offset, nested_type)
    # Fields accessible via nested_record.fields
```

Fields from nested types are added to parsing context for use in later length expressions.

---

## YAML Grammar System

### Overview

The YAML grammar system defines how to parse binary files with structured records. It's designed for formats where:
- File consists of a sequence of records
- Records may have different types
- Type is determined by a discriminator field
- Fields have dynamic lengths based on other fields

### Grammar Definition (`src/hexmap/core/yaml_grammar.py`)

#### Core Data Structures

**Grammar** - Top-level specification
```python
@dataclass
class Grammar:
    format: str                      # "record_stream"
    framing: FramingDef              # How records repeat
    record_switch: SwitchCase | None # Type discrimination
    types: dict[str, TypeDef]        # Type definitions
    registry: dict[str, RegistryEntry]  # Semantic mappings
    endian: EndianType | None        # Global default endianness
```

**TypeDef** - Record structure
```python
@dataclass
class TypeDef:
    name: str
    fields: list[FieldDef]
```

**FieldDef** - Individual field specification
```python
@dataclass
class FieldDef:
    name: str
    type: str                    # Primitive or custom type
    endian: EndianType | None    # Byte order override
    length: int | None           # Static length
    length_field: str | None     # Reference to length field
    length_expr: str | None      # Arithmetic expression
    validate: ValidationRule | None  # Validation constraint
    encoding: str | None         # Text encoding (ascii, utf-8, etc.)
    color: str | None            # Visualization color override
```

**SwitchCase** - Type discrimination
```python
@dataclass
class SwitchCase:
    expr: str                    # Field path (e.g., "Header.type_raw")
    cases: dict[str, str]        # Discriminator value -> type name
    default: str                 # Default type if no match
```

#### Grammar Parsing (`parse_yaml_grammar`)

**Location:** `src/hexmap/core/yaml_grammar.py:219`

**Input:** YAML text string
**Output:** `Grammar` object
**Process:**

1. **YAML Parsing**
   ```python
   data = yaml.safe_load(yaml_text)
   ```

2. **Format Validation**
   - Verify `format: record_stream`

3. **Global Endianness** (optional)
   ```python
   if "endian" in data:
       global_endian = EndianType(data["endian"])
   ```

4. **Framing Parsing**
   - Extract `repeat: until_eof`

5. **Record Switch Parsing** (optional)
   ```python
   if "switch" in record_data:
       record_switch = SwitchCase(
           expr=switch_data["expr"],
           cases=switch_data.get("cases", {}),
           default=switch_data.get("default", "")
       )
   ```

6. **Type Definitions**
   - For each type in `types:` section:
     - Parse field list
     - Handle validation rules
     - Handle endianness overrides
     - Parse color specifications
     - Parse length specifications (syntactic sugar)
     - Create `FieldDef` objects

7. **Registry Parsing**
   - Map type codes to semantic names
   - Parse decoder specifications

**Syntactic Sugar:**

Length field supports three forms:
```yaml
# Form 1: Static integer
- { name: data, type: bytes, length: 10 }

# Form 2: Field reference
- { name: data, type: bytes, length: payload_len }

# Form 3: Arithmetic expression
- { name: text, type: bytes, length: "nt_len_1 - 4" }
```

The parser automatically determines which form based on type.

#### Arithmetic Expression Evaluator

**Location:** `src/hexmap/core/yaml_grammar.py:105`

Safely evaluates arithmetic expressions for dynamic length calculation:

**Supported Operators:** `+`, `-`, `*`, `/`, `(`, `)`

**Process:**
1. Tokenize expression
2. Convert to Reverse Polish Notation (RPN) using Shunting Yard algorithm
3. Evaluate RPN with context values

**Example:**
```python
evaluator = ArithmeticEvaluator()
result = evaluator.evaluate("nt_len_1 - 4", {"nt_len_1": 50})
# Returns: 46
```

**Security:** No `eval()` - uses explicit parsing and validation.

### How YAML is Loaded and Validated

#### Loading Flow

1. **User Edits YAML** (`YAMLChunkingWidget`)
   - TextArea with syntax highlighting
   - Default YAML provided for FTM format

2. **Parse Button Pressed**
   ```python
   @on(Button.Pressed, "#parse-btn")
   def parse_yaml(self, event: Button.Pressed) -> None:
       yaml_text = self.query_one("#yaml-editor", TextArea).text
       # Parse and validate...
   ```

3. **YAML Parsing**
   ```python
   from hexmap.core.yaml_grammar import parse_yaml_grammar

   try:
       grammar = parse_yaml_grammar(yaml_text)
   except ValueError as e:
       # Show error to user
       self.notify(str(e), severity="error")
       return
   ```

4. **Grammar Validation**
   - `parse_yaml_grammar` validates:
     - YAML syntax (via `yaml.safe_load`)
     - Required sections present
     - Valid type references
     - Valid endianness values
     - Valid color specifications
     - Expression syntax

5. **Binary Parsing**
   ```python
   parser = RecordParser(grammar)
   records, errors = parser.parse_file(reader)
   ```

6. **Error Handling**
   - Grammar errors: shown immediately, parsing not attempted
   - Parse errors: shown after parsing, indicates data/grammar mismatch

#### Validation Steps

**Grammar Validation** (at parse time):

1. **YAML Syntax**
   - `yaml.safe_load()` raises `yaml.YAMLError` for syntax errors

2. **Format Field**
   ```python
   if format_type != "record_stream":
       raise ValueError(f"Unsupported format: {format_type}")
   ```

3. **Endianness**
   ```python
   global_endian = EndianType(data["endian"])  # Raises ValueError if invalid
   ```

4. **Color Specifications**
   ```python
   normalized, color_err = normalize_color(field_spec["color"])
   if color_err:
       raise ValueError(f"Field {field_spec['name']}: {color_err}")
   ```

5. **Type References**
   - Validated during parsing when fields reference custom types
   - If type not found: parse fails with error

6. **Expression Syntax**
   - Validated when expression is evaluated
   - Invalid operators/tokens: raises `ValueError`

**Binary Validation** (during parsing):

1. **Field Validation Rules**
   ```yaml
   - { name: delimiter, type: u16, validate: { equals: 0x001C } }
   ```
   - Checked in `_validate()` method
   - Failure causes record to be marked with error

2. **Length Bounds**
   - Ensures length doesn't exceed file size
   - Prevents buffer overruns

3. **Type Discrimination**
   - If discriminator field missing: error
   - If discriminator doesn't match any case: uses default

### Registry System

**Purpose:** Map type codes to human-readable names and decoders

**Definition:**
```yaml
registry:
  "0x0065":
    name: given_name
    decode:
      as: string
      encoding: ascii

  "0x0101":
    name: birth_year
    decode:
      as: u16
```

**Decoder Types:**
- `string` - Decode bytes as text
- `u16`/`u32` - Decode bytes as integer
- `hex` - Display as hex bytes
- `ftm_packed_date` - Custom FTM date format

**Usage:** (`src/hexmap/core/yaml_parser.py:358`)
```python
def decode_record_payload(record: ParsedRecord, grammar: Grammar) -> str | None:
    # Get type discriminator
    type_disc = record.fields["header"].value["type_raw"]
    type_key = f"0x{type_disc:04X}"

    # Look up in registry
    if type_key in grammar.registry:
        entry = grammar.registry[type_key]
        decoder = entry.decode
        # Decode based on decoder.as_type
```

---

## Data Flow

### Complete Flow: User Opens File

```
1. User Action
   └─> File selection dialog

2. File Loading (app.py)
   └─> PagedReader created
       └─> File size determined
       └─> First page read into cache

3. Tab Activation (user switches to Chunking)
   └─> YAMLChunkingWidget.on_mount()
       └─> Default YAML loaded into editor
       └─> Ready for parsing

4. User Clicks "Parse"
   └─> parse_yaml() handler
       ├─> parse_yaml_grammar(yaml_text)
       │   └─> Grammar object created
       │
       ├─> RecordParser(grammar)
       │   └─> Parser ready
       │
       └─> parse_file(reader)
           ├─> For each record:
           │   ├─> Determine type (switch)
           │   ├─> Parse fields sequentially
           │   └─> Create ParsedRecord
           │
           └─> Returns records, errors

5. Display Results
   ├─> set_data(records, reader)
   │   └─> IncrementalSpanManager created
   │
   └─> rebuild()
       ├─> If Hex tab:
       │   ├─> HexView mounted/shown
       │   ├─> Viewport monitoring started
       │   └─> update_viewport()
       │       ├─> Binary search for visible records
       │       ├─> Generate spans for ~80-100 records
       │       └─> HexView.set_span_index()
       │
       ├─> If Raw tab:
       │   ├─> DataTable mounted/shown
       │   └─> All records added as rows
       │
       └─> If Types tab:
           ├─> DataTable mounted/shown
           └─> Records grouped by type
```

### Viewport-Based Span Generation Flow

```
HexView Scrolling
   └─> Timer checks viewport (100ms interval)
       └─> _update_viewport()
           ├─> Get viewport bounds
           │   ├─> viewport_start = hex_view.viewport_offset
           │   └─> viewport_end = start + (visible_rows * bytes_per_row)
           │
           ├─> IncrementalSpanManager.update_viewport(start, end)
           │   ├─> Check if viewport unchanged (cache hit)
           │   │   └─> Return cached SpanIndex (0ms)
           │   │
           │   └─> Viewport changed:
           │       ├─> Binary search for records in range
           │       │   └─> bisect_right on offset array
           │       │
           │       ├─> For each overlapping record:
           │       │   └─> Generate field spans
           │       │       ├─> Determine type group
           │       │       ├─> Apply color override
           │       │       └─> Create Span object
           │       │
           │       ├─> Build SpanIndex from spans
           │       └─> Cache viewport + spans
           │
           └─> HexView.set_span_index(span_index)
               └─> HexView refreshes with colored fields
```

**Performance:**
- Offset index build: ~3ms (once)
- Viewport update: <1ms (only visible records)
- Cached viewport: 0ms (instant)

---

## Key Design Patterns

### 1. Viewport-Based Rendering

**Problem:** Rendering 50,000+ spans causes UI freeze

**Solution:** Only generate/render data for visible viewport

**Implementation:**
- `IncrementalSpanManager` maintains lightweight offset index
- Binary search finds records overlapping viewport
- Spans generated on-demand for visible area only
- Cache prevents redundant work

**Used by:**
- HexView (spans for field coloring)
- DataTable (built-in virtual scrolling)

### 2. Paged File I/O

**Problem:** Large files exceed memory

**Solution:** Read file in chunks (pages), cache recent pages

**Implementation:**
- `PagedReader` with 64KB pages
- LRU cache for recently accessed pages
- Transparent to consumers (looks like byte array)

**Used by:**
- All file reading (parsers, hex view, etc.)

### 3. Reactive State Management

**Problem:** UI updates when data changes

**Solution:** Textual's reactive properties

**Implementation:**
```python
class MyWidget(Widget):
    selected_record: reactive[int | None] = reactive(None)

    def watch_selected_record(self, old, new):
        # Called automatically when selected_record changes
        self.update_inspector()
```

**Used by:**
- Tab switching
- Record selection
- Schema updates

### 4. Event-Driven Architecture

**Problem:** Decouple components, enable async operations

**Solution:** Message passing between widgets

**Implementation:**
```python
@on(DataTable.RowSelected)
def row_selected(self, event: DataTable.RowSelected) -> None:
    record_index = int(event.row_key.value)
    self.show_record_details(record_index)
```

**Used by:**
- All user interactions
- Timer callbacks
- Cross-widget communication

### 5. Data Structure Separation

**Problem:** Parsing logic mixed with UI logic

**Solution:** Clear separation: core/ vs widgets/

**Implementation:**
```
core/           # Pure data structures and parsing
  ├─ io.py      # File I/O
  ├─ spans.py   # Data structures
  └─ yaml_*.py  # Parsing logic

widgets/        # UI components
  ├─ hex_view.py        # Displays data
  └─ yaml_chunking.py   # Orchestrates UI
```

**Benefits:**
- Testable without UI
- Reusable parsing logic
- Clear responsibilities

### 6. Lazy Evaluation

**Problem:** Don't compute until needed

**Solution:** Deferred span generation, viewport monitoring

**Implementation:**
- Grammar parsing: immediate (validate early)
- Record parsing: immediate (need structure)
- Span generation: lazy (only for viewport)
- Decoding: lazy (only for visible rows)

**Used by:**
- Span system (viewport-based)
- Registry decoding (on-demand)

### 7. Immutable Data Structures

**Problem:** Prevent accidental mutations, enable caching

**Solution:** Frozen dataclasses

**Implementation:**
```python
@dataclass(frozen=True)
class Span:
    offset: int
    length: int
    # ... immutable fields
```

**Used by:**
- Spans (safe to cache)
- Type definitions (never change after parse)

---

## Component Interactions

### Hex View + Span System

```
User Action: Switch to Hex tab
   └─> YAMLChunkingWidget.rebuild()
       ├─> HexView.reader = self.reader
       ├─> _build_hex_view()
       │   └─> _update_viewport()
       │       └─> IncrementalSpanManager.update_viewport()
       │           └─> Returns SpanIndex
       │
       └─> HexView.set_span_index(span_index)
           └─> HexView renders with colors

User Action: Scroll hex view
   └─> Timer callback (100ms)
       └─> _check_viewport()
           └─> _update_viewport()
               └─> [same as above]

HexView Rendering (internal)
   └─> For each visible byte:
       ├─> SpanIndex.find(offset)
       ├─> If span found:
       │   ├─> Check color_override
       │   ├─> Determine color (override or group)
       │   └─> Render with color
       └─> Else: default color
```

### YAML Editor + Parser

```
User Action: Edit YAML
   └─> TextArea updates
       └─> (No action until Parse clicked)

User Action: Click Parse
   └─> @on(Button.Pressed, "#parse-btn")
       ├─> Get YAML text from editor
       │
       ├─> parse_yaml_grammar(text)
       │   ├─> Validate YAML syntax
       │   ├─> Validate field types
       │   ├─> Validate colors
       │   └─> Return Grammar or raise ValueError
       │
       ├─> On error:
       │   └─> Show notification
       │
       └─> On success:
           ├─> RecordParser(grammar)
           ├─> parse_file(reader)
           ├─> set_data(records, reader)
           └─> Show results in current tab
```

### DataTable + Sorting

```
User Action: Click column header
   └─> @on(DataTable.HeaderSelected)
       ├─> Track sort column and direction
       │   ├─> Same column? Toggle direction
       │   └─> New column? Reset to ascending
       │
       └─> table.sort(column_key, reverse=sort_reverse)
           └─> DataTable re-renders sorted
```

---

## Performance Optimizations

### 1. Viewport-Based Rendering
- **Before:** 50,000+ spans generated upfront (5+ second freeze)
- **After:** ~240 spans for visible viewport (<1ms)
- **Speedup:** 200x faster

### 2. Binary Search for Record Lookup
- **Method:** `bisect_right` on offset array
- **Complexity:** O(log n) instead of O(n)
- **Impact:** Instant record lookup even with 10,000+ records

### 3. Span Caching
- **Strategy:** Cache viewport + generated spans
- **Hit rate:** Very high (scrolling within same screen)
- **Impact:** 0ms for cached viewports

### 4. Paged File I/O
- **Strategy:** 64KB pages with LRU cache
- **Impact:** Can handle multi-GB files
- **Memory:** Only active pages in memory

### 5. Virtual Scrolling (DataTable)
- **Built-in:** Textual DataTable handles automatically
- **Impact:** Smooth scrolling with 10,000+ rows
- **Approach:** Only render visible rows

### 6. Show/Hide Pattern
- **Before:** Remove and recreate widgets (slow, ID conflicts)
- **After:** Hide with CSS, keep mounted
- **Impact:** Instant tab switching

---

## Testing Strategy

### Unit Tests

**Core Parsing:**
- `tests/test_chunking.py` - YAML grammar parsing
- `tests/test_incremental_spans.py` - Viewport span generation
- `tests/test_yaml_color_overrides.py` - Color override system

**Data Structures:**
- `tests/test_spans.py` - Span and SpanIndex
- `tests/test_paged_reader.py` - PagedReader

**Focus:** Pure logic, no UI

### Integration Tests

**Widget Tests:**
- Test widget composition
- Test message handling
- Mock Textual App for context

**Focus:** Widget interactions

### Performance Tests

**Approach:**
- Benchmark with real files (data/*.FTM)
- Measure parse times, viewport updates
- Profile memory usage

---

## Configuration and Defaults

### Default YAML Grammar

**Location:** `src/hexmap/widgets/yaml_chunking.py:26`

Embedded default for FTM format:
```python
DEFAULT_YAML = """
format: record_stream
endian: little
# ... full grammar
"""
```

### Theme/Styling

**Location:** `src/hexmap/ui/theme.tcss`

Global CSS applied to all widgets.

### Application Settings

**Entry Point:** `src/hexmap/app.py`
- TITLE, CSS_PATH defined in HexmapApp class
- Command-line args for file path

---

## Extension Points

### Adding New Field Types

1. Add to `PrimitiveType` enum in `yaml_grammar.py`
2. Add parsing logic in `RecordParser._parse_field()`
3. Update documentation

### Adding New Decoder Types

1. Add case to `decode_record_payload()` in `yaml_parser.py`
2. Handle in DecoderDef.as_type
3. Document in YAML_GRAMMAR_REFERENCE.md

### Adding New Widgets

1. Create widget class extending `Widget` or `Static`
2. Define `compose()` for layout
3. Add CSS in theme.tcss
4. Wire up message handlers
5. Integrate into app.py tab system

### Custom Color Schemes

1. Modify `src/hexmap/ui/theme.tcss`
2. Override color variables
3. Apply to specific widgets

---

## Debugging and Development

### Enable Debug Mode

Textual provides dev tools:
```bash
textual console
python -m hexmap.app --dev
```

### Logging

Standard Python logging:
```python
import logging
logger = logging.getLogger(__name__)
logger.debug("Debug info")
```

### Textual Inspector

Press Ctrl+D (or F12) to open inspector:
- Widget tree
- CSS inspector
- Reactive properties
- Performance stats

---

## Dependencies

### Core Dependencies

- **textual** - TUI framework
- **pyyaml** - YAML parsing
- **numpy** - Array operations (minimal usage)

### Development Dependencies

- **pytest** - Testing framework
- **ruff** - Linter/formatter

---

## Future Architecture Considerations

### Potential Improvements

1. **Plugin System**
   - Allow user-defined decoder types
   - Custom visualizations
   - File format plugins

2. **Background Parsing**
   - Parse large files in background thread
   - Progressive display as records parse
   - Cancel/resume support

3. **Incremental Parsing**
   - Don't re-parse unchanged portions
   - Useful for live file monitoring

4. **Multi-file Support**
   - Compare multiple files side-by-side
   - Cross-file references

5. **Export Formats**
   - Export parsed data to JSON/CSV
   - Generate reports

6. **Undo/Redo**
   - Track state changes
   - Implement command pattern

---

## Summary

ByteMap's architecture is designed for:

✅ **Performance** - Viewport-based rendering, paged I/O, binary search
✅ **Scalability** - Handle large files without loading into memory
✅ **Maintainability** - Clear separation: core vs UI, immutable data
✅ **Extensibility** - Plugin-ready structure, modular design
✅ **User Experience** - Responsive UI, immediate feedback, error handling

The combination of Textual's TUI framework with careful performance optimization creates a powerful tool for binary file analysis that runs entirely in the terminal.
