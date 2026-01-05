"""Run comparison and diffing utilities.

This module provides tools for comparing parse runs to understand
how spec changes affect parsing results.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hexmap.core.run_artifacts import RunArtifact


# ============================================================================
# RUN DIFF
# ============================================================================

@dataclass(frozen=True)
class RunDiff:
    """Structured diff between two parse runs.

    Attributes:
        run_a_id: First run ID
        run_b_id: Second run ID
        coverage_delta: Change in coverage percentage (b - a)
        bytes_parsed_delta: Change in bytes parsed (b - a)
        record_count_delta: Change in record count (b - a)
        error_delta: Change in error count (b - a, negative = improvement)
        anomaly_delta: Change in anomaly count (b - a, negative = improvement)
        high_severity_delta: Change in high severity anomalies (b - a)
        summary: Human-readable summary
    """
    run_a_id: str
    run_b_id: str
    coverage_delta: float
    bytes_parsed_delta: int
    record_count_delta: int
    error_delta: int
    anomaly_delta: int
    high_severity_delta: int
    summary: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "run_a_id": self.run_a_id,
            "run_b_id": self.run_b_id,
            "coverage_delta": self.coverage_delta,
            "bytes_parsed_delta": self.bytes_parsed_delta,
            "record_count_delta": self.record_count_delta,
            "error_delta": self.error_delta,
            "anomaly_delta": self.anomaly_delta,
            "high_severity_delta": self.high_severity_delta,
            "summary": self.summary,
        }

    def is_improvement(self) -> bool:
        """Check if run B is an improvement over run A.

        Improvement criteria:
        - Coverage increased (or stayed same)
        - Errors decreased (or stayed same)
        - High severity anomalies decreased (or stayed same)

        Returns:
            True if run B improves on run A
        """
        return (
            self.coverage_delta >= 0 and
            self.error_delta <= 0 and
            self.high_severity_delta <= 0
        )


def diff_runs(run_a: RunArtifact, run_b: RunArtifact) -> RunDiff:
    """Compare two parse runs.

    Args:
        run_a: First run artifact
        run_b: Second run artifact

    Returns:
        RunDiff describing changes from A to B
    """
    stats_a = run_a.stats
    stats_b = run_b.stats

    # Compute deltas
    coverage_delta = stats_b.coverage_percentage - stats_a.coverage_percentage
    bytes_parsed_delta = stats_b.total_bytes_parsed - stats_a.total_bytes_parsed
    record_count_delta = stats_b.record_count - stats_a.record_count
    error_delta = stats_b.error_count - stats_a.error_count
    anomaly_delta = stats_b.anomaly_count - stats_a.anomaly_count
    high_severity_delta = stats_b.high_severity_anomalies - stats_a.high_severity_anomalies

    # Build summary
    summary_parts = []

    if coverage_delta > 0:
        summary_parts.append(f"Coverage improved by {coverage_delta:.1f}%")
    elif coverage_delta < 0:
        summary_parts.append(f"Coverage decreased by {abs(coverage_delta):.1f}%")
    else:
        summary_parts.append("Coverage unchanged")

    if error_delta < 0:
        summary_parts.append(f"Fixed {abs(error_delta)} error(s)")
    elif error_delta > 0:
        summary_parts.append(f"Introduced {error_delta} new error(s)")

    if high_severity_delta < 0:
        summary_parts.append(f"Reduced {abs(high_severity_delta)} high severity anomaly(ies)")
    elif high_severity_delta > 0:
        summary_parts.append(f"Introduced {high_severity_delta} high severity anomaly(ies)")

    if record_count_delta > 0:
        summary_parts.append(f"Parsed {record_count_delta} more record(s)")
    elif record_count_delta < 0:
        summary_parts.append(f"Parsed {abs(record_count_delta)} fewer record(s)")

    summary = "; ".join(summary_parts) if summary_parts else "No significant changes"

    return RunDiff(
        run_a_id=run_a.run_id,
        run_b_id=run_b.run_id,
        coverage_delta=coverage_delta,
        bytes_parsed_delta=bytes_parsed_delta,
        record_count_delta=record_count_delta,
        error_delta=error_delta,
        anomaly_delta=anomaly_delta,
        high_severity_delta=high_severity_delta,
        summary=summary,
    )


# ============================================================================
# COMPARISON UTILITIES
# ============================================================================

def compare_multiple_runs(baseline: RunArtifact, candidates: list[RunArtifact]) -> list[RunDiff]:
    """Compare multiple candidate runs against a baseline.

    Args:
        baseline: Baseline run to compare against
        candidates: List of candidate runs

    Returns:
        List of RunDiff objects, one for each candidate
    """
    return [diff_runs(baseline, candidate) for candidate in candidates]


def find_best_run(baseline: RunArtifact, candidates: list[RunArtifact]) -> tuple[RunArtifact | None, RunDiff | None]:
    """Find the best candidate run compared to baseline.

    "Best" is defined as:
    1. Must be an improvement (coverage up, errors down)
    2. Among improvements, prefer highest coverage increase
    3. Break ties by lowest anomaly count

    Args:
        baseline: Baseline run
        candidates: List of candidate runs

    Returns:
        (best_run, diff_from_baseline) or (None, None) if no improvements
    """
    if not candidates:
        return None, None

    # Compute diffs
    diffs = compare_multiple_runs(baseline, candidates)

    # Filter to improvements only
    improvements = [
        (candidate, diff)
        for candidate, diff in zip(candidates, diffs)
        if diff.is_improvement()
    ]

    if not improvements:
        return None, None

    # Sort by coverage delta (descending), then by anomaly count (ascending)
    improvements.sort(
        key=lambda x: (-x[1].coverage_delta, x[0].stats.anomaly_count)
    )

    return improvements[0]


def format_diff_report(diff: RunDiff, verbose: bool = False) -> str:
    """Format a diff as a human-readable report.

    Args:
        diff: RunDiff to format
        verbose: Include detailed metrics

    Returns:
        Formatted report string
    """
    lines = []
    lines.append("=" * 70)
    lines.append("RUN COMPARISON")
    lines.append("=" * 70)
    lines.append("")
    lines.append(f"Run A: {diff.run_a_id}")
    lines.append(f"Run B: {diff.run_b_id}")
    lines.append("")
    lines.append("SUMMARY")
    lines.append(f"  {diff.summary}")
    lines.append("")

    if verbose:
        lines.append("METRICS")
        lines.append(f"  Coverage:        {diff.coverage_delta:+.1f}%")
        lines.append(f"  Bytes parsed:    {diff.bytes_parsed_delta:+d}")
        lines.append(f"  Records:         {diff.record_count_delta:+d}")
        lines.append(f"  Errors:          {diff.error_delta:+d}")
        lines.append(f"  Anomalies:       {diff.anomaly_delta:+d}")
        lines.append(f"  High severity:   {diff.high_severity_delta:+d}")
        lines.append("")

    lines.append(f"VERDICT: {'✓ IMPROVEMENT' if diff.is_improvement() else '✗ NOT AN IMPROVEMENT'}")
    lines.append("")

    return "\n".join(lines)
