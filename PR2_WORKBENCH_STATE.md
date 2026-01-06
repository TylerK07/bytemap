# PR#2: Workbench State Model + Selection Cascade Plumbing

## Summary

Added reactive state model to AgentWorkbenchTab with selection cascade behavior. Users can now select versions, patch operations, and runs, with UI updates cascading from left to right. Uses mock data for testing - real SpecStore integration comes in PR#3.

## Files Changed

### New Files
1. **`src/hexmap/widgets/workbench_state.py`** (223 lines)
   - `WorkbenchState` dataclass with reactive fields
   - 5 custom Textual messages (VersionSelected, VersionCheckedOut, PatchOpSelected, RunSelected, EvidenceSelected)
   - Mock data classes (MockVersion, MockPatchOp, MockRun)
   - In-memory mock data (4 versions, patch ops, runs)

### Modified Files
1. **`src/hexmap/widgets/agent_workbench.py`** (395 lines, completely rewritten)
   - Added reactive properties: `selected_version_id`, `selected_patch_op_id`, `selected_run_id`
   - Replaced static placeholders with OptionList widgets
   - Added selection handlers and watchers
   - Implemented cascade: version → patch ops/runs → evidence
   - Added inspector panels at bottom of each column

2. **`src/hexmap/ui/theme.tcss`** (63 lines in workbench section, updated from 40)
   - Added styles for `.column-scroll`, `.column-inspector`, `.section-label`
   - Added styles for OptionList widgets
   - Added inspector styles

## New Classes & Data Structures

### Messages (`workbench_state.py`)

All messages inherit from `textual.message.Message`:

1. **`VersionSelected(version_id: str | None)`**
   - Posted when user selects a version in Column 1
   - `None` clears selection

2. **`VersionCheckedOut(version_id: str)`**
   - Posted when user checks out a version (PR#3+)
   - Makes it the working version

3. **`PatchOpSelected(patch_op_id: str | None)`**
   - Posted when user selects a patch operation in Column 2

4. **`RunSelected(run_id: str | None)`**
   - Posted when user selects a run in Column 2

5. **`EvidenceSelected(evidence_ref: dict | None)`**
   - Posted when evidence is selected (byte range, anomaly)
   - Used in PR#6 for hex view integration

### State Model

**`WorkbenchState`** (dataclass):
- `selected_version_id: str | None`
- `checked_out_version_id: str | None`
- `selected_patch_op_id: str | None`
- `selected_run_id: str | None`
- `selected_evidence_ref: dict | None`

Methods:
- `clear_derived_selections()` - Clears patch/run/evidence when version changes
- `clear_evidence_selection()` - Clears evidence when patch/run changes

### Mock Data

**PR#2 only** - replaced by real SpecStore in PR#3:

- `MOCK_VERSIONS`: 4 fake versions (baseline, 2 candidates, 1 draft)
- `MOCK_PATCH_OPS`: Patch operations per version
- `MOCK_RUNS`: Parse runs per version

Each mock includes display data (labels, scores, coverage deltas).

## Message/Event Flow

### Selection Cascade (Left → Right)

```
┌─────────────────────────────────────────────────────────────┐
│                    USER INTERACTIONS                         │
└─────────────────────────────────────────────────────────────┘
                              │
                              v
┌─────────────────────────────────────────────────────────────┐
│ Column 1: User clicks version in OptionList                 │
│                                                              │
│  OptionList.OptionSelected event                            │
│         │                                                    │
│         v                                                    │
│  on_option_list_option_selected()                           │
│         │                                                    │
│         v                                                    │
│  _handle_version_selected()                                 │
│         │                                                    │
│         ├──> Update state.selected_version_id               │
│         ├──> Update reactive selected_version_id            │
│         └──> Post VersionSelected message                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              v
┌─────────────────────────────────────────────────────────────┐
│ Reactive Watcher Triggered                                  │
│                                                              │
│  watch_selected_version_id() called                         │
│         │                                                    │
│         ├──> _populate_patch_ops_list(version_id)           │
│         ├──> _populate_runs_list(version_id)                │
│         └──> _update_version_inspector(version_id)          │
└─────────────────────────────────────────────────────────────┘
                              │
                              v
┌─────────────────────────────────────────────────────────────┐
│ Column 2: Patch Ops & Runs Lists Update                     │
│                                                              │
│  - Patch ops list filled with version's ops                 │
│  - Runs list filled with version's runs                     │
│  - Inspector shows version details                          │
└─────────────────────────────────────────────────────────────┘
                              │
                              v
┌─────────────────────────────────────────────────────────────┐
│ Column 2: User clicks patch op or run                       │
│                                                              │
│  OptionList.OptionSelected event                            │
│         │                                                    │
│         v                                                    │
│  _handle_patch_op_selected() or _handle_run_selected()      │
│         │                                                    │
│         ├──> Update state                                   │
│         ├──> Update reactive property                       │
│         └──> Post PatchOpSelected or RunSelected message    │
└─────────────────────────────────────────────────────────────┘
                              │
                              v
┌─────────────────────────────────────────────────────────────┐
│ Reactive Watcher Triggered                                  │
│                                                              │
│  watch_selected_patch_op_id() or watch_selected_run_id()    │
│         │                                                    │
│         └──> _update_patch_ops_inspector() or               │
│              _update_runs_inspector()                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              v
┌─────────────────────────────────────────────────────────────┐
│ Column 2/3: Inspector Updates                               │
│                                                              │
│  - Inspector shows patch op or run details                  │
│  - (PR#6: Column 3 Evidence will show hex highlights)       │
└─────────────────────────────────────────────────────────────┘
```

### Message Flow Summary

**Intra-widget (within AgentWorkbenchTab):**
1. OptionList selection → handler → state update → reactive watcher → UI update

**Inter-widget (future PRs):**
- VersionSelected → (PR#6) HexView updates evidence highlighting
- RunSelected → (PR#6) HexView loads run's spans
- EvidenceSelected → (PR#6) HexView scrolls to byte range

## Acceptance Checklist

- [x] WorkbenchState dataclass created with all required fields
- [x] 5 custom messages defined (VersionSelected, VersionCheckedOut, PatchOpSelected, RunSelected, EvidenceSelected)
- [x] Reactive properties added to AgentWorkbenchTab
- [x] OptionList widgets replace static placeholders
- [x] Selection handlers implemented
- [x] Reactive watchers implement cascade behavior
- [x] Mock data provides realistic test data
- [x] Version inspector shows details
- [x] Patch ops inspector shows details
- [x] Runs inspector shows details
- [x] Selecting version updates Column 2
- [x] Selecting patch op/run updates inspectors
- [x] No SpecStore integration (still mocked)

## Manual Verification Steps

### Test 1: Version Selection Cascade
```bash
python -m hexmap.app schema/ftm.yaml

# 1. Switch to Workbench tab (press "4")
# 2. Observe Column 1 has 4 versions listed:
#    [baseline] Initial ✓ (score: 45)
#    [candidate] Add header fields ✓ (score: 67, Δ: +22%)
#    [candidate] Fix length parsing ✗ (score: —, Δ: -5%)
#    [draft] Work in progress ✓ (score: 55, Δ: +10%)
#
# 3. Click first version "[baseline] Initial"
# 4. Observe Column 2 updates:
#    - Patch Operations: "(no patch operations)"
#    - Runs: "✓ Coverage: 45%, Score: 45"
# 5. Observe version inspector at bottom of Column 1 shows:
#    Version: Initial
#    Role: baseline
#    Status: ok
#    Score: 45.0
#    Coverage Δ: —
```

**Expected:** Column 2 populates with data for selected version, inspector shows details.

### Test 2: Patch Operations Selection
```bash
# Continuing from Test 1...

# 1. Click second version "[candidate] Add header fields"
# 2. Observe Column 2 updates:
#    - Patch Operations shows 2 ops:
#      InsertField: Add flags: u16
#      InsertField: Add count: u8
# 3. Click first patch op "InsertField: Add flags: u16"
# 4. Observe patch ops inspector shows:
#    Operation: InsertField
#    Path: types.Header.fields[2]
#    Summary: Add flags: u16
```

**Expected:** Patch ops list updates, selecting an op shows details in inspector.

### Test 3: Run Selection
```bash
# Continuing from Test 2...

# 1. Click the run "✓ Coverage: 67%, Score: 67"
# 2. Observe runs inspector shows:
#    Run: r2
#    Status: ok
#    Coverage: 67.0%
#    Score: 67.0
#    [Jump to error]
```

**Expected:** Run details appear in inspector.

### Test 4: Selection Cascade (version change clears derived)
```bash
# 1. Have version 2 selected with a patch op selected
# 2. Click version 1 (different version)
# 3. Observe:
#    - Column 2 lists update for version 1
#    - Patch op selection is cleared (no op selected)
#    - Patch ops inspector shows "Select a patch operation"
```

**Expected:** Changing version clears patch op/run selections.

### Test 5: Error State (version with parse error)
```bash
# 1. Click third version "[candidate] Fix length parsing ✗"
# 2. Observe:
#    - Version is marked with ✗
#    - Score shows "—"
#    - Coverage Δ shows "-5%"
#    - Runs list shows "✗ Coverage: 40%, Score: 0"
```

**Expected:** Error states are visually distinct.

## Testing

### Automated Tests
None for PR#2 - this is UI behavior with mock data. Future PRs will add integration tests when real data flows in.

### Manual Test Plan (Minimal)

**2-minute test:**

```bash
# 1. Start app (15 sec)
python -m hexmap.app schema/ftm.yaml

# 2. Navigate to Workbench (5 sec)
Press "4"

# 3. Test selection cascade (60 sec)
- Click version "[baseline] Initial" → Column 2 updates ✓
- Click version "[candidate] Add header fields" → Column 2 updates with 2 ops ✓
- Click first patch op → Inspector shows op details ✓
- Click version "[baseline] Initial" again → Patch op selection cleared ✓

# 4. Test all versions (30 sec)
- Click each version, verify Column 2 updates
- Verify inspector shows different details for each
```

**Pass criteria:**
- All versions selectable
- Column 2 updates correctly
- Inspectors show details
- Selection cascade works (version change clears derived)

## Design Notes

### Why Reactive Properties?

Textual's reactive system provides automatic dirty checking and efficient updates. When `selected_version_id` changes, only `watch_selected_version_id()` runs - no manual update tracking needed.

### Why Separate State Object?

The `WorkbenchState` dataclass serves as:
1. **Documentation** - clear schema of all state fields
2. **Reset logic** - `clear_derived_selections()` in one place
3. **Future serialization** - easy to save/restore state
4. **Type safety** - explicit types for all fields

### Selection Cascade Hierarchy

Following left-to-right inspection flow:
1. **Version** (Column 1) - primary selection
2. **Patch Op / Run** (Column 2) - derived from version
3. **Evidence** (Column 3) - derived from patch op / run

Changing higher-level selections clears lower levels.

### Mock Data Design

Mock data includes:
- **Varied states** - ok, lint_error, parse_error
- **Varied roles** - baseline, candidate, draft
- **Score progression** - shows improvements and regressions
- **Coverage deltas** - demonstrates comparison

This exercises all UI paths without needing real SpecStore.

## What Changed vs. PR#1

### Before (PR#1)
- Static placeholders: "(placeholder)" text
- No interaction
- No state

### After (PR#2)
- Interactive OptionList widgets
- Selectable versions, patch ops, runs
- Reactive state with cascade
- Inspector panels with details
- Mock data for testing
- Message system for future integration

## Dependencies

**New dependencies:** None

**Textual features used:**
- `reactive()` - reactive properties
- `Message` - custom messages
- `OptionList` - selectable lists
- `ScrollableContainer` - scrollable regions
- Watchers (`watch_*` methods)

## Future PRs

- **PR#3:** Replace mock data with real SpecStore integration
- **PR#4:** Add patch operation editing UI
- **PR#5:** Add run execution and error navigation
- **PR#6:** Integrate evidence with hex view (byte highlighting)
- **PR#7:** Add DraftSession support
- **PR#8:** Add Chat interface

## Implementation Notes

### Why Both State and Reactive Properties?

- **`self.state.selected_version_id`** - internal state object (data model)
- **`self.selected_version_id` (reactive)** - triggers watchers (view model)

This separation allows:
- State object can be serialized/deserialized
- Reactive properties trigger UI updates
- Clear separation of concerns

### Index Mapping Pattern

OptionList uses integer indices, but we need string IDs. The pattern:
```python
self._version_index_to_id: dict[int, str] = {}

# When populating:
for idx, version in enumerate(versions):
    list.add_option(label)
    self._version_index_to_id[idx] = version.id

# When handling selection:
version_id = self._version_index_to_id.get(option_index)
```

This matches the pattern in SchemaLibraryModal (line 2399 in app.py).

### Message Posting Pattern

Messages are posted but not handled within AgentWorkbenchTab (yet). In PR#6, HexView will subscribe to these messages to update evidence highlighting.

Pattern:
```python
self.post_message(VersionSelected(version_id))  # Bubbles up to app
```

App can handle with:
```python
def on_version_selected(self, event: VersionSelected) -> None:
    # Update hex view, etc.
```

## Performance Considerations

- **Reactive updates:** Only changed watchers fire
- **OptionList:** Efficient for < 1000 items (plenty for versions)
- **Mock data:** In-memory dicts - O(1) lookup
- **UI updates:** Only visible elements render

No performance concerns for PR#2 scope.

## Code Quality

- ✅ Type hints throughout
- ✅ Docstrings for all public methods
- ✅ Clear separation: handlers → state → watchers → UI
- ✅ Consistent naming: `_handle_*`, `_populate_*`, `_update_*`
- ✅ Error handling: checks for None, missing data
- ✅ Minimal diff: Only touches workbench files

## Known Limitations (by design for PR#2)

- ❌ No real SpecStore integration (mock data only)
- ❌ No patch operation editing
- ❌ No run execution
- ❌ No hex view integration
- ❌ No "Checkout" / "Promote" / "Branch" buttons (placeholders only)
- ❌ No "Jump to error" functionality

All addressed in future PRs.
