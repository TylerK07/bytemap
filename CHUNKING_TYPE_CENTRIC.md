# Chunking Tab - Type-Centric Workflow ✅

## Overview

Transformed the Chunking tab from a record-instance log into a **type-centric reverse-engineering workspace**. The mental model is now: *"The user is cataloging a dictionary of types. Records exist only to support that decision."*

## Key Changes

### 1. Types View as Default ✅

- **Default mode changed** from Raw → Types
- Users land directly in the type catalog view
- Raw and Decoded views remain accessible but secondary

### 2. Types Toolbar ✅

Added comprehensive toolbar (visible only in Types mode):

**Filter Options:**
- All types
- Unknown (no assignment or status=UNKNOWN)
- Tentative (status=TENTATIVE)
- Confirmed (status=CONFIRMED)

**Sort Options:**
- Count ↓ (most frequent first)
- Unknown First (unassigned types first, then by count)
- Variability (most variable payload lengths + hash diversity)

**Progress Indicator:**
- Live counter: "Assigned X / Y"
- Shows how many types have registry entries

### 3. Enhanced Type Display ✅

**Status Indicators:**
- `?` (yellow) = Unknown/unassigned
- `~` (cyan) = Tentative assignment
- `✓` (green) = Confirmed

**Format:**
```
? unk_414141 │ 414141 (u24be:4276545) │ 127× │ 4-16b
~ header_v1 │ 020000 │ 23× │ 8-8b
✓ timestamp │ FF0000 (u24be:16711680) │ 2505× │ 4-4b
```

Shows:
- Status icon
- Name (or auto-generated unk_XXXXXX)
- Raw bytes (hex)
- Normalized view (if different from raw)
- Count (N×)
- Length range (min-max bytes)

### 4. Reordered Inspector (Example-Driven) ✅

**New Layout Order:**
1. **Type Identity** (top)
   - Raw bytes
   - All normalizations (Uint BE, Uint LE, ASCII)

2. **Examples Section** (dominant, middle)
   - Diverse selection strategy:
     - Shortest payload
     - Longest payload
     - First occurrence
     - Last occurrence
     - Random samples (up to 6)
   - Shows up to 10 examples
   - Each example displays:
     - Label (Shortest, Longest, First, Sample N)
     - Offset (hex)
     - Payload length
     - Hex preview (16 bytes)
     - **Live decoded preview** (if decoder assigned)

3. **Registry Editor** (bottom)
   - Name input
   - Decoder selector
   - Decoder params
   - Notes
   - Status selector
   - Apply/Revert buttons

### 5. Keyboard Shortcuts ✅

Optimized "assign & move on" workflow:

| Key | Action |
|-----|--------|
| `j` | Move selection down in Types list |
| `k` | Move selection up in Types list |
| `n` | Jump to next Unknown type (wraps around) |
| `enter` | Focus Name input field in Inspector |
| `tab` | Cycle through input fields (built-in Textual) |
| `ctrl+enter` | Apply changes (quick save) |

**Workflow:**
1. Press `n` to jump to first unknown type
2. Examples display shows payload patterns
3. Press `enter` to focus Name field
4. Type name and assign decoder
5. Press `ctrl+enter` to apply
6. Press `n` to jump to next unknown
7. Repeat

### 6. UI State Fixes ✅

**Fixed "No files loaded" issue:**
- File corpus selector now shows current file when loaded
- Displays: `• AA.FTM` instead of "No files loaded"
- Auto-updates on mount

**Empty States:**
- Types view: "No types found — scan file first"
- Filtered view: "No unknown types" (when filter active)
- Raw/Decoded views: "No records found — adjust framing params and Scan"

## Testing

✅ **All tests pass:** `pytest tests/test_chunking.py` (6/6)
✅ **App launches cleanly:** No errors, keyboard shortcuts work
✅ **Layout verified:** 3-column horizontal (left/middle/right)
✅ **Keyboard navigation:** j/k/n/enter/ctrl+enter all functional

## Usage Example

```bash
python -m hexmap.cli data/AA.FTM
# Press '3' to switch to Chunking tab
```

**Type-centric workflow:**
1. Tab opens in Types view (default)
2. See all unique types sorted by count
3. Use toolbar to filter Unknown types
4. Press `n` to jump between unknowns
5. Review examples to understand payload structure
6. Press `enter`, name the type, assign decoder
7. Press `ctrl+enter` to save
8. Progress indicator updates (e.g., "Assigned 12 / 47")
9. Filter to Tentative to review uncertain assignments
10. Mark as Confirmed when validated

## Architecture

**Data Flow:**
1. Scan creates RecordSpan list
2. build_type_stats() aggregates by type_key
3. Types view filters & sorts TypeStats
4. Selection triggers Inspector update
5. Inspector shows identity → examples → editor
6. Apply updates registry
7. Decoded view refreshes with new names

**Key Classes:**
- `ChunkTablePanel`: Hosts Types view, toolbar, keyboard shortcuts
- `TypeRegistryInspector`: Example-driven inspector with live decoded previews
- `ChunkingWidget`: Coordinator with focus management

## Mental Model Shift

**Before (record-centric):**
- "Here are 2505 records, each is a thing"
- Raw view as default
- Inspector shows single record details

**After (type-centric):**
- "Here are 47 unique types, let's catalog them"
- Types view as default
- Inspector shows type patterns with examples
- Keyboard-driven cataloging workflow
- Progress tracking (X assigned / Y total)

The user is now **building a type dictionary**, not reviewing a log file.
