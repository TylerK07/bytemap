# Chunking Tab - Clean Type Display (Remove Numeric Normalization) ✅

## Problem

The UI was showing numeric type normalizations like `u24be: 0`, `u24be: 1280`, etc. everywhere:
- In the Types list
- In the Inspector identity section

This was **noise, not signal**. For type bytes specifically:
- You never reason about them numerically
- You reason about them as stable identifiers/tags
- Numeric interpretations (u24be, u24le) don't help identify purpose, name types, or decode payloads
- They add cognitive load without value

## Solution: Remove Numeric Normalization from UI

### Types View - Before

```
? unk_000500 │ 000500 (u24be:1280) │ 23× │ 8-8b
? unk_414141 │ 414141 (u24be:4276545) │ 127× │ 4-16b
```

**Problems:**
- `u24be:1280` is meaningless for identifying chunk type
- Clutters the display
- Distracts from actual semantic decoding task

### Types View - After

```
? unk_000500 │ 000500 │ 23× │ 8-8b
? unk_414141 │ 414141 (AAA) │ 127× │ 4-16b
```

**Clean:**
- Raw hex bytes (always shown)
- ASCII representation **only if printable** (e.g., `AAA` for `414141`)
- No numeric noise

### Inspector - Before

```
Type Inspector
─────────────
Type:
  Raw: 00 00 00
  Uint BE: u24be:0
  Uint LE: u24le:0
  ASCII: —
```

**Problems:**
- Shows `u24be:0` and `u24le:0` - completely useless
- Takes up space
- Doesn't help with decoding

### Inspector - After

```
Type Inspector
─────────────
Preview
  Raw: 000000
  ASCII: —

Decoder: [String ▼]
Examples:
  First: "FTMaker 2"
  ...
```

**Clean:**
- Raw hex (ground truth)
- ASCII only if printable
- Focus immediately on **decoder preview** and **examples**
- No numeric clutter

## Implementation Changes

### 1. Types View Formatting

```python
def _format_type_stats(self, type_key: str, stats: TypeStats) -> Text:
    """Format type statistics with raw hex (and optional ASCII if printable)."""
    # Status indicator + Name
    # ...

    # Type bytes (raw hex only)
    text.append(stats.type_bytes.hex(), style=PALETTE.parsed_offset)

    # Show ASCII if printable
    try:
        ascii_str = stats.type_bytes.decode('ascii')
        if ascii_str.isprintable() and not ascii_str.isspace():
            text.append(f" ({ascii_str})", style=PALETTE.inspector_dim)
    except:
        pass  # Not ASCII, that's fine

    # Count and stats
    # ...
```

### 2. Inspector Identity Section

```python
def _populate_identity(self) -> None:
    """Populate type identity section - raw hex and ASCII if printable."""
    # Show raw bytes
    raw_display.update(f"Raw: {self.current_entry.key_bytes.hex()}")

    # Show ASCII only if printable
    try:
        ascii_str = self.current_entry.key_bytes.decode('ascii')
        if ascii_str.isprintable() and not ascii_str.isspace():
            norm_display.update(f"ASCII: {ascii_str}")
        else:
            norm_display.update("ASCII: —")
    except:
        norm_display.update("ASCII: —")
```

## What Was Removed

❌ **Removed from UI:**
- `Uint BE: u24be:NNNN`
- `Uint LE: u24le:NNNN`
- `(u24be:NNNN)` annotations in Types list
- All numeric type normalization displays

✅ **Kept (internal):**
- Type normalization **data model** (still used for grouping types internally)
- Normalization selector in framing panel (for internal key generation)
- The actual normalization logic in `src/hexmap/core/chunks.py`

## Benefits

✅ **Cleaner UI** - No numeric noise cluttering the display
✅ **Focused workflow** - Decoder + Examples are visually dominant
✅ **Semantic only** - ASCII shown when it helps (printable tags like "HDR", "FMT")
✅ **Less cognitive load** - No meaningless `u24be:0` everywhere
✅ **Clear intent** - Type bytes are identifiers, not numbers

## Examples

### Binary Type (Non-printable)

```
? unk_000500 │ 000500 │ 23× │ 8-8b

Inspector:
  Raw: 000500
  ASCII: —
```

No ASCII clutter for binary types.

### Text-based Type (Printable)

```
? unk_484452 │ 484452 (HDR) │ 5× │ 16-16b

Inspector:
  Raw: 484452
  ASCII: HDR
```

ASCII shown because it's a helpful hint (`HDR` = header tag).

### Mixed Binary Type

```
? unk_ff0000 │ ff0000 │ 127× │ 4-16b

Inspector:
  Raw: ff0000
  ASCII: —
```

No ASCII for non-printable bytes - clean and focused.

## Testing

✅ All 6 chunking tests pass
✅ App launches with no errors
✅ Types view shows clean hex + optional ASCII
✅ Inspector shows raw + ASCII only (no numeric noise)

The UI is now **clean, semantic, and focused** on the actual reverse-engineering workflow!
