"""Scoring and ranking system for parse runs.

This module provides deterministic scoring to rank parse runs and identify
the best spec versions for a given binary file.

Key Concepts:
- Hard gates: Must pass to receive any score
- Soft metrics: Contribute to final 0-100 score
- Deterministic: Same inputs always produce same score
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hexmap.core.run_artifacts import RunArtifact


# ============================================================================
# SCORE BREAKDOWN
# ============================================================================

@dataclass(frozen=True)
class ScoreBreakdown:
    """Detailed breakdown of a run's score.

    Attributes:
        total_score: Final score (0-100, or -1 if failed hard gates)
        passed_hard_gates: Whether all hard gates passed
        hard_gate_results: Dict of hard gate results
        soft_metrics: Dict of soft metric scores
        penalties: Dict of penalty deductions
        summary: Human-readable summary
    """
    total_score: float
    passed_hard_gates: bool
    hard_gate_results: dict[str, bool]
    soft_metrics: dict[str, float]
    penalties: dict[str, float]
    summary: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "total_score": self.total_score,
            "passed_hard_gates": self.passed_hard_gates,
            "hard_gate_results": self.hard_gate_results,
            "soft_metrics": self.soft_metrics,
            "penalties": self.penalties,
            "summary": self.summary,
        }


# ============================================================================
# SCORING FUNCTION
# ============================================================================

def score_run(
    run: RunArtifact,
    baseline: RunArtifact | None = None
) -> ScoreBreakdown:
    """Score a parse run using hard gates and soft metrics.

    Hard Gates (all must pass):
    - parse_advanced: Parser must make progress (bytes_parsed > 0)
    - no_safety_violations: No high severity anomalies

    Soft Metrics (0-100 scale):
    - coverage_score: Based on coverage percentage
    - error_penalty: Deduction for parse errors
    - anomaly_penalty: Deduction for anomalies

    Args:
        run: RunArtifact to score
        baseline: Optional baseline for relative scoring

    Returns:
        ScoreBreakdown with total score and detailed breakdown
    """
    # Check hard gates
    hard_gate_results = {}
    # We assume grammar was valid if parse was attempted (can't check lint_valid from RunArtifact alone)
    # If parse failed completely, parse_advanced will catch it
    hard_gate_results["parse_advanced"] = run.stats.total_bytes_parsed > 0
    hard_gate_results["no_safety_violations"] = run.stats.high_severity_anomalies == 0

    passed_hard_gates = all(hard_gate_results.values())

    # If any hard gate fails, return -1 score
    if not passed_hard_gates:
        failed_gates = [name for name, passed in hard_gate_results.items() if not passed]
        return ScoreBreakdown(
            total_score=-1.0,
            passed_hard_gates=False,
            hard_gate_results=hard_gate_results,
            soft_metrics={},
            penalties={},
            summary=f"Failed hard gates: {', '.join(failed_gates)}",
        )

    # Compute soft metrics
    soft_metrics = {}
    penalties = {}

    # Coverage score (0-100)
    coverage_score = min(100.0, run.stats.coverage_percentage)
    soft_metrics["coverage"] = coverage_score

    # Error penalty (5 points per error, max 50 points)
    error_penalty = min(50.0, run.stats.error_count * 5.0)
    penalties["errors"] = error_penalty

    # Anomaly penalty (2 points per anomaly, max 30 points)
    anomaly_penalty = min(30.0, run.stats.anomaly_count * 2.0)
    penalties["anomalies"] = anomaly_penalty

    # Compute total score
    total_score = coverage_score - error_penalty - anomaly_penalty

    # Clamp to 0-100 range
    total_score = max(0.0, min(100.0, total_score))

    # Build summary
    summary_parts = []
    summary_parts.append(f"Coverage: {coverage_score:.1f}%")

    if error_penalty > 0:
        summary_parts.append(f"Error penalty: -{error_penalty:.1f}")

    if anomaly_penalty > 0:
        summary_parts.append(f"Anomaly penalty: -{anomaly_penalty:.1f}")

    summary_parts.append(f"Final score: {total_score:.1f}")

    # Add baseline comparison if provided
    if baseline is not None:
        baseline_score_breakdown = score_run(baseline)
        if baseline_score_breakdown.passed_hard_gates:
            delta = total_score - baseline_score_breakdown.total_score
            if delta > 0:
                summary_parts.append(f"(+{delta:.1f} vs baseline)")
            elif delta < 0:
                summary_parts.append(f"({delta:.1f} vs baseline)")
            else:
                summary_parts.append("(same as baseline)")

    summary = "; ".join(summary_parts)

    return ScoreBreakdown(
        total_score=total_score,
        passed_hard_gates=True,
        hard_gate_results=hard_gate_results,
        soft_metrics=soft_metrics,
        penalties=penalties,
        summary=summary,
    )


# ============================================================================
# RANKING UTILITIES
# ============================================================================

def rank_runs(runs: list[RunArtifact]) -> list[tuple[RunArtifact, ScoreBreakdown]]:
    """Rank multiple runs by score.

    Args:
        runs: List of RunArtifacts to rank

    Returns:
        List of (run, score_breakdown) tuples, sorted by score descending
    """
    scored_runs = [(run, score_run(run)) for run in runs]

    # Sort by total score descending
    scored_runs.sort(key=lambda x: x[1].total_score, reverse=True)

    return scored_runs


def find_best_scoring_run(
    runs: list[RunArtifact],
    baseline: RunArtifact | None = None
) -> tuple[RunArtifact | None, ScoreBreakdown | None]:
    """Find the highest scoring run.

    Args:
        runs: List of candidate runs
        baseline: Optional baseline for comparison

    Returns:
        (best_run, score_breakdown) or (None, None) if no runs pass hard gates
    """
    if not runs:
        return None, None

    # Score all runs
    scored_runs = [(run, score_run(run, baseline)) for run in runs]

    # Filter to those that passed hard gates
    passed_runs = [
        (run, score)
        for run, score in scored_runs
        if score.passed_hard_gates
    ]

    if not passed_runs:
        return None, None

    # Sort by total score descending
    passed_runs.sort(key=lambda x: x[1].total_score, reverse=True)

    return passed_runs[0]


def format_score_report(
    run: RunArtifact,
    score: ScoreBreakdown,
    verbose: bool = False
) -> str:
    """Format a score as a human-readable report.

    Args:
        run: RunArtifact that was scored
        score: Score breakdown
        verbose: Include detailed metrics

    Returns:
        Formatted report string
    """
    lines = []
    lines.append("=" * 70)
    lines.append("RUN SCORE REPORT")
    lines.append("=" * 70)
    lines.append("")
    lines.append(f"Run ID: {run.run_id}")
    lines.append(f"Spec Version: {run.spec_version_id}")
    lines.append("")

    if not score.passed_hard_gates:
        lines.append("HARD GATES: FAILED")
        lines.append("")
        for gate_name, passed in score.hard_gate_results.items():
            status = "✓" if passed else "✗"
            lines.append(f"  {status} {gate_name}")
        lines.append("")
        lines.append(f"TOTAL SCORE: {score.total_score:.1f} (FAILED)")
    else:
        lines.append("HARD GATES: PASSED ✓")
        lines.append("")

        if verbose:
            for gate_name, passed in score.hard_gate_results.items():
                lines.append(f"  ✓ {gate_name}")
            lines.append("")

        lines.append("SOFT METRICS")
        for metric_name, metric_value in score.soft_metrics.items():
            lines.append(f"  {metric_name}: {metric_value:.1f}")
        lines.append("")

        if score.penalties:
            lines.append("PENALTIES")
            for penalty_name, penalty_value in score.penalties.items():
                lines.append(f"  {penalty_name}: -{penalty_value:.1f}")
            lines.append("")

        lines.append(f"TOTAL SCORE: {score.total_score:.1f} / 100")
        lines.append("")

    lines.append("SUMMARY")
    lines.append(f"  {score.summary}")
    lines.append("")

    return "\n".join(lines)


def compare_scores(
    run_a: RunArtifact,
    run_b: RunArtifact
) -> str:
    """Compare scores of two runs.

    Args:
        run_a: First run
        run_b: Second run

    Returns:
        Human-readable comparison summary
    """
    score_a = score_run(run_a)
    score_b = score_run(run_b)

    lines = []
    lines.append("=" * 70)
    lines.append("SCORE COMPARISON")
    lines.append("=" * 70)
    lines.append("")
    lines.append(f"Run A: {run_a.run_id} (spec: {run_a.spec_version_id})")
    lines.append(f"  Score: {score_a.total_score:.1f}")
    lines.append(f"  {score_a.summary}")
    lines.append("")
    lines.append(f"Run B: {run_b.run_id} (spec: {run_b.spec_version_id})")
    lines.append(f"  Score: {score_b.total_score:.1f}")
    lines.append(f"  {score_b.summary}")
    lines.append("")

    # Determine winner
    if not score_a.passed_hard_gates and not score_b.passed_hard_gates:
        lines.append("RESULT: Both runs failed hard gates")
    elif not score_a.passed_hard_gates:
        lines.append("RESULT: Run B wins (Run A failed hard gates)")
    elif not score_b.passed_hard_gates:
        lines.append("RESULT: Run A wins (Run B failed hard gates)")
    else:
        delta = score_b.total_score - score_a.total_score
        if delta > 0:
            lines.append(f"RESULT: Run B wins by {delta:.1f} points")
        elif delta < 0:
            lines.append(f"RESULT: Run A wins by {abs(delta):.1f} points")
        else:
            lines.append("RESULT: Tie (same score)")

    lines.append("")

    return "\n".join(lines)
