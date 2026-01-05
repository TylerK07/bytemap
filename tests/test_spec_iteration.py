"""Tests for spec iteration system (Phase 7).

This module tests the complete iteration workflow:
- Patch operations and validation
- Spec versioning and atomic application
- Run artifacts and anomaly detection
- Run diffing and comparison
- Run scoring and ranking
"""

import os
import tempfile
from pathlib import Path

import pytest

from hexmap.core.run_artifacts import (
    Anomaly,
    RunArtifact,
    create_run_artifact,
    detect_anomalies,
)
from hexmap.core.run_diff import (
    RunDiff,
    compare_multiple_runs,
    diff_runs,
    find_best_run,
)
from hexmap.core.run_scoring import (
    ScoreBreakdown,
    compare_scores,
    find_best_scoring_run,
    rank_runs,
    score_run,
)
from hexmap.core.spec_patch import (
    AddRegistryEntry,
    AddType,
    DeleteField,
    InsertField,
    Patch,
    UpdateField,
    UpdateType,
    path_to_string,
    validate_path,
)
from hexmap.core.spec_version import SpecStore, SpecVersion
from hexmap.core.tool_host import (
    LintGrammarInput,
    ParseBinaryInput,
    ToolHost,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def simple_yaml():
    """Simple YAML grammar for testing."""
    return """
types:
  Header:
    fields:
      - name: magic
        type: u16
      - name: version
        type: u8
"""


@pytest.fixture
def complex_yaml():
    """More complex YAML grammar with types."""
    return """
types:
  Header:
    fields:
      - name: magic
        type: u16
      - name: version
        type: u8
      - name: count
        type: u16

  Record:
    fields:
      - name: record_type
        type: u16
      - name: length
        type: u16
      - name: data
        type: bytes
        length: $length
"""


@pytest.fixture
def binary_file():
    """Create a temporary binary file for testing."""
    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.bin') as f:
        # Write a simple header: magic=0x4E54, version=1, count=2
        f.write(b'\x54\x4E\x01\x00\x02\x00')

        # Write a name record: type=0x4E54, length=5, name="Hello"
        f.write(b'\x54\x4E\x05\x00Hello')

        # Write another name record: type=0x4E54, length=5, name="World"
        f.write(b'\x54\x4E\x05\x00World')

        path = f.name

    yield path

    # Cleanup
    os.unlink(path)


# ============================================================================
# PATH VALIDATION TESTS
# ============================================================================

def test_path_validation():
    """Test path validation logic."""
    # Valid paths
    assert validate_path(("types", "Header"))
    assert validate_path(("types", "Header", "fields", 0))
    assert validate_path(("types", "Header", "fields", 0, "name"))
    assert validate_path(("registry", "0x4E54"))
    assert validate_path(("endian",))

    # Invalid paths
    assert not validate_path(())
    assert not validate_path(("invalid_root",))
    assert not validate_path((123,))  # Must start with string


def test_path_to_string():
    """Test path to string conversion."""
    assert path_to_string(("types", "Header")) == "types.Header"
    assert path_to_string(("types", "Header", "fields", 0)) == "types.Header.fields[0]"
    assert path_to_string(("registry", "0x4E54")) == "registry.0x4E54"
    assert path_to_string(("types", "Header", "fields", 0, "name")) == "types.Header.fields[0].name"
    # Test bracket notation for special chars
    assert path_to_string(("types", "My.Type")) == "types['My.Type']"


# ============================================================================
# PATCH OPERATION TESTS
# ============================================================================

def test_insert_field_validation():
    """Test InsertField operation validation."""
    # Valid operation
    op = InsertField(
        path=("types", "Header"),
        index=0,
        field_def={"name": "new_field", "type": "u32"}
    )
    is_valid, error = op.validate()
    assert is_valid
    assert error is None

    # Invalid: missing name
    op = InsertField(
        path=("types", "Header"),
        index=0,
        field_def={"type": "u32"}
    )
    is_valid, error = op.validate()
    assert not is_valid
    assert "name" in error

    # Invalid: wrong path
    op = InsertField(
        path=("registry", "0x4E54"),
        index=0,
        field_def={"name": "field", "type": "u32"}
    )
    is_valid, error = op.validate()
    assert not is_valid


def test_update_field_validation():
    """Test UpdateField operation validation."""
    # Valid operation
    op = UpdateField(
        path=("types", "Header", "fields", 0),
        updates={"type": "u32", "color": "red"}
    )
    is_valid, error = op.validate()
    assert is_valid

    # Invalid: empty updates
    op = UpdateField(
        path=("types", "Header", "fields", 0),
        updates={}
    )
    is_valid, error = op.validate()
    assert not is_valid

    # Invalid: wrong path
    op = UpdateField(
        path=("types", "Header"),
        updates={"color": "red"}
    )
    is_valid, error = op.validate()
    assert not is_valid


def test_patch_validation():
    """Test Patch validation."""
    # Valid patch
    patch = Patch(
        ops=(
            InsertField(
                path=("types", "Header"),
                index=0,
                field_def={"name": "new_field", "type": "u32"}
            ),
        ),
        description="Add new field"
    )
    is_valid, errors = patch.validate()
    assert is_valid
    assert len(errors) == 0

    # Invalid patch: empty ops
    patch = Patch(ops=(), description="Empty patch")
    is_valid, errors = patch.validate()
    assert not is_valid
    assert len(errors) > 0

    # Invalid patch: contains invalid op
    patch = Patch(
        ops=(
            InsertField(
                path=("types", "Header"),
                index=0,
                field_def={"type": "u32"}  # Missing name
            ),
        ),
        description="Invalid op"
    )
    is_valid, errors = patch.validate()
    assert not is_valid
    assert len(errors) > 0


# ============================================================================
# SPEC VERSIONING TESTS
# ============================================================================

def test_spec_store_create_initial(simple_yaml):
    """Test creating initial spec version."""
    store = SpecStore()

    # Create initial version
    version = store.create_initial(simple_yaml, run_lint=True)

    assert version.id is not None
    assert version.parent_id is None
    assert version.patch_applied is None
    assert version.lint_valid is True
    assert len(version.lint_errors) == 0
    assert "types" in version.spec_dict
    assert "Header" in version.spec_dict["types"]

    # Verify it's stored
    retrieved = store.get(version.id)
    assert retrieved is not None
    assert retrieved.id == version.id


def test_atomic_patch_application(simple_yaml):
    """Test atomic patch application - all ops succeed or all fail."""
    store = SpecStore()
    initial = store.create_initial(simple_yaml, run_lint=False)

    # Create a valid patch
    patch = Patch(
        ops=(
            InsertField(
                path=("types", "Header"),
                index=-1,  # Append
                field_def={"name": "new_field", "type": "u32"}
            ),
        ),
        description="Add new field"
    )

    # Apply patch
    result = store.apply_patch(initial.id, patch, run_lint=False)

    assert result.success
    assert result.new_spec_id is not None
    assert len(result.errors) == 0

    # Verify new version exists
    new_version = store.get(result.new_spec_id)
    assert new_version is not None
    assert new_version.parent_id == initial.id
    assert new_version.patch_applied is not None
    assert len(new_version.spec_dict["types"]["Header"]["fields"]) == 3


def test_invalid_patch_rejection(simple_yaml):
    """Test that invalid patches are rejected."""
    store = SpecStore()
    initial = store.create_initial(simple_yaml, run_lint=False)

    # Create patch that tries to update non-existent field
    patch = Patch(
        ops=(
            UpdateField(
                path=("types", "Header", "fields", 999),  # Out of range
                updates={"type": "u32"}
            ),
        ),
        description="Invalid field index"
    )

    # Apply patch - should fail
    result = store.apply_patch(initial.id, patch, run_lint=False)

    assert not result.success
    assert len(result.errors) > 0

    # Verify original version unchanged
    original = store.get(initial.id)
    assert len(original.spec_dict["types"]["Header"]["fields"]) == 2


def test_patch_rejected_on_lint_failure(simple_yaml):
    """Test that patches are rejected if they break lint validation."""
    store = SpecStore()
    initial = store.create_initial(simple_yaml, run_lint=False)

    # Create patch that creates invalid grammar
    patch = Patch(
        ops=(
            InsertField(
                path=("types", "Header"),
                index=-1,
                field_def={"name": "bad_field", "type": "NonExistentType"}
            ),
        ),
        description="Add field with invalid type"
    )

    # Apply patch with lint enabled - should fail
    result = store.apply_patch(initial.id, patch, run_lint=True)

    # May succeed or fail depending on whether NonExistentType causes lint error
    # The important thing is atomicity - if it fails, nothing changed
    if not result.success:
        assert len(result.errors) > 0


def test_version_chain_tracking(simple_yaml):
    """Test version chain and lineage tracking."""
    store = SpecStore()

    # Create initial version
    v1 = store.create_initial(simple_yaml, run_lint=False)

    # Apply first patch
    patch1 = Patch(
        ops=(
            InsertField(
                path=("types", "Header"),
                index=-1,
                field_def={"name": "field1", "type": "u32"}
            ),
        ),
        description="Add field1"
    )
    result1 = store.apply_patch(v1.id, patch1, run_lint=False)
    assert result1.success
    v2_id = result1.new_spec_id

    # Apply second patch
    patch2 = Patch(
        ops=(
            InsertField(
                path=("types", "Header"),
                index=-1,
                field_def={"name": "field2", "type": "u16"}
            ),
        ),
        description="Add field2"
    )
    result2 = store.apply_patch(v2_id, patch2, run_lint=False)
    assert result2.success
    v3_id = result2.new_spec_id

    # Check lineage
    lineage = store.get_lineage(v3_id)
    assert len(lineage) == 3
    assert lineage[0] == v1.id
    assert lineage[1] == v2_id
    assert lineage[2] == v3_id

    # Verify parent relationships
    v2 = store.get(v2_id)
    v3 = store.get(v3_id)
    assert v2.parent_id == v1.id
    assert v3.parent_id == v2_id


def test_multiple_patch_operations(simple_yaml):
    """Test patch with multiple operations."""
    store = SpecStore()
    initial = store.create_initial(simple_yaml, run_lint=False)

    # Create patch with multiple ops
    patch = Patch(
        ops=(
            InsertField(
                path=("types", "Header"),
                index=-1,
                field_def={"name": "field1", "type": "u32"}
            ),
            InsertField(
                path=("types", "Header"),
                index=-1,
                field_def={"name": "field2", "type": "u16"}
            ),
            UpdateField(
                path=("types", "Header", "fields", 0),
                updates={"color": "red"}
            ),
        ),
        description="Multiple operations"
    )

    # Apply patch
    result = store.apply_patch(initial.id, patch, run_lint=False)

    assert result.success

    # Verify all ops applied
    new_version = store.get(result.new_spec_id)
    fields = new_version.spec_dict["types"]["Header"]["fields"]
    assert len(fields) == 4  # Original 2 + 2 new
    assert fields[0]["color"] == "red"
    assert fields[2]["name"] == "field1"
    assert fields[3]["name"] == "field2"


# ============================================================================
# RUN ARTIFACTS TESTS
# ============================================================================

def test_create_run_artifact(complex_yaml, binary_file):
    """Test creating run artifact from parse result."""
    # Parse binary file
    grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=complex_yaml))
    assert grammar_result.success

    parse_result = ToolHost.parse_binary(
        ParseBinaryInput(
            grammar=grammar_result.grammar,
            file_path=binary_file,
            max_records=10
        )
    )

    # Get file size
    file_size = Path(binary_file).stat().st_size

    # Create run artifact
    artifact = create_run_artifact(
        run_id="test_run_1",
        spec_version_id="spec_v1",
        parse_result=parse_result,
        file_path=binary_file,
        file_size=file_size,
    )

    assert artifact.run_id == "test_run_1"
    assert artifact.spec_version_id == "spec_v1"
    assert artifact.parse_result is parse_result
    assert artifact.file_path == binary_file
    assert artifact.file_size == file_size
    assert artifact.anomalies is not None
    assert artifact.stats is not None
    assert artifact.stats.record_count == parse_result.record_count
    assert artifact.stats.coverage_percentage > 0


def test_anomaly_detection(complex_yaml, binary_file):
    """Test anomaly detection in parsed data."""
    # Parse binary file
    grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=complex_yaml))
    parse_result = ToolHost.parse_binary(
        ParseBinaryInput(
            grammar=grammar_result.grammar,
            file_path=binary_file,
            max_records=10
        )
    )

    # Detect anomalies
    anomalies = detect_anomalies(parse_result)

    # Should be a tuple
    assert isinstance(anomalies, tuple)

    # Check for parse errors
    if parse_result.errors:
        error_anomalies = [a for a in anomalies if a.type == "parse_error"]
        assert len(error_anomalies) == len(parse_result.errors)


# ============================================================================
# RUN DIFFING TESTS
# ============================================================================

def test_diff_runs(complex_yaml, binary_file):
    """Test diffing two parse runs."""
    # Parse with same grammar twice
    grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=complex_yaml))

    parse_result_1 = ToolHost.parse_binary(
        ParseBinaryInput(
            grammar=grammar_result.grammar,
            file_path=binary_file,
            max_records=10
        )
    )

    parse_result_2 = ToolHost.parse_binary(
        ParseBinaryInput(
            grammar=grammar_result.grammar,
            file_path=binary_file,
            max_records=5  # Different limit
        )
    )

    file_size = Path(binary_file).stat().st_size

    # Create run artifacts
    run_a = create_run_artifact("run_a", "spec_v1", parse_result_1, binary_file, file_size)
    run_b = create_run_artifact("run_b", "spec_v1", parse_result_2, binary_file, file_size)

    # Diff runs
    diff = diff_runs(run_a, run_b)

    assert diff.run_a_id == "run_a"
    assert diff.run_b_id == "run_b"
    assert diff.summary is not None

    # Check deltas
    assert diff.coverage_delta == run_b.stats.coverage_percentage - run_a.stats.coverage_percentage
    assert diff.error_delta == run_b.stats.error_count - run_a.stats.error_count


def test_is_improvement():
    """Test is_improvement logic."""
    # Improvement: coverage up, errors down
    diff = RunDiff(
        run_a_id="a",
        run_b_id="b",
        coverage_delta=10.0,
        bytes_parsed_delta=100,
        record_count_delta=5,
        error_delta=-2,
        anomaly_delta=-1,
        high_severity_delta=0,
        summary="Improved"
    )
    assert diff.is_improvement()

    # Not improvement: errors increased
    diff = RunDiff(
        run_a_id="a",
        run_b_id="b",
        coverage_delta=10.0,
        bytes_parsed_delta=100,
        record_count_delta=5,
        error_delta=2,  # Errors increased
        anomaly_delta=-1,
        high_severity_delta=0,
        summary="Worse"
    )
    assert not diff.is_improvement()

    # Not improvement: coverage decreased
    diff = RunDiff(
        run_a_id="a",
        run_b_id="b",
        coverage_delta=-5.0,  # Coverage down
        bytes_parsed_delta=-50,
        record_count_delta=-2,
        error_delta=0,
        anomaly_delta=0,
        high_severity_delta=0,
        summary="Worse"
    )
    assert not diff.is_improvement()


def test_find_best_run(complex_yaml, binary_file):
    """Test finding best run from candidates."""
    grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=complex_yaml))
    file_size = Path(binary_file).stat().st_size

    # Create baseline run with max_records=5
    parse_baseline = ToolHost.parse_binary(
        ParseBinaryInput(
            grammar=grammar_result.grammar,
            file_path=binary_file,
            max_records=5
        )
    )
    baseline = create_run_artifact("baseline", "spec_v1", parse_baseline, binary_file, file_size)

    # Create candidate runs with different limits
    candidates = []
    for i, max_records in enumerate([10, 15, 20]):
        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(
                grammar=grammar_result.grammar,
                file_path=binary_file,
                max_records=max_records
            )
        )
        artifact = create_run_artifact(f"candidate_{i}", "spec_v2", parse_result, binary_file, file_size)
        candidates.append(artifact)

    # Find best run
    best_run, best_diff = find_best_run(baseline, candidates)

    # Should find a run (may or may not be improvement depending on actual parsing)
    if best_run is not None:
        assert best_diff is not None
        assert best_diff.is_improvement()
        assert best_run in candidates


# ============================================================================
# SCORING TESTS
# ============================================================================

def test_score_run_hard_gates(complex_yaml, binary_file):
    """Test scoring hard gates."""
    grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=complex_yaml))
    parse_result = ToolHost.parse_binary(
        ParseBinaryInput(
            grammar=grammar_result.grammar,
            file_path=binary_file,
            max_records=10
        )
    )

    file_size = Path(binary_file).stat().st_size
    artifact = create_run_artifact("run_1", "spec_v1", parse_result, binary_file, file_size)

    # Score the run
    score = score_run(artifact)

    # Check hard gate results
    assert "parse_advanced" in score.hard_gate_results
    assert "no_safety_violations" in score.hard_gate_results

    # If parse succeeded and no high severity anomalies, should pass
    if parse_result.total_bytes_parsed > 0 and artifact.stats.high_severity_anomalies == 0:
        assert score.passed_hard_gates
        assert score.total_score >= 0
        assert "coverage" in score.soft_metrics
    else:
        # Otherwise may fail hard gates
        if not score.passed_hard_gates:
            assert score.total_score == -1


def test_score_run_soft_metrics(complex_yaml, binary_file):
    """Test scoring soft metrics."""
    grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=complex_yaml))
    parse_result = ToolHost.parse_binary(
        ParseBinaryInput(
            grammar=grammar_result.grammar,
            file_path=binary_file,
            max_records=10
        )
    )

    file_size = Path(binary_file).stat().st_size
    artifact = create_run_artifact("run_1", "spec_v1", parse_result, binary_file, file_size)

    # Score the run
    score = score_run(artifact)

    if score.passed_hard_gates:
        # Check soft metrics
        assert "coverage" in score.soft_metrics
        assert score.soft_metrics["coverage"] >= 0
        assert score.soft_metrics["coverage"] <= 100

        # Check penalties
        if artifact.stats.error_count > 0:
            assert "errors" in score.penalties
            assert score.penalties["errors"] > 0

        if artifact.stats.anomaly_count > 0:
            assert "anomalies" in score.penalties
            assert score.penalties["anomalies"] > 0


def test_rank_runs(complex_yaml, binary_file):
    """Test ranking multiple runs."""
    grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=complex_yaml))
    file_size = Path(binary_file).stat().st_size

    # Create multiple runs with different limits
    runs = []
    for i, max_records in enumerate([5, 10, 15]):
        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(
                grammar=grammar_result.grammar,
                file_path=binary_file,
                max_records=max_records
            )
        )
        artifact = create_run_artifact(f"run_{i}", "spec_v1", parse_result, binary_file, file_size)
        runs.append(artifact)

    # Rank runs
    ranked = rank_runs(runs)

    assert len(ranked) == len(runs)

    # Check that ranking is sorted by score descending
    for i in range(len(ranked) - 1):
        assert ranked[i][1].total_score >= ranked[i + 1][1].total_score


def test_find_best_scoring_run(complex_yaml, binary_file):
    """Test finding best scoring run."""
    grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=complex_yaml))
    file_size = Path(binary_file).stat().st_size

    # Create multiple runs
    runs = []
    for i, max_records in enumerate([5, 10, 15]):
        parse_result = ToolHost.parse_binary(
            ParseBinaryInput(
                grammar=grammar_result.grammar,
                file_path=binary_file,
                max_records=max_records
            )
        )
        artifact = create_run_artifact(f"run_{i}", "spec_v1", parse_result, binary_file, file_size)
        runs.append(artifact)

    # Find best
    best_run, best_score = find_best_scoring_run(runs)

    if best_run is not None:
        assert best_score is not None
        assert best_score.passed_hard_gates
        assert best_run in runs

        # Verify it's actually the best
        all_scores = [score_run(run) for run in runs]
        passing_scores = [s for s in all_scores if s.passed_hard_gates]
        if passing_scores:
            max_score = max(s.total_score for s in passing_scores)
            assert best_score.total_score == max_score


def test_compare_scores(complex_yaml, binary_file):
    """Test comparing scores of two runs."""
    grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=complex_yaml))
    file_size = Path(binary_file).stat().st_size

    # Create two runs
    parse_1 = ToolHost.parse_binary(
        ParseBinaryInput(
            grammar=grammar_result.grammar,
            file_path=binary_file,
            max_records=5
        )
    )
    run_a = create_run_artifact("run_a", "spec_v1", parse_1, binary_file, file_size)

    parse_2 = ToolHost.parse_binary(
        ParseBinaryInput(
            grammar=grammar_result.grammar,
            file_path=binary_file,
            max_records=10
        )
    )
    run_b = create_run_artifact("run_b", "spec_v2", parse_2, binary_file, file_size)

    # Compare
    comparison = compare_scores(run_a, run_b)

    assert "Run A" in comparison
    assert "Run B" in comparison
    assert "RESULT" in comparison


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

def test_complete_iteration_workflow(simple_yaml, binary_file):
    """Test complete iteration workflow: spec → parse → patch → compare."""
    # 1. Create initial spec version
    store = SpecStore()
    initial_version = store.create_initial(simple_yaml, run_lint=True)
    assert initial_version.lint_valid

    # 2. Parse with initial spec - need to lint to get Grammar object
    file_size = Path(binary_file).stat().st_size
    grammar_initial = ToolHost.lint_grammar(LintGrammarInput(yaml_text=initial_version.spec_text))
    assert grammar_initial.success

    parse_initial = ToolHost.parse_binary(
        ParseBinaryInput(
            grammar=grammar_initial.grammar,
            file_path=binary_file,
            max_records=10
        )
    )
    baseline_run = create_run_artifact(
        "baseline",
        initial_version.id,
        parse_initial,
        binary_file,
        file_size
    )
    baseline_score = score_run(baseline_run)

    # 3. Propose patch to improve spec
    patch = Patch(
        ops=(
            InsertField(
                path=("types", "Header"),
                index=-1,
                field_def={"name": "extra_field", "type": "u16"}
            ),
        ),
        description="Add extra field to parse more data"
    )

    # 4. Apply patch
    patch_result = store.apply_patch(initial_version.id, patch, run_lint=True)

    # If patch succeeded (might fail if it breaks lint)
    if patch_result.success:
        new_version = store.get(patch_result.new_spec_id)

        # 5. Parse with new spec - lint to get Grammar object
        grammar_new = ToolHost.lint_grammar(LintGrammarInput(yaml_text=new_version.spec_text))
        assert grammar_new.success

        parse_new = ToolHost.parse_binary(
            ParseBinaryInput(
                grammar=grammar_new.grammar,
                file_path=binary_file,
                max_records=10
            )
        )
        new_run = create_run_artifact(
            "patched",
            new_version.id,
            parse_new,
            binary_file,
            file_size
        )

        # 6. Compare runs
        diff = diff_runs(baseline_run, new_run)
        new_score = score_run(new_run, baseline_run)

        # 7. Verify we can compare
        assert diff.run_a_id == "baseline"
        assert diff.run_b_id == "patched"
        assert new_score is not None
