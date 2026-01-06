# PR#7: Draft/Promote/Branch Functionality

## Summary

Implemented write operations for version management. Users can now promote versions to baseline (changing the reference point for comparisons) and create branch versions using patch application. The Promote and Branch buttons are now fully functional, enabling version graph manipulation and spec iteration workflows. This completes the core workbench functionality, with only Chat interface (PR#8) remaining.

## Files Changed

### Modified Files

1. **`src/hexmap/widgets/workbench_manager.py`** (70 lines changed)
   - **Added import**: `from hexmap.core.spec_patch import Patch`
   - **Added method**: `promote_to_baseline(version_id)` - sets version as baseline reference
   - **Added method**: `create_branch_version(parent_id, patch, label)` - creates child version with patch

2. **`src/hexmap/widgets/agent_workbench.py`** (80 lines changed)
   - **Added imports**: `InsertField, Patch` from spec_patch
   - **Implemented `_handle_promote()`** - promotes selected version to baseline
   - **Implemented `_handle_branch()`** - creates branch version with test patch
   - Both handlers refresh UI and update inspector

## What Changed vs. PR#6

### Before (PR#6)
- Promote button showed placeholder message
- Branch button showed placeholder message
- No version creation capability
- Baseline was fixed (initial version only)
- Read-only workbench

### After (PR#7)
- Promote button sets selected version as baseline
- Branch button creates new version with patch applied
- Real version graph manipulation
- Coverage deltas update when baseline changes
- Write-enabled workbench (version creation works)

## Data Flow

### Promote Flow

```
User clicks "Promote" button
    → on_button_pressed(event) with btn-promote
    → _handle_promote()
        │
        ├──> Check manager and selected_version_id
        ├──> manager.promote_to_baseline(version_id)
        │    │
        │    ├──> Clear previous baseline role
        │    │    (old baseline becomes "candidate")
        │    ├──> Set _baseline_version_id = version_id
        │    └──> Update metadata.role = "baseline"
        │
        ├──> _populate_version_list()
        │    └──> Versions redisplayed with new [baseline] badge
        │
        └──> _update_version_inspector(version_id)
             └──> Inspector shows new role
        │
        v
    Version list shows:
        - New [baseline] badge on promoted version
        - Old baseline now shows [candidate]
        - Coverage deltas recalculated vs new baseline
```

### Branch Flow

```
User clicks "Branch" button
    → on_button_pressed(event) with btn-branch
    → _handle_branch()
        │
        ├──> Check manager and selected_version_id
        ├──> Get parent version from manager
        ├──> Find first type in schema
        ├──> Create test patch:
        │    Patch(ops=(
        │        InsertField(
        │            path=("types", "FirstType"),
        │            index=-1,  # Append
        │            field_def={
        │                "name": "comment",
        │                "type": "str",
        │                "length": 64
        │            }
        │        ),
        │    ))
        │
        ├──> manager.create_branch_version(parent_id, patch, label)
        │    │
        │    ├──> spec_store.apply_patch(parent_id, patch, run_lint=True)
        │    │    │
        │    │    ├──> Validate patch
        │    │    ├──> Apply ops to spec_dict
        │    │    ├──> Serialize to YAML
        │    │    ├──> Run lint
        │    │    └──> Create SpecVersion with patch_applied
        │    │
        │    ├──> Create VersionMetadata (role="candidate")
        │    ├──> Auto-run parse: _run_parse_for_version()
        │    │    └──> Create RunArtifact with stats and anomalies
        │    └──> Return new_version_id
        │
        ├──> _populate_version_list()
        │    └──> New version appears in list
        │
        └──> Auto-select new version
             └──> Highlight new version in OptionList
        │
        v
    Version list shows:
        - New [candidate] version
        - With real score and coverage
        - Coverage delta vs baseline
        - User can inspect patch ops and run results
```

## New WorkbenchManager Methods

### promote_to_baseline(version_id)

```python
def promote_to_baseline(self, version_id: str) -> None:
    """Promote a version to baseline.

    The baseline is the reference version for coverage comparisons.

    Args:
        version_id: Version ID to promote to baseline
    """
```

**What it does:**
1. Clears previous baseline role (old baseline → "candidate")
2. Sets `_baseline_version_id = version_id`
3. Updates metadata role to "baseline" (preserves "checked_out" if set)

**Effect:**
- Coverage deltas recalculate vs new baseline
- Version list shows [baseline] badge on new version
- Inspector shows "Role: baseline"

### create_branch_version(parent_version_id, patch, label)

```python
def create_branch_version(
    self,
    parent_version_id: str,
    patch: Patch,
    label: str = "Branch"
) -> str | None:
    """Create a new version by applying a patch to a parent version.

    Args:
        parent_version_id: ID of parent version
        patch: Patch to apply
        label: Display label for new version

    Returns:
        New version ID or None if patch failed
    """
```

**What it does:**
1. Calls `spec_store.apply_patch(parent_id, patch, run_lint=True)`
2. Creates VersionMetadata with role="candidate"
3. Auto-runs parse to create RunArtifact
4. Returns new version ID

**Effect:**
- New version appears in version list
- Has real parse results and score
- Shows patch operations in Column 2 Patches tab
- Can be inspected, promoted, or branched further

## Test Patch Implementation

### Current Approach (PR#7)

For PR#7, the Branch button creates a **simple test patch** that adds a comment field:

```python
test_patch = Patch(
    ops=(
        InsertField(
            path=("types", first_type_name),
            index=-1,  # Append to end
            field_def={"name": "comment", "type": "str", "length": 64}
        ),
    ),
    description=f"Branch from {parent_label}: Add comment field"
)
```

**Rationale:**
- Demonstrates patch application workflow
- Creates a valid, parseable schema
- Shows version graph building
- Enables testing of promote/branch mechanics

**Future (PR#8):**
- Chat interface will allow LLM to propose patches
- User can review and apply suggested patches
- Test patch approach replaced with AI-driven suggestions

## SpecStore.apply_patch() Integration

### Patch Application Pipeline

```python
result = spec_store.apply_patch(
    parent_version_id=parent_id,
    patch=patch,
    run_lint=True
)
```

**Steps:**
1. **Validate patch**: Check all operations are well-formed
2. **Apply ops atomically**: Modify spec_dict (all succeed or all fail)
3. **Serialize**: Convert spec_dict back to YAML text
4. **Run lint**: Validate resulting schema
5. **Create SpecVersion**: Store with patch_applied reference
6. **Return PatchResult**: Success status and new version ID

**Failure cases:**
- Invalid patch operations
- Type/field not found
- Lint errors in resulting schema
- Returns `PatchResult(success=False, errors=...)`

## Acceptance Checklist

- [x] `promote_to_baseline()` method added to WorkbenchManager
- [x] `create_branch_version()` method added to WorkbenchManager
- [x] `_handle_promote()` implemented (promotes to baseline)
- [x] `_handle_branch()` implemented (creates branch with test patch)
- [x] Version list refreshes after promote/branch
- [x] Inspector updates after operations
- [x] New version auto-selected after branch
- [x] Coverage deltas recalculate after promote
- [x] Baseline badge updates correctly
- [x] No import errors
- [x] App loads successfully
- [x] Buttons functional (no placeholders)

## Manual Verification Steps

### Test 1: Promote Version to Baseline

```bash
python -m hexmap.app schema/ftm.yaml

# 1. Initialize workbench (30 sec)
Press "4"
Wait for initialization
Click version in Column 1

# 2. Note current baseline (10 sec)
Observe: [baseline] Current Schema (initial version)

# 3. Create a branch version (20 sec)
Click "Branch" button
Wait 1-2 seconds for parse to complete
Observe: New version appears "[candidate] Branch from Current Schema"

# 4. Promote the branch to baseline (20 sec)
Ensure branch version is selected
Click "Promote" button
Observe:
  - Version list updates
  - Branch version now shows [baseline]
  - Original version now shows [candidate]
  - Coverage deltas update (original now shows delta vs branch)

# Expected:
# - Promote works without errors
# - Baseline badge moves to promoted version
# - Deltas recalculate correctly
```

### Test 2: Branch from Version

```bash
# Continuing from Test 1...

# 1. Select any version (10 sec)
Click a version in Column 1

# 2. Create branch (20 sec)
Click "Branch" button
Wait for parse
Observe:
  - New version appears
  - Automatically selected
  - Shows in Column 1 with score and coverage

# 3. View branch details (30 sec)
Click "Patches & Changes" tab in Column 2
Observe:
  - Shows 1 patch operation: "insert_field: types.FirstType"
  - Click it to see details
  - Shows: "Add comment field"

Click "Runs" tab in Column 2
Observe:
  - Shows 1 run with coverage and score
  - Different from parent (comment field adds bytes)

# Expected:
# - Branch creates new version successfully
# - Patch visible in UI
# - Run shows different parse results
```

### Test 3: Multiple Branches

```bash
# 1. Create first branch (20 sec)
Select initial version
Click "Branch"
Note new version: "Branch from Current Schema"

# 2. Create second branch from same parent (20 sec)
Select initial version again
Click "Branch"
Note second version: "Branch from Current Schema" (again)

# 3. Create branch from branch (20 sec)
Select first branch version
Click "Branch"
Note third version: "Branch from Branch from Current Schema"

# 4. Observe version graph (20 sec)
Version list shows:
  - Initial (parent of 2 branches)
  - Branch 1 (child of initial, parent of branch 3)
  - Branch 2 (child of initial)
  - Branch 3 (child of branch 1)

# Expected:
# - Can branch from any version
# - Labels reflect lineage
# - Each has independent patch history
```

### Test 4: Promote and Compare

```bash
# 1. Create branch with better coverage (30 sec)
# (In practice, would edit schema to improve parse)
# For test, just create any branch

# 2. Note coverage delta (10 sec)
Observe: Δ: +X.X% or -X.X% vs baseline

# 3. Promote branch to baseline (10 sec)
Click "Promote"

# 4. Observe delta reversal (10 sec)
Original version now shows: Δ: (opposite sign)

# Expected:
# - Deltas flip when baseline changes
# - Scores stay the same (absolute values)
# - Comparison reference point updates
```

## Known Limitations (by design for PR#7)

- ✅ Branch creates test patch only (adds comment field)
- ✅ No patch creation UI yet (PR#8 will add Chat interface)
- ✅ No draft session tracking yet (simple immediate commits)
- ✅ No squash commit functionality yet (each branch is atomic)
- ✅ Cannot edit existing versions (immutable by design)
- ✅ Cannot delete versions (future enhancement)

## Code Quality

- ✅ Type hints throughout
- ✅ Docstrings for all new methods
- ✅ Error handling (version not found, patch failed)
- ✅ Graceful UI updates (no flicker)
- ✅ Auto-select new version after branch
- ✅ No modifications to Phase 7 core (SpecStore, Patch APIs unchanged)
- ✅ Minimal diff (150 lines total across 2 files)

## Testing

### Automated Tests
None for PR#7 - integration with live SpecStore and patch application. Future PRs may add integration tests.

### Manual Test Plan (Minimal)

**4-minute test:**

```bash
# 1. Start app (30 sec)
python -m hexmap.app schema/ftm.yaml

# 2. Initialize workbench (30 sec)
Press "4"
Wait for initialization

# 3. Test Branch (60 sec)
Click initial version
Click "Branch" button
Wait for new version to appear
Verify: New version appears with real score
Verify: Auto-selected

# 4. Test Promote (60 sec)
Ensure branch version selected
Click "Promote" button
Verify: Baseline badge moves to branch
Verify: Original shows delta vs new baseline

# 5. Test multiple branches (60 sec)
Select original version
Click "Branch" again
Verify: Second branch appears
Click first branch
Click "Branch"
Verify: Can branch from branch

# 6. Verify patch ops (30 sec)
Select any branch version
Click "Patches & Changes" tab
Verify: Shows insert_field operation
Click it
Verify: Inspector shows field details
```

**Pass criteria:**
- Branch creates new versions successfully
- Promote updates baseline correctly
- UI refreshes without errors
- New versions have real parse results
- Patch operations visible

## Design Notes

### Why Test Patch Instead of Full Patch UI?

**Problem:** PR#7 needs to demonstrate patch application, but full patch creation UI is complex.

**Solution:** Use simple test patch (add comment field) to prove the workflow.

**Benefits:**
- Demonstrates end-to-end patch application
- Tests SpecStore.apply_patch() integration
- Shows version graph building
- Validates parse re-running
- Enables testing of promote/branch mechanics

**Trade-off:** Not user-driven yet, but proves infrastructure works.

**PR#8 will add:** Chat interface for LLM-proposed patches, replacing test patch approach.

### Why Auto-Select After Branch?

**Problem:** After creating branch, user wants to inspect it immediately.

**Solution:** Auto-select new version in list after branch creation.

**Benefits:**
- Reduces clicks (don't need to hunt for new version)
- Immediate feedback (see parse results)
- Natural workflow (create → inspect → decide next action)

**Implementation:**
```python
for idx, vid in self._version_index_to_id.items():
    if vid == new_version_id:
        if self._version_list:
            self._version_list.highlighted = idx
        break
```

### Why Recalculate All Deltas on Promote?

**Problem:** When baseline changes, all version deltas need to update.

**Solution:** `_populate_version_list()` calls `get_coverage_delta_vs_baseline()` for each version.

**Benefits:**
- Deltas always reflect current baseline
- No stale data
- Simple implementation (no caching needed)

**Performance:** O(n) where n = number of versions. Acceptable for typical workbench (< 20 versions).

### Why role="candidate" for Branches?

**Roles:**
- **baseline**: Reference version for comparisons
- **candidate**: Alternative version being evaluated
- **draft**: Work in progress (not used yet in PR#7)
- **checked_out**: Working version for edits

**Branched versions are "candidate"** because:
- They're alternatives to the baseline
- They're being evaluated for promotion
- Clear semantic meaning

**In PR#8:** Draft role will be used for LLM-proposed patches before commit.

## Dependencies

**Phase 7 APIs used:**
- `SpecStore.apply_patch(parent_id, patch, run_lint)` - patch application
- `SpecStore.get(version_id)` - version retrieval
- `Patch(ops, description)` - patch construction
- `InsertField(path, index, field_def)` - patch operation
- All RunArtifact, scoring, and tool_host APIs (unchanged from PR#5)

**No new external dependencies.**

## Future PRs

- **PR#8:** Add Chat interface for patch proposal (LLM-driven spec iteration)
  - Replace test patch with AI suggestions
  - User review and approval workflow
  - Patch bundle proposals
  - Natural language spec iteration

## Performance Considerations

**Promote:**
- Updates metadata roles: O(1) for old + new baseline
- Refresh version list: O(n) where n = number of versions
- Instant for typical workbench (< 20 versions)

**Branch:**
- Patch application: O(m) where m = number of ops (typically 1-5)
- Parse run: O(k) where k = file size and max_records
- Limited to 1000 records (safety)
- Typically 1-2 seconds for branch creation

**Optimization Opportunities:**
- Cache parsed grammars (future enhancement)
- Incremental parsing (future enhancement)
- Currently not needed - performance is acceptable

## Success Metrics

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Promote functionality | Working | ✓ | ✅ |
| Branch functionality | Working | ✓ | ✅ |
| Version creation | Working | ✓ | ✅ |
| Patch application | Working | ✓ | ✅ |
| UI updates correctly | Yes | ✓ | ✅ |
| No regressions | All tabs work | ✓ | ✅ |
| Buttons functional | No placeholders | ✓ | ✅ |

All targets met!

## Diff Summary

**Lines changed:** 150 (70 in workbench_manager.py, 80 in agent_workbench.py)
**Files modified:** 2
**New files:** 0
**Deleted files:** 0

**Key changes:**
- Added Patch import to workbench_manager.py
- Added promote_to_baseline() method
- Added create_branch_version() method
- Added InsertField, Patch imports to agent_workbench.py
- Implemented _handle_promote() (was placeholder)
- Implemented _handle_branch() (was placeholder)
- UI refreshes after operations
- Auto-select new version after branch

## **Core Workbench Complete!** 🎉

After PR#7, the **core workbench functionality is complete**:

| Feature | Status | PR |
|---------|--------|-----|
| **Browse versions** | ✅ Complete | PR#3 |
| **View patch ops** | ✅ Complete | PR#4 |
| **View run results** | ✅ Complete | PR#5 |
| **View evidence** | ✅ Complete | PR#6 |
| **Promote to baseline** | ✅ Complete | PR#7 |
| **Create branches** | ✅ Complete | PR#7 |
| **Patch application** | ✅ Complete | PR#7 |

**Users can now:**
- ✅ Browse version history
- ✅ Inspect patches and runs
- ✅ See error locations in hex view
- ✅ Promote versions to baseline
- ✅ Create branch versions
- ✅ Build version graphs
- ✅ Compare versions by coverage and score

**Only remaining:** PR#8 (Chat interface for LLM-driven patch proposals)

## What's Next?

PR#8 will add the **Chat interface** for LLM-driven spec iteration:
- Natural language patch proposals
- LLM suggests spec improvements based on parse errors
- User reviews and applies suggested patches
- Replaces test patch with AI-driven suggestions
- Completes the vision of LLM-assisted binary format reverse engineering

This will be the final PR in the systematic build, completing the full Agent Workbench!
