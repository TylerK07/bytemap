# Spec Iteration Guide (Phase 7)

## Overview

The Spec Iteration system provides a **safe, auditable write surface** for LLM-driven binary analysis. It enables autonomous agents to iteratively improve binary grammar specifications through structured patches, atomic application, and automated comparison.

**Key Capabilities:**
- ✅ Structured patch operations (no raw YAML editing)
- ✅ Atomic patch application (all ops succeed or all fail)
- ✅ Version tracking with full lineage
- ✅ Anomaly detection in parse results
- ✅ Automated run comparison and diffing
- ✅ Deterministic scoring and ranking
- ✅ Complete auditability

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SPEC ITERATION SYSTEM                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐      ┌──────────────┐                    │
│  │   Spec       │      │    Run       │                    │
│  │  Patches     │      │  Artifacts   │                    │
│  │              │      │              │                    │
│  │ • Patch Ops  │      │ • Anomalies  │                    │
│  │ • Validation │      │ • Stats      │                    │
│  └──────┬───────┘      └──────┬───────┘                    │
│         │                     │                            │
│         v                     v                            │
│  ┌──────────────┐      ┌──────────────┐                    │
│  │   Spec       │      │    Run       │                    │
│  │ Versioning   │      │  Diffing     │                    │
│  │              │      │              │                    │
│  │ • SpecStore  │      │ • Comparison │                    │
│  │ • Atomic     │      │ • Scoring    │                    │
│  │   Apply      │      │ • Ranking    │                    │
│  └──────────────┘      └──────────────┘                    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                          │
                          v
         ┌─────────────────────────────────┐
         │      Tool Host (Phases 1-6)     │
         │  • lint_grammar                 │
         │  • parse_binary                 │
         │  • generate_spans               │
         │  • analyze_coverage             │
         │  • decode_field                 │
         │  • query_records                │
         └─────────────────────────────────┘
```

## Core Concepts

### 1. Patch Operations

Structured operations on spec AST instead of raw YAML manipulation.

**Available Operations:**
- `InsertField`: Add field to type's field list
- `UpdateField`: Modify existing field properties
- `DeleteField`: Remove field from type
- `AddType`: Add new type definition
- `UpdateType`: Update type properties
- `AddRegistryEntry`: Add registry entry

**Path-Based Addressing:**
Simple tuple paths for navigating spec structure:
```python
("types", "Header")                    # Type
("types", "Header", "fields", 0)       # Field
("types", "Header", "fields", 0, "name")  # Field property
```

### 2. Spec Versioning

Immutable snapshots with parent-child tracking create version lineage.

**Key Properties:**
- Each version has unique ID
- Versions are immutable (frozen dataclasses)
- Parent ID creates version graph
- Patches are auditable
- Lint validation on every version

### 3. Run Artifacts

Complete snapshot of parse run with quality metrics.

**Components:**
- Parse result from Tool Host
- Detected anomalies (absurd_length, field_overflow, etc.)
- Coverage statistics
- Error counts
- Tie to specific spec version

### 4. Run Diffing

Structured comparison showing deltas between runs.

**Metrics:**
- Coverage delta
- Error delta
- Anomaly delta
- Record count delta
- Improvement detection

### 5. Scoring

Deterministic scoring with hard gates and soft metrics.

**Hard Gates (must pass):**
- parse_advanced: Parser made progress
- no_safety_violations: No high severity anomalies

**Soft Metrics (0-100):**
- Coverage percentage
- Error penalties
- Anomaly penalties

## Module Reference

### spec_patch.py

**Patch Operations:**
```python
from hexmap.core.spec_patch import InsertField, Patch

# Create patch with single operation
patch = Patch(
    ops=(
        InsertField(
            path=("types", "Header"),
            index=-1,  # Append
            field_def={"name": "new_field", "type": "u32"}
        ),
    ),
    description="Add new field to Header"
)

# Validate before applying
is_valid, errors = patch.validate()
```

**Path Utilities:**
```python
from hexmap.core.spec_patch import path_to_string, validate_path

# Convert path to human-readable string
path_to_string(("types", "Header", "fields", 0))
# → "types.Header.fields[0]"

# Validate path structure
validate_path(("types", "Header"))  # → True
```

### spec_version.py

**Spec Store:**
```python
from hexmap.core.spec_version import SpecStore

# Create store
store = SpecStore()

# Create initial version
initial = store.create_initial(yaml_text, run_lint=True)

# Apply patch atomically
result = store.apply_patch(initial.id, patch, run_lint=True)

if result.success:
    new_version = store.get(result.new_spec_id)
else:
    print(f"Patch failed: {result.errors}")

# Track lineage
lineage = store.get_lineage(new_version.id)

# Diff specs
diff = store.diff_specs(initial.id, new_version.id)
```

### run_artifacts.py

**Run Artifacts:**
```python
from hexmap.core.run_artifacts import create_run_artifact
from hexmap.core.tool_host import ToolHost, ParseBinaryInput

# Parse binary
parse_result = ToolHost.parse_binary(
    ParseBinaryInput(
        grammar=grammar,
        file_path=binary_path,
        max_records=100
    )
)

# Create artifact with anomaly detection
artifact = create_run_artifact(
    run_id="run_1",
    spec_version_id=spec_version.id,
    parse_result=parse_result,
    file_path=binary_path,
    file_size=file_size
)

# Access stats
print(f"Coverage: {artifact.stats.coverage_percentage:.1f}%")
print(f"Anomalies: {artifact.stats.anomaly_count}")
print(f"High severity: {artifact.stats.high_severity_anomalies}")
```

### run_diff.py

**Run Diffing:**
```python
from hexmap.core.run_diff import diff_runs, find_best_run

# Compare two runs
diff = diff_runs(baseline_run, new_run)

print(f"Coverage delta: {diff.coverage_delta:+.1f}%")
print(f"Error delta: {diff.error_delta:+d}")
print(f"Is improvement: {diff.is_improvement()}")

# Find best among candidates
best_run, best_diff = find_best_run(baseline_run, candidate_runs)
```

### run_scoring.py

**Scoring:**
```python
from hexmap.core.run_scoring import score_run, find_best_scoring_run

# Score single run
score = score_run(run, baseline=None)

print(f"Total score: {score.total_score:.1f}/100")
print(f"Passed gates: {score.passed_hard_gates}")
print(f"Summary: {score.summary}")

# Find best scoring run
best_run, best_score = find_best_scoring_run(candidates, baseline)
```

## Complete Workflow

### Step 1: Create Initial Spec

```python
from hexmap.core.spec_version import SpecStore

store = SpecStore()

initial_yaml = """
types:
  Header:
    fields:
      - name: magic
        type: u16
      - name: version
        type: u8
"""

initial_version = store.create_initial(initial_yaml, run_lint=True)
```

### Step 2: Parse and Create Baseline

```python
from hexmap.core.tool_host import ToolHost, LintGrammarInput, ParseBinaryInput
from hexmap.core.run_artifacts import create_run_artifact
from pathlib import Path

# Lint to get Grammar object
grammar_result = ToolHost.lint_grammar(
    LintGrammarInput(yaml_text=initial_version.spec_text)
)

# Parse binary
parse_result = ToolHost.parse_binary(
    ParseBinaryInput(
        grammar=grammar_result.grammar,
        file_path=binary_file,
        max_records=100
    )
)

# Create baseline artifact
file_size = Path(binary_file).stat().st_size
baseline_run = create_run_artifact(
    run_id="baseline",
    spec_version_id=initial_version.id,
    parse_result=parse_result,
    file_path=binary_file,
    file_size=file_size
)
```

### Step 3: Propose Candidate Patches

```python
from hexmap.core.spec_patch import InsertField, Patch

# Candidate 1: Add single field
patch_1 = Patch(
    ops=(
        InsertField(
            path=("types", "Header"),
            index=-1,
            field_def={"name": "flags", "type": "u16"}
        ),
    ),
    description="Add flags field"
)

# Candidate 2: Add multiple fields
patch_2 = Patch(
    ops=(
        InsertField(
            path=("types", "Header"),
            index=-1,
            field_def={"name": "flags", "type": "u16"}
        ),
        InsertField(
            path=("types", "Header"),
            index=-1,
            field_def={"name": "count", "type": "u8"}
        ),
    ),
    description="Add flags and count fields"
)

patches = [patch_1, patch_2]
```

### Step 4: Apply Patches and Parse

```python
candidate_runs = []

for i, patch in enumerate(patches, 1):
    # Apply patch
    result = store.apply_patch(initial_version.id, patch, run_lint=True)

    if result.success:
        new_version = store.get(result.new_spec_id)

        # Parse with new spec
        grammar_new = ToolHost.lint_grammar(
            LintGrammarInput(yaml_text=new_version.spec_text)
        )

        if grammar_new.success:
            parse_new = ToolHost.parse_binary(
                ParseBinaryInput(
                    grammar=grammar_new.grammar,
                    file_path=binary_file,
                    max_records=100
                )
            )

            run = create_run_artifact(
                run_id=f"candidate_{i}",
                spec_version_id=new_version.id,
                parse_result=parse_new,
                file_path=binary_file,
                file_size=file_size
            )

            candidate_runs.append(run)
```

### Step 5: Compare and Score

```python
from hexmap.core.run_diff import diff_runs
from hexmap.core.run_scoring import score_run

for run in candidate_runs:
    # Diff against baseline
    diff = diff_runs(baseline_run, run)

    # Score
    score = score_run(run, baseline_run)

    print(f"Run {run.run_id}:")
    print(f"  Diff: {diff.summary}")
    print(f"  Score: {score.total_score:.1f}/100")
    print(f"  Improvement: {diff.is_improvement()}")
```

### Step 6: Select Best

```python
from hexmap.core.run_diff import find_best_run
from hexmap.core.run_scoring import find_best_scoring_run

# By diff criteria
best_by_diff, best_diff = find_best_run(baseline_run, candidate_runs)

# By scoring
best_by_score, best_score = find_best_scoring_run(candidate_runs, baseline_run)

if best_by_score:
    print(f"Best candidate: {best_by_score.run_id}")
    print(f"Score: {best_score.total_score:.1f}/100")
    print(f"Coverage: {best_by_score.stats.coverage_percentage:.1f}%")
```

## LLM Integration

### Agent Function Template

```python
def agent_improve_spec(
    current_spec_yaml: str,
    binary_file: str,
    max_iterations: int = 5
) -> dict:
    """Autonomous agent function for spec improvement.

    Args:
        current_spec_yaml: Current spec YAML
        binary_file: Path to binary file
        max_iterations: Max improvement iterations

    Returns:
        Dict with best spec, scores, and audit trail
    """
    from pathlib import Path
    from hexmap.core.spec_version import SpecStore
    from hexmap.core.run_artifacts import create_run_artifact
    from hexmap.core.run_scoring import score_run, find_best_scoring_run
    from hexmap.core.spec_patch import Patch, InsertField
    from hexmap.core.tool_host import ToolHost, LintGrammarInput, ParseBinaryInput

    store = SpecStore()
    file_size = Path(binary_file).stat().st_size

    # Create initial version
    current_version = store.create_initial(current_spec_yaml, run_lint=True)

    # Parse with current spec
    grammar = ToolHost.lint_grammar(LintGrammarInput(yaml_text=current_version.spec_text))
    parse = ToolHost.parse_binary(
        ParseBinaryInput(
            grammar=grammar.grammar,
            file_path=binary_file,
            max_records=100
        )
    )

    baseline = create_run_artifact(
        "baseline", current_version.id, parse, binary_file, file_size
    )
    baseline_score = score_run(baseline)

    best_version = current_version
    best_score = baseline_score

    for iteration in range(max_iterations):
        # Agent proposes candidate patches
        # (In real system, LLM would generate these based on parse results)
        candidates = agent_propose_patches(best_version, baseline)

        # Apply and evaluate
        candidate_runs = []
        for patch in candidates:
            result = store.apply_patch(best_version.id, patch, run_lint=True)
            if result.success:
                new_version = store.get(result.new_spec_id)
                grammar = ToolHost.lint_grammar(
                    LintGrammarInput(yaml_text=new_version.spec_text)
                )
                if grammar.success:
                    parse = ToolHost.parse_binary(
                        ParseBinaryInput(
                            grammar=grammar.grammar,
                            file_path=binary_file,
                            max_records=100
                        )
                    )
                    run = create_run_artifact(
                        f"iter{iteration}_candidate", new_version.id,
                        parse, binary_file, file_size
                    )
                    candidate_runs.append(run)

        # Find best
        if candidate_runs:
            best_run, score = find_best_scoring_run(candidate_runs, baseline)
            if best_run and score.total_score > best_score.total_score:
                best_version = store.get(best_run.spec_version_id)
                best_score = score
                baseline = best_run
            else:
                break  # No improvement
        else:
            break

    return {
        "best_spec_yaml": best_version.spec_text,
        "best_spec_id": best_version.id,
        "final_score": best_score.total_score,
        "coverage": baseline.stats.coverage_percentage,
        "lineage": store.get_lineage(best_version.id)
    }
```

## Safety Guarantees

### Atomic Application

Patches are applied atomically - all operations succeed or all fail:

```python
# If any operation fails, no changes are made
patch = Patch(
    ops=(
        InsertField(...),  # OK
        UpdateField(...),  # FAILS (field doesn't exist)
        DeleteField(...),  # Never executed
    )
)

result = store.apply_patch(parent_id, patch)
# result.success = False
# Original spec unchanged
```

### Lint Validation

Patches are rejected if they break grammar rules:

```python
patch = Patch(
    ops=(
        InsertField(
            path=("types", "Header"),
            field_def={"name": "bad", "type": "NonExistentType"}
        ),
    )
)

result = store.apply_patch(parent_id, patch, run_lint=True)
# result.success = False
# result.errors = ["Lint failed: Unknown type 'NonExistentType'"]
```

### Immutability

All artifacts are immutable (frozen dataclasses):

```python
run_artifact.stats.coverage_percentage = 99.0  # ❌ Error: frozen
patch.description = "Changed"  # ❌ Error: frozen
```

### Auditability

Complete audit trail for every change:

```python
# Every version tracks its parent
version.parent_id  # → ID of parent

# Every version records applied patch
version.patch_applied  # → Patch object

# Full lineage from root
lineage = store.get_lineage(version_id)  # → [root_id, ..., version_id]

# Detailed diff
diff = store.diff_specs(old_id, new_id)
# → Lists all changes
```

## Performance Considerations

### Memory

- SpecStore keeps all versions in memory
- For large iteration sessions, consider persisting to disk
- Each RunArtifact includes full ParseResult (can be large)

### Optimization Tips

1. **Limit max_records** during iteration:
   ```python
   ParseBinaryInput(..., max_records=100)  # Don't parse entire file
   ```

2. **Skip lint for internal iterations**:
   ```python
   store.apply_patch(parent_id, patch, run_lint=False)  # Faster
   ```

3. **Reuse Grammar objects**:
   ```python
   grammar = ToolHost.lint_grammar(...)
   # Reuse for multiple parses
   ```

## Testing

Run Phase 7 tests:
```bash
pytest tests/test_spec_iteration.py -v
```

**Test Coverage:**
- 22 comprehensive tests
- Path validation
- Patch operations
- Atomic application
- Version tracking
- Anomaly detection
- Run diffing
- Scoring
- Complete workflow

## Demo Script

Run the demo to see complete examples:
```bash
python demo_spec_iteration.py
```

**Examples Included:**
1. Basic iteration workflow
2. Version lineage tracking
3. Detailed score breakdown

## Related Documentation

- `TOOL_HOST_STATUS.md` - Tool Host (Phases 1-6) overview
- `TOOL_HOST_IMPLEMENTATION.md` - Tool Host technical details
- `ARCHITECTURE.md` - Overall system architecture
- `YAML_GRAMMAR_REFERENCE.md` - YAML grammar syntax

## Summary

Phase 7 provides a **complete write surface** for LLM-driven spec iteration:

✅ **Safe:** Structured patches, atomic application, lint validation
✅ **Auditable:** Full version tracking, diff reports, lineage
✅ **Deterministic:** Same inputs → same outputs
✅ **Typed:** Explicit input/output schemas
✅ **Tested:** 22 comprehensive tests
✅ **Documented:** Complete guide and examples

**Ready for production LLM integration.**
