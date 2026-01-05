"""Run artifacts and anomaly detection for spec evaluation.

This module ties together parsing results with anomaly detection to create
comprehensive run artifacts for comparing different spec versions.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from hexmap.core.tool_host import AnalyzeCoverageInput, ParseResult, ToolHost


# ============================================================================
# ANOMALY DETECTION
# ============================================================================

@dataclass(frozen=True)
class Anomaly:
    """Detected anomaly in parsed data.

    Attributes:
        type: Type of anomaly (absurd_length, field_overflow, etc.)
        severity: high, medium, low
        record_offset: Offset of affected record
        field_name: Name of affected field (if applicable)
        message: Human-readable description
        value: Problematic value (if applicable)
    """
    type: str
    severity: str
    record_offset: int
    field_name: str | None = None
    message: str = ""
    value: Any = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "type": self.type,
            "severity": self.severity,
            "record_offset": self.record_offset,
            "field_name": self.field_name,
            "message": self.message,
            "value": self.value,
        }


def detect_anomalies(parse_result: ParseResult) -> tuple[Anomaly, ...]:
    """Detect anomalies in parsed records.

    Uses deterministic heuristics to identify:
    - Absurdly large length fields
    - Fields that overflow record boundaries
    - Suspiciously small/large values
    - Parsing errors

    Args:
        parse_result: Parse result to analyze

    Returns:
        Tuple of detected anomalies
    """
    anomalies = []

    # Check for parse errors
    for error in parse_result.errors:
        # Extract offset from error message if present
        offset = 0
        if "at" in error and "0x" in error:
            try:
                offset_str = error.split("0x")[1].split(":")[0].split(" ")[0]
                offset = int(offset_str, 16)
            except:
                pass

        anomalies.append(
            Anomaly(
                type="parse_error",
                severity="high",
                record_offset=offset,
                message=error,
            )
        )

    # Analyze each record
    for record in parse_result.records:
        # Check for errors in record
        if record.error:
            anomalies.append(
                Anomaly(
                    type="record_error",
                    severity="high",
                    record_offset=record.offset,
                    message=record.error,
                )
            )

        # Check each field
        for field_name, field in record.fields.items():
            # Check for absurdly large length fields
            if "length" in field_name.lower():
                if isinstance(field.value, int):
                    # Length > 10MB is suspicious
                    if field.value > 10 * 1024 * 1024:
                        anomalies.append(
                            Anomaly(
                                type="absurd_length",
                                severity="high",
                                record_offset=record.offset,
                                field_name=field_name,
                                message=f"Length field {field.value} exceeds 10MB",
                                value=field.value,
                            )
                        )
                    # Length > 1MB is worth noting
                    elif field.value > 1024 * 1024:
                        anomalies.append(
                            Anomaly(
                                type="large_length",
                                severity="medium",
                                record_offset=record.offset,
                                field_name=field_name,
                                message=f"Length field {field.value} exceeds 1MB",
                                value=field.value,
                            )
                        )

            # Check for fields larger than containing record
            if field.size > record.size:
                anomalies.append(
                    Anomaly(
                        type="field_overflow",
                        severity="high",
                        record_offset=record.offset,
                        field_name=field_name,
                        message=f"Field size {field.size} exceeds record size {record.size}",
                        value=field.size,
                    )
                )

            # Check for suspiciously small integers in "count" fields
            if "count" in field_name.lower():
                if isinstance(field.value, int) and field.value == 0:
                    anomalies.append(
                        Anomaly(
                            type="zero_count",
                            severity="low",
                            record_offset=record.offset,
                            field_name=field_name,
                            message=f"Count field is zero",
                            value=0,
                        )
                    )

    return tuple(anomalies)


# ============================================================================
# RUN STATISTICS
# ============================================================================

@dataclass(frozen=True)
class RunStats:
    """Statistics about a parse run.

    Attributes:
        record_count: Number of records parsed
        total_bytes_parsed: Total bytes consumed
        parse_stopped_at: Offset where parsing stopped
        file_size: Size of input file
        coverage_percentage: Percentage of file covered
        error_count: Number of parse errors
        anomaly_count: Number of anomalies detected
        high_severity_anomalies: Count of high severity anomalies
    """
    record_count: int
    total_bytes_parsed: int
    parse_stopped_at: int
    file_size: int
    coverage_percentage: float
    error_count: int
    anomaly_count: int
    high_severity_anomalies: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "record_count": self.record_count,
            "total_bytes_parsed": self.total_bytes_parsed,
            "parse_stopped_at": self.parse_stopped_at,
            "file_size": self.file_size,
            "coverage_percentage": self.coverage_percentage,
            "error_count": self.error_count,
            "anomaly_count": self.anomaly_count,
            "high_severity_anomalies": self.high_severity_anomalies,
        }


def compute_stats(
    parse_result: ParseResult,
    file_size: int,
    anomalies: tuple[Anomaly, ...]
) -> RunStats:
    """Compute statistics for a parse run.

    Args:
        parse_result: Parse result
        file_size: Size of input file
        anomalies: Detected anomalies

    Returns:
        RunStats with computed statistics
    """
    # Compute coverage
    coverage = ToolHost.analyze_coverage(
        AnalyzeCoverageInput(parse_result=parse_result, file_size=file_size)
    )

    # Count high severity anomalies
    high_severity_count = sum(1 for a in anomalies if a.severity == "high")

    return RunStats(
        record_count=parse_result.record_count,
        total_bytes_parsed=parse_result.total_bytes_parsed,
        parse_stopped_at=parse_result.parse_stopped_at,
        file_size=file_size,
        coverage_percentage=coverage.coverage_percentage,
        error_count=len(parse_result.errors),
        anomaly_count=len(anomalies),
        high_severity_anomalies=high_severity_count,
    )


# ============================================================================
# RUN ARTIFACT
# ============================================================================

@dataclass(frozen=True)
class RunArtifact:
    """Complete artifact from a parse run.

    Ties together spec version, parse results, coverage, and anomalies.

    Attributes:
        run_id: Unique ID for this run
        spec_version_id: ID of spec version used
        created_at: Unix timestamp
        parse_result: Parse result from ToolHost
        file_path: Path to parsed file
        file_size: Size of parsed file
        anomalies: Detected anomalies
        stats: Computed statistics
    """
    run_id: str
    spec_version_id: str
    created_at: float
    parse_result: ParseResult
    file_path: str
    file_size: int
    anomalies: tuple[Anomaly, ...]
    stats: RunStats

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict (excluding large fields)."""
        return {
            "run_id": self.run_id,
            "spec_version_id": self.spec_version_id,
            "created_at": self.created_at,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "anomaly_count": len(self.anomalies),
            "stats": self.stats.to_dict(),
        }


def create_run_artifact(
    run_id: str,
    spec_version_id: str,
    parse_result: ParseResult,
    file_path: str,
    file_size: int,
) -> RunArtifact:
    """Create run artifact from parse result.

    Args:
        run_id: Unique ID for this run
        spec_version_id: ID of spec version used
        parse_result: Parse result from ToolHost
        file_path: Path to parsed file
        file_size: Size of parsed file

    Returns:
        Complete RunArtifact with anomalies and stats
    """
    # Detect anomalies
    anomalies = detect_anomalies(parse_result)

    # Compute stats
    stats = compute_stats(parse_result, file_size, anomalies)

    return RunArtifact(
        run_id=run_id,
        spec_version_id=spec_version_id,
        created_at=time.time(),
        parse_result=parse_result,
        file_path=file_path,
        file_size=file_size,
        anomalies=anomalies,
        stats=stats,
    )
