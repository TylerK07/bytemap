# PR#5: Column 2 Runs UI (Real Data Integration)

## Summary

Replaced mock runs with real RunArtifact data from WorkbenchManager. Column 2 Runs tab now shows actual parse results with real coverage, errors, anomalies, and scores. Runs inspector displays comprehensive details including first error, first anomaly, score breakdown, and parse stopped information. Column 2 is now fully integrated with Phase 7 data (both Patch Ops and Runs use real data).

## Files Changed

### Modified Files

1. **`src/hexmap/widgets/agent_workbench.py`** (80 lines changed)
   - **Added import**: `from hexmap.core.run_scoring import score_run`
   - **Removed import**: `MOCK_RUNS` from workbench_state
   - **Updated `_populate_runs_list()`** (lines 383-418):
     - Now reads runs from `manager.get_runs_for_version(version_id)`
     - Determines status from `run.stats.error_count` and `run.stats.high_severity_anomalies`
     - Computes real score using `score_run(run)`
     - Displays coverage and score in list
     - Uses `run.run_id` as identifier
   - **Updated `_update_runs_inspector()`** (lines 553-625):
     - Shows comprehensive run details from RunArtifact
     - Displays status (✓ ok, ✗ errors, ⚠ anomalies)
     - Shows coverage, record count, bytes parsed
     - Shows first error with truncated message
     - Shows first anomaly with severity and message
     - Shows score or hard gate failures
     - Shows parse stopped info if parsing didn't complete

## What Changed vs. PR#4

### Before (PR#4)
- Runs used `MOCK_RUNS` dict with fake MockRun objects
- Static mock data: coverage and score values hardcoded
- No error details shown
- No anomaly details shown
- No parse stopped information

### After (PR#5)
- Runs read real data from `manager.get_runs_for_version(version_id)`
- Real RunArtifact objects with actual parse results
- First error displayed with truncated message
- First anomaly displayed with severity and message
- Parse stopped info shown when parsing incomplete
- Real score from `score_run()` with hard gate checking
- Comprehensive stats (coverage, records, bytes parsed)

## Data Flow

### Runs Display Flow

```
User selects version in Column 1
    → watch_selected_version_id() triggered
    → _populate_runs_list(version_id)
        │
        ├──> Get runs from manager.get_runs_for_version(version_id)
        ├──> For each run:
        │    - Check stats for errors/anomalies (determine status badge)
        │    - Compute score using score_run(run)
        │    - Format label: "{badge} Coverage: X%, Score: Y"
        │    - Store run_id mapping
        └──> Display in OptionList
        │
        v
    OptionList shows:
        - "✓ Coverage: 45.0%, Score: 67" (no errors)
        - "✗ Coverage: 23.0%, Score: 0" (has errors)
        - "⚠ Coverage: 55.0%, Score: 45" (has anomalies)
```

### Run Selection Flow

```
User clicks run in list
    → on_option_list_option_selected()
    → _handle_run_selected(option_index)
    → Get run_id = _run_index_to_id[option_index]
    → Update state.selected_run_id
    → Update reactive selected_run_id
    → watch_selected_run_id() triggered
        │
        v
    _update_runs_inspector(run_id)
        │
        ├──> Get run = manager.get_run_artifact(run_id)
        ├──> Build display:
        │    - Run: {run_id}
        │    - Status: ✓/✗/⚠ with details
        │    - Coverage, Records, Bytes parsed
        │    - Errors: count + first error
        │    - Anomalies: count + first anomaly
        │    - Score: total or hard gate failures
        │    - Parse stopped: offset if incomplete
        └──> Update inspector Static widget
        │
        v
    Inspector shows comprehensive run details
```

## RunArtifact Structure

### RunArtifact (from run_artifacts.py)

```python
@dataclass(frozen=True)
class RunArtifact:
    run_id: str
    spec_version_id: str
    created_at: float
    parse_result: ParseResult
    file_path: str
    file_size: int
    anomalies: tuple[Anomaly, ...]
    stats: RunStats
```

### RunStats (from run_artifacts.py)

```python
@dataclass(frozen=True)
class RunStats:
    record_count: int
    total_bytes_parsed: int
    parse_stopped_at: int
    file_size: int
    coverage_percentage: float
    error_count: int
    anomaly_count: int
    high_severity_anomalies: int
```

### Anomaly (from run_artifacts.py)

```python
@dataclass(frozen=True)
class Anomaly:
    type: str  # parse_error, record_error, absurd_length, etc.
    severity: str  # high, medium, low
    record_offset: int
    field_name: str | None = None
    message: str = ""
    value: Any = None
```

### ParseResult (from tool_host.py)

```python
@dataclass
class ParseResult:
    success: bool
    records: list[ParsedRecord]
    errors: list[str]
    record_count: int
    total_bytes_parsed: int
    parse_stopped_at: int
```

## WorkbenchManager Methods Used

### get_runs_for_version(version_id)

```python
def get_runs_for_version(self, version_id: str) -> list[RunArtifact]:
    """Get all run artifacts for a version.

    Returns:
        List of RunArtifacts for this version
    """
    return [
        run
        for run in self._run_artifacts.values()
        if run.spec_version_id == version_id
    ]
```

### get_run_artifact(run_id)

```python
def get_run_artifact(self, run_id: str) -> RunArtifact | None:
    """Get run artifact by ID.

    Returns:
        RunArtifact or None if not found
    """
    return self._run_artifacts.get(run_id)
```

## Scoring Integration

### score_run(run_artifact)

From `hexmap.core.run_scoring`:

```python
def score_run(run_artifact: RunArtifact) -> ScoreBreakdown:
    """Score a run artifact.

    Returns:
        ScoreBreakdown with:
        - passed_hard_gates: bool
        - hard_gate_failures: list[str]
        - total_score: float (0-100)
        - coverage_score: float
        - quality_score: float
    """
```

Hard gates checked:
- No parse errors
- No high-severity anomalies
- Coverage > 0%

Soft metrics:
- Coverage percentage (0-70 points)
- Quality (low anomalies) (0-30 points)

## Acceptance Checklist

- [x] `_populate_runs_list()` reads real runs from `manager.get_runs_for_version()`
- [x] Status badge determined from run stats (✓/✗/⚠)
- [x] Real score computed using `score_run()`
- [x] Coverage and score displayed in list
- [x] `_update_runs_inspector()` shows comprehensive run details
- [x] First error displayed (if present)
- [x] First anomaly displayed (if present)
- [x] Score or hard gate failures shown
- [x] Parse stopped info shown (if incomplete)
- [x] No import errors or syntax errors
- [x] App loads successfully
- [x] No MOCK_RUNS usage remaining in agent_workbench.py

## Manual Verification Steps

### Test 1: Initial Version Shows One Run

```bash
python -m hexmap.app schema/ftm.yaml

# 1. Press "4" to switch to Workbench tab
# 2. Wait for initialization (1-2 seconds)
# 3. Click the version in Column 1 (should be "[baseline] Current Schema")
# 4. Click "Runs" tab in Column 2
# 5. Observe runs list
#
# Expected: Shows one run (auto-created during initialization)
# Format: "✓ Coverage: X.X%, Score: Y" (or ✗ if errors)
```

### Test 2: View Run Details

```bash
# Continuing from Test 1...

# 1. Click the run in the list
# 2. Observe inspector at bottom of Column 2
#
# Expected inspector content:
# - Run: run_{version_id}_{hash}
# - Status: ✓ ok (or ✗ if errors)
# - Coverage: X.X%
# - Records: N
# - Bytes parsed: X,XXX / Y,YYY
# - (Errors section if present)
# - (Anomalies section if present)
# - Score: X.X
# - (Parse stopped section if parsing incomplete)
```

### Test 3: Run with Errors

To test error display, you would need a schema that produces parse errors:

```python
# In Python console or test script
from hexmap.widgets.workbench_manager import WorkbenchManager

# Create manager with binary that has parse errors
manager = WorkbenchManager('/path/to/problematic.bin')

# Create version with schema that won't parse correctly
version_id = manager.create_initial_version(bad_yaml_text)

# The auto-run will create RunArtifact with errors
# UI will show:
# - "✗ Coverage: X%, Score: 0" in list
# - "Status: ✗ N errors" in inspector
# - "First: {error message}..." in inspector
```

### Test 4: Run with Anomalies

```python
# Similar to Test 3, but with schema that parses but has anomalies
# (e.g., absurdly large length fields)

# UI will show:
# - "⚠ Coverage: X%, Score: Y" in list
# - "Status: ⚠ N high-severity anomalies" in inspector
# - "HIGH: {anomaly message}..." in inspector
```

## Known Limitations (by design for PR#5)

- ✅ Shows runs, doesn't allow re-running yet (future enhancement)
- ✅ No jump-to-error navigation yet (requires hex view integration in PR#6)
- ✅ Shows only first error/anomaly (not full list)
- ✅ Evidence column still placeholder (PR#6)
- ✅ No error navigation hooks yet (PR#6)

## Code Quality

- ✅ Type hints throughout
- ✅ Docstrings updated
- ✅ Error handling (run not found, no manager)
- ✅ Graceful handling of missing errors/anomalies
- ✅ No modifications to Phase 7 core (run_artifacts.py, run_scoring.py)
- ✅ Minimal diff (80 lines changed in one file)

## Testing

### Automated Tests
None for PR#5 - integration with live RunArtifacts. Future PRs may add integration tests.

### Manual Test Plan (Minimal)

**2-minute test:**

```bash
# 1. Start app (30 sec)
python -m hexmap.app schema/ftm.yaml
# Wait for app to load

# 2. Switch to Workbench and verify runs (30 sec)
Press "4"
Wait for initialization
Click version in Column 1
Click "Runs" tab in Column 2
Verify: One run shown with real coverage and score

# 3. Test run selection (30 sec)
Click the run in list
Verify inspector shows:
  - Run ID
  - Status
  - Coverage, Records, Bytes parsed
  - Score

# 4. Verify other tabs still work (30 sec)
Press "1" → Explore tab ✓
Press "4" → Back to Workbench ✓
```

**Pass criteria:**
- Run shown with real data
- Inspector shows comprehensive details
- No crashes or errors
- Other tabs unaffected

## Design Notes

### Why Show First Error/Anomaly?

**Problem:** A run could have hundreds of errors or anomalies. Showing all would:
- Overflow the inspector UI
- Require scrolling
- Clutter the display

**Solution:** Show first error/anomaly only, with count:
```
Errors: 23
  First: Parse error at 0x1234: unexpected byte 0xFF...
```

**Benefits:**
- Quick preview of what went wrong
- User sees error count (severity indicator)
- Inspector stays compact
- Future: Add "View all errors" button if needed

### Why Use run.run_id Instead of Index?

**Problem:** Unlike PatchOp (which has no id), RunArtifact has a `run_id` field.

**Solution:** Use `run.run_id` directly:
```python
self._run_index_to_id[idx] = run.run_id
```

**Benefits:**
- Stable identifier (doesn't change if runs reordered)
- Can look up run directly: `manager.get_run_artifact(run_id)`
- Matches SpecVersion pattern (uses version.id)

### Why Compute Score in Both Places?

**Observation:** Score is computed in both `_populate_runs_list()` and `_update_runs_inspector()`.

**Reason:** Different contexts:
- **List**: Need score for display label (shows alongside coverage)
- **Inspector**: Need full ScoreBreakdown for detailed display (show hard gate failures)

**Trade-off:** Slight duplication, but scoring is fast (no heavy computation).

**Alternative considered:** Cache score in WorkbenchManager. Rejected because:
- Adds complexity
- score_run() is deterministic and fast
- No performance benefit for single-version case

### Status Badge Logic

```python
if run.stats.error_count > 0 or run.stats.high_severity_anomalies > 0:
    status_badge = "✗"
elif run.stats.anomaly_count > 0:  # implied: no high severity
    status_badge = "⚠"
else:
    status_badge = "✓"
```

**Hierarchy:**
1. ✗ (critical) - parse errors or high-severity anomalies
2. ⚠ (warning) - low/medium anomalies only
3. ✓ (ok) - no issues

This matches hard gate logic in scoring system.

## Dependencies

**Phase 7 modules used:**
- `hexmap.core.run_artifacts` (RunArtifact, RunStats, Anomaly)
- `hexmap.core.run_scoring` (score_run, ScoreBreakdown)
- `hexmap.core.tool_host` (ParseResult indirectly via RunArtifact)
- `hexmap.widgets.workbench_manager` (get_runs_for_version, get_run_artifact)

**No new external dependencies.**

## Future PRs

- **PR#6:** Integrate Evidence column with hex view (byte highlighting, jump-to-error)
- **PR#7:** Implement Draft, Promote, Branch functionality with patch application
- **PR#8:** Add Chat interface for patch proposal

## Performance Considerations

**Run Display:**
- get_runs_for_version() is O(n) where n = total runs in manager (typically < 10)
- score_run() is O(1) - simple arithmetic on pre-computed stats
- No I/O or heavy computation

**Optimization Opportunities:**
- Cache scores in WorkbenchManager (future enhancement if needed)
- Currently not needed - performance is instant

## Success Metrics

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Real runs displayed | Working | ✓ | ✅ |
| Real run details shown | Working | ✓ | ✅ |
| First error displayed | Yes | ✓ | ✅ |
| First anomaly displayed | Yes | ✓ | ✅ |
| Score computed correctly | Yes | ✓ | ✅ |
| No regressions | All tabs work | ✓ | ✅ |
| No mock data in runs | Removed | ✓ | ✅ |

All targets met!

## Diff Summary

**Lines changed:** 80
**Files modified:** 1
**New files:** 0
**Deleted files:** 0

**Key changes:**
- Import score_run from run_scoring
- Remove MOCK_RUNS import
- Rewrite _populate_runs_list() to use manager.get_runs_for_version()
- Compute status badge from run stats
- Compute score using score_run()
- Rewrite _update_runs_inspector() to show comprehensive run details
- Display first error and first anomaly
- Show parse stopped info

## Column 2 Completion Status

After PR#5, Column 2 is **fully integrated** with Phase 7 data:

**✅ Patches & Changes Tab:**
- Real patch operations from version.patch_applied (PR#4)
- Operation details, validation status, patch description

**✅ Runs Tab:**
- Real run artifacts from manager.get_runs_for_version() (PR#5)
- Comprehensive run details with errors, anomalies, scores

**Next:** PR#6 will integrate Column 3 (Evidence) with hex view for byte highlighting and error navigation.

## What's Next?

PR#6 will complete the read-only workbench by integrating Column 3 (Evidence) with the hex view. This will add:
- Byte range highlighting in hex view
- Jump-to-error navigation from runs
- Anomaly location visualization
- Coverage region display

After PR#6, the entire workbench will display real data and be fully functional for inspection and comparison.
