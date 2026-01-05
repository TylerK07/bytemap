"""Demo script for spec iteration system (Phase 7).

This demonstrates the complete workflow for LLM-driven binary analysis:
1. Load initial spec version
2. Parse binary file
3. Propose candidate patches
4. Apply patches atomically
5. Compare parse runs
6. Score and rank candidates
7. Select best improvement

Usage:
    python demo_spec_iteration.py
"""

import tempfile
from pathlib import Path

from hexmap.core.run_artifacts import create_run_artifact
from hexmap.core.run_diff import diff_runs, find_best_run, format_diff_report
from hexmap.core.run_scoring import (
    compare_scores,
    find_best_scoring_run,
    format_score_report,
    score_run,
)
from hexmap.core.spec_patch import InsertField, Patch, UpdateField
from hexmap.core.spec_version import SpecStore
from hexmap.core.tool_host import (
    LintGrammarInput,
    ParseBinaryInput,
    ToolHost,
)


def create_test_binary() -> str:
    """Create a test binary file for demonstration.

    Binary structure:
    - Header (6 bytes): magic=0x4D42 (BM), version=1, flags=0x0003
    - Record 1 (8 bytes): type=0x0001, length=4, data=[0x01, 0x02, 0x03, 0x04]
    - Record 2 (10 bytes): type=0x0002, length=6, data=[0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF]
    - Footer (4 bytes): checksum=0xDEADBEEF
    Total: 28 bytes
    """
    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.bin') as f:
        # Header
        f.write(b'\x42\x4D')  # magic "BM"
        f.write(b'\x01')      # version
        f.write(b'\x03\x00')  # flags
        f.write(b'\x02')      # record_count

        # Record 1
        f.write(b'\x01\x00')  # type
        f.write(b'\x04\x00')  # length
        f.write(b'\x01\x02\x03\x04')  # data

        # Record 2
        f.write(b'\x02\x00')  # type
        f.write(b'\x06\x00')  # length
        f.write(b'\xAA\xBB\xCC\xDD\xEE\xFF')  # data

        # Footer
        f.write(b'\xEF\xBE\xAD\xDE')  # checksum

        return f.name


def example_1_basic_workflow():
    """Example 1: Complete iteration workflow from scratch."""
    print("=" * 80)
    print("EXAMPLE 1: Basic Iteration Workflow")
    print("=" * 80)
    print()

    # Create test binary
    binary_file = create_test_binary()
    file_size = Path(binary_file).stat().st_size
    print(f"Created test binary: {binary_file} ({file_size} bytes)")
    print()

    # 1. Define initial spec (incomplete - only parses header)
    initial_yaml = """
types:
  Header:
    fields:
      - name: magic
        type: u16
      - name: version
        type: u8
"""

    print("=" * 80)
    print("STEP 1: Create Initial Spec Version")
    print("=" * 80)
    print()
    print("Initial YAML:")
    print(initial_yaml)

    # Create spec store and initial version
    store = SpecStore()
    initial_version = store.create_initial(initial_yaml, run_lint=True)

    print(f"Created spec version: {initial_version.id}")
    print(f"Lint valid: {initial_version.lint_valid}")
    print()

    # 2. Parse with initial spec
    print("=" * 80)
    print("STEP 2: Parse Binary with Initial Spec")
    print("=" * 80)
    print()

    # Lint to get Grammar object
    grammar_result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=initial_version.spec_text))
    assert grammar_result.success

    parse_initial = ToolHost.parse_binary(
        ParseBinaryInput(
            grammar=grammar_result.grammar,
            file_path=binary_file,
            max_records=100
        )
    )

    baseline_run = create_run_artifact(
        run_id="baseline_run",
        spec_version_id=initial_version.id,
        parse_result=parse_initial,
        file_path=binary_file,
        file_size=file_size
    )

    print(f"Records parsed: {baseline_run.stats.record_count}")
    print(f"Bytes parsed: {baseline_run.stats.total_bytes_parsed}/{file_size}")
    print(f"Coverage: {baseline_run.stats.coverage_percentage:.1f}%")
    print(f"Errors: {baseline_run.stats.error_count}")
    print(f"Anomalies: {baseline_run.stats.anomaly_count}")
    print()

    # Score baseline
    baseline_score = score_run(baseline_run)
    print(f"Baseline score: {baseline_score.total_score:.1f}/100")
    print(f"Summary: {baseline_score.summary}")
    print()

    # 3. Propose candidate patches to improve coverage
    print("=" * 80)
    print("STEP 3: Propose Candidate Patches")
    print("=" * 80)
    print()

    # Candidate 1: Add flags and record_count fields to Header
    patch_1 = Patch(
        ops=(
            InsertField(
                path=("types", "Header"),
                index=-1,
                field_def={"name": "flags", "type": "u16"}
            ),
            InsertField(
                path=("types", "Header"),
                index=-1,
                field_def={"name": "record_count", "type": "u8"}
            ),
        ),
        description="Extend Header with flags and record_count"
    )

    # Candidate 2: Add flags but with wrong type (u8 instead of u16)
    patch_2 = Patch(
        ops=(
            InsertField(
                path=("types", "Header"),
                index=-1,
                field_def={"name": "flags", "type": "u8"}  # Wrong! Should be u16
            ),
        ),
        description="Extend Header with flags (wrong type)"
    )

    # Candidate 3: Add complete record structure
    patch_3 = Patch(
        ops=(
            InsertField(
                path=("types", "Header"),
                index=-1,
                field_def={"name": "flags", "type": "u16"}
            ),
            InsertField(
                path=("types", "Header"),
                index=-1,
                field_def={"name": "record_count", "type": "u8"}
            ),
        ),
        description="Complete header structure"
    )

    patches = [patch_1, patch_2, patch_3]

    for i, patch in enumerate(patches, 1):
        print(f"Candidate {i}: {patch.description}")
        print(f"  Operations: {len(patch.ops)}")
        is_valid, errors = patch.validate()
        print(f"  Valid: {is_valid}")
        if errors:
            print(f"  Errors: {errors}")
    print()

    # 4. Apply patches and create candidate runs
    print("=" * 80)
    print("STEP 4: Apply Patches and Parse")
    print("=" * 80)
    print()

    candidate_runs = []

    for i, patch in enumerate(patches, 1):
        print(f"Applying candidate {i}...")

        # Apply patch
        result = store.apply_patch(initial_version.id, patch, run_lint=True)

        if result.success:
            print(f"  ✓ Patch applied successfully")

            # Get new version
            new_version = store.get(result.new_spec_id)

            # Parse with new spec
            grammar_new = ToolHost.lint_grammar(LintGrammarInput(yaml_text=new_version.spec_text))
            if grammar_new.success:
                parse_new = ToolHost.parse_binary(
                    ParseBinaryInput(
                        grammar=grammar_new.grammar,
                        file_path=binary_file,
                        max_records=100
                    )
                )

                run_artifact = create_run_artifact(
                    run_id=f"candidate_{i}_run",
                    spec_version_id=new_version.id,
                    parse_result=parse_new,
                    file_path=binary_file,
                    file_size=file_size
                )

                candidate_runs.append((i, run_artifact))

                print(f"  Coverage: {run_artifact.stats.coverage_percentage:.1f}%")
                print(f"  Errors: {run_artifact.stats.error_count}")
            else:
                print(f"  ✗ Grammar lint failed")
        else:
            print(f"  ✗ Patch failed: {result.errors[0]}")
        print()

    # 5. Compare runs using diff
    print("=" * 80)
    print("STEP 5: Compare Runs with Baseline")
    print("=" * 80)
    print()

    for i, run in candidate_runs:
        diff = diff_runs(baseline_run, run)
        print(f"Candidate {i}:")
        print(f"  {diff.summary}")
        print(f"  Improvement: {'✓' if diff.is_improvement() else '✗'}")
        print()

    # 6. Score and rank candidates
    print("=" * 80)
    print("STEP 6: Score and Rank Candidates")
    print("=" * 80)
    print()

    runs_only = [run for _, run in candidate_runs]

    for i, run in candidate_runs:
        score = score_run(run, baseline_run)
        print(f"Candidate {i}:")
        print(f"  Score: {score.total_score:.1f}/100")
        print(f"  Passed gates: {'✓' if score.passed_hard_gates else '✗'}")
        print(f"  {score.summary}")
        print()

    # 7. Find best candidate
    print("=" * 80)
    print("STEP 7: Select Best Candidate")
    print("=" * 80)
    print()

    # Using diff-based comparison
    best_by_diff, best_diff = find_best_run(baseline_run, runs_only)

    if best_by_diff:
        print("Best by diff criteria:")
        print(f"  Run: {best_by_diff.run_id}")
        print(f"  Spec: {best_by_diff.spec_version_id}")
        print(f"  Coverage: {best_by_diff.stats.coverage_percentage:.1f}%")
        print(f"  {best_diff.summary}")
        print()

    # Using scoring
    best_by_score, best_score_breakdown = find_best_scoring_run(runs_only, baseline_run)

    if best_by_score:
        print("Best by scoring:")
        print(f"  Run: {best_by_score.run_id}")
        print(f"  Spec: {best_by_score.spec_version_id}")
        print(f"  Score: {best_score_breakdown.total_score:.1f}/100")
        print(f"  {best_score_breakdown.summary}")
        print()

    # Cleanup
    Path(binary_file).unlink()
    print("Demo complete!")
    print()


def example_2_version_lineage():
    """Example 2: Track version lineage through multiple iterations."""
    print("=" * 80)
    print("EXAMPLE 2: Version Lineage Tracking")
    print("=" * 80)
    print()

    # Create spec store
    store = SpecStore()

    # Create initial version
    initial_yaml = """
types:
  Header:
    fields:
      - name: magic
        type: u16
"""

    v1 = store.create_initial(initial_yaml, run_lint=False)
    print(f"Version 1: {v1.id} (initial)")

    # Apply series of patches
    patch_2 = Patch(
        ops=(
            InsertField(
                path=("types", "Header"),
                index=-1,
                field_def={"name": "version", "type": "u8"}
            ),
        ),
        description="Add version field"
    )

    result_2 = store.apply_patch(v1.id, patch_2, run_lint=False)
    print(f"Version 2: {result_2.new_spec_id} (added version)")

    patch_3 = Patch(
        ops=(
            InsertField(
                path=("types", "Header"),
                index=-1,
                field_def={"name": "flags", "type": "u16"}
            ),
        ),
        description="Add flags field"
    )

    result_3 = store.apply_patch(result_2.new_spec_id, patch_3, run_lint=False)
    print(f"Version 3: {result_3.new_spec_id} (added flags)")

    # Show lineage
    lineage = store.get_lineage(result_3.new_spec_id)
    print()
    print("Version lineage (root to current):")
    for i, version_id in enumerate(lineage, 1):
        version = store.get(version_id)
        desc = version.patch_applied.description if version.patch_applied else "initial"
        print(f"  {i}. {version_id}: {desc}")
    print()

    # Show diff between versions
    diff = store.diff_specs(v1.id, result_3.new_spec_id)
    print(f"Changes from v1 to v3:")
    for change in diff.changes:
        print(f"  - {change}")
    print()


def example_3_detailed_scoring():
    """Example 3: Detailed score breakdown and reporting."""
    print("=" * 80)
    print("EXAMPLE 3: Detailed Score Breakdown")
    print("=" * 80)
    print()

    # Create test binary
    binary_file = create_test_binary()
    file_size = Path(binary_file).stat().st_size

    # Create two different specs
    yaml_1 = """
types:
  Header:
    fields:
      - name: magic
        type: u16
      - name: version
        type: u8
"""

    yaml_2 = """
types:
  Header:
    fields:
      - name: magic
        type: u16
      - name: version
        type: u8
      - name: flags
        type: u16
      - name: record_count
        type: u8
"""

    # Parse with both specs
    grammar_1 = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml_1))
    parse_1 = ToolHost.parse_binary(
        ParseBinaryInput(
            grammar=grammar_1.grammar,
            file_path=binary_file,
            max_records=100
        )
    )
    run_1 = create_run_artifact("run_1", "spec_1", parse_1, binary_file, file_size)

    grammar_2 = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml_2))
    parse_2 = ToolHost.parse_binary(
        ParseBinaryInput(
            grammar=grammar_2.grammar,
            file_path=binary_file,
            max_records=100
        )
    )
    run_2 = create_run_artifact("run_2", "spec_2", parse_2, binary_file, file_size)

    # Get detailed score reports
    score_1 = score_run(run_1)
    score_2 = score_run(run_2)

    print("Score Report for Run 1:")
    print(format_score_report(run_1, score_1, verbose=True))

    print("Score Report for Run 2:")
    print(format_score_report(run_2, score_2, verbose=True))

    # Compare scores
    print("Comparison:")
    print(compare_scores(run_1, run_2))

    # Cleanup
    Path(binary_file).unlink()


def main():
    """Run all examples."""
    print()
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 20 + "SPEC ITERATION DEMO (Phase 7)" + " " * 29 + "║")
    print("╚" + "═" * 78 + "╝")
    print()

    try:
        example_1_basic_workflow()
        print("\n" + "=" * 80 + "\n")
        example_2_version_lineage()
        print("\n" + "=" * 80 + "\n")
        example_3_detailed_scoring()

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    print()
    print("✅ All examples completed successfully!")
    print()
    return 0


if __name__ == "__main__":
    exit(main())
