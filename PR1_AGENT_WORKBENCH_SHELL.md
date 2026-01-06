# PR#1: Add "Agent Workbench" Tab Shell

## Summary

Added new "Agent Workbench" tab to the existing tab system with 3-column placeholder layout and file context display. This is the foundation for Phase 7's spec iteration UI.

## Files Changed

### New Files
1. **`src/hexmap/widgets/agent_workbench.py`** (59 lines)
   - New widget for Agent Workbench tab
   - 3-column placeholder layout
   - File path display in header

### Modified Files
1. **`src/hexmap/app.py`** (5 changes)
   - Added import for `AgentWorkbenchTab` (line 63)
   - Added keybinding `("4", "tab_4", "Workbench")` (line 93)
   - Instantiated `self.agent_workbench` in compose (line 168)
   - Added TabPane for Workbench (line 175)
   - Added `action_tab_4()` method (lines 679-683)

2. **`src/hexmap/ui/theme.tcss`** (40 lines added)
   - CSS styles for workbench header, columns, and content
   - Focus states for column navigation

## New Classes

### `AgentWorkbenchTab(Container)`
**Location:** `src/hexmap/widgets/agent_workbench.py`

**Constructor:**
```python
def __init__(self, file_path: str) -> None
```

**Instance Variables:**
- `self.file_path: str` - Path to binary file being analyzed

**Methods:**
- `compose() -> ComposeResult` - Renders 3-column layout with headers

**Layout Structure:**
```
┌─────────────────────────────────────────────────────────┐
│ Agent Workbench: /path/to/file.bin                     │
├──────────────────┬──────────────────┬───────────────────┤
│ Column 1:        │ Column 2:        │ Column 3:         │
│ Versions         │ Patches & Runs   │ Evidence          │
│                  │                  │                   │
│ (placeholder)    │ (placeholder)    │ (placeholder)     │
└──────────────────┴──────────────────┴───────────────────┘
```

## Message/Event Flow

**PR#1 has no message flow** - this is a shell with static placeholders only.

### Current Flow (this PR):
```
User presses "4"
    → action_tab_4() called
    → TabbedContent switches to "tab-workbench"
    → AgentWorkbenchTab renders static layout
```

### Future Flow (PR#2+):
- Selection events will be added in PR#2
- State updates will cascade to columns
- Real data from SpecStore in PR#3+

## Acceptance Checklist

- [x] AgentWorkbenchTab widget created
- [x] Widget imported in app.py
- [x] TabPane registered in TabbedContent
- [x] Keybinding "4" works
- [x] File path displays in tab header
- [x] 3 columns render with headers
- [x] No core logic changes
- [x] No parser invocation
- [x] No SpecStore integration

## Manual Verification Steps

### Test 1: Tab Appears and Switches
```bash
# Run the app with any binary file
python -m hexmap.app /path/to/any/file.bin

# Once app loads:
1. Press "4" key
2. Verify tab switches to "Workbench"
3. Verify status bar shows: "4 Workbench  LLM-driven spec iteration"
4. Press Ctrl+Tab to cycle through tabs
5. Verify Workbench tab is in the rotation
```

**Expected:** Tab switches successfully, Workbench tab appears in rotation.

### Test 2: File Context Display
```bash
# Run with a specific file
python -m hexmap.app /tmp/test.bin

# Switch to Workbench tab (press "4")
```

**Expected:** Header shows "Agent Workbench: /tmp/test.bin"

### Test 3: Layout Structure
```bash
# Switch to Workbench tab
# Observe the layout
```

**Expected:**
- 3 columns side-by-side
- Column headers: "Column 1: Versions", "Column 2: Patches & Runs", "Column 3: Evidence"
- Each column shows "(placeholder)" content
- Columns have visible borders

### Test 4: Focus and Navigation
```bash
# Switch to Workbench tab
# Press Tab/Shift+Tab to navigate
```

**Expected:**
- Focus cycles through columns (borders highlight on focus)
- Textual's default focus navigation works

### Test 5: No Regression on Other Tabs
```bash
# Test existing tabs still work
1. Press "1" → Explore tab
2. Press "2" → Diff tab
3. Press "3" → Chunking tab
4. Press "4" → Workbench tab
```

**Expected:** All tabs work, no errors, no layout issues.

## Testing

### Automated Tests
None for this PR - this is UI shell only. Future PRs will add tests for state management and interactions.

### Manual Test Plan (Minimal)
1. Start app: `python -m hexmap.app schema/ftm.yaml`
2. Press "4" to switch to Workbench
3. Verify file path in header matches the opened file
4. Verify 3 columns render
5. Press "1" to return to Explore tab (verify no errors)

**Test Duration:** ~30 seconds

## Design Notes

### Why This Approach?
- **Minimal diff:** Only adds new code, doesn't modify existing widgets
- **Scoped:** Just the shell, no logic or data integration
- **Testable:** Easy to verify visually
- **Foundation:** Provides structure for future PRs to build on

### Left-to-Right Hierarchy
Following the spec, the layout is:
1. **Left (Column 1):** Versions - primary selection point
2. **Middle (Column 2):** Patches/Runs - derived from version selection
3. **Right (Column 3):** Evidence - derived from patch/run selection

This matches the natural inspection flow: Select version → Inspect changes → View evidence.

## What Changed vs. Original Code

### Before
- 3 tabs: Explore, Diff, Chunking
- Keybindings: 1, 2, 3

### After
- 4 tabs: Explore, Diff, Chunking, **Workbench**
- Keybindings: 1, 2, 3, **4**
- New widget: `AgentWorkbenchTab`
- New CSS: `.workbench-*` styles

## Dependencies

**No new dependencies.** Uses only existing Textual widgets:
- `Container`
- `Horizontal`
- `Static`

## Future PRs

- **PR#2:** Add state model and selection messages
- **PR#3:** Integrate SpecStore for real version data
- **PR#4:** Build Patch Ops UI
- **PR#5:** Build Runs UI
- **PR#6:** Integrate Evidence with hex view
- **PR#7:** Add DraftSession support
- **PR#8:** Add Chat interface
