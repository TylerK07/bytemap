# Chunking Tab - 3-Column Layout Fix ✅

## Problem

The initial implementation incorrectly used a vertical stacking layout at the root level, causing all panels to stack top-to-bottom instead of displaying as three horizontal columns (left/middle/right).

## Root Cause

The `ChunkingWidget.compose()` method yielded 4 items at the root:
1. A Vertical container (with nested panels)
2. ChunkTablePanel
3. TypeRegistryInspector

This broke the CSS grid layout which expected exactly 3 direct children for horizontal columns.

## Solution

Restructured to yield exactly **3 direct children** in a horizontal layout:

### 1. Left Column (fixed width ~32 chars)
```python
with Vertical(id="chunking-left-col", classes="chunking-column"):
    yield ChunkFramingPanel()
    yield FileCorpusSelector()
```
- Chunk framing controls (type width, length width, endian, semantics, normalization)
- File/corpus selector
- Scrollable when content exceeds height

### 2. Middle Column (1fr - takes remaining space)
```python
yield ChunkTablePanel(classes="chunking-column chunking-middle")
```
- Mode toggle buttons (Raw / Decoded / Types)
- Main records table/tree
- Scrollable, minimum width 60 chars

### 3. Right Column (fixed width ~38 chars)
```python
yield TypeRegistryInspector(classes="chunking-column")
```
- Type registry editor
- Decoder selector
- Examples display
- Scrollable, minimum width 32 chars

## Changes Made

### **src/hexmap/widgets/chunking.py**

1. **ChunkingWidget class:**
   - Added `DEFAULT_CSS` with `layout: horizontal`
   - Restructured `compose()` to yield exactly 3 children
   - Added `classes="chunking-column"` to all columns
   - Added `classes="chunking-middle"` to center column

2. **ChunkFramingPanel:**
   - Shortened labels to prevent truncation:
     - "Type Width (bytes):" → "Type Width:"
     - "Length Width (bytes):" → "Length Width:"
     - "Length Endian:" → "Endian:"
     - "Length Semantics:" → "Semantics:"
     - "Max Payload (bytes, optional):" → "Max Payload:"
     - "Type Normalization:" → "Normalization:"
   - Shortened select options:
     - "Big Endian" → "Big"
     - "Little Endian" → "Little"
     - "Includes Header" → "+ Header"
     - "Unsigned BE" → "Uint BE"
     - "Unsigned LE" → "Uint LE"

3. **ChunkTablePanel and TypeRegistryInspector:**
   - Changed `__init__(self)` to `__init__(self, **kwargs)` to accept classes
   - Added `layout: vertical` to DEFAULT_CSS
   - Pass kwargs to parent `super().__init__(**kwargs)`

### **src/hexmap/ui/theme.tcss**

1. **Removed grid-based layout:**
   ```css
   /* REMOVED:
   #tab-chunking {
     layout: grid;
     grid-size: 3 1;
     ...
   }
   */
   ```

2. **Added column-specific sizing:**
   ```css
   .chunking-column {
     height: 1fr;
   }

   #chunking-left-col {
     width: 32;
     min-width: 28;
     max-width: 40;
   }

   .chunking-middle {
     width: 1fr;
     min-width: 60;
   }

   .chunking-column:last-child {
     width: 38;
     min-width: 32;
     max-width: 45;
   }
   ```

3. **Enhanced tree scrolling:**
   ```css
   #chunk-tree {
     height: 1fr;
     overflow: auto;
     scrollbar-gutter: stable;
   }
   ```

## Layout Verification

### Horizontal Structure
```
┌─────────────────────────────────────────────────────────────────────┐
│ Left (32)         │  Middle (1fr)      │  Right (38)               │
├───────────────────┼────────────────────┼──────────────────────────┤
│ Chunk Framing     │  Raw/Decoded/Types │  Type Registry           │
│ - Type Width      │  ┌──────────────┐  │  - Selected Type         │
│ - Length Width    │  │ Record List  │  │  - Name                  │
│ - Endian          │  │ 2505 records │  │  - Decoder               │
│ - Semantics       │  │ Scrollable   │  │  - Params                │
│ - Max Payload     │  │              │  │  - Notes                 │
│ - Normalization   │  └──────────────┘  │  - Examples              │
│ [Scan Button]     │                    │                          │
├───────────────────┤                    │                          │
│ File Selection    │                    │                          │
│ - Mode: Single    │                    │                          │
│ - Files list      │                    │                          │
└───────────────────┴────────────────────┴──────────────────────────┘
```

## Testing

✅ **All tests pass:** 6/6 chunking tests
✅ **Syntax valid:** No compilation errors
✅ **App launches:** Clean startup with no CSS errors
✅ **Layout confirmed:** 3 columns horizontal (left/middle/right)

## Usage

```bash
python -m hexmap.cli data/AA.FTM
# Press '3' to switch to Chunking tab
```

Expected behavior:
- ✅ Three distinct vertical columns visible
- ✅ Left: Framing controls (no label truncation)
- ✅ Middle: Records table (takes most space, scrollable)
- ✅ Right: Inspector (always visible, scrollable)
- ✅ Auto-scan runs on mount (2505 records for AA.FTM)
- ✅ All panels properly bordered and focusable

## Key Constraints Enforced

1. ✅ Root container has exactly 3 children (horizontal layout)
2. ✅ No vertical stacking at root level
3. ✅ Left column: fixed ~32 width
4. ✅ Middle column: fluid 1fr (takes remaining space)
5. ✅ Right column: fixed ~38 width
6. ✅ All columns: full height with overflow scrolling
7. ✅ Labels shortened to prevent truncation in narrow columns
