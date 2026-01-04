# Chunking Tab - Live Decoder Preview ✅

## Problem

Previously, when you selected a decoder in the Inspector, **you couldn't see what it did** until you pressed Apply. The Examples section showed raw hex even though "Decoder: String" was selected in the registry editor. This made it hard to experiment with decoders and verify they worked correctly.

## Solution: Split Preview/Registry Sections

Refactored the Type Inspector into **two distinct sections**:

### 1. Preview Section (Top) - Try Before You Commit

**Purpose**: Live preview of what happens if you use this decoder

**Contents:**
- Type identity (raw bytes + normalizations)
- **Decoder selector** (the "try it" control)
- **Decoded examples** (rendered with preview decoder)

**Behavior:**
- Changing the decoder **immediately re-renders examples** with decoded output
- This happens as a **preview** (no-commit "try") - doesn't affect registry or Decoded view
- You can experiment with different decoders to find the right one

### 2. Registry Section (Below) - Commit Your Choice

**Purpose**: Persist the decoder choice and assign metadata

**Contents:**
- Name input
- Notes input
- Status selector (Unknown/Tentative/Confirmed)
- Apply/Revert buttons

**Behavior:**
- **Apply commits** the preview decoder to the registry entry
- Updates the Decoded view table with the new decoder
- Revert resets preview decoder to match saved registry entry

## Example Workflow

**Before (broken):**
1. Click a type in Types list
2. In inspector, change "Decoder" to "String"
3. Examples still show raw hex: `46544d616b6572203200`
4. No idea if String decoder is correct
5. Press Apply blindly, hope it works

**After (fixed):**
1. Click a type in Types list
2. In Preview section, change "Try Decoder" to "String"
3. Examples **immediately update**: `FTMaker 2 (46544d616b6572203200)`
4. Can **see decoded value** before committing
5. If it looks good, press Apply to persist
6. If not, try "Integer" or another decoder

## Technical Implementation

### Preview State

```python
class TypeRegistryInspector:
    def __init__(self):
        # Preview state (live decoder selection before Apply)
        self.preview_decoder_id: str = "none"
        self.preview_decoder_params: DecoderParams = DecoderParams()
```

### Live Re-render on Decoder Change

```python
@on(Select.Changed, "#preview-decoder-select")
def preview_decoder_changed(self, event: Select.Changed) -> None:
    """Handle preview decoder selection - immediately re-render examples."""
    self.preview_decoder_id = str(event.value)
    self.preview_decoder_params = DecoderParams()
    # Re-render examples with new decoder
    self._update_examples()
```

### Examples Use Preview Decoder

```python
def _update_examples(self) -> None:
    """Update examples display with decoded previews using preview decoder."""
    # ... get diverse examples ...

    for label, example in examples[:10]:
        # Show decoded preview if preview decoder is set
        if self.preview_decoder_id != "none":
            decoded = decode_payload(payload, self.preview_decoder_id, self.preview_decoder_params)
            if decoded:
                # Show decoded value prominently
                examples_text.append(decoded[:60], style=PALETTE.inspector_value)
                # Show hex as secondary
                examples_text.append(f" ({preview.hex()[:32]})", style=PALETTE.inspector_dim)
```

### Apply Commits Preview Decoder

```python
@on(Button.Pressed, "#apply-button")
def apply_changes(self) -> None:
    """Apply changes to registry entry - commits preview decoder."""
    # Update entry with preview decoder (commit the preview)
    self.current_entry = TypeRegistryEntry(
        key_bytes=self.current_entry.key_bytes,
        name=name,
        decoder_id=self.preview_decoder_id,  # Commit preview decoder
        decoder_params=self.preview_decoder_params,  # Commit preview params
        notes=notes,
        status=DecoderStatus(status_str),
    )
    # Update registry and refresh Decoded view
    self.registry[self.current_type_key] = self.current_entry
    app.chunking_widget.registry_updated()
```

## UI Layout

```
┌─────────────────────────────────────┐
│ Type Inspector                      │
├─────────────────────────────────────┤
│ === PREVIEW SECTION ===             │
│ Type: 414141                        │
│ Raw: 414141                         │
│ Uint BE: u24be:4276545              │
│                                     │
│ Try Decoder: [String ▼]             │
│                                     │
│ Examples:                           │
│ First: 00000010 "FTMaker 2" (4654..)│
│ Last:  00001a3c "Builder" (427569..)│
│ Shortest: ... "A" (41)              │
│ Longest: ... "Very Long Name..." (..)│
│                                     │
├─────────────────────────────────────┤
│ === REGISTRY SECTION ===            │
│ Name: [header_v1_____________]      │
│ Notes: [____________________]       │
│ Status: [Tentative ▼]               │
│ [Apply] [Revert]                    │
└─────────────────────────────────────┘
```

## Benefits

✅ **Immediate feedback** - See decoded output instantly
✅ **Experimentation** - Try different decoders without committing
✅ **Confidence** - Verify decoder works before Apply
✅ **No surprises** - Examples show exactly what Decoded view will display
✅ **Clear separation** - Preview (try) vs Registry (commit)

## Example: String Decoder

```
Try Decoder: String

Examples:
First: 00000123 FTMaker 2 (46544d616b65722032)
Last:  000015ab Document Builder (446f63756d656e74204275696c646572)
Shortest: 0000beef A (41)
Sample 1: 00001234 Header v1.2 (48656164657220763...)
```

**Without decoder:**
```
Examples:
First: 00000123 46544d616b65722032
Last:  000015ab 446f63756d656e74204275696c646572
```

The decoded output is now **immediately visible** as you select decoders!
